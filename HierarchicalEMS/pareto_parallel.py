import numpy as np
import random
import concurrent.futures
import matplotlib.pyplot as plt
import pandas as pd
from config import *
from data import *
from house_agent import HouseAgent
from community_controller import CommunityController

alphas = [0.01, 0.05, 0.15, 0.30, 0.50]
sigmas = [0.0, 0.1, 0.25, 0.5, 0.75]
num_simulations = 20  # Number of seeds per combination

# Package the simulation into a standalone worker function
def run_single_simulation(params):
    alpha, sigma, seed_val = params
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

    return {'Sigma': sigma, 'Alpha': alpha, 'Seed': seed_val, 'Cost': total_community_cost, 'Peak': max_peak}


# __main__ guard prevents child process recursively executing main process
if __name__ == '__main__':
    print(f"Starting 2D Pareto Sweep on MULTIPLE CORES...")
    
    # Create a list of all 500 tasks (25 combos * 20 seeds)
    combinations = [(a, s, seed) for a in alphas for s in sigmas for seed in range(num_simulations)]
    
    flat_data = []

    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Submit all tasks to the queue
        futures = {executor.submit(run_single_simulation, combo): combo for combo in combinations}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                flat_data.append(res)
                
                # Overwrite the CSV continuously
                df = pd.DataFrame(flat_data)
                df.to_csv('pareto_results_parallel.csv', index=False)
                
                print(f"Done -> Alpha: {res['Alpha']:<4} | Sigma: {res['Sigma']:<4} | Seed: {res['Seed']:<2} | Peak: {res['Peak']:>5.2f} kW | Cost: £{res['Cost']:.2f}")
            except Exception as exc:
                print(f"A simulation crashed: {exc}")

    print("\nAll simulations finished! Averaging data for 2D Pareto Graphs...")

    # Load the raw data and average the seeds together for plotting
    final_df = pd.read_csv('pareto_results_parallel.csv')
    avg_df = final_df.groupby(['Sigma', 'Alpha']).mean().reset_index()

    results = {sigma: {'alphas': [], 'costs': [], 'peaks': []} for sigma in sigmas}
    
    for _, row in avg_df.iterrows():
        s = row['Sigma']
        results[s]['alphas'].append(row['Alpha'])
        results[s]['costs'].append(row['Cost'])
        results[s]['peaks'].append(row['Peak'])
        
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', "#cc08b2"] 

    # Graph 1: Cost vs Alpha
    for i, sigma in enumerate(sigmas):
        axes[0].plot(results[sigma]['alphas'], results[sigma]['costs'], marker='o', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[0].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[0].set_ylabel('Total Community Daily Cost (£)', fontsize=12)
    axes[0].set_title('Financial Impact of Paranoia', fontsize=14, fontweight='bold')
    axes[0].grid(True, linestyle='--', alpha=0.7)
    axes[0].legend()
    axes[0].invert_xaxis()

    # Graph 2: Peak Demand vs Alpha
    for i, sigma in enumerate(sigmas):
        axes[1].plot(results[sigma]['alphas'], results[sigma]['peaks'], marker='s', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[1].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label=f'Transformer Limit ({I_max}kW)')
    axes[1].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[1].set_ylabel('Maximum Peak Demand (kW)', fontsize=12)
    axes[1].set_title('Grid Security vs. Risk Tolerance', fontsize=14, fontweight='bold')
    axes[1].grid(True, linestyle='--', alpha=0.7)
    axes[1].legend()
    axes[1].invert_xaxis()

    # Graph 3: The True Pareto Frontier (Cost vs Peak)
    for i, sigma in enumerate(sigmas):
        axes[2].plot(results[sigma]['costs'], results[sigma]['peaks'], marker='^', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[2].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label=f'Transformer Limit ({I_max}kW)')
    axes[2].set_xlabel('Total Community Daily Cost (£)', fontsize=12)
    axes[2].set_ylabel('Maximum Peak Demand (kW)', fontsize=12)
    axes[2].set_title('Pareto Frontier: Cost vs. Peak', fontsize=14, fontweight='bold')
    axes[2].grid(True, linestyle='--', alpha=0.7)
    axes[2].legend()

    plt.tight_layout()
    plt.show()