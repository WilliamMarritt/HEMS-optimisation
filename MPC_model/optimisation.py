# optimization.py
import pulp
from config import *
from data import *

def solve_mpc_step(start_step, intital_soc_E, initial_soc_TH, appliances_already_run, history_E, horizon=48, mode="minimise_cost"):
    # Createa  a local timeline from 0 to H for the solver
    mpc_steps = range(horizon)

    local_demand = [electric_demand_per_house[(start_step + k) % total_steps] for k in mpc_steps]
    local_heat_demand = [heat_demand_per_house[(start_step + k) % total_steps] for k in mpc_steps]
    local_prices = [price_grid_elec[(start_step + k) % total_steps] for k in mpc_steps]

    model = pulp.LpProblem(f"MPC_Optimization_Step_{start_step}", pulp.LpMinimize)

    S_E = pulp.LpVariable.dicts("SoC", mpc_steps, 0, C_E)

    I = pulp.LpVariable.dicts("Grid_Import", mpc_steps, 0)

    # E: binary variable E_jit indicates "task i from home j that is done at time t" 
    E = pulp.LpVariable.dicts("Appliance_Start", ((h, app["name"], t) for h in homes for app in appliances for t in mpc_steps), cat='Binary')

    # f_t: Thermal Storage discharge
    f = pulp.LpVariable.dicts("Thermal_Discharge", mpc_steps, lowBound=0, cat='Continuous')

    # g_T t: Thermal Storage charge
    g_T = pulp.LpVariable.dicts("Thermal_Charge", mpc_steps, lowBound=0, cat='Continuous')

    # Create variables for charge and discharge rates of the electrical storage
    z = pulp.LpVariable.dicts("Charge_Rate", mpc_steps, lowBound=0, cat='Continuous')
    y = pulp.LpVariable.dicts("Discharge_Rate", mpc_steps, lowBound=0, cat='Continuous')

    # Power output of CHP
    u = pulp.LpVariable.dicts("u_CHP", mpc_steps, lowBound=0, upBound=C_CHP, cat='Continuous')

    # Power output of Boiler
    x_t = pulp.LpVariable.dicts("x_Boiler", mpc_steps, lowBound=0, upBound=C_B, cat='Continuous')

    # State of Charge for Thermal Storage
    S_TH = pulp.LpVariable.dicts("S_Thermal_stored", mpc_steps, lowBound=0, upBound=C_TH, cat='Continuous')

    model += S_E[0] == intital_soc_E
    model += S_TH[0] == initial_soc_TH

    for k in mpc_steps:
        # Equations 1, 2, 7, 8

        model += u[k] <= C_CHP, f"CHP_Capacity{k}"
        model += x_t[k] <= C_B, f"Boiler_Capacity{k}"
        model += y[k] <= D_E, f"Discharge_Rate_Limit{k}"
        model += z[k] <= G_E, f"Charge_Limit{k}"

        # Storage Dynamics (Eq 5)
        if k > 0:
            model += S_E[k] == S_E[k-1] + (nu_E * delta * z[k]) - (delta * y[k] / nu_E)
            model += S_TH[k] == S_TH[k-1] + (delta * g_T[k]) - (delta * f[k] / nu_TH)

    for h in homes:
        for app in appliances:
            name = app["name"]
            
            if appliances_already_run[h][name] == True:
                # If it already ran today, force it off for this entire prediction horizon
                for k in mpc_steps:
                    model += E[h, name, k] == 0, f"Already_Run_Home_{h}_{name}_k{k}"
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
                    abs_t = (start_step + k) % total_steps

                    # Check if the appliance window crosses midnight
                    if abs_start_limit <= abs_end_limit:
                        is_valid = (abs_start_limit <= abs_t <= abs_end_limit)
                    else:
                        is_valid = (abs_t >= abs_start_limit or abs_t <= abs_end_limit)
                    
                    if is_valid and not window_closed:
                        valid_k_starts.append(k)
                        found_window = True
                    else:
                        if found_window:
                            window_closed = True        
                    
                        model += E[h, name, k] == 0, f"Invalid_Start_Home_{h}_App_{name}_Step_{k}"
                
                if len(valid_k_starts) > 0:
                    model += pulp.lpSum(E[h, name, k] for k in valid_k_starts) == 1, f"Scheduling_Home_{h}_App_{name}"
         
            
    flexible_load = {}   
    locked_in_power = {}        
    for k in mpc_steps:
        load_at_k = 0
        locked_power = 0
        for h in homes:
            for app in appliances:
                name = app["name"]
                power = app["Power"]
                duration_steps = int(app["Slots"])
                
                # Future/ present loads scheduled here
                possible_local_starts = [ks for ks in range(k - duration_steps + 1, k + 1) if ks >= 0]
                load_at_k += pulp.lpSum(E[(h, name, ks)] for ks in possible_local_starts) * power    

                # Past loads still running
                for past_k in range(-duration_steps + 1, 0):
                    if (k - past_k) < duration_steps:
                        past_t = (start_step + past_k)
                        if history_E.get((h, name, past_t), 0) == 1:
                            locked_power += power

        flexible_load[k] = load_at_k
        locked_in_power[k] = locked_power # Save the locked-in power for step k


    for k in mpc_steps:
        # Base Demands
        total_elec_demand = local_demand[k] * num_homes
        total_heat_demand = local_heat_demand[k] * num_homes

        model += total_elec_demand + flexible_load[k] + locked_in_power[k] == u[k] + y[k] - z[k] + I[k], f"Electric_Demand_Balance_{k}"
        model += total_heat_demand == (alpha * u[k]) + x_t[k] + f[k] - g_T[k], f"Heat_Demand_Balance_{k}"

    model += S_E[horizon-1] >= intital_soc_E, "End_SoC_E"

    total_cost = pulp.lpSum([
        delta * (I[k] * local_prices[k] + 
                 (u[k] + x_t[k] / 0.85) * price_gas) +
                 y[k] * wear_cost_elec +
                 f[k] * wear_cost_therm
        for k in mpc_steps
    ])

    model += total_cost

    model.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=30, gapRel=0.05))

    if pulp.LpStatus[model.status] == 'Optimal':
        # At k = 0
        current_u = u[0].varValue
        current_z = z[0].varValue
        current_y = y[0].varValue
        current_I = I[0].varValue
        current_f = f[0].varValue
        current_g_T = g_T[0].varValue
        current_x_t = x_t[0].varValue

        current_E_starts = []
        for h in homes:
            for app in appliances:
                name = app["name"]
                if E[h, name, 0].varValue > 0.9:
                    current_E_starts.append((h, name))
        return {
            'status': 'Optimal',
            'cost': pulp.value(total_cost),
            'u': current_u,
            'charge' : current_z,
            'z': current_z,
            'discharge' : current_y,
            'y': current_y,
            'import' : current_I,
            'f': current_f,
            'g_T': current_g_T,
            'x_t': current_x_t,
            'app_starts': current_E_starts,
            'current_soc_E': S_E[0].varValue,
            'current_soc_TH': S_TH[0].varValue
            }

    else:
        return {'status': 'Infeasible'}
    
