#%%

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
import random
from config import *
from data import *
from house_agent import HouseAgent
from community_controller import CommunityController
import concurrent.futures
import pandas as pd

alphas = [0.01, 0.05, 0.15, 0.30, 0.50] # 0.01 = Highly Paranoid, 0.50 = Ignores risk completely
sigmas = [0.0, 0.1, 0.25, 0.5, 0.75]          # Size of the expected human spikes
num_simulations = 20

results = {sigma: {'alphas': [], 'costs': [], 'peaks': []} for sigma in sigmas}

print("Starting 3D Pareto Sweep")

for alpha in alphas:
    for sigma in sigmas:

        accumulated_peak = 0.0
        accumulated_cost = 0.0


        for sim in range(num_simulations):
            random.seed(sim) 

            
            houses = [HouseAgent(i, PV_capacity, C_E, I_max / num_homes) for i in range(num_homes)]
            community = CommunityController(transformer_limit=I_max)

            for house in houses:
                house.alpha = alpha
                house.sigma_human = sigma

            max_peak = 0.0
            sim_total_cost = 0.0

            # Run a  24-hour simulation
            for step in range(48): 
                approved_schedules, peak_demand = community.negotiate_schedules(houses, step)
                
                step_actual_peak = 0.0
                step_actual_cost = 0.0 

                for house in houses:
                    sched = next(s for s in approved_schedules if s["house_id"] == house.house_id)

                    house.execute_physical_action(sched, step)

                    true_import = house.history_E[("Grid_Import", step)]
                    step_actual_peak += true_import
                    step_actual_cost += true_import * price_grid_elec[step % total_steps] * delta

                sim_max_peak = max(max_peak, step_actual_peak)
                sim_total_cost += step_actual_cost

            accumulated_peak += sim_max_peak
            accumulated_cost += sim_total_cost

            
            print(f"    -> Seed {sim} finished for a={alpha}, s={sigma}")

        flat_data = []
            
        
        avg_peak = accumulated_peak / num_simulations
        avg_cost = accumulated_cost / num_simulations       

        print(f"Sweep Done -> Alpha: {alpha:<4} | Sigma: {sigma:<4} | Peak: {avg_peak:>5.2f} kW | Cost: £{avg_cost:.2f}")

        results[sigma]['alphas'].append(alpha)
        results[sigma]['costs'].append(avg_cost)
        results[sigma]['peaks'].append(avg_peak)

        # s_key used to not overwrite sigma
        for s_key, data in results.items():
            for a, c, p in zip(data['alphas'], data['costs'], data['peaks']):
                flat_data.append([s_key, a, c, p])

        df = pd.DataFrame(flat_data, columns=['Sigma', 'Alpha', 'Cost', 'Peak'])

        df.to_csv('pareto_results_laptop1.csv', index=False)
        print("Data successfully saved to CSV")


#%%
print("\nGenerating 2D Pareto Graphs...")

fig, axes = plt.subplots(1, 3, figsize=(18, 6))
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', "#a20aa0"] 

for i, sigma in enumerate(sigmas):
    axes[0].plot(results[sigma]['alphas'], results[sigma]['costs'], marker='o', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
axes[0].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
axes[0].set_ylabel('Total Community Daily Cost (£)', fontsize=12)
axes[0].set_title('Financial Impact from Decreasing Risk', fontsize=14, fontweight='bold')
axes[0].grid(True, linestyle='--', alpha=0.7)
axes[0].legend()
axes[0].invert_xaxis()

for i, sigma in enumerate(sigmas):
    axes[1].plot(results[sigma]['alphas'], results[sigma]['peaks'], marker='s', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
axes[1].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label=f'Power Draw Limit ({I_max}kW)')
axes[1].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
axes[1].set_ylabel('Maximum Peak Demand (kW)', fontsize=12)
axes[1].set_title('Grid Security vs. Risk Tolerance', fontsize=14, fontweight='bold')
axes[1].grid(True, linestyle='--', alpha=0.7)
axes[1].legend()
axes[1].invert_xaxis()

for i, sigma in enumerate(sigmas):
    axes[2].plot(results[sigma]['costs'], results[sigma]['peaks'], marker='^', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
axes[2].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label='Power Draw Limit (10kW)')
axes[2].set_xlabel('Total Community Daily Cost (£)', fontsize=12)
axes[2].set_ylabel('Maximum Peak Demand (kW)', fontsize=12)
axes[2].set_title('Pareto Curve: Cost vs. Peak', fontsize=14, fontweight='bold')
axes[2].grid(True, linestyle='--', alpha=0.7)
axes[2].legend()

plt.tight_layout()
plt.show()

# %%

