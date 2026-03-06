# community_controller.py
from config import *
import concurrent.futures


class CommunityController:
    def __init__(self, transformer_limit=num_homes):
        self.limit = transformer_limit
    
    def negotiate_schedules(self, house_agents, current_step):
        # Iterative pricing loop
        # Start with zero penalties

        current_penalties = [0.0] * 48
        agreed = False
        iteration = 0
        max_iterations = 10

        final_approved_data = []

        while not agreed and iteration < max_iterations:
            iteration += 1
            proposed_profiles = []
            house_data_packages = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(house_agents)) as executor:
                # executor.map runs them all at once, but returns the 'data' results 
                # in the exact same order as the 'house_agents' list
                results = list(executor.map(lambda h: h.generate_proposed_schedule(current_step, current_penalties), house_agents))

            for house, data in zip(house_agents, results):
                if data["status"] == "Optimal":
                    proposed_profiles.append(data["proposed_import_profile"])
                    house_data_packages.append(data)
                else:
                    # If house is infeasible, take whatever breaches necessary
                    proposed_profiles.append(data["proposed_import_profile"])
                    house_data_packages.append(data)
                    
            total_community_demand = [sum(x) for x in zip(*proposed_profiles)]

            breach_detected = False
            for k in range(48):
                if total_community_demand[k] > self.limit:
                    breach_detected = True

                    breach_amount = total_community_demand[k] - self.limit
                    current_penalties[k] += (breach_amount * 0.2)
            final_approved_data = house_data_packages

            if not breach_detected:
                agreed = True
                final_approved_data = house_data_packages
                print(f"    [Step {current_step}] Schedules Approved in {iteration} iterations. Peak Demand: {max(total_community_demand):.2f} kW")
        
        if not agreed:        
            worst_k = total_community_demand.index(max(total_community_demand))
            worst_demand = total_community_demand[worst_k]

            print(f"    [Step {current_step}] WARNING: Max iterations reached. Accepting schedule with breaches.")
            print(f"      -> Worst breach occurs looking ahead {worst_k} steps.")
            print(f"      -> Demand: {worst_demand:.2f} kW (Limit: {self.limit} kW)")
            
            # Print exactly what each house is doing at that specific problem step
            house_loads = [profiles[worst_k] for profiles in proposed_profiles]
            max_power = I_max/num_homes
            breakdown = " | ".join([f"H{i}: {load:.2f}kW" for i, load in enumerate(house_loads) if load > max_power])            
            print(f"      -> Culprits: {breakdown}")

        return final_approved_data, total_community_demand[0]