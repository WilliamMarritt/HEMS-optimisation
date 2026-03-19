# baseline.py
from config import *
from data import *

def run_uncoordinated_baseline():
    print("Running Uncoordinated Baseline Simulation (48 hours)...")
    
    time_steps_48h = range(total_steps * 2)
    
    total_cost = 0
    total_co2 = 0
    
    # Track metrics for  graph 
    history_I = []
    
    for t in time_steps_48h:
        local_t = t % total_steps
        day = t // total_steps
        
        elec_demand = electric_demand_per_house[local_t] * num_homes
        heat_demand = heat_demand_per_house[local_t] * num_homes
        
        # Add Appliance Demands (Uncoordinated: Everyone starts exactly at T_S)
        appliance_load = 0
        for app in appliances:
            name = app["name"]
            power = app["Power"]
            duration = int(app["Slots"])
            start_step = int(app["T_S"] * steps_per_hour)
            
            # Check if this appliance is running right now based on its strictly forced start time
            for look_back in range(duration):
                past_t = t - look_back
                if past_t >= 0:
                    past_local_t = past_t % total_steps
                    if past_local_t == start_step:
                        appliance_load += power*30
                        
        total_elec_demand = elec_demand + appliance_load
        
     
        # No Battery, No CHP
        grid_import = total_elec_demand
        boiler_output = heat_demand
        
        # Calculate Base vs Extra Import for the 60 kW Threshold Penalty
        if grid_import > I_max:
            I_base = I_max
            I_extra = grid_import - I_max
        else:
            I_base = grid_import
            I_extra = 0
            
        history_I.append(grid_import)
            
        # Electricity: Base price + 5p penalty for going over the threshold
        elec_cost = delta * ((I_base + I_extra) * price_grid_elec[local_t] + (I_extra * 0.05))
        # Gas: Boiler runs at 85% efficiency
        gas_cost = delta * ((boiler_output / 0.85) * price_gas)
        
        total_cost += elec_cost + gas_cost
        
        elec_co2 = delta * (grid_import * CO2_grid[local_t])
        gas_co2 = delta * (boiler_output * xi_Boiler)
        
        total_co2 += elec_co2 + gas_co2

    print("\n--- UNCOORDINATED BASELINE RESULTS ---")
    print(f"Total 48h Cost: £{total_cost:.2f}")
    print(f"Total 48h CO2:  {total_co2:.2f} kg")
    print(f"Peak Grid Import: {max(history_I):.2f} kW")
    print("-" * 38)
    
    return total_cost, total_co2, history_I

if __name__ == "__main__":
    run_uncoordinated_baseline()