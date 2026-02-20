
#%%
# main.py
from config import *
from data import *
from optimisation import solve_mpc_step
from visualisation import plot_results


# --- Minimise Cost ---
print("Running MPC Simulation for 24 hours...")
current_soc_E = 0
current_soc_TH = 0

appliances_already_run = {
    h: {app["name"]: False for app in appliances} for h in homes
}

history_u = []
history_I = []
history_soc_E = []
history_E = {}
total_time_run = 0
total_daily_cost = 0

# Run for 2 days (96 steps)
for t in range(total_steps* 2):
    local_t = t % total_steps
    day = t // total_steps      # Day 1 or Day 2

    if local_t == 0 and day == 1:
        for h in homes:
            for app in appliances:
                appliances_already_run[h][app["name"]] = False

    hour = int(t * delta)
    minute = int((t * delta * 60) % 60)

    print(f"Solving MPC for time step {t} (Hour {hour:02d}:{minute:02d})...")

    result = solve_mpc_step(
        start_step=t,
        intital_soc_E=current_soc_E,
        initial_soc_TH=current_soc_TH,
        appliances_already_run=appliances_already_run,
        history_E=history_E,
        horizon=48,
        mode = "minimise_cost"
    )

    if result['status'] != 'Optimal':
        print(f"Warning: Solver Failed at step {t} with status")
        break

    total_time_run += result.get('solve_time', 0)

    history_u.append(result['u'])
    history_I.append(result['import'])
    history_soc_E.append(current_soc_E)

    total_daily_cost += (result["import"] * price_grid_elec[local_t] * delta) + \
                    ((result["u"] + (result["x_t"] / 0.85)) * price_gas * delta) + \
                    (result["f"] * wear_cost_therm * delta) + \
                    (result["y"] * wear_cost_elec * delta)

    for h, name in result['app_starts']:
        appliances_already_run[h][name] = True
        # Use absolute t so the graph plots across 48 h
        history_E[(h, name, t)] = 1
        print(f"  - Scheduled {name} for Home {h} at time step {t}")

    current_soc_E = current_soc_E + (nu_E * delta * result['z']) - (delta * result['y'] / nu_E)
    current_soc_E = max(0, min(C_E, current_soc_E))  # Ensure SoC stays within bounds

    current_soc_TH = current_soc_TH + (delta * result['g_T']) - (delta * result['f'] / nu_TH)
    current_soc_TH = max(0, min(C_TH, current_soc_TH))  #

daily_average_cost = total_daily_cost / 2

print("\n --- Simulation Complete ---")
print("Total cost for the day: £{:.2f}".format(total_daily_cost))
print("Total Computation Time: {:.2f} seconds".format(total_time_run))

print("Generating Plots...")

#%%


from visualisation import plot_results

plot_results(history_u, history_I, history_soc_E, history_E, price_grid_elec)

# %%
