# Contains constants and system parameters

# config.py
verbose = True

def vprint(*args, **kwargs):
    if verbose:
        print(*args, **kwargs)

# Community Settings
num_homes = 5
homes = range(num_homes)
I_max = 7.5

# Simulation Time Settings
delta = 0.5
steps_per_hour = int(1 / delta)
total_steps = 24 * steps_per_hour
time_steps = range(total_steps)  # 48 half-hourly time steps for a 24-hour period

# Physical System Constants (parameters taken from the paper)

C_E = 11      # Electrical storage capacity
C_TH = 5.0     # Thermal storage capacity
COP = 3.0       # Heat Pump coefficient of performance (possibly optimistic/ sunny day)

D_E = 10        # Maximum electrical discharge rate
G_E = 10        # Maximum electrical charge rate
S_init = 0.6*C_E

nu_E = 0.95     # Electrical efficiency of ESS
nu_TH = .098    # Thermal efficiency of ESS

PV_capacity = 3.69

# Cost Parameters
wear_cost_elec = 0.005
wear_cost_therm = 0.001

# Thermal Parameters
UA = 0.085      # Heat transfer coefficient
C_in = 2.5
T_target = 20.0
T_min = 18.0
T_max = 22.0


