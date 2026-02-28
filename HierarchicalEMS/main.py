# main.py

import time
from config import *
from house_agent import HouseAgent
from community_controller import CommunityController
from visualisation import plot_simulation_results
from data import *
import json

def run_simulation():
    print("Initialising Microgrid Community")
    houses = [HouseAgent(i, PV_capacity, C_E, I_max / num_homes) for i in range(num_homes)]    
    community = CommunityController(transformer_limit=I_max)

    history_community_demand = []
    history_h0_soc = []
    history_h0_fridge_temp = []
    history_actual_community_demand = []

    h0_import = []
    h0_discharge = []
    h0_charge = []
    h0_solar = []


    simulation_steps = 96

    print(f"Starting simulation for {num_homes} homes over {simulation_steps} steps")
    start_time = time.time()
    
    for step in range(simulation_steps):
        print(f"Time Step {step}")

        approved_schedules, peak_demand = community.negotiate_schedules(houses, step)
        
        step_physical_demand = 0.0
        current_solar_per_house = PV_capacity * solar_profile[step % total_steps]
        
        for sched in approved_schedules:
            h_import = sched.get("planned_import_k0", 0.0)
            h_charge = sched.get("planned_charge_k0", 0.0)
            h_discharge = sched.get("planned_discharge_k0", 0.0)
            
            # The Power Balance Formula
            h_load = h_import + current_solar_per_house + h_discharge - h_charge
            step_physical_demand += h_load
        
        # for total power demand plot
        history_actual_community_demand.append(step_physical_demand)

        history_community_demand.append(peak_demand)

        for house in houses:
            house_schedule = next((item for item in approved_schedules if item["house_id"] == house.house_id), None)

            if house_schedule is None:
                continue 
    
            house.execute_physical_action(house_schedule, step)

            if house.house_id == 0:
                apps = house_schedule.get("starting_appliances", [])
                app_text = f"  | Starting Appliances: {apps}" if apps else ""
                print(f"    House 0 Status: {house_schedule['explainability']} (Battery: {house.current_soc:.2f} kWh){app_text}")

        history_h0_soc.append(houses[0].current_soc)
        history_h0_fridge_temp.append(houses[0].current_T_fridge)
        

        h0_solar.append(PV_capacity * solar_profile[step % total_steps])
        h0_sched = next((item for item in approved_schedules if item["house_id"] == 0))
        h0_import.append(h0_sched["planned_import_k0"])
        h0_discharge.append(h0_sched["planned_discharge_k0"])
        h0_charge.append(h0_sched["planned_charge_k0"])
        

        
        print("-" * 25)

    end_time = time.time()
    print("Simulation Complete")
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    print(f"Maximum Community Peak Demand hit: {max(history_community_demand):.2f} kW")
    print(f"Transformer Limit: {I_max} kW")

    if max(history_community_demand) <= I_max + 0.1:
        print("Success: the limit was protected")
    else:
        print("WARNING: the community breached the limit.")

    print("\nSaving simulation data to disk...")
    save_data = {
        "community_demand": history_community_demand,
        "h0_soc": history_h0_soc
    }
    with open("simulation_results.json", "w") as f:
        json.dump(save_data, f, indent=4)
    print("Data saved to 'simulation_results.json'")

    print("\nGenerating visuals")
    
    appliance_data = {
        app["name"]: {'counts': [0] * simulation_steps, 'power': [0.0] * simulation_steps} 
        for app in appliances
    }
    
    # Keep tracking the fridge now removed from appliances dictionary in data.py
    appliance_data["Fridge"] = {'counts': [0] * simulation_steps, 'power': [0.0] * simulation_steps}

    for t in range(simulation_steps):
        for app in appliances:
            name = app["name"]
            power = app["Power"]
            duration = int(app["Slots"])
            count = 0

            fridge_power = 0.0
            
            # appliance_data["Fridge"]['counts'][t] = 1 if fridge_power > 0 else 0
            # appliance_data["Fridge"]['power'][t] = fridge_power

            for house in [houses[0]]: 
                for look_back in range(duration):
                    past_t = t - look_back
                    if past_t >= 0 and house.history_E.get((name, past_t), 0) == 1:
                        count += 1 
                        break 
            
            appliance_data[name]['counts'][t] = count
            appliance_data[name]['power'][t]  = count * power

        fridge_power = 0.0
        for house in [houses[0]]:
            fridge_power += house.history_E.get(("Fridge", t), 0.0)
                
        appliance_data["Fridge"]['counts'][t] = 1 if fridge_power > 0 else 0
        appliance_data["Fridge"]['power'][t] = fridge_power
    
        # fridge_count = 0
        # for house in [houses[0]]:
        #     if house.history_E.get(("Fridge", t), 0) == 1:
        #         fridge_count += 1
                
        # appliance_data["Fridge"]['counts'][t] = fridge_count
        # appliance_data["Fridge"]['power'][t] = fridge_count * 0.3 # 0.3 kW compressor power

    # Sort appliances for better visualisation (most used at the bottom)
    sorted_appliances = sorted(appliance_data.items(), key=lambda item: sum(item[1]['counts']), reverse=True) 
    
    print("\nAppliance Sort Order (by total time steps):")
    for name, data in sorted_appliances:
        print(f"  {name}: {sum(data['counts'])} steps")
    
    appliance_power_data = {name: data['power'] for name, data in sorted_appliances}

    plot_simulation_results(
        community_demand=history_community_demand,
        transformer_limit=I_max,
        h0_soc=history_h0_soc,
        grid_prices=price_grid_elec,
        appliance_data=appliance_power_data,
        h0_import=h0_import,
        h0_discharge=h0_discharge,
        h0_solar=h0_solar,
        h0_charge=h0_charge,
        h0_fridge_temp=history_h0_fridge_temp,
        community_actual_demand=history_actual_community_demand
    )

if __name__ == "__main__":
    run_simulation()