# main.py
from config import *
from data import *
from optimisation import solve_scenario
from visualisation import plot_results

total_time_run = 0

# --- Minimise Cost ---
print("Running Cost Minimisation...")
min_cost, co2_at_min_cost, _, _, _, _, t_run = solve_scenario(mode="minimise_cost")
total_time_run += t_run

if min_cost is not None:
    print(f"Cheapest Cost: £{min_cost:.2f}, CO2 Emissions: {co2_at_min_cost:.2f} kg")
else:
    print("No feasible solution found for cost minimisation.")

# --- Minimise CO2 ---
print("Running CO2 Minimisation...")
cost_at_min_co2, min_co2, _, _, _, _, t_run = solve_scenario(mode="minimise_co2")
total_time_run += t_run

if cost_at_min_co2 is not None:
    print(f"Lowest CO2: {min_co2:.2f} kg, Cost: £{cost_at_min_co2:.2f}")
else:
    print("No feasible solution found for CO2 minimisation.")

# Pareto Curve
steps = 5
phi2_max = co2_at_min_cost
phi2_min = min_co2

print(f"\n{'Limit (kg)':<12} | {'Cost (£)':<10} | {'Actual CO2 (kg)':<15}")
print("-" * 45)

for k in range(steps + 1):
    # Calculate epsilon (the limit)
    epsilon = phi2_max - ((phi2_max - phi2_min) * k / steps)

    # Solve minimising cost with CO2 limit
    cost, actual_co2, _, _, _, _, t_run = solve_scenario(mode="minimise_cost", co2_limit=epsilon)
    total_time_run += t_run

    if cost is not None:
        print(f"{epsilon:<12.2f} | {cost:<10.2f} | {actual_co2:<15.2f}")
    else:
        print(f"{epsilon:<12.2f} | {'Infeasible':<10} | {'N/A':<15}")


# --- Final Plot (Middle Limit) ---
middle_limit = (co2_at_min_cost + min_co2) / 2
print("\nSolving Final Schedule (Middle Limit)...")
cost, co2, u_final, S_E_final, E_final, I_final, t_run = solve_scenario(mode="minimise_cost", co2_limit=middle_limit)
total_time_run += t_run

print("\n--- FINAL SCHEDULE (Middle Limit) ---")
print(f"Cost: £{cost:.2f}, CO2: {co2:.2f} kg")
print("Status: Optimal")

# Print Start Times
h = 0
for t in time_steps:
        # Convert step to actual time 
        hour = int(t * delta)
        minute = int((t * delta * 60) % 60)
        time_str = f"{hour:02d}:{minute:02d}"
        
        active_apps = []
        for app in appliances:
            name = app["name"]
            # Check if this appliance is starting 
            if E_final[h, name, t].varValue > 0.9:
                active_apps.append(f"START {name}")
            
            # Check if it is currently RUNNING (based on previous starts)
            duration_steps = int(app["Slots"])
            for look_back in range(1, duration_steps):
                prev_t = t - look_back
                if prev_t >= 0 and E_final[h, name, prev_t].varValue > 0.9:
                    active_apps.append(f"Running ({name})")

        if active_apps:
            print(f"{time_str} : {', '.join(active_apps)}")

if u_final is not None:
    print("Generating plots...")
    plot_results(u_final, S_E_final, E_final, I_final, price_grid_elec)

print(f"Total time taken for all optimisations: {total_time_run:.2f} seconds")