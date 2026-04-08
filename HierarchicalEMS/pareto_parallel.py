import numpy as np
import random
import concurrent.futures
import matplotlib.pyplot as plt
import pandas as pd
import os
from config import *
from data import *
from house_agent import HouseAgent
from community_controller import CommunityController

alphas = [0.01, 0.05, 0.15, 0.30, 0.50]
sigmas = [0.0, 0.1, 0.25, 0.5, 0.75]
num_simulations = 1

def run_single_simulation(params):
    alpha, sigma, seed_val = params
    np.random.seed(seed_val) 
    random.seed(seed_val)
    
    houses = [HouseAgent(i, PV_capacity, C_E, I_max / num_homes) for i in range(num_homes)]
    community = CommunityController(transformer_limit=I_max)

    for house in houses:
        house.alpha = alpha
        house.sigma_human = sigma

    max_peak = 0.0
    total_community_cost = 0.0

    for step in range(48): 
        approved_schedules, peak_demand = community.negotiate_schedules(houses, step)

        step_actual_peak = 0.0
        step_actual_cost = 0.0

        for house in houses:
            sched = next(s for s in approved_schedules if s["house_id"] == house.house_id)
            house.execute_physical_action(sched, step)
            true_import = house.history_E.get(("Grid_Import", step), 0.0)

            step_actual_peak += true_import
            step_actual_cost += true_import * price_grid_elec[step % total_steps] * delta

        max_peak = max(max_peak, step_actual_peak)
        total_community_cost += step_actual_cost

    community_total_sla_score = 0.0
    sim_steps_run = len(houses[0].history_T_in) 

    for house in houses:
        total_tasks = 0.0
        fulfilled_tasks = 0.0
        
        # Flexible Appliances (EV) 
        ev_appliance = next((app for app in house.personal_appliances if app["name"] == "Electric car"), None)
        if ev_appliance is not None:
            ev_req = ev_appliance.get("Required_Energy", 0.0)
            if ev_req > 0:
                ev_delivered = sum(house.history_E.get(("Electric car", s), 0.0) * delta for s in range(sim_steps_run))
                total_tasks += 1.0
                fulfilled_tasks += min(1.0, ev_delivered / ev_req)
                
        # Standard Appliances
        for app in house.personal_appliances:
            if app.get("power_type") == "flexible": 
                continue
            total_tasks += 1.0
            if any(house.history_E.get((app["name"], s), 0) > 0 for s in range(sim_steps_run)):
                fulfilled_tasks += 1.0
                
        # Thermal Comfort 
        avg_temp = sum(house.history_T_in) / sim_steps_run if sim_steps_run > 0 else 0
        
        total_tasks += 1.0
        if avg_temp >= 18.0:
            fulfilled_tasks += 1.0
        elif avg_temp >= 16.0:
            fulfilled_tasks += 0.5 + (0.5 * ((avg_temp - 16.0) / 2.0))
        else:
            fulfilled_tasks += 0.0
        
        house_sla_pct = (fulfilled_tasks / total_tasks) * 100 if total_tasks > 0 else 100.0
        community_total_sla_score += house_sla_pct

    avg_community_sla = community_total_sla_score / num_homes

    return {'Sigma': sigma, 'Alpha': alpha, 'Seed': seed_val, 'Cost': total_community_cost, 'Peak': max_peak, 'SLA': avg_community_sla}


