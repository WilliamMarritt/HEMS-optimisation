# main.py

import time
from config import *
from house_agent import HouseAgent
from community_controller import CommunityController
from visualisation import plot_simulation_results
from data import *  
import json
import random
import pickle

PLAYBACK_MODE = False
PLAYBACK_ALPHA = 0.01
PLAYBACK_SIGMA = 0.75
PLAYBACK_SEED = 0
CACHE_FILE = 'simulation_cache_extended.pkl'



def run_simulation():
    # locks the random shifting to a specific repeatable timeline
    if PLAYBACK_MODE:
        print(f"Loading data for Alpha={PLAYBACK_ALPHA}, Sigma={PLAYBACK_SIGMA}, Seed={PLAYBACK_SEED} from cache")
        try:
            with open(CACHE_FILE, 'rb') as f:
                all_cache = pickle.load(f)
        except:
            print("Error: File not found")
            return
        
        cache_key = (PLAYBACK_ALPHA, PLAYBACK_SIGMA, PLAYBACK_SEED)
        if cache_key not in all_cache:
            print(f"Error: Combination {cache_key} not found in cache data")
            return
    
        data = all_cache[cache_key]
        print("Data Loaded")

        plot_simulation_results(
            community_demand=data['community_demand'],
            dumb_appliance_data=data['dumb_appliance_data'],
            h0_dumb_heat_pump=data['h0_dumb_heat_pump'],
            transformer_limit=I_max,
            h0_soc=data['h0_soc'],
            grid_prices=price_grid_elec, 
            appliance_data=data['appliance_data'],
            h0_import=data['h0_import'],
            h0_discharge=data['h0_discharge'],
            h0_solar=data['h0_solar'],
            h0_charge=data['h0_charge'],
            h0_fridge_temp=data['h0_fridge_temp'],
            h0_freezer_temp=data['h0_freezer_temp'],
            community_actual_demand=data['community_actual_demand'],
            h0_heat_pump=data['h0_heat_pump'],
            h0_thermal_storage=data['h0_thermal_storage'],
            h0_indoor_temp=data['h0_indoor_temp'],
            all_houses_import=data['all_houses_import']
        )
        return

    random.seed(0)
    simulation_steps = 96

    print("Initialising Microgrid Community")
    houses = [HouseAgent(i, PV_capacity, C_E, I_max / num_homes) for i in range(num_homes)]    
    community = CommunityController(transformer_limit=I_max)

    history_community_demand = []
    history_h0_soc = []
    history_h0_soc_th = []
    history_h0_fridge_temp = []
    history_h0_freezer_temp = []
    history_actual_community_demand = []

    h0_import = []
    h0_discharge = []
    h0_charge = []
    h0_solar = []

    print(f"Starting simulation for {num_homes} homes over {simulation_steps} steps")
    start_time = time.time()
    
    for step in range(simulation_steps):
        vprint(f"Time Step {step}")

        approved_schedules, peak_demand = community.negotiate_schedules(houses, step)

        # Calculate total community slack
        total_planned_import = sum(sched["planned_import_k0"] for sched in approved_schedules)
        global_slack = max(0.0, I_max - total_planned_import)

        for sched in approved_schedules:
            sched["community_slack_k0"] = global_slack
        
        for house in houses:
            house_schedule = next((item for item in approved_schedules if item["house_id"] == house.house_id), None)
            if house_schedule is not None:
                house.execute_physical_action(house_schedule, step)

        step_true_community_import = 0.0
        step_open_community_demand = 0.0
        
        for house in houses:
            net_import = house.history_E.get(("Grid_Import", step), 0.0)
            solar_export = house.history_E.get(("Grid_Export", step), 0.0)
            step_true_community_import += (net_import - solar_export)

            # pv_gen = house.history_E.get(("PV_Generation", step), 0.0)
            # open_import, open_export = house.calculate_open_loop_demand(step, pv_gen)
            # house.history_E[("Open_Loop_Import", step)] = open_import
            # house.history_E[("Open_Loop_Export", step)] = open_export
            open_import = house.history_E.get(("Open_Loop_Import", step), 0.0)
            open_export = house.history_E.get(("Open_Loop_Export", step), 0.0)
            step_open_community_demand += open_import

        step_true_community_import = max(0.0, step_true_community_import)
        history_community_demand.append(step_true_community_import)
        history_actual_community_demand.append(step_open_community_demand)

        # Log House 0 specific data for the detailed slides
        history_h0_soc.append(houses[0].current_soc)
        history_h0_soc_th.append(houses[0].current_soc_th)
        history_h0_fridge_temp.append(houses[0].current_T_fridge)
        history_h0_freezer_temp.append(houses[0].current_T_freezer)
        
        h0_solar.append(PV_capacity * efficiency* solar_profile[step % total_steps])
        
        h0_sched = next((item for item in approved_schedules if item["house_id"] == 0))
        h0_import.append(houses[0].history_E.get(("Grid_Import", step), 0.0))
        h0_discharge.append(houses[0].history_E.get(("Battery_Discharge", step), 0.0))
        h0_charge.append(h0_sched["planned_charge_k0"])
        
        if houses[0].house_id == 0:
            apps = h0_sched.get("starting_appliances", [])
            app_text = f"  | Starting Appliances: {apps}" if apps else ""
            vprint(f"    House 0 Status: {h0_sched['explainability']} (Battery: {houses[0].current_soc:.2f} kWh){app_text}")

        vprint("-" * 25)

    end_time = time.time()

    print("\n" + "="*40)
    print("  TOTAL SIMULATION HOUSE ENERGY SUMMARY")
    print("="*40)

    community_total_sla_score = 0.0
    sim_steps_run = len(houses[0].history_T_in)
    
    for house in houses:
        # Find the absolute highest peak from the open loop vs closed loop
        total_tasks = 0.0
        fulfilled_tasks = 0.0
        
        ev_appliance = next((app for app in house.personal_appliances if app["name"] == "Electric car"), None)
        if ev_appliance is not None:
            ev_req = ev_appliance.get("Required_Energy", 0.0)
            if ev_req > 0:
                # Sum the exact kW pulled at every step * 0.5 hours (delta)
                ev_delivered = house.flexible_energy_delivered.get("Electric car", 0.0)                
                total_tasks += 1.0
                fulfilled_tasks += min(1.0, ev_delivered / ev_req)

        # Standard appliances - binary score
        for app in house.personal_appliances:
            if app.get("power_type") == "flexible": 
                continue # Already handled EV
            total_tasks += 1.0
            if any(house.history_E.get((app["name"], s), 0) > 0 for s in range(sim_steps_run)):
                    fulfilled_tasks += 1.0
        
        # Instead of a strict 18.0 threshold, calculate the average temperature.        thermal_steps_ok = sum(1 for t in house.history_T_in if t >= 18.0)
        avg_temp = sum(house.history_T_in) / sim_steps_run if sim_steps_run > 0 else 0
            
        total_tasks += 1.0
        if avg_temp >= 18.0:
            fulfilled_tasks += 1.0
        elif avg_temp >= 16.0:
            # Partial credit: 16.0C to 17.9C gives a sliding scale from 50% to 95%
            fulfilled_tasks += 0.5 + (0.5 * ((avg_temp - 16.0) / 2.0))
        else:
            fulfilled_tasks += 0.0
        
        # Calculate final percentage for this house
        house_sla_pct = (fulfilled_tasks / total_tasks) * 100 if total_tasks > 0 else 100.0
        community_total_sla_score += house_sla_pct

        max_raw_peak = 0.0
        peak_raw_step = 0
        for s in range(simulation_steps):
            val = house.history_E.get(("Open_Loop_Import", s), 0.0)
            if val > max_raw_peak:
                max_raw_peak = val
                peak_raw_step = s
        
        peak_time_hours = peak_raw_step * delta
        
        # Identify which devices were running during that peak step
        causing_devices = []
        dumb_hp = house.history_E.get(("Open_Loop_Heat_Pump", peak_raw_step), 0.0)
        if dumb_hp > 0.1:
            causing_devices.append(f"Heat Pump ({dumb_hp:.1f}kW)")
            
        for app in appliances:
            dumb_pwr = house.history_E.get((f"Open_Loop_{app['name']}", peak_raw_step), 0.0)
            if dumb_pwr > 0.1:
                causing_devices.append(f"{app['name']} ({dumb_pwr:.1f}kW)")
                
        device_str = ", ".join(causing_devices) if causing_devices else "Base Load / Standard Appliances"

        max_controlled_peak = max([house.history_E.get(("Grid_Import", s), 0) for s in range(simulation_steps)])
        
        vprint(f"House {house.house_id}:")
        vprint(f"  Unsmart House (Open Loop):")
        vprint(f"    - Grid Import Peak : {max_raw_peak:.2f} kW (Hit at Hour {peak_time_hours})")
        vprint(f"    - Devices Causing Peak : {device_str}")
        vprint(f"    - Total Energy Used (48h): {house.daily_total_uncontrolled_energy:.2f} kWh")
        vprint(f"  Smart HEMS (Closed Loop):")
        vprint(f"    - Grid Import Peak : {max_controlled_peak:.2f} kW")
        vprint(f"    - Total Energy Used (48h): {house.daily_total_controlled_energy:.2f} kWh")

        ev_appliance = next((app for app in appliances if app["name"] == "Electric car"), None)#
        if ev_appliance is not None:
            ev_delivered = house.flexible_energy_delivered.get("Electric car", 0.0)
            ev_req = next((app["Required_Energy"] for app in appliances if app["name"] == "Electric car"), 0.0)
            vprint(f"    - EV Charge Delivered: {ev_delivered:.2f} kWh / {ev_req:.2f} kWhn")
        else:
            vprint(f"    - EV Charge Delivered: (Car not used today)")
        vprint(f"    - Comprehensive Service Level (SLA): {house_sla_pct:.1f}%\n")

    uncontrolled_community_peak = max(history_actual_community_demand)
    controlled_community_peak = max(history_community_demand)
    print("Simulation Complete")
    print(f"Time taken: {end_time - start_time:.2f} seconds")

    print(f"Maximum Community Peak Demand hit: {controlled_community_peak:.2f} kW")
    print(f"Uncontrolled Peak:  {uncontrolled_community_peak:.2f} kW")
    print(f"Power Draw Limit: {I_max} kW")
 
    avg_uncontrolled_demand = sum(history_actual_community_demand) / simulation_steps
    avg_controlled_demand = sum(history_community_demand) / simulation_steps
    
    uncontrolled_par = uncontrolled_community_peak / avg_uncontrolled_demand if avg_uncontrolled_demand > 0 else 0
    controlled_par = controlled_community_peak / avg_controlled_demand if avg_controlled_demand > 0 else 0
    
    uncontrolled_breaches = sum(1 for d in history_actual_community_demand if d > I_max + 0.01)
    controlled_breaches = sum(1 for d in history_community_demand if d > I_max + 0.01)

    total_uncontrolled_cost = 0.0
    total_controlled_cost = 0.0
    total_controlled_export_kwh = 0.0

    for step in range(simulation_steps):
        price_in = price_grid_elec[step % total_steps]
        price_out = price_grid_export[step % total_steps]
        
        step_open_import = sum(h.history_E.get(("Open_Loop_Import", step), 0.0) for h in houses)
        step_open_export = sum(h.history_E.get(("Open_Loop_Export", step), 0.0) for h in houses)

        step_smart_import = sum(h.history_E.get(("Grid_Import", step), 0.0) for h in houses)
        step_smart_export = sum(h.history_E.get(("Grid_Export", step), 0.0) for h in houses)
        
        total_uncontrolled_cost += (step_open_import * price_in * delta) - (step_open_export * price_out * delta)
        total_controlled_cost += (step_smart_import * price_in * delta) - (step_smart_export * price_out * delta)
        total_controlled_export_kwh += step_smart_export * delta

    fridge_violations = sum(1 for t in history_h0_fridge_temp if t > 5.5)

    header = '\n\nPerformance Metric'   # < Python 3.12 does not support \ in f strings
    print(f"{header:<35} | {'Uncontrolled Grid':<11} | {'Smart Grid':<11}")
    print("-" * 65)
    print("Grid Stability")
    print(f"  Absolute Peak Demand (kW)         | {uncontrolled_community_peak:<11.2f} | {controlled_community_peak:<11.2f}")
    print(f"  Peak-to-Average Ratio (PAR)       | {uncontrolled_par:<11.2f} | {controlled_par:<11.2f}")
    print(f"  Transformer Breaches (30m steps)  | {uncontrolled_breaches:<11} | {controlled_breaches:<11}")
    print("-" * 65)
    print("Community Economics")
    print(f"  Total Energy Cost (£)             | £{total_uncontrolled_cost:<10.2f} | £{total_controlled_cost:<10.2f}")
    if total_uncontrolled_cost > 0:
        savings_pct = ((total_uncontrolled_cost - total_controlled_cost) / total_uncontrolled_cost) * 100
        print(f"  Cost Savings (%)                  | {'---':<11} | {savings_pct:.1f}%")
    print(f"  Peer-to-Peer Solar Export (kWh)   | {'0.00':<11} | {total_controlled_export_kwh:<11.2f}")
    print("-" * 65)
    print("User Comfort")
    print(f"  H0 Fridge Violations (>5.5°C)     | {'0':<11} | {fridge_violations:<11}")
    avg_community_sla = community_total_sla_score / num_homes
    print(f"  Community Appliance SLA (%)       | {'100.0%':<11} | {avg_community_sla:.1f}%")

    total_uncontrolled_kwh = sum(house.daily_total_uncontrolled_energy for house in houses)
    total_controlled_kwh = sum(house.daily_total_controlled_energy for house in houses)

    print(f"Dumb Grid (Uncontrolled) : {total_uncontrolled_kwh:.2f} kWh")
    print(f"Smart Grid (Controlled)  : {total_controlled_kwh:.2f} kWh")


    if max(history_community_demand) <= I_max + 0.1:
        print("Success: the limit was protected")
    else:
        print("WARNING: the community breached the limit.")
    print("\nGenerating visuals")
    
    appliance_data = {
        app["name"]: {'counts': [0] * simulation_steps, 'power': [0.0] * simulation_steps} 
        for app in appliances
    }
    
    # Keep tracking the fridge now removed from appliances dictionary in data.py
    appliance_data["Fridge"] = {'counts': [0] * simulation_steps, 'power': [0.0] * simulation_steps}
    appliance_data["Freezer"] = {'counts': [0] * simulation_steps, 'power': [0.0] * simulation_steps}
   
    for t in range(simulation_steps):
        for app in appliances:
            name = app["name"]
            power_type = app.get("power_type", "constant")       

            rogue_power_total = 0.0
            for house in [houses[0]]:
                rogue_power_total += house.history_E.get(("Rogue_Load", t), 0.0)

            # Ensure the dictionary key exists before assigning
            if "Unpredicted_Human_Load" not in appliance_data:
                appliance_data["Unpredicted_Human_Load"] = {'counts': [0] * simulation_steps, 'power': [0.0] * simulation_steps}
                
            appliance_data["Unpredicted_Human_Load"]['counts'][t] = 1 if rogue_power_total > 0 else 0
            appliance_data["Unpredicted_Human_Load"]['power'][t] = rogue_power_total

            if power_type == "constant":
                power = app["Power"]
                duration = int(app["Slots"])
                count = 0
                for house in [houses[0]]:
                    for look_back in range(duration):
                        past_t = t - look_back
                        if past_t >= 0 and house.history_E.get((name, past_t), 0) == 1:
                            count += 1
                            break

                appliance_data[name]['counts'][t] = count
                appliance_data[name]['power'][t] = count * power

            elif power_type == "flexible":
                exact_power = 0.0
                for house in [houses[0]]:
                    exact_power += house.history_E.get((name, t), 0.0)
                
                appliance_data[name]['counts'][t] = 1 if exact_power > 0 else 0
                appliance_data[name]['power'][t] = exact_power

            
        fridge_power = 0.0
        freezer_power = 0.0
        #
        for house in [houses[0]]:
            fridge_power += house.history_E.get(("Fridge", t), 0.0)
            freezer_power += house.history_E.get(("Freezer", t), 0.0)
                
        appliance_data["Fridge"]['counts'][t] = 1 if fridge_power > 0 else 0
        appliance_data["Fridge"]['power'][t] = fridge_power

        appliance_data["Freezer"]['counts'][t] = 1 if freezer_power > 0 else 0
        appliance_data["Freezer"]['power'][t] = freezer_power
    
    # Sort appliances for better visualisation (most used at the bottom)
    sorted_appliances = sorted(appliance_data.items(), key=lambda item: sum(item[1]['counts']), reverse=True) 
    
    h0_heat_pump = []
    for t in range(simulation_steps):
        hp_power = houses[0].history_E.get(("Heat_Pump", t), 0.0)
        h0_heat_pump.append(hp_power)


    # print("\nAppliance Sort Order (by total time steps):")
    # for name, data in sorted_appliances:
    #     print(f"  {name}: {sum(data['counts'])} steps")
    
    appliance_power_data = {name: data['power'] for name, data in sorted_appliances}

    all_houses_import = []
    for h in houses:
        house_history = [h.history_E.get(("Grid_Import", step), 0.0) for step in range(total_steps*2)]
        all_houses_import.append(house_history)

    test_step = 26
    sum_of_individual_imports = sum(house[test_step] for house in all_houses_import)
    total_community_demand = history_actual_community_demand[test_step]
    sum_of_individual_exports = sum(house.history_E.get(("Grid_Export", test_step), 0.0) for house in houses)

    # print(f"Sum of individual house imports: {sum_of_individual_imports} kW")
    # print(f"Sum of individual house exports: {sum_of_individual_exports} kW")
    # print(f"Net community transformer load: {total_community_demand} kW")
    dumb_appliance_data = {app["name"]: [0.0] * simulation_steps for app in appliances}
    dumb_appliance_data["Fridge"] = [0.0] * simulation_steps
    dumb_appliance_data["Freezer"] = [0.0] * simulation_steps
    h0_dumb_heat_pump = [0.0] * simulation_steps


    for t in range(simulation_steps):
        h0_dumb_heat_pump[t] = houses[0].history_E.get(("Open_Loop_Heat_Pump", t), 0.0)
        
        dumb_appliance_data["Fridge"][t] = houses[0].history_E.get(("Open_Loop_Fridge", t), 0.0)
        dumb_appliance_data["Freezer"][t] = houses[0].history_E.get(("Open_Loop_Freezer", t), 0.0)
        for app in appliances:
            dumb_appliance_data[app["name"]][t] = houses[0].history_E.get((f"Open_Loop_{app['name']}", t), 0.0)
            
    plot_simulation_results(
        community_demand=history_community_demand,
        dumb_appliance_data=dumb_appliance_data,
        h0_dumb_heat_pump=h0_dumb_heat_pump,
        transformer_limit=I_max,
        h0_soc=history_h0_soc,
        grid_prices=price_grid_elec,
        appliance_data=appliance_power_data,
        h0_import=h0_import,
        h0_discharge=h0_discharge,
        h0_solar=h0_solar,
        h0_charge=h0_charge,
        h0_fridge_temp=history_h0_fridge_temp,
        h0_freezer_temp=history_h0_freezer_temp,
        community_actual_demand=history_actual_community_demand,
        h0_heat_pump=h0_heat_pump,
        h0_thermal_storage=history_h0_soc_th,
        h0_indoor_temp=houses[0].history_T_in,  
        all_houses_import=all_houses_import        
    )

if __name__ == "__main__":
    run_simulation()