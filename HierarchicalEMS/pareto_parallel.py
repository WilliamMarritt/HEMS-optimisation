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
import pickle



alphas = [0.01, 0.05, 0.15, 0.30, 0.50]
sigmas = [0.0, 0.1, 0.25, 0.5, 0.75]

# alphas = [0.30]
# sigmas = [0.75]
num_simulations = 20 

def run_single_simulation(params):
    alpha, sigma, seed_val = params
    np.random.seed(seed_val) 
    random.seed(seed_val)
    
    houses = [HouseAgent(i, PV_capacity, C_E, I_max / num_homes) for i in range(num_homes)]
    community = CommunityController(transformer_limit=I_max)
    
    for house in houses:
        house.alpha = alpha
        house.sigma_human = sigma

    cache = {
        'community_demand': [], 'community_actual_demand': [],
        'h0_soc': [], 'h0_thermal_storage': [], 'h0_fridge_temp': [], 'h0_freezer_temp': [],
        'h0_import': [], 'h0_discharge': [], 'h0_charge': [], 'h0_solar': [],
        'h0_heat_pump': [], 'h0_indoor_temp': [], 'all_houses_import': [[] for _ in range(num_homes)],
        'h0_dumb_heat_pump': [],
        'dumb_appliance_data': {app["name"]: [] for app in appliances},
        'appliance_data': {app["name"]: [] for app in appliances}
    }

    cache['dumb_appliance_data']['Fridge'] = []
    cache['dumb_appliance_data']['Freezer'] = []
    cache['appliance_data']['Fridge'] = []
    cache['appliance_data']['Freezer'] = []
    cache['appliance_data']['Unpredicted_Human_Load'] = []


    max_smart_peak = 0.0
    total_smart_cost = 0.0
    total_smart_net_energy = 0.0 

    smart_breach_count = 0
    smart_breach_energy = 0.0

    max_open_peak = 0.0
    total_open_cost = 0.0
    total_open_net_energy = 0.0 

    open_breach_count = 0
    open_breach_energy = 0.0

    days = 2

    for step in range(48*days): 
        approved_schedules, peak_demand = community.negotiate_schedules(houses, step)

        step_smart_import = 0.0
        step_smart_export = 0.0
        step_open_import = 0.0
        step_open_export = 0.0

        for house in houses:
            sched = next(s for s in approved_schedules if s["house_id"] == house.house_id)
            house.execute_physical_action(sched, step)
            
            step_smart_export += house.history_E.get(("Grid_Export", step), 0.0)
            step_smart_import += house.history_E.get(("Grid_Import", step), 0.0)
            
            abs_t = step % total_steps
            pv_gen = house.pv_capacity * solar_profile[abs_t]

            open_import = house.history_E.get(("Open_Loop_Import", step), 0.0)
            open_export = house.history_E.get(("Open_Loop_Export", step), 0.0)
            
            step_open_import += open_import
            step_open_export += open_export

            cache['all_houses_import'][house.house_id].append(house.history_E.get(("Grid_Import", step), 0.0))
        
        abs_t = step % total_steps
        
        cache['community_demand'].append(step_smart_import)
        cache['community_actual_demand'].append(step_open_import)
        h0 = houses[0]
        abs_t = step % total_steps
        cache['h0_soc'].append(h0.current_soc)
        cache['h0_thermal_storage'].append(h0.current_soc_th)
        cache['h0_fridge_temp'].append(h0.current_T_fridge)
        cache['h0_freezer_temp'].append(h0.current_T_freezer)
        cache['h0_indoor_temp'].append(h0.current_T_in)
        
        h0_sched = next(s for s in approved_schedules if s["house_id"] == 0)
        cache['h0_charge'].append(h0_sched.get("planned_charge_k0", 0.0))
        cache['h0_import'].append(h0.history_E.get(("Grid_Import", step), 0.0))
        cache['h0_discharge'].append(h0.history_E.get(("Battery_Discharge", step), 0.0))
        cache['h0_solar'].append(h0.pv_capacity * efficiency * solar_profile[abs_t])
        cache['h0_heat_pump'].append(h0.history_E.get(("Heat_Pump", step), 0.0))
        cache['h0_dumb_heat_pump'].append(h0.history_E.get(("Open_Loop_Heat_Pump", step), 0.0))

        cache['dumb_appliance_data']['Fridge'].append(h0.history_E.get(("Open_Loop_Fridge", step), 0.0))
        cache['dumb_appliance_data']['Freezer'].append(h0.history_E.get(("Open_Loop_Freezer", step), 0.0))
        cache['appliance_data']['Fridge'].append(h0.history_E.get(("Fridge", step), 0.0))
        cache['appliance_data']['Freezer'].append(h0.history_E.get(("Freezer", step), 0.0))
        cache['appliance_data']['Unpredicted_Human_Load'].append(h0.history_E.get(("Rogue_Load", step), 0.0))

        for app in appliances:
            name = app["name"]
            cache['dumb_appliance_data'][name].append(h0.history_E.get((f"Open_Loop_{name}", step), 0.0))
            
            if app.get("power_type", "constant") == "constant":
                count = sum(1 for past_t in range(max(0, step - int(app["Slots"]) + 1), step + 1) if h0.history_E.get((name, past_t), 0) == 1)
                cache['appliance_data'][name].append(count * app["Power"])
            else:
                cache['appliance_data'][name].append(h0.history_E.get((name, step), 0.0))

        net_smart_community_demand = max(0.0, step_smart_import - step_smart_export)
        net_open_community_demand = max(0.0, step_open_import - step_open_export)

        max_smart_peak = max(max_smart_peak, net_smart_community_demand)
        max_open_peak = max(max_open_peak, net_open_community_demand)

        if net_smart_community_demand > I_max:
            smart_breach_count += 1
            smart_breach_energy += (net_smart_community_demand - I_max) * delta
        if net_open_community_demand > I_max:
            open_breach_count += 1
            open_breach_energy += (net_open_community_demand - I_max) * delta
        
        price_in, price_out = price_grid_elec[abs_t], price_grid_export[abs_t]

        total_smart_cost += (step_smart_import * price_in * delta) - (step_smart_export * price_out * delta)
        total_open_cost += (step_open_import * price_in * delta) - (step_open_export * price_out * delta)

        total_smart_net_energy += (step_smart_import - step_smart_export) * delta
        total_open_net_energy += (step_open_import - step_open_export) * delta

    smart_end_soc = sum(h.current_soc for h in houses)
    open_end_soc = sum(h.open_soc for h in houses)
    soc_delta = smart_end_soc - open_end_soc
    average_price = sum(price_grid_elec[:48]) / 48.0
    total_smart_cost -= ((smart_end_soc - open_end_soc) * (sum(price_grid_elec[:48]) / 48.0))

    community_total_sla_score = 0.0
    sim_steps_run = 48

       
    for house in houses:
        total_tasks = 0.0
        fulfilled_tasks = 0.0
        
        # 1. Flexible Appliances (EV) 
        ev_appliance = next((app for app in house.personal_appliances if app["name"] == "Electric car"), None)
        if ev_appliance is not None:
            ts = ev_appliance.get("T_S", 0.0)
            tf = ev_appliance.get("T_F", 0.0)
            crosses_midnight = tf < ts 
            ev_req = ev_appliance.get("Required_Energy", 0.0)
            
            if ev_req > 0:
                ev_delivered = house.flexible_energy_delivered.get("Electric car", 0.0)
                total_tasks += 1.0
                expected_progress = min(1.0, (sim_steps_run - ts) / ((tf + 48) - ts) if crosses_midnight else 1.0)
                target_energy_by_end_of_sim = ev_req * expected_progress
                
                if target_energy_by_end_of_sim > 0:
                    fulfilled_tasks += min(1.0, ev_delivered / target_energy_by_end_of_sim)
                else:
                    fulfilled_tasks += 1.0 
                
        # 2. Standard Appliances
        for app in house.personal_appliances:
            if app.get("power_type") == "flexible":
                continue  # EV already handled above
    
            # if doesnt start in 24 hour sim still counted        
            window_opens_in_sim = any((app.get("T_S", 0.0) * steps_per_hour) <= s < sim_steps_run for s in range(sim_steps_run))

            if not window_opens_in_sim:
                continue

            total_tasks += 1.0
            if any(house.history_E.get((app["name"], s), 0) > 0 for s in range(sim_steps_run)):
                fulfilled_tasks += 1.0     

        # 3. Thermal Comfort 
        avg_temp = sum(house.history_T_in) / len(house.history_T_in) if house.history_T_in else 0
        total_tasks += 1.0
        if avg_temp >= 18.0: 
            fulfilled_tasks += 1.0
        elif avg_temp >= 16.0: 
            fulfilled_tasks += 0.5 + (0.5 * ((avg_temp - 16.0) / 2.0))
        
        house_sla_pct = (fulfilled_tasks / total_tasks) * 100 if total_tasks > 0 else 100.0
        community_total_sla_score += house_sla_pct

    avg_community_sla = community_total_sla_score / num_homes
    cost_saving_pct = (total_open_cost - total_smart_cost) / abs(total_open_cost) * 100 if total_open_cost != 0 else 0.0
    peak_reduction_pct = (max_open_peak - max_smart_peak) / max_open_peak * 100

    return {
        'Sigma': sigma, 'Alpha': alpha, 'Seed': seed_val,
        'Cost_Saving': cost_saving_pct, 'Peak_Reduction': peak_reduction_pct, 'SLA': avg_community_sla,
        'Smart_Breach_Count': smart_breach_count, 'Smart_Breach_Energy': smart_breach_energy,
        'Open_Breach_Count': open_breach_count, 'Open_Breach_Energy': open_breach_energy,
        'Smart_Peak': max_smart_peak, 'Open_Peak': max_open_peak,
        'Smart_Cost': total_smart_cost, 'Open_Cost': total_open_cost,
        'Smart_Energy': total_smart_net_energy, 'Open_Energy': total_open_net_energy,
        'Time_Series_Cache': cache  
    }