if __name__ == '__main__':
    csv_file = 'test.csv'
    completed_runs = set()
    cols = ['Sigma', 'Alpha', 'Seed', 'Cost', 'Peak', 'SLA']
    if os.path.exists(csv_file):
        try:
            existing_df = pd.read_csv(csv_file)
            completed_runs = set(zip(existing_df['Alpha'], existing_df['Sigma'], existing_df['Seed'].astype(int)))
        except Exception:
            pass
    else:
        pd.DataFrame(columns=cols).to_csv(csv_file, index=False)

    all_combinations = [(round(a, 4), round(s, 4), seed) for a in alphas for s in sigmas for seed in range(num_simulations)]
    combinations = [c for c in all_combinations if c not in completed_runs]
    
    print(f"Resuming... {len(completed_runs)} completed, {len(combinations)} remaining.")

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(run_single_simulation, combo): combo for combo in combinations}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                
                # Append single row to CSV immediately
                pd.DataFrame([res], columns=cols).to_csv(csv_file, mode='a', header=False, index=False)
                
                print(f"Done -> Alpha: {res['Alpha']:<4} | Sigma: {res['Sigma']:<4} | Seed: {res['Seed']:<2} | Peak: {res['Peak']:>5.2f} kW | Cost: £{res['Cost']:.2f}")
            except Exception as exc:
                print(f"A simulation crashed: {exc}")

    print("\nAll simulations finished! Averaging data for 2D Pareto Graphs...")

    final_df = pd.read_csv(csv_file)
    avg_df = final_df.groupby(['Sigma', 'Alpha']).mean().reset_index()

    results = {sigma: {'alphas': [], 'costs': [], 'peaks': [], 'slas': []} for sigma in sigmas}
    
    for _, row in avg_df.iterrows():
        s = round(row['Sigma'], 2)
        results[s]['alphas'].append(round(row['Alpha'], 4)),
        results[s]['costs'].append(round(row['Cost'], 2)),
        results[s]['peaks'].append(int(row['Peak']))
        results[s]['slas'].append(round(row['SLA'], 2))

    for sigma in sigmas:
        sort_id = np.argsort(results[sigma]['alphas'])
        for key in ['alphas', 'costs', 'peaks', 'slas']:
            results[sigma][key] = [results[sigma][key][i] for i in sort_id]

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', "#cc08b2"] 

    for i, sigma in enumerate(sigmas):
        axes[0, 0].plot(results[sigma]['alphas'], results[sigma]['costs'], marker='o', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[0, 0].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[0, 0].set_ylabel('Total Community Daily Cost (£)', fontsize=12)
    axes[0, 0].set_title('Financial Impact of Paranoia', fontsize=14, fontweight='bold')
    axes[0, 0].grid(True, linestyle='--', alpha=0.7)
    axes[0, 0].legend()
    axes[0, 0].invert_xaxis()

    for i, sigma in enumerate(sigmas):
        axes[0, 1].plot(results[sigma]['alphas'], results[sigma]['peaks'], marker='s', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[0, 1].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label=f'Transformer Limit ({I_max}kW)')
    axes[0, 1].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[0, 1].set_ylabel('Maximum Peak Demand (kW)', fontsize=12)
    axes[0, 1].set_title('Grid Security vs. Risk Tolerance', fontsize=14, fontweight='bold')
    axes[0, 1].grid(True, linestyle='--', alpha=0.7)
    axes[0, 1].legend()
    axes[0, 1].invert_xaxis()

    for i, sigma in enumerate(sigmas):
        axes[1, 0].plot(results[sigma]['alphas'], results[sigma]['slas'], marker='d', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[1, 0].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[1, 0].set_ylabel('Community SLA Fulfillment (%)', fontsize=12)
    axes[1, 0].set_title('User Comfort & Reliability (SLA)', fontsize=14, fontweight='bold')
    axes[1, 0].grid(True, linestyle='--', alpha=0.7)
    axes[1, 0].set_ylim(-5, 105)
    axes[1, 0].legend()
    axes[1, 0].invert_xaxis()

    for i, sigma in enumerate(sigmas):
        axes[1, 1].plot(results[sigma]['costs'], results[sigma]['peaks'], marker='^', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[1, 1].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label=f'Transformer Limit ({I_max}kW)')
    axes[1, 1].set_xlabel('Total Community Daily Cost (£)', fontsize=12)
    axes[1, 1].set_ylabel('Maximum Peak Demand (kW)', fontsize=12)
    axes[1, 1].set_title('Pareto Frontier: Cost vs. Peak', fontsize=14, fontweight='bold')
    axes[1, 1].grid(True, linestyle='--', alpha=0.7)
    axes[1, 1].legend()

    plt.tight_layout()
    plt.show()