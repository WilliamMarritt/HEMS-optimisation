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

alphas = [0.01, 0.05, 0.15, 0.30, 0.50] # 0.01 = Highly Paranoid, 0.50 = Ignores risk completely
sigmas = [0.0, 0.1, 0.25, 0.5]          # Size of the expected human spikes

results = {sigma: {'alphas': [], 'costs': [], 'peaks': []} for sigma in sigmas}

print("Starting 3D Pareto Sweep. This will run 20 rapid simulations...")

for alpha in alphas:
    for sigma in sigmas:
        random.seed(42) 
        
        houses = [HouseAgent(i, PV_capacity, C_E, I_max / num_homes) for i in range(num_homes)]
        community = CommunityController(transformer_limit=I_max)

        for house in houses:
            house.alpha = alpha
            house.sigma_human = sigma

        max_peak = 0.0
        total_community_cost = 0.0

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

            max_peak = max(max_peak, step_actual_peak)
            total_community_cost += step_actual_cost

          

        print(f"Sweep Done -> Alpha: {alpha:<4} | Sigma: {sigma:<4} | Peak: {max_peak:>5.2f} kW | Cost: £{total_community_cost:.2f}")

        results[sigma]['alphas'].append(alpha)
        results[sigma]['costs'].append(total_community_cost)
        results[sigma]['peaks'].append(max_peak)

#%%
print("\nGenerating 2D Pareto Graphs...")

fig, axes = plt.subplots(1, 3, figsize=(18, 6))
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728'] 

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
axes[1].axhline(y=I_max, color='r', linestyle='--', linewidth=2, label='Power Draw Limit (10kW)')
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
