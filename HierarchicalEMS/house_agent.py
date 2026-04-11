# house_agent.py
import pulp
from config import *
from data import *
import random
import copy
import scipy.stats as stats


class HouseAgent:
    def __init__(self, house_id, pv_capacity, battery_capacity, house_limit):
        # House physical hardware
        self.house_id = house_id
        self.house_limit = house_limit
        self.pv_capacity = pv_capacity
        self.battery_capacity = battery_capacity

        self.current_soc =  S_init
        self.open_soc = S_init
        self.current_soc_th = 0.25 * C_TH
        self.appliances_already_run = {app["name"]: False for app in appliances}
        self.history_E = {}
        self.history_T_in = []

        self.current_T_fridge = 4.0
        self.current_T_freezer = -18.0

        self.alpha = 0.1                       # Define risk tolerance, 0.05 = 95% guarantee of safety
        self.sigma_human = 0.75           # ~ 0.75 kW standard deviation

        self.daily_total_uncontrolled_energy = 0.0
        self.daily_total_controlled_energy = 0.0
        self.current_T_in = 20.0
        
    
        # Add randomness
        magnitude = random.uniform(0.7, 1.3)    # +/- 30% of total energy use
        time_shift = random.randint(-3, 3)      # +/- 1.5 hours of routine shift

        total_len = len(electric_demand_per_house)
        self.personal_elec_demand = [
            electric_demand_per_house[(i - time_shift) % total_len] * magnitude
            for i in range(total_len)
        ]


        self.flexible_energy_delivered = {}
        for app in appliances:
            if app.get("power_type") == "flexible":
                self.flexible_energy_delivered[app["name"]] = 0.0

        # Pregenerating randomness
       

        self.rogue_spikes_timeline = [
            random.choice([1.5, 2.5, 3.5]) if random.random() < 0.10 else 0.0
            for _ in range(total_steps * 2)
        ]    

        self.noise = [random.uniform(-0.05, 0.05) for _ in range(48)]

        self.randomise_daily_appliances()

        

    def randomise_daily_appliances(self):
        # Generate a fresh schedule for each day
        # Appliance window variance and continuous-time random allocation
        # Decide which appliances run based on probability of occurence
        new_daily_appliances = []

        for app in copy.deepcopy(appliances):
            name = app["name"]
            is_mid_cycle = False

            # Check if the EV is currently mid-charge from yesterday
            if app.get("power_type") == "flexible":
                delivered = self.flexible_energy_delivered.get(name, 0.0)
                # If has some charge, it is mid cycle
                is_mid_cycle = delivered > 0.0

            if app.get("power_type") == "constant":
                duration_steps = int(app["Slots"])
                for past_k in range(1, duration_steps + 1):
                    past_t = total_steps - past_k
                    if self.history_E.get((name, past_t), 0) == 1:
                        is_mid_cycle = True
                        break
            
            if is_mid_cycle:
                # Find yesterday's exact safe profile in self.personal_appliances
                yesterdays_app = next((a for a in getattr(self, 'personal_appliances', []) if a["name"] == name), None)
                if yesterdays_app:
                    new_daily_appliances.append(yesterdays_app)
                continue # Skip the rest of the randomizer for this specific appliance

            if "prob" in app and random.random() > app["prob"]:
                continue

            window_shift = random.uniform(-2.0, 2.0)

            # apply shift but keep within 0-24 bounds
            new_ts = (app["T_S"] + window_shift) % 24.0
            new_tf = (app["T_F"] + window_shift) % 24.0
            app["T_S"] = new_ts
            app["T_F"] = new_tf

            # Calculat exact physical duration in hours
            if app.get("power_type") == "constant":
                duration_hours = int(app["Slots"]) * delta
            else:
                duration_hours = app["Required_Energy"] / app["Max_Power"]
                # To allow flattening the window must be large enough to charge at min_power
                min_flat_window = app["Required_Energy"] / app.get("Min_Power", 1.5)

                # Force the deadline to extend if the random window is too tight
                adjusted_tf_temp = new_tf if new_tf >= new_ts else new_tf + 24.0
                if (adjusted_tf_temp - new_ts) < min_flat_window:
                    new_tf = (new_ts + min_flat_window) % 24.0
                    
                    app["T_F"] = new_tf 

            # Handle widnows that cross midnight
            adjusted_tf = new_tf if new_tf >= new_ts else new_tf + 24.0
            
            if app.get("power_type") == "flexible":
                # The user must plug it in with enough time to do a slow, flat charge
                latest_start = adjusted_tf - min_flat_window
            else:
                # Constant appliances use their fixed duration
                latest_start = adjusted_tf - duration_hours

            # Pick a completely continuous rnadom fractional hour: when the user actually turns on the appliance
            if latest_start > new_ts:
                human_start_hour = random.uniform(new_ts, latest_start)
            else:
                human_start_hour = new_ts
            
            app["human_start_hour"] = human_start_hour % 24.0
            app["human_duration_hours"] = duration_hours

            new_daily_appliances.append(app)
        
        self.personal_appliances = new_daily_appliances
        self.uncontrolled_appliances = [
            app for app in new_daily_appliances if not app.get('deferrable', True)
        ]

        # reset the tracker for today's specific appliances
        for app in self.personal_appliances:
            if not self.history_E.get((app["name"], total_steps -1 ), 0) == 1:
                self.appliances_already_run[app["name"]] = False
        ev = next((a for a in self.personal_appliances if a["name"] == "Electric car"), None)
        # if ev:
        #     print(f"--> House {self.house_id} EV Window: Plugs in at {ev['T_S']:.2f}, Needs full by {ev['T_F']:.2f}. Energy needed: {ev.get('Required_Energy', 0)} kWh")

    def generate_proposed_schedule(self, current_step, community_penalty_prices):
        # Lower level solver
        # Runs a 24 hour look ahead MPC using PuLP to minimise the house's nill
        # Takes the community penalty prices into account to avoid causing grid spikes


        if current_step > 0 and current_step % total_steps == 0:
            self.randomise_daily_appliances()

            for app_name in self.appliances_already_run:
                self.appliances_already_run[app_name]= False

        horizon = 48
        mpc_steps = range(horizon)

        model = pulp.LpProblem(f"House_{self.house_id}_Step_{current_step}", pulp.LpMinimize)

        # PuLP variable definition
        S_E = pulp.LpVariable.dicts(f"SoC_H{self.house_id}", mpc_steps, 0, self.battery_capacity)
        z = pulp.LpVariable.dicts(f"Charge_Rate_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        y = pulp.LpVariable.dicts(f"Discharge_Rate_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        I = pulp.LpVariable.dicts(f"Grid_Import_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        I_excess = pulp.LpVariable.dicts(f"Excess_Import_H{self.house_id}", mpc_steps, lowBound=0, cat='continuous')
        I_excess_eff = pulp.LpVariable.dicts(f"Excess_Eff_Import_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        I_export = pulp.LpVariable.dicts(f"Grid Export", mpc_steps, lowBound=0)
        # binary state (1 = Importing, 0 = Exporting)
        Z_grid = pulp.LpVariable.dicts(f"Grid_State_H{self.house_id}", mpc_steps, cat='Binary')

        P_HP = pulp.LpVariable.dicts(f"Heat_Pump_Power_H{self.house_id}", mpc_steps, lowBound=0, upBound=10.0, cat='Continuous')
        P_HP_Space = pulp.LpVariable.dicts(f"HP_Space_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        P_HP_DHW = pulp.LpVariable.dicts(f"P_HP_DHW{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        S_TH = pulp.LpVariable.dicts(f"SoC_Therm_H{self.house_id}", mpc_steps, 0, C_TH, cat='Continuous')
        T_in = pulp.LpVariable.dicts(f"T_house_H{self.house_id}", mpc_steps, lowBound=T_min, upBound=T_max, cat='Continuous')
        diff = pulp.LpVariable.dicts(f"T_diff_H{self.house_id}", mpc_steps, lowBound=0)                 # Comfort deviation variable     

        T_fr = pulp.LpVariable.dicts(f"T_fridge_H{self.house_id}", mpc_steps, lowBound=2, upBound=5, cat='Continuous')
        T_fz = pulp.LpVariable.dicts(f"T_freezer_H{self.house_id}", mpc_steps, lowBound=-22.0, upBound=-15.0, cat='Continuous')
        P_comp_fr = pulp.LpVariable.dicts(f"Fridge_Comp_Power_H{self.house_id}", mpc_steps, lowBound=0.0, upBound=0.3, cat='Continuous')
        P_comp_fz = pulp.LpVariable.dicts(f"Freezer_Comp_Power_H{self.house_id}", mpc_steps, lowBound=0.0, upBound=0.3, cat='Continuous')
        P_max_local = pulp.LpVariable(f"Peak_Import_H{self.house_id}", lowBound=0, cat='Continuous') 
        P_max_flex = pulp.LpVariable(f"Peak_Flex_H{self.house_id}", lowBound=0, cat='Continuous')

        # Chance constraint setup
        # Calculate the Z-score using the Inverse Cumulative Distribution Function
        z_score = stats.norm.ppf(1- self.alpha)
        safety_margin = z_score * self.sigma_human

        safety_margin_kw = z_score * self.sigma_human
        safety_reserve_kwh = safety_margin_kw * delta

        base_soc_floor = 0.05 * self.battery_capacity       # always keep a little bit regardless of sigma
        dynamic_soc_min = min(self.battery_capacity, base_soc_floor + safety_reserve_kwh)

        # Chance Constraint implementation
        # Shrink the house limit by the safety margin, if the margin is larger than the limit, floor it to prevent negative
        effective_limit = max(0.0, self.house_limit - safety_margin)

        E = {}       # For Type 1 & 2: Constant, Non-Interruptible (Start Times)
        P_flex = {}  # For Type 3: Flexible Power draw
        O_flex = {}  # For Type 3: Binary On/Off State (for minimum power limits)

        E_deficit = {}
        for app in self.personal_appliances:
            if app.get("power_type") == "flexible":
                E_deficit[app["name"]] = pulp.LpVariable(f"Deficit_{app['name']}_H{self.house_id}", lowBound=0, cat="Continuous")

        Reserve_deficit = pulp.LpVariable.dicts(f"Reserve_deficit_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')

        for app in self.personal_appliances:
            name = app["name"]
            for k in mpc_steps:
                if app["power_type"] == "constant":
                    E[(name, k)] = pulp.LpVariable(f"Start_{name}_H{self.house_id}_k{k}", cat='Binary')
                elif app["power_type"] == "flexible":
                    P_flex[(name, k)] = pulp.LpVariable(f"Power_{name}_H{self.house_id}_k{k}", lowBound=0, cat='Continuous')
                    O_flex[(name, k)] = pulp.LpVariable(f"State_{name}_H{self.house_id}_k{k}", cat='Binary')

        # Battery Limits and Dynamics Loop
        for k in mpc_steps:
            model += y[k] <= D_E, f"Discharge_Rate_Limit{k}"
            model += z[k] <= G_E, f"Charge_Limit{k}"
            model += I[k] <= self.house_limit + I_excess[k], f"Grid_limit_{k}"
            model += I[k] <= effective_limit +  I_excess_eff[k], f"Grid_limit_eff_{k}"

            M = 20.0  # Safe physical wire limit in kW
            model += I[k] <= M * Z_grid[k], f"Max_Import_State_{k}"
            model += I_export[k] <= M * (1 - Z_grid[k]), f"Max_Export_State_{k}"

            # The sum of unused grid capacity + unused battery discharge + interruptible charging
            # must always be capable of absorbing the suddent chance-constraint spikes
            # The battery inverter must always maintain enough headroom to absorb a rogue spike
            model += (D_E - y[k]) + z[k] >= safety_margin
            model += I[k] <= P_max_local, f"Track_Peak_{k}"

            # Sum flexible appliances AND the Heat Pump to squash them together
            flex_sum = pulp.lpSum([P_flex[(app["name"], k)] for app in self.personal_appliances if app.get("power_type") == "flexible" and (app["name"], k) in P_flex])
            
            # The £1.50 objective penalty will now force the EV and Heat Pump to flatten
            model += flex_sum + P_HP[k] <= P_max_flex, f"Track_Flex_Peak_{k}"
            # The battery is forced to keep enough energy to survive a 30-minute spike
           
            model += S_E[k] >= dynamic_soc_min - Reserve_deficit[k], f"Soft_Safety_Reserve_k{k}"
            
            # Storage Dynamics
            if k == 0:
                model += S_E[0] == self.current_soc + (nu_E * delta * z[0]) - (delta * y[0] / nu_E)
            else:
                # Subsequent steps look backwards at k-1
                model += S_E[k] == S_E[k-1] + (nu_E * delta * z[k]) - (delta * y[k] / nu_E)

          
            
        # Physical Constraints
        local_elec_demand = [self.personal_elec_demand[(current_step + k) % total_steps] for k in mpc_steps]
        #Local Data Arrays for this specific prediction horizon
        # Rogue user interjection
        rogue_power = self.rogue_spikes_timeline[current_step]
        
        # local_elec_demand[0] += rogue_power     # This is now handled as an unforeseen spike in the RTAS stage
        
        solar_generation_per_house = [self.pv_capacity * efficiency * multiplier for multiplier in solar_profile]
        local_solar_gen = [solar_generation_per_house[(current_step + k) % 48] for k in mpc_steps]

        flexible_load = {k: 0.0 for k in mpc_steps}
        locked_in_power = {k: 0.0 for k in mpc_steps}

        for app in self.personal_appliances:
            name = app["name"]
            power_type = app["power_type"]
            interruptible = app.get("interruptible", False)
            deferrable = app.get("deferrable", True)

            if power_type == "constant" and not interruptible:
                power = app["Power"]
                duration_steps = int(app["Slots"])

                if self.appliances_already_run.get(name) == True:
                    for k in mpc_steps:
                        model += E[(name, k)] == 0, f"Already_run_{name}_{k}"
                else:
                    abs_start_limit = int(app["T_S"] * steps_per_hour)
                    abs_end_limit = int(app["T_F"] * steps_per_hour - duration_steps) % total_steps

                    valid_k_starts = []
                    window_closed = False
                    found_window = False

                    for k in mpc_steps:
                        abs_t = (current_step + k) % total_steps
                        if abs_start_limit <= abs_end_limit:
                            is_valid = (abs_start_limit <= abs_t <= abs_end_limit)
                        else:
                            is_valid = (abs_t >= abs_start_limit or abs_t <= abs_end_limit)
                        
                        if is_valid:
                            if not window_closed:
                                valid_k_starts.append(k)
                                found_window = True
                            else:
                                model += E[name, k] == 0
                        else:
                            if found_window:
                                window_closed = True
                            model += E[name, k] == 0

                    if len(valid_k_starts) > 0:
                        model += pulp.lpSum(E[name, k] for k in valid_k_starts) == 1, f"Sched_{name}"

                # Calculate physical load profiles for constant appliances
                for k in mpc_steps:
                    # Future/present starts
                    possible_local_starts = [ks for ks in range(k - duration_steps + 1, k + 1) if ks >= 0]
                    flexible_load[k] += pulp.lpSum(E[(name, ks)] for ks in possible_local_starts) * power    

                    # Past loads still running (locked in)
                    for past_k in range(-duration_steps + 1, 0):
                        if (k - past_k) < duration_steps:
                            past_t = (current_step + past_k)
                            if self.history_E.get((name, past_t), 0) == 1:
                                locked_in_power[k] += power

            elif power_type == "flexible":
                min_p = app["Min_Power"]
                max_p = app["Max_Power"]
                req_energy = app["Required_Energy"]
                

                abs_start_limit = int(app["T_S"] * steps_per_hour)
                abs_t_current = current_step % total_steps
                
                if abs_t_current == abs_start_limit: 
                    delivered_so_far = 0.0
                else:
                    delivered_so_far = self.flexible_energy_delivered.get(name, 0.0)
                
                req_energy = max(0.0, req_energy - delivered_so_far)

                abs_end_limit = int(app["T_F"] * steps_per_hour) % total_steps
                current_session_k = []
                found_session = False
                session_ended = False

                for k in mpc_steps:
                    abs_t = (current_step + k) % total_steps
                    
                    # Window logic (allows crossing midnight)
                    if abs_start_limit <= abs_end_limit:
                        is_valid = (abs_start_limit <= abs_t < abs_end_limit)
                    else:
                        is_valid = (abs_t >= abs_start_limit or abs_t < abs_end_limit)
                        
                    if is_valid:
                        if not session_ended:
                            current_session_k.append(k)
                            found_session = True
                        else:
                            # Strictly off outside the window
                            model += O_flex[(name, k)] == 0, f"Off_Out_{name}_{k}"
                            model += P_flex[(name, k)] == 0, f"Zero_Out_{name}_{k}"
                    else:
                        if found_session:
                            session_ended = True
                        model += O_flex[(name, k)] == 0, f"Off_Out_{name}_{k}"
                        model += P_flex[(name, k)] == 0, f"Zero_Out_{name}_{k}"
                    
                    # The Semi-Continuous Logic: If On, must be between Min and Max
                    model += P_flex[(name, k)] >= min_p * O_flex[(name, k)], f"Min_{name}_{k}"
                    model += P_flex[(name, k)] <= max_p * O_flex[(name, k)], f"Max_{name}_{k}"
                    
                    # Add directly to the flexible load (no locked-in history needed because it can be paused)
                    flexible_load[k] += P_flex[(name, k)]

                model += pulp.lpSum(P_flex[(name, k)] * delta for k in current_session_k) >= req_energy - E_deficit[name], f"Energy_Req_Min_{name}"
                model += pulp.lpSum(P_flex[(name, k)] * delta for k in current_session_k) <= req_energy, f"Energy_Req_Max_{name}"
        
        local_T_out = [current_ambient_temp_profile[(current_step + k) % 48] for k in mpc_steps]

        for k in mpc_steps:
            model += (local_elec_demand[k] + flexible_load[k] + locked_in_power[k] + P_HP[k] + z[k] + (0.3 * P_comp_fr[k]) + (0.3 * P_comp_fz[k]) + I_export[k] == I[k] + local_solar_gen[k] + y[k]), f"Power_balance_{k}"
            
            model += P_HP_Space[k] + P_HP_DHW[k] == P_HP[k], f"HP_Split_{k}"

            if k == 0:
                model += T_fr[0] == self.current_T_fridge + (0.1196 * delta) - (((0.1467 + 0.1196) / 0.3) * delta * P_comp_fr[0])
                model += T_fz[0] == self.current_T_freezer + ((15/67) * delta) - (((7/25) + (15/67)) / 0.3 * delta * P_comp_fz[0])
                model += T_in[0] == self.current_T_in + (delta/C_in) * ((P_HP_Space[0] * COP) - (UA * (self.current_T_in - local_T_out[0])))
                model += S_TH[0] == self.current_soc_th + (P_HP_DHW[0] * COP * delta)

            else: 
                model += T_fr[k] == T_fr[k-1] + (0.1196 * delta) - (((0.1467 + 0.1196) / 0.3) * delta * P_comp_fr[k])
                model += T_fz[k] == T_fz[k-1] + ((15/67) * delta) - (((7/25) + (15/67)) / 0.3 * delta * P_comp_fz[k])
                model += T_in[k] == T_in[k-1] + (delta/C_in) * ((P_HP_Space[k] * COP) - (UA * (T_in[k-1] - local_T_out[k])))
                model += S_TH[k] == S_TH[k-1] + (P_HP_DHW[k] * COP * delta)

            # Comfort Deviation Constraints
            model += diff[k] >= T_in[k] - T_target
            model += diff[k] >= T_target - T_in[k]


    
        # Objective Function
        local_prices = [price_grid_elec[(current_step + k) % 48] for k in mpc_steps]
        local_export_prices = [price_grid_export[(current_step + k) % 48] for k in mpc_steps]

        # Generate a noise profile for this specific house
        # noise = self.noise

        total_cost = pulp.lpSum([
            delta * (I[k] * (local_prices[k] + community_penalty_prices[k])) -
            delta * (I_export[k] * local_export_prices[k]) +  
            (1000 * I_excess[k]) +      # penalty for going over 1kW battery will no save itself for the 35p peak
            (100 * I_excess_eff[k]) +   # soft penalty for encroaching on the chance constraint margin
            (200 * Reserve_deficit[k]) +
            (5.0 * diff[k]) + 
            delta * (y[k] * wear_cost_elec) + 
            delta * (P_HP[k] * wear_cost_therm)
            for k in mpc_steps
        ])
        

        for app in self.personal_appliances:
            if app.get("power_type") == "flexible":
                total_cost += 5000 * E_deficit[app["name"]]


        terminal_value_rate = 00.8
        # Lowered so the battery will prioritize Agile prices over perfect flatness
        final_objective = total_cost - (terminal_value_rate * S_E[horizon - 1]) + (0.1 * P_max_local) + (10 * P_max_flex)        
        model += final_objective 

    
        # Terminal Region
        model += S_E[horizon - 1] >= dynamic_soc_min, "Terminal_Region_Lower_Bound"
        
        model += T_in[horizon - 1] >= T_min, "Terminal_Thermal_Region"

        terminal_target_therm = 0.25 * C_TH
        model += S_TH[horizon - 1] >= terminal_target_therm, "Terminal_Tank_Reserve"
        

        model.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=10))

        if pulp.LpStatus[model.status] == "Optimal"or (pulp.LpStatus[model.status] == "Not Solved" and pulp.value(I[0]) is not None):
            proposed_import_profile = [pulp.value(I[k]) for k in mpc_steps]

            current_import = pulp.value(I[0])
            current_charge = pulp.value(z[0])
            current_discharge = pulp.value(y[0])
            current_export = pulp.value(I_export[0])
            next_soc = pulp.value(S_E[0])
            if next_soc < dynamic_soc_min:
                vprint(f"House {self.house_id} [Step {current_step}]: MPC intentionally planned to drop SoC to {next_soc:.2f} kWh")

            if current_discharge > 0 and community_penalty_prices[0] > 0:
                reason = f"Discharging {current_discharge:.2f}kW to protect the grid import limit and avoid the penalty fee"
            elif current_charge > 0 and local_solar_gen[0] > current_import:
                reason = f"Charging {current_charge:.2f}kW to soak up free excess solar energy."
            elif current_discharge > 0 and local_prices[0] > 0.20: # Assuming 20p is peak pricing
                reason = f"Discharging {current_discharge:.2f}kW to avoid peak base pricing."
            else:
                reason = f"Normal operation. Grid price is £{local_prices[0]:.2f}/kWh"

            starting_appliances = []
            flexible_powers = {}

            for app in self.personal_appliances:
                name = app["name"]
                power_type = app.get("power_type", "constant")
                interruptible = app.get("interruptible", False)
                
                if power_type == "constant" and not interruptible:
                    if pulp.value(E[name, 0]) >= 0.5:
                        starting_appliances.append(name)
                elif power_type == "flexible" and interruptible:
                    val = pulp.value(P_flex[(name, 0)])
                    flexible_powers[name] = val if val is not None else 0.0


            # Return the data package
            return {
                "house_id": self.house_id,
                "status": "Optimal",
                "proposed_import_profile": proposed_import_profile,
                "planned_import_k0": current_import,
                "planned_charge_k0": current_charge,
                "planned_discharge_k0": current_discharge,
                "planned_export_k0": current_export,
                "next_soc_calculation": next_soc,
                "explainability": reason,
                "next_soc_th_calculation": pulp.value(S_TH[0]),
                "starting_appliances": starting_appliances,
                "next_T_fridge": pulp.value(T_fr[0]),
                "next_T_freezer": pulp.value(T_fz[0]),
                "fridge_compressor_k0": pulp.value(P_comp_fr[0]),
                "freezer_compressor_k0": pulp.value(P_comp_fz[0]),
                "planned_excess_k0": pulp.value(I_excess[0]),
                "rogue_power_k0": rogue_power,
                "heat_pump_power_k0": pulp.value(P_HP[0]),
                "flexible_powers_k0": flexible_powers,
                "next_T_in_calculation": pulp.value(T_in[0])


            }
        else:
            # Fallback Logic
            print(f"House {self.house_id} SOLVER FAILED - Triggering Dumb Fallback")
            
            starting_appliances = []
            non_optimal_profile = [0.0] *  horizon
            flexible_powers_fallback  = {app["name"]: 0.0 for app in self.personal_appliances if app.get("power_type") == "flexible"}

            for app in self.personal_appliances:
                name = app["name"]
                if not self.appliances_already_run.get(name, False):
                    abs_start_limit = int(app["human_start_hour"] * steps_per_hour)
                    abs_t = current_step % total_steps
                    if abs_t == abs_start_limit:
                        starting_appliances.append(name)
                
                #     abs_start_limit = int(app["T_S"] * steps_per_hour)
                #     abs_t = current_step % total_steps
                #     if abs_t == abs_start_limit:
                #         starting_appliances.append(name)

                
            solar_generation_per_house = [self.pv_capacity * efficiency * multiplier for multiplier in solar_profile]
            local_solar_gen = [solar_generation_per_house[(current_step + k) % 48] for k in mpc_steps]
            
            # Revert to bang-bang control for thermostat
            if self.current_T_in < T_target:
                dumb_hp_power = 3.0 
            else:
                dumb_hp_power = 0.0

            abs_t = current_step % total_steps
            current_demand = self.personal_elec_demand[abs_t] + dumb_hp_power + 0.27 # Base + HP + Fridge/Freezer (0.135 * 2)

            # Add power for appliances starting right now
            for name in starting_appliances:
                app_info = next(a for a in self.personal_appliances if a["name"] == name)
                power = app_info.get("Power", app_info.get("Max_Power", 0.0))
                current_demand += power
                if app_info.get("power_type") == "flexible":
                    flexible_powers_fallback[name] = power
                
            # Add power for appliances that are already running from previous steps
            for app in self.personal_appliances:
                if not app.get('deferrable', True):
                    continue

                name = app["name"]
                
                app_dur = app.get("human_duration_hours", 0.0)
                if app_dur == 0.0 and app.get("Max_Power", 0.0) > 0:
                    app_dur = app.get("Required_Energy", 0.0) / app.get("Max_Power", 1.0)
                    
                duration_steps = int(app_dur * steps_per_hour)
                power = app.get("Power", app.get("Max_Power", 0.0))
                
                for past_k in range(1, duration_steps):
                    past_t = current_step - past_k
                    if past_t >= 0 and self.history_E.get((name, past_t), 0) == 1:
                        current_demand += power
                        if app.get("power_type") == "flexible":
                            flexible_powers_fallback[name] = power
                        break 
                        
            current_import = max(0.0, current_demand - local_solar_gen[0])
            non_optimal_profile[0] = current_import

            del model


            return {
                "house_id": self.house_id,
                "status": "Dumb_Fallback",
                "proposed_import_profile": non_optimal_profile,
                "planned_import_k0": current_import,
                "planned_charge_k0": 0.0,
                "planned_discharge_k0": 0.0,
                "planned_export_k0": 0.0,
                "next_soc_calculation": self.current_soc,  # Battery sits idle
                "explainability": "OPTIMISATION FAILED: Reverting to Dumb House mode",
                "next_soc_th_calculation": self.current_soc_th,
                "starting_appliances": starting_appliances,
                "next_T_fridge": self.current_T_fridge,
                "next_T_freezer": self.current_T_freezer,
                "fridge_compressor_k0": 0.3,
                "freezer_compressor_k0": 0.3,
                "rogue_power_k0": rogue_power,
                "heat_pump_power_k0": dumb_hp_power,
                "flexible_powers_k0": flexible_powers_fallback,
                "next_T_in_calculation": 20.0
            }
        # Empty RAM

    def calculate_open_loop_demand(self, current_step, pv_gen=0.0):
        # Calculate the total electricity demand of the house as if it had no smart controls.
        # This is the "dumb" baseline against which the smart system's performance is compared.
        abs_t = current_step % total_steps
        gross_open_demand = self.personal_elec_demand[abs_t]
        
        # Instead of sharing the Smart House's thermometer calculate the exact physical energy required to maintain the target temperature.
        # A dumb house's bang-bang thermostat averages out to exactly this continuous load:
        local_T_out = current_ambient_temp_profile[abs_t]
        dumb_hp_elec_power = max(0.0, (UA * (T_target - local_T_out)) / COP)
        gross_open_demand += dumb_hp_elec_power
        self.history_E[("Open_Loop_Heat_Pump", current_step)] = dumb_hp_elec_power

        # Define the current time interval for checking appliance overlaps.
        step_start_hour = (current_step % total_steps) * delta
        step_end_hour = step_start_hour + delta

    
        # A dumb house plugs the EV in immediately and blasts it at Max Power.
        for app in self.personal_appliances:
            # EVs sometimes use "arrival_time" instead of "human_start_hour", so we use .get() fallbacks
            app_start = app.get("human_start_hour", app.get("arrival_time", 0.0))
            
            # Dynamically determine Power and Duration
            if app["name"] == "Electric car":
                power = 7.0  # Standard 7.0 kW home charger
                req_energy = app.get("Required_Energy", 0.0)
                app_dur = req_energy / power if power > 0 else 0.0
            else:
                power = app.get("Power", app.get("Max_Power", 0.0))
                # Try duration first, if missing, calculate it from Required Energy
                app_dur = app.get("human_duration_hours", 0.0)
                if app_dur == 0.0 and power > 0:
                    app_dur = app.get("Required_Energy", 0.0) / power

            # If the appliance doesn't exist today, skip it
            if power == 0.0 or app_dur == 0.0:
                continue

            app_end = app_start + app_dur
            total_overlap_hours = 0.0

            # Calculate exact overlap within this 30-minute time step
            for shift in [-24.0, 0.0, 24.0]:
                s_start = app_start + shift
                s_end = app_end + shift
                overlap = max(0.0, min(step_end_hour, s_end) - max(step_start_hour, s_start))
                total_overlap_hours += overlap

            # Calculate the average power consumed by the appliance during this time step.
            average_power_for_step = (power * total_overlap_hours) / delta
            gross_open_demand += average_power_for_step
            self.history_E[(f"Open_Loop_{app['name']}", current_step)] = average_power_for_step

        open_fridge_power = 0.135
        open_freezer_power = 0.135
        gross_open_demand += (open_freezer_power + open_fridge_power)

        self.history_E[("Open_Loop_Fridge", current_step)] = open_fridge_power
        self.history_E[("Open_Loop_Freezer", current_step)] = open_freezer_power

        # Battery logic: excess solar in, discharge when demand high
        net_load = gross_open_demand - pv_gen

        open_loop_import = 0.0
        open_loop_export = 0.0

        if net_load < 0: # Excess solar
            excess = abs(net_load)
            charge_amount = min(excess, G_E, (C_E - self.open_soc) / nu_E)
            self.open_soc += charge_amount * nu_E * delta

            open_loop_export = excess - charge_amount

        elif net_load > 0: 
            discharge_amount = min(net_load, D_E, self.open_soc * nu_E)
            self.open_soc -= (discharge_amount/nu_E) * delta

            open_loop_import = net_load - discharge_amount
        
        return open_loop_import, open_loop_export
       
        
        
        
    def execute_physical_action(self, accepted_schedule, current_step):
        # Updates the physical state of the house to move forward in time
       
        # Calculate Unsmart Grid Import (Demand minus whatever the solar is doing right now)
        abs_t = current_step % total_steps
        solar_gen = self.pv_capacity * solar_profile[abs_t]

        open_loop_import, open_loop_export = self.calculate_open_loop_demand(current_step, solar_gen)
        
        self.history_E[("Open_Loop_Import", current_step)] = open_loop_import
        self.history_E[("Open_Loop_Export", current_step)] = open_loop_export

        self.daily_total_uncontrolled_energy += open_loop_import * delta

        self.current_T_in = accepted_schedule.get("next_T_in_calculation", self.current_T_in)
        self.history_T_in.append(self.current_T_in)
        
        #
        # From this point onwards, the code is executing the *actual* smart control actions.
        # It takes the MPC's optimal plan and adjusts it in real-time for any unforeseen events.
        #
        
        if accepted_schedule["status"] == "Optimal":
            # Real Time Adjusting Stage (RTAS) Control
            # Read MPC's original plan
            planned_discharge = accepted_schedule["planned_discharge_k0"]
            planned_import = accepted_schedule["planned_import_k0"]
            planned_export = accepted_schedule.get("planned_export_k0", 0.0)
            community_slack = accepted_schedule.get("community_slack_k0", 0.0)
            dynamic_limit = planned_import + community_slack

            hp_power = accepted_schedule.get("heat_pump_power_k0", 0.0)
            flex_apps = accepted_schedule.get("flexible_powers_k0", {}).copy()            
            rogue_spike = accepted_schedule.get("rogue_power_k0", 0.0)

            spike_duration = random.uniform(1.0, 29.0) / 60.0 if rogue_spike > 0 else 0.0
            normal_duration = delta-spike_duration

            emergency_discharge = 0.0
            shedded_hp = 0.0
            shedded_flex = {name: 0.0 for name in flex_apps}

            if planned_import + rogue_spike > dynamic_limit:
                excess_demand = (planned_import + rogue_spike) - dynamic_limit
                available_inverter_capacity = D_E - planned_discharge
                available_energy_kw = (self.current_soc * nu_E) / spike_duration if spike_duration > 0 else 0.0
                
                emergency_discharge = min(excess_demand, available_inverter_capacity, available_energy_kw)
                excess_demand -= emergency_discharge

                if excess_demand > 0.01:
                    if hp_power > 0:
                        shedded_hp = min(excess_demand, hp_power)
                        excess_demand -= shedded_hp
                        print(f"    [RTAS] H{self.house_id} Shed {shedded_hp:.2f}kW of Heat Pump for {spike_duration*60:.0f} mins")

                    for name, pwr in flex_apps.items():
                        if excess_demand > 0.01 and pwr > 0:
                            shed = min(excess_demand, pwr)
                            shedded_flex[name] = shed
                            excess_demand -= shed
                            print(f"  [RTAS] H{self.house_id} Shed {shed:.2f}kW of {name} for {spike_duration*60:.0f} mins")
                    
            # Battery outputs (planned + emergency). Flex apps draw (planned - shed)
            # Battery output (planned) Flex apps draw (planned)

            energy_discharged_spike = (planned_discharge + emergency_discharge) * spike_duration
            energy_discharged_normal = planned_discharge * normal_duration
            total_discharge_energy = energy_discharged_spike + energy_discharged_normal

            # Recalculate SoC
            actual_charge = accepted_schedule["planned_charge_k0"]
            true_next_soc = self.current_soc + (nu_E * delta * actual_charge) - (total_discharge_energy / nu_E)
            self.current_soc = true_next_soc
            self.current_soc_th = accepted_schedule.get("next_soc_th_calculation", self.current_soc_th)
            self.current_T_fridge = accepted_schedule["next_T_fridge"]
            self.current_T_freezer = accepted_schedule["next_T_freezer"]


            # Time weighted logging for graphs
            avg_hp = ((hp_power - shedded_hp) * spike_duration + hp_power * normal_duration) / delta
            self.history_E[("Heat_Pump", current_step)] = avg_hp

            avg_rogue = (rogue_spike * spike_duration) / delta
            self.history_E[("Rogue_Load", current_step)] = avg_rogue

            avg_discharge = total_discharge_energy / delta
            self.history_E[("Battery_Discharge", current_step)] = avg_discharge

            for name, pwr in flex_apps.items():
                avg_flex = ((pwr - shedded_flex[name]) * spike_duration + pwr * normal_duration) / delta
                self.history_E[(name, current_step)] = avg_flex

                # Update the delivered energy tracker so that the MPC knows it missed some charge
                if current_step % total_steps == int(next(a["T_S"] for a in self.personal_appliances if a["name"] == name) * steps_per_hour):
                    self.flexible_energy_delivered[name] = 0.0
                    
                self.flexible_energy_delivered[name] += avg_flex * delta
            
            # Log standard appliances
            self.history_E[("Fridge", current_step)] = accepted_schedule["fridge_compressor_k0"]
            self.history_E[("Freezer", current_step)] = accepted_schedule["freezer_compressor_k0"]
            
            # True Grid Import Average
            avg_net = planned_import - planned_export + avg_rogue - (emergency_discharge * spike_duration / delta) - (shedded_hp * spike_duration / delta) - sum(s * spike_duration / delta for s in shedded_flex.values())

            true_import = max(0.0, avg_net)
            true_export = max(0.0, -avg_net)

            self.history_E[("Grid_Import", current_step)] = true_import
            self.history_E[("Grid_Export", current_step)] = true_export
            self.daily_total_controlled_energy += true_import*delta


            started_apps = accepted_schedule.get("starting_appliances", [])
            for app_name in started_apps:
                self.appliances_already_run[app_name] = True
                self.history_E[(app_name, current_step)] = 1

        else:
            fallback_import = accepted_schedule["planned_import_k0"]
            
            # Log the grid import so pareto_parallel doesn't crash
            self.history_E[("Grid_Import", current_step)] = fallback_import
            self.history_E[("Grid_Export", current_step)] = 0.0
            self.daily_total_controlled_energy += fallback_import * delta
            
            # Log the fallback assets
            self.history_E[("Heat_Pump", current_step)] = accepted_schedule.get("heat_pump_power_k0", 0.0)
            self.history_E[("Rogue_Load", current_step)] = accepted_schedule.get("rogue_power_k0", 0.0)
            self.history_E[("Battery_Discharge", current_step)] = 0.0
            
            # Log flexible powers if any
            flex_apps_fb = accepted_schedule.get("flexible_powers_k0", {})
            for name, pwr in flex_apps_fb.items():
                self.history_E[(name, current_step)] = pwr
                if current_step % total_steps == int(next(a["T_S"] for a in self.personal_appliances if a["name"] == name) * steps_per_hour):
                    self.flexible_energy_delivered[name] = 0.0
                self.flexible_energy_delivered[name] += pwr * delta

            # Log Fridge and Freezer
            self.history_E[("Fridge", current_step)] = accepted_schedule.get("fridge_compressor_k0", 0.0)
            self.history_E[("Freezer", current_step)] = accepted_schedule.get("freezer_compressor_k0", 0.0)

            # Update state values from schedule (prevents frozen states during fallback)
            self.current_soc = accepted_schedule.get("next_soc_calculation", self.current_soc)
            self.current_soc_th = accepted_schedule.get("next_soc_th_calculation", self.current_soc_th)
            self.current_T_fridge = accepted_schedule.get("next_T_fridge", self.current_T_fridge)
            self.current_T_freezer = accepted_schedule.get("next_T_freezer", self.current_T_freezer)

            started_apps = accepted_schedule.get("starting_appliances", [])
            for app_name in started_apps:
                self.appliances_already_run[app_name] = True
                self.history_E[(app_name, current_step)] = 1        
                
        
