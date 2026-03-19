# data.py
from config import total_steps, steps_per_hour
import pandas as pd
import numpy as np

# Load the CREST CSV
crest_df = pd.read_csv('../../Crest Data/CrestData_5house_June_WD.csv', skiprows=1)
crest_df = crest_df.drop([0, 1]).reset_index(drop=True)

crest_df["Dwelling index"] = crest_df['Dwelling index'].astype(int)
crest_df["Space_Heat_W"] = crest_df['Heat output from primary heating system to space'].astype(float)
crest_df["Water_heat_W"] = crest_df['Heat output from primary heating system to hot water'].astype(float)

crest_df['Total_Thermal_Demand_kW'] = (crest_df['Space_Heat_W'] + crest_df["Water_heat_W"]) / 1000.0

house1_thermal = crest_df[crest_df['Dwelling index'] == 1].reset_index(drop=True)

heat_demand_per_house = []

# Match CREST time steps to 30 min intervals
for step in range(48):
    chunk = house1_thermal['Total_Thermal_Demand_kW'].iloc[step*30: (step+1)*30]

    heat_demand_per_house.append(chunk.mean())

# Run for 96 steps
heat_demand_per_house = heat_demand_per_house + heat_demand_per_house


# Auto-generated demand profiles for testing
electric_demand_per_house = [0.15] * total_steps # Low background load

heat_demand_per_house = [
    0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1,    
    0.2, 0.5, 1.2, 1.8, 2.0, 1.8, 1.0, 0.5,    
    0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3,    
    0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.4,    
    0.5, 0.8, 1.2, 1.5, 1.8, 2.0, 2.0, 1.8,    
    1.5, 1.0, 0.8, 0.5, 0.3, 0.2, 0.2, 0.1    
]                      

CO2_grid = [
    0.40, 0.40, 0.39, 0.38, 0.37, 0.36, 0.37, 0.38, 0.39, 0.40, 0.40, 0.39,
    0.38, 0.37, 0.36, 0.35, 0.34, 0.33, 0.32, 0.31, 0.30, 0.29, 0.29, 0.30,
    0.32, 0.35, 0.38, 0.40, 0.41, 0.40, 0.39, 0.35, 0.32, 0.30, 0.29, 0.29,
    0.30, 0.35, 0.38, 0.39, 0.38, 0.37, 0.37, 0.36, 0.36, 0.37, 0.38, 0.39
]



current_scenario = "SHOULDER"

if current_scenario == "SHOULDER":
    solar_profile = [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0127, 0.0127, 0.1112, 0.1112, 0.1195, 0.1195, 0.5835, 0.5835, 0.8647, 0.8647, 1.0000, 1.0000, 0.5625, 0.5625, 0.4716, 0.4716, 0.4751, 0.4751, 0.6392, 0.6392, 0.7705, 0.7705, 0.4472, 0.4472, 0.1578, 0.1578, 0.0365, 0.0365, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000]
    efficiency = 0.66
    price_grid_elec = [0.1470, 0.1472, 0.1449, 0.1500, 0.1554, 0.1478, 0.1500, 0.1464, 0.1581, 0.1500, 0.1512, 0.1533, 0.1665, 0.1680, 0.1680, 0.1974, 0.2171, 0.2058, 0.2218, 0.2150, 0.2050, 0.1995, 0.1869, 0.1869, 0.1781, 0.1728, 0.1686, 0.1575, 0.1512, 0.1506, 0.1491, 0.1491, 0.2961, 0.3045, 0.3354, 0.3570, 0.3715, 0.3698, 0.2100, 0.2100, 0.1856, 0.1701, 0.1743, 0.1617, 0.1611, 0.1329, 0.1915, 0.1640]
