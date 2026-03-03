# optimization.py
import pulp
from config import *
from data import *

def solve_scenario(mode="minimise_cost", co2_limit=None):
    time_steps_48h = range(total_steps *2)
    # E: binary variable E_jit indicates "task i from home j that is done at time t" 
    E = pulp.LpVariable.dicts("Appliance_Start", ((h, app["name"], day, t) for h in homes for app in appliances for day in [0, 1]for t in time_steps_48h), cat='Binary')

    # I_t: Electricity import from the grid: I_extra is required as a penalty for going over the cap
    I_base = pulp.LpVariable.dicts("Grid_Import", time_steps_48h, lowBound=0, upBound=I_max, cat='Continuous')
    I_extra = pulp.LpVariable.dicts("Grid_Import_Extra", time_steps_48h, lowBound=0, cat='Continuous')
    I = {t: I_base[t] + I_extra[t] for t in time_steps_48h}


    # f_t: Thermal Storage discharge
    f = pulp.LpVariable.dicts("Thermal_Discharge", time_steps_48h, lowBound=0, cat='Continuous')

    # g_T t: Thermal Storage charge
    g_T = pulp.LpVariable.dicts("Thermal_Charge", time_steps_48h, lowBound=0, cat='Continuous')

    # Create variables for charge and discharge rates of the electrical storage
    z = pulp.LpVariable.dicts("Charge_Rate", time_steps_48h, lowBound=0, cat='Continuous')
    y = pulp.LpVariable.dicts("Discharge_Rate", time_steps_48h, lowBound=0, cat='Continuous')

    model = pulp.LpProblem("HEMS_Optimization", pulp.LpMinimize)

    # Power output of CHP
    u = pulp.LpVariable.dicts("u_CHP", time_steps_48h, lowBound=0, upBound=C_CHP, cat='Continuous')

    # Power output of Boiler
    x_t = pulp.LpVariable.dicts("x_Boiler", time_steps_48h, lowBound=0, upBound=C_B, cat='Continuous')

    # State of Charge for Electrical Storage
    S_E = pulp.LpVariable.dicts("S_Elec_stored", time_steps_48h, lowBound=0, upBound=C_E, cat='Continuous')

    # State of Charge for Thermal Storage
    S_TH = pulp.LpVariable.dicts("S_Thermal_stored", time_steps_48h, lowBound=0, upBound=C_TH, cat='Continuous')


    # Appliance scheduling constraints (per home)
    for h in homes:
        for app in appliances:
            name = app["name"]
            duration_steps = int(app["Slots"])
            start_step = int(app["T_S"]* steps_per_hour)
            end_step = int(app["T_F"]* steps_per_hour - app["Slots"])

            for day in [0, 1]:
                # +1 because range is exclusive at the end
                valid_start_steps = []
                abs_start_limit = day * total_steps + start_step
                abs_end_limit = day * total_steps + end_step


                # If overnight appliance, the end limit is in the next day
                if start_step >= end_step:
                    abs_end_limit += total_steps
                
                abs_end_limit -= duration_steps # Last valid start slot

                for t in time_steps_48h:
                    # Only allow scheduling if the task finishes before the 48h window
                    # Allowing overnight appliances on Day 1 to wrap around to hour 0
                    if (abs_start_limit <= t <= abs_end_limit) or (abs_start_limit <= t + (total_steps * 2) <= abs_end_limit):                        
                        valid_start_steps.append(t)
                    else:
                        model += E[h, name, day, t] == 0, f"Invalid_Start_Home_{h}_App_{name}_Step_{t}_day_{day}"

                if len(valid_start_steps) > 0:
                    # pulp.lpSum: must pick exactly one of these valid time slots
                    model += pulp.lpSum(E[h, name, day, t] for t in valid_start_steps) == 1, f"Appliance_{name}_Scheduling_Day_{day}_Home_{h}"
                else:
                    model += pulp.lpSum(E[h, name, day, t] for t in time_steps_48h) == 0, f"Appliance_{name}_NoFit_Day_{day}_Home{h}"

        

    # Calculate Flexible Load (sum of all homes)
    flexible_load = {}
    for t in time_steps_48h:
        load_at_t = 0
        for h in homes:
            for app in appliances:
                name = app["name"]
                duration_steps = int(app["Slots"])
                power = app["Power"]
                # Let the power draw "spill over" the 48h boundary back to the start
                possible_start_steps = [(t - k) % (total_steps * 2) for k in range(duration_steps)]
                
                app_load = 0
            # d is required to create a isolated local variable
                for d in [0, 1]:
                    for ts in possible_start_steps:
                         app_load += E[h, name, d, ts]    
                    
                load_at_t += app_load * power
        flexible_load[t] = load_at_t

    # Hourly constraints
    for t in time_steps_48h:
        local_t = t % total_steps
        total_elec_demand = electric_demand_per_house[local_t] * num_homes
        total_heat_demand = heat_demand_per_house[local_t] * num_homes

        model += total_elec_demand + flexible_load[t] == u[t] + y[t] - z[t] + I[t], f"Meet_Electric_Demand_{t}"
        # Eq 14
        model += total_heat_demand == (alpha * u[t]) + x_t[t] + f[t] - g_T[t], f"Meet_Heat_Demand_{t}"

        # Eq 1: CHP capacity constraint
        model += u[t] <= C_CHP, f"CHP_Capacity_Constraint_{t}"

        # Eq 2: Boiler capacity constraint
        model += x_t[t] <= C_B, f"Boiler_Capacity_Constraint_{t}"

        # Eq 3: Electrical storage capacity constraint
        model += S_E[t] <= C_E, f"Electrical_Storage_Capacity_Constraint_{t}"

        # Eq 4: Thermal storage capacity constraint
        model += S_TH[t] <= C_TH, f"Thermal_Storage_Capacity_Constraint_{t}"

        # Eq 7: Discharge rate limit    
        model += y[t] <= D_E, f"Discharge_Rate_Limit_{t}"

        # Eq 8: Charge rate limit
        model += z[t] <= G_E, f"Charge_Rate_Limit_{t}"

        if t == 0:
            S_prev_E = S_init
            S_prev_TH = 0  # Assuming Thermal Storage starts empty
        else :
            # Eq 5
            S_prev_E = S_E[t-1]
            S_prev_TH = S_TH[t-1]


        model += S_E[t] == S_prev_E + (nu_E * delta * z[t]) - (delta* y[t] / nu_E), f"Battery_Balance{t}"
        model += S_TH[t] == S_prev_TH + (delta * g_T[t]) - (delta * f[t] / nu_TH), f"Therm_Balance_Logic_{t}"
        
    last_hour = (total_steps*2) - 1

    # Eq 6: Boundary condition for no daily electricity accumulation
    model += S_E[last_hour] == S_init, "End_of_Day_Balance"

    # Objective Functions (Eq 18a and 19)
    # Cost Objective
    total_cost = pulp.lpSum([
            delta * (   
                (I_base[t] + I_extra[t]) * price_grid_elec[t % total_steps] +
                (I_extra[t] * 0.05) + 
                (u[t] + x_t[t] / 0.85) * price_gas) +
                y[t] * wear_cost_elec +
                f[t] * wear_cost_therm
        for t in time_steps_48h    
        ])

    # CO2 Objective
    total_co2 = pulp.lpSum([
        delta * (
            u[t] * xi_CHP +         # CHP emissions
            I[t] * CO2_grid[local_t] +    # Grid emissions
            x_t[t] * xi_Boiler      # Boiler emissions
        ) for t in time_steps_48h
    ])

    # Apply Epsilon Constraint (Eq 21) with +0.001 to avoid numerical issues
    if co2_limit is not None:
        model += total_co2 <= co2_limit + 0.001, "CO2_Emissions_Limit"

    # Set Objective
    if mode == "minimise_cost":
        model += total_cost
    else:
        model += total_co2

    # Solve
    model.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=30, gapRel=0.05))
    solve_time = model.solutionTime

    if pulp.LpStatus[model.status] == 'Optimal':
        return pulp.value(total_cost), pulp.value(total_co2), u, S_E, E, I_base, I_extra, solve_time
    else:
        print("FAILED")
        print("Solve time", solve_time)
        
        return None, None, None, None, None, None, None, solve_time