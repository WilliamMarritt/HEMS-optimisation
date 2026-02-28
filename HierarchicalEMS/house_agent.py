# house_agent.py
import pulp
from config import *
from data import *
import random

class HouseAgent:
    def __init__(self, house_id, pv_capacity, battery_capacity, house_limit):
        # House physical hardware
        self.house_id = house_id
        self.house_limit = house_limit
        self.pv_capacity = pv_capacity
        self.battery_capacity = battery_capacity

        self.current_soc =  S_init
        self.current_soc_th = 0.5 * C_TH
        self.appliances_already_run = {app["name"]: False for app in appliances}
        self.history_E = {}

        self.current_T_fridge = 4.0
        self.current_T_freezer = -18.0
    
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
        E = pulp.LpVariable.dicts(f"Appliance_Start_H{self.house_id}", ((app["name"], t)  for app in appliances for t in mpc_steps), cat='Binary')
        P_HP = pulp.LpVariable.dicts(f"Heat_Pump_Power_H{self.house_id}", mpc_steps, lowBound=0, upBound=10.0, cat='Continuous')
        S_TH = pulp.LpVariable.dicts(f"SoC_Therm_H{self.house_id}", mpc_steps, 0, C_TH, cat='Continuous')
        T_fr = pulp.LpVariable.dicts(f"T_fridge_H{self.house_id}", mpc_steps, lowBound=2, upBound=5, cat='Continuous')
        T_fz = pulp.LpVariable.dicts(f"T_freezer_H{self.house_id}", mpc_steps, lowBound=-22.0, upBound=-15.0, cat='Continuous')
        P_comp = pulp.LpVariable.dicts(f"Compressor_Power_H{self.house_id}", mpc_steps, lowBound=0.0, upBound=0.3, cat='Continuous')


        # PuLP constraints

        # Battery Limits and Dynamics Loop
        for k in mpc_steps:
            model += y[k] <= D_E, f"Discharge_Rate_Limit{k}"
            model += z[k] <= G_E, f"Charge_Limit{k}"
            model += I[k] <= self.house_limit + I_excess[k], f"Dynamic_1kW_limit_{k}"
            # Storage Dynamics
            if k == 0:
                model += S_E[0] == self.current_soc + (nu_E * delta * z[0]) - (delta * y[0] / nu_E)
            else:
                # Subsequent steps look backwards at k-1
                model += S_E[k] == S_E[k-1] + (nu_E * delta * z[k]) - (delta * y[k] / nu_E)

        for app in appliances:
            name = app["name"]
            
            if self.appliances_already_run[name] == True:
                # If it already ran today, force it off for this entire prediction horizon
                for k in mpc_steps:
                    model += E[name, k] == 0, f"Already_Run_Home_{self.house_id}_{name}_k{k}"
            else:
                # If it hasn't run yet, do the normal scheduling
                duration_steps = int(app["Slots"])
                abs_start_limit = int(app["T_S"] * steps_per_hour)
                abs_end_limit = int(app["T_F"] * steps_per_hour - duration_steps) % total_steps
                
                valid_k_starts = []
                found_window = False
                window_closed = False

                for k in mpc_steps:
                    # Map local step k to absolute step
                    abs_t = (current_step + k) % total_steps

                    # Check if the appliance window crosses midnight
                    if abs_start_limit <= abs_end_limit:
                        is_valid = (abs_start_limit <= abs_t <= abs_end_limit)
                    else:
                        is_valid = (abs_t >= abs_start_limit or abs_t <= abs_end_limit)
                    
                    # If the time is within the allowed window valid start
                    if is_valid:
                        if not window_closed:
                            valid_k_starts.append(k)
                            found_window = True
                        else:
                            model += E[name, k] == 0, f"Future_Window_Home_{self.house_id}_App_{name}_Step_{k}"     
                    else:
                        if found_window:
                            # Otherwise force the solver to keep the appliance OFF
                            window_closed = True
                        
                        model += E[name, k] == 0, f"Invalid_Start_Home_{self.house_id}_App_{name}_Step_{k}"

                # Require the appliance to start exactly once in its valid windows
                if len(valid_k_starts) > 0:
                    model += pulp.lpSum(E[name, k] for k in valid_k_starts) == 1, f"Scheduling_Home_{self.house_id}_App_{name}"


            
        # Physical Constraints

        #Local Data Arrays for this specific prediction horizon
        local_elec_demand = [electric_demand_per_house[(current_step + k) % total_steps] for k in mpc_steps]
        local_heat_demand = [heat_demand_per_house[(current_step + k) % total_steps] for k in mpc_steps]
        solar_generation_per_house = [self.pv_capacity * multiplier for multiplier in solar_profile]
        local_solar_gen = [solar_generation_per_house[(current_step + k) % total_steps] for k in mpc_steps]


        flexible_load = {}   
        locked_in_power = {}        
        for k in mpc_steps:
            load_at_k = 0
            locked_power = 0
            for app in appliances:
                name = app["name"]
                power = app["Power"]
                duration_steps = int(app["Slots"])
                
                # Future/ present loads scheduled here
                possible_local_starts = [ks for ks in range(k - duration_steps + 1, k + 1) if ks >= 0]
                load_at_k += pulp.lpSum(E[(name, ks)] for ks in possible_local_starts) * power    

                # Past loads still running
                for past_k in range(-duration_steps + 1, 0):
                    if (k - past_k) < duration_steps:
                        past_t = (current_step + past_k)
                        if self.history_E.get((name, past_t), 0) == 1:
                            locked_power += power

            flexible_load[k] = load_at_k
            locked_in_power[k] = locked_power # Save the locked-in power for step k

        for k in mpc_steps:
            model += (local_elec_demand[k] + flexible_load[k] + locked_in_power[k] + P_HP[k] + z[k] + (0.3 * P_comp[k]) <= I[k] + local_solar_gen[k] + y[k]), f"Power_balance_{k}"
            if k == 0:
                model += S_TH[0] == self.current_soc_th + (P_HP[0] * COP * delta) - (local_heat_demand[0] * delta), f"Therm_Balance_0"
                model += T_fr[0] == self.current_T_fridge + (0.1196 * delta) - (((0.1467 + 0.1196) / 0.3) * delta * P_comp[0])
                model += T_fz[0] == self.current_T_freezer + ((15/67) * delta) - (((7/25) + (15/67)) / 0.3 * delta * P_comp[0])

            else: 
                model += S_TH[k] == S_TH[k-1] + (P_HP[k] * COP * delta) - (local_heat_demand[k]*delta), f"Therm_Balance{k}"
                model += T_fr[k] == T_fr[k-1] + (0.1196 * delta) - (((0.1467 + 0.1196) / 0.3) * delta * P_comp[k])
                model += T_fz[k] == T_fz[k-1] + ((15/67) * delta) - (((7/25) + (15/67)) / 0.3 * delta * P_comp[k])


        

        # Objective Function
        local_prices = [price_grid_elec[(current_step + k) % total_steps] for k in mpc_steps]

        # Generate a noise profile for this specific house
        noise = [random.uniform(0.00001, 0.00099) for _ in mpc_steps]


        total_cost = pulp.lpSum([
            delta * (I[k] * (local_prices[k] + community_penalty_prices[k] + noise[k])) + 
            (1000 * I_excess[k]) +      # penalty for going over 1kW
            delta * (y[k] * wear_cost_elec) + 
            delta * (P_HP[k] * wear_cost_therm)
            for k in mpc_steps
        ])

        model += total_cost

        # Force the battery to finish the 24 hour horizon with at least as much charge as it started with
        model += S_E[horizon - 1] >= self.current_soc, "Terminal_SoC_Constraint"

        model.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=10))

        if pulp.LpStatus[model.status] == "Optimal":
            proposed_import_profile = [pulp.value(I[k]) for k in mpc_steps]

            current_import = pulp.value(I[0])
            current_charge = pulp.value(z[0])
            current_discharge = pulp.value(y[0])
            next_soc = pulp.value(S_E[0])

            if current_discharge > 0 and community_penalty_prices[0] > 0:
                reason = f"Discharging {current_discharge:.2f}kW to protect the community transformer and avoid the penalty fee"
            elif current_charge > 0 and local_solar_gen[0] > current_import:
                reason = f"Charging {current_charge:.2f}kW to soak up free excess solar energy."
            elif current_discharge > 0 and local_prices[0] > 0.20: # Assuming 20p is peak pricing
                reason = f"Discharging {current_discharge:.2f}kW to avoid peak base pricing."
            else:
                reason = f"Normal operation. Grid price is £{local_prices[0]:.2f}/kWh"

            starting_appliances = []
            for app in appliances:
                if pulp.value(E[app["name"], 0]) >= 0.5:
                    starting_appliances.append(app["name"]) 

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
                "fridge_compressor_k0": pulp.value(P_comp[0]),
                "planned_excess_k0": pulp.value(I_excess[0])
            }
        else:
            # Fallback Logic
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

            current_demand = local_elec_demand            

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
                "fridge_compressor_k0": 1
            }
        
    def execute_physical_action(self, accepted_schedule, current_step):
        # Updates the physical state of the house to move forward in time
        # if current_step > 0 and current_step % total_steps == 0:
        #     for app_name in self.appliances_already_run:
        #         self.appliances_already_run[app_name]= False


        if accepted_schedule["status"] == "Optimal":
            self.current_soc = accepted_schedule["next_soc_calculation"]
            self.current_soc_th = accepted_schedule.get("next_soc_th_calculation", self.current_soc_th)

            self.current_T_fridge = accepted_schedule["next_T_fridge"]
            self.current_T_freezer = accepted_schedule["next_T_freezer"]
            
            # Manually log the fridge into history_E if the compressor fired
            self.history_E[("Fridge", current_step)] = accepted_schedule["fridge_compressor_k0"]
            
            started_apps = accepted_schedule.get("starting_appliances", [])
            
            for app_name in started_apps:
                self.appliances_already_run[app_name] = True
                self.history_E[(app_name, current_step)] = 1

