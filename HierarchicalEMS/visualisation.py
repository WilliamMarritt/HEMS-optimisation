# visualisation.py
import json
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np

def plot_simulation_results(community_demand, transformer_limit, h0_soc, grid_prices, appliance_data,
                            h0_import=None, h0_discharge=None, h0_solar=None, h0_charge=None, 
                            h0_fridge_temp=None, community_actual_demand=None, ) :
    
    # create a time axis in hours
    steps = len(community_demand)
    time_axis_hours = np.arange(steps) / 2.0

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12,10), sharex=True)

    # PLOT 1: plot community demand
    if community_actual_demand is not None:
        ax1.plot(time_axis_hours, community_actual_demand, label="Actual Physical Demand (kW)", color='purple', linewidth=2, alpha=0.5)
    
    ax1.plot(time_axis_hours, community_demand, label="Total Community Demand (kW)", color='blue', linewidth=2)
    ax1.plot(time_axis_hours, h0_soc, label="House 0 Battery SoC", color='green', linewidth=2)

    ax1.axhline(y=transformer_limit, color='red', linestyle='--', linewidth=2, label=f"Tranformer Limit ({transformer_limit} kW)")

    # Formatting Plot 1
    ax1.set_ylabel("Power Demand (kW)", color='blue', fontweight='bold')
    ax1.set_title("Microgrid Hierarchical Control: 48-Hour Simulation Results", fontsize=14, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    
    extended_prices = [grid_prices[i % len(grid_prices)] for i in range(steps)]

    # Add Grid Price on a secondary Y-axis to prove the system avoids expensive times
    ax1_price = ax1.twinx()
    ax1_price.plot(time_axis_hours, extended_prices, color='orange', linestyle='-.', linewidth=1.5, alpha=0.8, label="Grid Price (£/kWh)")
    ax1_price.set_ylabel("Grid Price (£/kWh)", color='orange', fontweight='bold')
    
    # Combine legends for Plot 1
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax1_price.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right')

    # PLOT 2: house 0 battery SoC
    # any solar generated that is not charging the battery is used to power house
    if h0_solar is not None and h0_charge is not None:
        solar_used = [max(0, s-c) for s, c in zip(h0_solar, h0_charge)]
    
    # Stack the supplies
        ax2.bar(time_axis_hours, h0_import, width=0.5, label="Grid Import", color='red', alpha=0.6, align='edge')
        ax2.bar(time_axis_hours, h0_discharge, bottom=h0_import, width=0.5, label="Battery Discharge", color='green', alpha=0.6, align='edge')
        bottom_solar = np.array(h0_import) + np.array(h0_discharge)
        ax2.bar(time_axis_hours, solar_used, bottom=bottom_solar, width=0.5, label="Solar Consumed", color='gold', alpha=0.6, align='edge')
                
        neg_charge = [-c for c in h0_charge]
        ax2.bar(time_axis_hours, neg_charge, width=0.5, label="Battery Charging", color='lightgreen', alpha=0.8, align='edge')
        ax2.axhline(y=0, color='black', linewidth=1)

        ax2.set_ylabel("Power Dispatch for house 0 (kW)", fontweight='bold')
        ax2.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)
        ax2.grid(True, linestyle=':', alpha=0.6)
    
    # Plot 3: stacked Appliance Schedule   

    colors = cm.tab20.colors  # List of 20 colors
    bottom = np.zeros(steps)
    
    for i, (name, power_series) in enumerate(appliance_data.items()):
        if sum(power_series) > 0: 
            ax3.bar(time_axis_hours, power_series, bottom=bottom, width=0.5, label=name, alpha=0.8, align='edge', color=colors[i % 20])
            bottom += np.array(power_series)

    peak_power = max(bottom) if len(bottom) > 0 else 1.0
    ax3.set_ylim(0, peak_power * 1.2 if peak_power > 0 else 1.0) 
    ax3.set_ylabel("Power used (kW)", fontweight='bold')
    ax3.set_xlabel("Time (Hours)", fontweight='bold')
    
    # Legend outside the plot to the right
    ax3.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)
    ax3.grid(True, axis='y', linestyle=':', alpha=0.6)

    # if h0_fridge_temp is not None:
    #     ax4.plot(time_axis_hours, h0_fridge_temp, label="Internal Temp ($^\circ\text{C}$)", color='cyan', linewidth=2)
    #     ax4.axhline(y=4.0, color='black', linestyle=':', linewidth=1.5, label="Target ($4.0^\circ\text{C}$)")
    #     ax4.axhline(y=6.0, color='red', linestyle='--', linewidth=1.5, label="Max Safe Temp ($6.0^\circ\text{C}$)")
        
    #     ax4.set_ylabel("Fridge Temp ($^\circ\text{C}$)", color='c', fontweight='bold')
    #     ax4.set_ylim(3.5, 6.5)
    #     ax4.legend(loc='upper left')
    #     ax4.grid(True, linestyle=':', alpha=0.6)

    #     # Add the continuous compressor power on a secondary axis
    #     if "Fridge" in appliance_data:
    #         ax4_power = ax4.twinx()
    #         ax4_power.fill_between(time_axis_hours, appliance_data["Fridge"], color='lightsteelblue', alpha=0.4, step='post', label="Compressor Power (kW)")            
    #         ax4_power.set_ylabel("Compressor Power (kW)", color='lightsteelblue', fontweight='bold')
    #         ax4_power.set_ylim(0, 0.4)
    #         ax4_power.legend(loc='upper right')

    # ax4.set_xlabel("Time (Hours)", fontweight='bold')



    # Final layout adjustments and save
    plt.tight_layout()
    plt.savefig("Final_Simulation_Results.png", dpi=300)
    print("\nGraph saved as 'Final_Simulation_Results.png'")
    plt.show()

