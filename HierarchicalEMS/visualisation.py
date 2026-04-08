# visualisation.py
import json
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
from matplotlib.widgets import Button
from config import COP  # Import COP to calculate thermal output

def plot_simulation_results(community_demand,  dumb_appliance_data=None, h0_dumb_heat_pump=None,
                            transformer_limit=None, h0_soc=None, grid_prices=None, appliance_data=None,
                            h0_import=None, h0_discharge=None, h0_solar=None, h0_charge=None, 
                            h0_fridge_temp=None, h0_freezer_temp=None, community_actual_demand=None, 
                            h0_heat_pump=None, h0_thermal_storage=None, all_houses_import=None, h0_indoor_temp=None) :
    
    steps = len(community_demand)
    time_axis_hours = np.arange(steps) / 2.0
    
    x_ticks = np.arange(0, max(time_axis_hours) + 3, 3)

    fig = plt.figure(figsize=(18, 8))
    plt.subplots_adjust(bottom=0.2, right=0.80, hspace=0.35)

    # Subplots setup
    ax1_top = fig.add_subplot(211)
    ax1_bottom = fig.add_subplot(212, sharex=ax1_top)
    
    ax2 = fig.add_subplot(111)
    ax3 = fig.add_subplot(111)
    ax4 = fig.add_subplot(111)
    
    # Split Slide 5 into two axes
    ax5_top = fig.add_subplot(211)
    ax5_bottom = fig.add_subplot(212, sharex=ax1_top)

    ax6 = fig.add_subplot(111)
    ax7 = fig.add_subplot(111)

    # Apply the 3-hour ticks to all axes
    for ax in [ax1_top, ax1_bottom, ax2, ax3, ax4, ax5_top, ax5_bottom, ax6]:
        ax.set_xticks(x_ticks)

    # SLIDE 1: Community Demand & Grid Prices
    if community_actual_demand is not None:
        ax1_top.plot(time_axis_hours, community_actual_demand, label="Uncontrolled Loop Demand (kW)", color='purple', linewidth=2, alpha=0.5)
    
    ax1_top.plot(time_axis_hours, community_demand, label="Total Community Grid Import (kW)", color='blue', linewidth=2)
    ax1_top.axhline(y=transformer_limit, color='red', linestyle='--', linewidth=2, label=f"Transformer Limit ({transformer_limit} kW)")

    ax1_top.set_ylabel("Power (kW)", fontweight='bold')
    ax1_top.set_title("Slide 1/6: Microgrid Hierarchical Control", fontsize=14, fontweight='bold')
    ax1_top.grid(True, linestyle=':', alpha=0.6)
    
    extended_prices = [grid_prices[i % len(grid_prices)] for i in range(steps)]
    ax1_price = ax1_top.twinx()
    ax1_price.plot(time_axis_hours, extended_prices, color='orange', linestyle='-.', linewidth=1.5, alpha=0.8, label="Grid Price (£/kWh)")
    ax1_price.set_ylabel("Grid Price (£/kWh)", color='orange', fontweight='bold')
    
    lines_1, labels_1 = ax1_top.get_legend_handles_labels()
    lines_2, labels_2 = ax1_price.get_legend_handles_labels()
    ax1_top.legend(lines_1 + lines_2, labels_1 + labels_2, bbox_to_anchor=(1.03, 1), loc='upper left', borderaxespad=0.)

    if h0_solar is not None and h0_soc is not None:
        ax1_bottom.plot(time_axis_hours, h0_solar, label="H0 Solar Input (kW)", color='gold', linewidth=2)
        ax1_bottom.set_ylabel("Solar Power (kW)", fontweight='bold')
        ax1_bottom.set_xlabel("Time (Hours)", fontweight='bold')
        ax1_bottom.grid(True, linestyle=':', alpha=0.6)

        ax1_soc = ax1_bottom.twinx()
        ax1_soc.plot(time_axis_hours, h0_soc, label="House 0 Battery SoC (kWh)", color='green', linewidth=2)
        ax1_soc.set_ylabel("Stored Energy (kWh)", color='green', fontweight='bold')
        ax1_soc.set_ylim(ymin=0)


        lines_b1, labels_b1 = ax1_bottom.get_legend_handles_labels()
        lines_b2, labels_b2 = ax1_soc.get_legend_handles_labels()
        ax1_bottom.legend(lines_b1 + lines_b2, labels_b1 + labels_b2, bbox_to_anchor=(1.03, 1), loc='upper left', borderaxespad=0.)


    # SLIDE 2: Power Dispatch
    if h0_solar is not None and h0_charge is not None:
        solar_used = [max(0, s-c) for s, c in zip(h0_solar, h0_charge)]
        ax2.bar(time_axis_hours, h0_import, width=0.5, label="Grid Import", color='red', alpha=0.6, align='edge')
        ax2.bar(time_axis_hours, h0_discharge, bottom=h0_import, width=0.5, label="Battery Discharge", color='green', alpha=0.6, align='edge')
        bottom_solar = np.array(h0_import) + np.array(h0_discharge)
        ax2.bar(time_axis_hours, solar_used, bottom=bottom_solar, width=0.5, label="Solar Consumed", color='gold', alpha=0.6, align='edge')
        
        neg_charge = [-c for c in h0_charge]
        ax2.bar(time_axis_hours, neg_charge, width=0.5, label="Battery Charging", color='lightgreen', alpha=0.8, align='edge')
        ax2.axhline(y=0, color='black', linewidth=1)

        ax2.set_ylabel("Power Dispatch for house 0 (kW)", fontweight='bold')
        ax2.set_xlabel("Time (Hours)", fontweight='bold')
        ax2.set_title("Slide 2/6: House 0 Power Dispatch", fontsize=14, fontweight='bold')
        ax2.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)
        ax2.grid(True, linestyle=':', alpha=0.6)

    # SLIDE 3: Stacked Appliance Schedule
    colors = cm.tab20.colors
    bottom_arr = np.zeros(steps)
    
    if h0_heat_pump is not None and sum(h0_heat_pump) > 0:
        ax3.bar(time_axis_hours, h0_heat_pump, bottom=bottom_arr, width=0.5, label="Heat Pump", alpha=0.8, align="edge", color="purple")
        bottom_arr += np.array(h0_heat_pump)

    for i, (name, power_series) in enumerate(appliance_data.items()):
        if sum(power_series) > 0: 
            ax3.bar(time_axis_hours, power_series, bottom=bottom_arr, width=0.5, label=name, alpha=0.8, align='edge', color=colors[i % 20])
            bottom_arr += np.array(power_series)

    peak_power = max(bottom_arr) if len(bottom_arr) > 0 else 1.0
    ax3.set_ylim(0, peak_power * 1.2 if peak_power > 0 else 1.0) 
    ax3.set_ylabel("Power used (kW)", fontweight='bold')
    ax3.set_xlabel("Time (Hours)", fontweight='bold')
    ax3.set_title("Slide 3/6: House 0 Stacked Appliance Schedule", fontsize=14, fontweight='bold')
    ax3.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)
    ax3.grid(True, axis='y', linestyle=':', alpha=0.6)

    # SLIDE 4: Heat Pump & Thermal Storage
    if h0_heat_pump is not None:
        hp_thermal_output = [p * COP for p in h0_heat_pump]
        
        # Bottom axis (Power)
        ax4.fill_between(time_axis_hours, 0, hp_thermal_output, color='purple', alpha=0.3, label=f"HP Thermal Output (COP {COP})")
        ax4.plot(time_axis_hours, hp_thermal_output, color='purple', linewidth=2)
        
        ax4.set_ylabel("Thermal Power (kW)", fontweight='bold')
        ax4.set_xlabel("Time (Hours)", fontweight='bold')
        ax4.set_title("Slide 4/6: House 0 Thermodynamics & Storage", fontsize=14, fontweight='bold')
        ax4.grid(True, linestyle='--', alpha=0.5)

        # Top axis (Temperatures and Tank)
        ax4_temp = ax4.twinx()
        
        # Plot Indoor Temperature
        if h0_indoor_temp is not None:
            ax4_temp.plot(time_axis_hours, h0_indoor_temp, label="Indoor Temp ($^\circ$C)", color='crimson', linewidth=2.5)
            # Add Comfort Bounds
            ax4_temp.axhline(y=22.0, color='red', linestyle=':', linewidth=1.5, alpha=0.5, label="Max Temp")
            ax4_temp.axhline(y=18.0, color='blue', linestyle=':', linewidth=1.5, alpha=0.5, label="Min Temp")
        
        # Plot Water Tank (if it exists)
        if h0_thermal_storage is not None:
            ax4_temp.plot(time_axis_hours, h0_thermal_storage, label="Water Tank (kWh)", color='teal', linewidth=2, linestyle='--')
            
        ax4_temp.set_ylabel("Temperature ($^\circ$C) / Storage (kWh)", fontweight='bold')
        
        # Combine legends
        lines_4, labels_4 = ax4.get_legend_handles_labels()
        lines_4t, labels_4t = ax4_temp.get_legend_handles_labels()
        ax4.legend(lines_4 + lines_4t, labels_4 + labels_4t, bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)

    # SLIDE 5: Split Refrigeration Profiles
    has_fridge_power = "Fridge" in appliance_data
    has_freezer_power = "Freezer" in appliance_data
    
    if h0_fridge_temp is not None:
        ax5_top.plot(time_axis_hours, h0_fridge_temp, label="Fridge Temp ($^\circ$C)", color='cyan', linewidth=2)
        ax5_top.axhline(y=4.0, color='black', linestyle=':', linewidth=1.5, alpha=0.6, label="Target")
        ax5_top.axhline(y=6.0, color='red', linestyle='--', linewidth=1.5, alpha=0.6, label="Max Limit")
        ax5_top.set_ylabel("Fridge Temp ($^\circ$C)", fontweight='bold')
        ax5_top.set_title("Slide 5/6: House 0 Refrigeration Profiles", fontsize=14, fontweight='bold')
        ax5_top.grid(True, linestyle=':', alpha=0.6)
        
        if has_fridge_power:
            ax5_top_p = ax5_top.twinx()
            ax5_top_p.fill_between(time_axis_hours, appliance_data["Fridge"], color='lightskyblue', alpha=0.4, step='post', label="Compressor Power")
            ax5_top_p.set_ylabel("Power (kW)", color='lightskyblue', fontweight='bold')
            ax5_top_p.set_ylim(0, max(appliance_data.get("Fridge", [0]))*1.5 + 0.1)

            l5t, lab5t = ax5_top.get_legend_handles_labels()
            l5tp, lab5tp = ax5_top_p.get_legend_handles_labels()
            ax5_top.legend(l5t + l5tp, lab5t + lab5tp, bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)

    if h0_freezer_temp is not None:
        ax5_bottom.plot(time_axis_hours, h0_freezer_temp, label="Freezer Temp ($^\circ$C)", color='blue', linewidth=2)
        ax5_bottom.axhline(y=-20.0, color='black', linestyle=':', linewidth=1.5, alpha=0.6, label="Target")
        ax5_bottom.axhline(y=-18.0, color='red', linestyle='--', linewidth=1.5, alpha=0.6, label="Max Limit")
        ax5_bottom.set_ylabel("Freezer Temp ($^\circ$C)", fontweight='bold')
        ax5_bottom.set_xlabel("Time (Hours)", fontweight='bold')
        ax5_bottom.grid(True, linestyle=':', alpha=0.6)
        
        if has_freezer_power:
            ax5_bot_p = ax5_bottom.twinx()
            ax5_bot_p.fill_between(time_axis_hours, appliance_data["Freezer"], color='royalblue', alpha=0.4, step='post', label="Compressor Power")
            ax5_bot_p.set_ylabel("Power (kW)", color='royalblue', fontweight='bold')
            ax5_bot_p.set_ylim(0, max(appliance_data.get("Freezer", [0]))*1.5 + 0.1)

            l5b, lab5b = ax5_bottom.get_legend_handles_labels()
            l5bp, lab5bp = ax5_bot_p.get_legend_handles_labels()
            ax5_bottom.legend(l5b + l5bp, lab5b + lab5bp, bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)

    if all_houses_import is not None:
        bottom_import = np.zeros(steps)
        num_houses = len(all_houses_import)
        cmap = plt.get_cmap('turbo')
        house_colors = [cmap(i / num_houses) for i in range(num_houses)]        
        for i, house_import in enumerate(all_houses_import):
            ax6.bar(time_axis_hours, house_import, bottom=bottom_import, width=0.5, 
                    label=f"House {i}", align='edge', color=house_colors[i % len(house_colors)], alpha=0.85)
            bottom_import += np.array(house_import)
            
        ax6.axhline(y=transformer_limit, color='red', linestyle='--', linewidth=2, label=f"Transformer Limit ({transformer_limit} kW)")
        ax6.set_ylabel("Grid Import (kW)", fontweight='bold')
        ax6.set_xlabel("Time (Hours)", fontweight='bold')
        ax6.set_title("Slide 6/6: Community Grid Import Breakdown by House", fontsize=14, fontweight='bold')
        ax6.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)
        ax6.grid(True, axis='y', linestyle=':', alpha=0.6)

    if dumb_appliance_data is not None:
        bottom_arr_dumb = np.zeros(steps)
        
        if h0_dumb_heat_pump is not None and sum(h0_dumb_heat_pump) > 0:
            ax7.bar(time_axis_hours, h0_dumb_heat_pump, bottom=bottom_arr_dumb, width=0.5, label="Heat Pump (Dumb)", alpha=0.8, align="edge", color="purple")
            bottom_arr_dumb += np.array(h0_dumb_heat_pump)

        for i, (name, power_series) in enumerate(dumb_appliance_data.items()):
            if sum(power_series) > 0: 
                ax7.bar(time_axis_hours, power_series, bottom=bottom_arr_dumb, width=0.5, label=name, alpha=0.8, align='edge', color=colors[i % 20])
                bottom_arr_dumb += np.array(power_series)

        peak_power_dumb = max(bottom_arr_dumb) if len(bottom_arr_dumb) > 0 else 1.0
        ax7.set_ylim(0, peak_power_dumb * 1.2 if peak_power_dumb > 0 else 1.0) 
        ax7.set_ylabel("Power used (kW)", fontweight='bold')
        ax7.set_xlabel("Time (Hours)", fontweight='bold')
        ax7.set_title("Slide 7/7: House 0 UNCONTROLLED Appliance Schedule", fontsize=14, fontweight='bold')
        ax7.legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0.)
        ax7.grid(True, axis='y', linestyle=':', alpha=0.6)


    slide1_axes = [ax1_top, ax1_bottom, ax1_price]
    if h0_solar is not None and h0_soc is not None:
        slide1_axes.append(ax1_soc)
        
    slide4_axes = [ax4]
    if h0_heat_pump is not None:
        slide4_axes.append(ax4_temp)

    slide5_axes = []
    if h0_fridge_temp is not None:
        slide5_axes.append(ax5_top)
        if has_fridge_power: slide5_axes.append(ax5_top_p)
    if h0_freezer_temp is not None:
        slide5_axes.append(ax5_bottom)
        if has_freezer_power: slide5_axes.append(ax5_bot_p)
        
    slides = [slide1_axes, [ax2], [ax3], slide4_axes, slide5_axes, [ax6], [ax7]]
    
    class SlideController:
        ind = 0
        def next(self, event):
            self.ind = (self.ind + 1) % len(slides)
            self.update()

        def prev(self, event):
            self.ind = (self.ind - 1) % len(slides)
            self.update()
            
        def update(self):
            for i, group in enumerate(slides):
                for ax in group:
                    ax.set_visible(i == self.ind)
            fig.canvas.draw_idle()

    controller = SlideController()
    controller.update() 
    
    axprev = plt.axes([0.4, 0.05, 0.1, 0.075])
    axnext = plt.axes([0.51, 0.05, 0.1, 0.075])
    
    bprev = Button(axprev, '⬅ Prev')
    bnext = Button(axnext, 'Next ➡')
    
    bprev.on_clicked(controller.prev)
    bnext.on_clicked(controller.next)

    fig._bprev = bprev
    fig._bnext = bnext

    plt.show()