elif current_scenario == "SUMMER":
    solar_profile =  [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0167, 0.0167, 0.0658, 0.0658, 0.1160, 0.1160, 0.3040, 0.3040, 0.5673, 0.5673, 0.8341, 0.8341, 0.9231, 0.9231, 0.9937, 0.9937, 1.0000, 1.0000, 0.6904, 0.6904, 0.6776, 0.6776, 0.4335, 0.4335, 0.3961, 0.3961, 0.1939, 0.1939, 0.0915, 0.0915, 0.0150, 0.0150, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000]
    efficiency = 0.83
    price_grid_elec = 0.1814, 0.1730, 0.1653, 0.1691, 0.1765, 0.1546, 0.1528, 0.1478, 0.1449, 0.1411, 0.1443, 0.1378, 0.1348, 0.1372, 0.1035, 0.1176, 0.0630, 0.0974, 0.1092, 0.1071, 0.0995, 0.0874, 0.0798, 0.0420, 0.0357, 0.0315, 0.0508, 0.0403, 0.0437, 0.0451, 0.0624, 0.0693, 0.2680, 0.3024, 0.3192, 0.3314, 0.3339, 0.3343, 0.2054, 0.2184, 0.2318, 0.2310, 0.2222, 0.2266, 0.1949, 0.1902, 0.1949, 0.2222
else:
    solar_profile = [0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0274, 0.0274, 0.2161, 0.2161, 0.4421, 0.4421, 0.4633, 0.4633, 0.9341, 0.9341, 1.0000, 1.0000, 0.4991, 0.4991, 0.0414, 0.0414, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000]
    efficiency = 0.66
    price_grid_elec = [0.1991, 0.2102, 0.1991, 0.1991, 0.1991, 0.1989, 0.1986, 0.1991, 0.1991, 0.1991, 0.2310, 0.2039, 0.2100, 0.2352, 0.2709, 0.2785, 0.2919, 0.2940, 0.2835, 0.2856, 0.2722, 0.2685, 0.2541, 0.2436, 0.2520, 0.2587, 0.2553, 0.2493, 0.2310, 0.2557, 0.2459, 0.2932, 0.4259, 0.4935, 0.5151, 0.5292, 0.5040, 0.4730, 0.2982, 0.2478, 0.2665, 0.2341, 0.2453, 0.2042, 0.1991, 0.1917, 0.2142, 0.2077]

# Appliance Definitions
# T_S: Earliest start, T_F: Latest finish, P: Duration (hours)
appliances = [
    # Wet Appliances
    {'name': 'Dish washer',       'prob': 0.57, 'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 9,  'T_F': 17, 'Slots': 4,  'Power': 1.0}, 
    {'name': 'Washing machine',   'prob': 0.78, 'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 9,  'T_F': 12, 'Slots': 3,  'Power': 1.2}, 
    {'name': 'Spin dryer',        'prob': 0.71, 'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 13, 'T_F': 18, 'Slots': 2,  'Power': 2.0}, 

    # Cleaning & Cooking 
    {'name': 'Vacuum cleaner',    'prob': 0.28, 'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 9,  'T_F': 17, 'Slots': 1,  'Power': 1.2}, 
    {'name': 'Cooker hob',        'prob': 0.82, 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 17, 'T_F': 19, 'Slots': 1,  'Power': 2.0}, 
    {'name': 'Cooker oven',       'prob': 0.70, 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 17, 'T_F': 19, 'Slots': 1,  'Power': 3.0}, 
    {'name': 'Microwave',         'prob': 1.00, 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 8,  'T_F': 9,  'Slots': 1,  'Power': 1.2}, 

    # Lighting & Electronics 
    {'name': 'Interior lighting', 'prob': 1.00, 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 16, 'T_F': 24, 'Slots': 16, 'Power': 0.15}, 
    {'name': 'Laptop',            'prob': 1.00, 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 18, 'T_F': 24, 'Slots': 4,  'Power': 0.05}, 
    {'name': 'Desktop',           'prob': 0.50, 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 18, 'T_F': 24, 'Slots': 6,  'Power': 0.20}, 

    # Flexible EV Load
    {'name': 'Electric car',      'prob': 0.43, 'deferrable': True,  'interruptible': True,  'power_type': "flexible", 'T_S': 18, 'T_F': 8,  'Min_Power': 1.4, 'Max_Power': 7.0, 'Required_Energy': 13.5}
]

app_names = [a["name"] for a in appliances]