if __name__ == '__main__':
    csv_file = 'pareto_2day_10house_10kW.csv'
    cache_file = 'simulation_cache_1.pkl'
    all_cache = {}
    completed_runs = set()

    cols = ['Sigma', 'Alpha', 'Seed', 'Cost_Saving', 'Peak_Reduction', 'SLA', 
            'Smart_Breach_Count', 'Smart_Breach_Energy', 'Open_Breach_Count', 'Open_Breach_Energy',
            'Smart_Peak', 'Open_Peak', 'Smart_Cost', 'Open_Cost', 'Smart_Energy', 'Open_Energy']    
            
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            completed_runs = set(zip(df['Alpha'].round(4), df['Sigma'].round(4), df['Seed'].astype(int)))
        except: pass
    else:
        pd.DataFrame(columns=cols).to_csv(csv_file, index=False)

    all_combinations = [(round(a, 4), round(s, 4), seed) for a in alphas for s in sigmas for seed in range(num_simulations)]
    combinations = [c for c in all_combinations if c not in completed_runs]
    
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                all_cache = pickle.load(f)
        except: pass


    print(f"Resuming... {len(completed_runs)} completed, {len(combinations)} remaining.")

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(run_single_simulation, combo): combo for combo in combinations}
        
        for future in concurrent.futures.as_completed(futures):
            try:
                res = future.result()
                # Append single row to CSV immediately
                combo_key = (res['Alpha'], res['Sigma'], res['Seed'])
                cache_payload = res.pop('Time_Series_Cache')
                all_cache[combo_key] = cache_payload
                
                
                pd.DataFrame([res], columns=cols).to_csv(csv_file, mode='a', header=False, index=False)
                
                with open(cache_file, 'wb') as f:
                    pickle.dump(all_cache, f)
                
                print(f"Done -> Alpha: {res['Alpha']:<4} | Sigma: {res['Sigma']:<4} | Seed: {res['Seed']:<2} | Peak: {res['Peak_Reduction']:>5.2f} kW | Cost: {res['Cost_Saving']:.2f} | SLA: {res['SLA']:>5.2f}")
            except Exception as exc:
                print(f"A simulation crashed: {exc}")

    print("\nAll simulations finished! Averaging data for 2D Pareto Graphs...")

    final_df = pd.read_csv(csv_file)
    
    overall_avg_open_energy = final_df['Open_Energy'].mean()
    print(f"Overall Average Open Energy across all simulations: {overall_avg_open_energy:.2f} kWh")

    avg_df = final_df.groupby(['Sigma', 'Alpha']).mean().reset_index()

    results = {sigma: {'alphas': [], 'costs': [], 'peaks': [], 'slas': [], 
                       'count_reduction': [], 'energy_reduction': []} for sigma in sigmas}    
    
    for _, row in avg_df.iterrows():
       
        s = float(round(row['Sigma'], 2))
        if s in results:
            results[s]['alphas'].append(round(row['Alpha'], 4))
            results[s]['costs'].append(round(row['Cost_Saving'], 2))
            results[s]['peaks'].append(round(row['Peak_Reduction'], 2))
            results[s]['slas'].append(round(row['SLA'], 2))

            open_c = row['Open_Breach_Count']
            smart_c = row['Smart_Breach_Count']
            c_red = ((open_c - smart_c) / open_c * 100) if open_c > 0 else 0.0
            results[s]['count_reduction'].append(round(c_red, 2))

            open_e = row['Open_Breach_Energy']
            smart_e = row['Smart_Breach_Energy']
            e_red = ((open_e - smart_e) / open_e * 100) if open_e > 0 else 0.0
            results[s]['energy_reduction'].append(round(e_red, 2))

    for sigma in sigmas:
        sort_id = np.argsort(results[sigma]['alphas'])
        for key in ['alphas', 'costs', 'peaks', 'slas', 'count_reduction', 'energy_reduction']:
                results[sigma][key] = [results[sigma][key][i] for i in sort_id]

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', "#cc08b2"] 

    # [0, 0] Financial Benefit (Unchanged)
    for i, sigma in enumerate(sigmas):
        axes[0, 0].plot(results[sigma]['alphas'], results[sigma]['costs'], marker='o', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[0, 0].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[0, 0].set_ylabel('Cost Savings vs Dumb House (%)', fontsize=12)
    axes[0, 0].set_title('Financial Benefit of Smart HEMS', fontsize=14, fontweight='bold')
    axes[0, 0].grid(True, linestyle='--', alpha=0.7)
    axes[0, 0].legend()
    axes[0, 0].invert_xaxis()

    # Inserted: [0, 1] Breach Count Reduction
    for i, sigma in enumerate(sigmas):
        axes[0, 1].plot(results[sigma]['alphas'], results[sigma]['count_reduction'], marker='s', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[0, 1].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[0, 1].set_ylabel('Breach Count Reduction (%)', fontsize=12)
    axes[0, 1].set_title('1kW Breach Frequency Prevention', fontsize=14, fontweight='bold')
    axes[0, 1].grid(True, linestyle='--', alpha=0.7)
    axes[0, 1].legend()
    axes[0, 1].invert_xaxis()

    # Inserted: [0, 2] Breach Energy Reduction
    for i, sigma in enumerate(sigmas):
        axes[0, 2].plot(results[sigma]['alphas'], results[sigma]['energy_reduction'], marker='X', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[0, 2].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[0, 2].set_ylabel('Breach Energy Reduction (%)', fontsize=12)
    axes[0, 2].set_title('1kW Breach Severity Prevention', fontsize=14, fontweight='bold')
    axes[0, 2].grid(True, linestyle='--', alpha=0.7)
    axes[0, 2].legend()
    axes[0, 2].invert_xaxis()

    # [1, 0] SLA / Comfort (Unchanged)
    for i, sigma in enumerate(sigmas):
        axes[1, 0].plot(results[sigma]['alphas'], results[sigma]['slas'], marker='d', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[1, 0].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[1, 0].set_ylabel('Community SLA Fulfillment (%)', fontsize=12)
    axes[1, 0].set_title('User Comfort & Reliability (SLA)', fontsize=14, fontweight='bold')
    axes[1, 0].grid(True, linestyle='--', alpha=0.7)
    axes[1, 0].set_ylim(-5, 105)
    axes[1, 0].legend()
    axes[1, 0].invert_xaxis()

    # [1, 1] Peak Reduction (Unchanged)
    for i, sigma in enumerate(sigmas):
        axes[1, 1].plot(results[sigma]['alphas'], results[sigma]['peaks'], marker='v', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[1, 1].set_xlabel('Alpha (Risk Tolerance)', fontsize=12)
    axes[1, 1].set_ylabel('Absolute Peak Reduction (%)', fontsize=12)
    axes[1, 1].set_title('Max Demand: Absolute Peak Shaving', fontsize=14, fontweight='bold')
    axes[1, 1].grid(True, linestyle='--', alpha=0.7)
    axes[1, 1].legend()
    axes[1, 1].invert_xaxis()

    # Changed: [1, 2] Normalized Pareto now compares Cost Savings against Breach Energy Reduction
    for i, sigma in enumerate(sigmas):
        axes[1, 2].plot(results[sigma]['costs'], results[sigma]['energy_reduction'], marker='^', linewidth=2, color=colors[i], label=f'Sigma={sigma}kW')
    axes[1, 2].set_xlabel('Cost Savings (%)', fontsize=12)
    axes[1, 2].set_ylabel('Breach Energy Reduction (%)', fontsize=12)
    axes[1, 2].set_title('True Pareto: Economy vs. Grid Security', fontsize=14, fontweight='bold')
    axes[1, 2].grid(True, linestyle='--', alpha=0.7)
    axes[1, 2].legend()

    plt.tight_layout()
    plt.show()