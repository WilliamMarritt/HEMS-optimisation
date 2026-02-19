# Cooperative HEMS Optimization Project

This project implements a Mixed Integer Linear Programming (MILP) model for optimizing energy schedules across 30 homes in a microgrid. It minimizes cost and CO2 emissions using a Receding Horizon Control (MPC) framework.


## Structure
- `main.py`: Entry point for simulation.
- `config.py`: System parameters (Battery capacity, Prices, CHP specs).
- `optimization.py`: PuLP model definitions.
- `visualization.py`: Matplotlib plotting functions.
- `data.py`: Demand profiles and weather data.

## Installation
1. Install dependencies: `pip install -r requirements.txt`
2. Run simulation: `python main.py`

## References

This project is based on the mathematical model and system parameters presented in:

> **Zhang, D., Evangelisti, S., Lettieri, P., & Papageorgiou, L. G. (2016).** > *Economic and environmental scheduling of smart homes with microgrid: DER operation and electrical tasks.* > Energy Conversion and Management, 110, 113-124. [doi.org/10.1016/j.enconman.2015.11.050](https://doi.org/10.1016/j.enconman.2015.11.050)
