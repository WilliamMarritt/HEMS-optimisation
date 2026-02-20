# visualisation.py
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
from config import *
from data import *

def plot_results(history_u, history_I, history_soc_E, history_E, price_grid_elec):
    time_steps_96 = range(total_steps*2)
    hours = [t * delta for t in time_steps_96]

    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)

    # --- Plot 1: Power Balance ---
    chp_power = history_u
    grid_import = history_I

    total_demand = []
    for t in time_steps_96:
        local_t = t % total_steps
        d_t = electric_demand_per_house[local_t] * num_homes
        for h in homes:
            for app in appliances:
                name = app["name"]
                power = app["Power"]
                duration = int(app["Slots"])
                is_running = 0
                
                for look_back in range(duration):
                    if (t - look_back) >= 0 and history_E.get((h, name, t - look_back), 0) == 1:
                        is_running = 1
                if is_running:
                    d_t += power
        total_demand.append(d_t)

    axes[0].plot(hours, total_demand, 'k-', linewidth=2, label='Total Demand')
    axes[0].stackplot(hours, chp_power, grid_import, labels=['CHP Gen', 'Grid Import'], alpha = 0.6, colors=['#1f77b4', '#ff7f0e'])
    axes[0].set_ylabel('Power (kW)')
    axes[0].set_title('Building Power Balance')
    axes[0].legend(loc='upper left')
    axes[0].grid(True, alpha=0.3)

    # --- Plot 2: Battery SoC and Grid Price ---
    ax2 = axes[1]
    soc = history_soc_E
    line1 = ax2.plot(hours, soc, 'g-', label='Battery SoC (kWh)', linewidth=2)
    ax2.set_ylabel('Stored Energy (kWh)', color = 'b')
    ax2.tick_params(axis='y', labelcolor='b')
    ax2.set_ylim(0, C_E)

    ax2_price = ax2.twinx()
    price_grid_elec_96 =  price_grid_elec + price_grid_elec
    line2 = ax2_price.plot(hours, price_grid_elec_96, 'r--', label='Grid Price (£/kWh)', linewidth=2)
    ax2_price.set_ylabel('Grid Price (£/kWh)', color='r')
    ax2_price.tick_params(axis='y', labelcolor='r')

    lns = line1 + line2
    labels = [l.get_label() for l in lns]
    ax2.legend(lns, labels, loc='upper left')
    ax2.set_title('Battery State of Charge and Grid Price')
    ax2.grid(True, alpha=0.3)

    # --- Plot 3: Appliance Schedule ---
    appliance_data = {
            name: {'counts': [0] * (total_steps*2), 'power': [0] * (total_steps*2)} 
            for name in app_names
        }
    
    for t in time_steps_96:
        for app in appliances:
            name = app["name"]
            power = app["Power"]
            count = 0

            for h in homes:
                duration = int(app["Slots"])
                for look_back in range(duration):
                    if (t - look_back) >= 0 and history_E.get((h, name, t-look_back), 0) > 0.9:
                        count += 1 
                        break 
            
            appliance_data[name]['counts'][t] = count
            appliance_data[name]['power'][t]  = count * power
          
    # Sort appliances for better visualisation (most used at the bottom)
    sorted_appliances = sorted(appliance_data.items(), key=lambda item: sum(item[1]['counts']), reverse=True)   

    # Plot as a stacked bar chart 
    colors = cm.tab20.colors  # List of 20 colors
    bottom = np.zeros(total_steps*2)
    
    for i, (name, data) in enumerate(sorted_appliances):
        power_series = data['power']

        if sum(power_series) > 0: 
            axes[2].bar(hours, power_series, bottom=bottom, width=delta, label=name, alpha=0.8, align='edge', color=colors[i % 20])
            bottom += np.array(power_series)
            
    peak_power = max(bottom)
    # Safety check if peak is 0
    ylim_top = peak_power * 1.2 if peak_power > 0 else 1.0

    axes[2].set_ylabel("Power used by Appliances (kW)")
    axes[2].set_ylim(0, ylim_top)  # Add some headroom above the peak
    axes[2].set_xlabel("Hour of Day")
    axes[2].set_xticks(range(0, 49, 2))
    axes[2].set_title("Aggregate Appliance Scheduling")
    axes[2].legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    axes[2].grid(True, axis='y', alpha=0.3)

    plt.tight_layout()
    plt.show()