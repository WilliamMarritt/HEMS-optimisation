# Contains constants and system parameters

# config.py

# Simulation Time Settings
delta = 0.5
steps_per_hour = int(1 / delta)
total_steps = 24 * steps_per_hour
time_steps = range(total_steps)  # 48 half-hourly time steps for a 24-hour period

# Physical System Constants (parameters taken from the paper)
alpha = 1.2     # CHP Heat-to_Power ratio   

C_CHP = 20.0    # CHP generator capacity
C_B = 120       # Boiler capacity
C_E = 10.0      # Electrical storage capacity
C_TH = 20.0     # Thermal storage capacity

D_E = 10        # Maximum electrical discharge rate
G_E = 10        # Maximum electrical charge rate
S_init = 0

nu_E = 0.95     # Electrical efficiency of ESS
nu_TH = .098    # Thermal efficiency of ESS

xi_CHP = 0.5445
xi_Boiler = 0.3109

# Cost Parameters
wear_cost_elec = 0.005
wear_cost_therm = 0.001
price_gas = 0.08

# Community Settings
num_homes = 30
homes = range(num_homes)