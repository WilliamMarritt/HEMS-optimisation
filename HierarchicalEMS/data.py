# data.py
from config import total_steps, steps_per_hour

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

price_grid_elec = [
    0.07, 0.07, 0.07, 0.07, 0.07, 0.07, 0.07, 0.07, 0.08, 0.09, 0.10, 0.12,
    0.25, 0.30, 0.35, 0.37, 0.37, 0.35, 0.30, 0.25,
    0.20, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.18, 0.20, 0.22, 0.25, 0.28,
    0.40, 0.45, 0.50, 0.50, 0.45, 0.40,    
    0.30, 0.25, 0.20, 0.15, 0.12, 0.10, 0.09, 0.08, 0.07, 0.07
]

solar_profile = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    0.05, 0.10, 0.20, 0.35, 0.50, 0.65, 0.75, 0.85, 0.90, 0.95, 0.98, 1.00,
    1.00, 0.98, 0.95, 0.90, 0.85, 0.75, 0.65, 0.50, 0.35, 0.20, 0.10, 0.05,
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
]

# Appliance Definitions
# T_S: Earliest start, T_F: Latest finish, P: Duration (hours)
appliances = [
    {'name': 'Dish washer',       'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 9,  'T_F': 17, 'P': 2,   'Slots': 4,  'Power': 1.0},
    {'name': 'Washing machine',   'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 9,  'T_F': 12, 'P': 1.5, 'Slots': 3,  'Power': 1.2},
    {'name': 'Spin dryer',        'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 13, 'T_F': 18, 'P': 1,   'Slots': 2,  'Power': 2.5},
    {'name': 'Vacuum cleaner',    'deferrable': True,  'interruptible': False, 'power_type': "constant", 'T_S': 9,  'T_F': 17, 'P': 0.5, 'Slots': 1,  'Power': 1.2},
    {'name': 'Cooker hob',        'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 8,  'T_F': 9,  'P': 0.5, 'Slots': 1,  'Power': 3.0},
    {'name': 'Cooker oven',       'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 18, 'T_F': 19, 'P': 0.5, 'Slots': 1,  'Power': 5.0},
    {'name': 'Microwave',         'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 8,  'T_F': 9,  'P': 0.5, 'Slots': 1,  'Power': 1.7},
    {'name': 'Interior lighting', 'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 18, 'T_F': 24, 'P': 6,   'Slots': 12, 'Power': 0.84},
    {'name': 'Laptop',            'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 18, 'T_F': 24, 'P': 2,   'Slots': 4,  'Power': 0.1},
    {'name': 'Desktop',           'deferrable': False, 'interruptible': False, 'power_type': "constant", 'T_S': 18, 'T_F': 24, 'P': 3,   'Slots': 6,  'Power': 0.3},
    {'name': 'Electric car',      'deferrable': True,  'interruptible': True,  'power_type': "flexible", 'T_S': 18, 'T_F': 8, 'P': 3,    'Slots': 6, 'Min_Power': 1.4, 'Max_Power': 7.0, 'Required_Energy': 10.5}
]

# Calculate Slots (duration in steps) and extract names
appliances = [{**item, 'Slots': item['P'] * steps_per_hour} for item in appliances]
app_names = [a["name"] for a in appliances]