# optimization.py
import pulp
from config import *
from data import *

def solve_scenario(mode="minimise_cost", co2_limit=None):
    # E: binary variable E_jit indicates "task i from home j that is done at time t" 
    E = pulp.LpVariable.dicts("Appliance_Start", ((h, app["name"], t) for h in homes for app in appliances for t in time_steps), cat='Binary')

    # I_t: Electricity import from the grid
    I = pulp.LpVariable.dicts("Grid_Import", time_steps, lowBound=0, cat='Continuous')

    # f_t: Thermal Storage discharge
    f = pulp.LpVariable.dicts("Thermal_Discharge", time_steps, lowBound=0, cat='Continuous')

    # g_T t: Thermal Storage charge
    g_T = pulp.LpVariable.dicts("Thermal_Charge", time_steps, lowBound=0, cat='Continuous')

    # Create variables for charge and discharge rates of the electrical storage
    z = pulp.LpVariable.dicts("Charge_Rate", time_steps, lowBound=0, cat='Continuous')
    y = pulp.LpVariable.dicts("Discharge_Rate", time_steps, lowBound=0, cat='Continuous')

    model = pulp.LpProblem("HEMS_Optimization", pulp.LpMinimize)

    # Power output of CHP
    u = pulp.LpVariable.dicts("u_CHP", time_steps, lowBound=0, upBound=C_CHP, cat='Continuous')

    # Power output of Boiler
    x_t = pulp.LpVariable.dicts("x_Boiler", time_steps, lowBound=0, upBound=C_B, cat='Continuous')

    # State of Charge for Electrical Storage
    S_E = pulp.LpVariable.dicts("S_Elec_stored", time_steps, lowBound=0, upBound=C_E, cat='Continuous')

    # State of Charge for Thermal Storage
    S_TH = pulp.LpVariable.dicts("S_Thermal_stored", time_steps, lowBound=0, upBound=C_TH, cat='Continuous')


    # Appliance scheduling constraints (per home)
    for h in homes:
        for app in appliances:
            name = app["name"]
            start_step = int(app["T_S"]* steps_per_hour)
            end_step = int(app["T_F"]* steps_per_hour - app["Slots"])

            # +1 because range is exclusive at the end
            valid_start_steps = range(start_step, end_step + 1)

            # Each home must start each task exactly once
            model += pulp.lpSum(E[h, name, t] for t in valid_start_steps) == 1, f"Appliance_{name}_Scheduling_Home_{h}"

            # Force start to 0 outside the valid window
            for t in time_steps:
                if t < start_step or t > end_step:
                    model += E[h, name, t] == 0, f"Appliance_{name}_Invalid_Start_{t}_Home_{h}"


    # Calculate Flexible Load (sum of all homes)
    flexible_load = {}
    for t in time_steps:
        load_at_t = 0
        for h in homes:
            for app in appliances:
                name = app["name"]
                duration_steps = int(app["Slots"])
                power = app["Power"]
                possible_start_steps = [ts for ts in range(t- duration_steps + 1, t + 1) if ts >= 0]    # ts = t_start
                load_at_t += pulp.lpSum(E[(h, name, ts)] for ts in possible_start_steps) * power
        flexible_load[t] = load_at_t

    # Hourly constraints
    for t in time_steps:
        total_elec_demand = electric_demand_per_house[t] * num_homes
        total_heat_demand = heat_demand_per_house[t] * num_homes

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
        
    last_hour = 47

    # Eq 6: Boundary condition for no daily electricity accumulation
    model += S_E[last_hour] == S_init, "End_of_Day_Balance"

    # Objective Functions (Eq 18a and 19)
    # Cost Objective
    total_cost = pulp.lpSum([
        delta * (I[t] * price_grid_elec[t] +
                (u[t] + x_t[t] / 0.85) * price_gas) +
                y[t] * wear_cost_elec +
                f[t] * wear_cost_therm
        for t in time_steps    
        ])

    # CO2 Objective
    total_co2 = pulp.lpSum([
        delta * (
            u[t] * xi_CHP +         # CHP emissions
            I[t] * CO2_grid[t] +    # Grid emissions
            x_t[t] * xi_Boiler      # Boiler emissions
        ) for t in time_steps
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
        return pulp.value(total_cost), pulp.value(total_co2), u, S_E, E, I, solve_time
    else:
        return None, None, None, None, None, None, solve_time