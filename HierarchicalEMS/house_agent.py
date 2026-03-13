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
        self.current_soc_th = 0.25 * C_TH
        self.appliances_already_run = {app["name"]: False for app in appliances}
        self.history_E = {}

        self.current_T_fridge = 4.0
        self.current_T_freezer = -18.0

        self.alpha = 0.01                       # Define risk tolerance, 0.05 = 95% guarantee of safety
        self.sigma_human = 0.75                 # ~ 0.75 kW standard deviation

        self.daily_total_uncontrolled_energy = 0.0
        self.daily_total_controlled_energy = 0.0
    
        # Add randomness
        magnitude = random.uniform(0.7, 1.3)    # +/- 30% of total energy use
        time_shift = random.randint(-3, 3)      # +/- 1.5 hours of routine shift

        total_len = len(electric_demand_per_house)
        self.personal_elec_demand = [
            electric_demand_per_house[(i - time_shift) % total_len] * magnitude
            for i in range(total_len)
        ]

        self.personal_heat_demand = heat_demand_per_house.copy()   

        self.flexible_energy_delivered = {}
        for app in appliances:
            if app.get("power_type") == "flexible":
                self.flexible_energy_delivered[app["name"]] = 0.0


        # Appliance window variance
        self.personal_appliances = copy.deepcopy(appliances)
        for app in self.personal_appliances:
            window_shift = random.uniform(-2.0, 2.0)

            # apply shift but keep within 0-24 bounds
            new_ts = (app["T_S"] + window_shift) % 24.0
            new_tf = (app["T_F"] + window_shift) % 24.0
            app["T_S"] = new_ts
            app["T_F"] = new_tf

          

    def generate_proposed_schedule(self, current_step, community_penalty_prices):
        # Lower level solver
        # Runs a 24 hour look ahead MPC using PuLP to minimise the house's nill
        # Takes the community penalty prices into account to avoid causing grid spikes


        if current_step > 0 and current_step % total_steps == 0:
            for app_name in self.appliances_already_run:
                self.appliances_already_run[app_name]= False

        horizon = 48
        mpc_steps = range(horizon)

        model = pulp.LpProblem(f"House_{self.house_id}_Step_{current_step}", pulp.LpMinimize)

        # PuLP variable definition
        S_E = pulp.LpVariable.dicts(f"SoC_H{self.house_id}", mpc_steps, 0, self.battery_capacity)
        z = pulp.LpVariable.dicts(f"Charge_Rate_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        y = pulp.LpVariable.dicts(f"Discharge_Rate_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')
        I = pulp.LpVariable.dicts(f"Grid_Import_H{self.house_id}", mpc_steps, lowBound=0, upBound=I_max, cat='Continuous')
        I_excess = pulp.LpVariable.dicts(f"Excess_Import_H{self.house_id}", mpc_steps, lowBound=0, cat='continuous')
        P_HP = pulp.LpVariable.dicts(f"Heat_Pump_Power_H{self.house_id}", mpc_steps, lowBound=0, upBound=10.0, cat='Continuous')
        S_TH = pulp.LpVariable.dicts(f"SoC_Therm_H{self.house_id}", mpc_steps, 0, C_TH, cat='Continuous')
        T_fr = pulp.LpVariable.dicts(f"T_fridge_H{self.house_id}", mpc_steps, lowBound=2, upBound=5, cat='Continuous')
        T_fz = pulp.LpVariable.dicts(f"T_freezer_H{self.house_id}", mpc_steps, lowBound=-22.0, upBound=-15.0, cat='Continuous')
        P_comp_fr = pulp.LpVariable.dicts(f"Fridge_Comp_Power_H{self.house_id}", mpc_steps, lowBound=0.0, upBound=0.3, cat='Continuous')
        P_comp_fz = pulp.LpVariable.dicts(f"Freezer_Comp_Power_H{self.house_id}", mpc_steps, lowBound=0.0, upBound=0.3, cat='Continuous')

        # Chance constraint setup
        # Calculate the Z-score using the Inverse Cumulative Distribution Function
        z_score = stats.norm.ppf(1- self.alpha)
        safety_margin = z_score * self.sigma_human

        # Chance Constraint implementation
        # Shrink the house limit by the safety margin, if the margin is larger than the limit, floor it to prevent negative
        effective_limit = max(0.0, self.house_limit - safety_margin)

        E = {}       # For Type 1 & 2: Constant, Non-Interruptible (Start Times)
        P_flex = {}  # For Type 3: Flexible Power draw
        O_flex = {}  # For Type 3: Binary On/Off State (for minimum power limits)

        E_deficit = {}
        for app in appliances:
            if app.get("power_type") == "flexible":
                E_deficit[app["name"]] = pulp.LpVariable(f"Defecit_{app['name']}_H{self.house_id}", lowBound=0, cat="Continuous")

        Reserve_deficit = pulp.LpVariable.dicts(f"Reserve_deficit_H{self.house_id}", mpc_steps, lowBound=0, cat='Continuous')

        for app in appliances:
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
            model += I[k] <= self.house_limit +  I_excess[k], f"Dynamic_limit_{k}"

            # The sum of unused grid capacity + unused battery discharge + interruptible charging
            # must always be capable of absorbing the suddent chance-constraint spikes
            model += (self.house_limit - I[k]) + (D_E - y[k]) + z[k] >= safety_margin

            # The battery is forced to keep enough energy to survive a 30-minute spike
            reserve_hours = 0
            model += S_E[k] >= (safety_margin * reserve_hours) / nu_E, f"Energy_Reserve_{k}"

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
        rogue_power = 0.0

        # 10% chance at any given time step that a human does something unpredictable
        if random.random() < 0.10:
            # Randomly choose a device
            rogue_power = random.choice([1.5, 2.5, 3.5])
        
        local_elec_demand[0] += rogue_power     
        local_heat_demand = [heat_demand_per_house[(current_step + k) % total_steps] for k in mpc_steps]
        solar_generation_per_house = [self.pv_capacity * multiplier for multiplier in solar_profile]
        local_solar_gen = [solar_generation_per_house[(current_step + k) % total_steps] for k in mpc_steps]

        flexible_load = {k: 0.0 for k in mpc_steps}
        locked_in_power = {k: 0.0 for k in mpc_steps}

        for app in appliances:
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

            elif power_type == "flexible" and interruptible:
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
                        model += P_flex[(name, k)] == 0, f"Zero_out_{name}_{k}"
                    
                    # The Semi-Continuous Logic: If On, must be between Min and Max
                    model += P_flex[(name, k)] >= min_p * O_flex[(name, k)], f"Min_{name}_{k}"
                    model += P_flex[(name, k)] <= max_p * O_flex[(name, k)], f"Max_{name}_{k}"
                    
                    # Add directly to the flexible load (no locked-in history needed because it can be paused!)
                    flexible_load[k] += P_flex[(name, k)]

                model += pulp.lpSum(P_flex[(name, k)] * delta for k in current_session_k) >= req_energy - E_deficit[name], f"Energy_Req_Min_{name}"
                model += pulp.lpSum(P_flex[(name, k)] * delta for k in current_session_k) <= req_energy, f"Energy_Req_Max_{name}"
        
        for k in mpc_steps:
            model += (local_elec_demand[k] + flexible_load[k] + locked_in_power[k] + P_HP[k] + z[k] + (0.3 * P_comp_fr[k]) + (0.3 * P_comp_fz[k]) <= I[k] + local_solar_gen[k] + y[k]), f"Power_balance_{k}"
            if k == 0:
                model += S_TH[0] == self.current_soc_th + (P_HP[0] * COP * delta) - (local_heat_demand[0] * delta), f"Therm_Balance_0"
                model += T_fr[0] == self.current_T_fridge + (0.1196 * delta) - (((0.1467 + 0.1196) / 0.3) * delta * P_comp_fr[0])
                model += T_fz[0] == self.current_T_freezer + ((15/67) * delta) - (((7/25) + (15/67)) / 0.3 * delta * P_comp_fz[0])

            else: 
                model += S_TH[k] == S_TH[k-1] + (P_HP[k] * COP * delta) - (local_heat_demand[k]*delta), f"Therm_Balance{k}"
                model += T_fr[k] == T_fr[k-1] + (0.1196 * delta) - (((0.1467 + 0.1196) / 0.3) * delta * P_comp_fr[k])
                model += T_fz[k] == T_fz[k-1] + ((15/67) * delta) - (((7/25) + (15/67)) / 0.3 * delta * P_comp_fz[k])


    
        # Objective Function
        local_prices = [price_grid_elec[(current_step + k) % total_steps] for k in mpc_steps]

        # Generate a noise profile for this specific house
        noise = [random.uniform(0.00001, 0.00099) for _ in mpc_steps]


        total_cost = pulp.lpSum([
            delta * (I[k] * (local_prices[k] + community_penalty_prices[k] + noise[k])) + 
            (1000 * I_excess[k]) +      # penalty for going over 1kW
            (50 * Reserve_deficit[k]) +       # penalty for an empty battery
            delta * (y[k] * wear_cost_elec) + 
            delta * (P_HP[k] * wear_cost_therm)
            for k in mpc_steps
        ])
        
        for app in appliances:
            if app.get("power_type") == "flexible":
                total_cost += 500 * E_deficit[app["name"]]

        model += total_cost

        # Force the battery to finish the 24 hour horizon with at least as much charge as it started with
        model += S_E[horizon - 1] >= 0.10 * self.battery_capacity, "Terminal_SoC_Constraint"
        model += S_TH[horizon - 1] >= 0.10 * C_TH, "Terminal_Thermal_Constraint"

        model.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=10))

        if pulp.LpStatus[model.status] == "Optimal":
            proposed_import_profile = [pulp.value(I[k]) for k in mpc_steps]

            current_import = pulp.value(I[0])
            current_charge = pulp.value(z[0])
            current_discharge = pulp.value(y[0])
            next_soc = pulp.value(S_E[0])

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

            for app in appliances:
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


            }
        else:
            # Fallback Logic
            print(f"House {self.house_id} SOLVER FAILED - Triggering Dumb Fallback")
            
            starting_appliances = []
            non_optimal_profile = [0.0] *  horizon


            for app in appliances:
                name = app["name"]
                if not self.appliances_already_run[name]:
                    abs_start_limit = int(app["T_S"] * steps_per_hour)
                    abs_t = current_step % total_steps
                    if abs_t == abs_start_limit:
                        starting_appliances.append(name)

            current_demand = local_elec_demand[0]
            # Add power for appliances starting right now
            for name in starting_appliances:
                app_info = next(a for a in appliances if a["name"] == name)
                current_demand += app_info["Power"]
                
            # Add power for appliances that are already running from previous steps
            for app in appliances:
                name = app["name"]
                duration = int(app["Slots"])
                for past_k in range(1, duration):
                    past_t = current_step - past_k
                    if past_t >= 0 and self.history_E.get((name, past_t), 0) == 1:
                        current_demand += app["Power"]
                        break 
                        
            # 3. Calculate Grid Imports (Demand minus whatever the solar panels are currently producing)
            current_import = max(0, current_demand - local_solar_gen[0])
            non_optimal_profile[0] = current_import


            return {
                "house_id": self.house_id,
                "status": "Dumb_Fallback",
                "proposed_import_profile": non_optimal_profile,
                "planned_import_k0": current_import,
                "planned_charge_k0": 0.0,
                "planned_discharge_k0": 0.0,
                "next_soc_calculation": self.current_soc,  # Battery sits idle
                "explainability": "OPTIMISATION FAILED: Reverting to Dumb House mode",
                "next_soc_th_calculation": self.current_soc_th,
                "starting_appliances": starting_appliances,
                "next_T_fridge": self.current_T_fridge,
                "next_T_freezer": self.current_T_freezer,
                "fridge_compressor_k0": 0.3,
                "freezer_compressor_k0": 0.3,
                "rogue_power_k0": rogue_power,
                "heat_pump_power_k0": local_heat_demand[0]/ COP,
                "flexible_powers_k0": {app["name"]: 0.0 for app in appliances if app.get("power_type") == "flexible"},
            }
        
    def execute_physical_action(self, accepted_schedule, current_step):
        # Updates the physical state of the house to move forward in time

        # Calculate open loop control power usage
        abs_t = current_step % total_steps
        rogue_spike = accepted_schedule.get("rogue_power_k0", 0.0)
        open_loop_demand = self.personal_elec_demand[abs_t] + rogue_spike
        
        # Dumb Heat Pump: draws exactly what is needed right now, no thermal storage buffer
        # Dumb Fridge & Freezer: Steady-state compressor draw to maintain temp, ~0.135kW each
        # Dumb Appliances (They turn on exactly at their preferred start window)

        open_loop_demand += self.personal_heat_demand[abs_t] / COP
        open_loop_demand += 0.27 
        
        for app in self.personal_appliances:
            start_step = int(app["T_S"] * steps_per_hour)
            
            if app.get("power_type") == "constant":
                duration = int(app["Slots"])
                power = app["Power"]
            else: # Flexible (Unsmart EV chargers just plug in and draw max power instantly)
                duration = int((app["Required_Energy"] / app["Max_Power"]) * steps_per_hour) + 1
                power = app["Max_Power"]
                
            end_step = (start_step + duration) % total_steps
            
            # Check if this exact step falls inside the "dumb" running window
            if start_step <= end_step:
                if start_step <= abs_t < end_step:
                    open_loop_demand += power
            else: # The running window crosses midnight
                if abs_t >= start_step or abs_t < end_step:
                    open_loop_demand += power

        # Calculate Unsmart Grid Import (Demand minus whatever the solar is doing right now)
        solar_gen = self.pv_capacity * solar_profile[abs_t]
        open_loop_import = max(0.0, open_loop_demand - solar_gen)
        
        self.history_E[("Open_Loop_Import", current_step)] = open_loop_import
        self.daily_total_uncontrolled_energy += open_loop_import * delta


        if accepted_schedule["status"] == "Optimal":

            # Real Time Adjusting Stage (RTAS) Control
            # Read MPC's original plan
            planned_discharge = accepted_schedule["planned_discharge_k0"]
            planned_import = accepted_schedule["planned_import_k0"]
            community_slack = accepted_schedule.get("community_slack_k0", 0.0)
            dynamic_limit = self.house_limit + community_slack

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

                emergency_discharge = min(excess_demand, available_inverter_capacity)
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
                if current_step % total_steps == int(next(a["T_S"] for a in appliances if a["name"] == name) * steps_per_hour):
                    self.flexible_energy_delivered[name] = 0.0
                self.flexible_energy_delivered[name] += avg_flex * delta
            
            # Log standard appliances
            self.history_E[("Fridge", current_step)] = accepted_schedule["fridge_compressor_k0"]
            self.history_E[("Freezer", current_step)] = accepted_schedule["freezer_compressor_k0"]
            
            # True Grid Import Average
            avg_import = planned_import + avg_rogue - (emergency_discharge * spike_duration / delta) - (shedded_hp * spike_duration / delta) - sum(s * spike_duration / delta for s in shedded_flex.values())
            self.history_E[("Grid_Import", current_step)] = max(0.0, avg_import)
            self.daily_total_controlled_energy += max(0.0, avg_import) * delta


            started_apps = accepted_schedule.get("starting_appliances", [])
            for app_name in started_apps:
                self.appliances_already_run[app_name] = True
                self.history_E[(app_name, current_step)] = 1
                
                
        

