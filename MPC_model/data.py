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

# Appliance Definitions
# T_S: Earliest start, T_F: Latest finish, P: Duration (hours)
appliances = [
    {'name': 'Dish washer', 'T_S': 9, 'T_F': 17, 'P': 2, 'Power': 1.0},
    {'name': 'Washing machine', 'T_S': 9, 'T_F': 12, 'P': 1.5, 'Power': 1.2},
    {'name': 'Spin dryer', 'T_S': 13, 'T_F': 18, 'P': 1, 'Power': 2.5},
    {'name': 'Cooker hob', 'T_S': 8, 'T_F': 9, 'P': 0.5, 'Power': 3},
    {'name': 'Cooker oven', 'T_S': 18, 'T_F': 19, 'P': 0.5, 'Power': 5},
    {'name': 'Microwave', 'T_S': 8, 'T_F': 9, 'P': 0.5, 'Power': 1.7},
    {'name': 'Interior lighting', 'T_S': 18, 'T_F': 24, 'P': 6, 'Power': 0.84},
    {'name': 'Laptop', 'T_S': 18, 'T_F': 24, 'P': 2, 'Power': 0.1},
    {'name': 'Desktop', 'T_S': 18, 'T_F': 24, 'P': 3, 'Power': 0.3},
    {'name': 'Vacuum cleaner', 'T_S': 9, 'T_F': 17, 'P': 0.5, 'Power': 1.2},
    {'name': 'Fridge', 'T_S': 0, 'T_F': 24, 'P': 24, 'Power': 0.3},
    {'name': 'Electric car', 'T_S': 18, 'T_F': 8, 'P': 3, 'Power': 3.5}
]

# Calculate Slots (duration in steps) and extract names
appliances = [{**item, 'Slots': item['P'] * steps_per_hour} for item in appliances]
app_names = [a["name"] for a in appliances]