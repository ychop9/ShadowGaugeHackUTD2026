#This file defines the basic structures for Tanks, Pumps, and Pipelines.
# Import dataclass to create simple data containers
from dataclasses import dataclass
# Import List to specify list data types in Python
from typing import List

# Define the container class for tank data
@dataclass
class Tank:
    # Stores the unique identifier for the tank
    id: str
    # Stores the human-readable name of the tank
    name: str
    # Stores current fluid volume in barrels
    current_volume_bbl: float
    # Stores maximum fluid volume capacity in barrels
    max_capacity_bbl: float
    # Stores incoming fluid rate in barrels per hour
    inflow_rate_bbl_hr: float
    # Stores outgoing fluid rate in barrels per hour
    outflow_rate_bbl_hr: float

    # Property decorator lets us call this like an attribute
    @property
    # Calculates net hourly fluid change rate
    def net_flow_rate(self) -> float:
        # Net flow is inflow minus outflow
        return self.inflow_rate_bbl_hr - self.outflow_rate_bbl_hr

    # Property decorator for available remaining capacity
    @property
    # Calculates remaining space left in the tank
    def headroom_bbl(self) -> float:
        # Headroom is max capacity minus current volume
        return self.max_capacity_bbl - self.current_volume_bbl

# Define the container class for pump data
@dataclass
class Pump:
    # Stores the unique identifier for the pump
    id: str
    # Stores the source tank ID where pump receives fluid
    source_tank_id: str
    # Stores the target tank ID where pump sends fluid
    target_tank_id: str
    # Stores maximum flow rate capacity in barrels per hour
    flow_capacity_bbl_hr: float
    # Stores current status like OPERATIONAL or FAILED
    status: str
    # Stores cost to run the pump per hour
    power_cost_per_hr: float
    # Stores estimated fix cost if pump fails
    maintenance_cost: float

# Define the container class for pipeline data
@dataclass
class Pipeline:
    # Stores the unique identifier for the pipeline segment
    id: str
    # Stores the starting node or tank ID
    source_id: str
    # Stores the ending node or tank ID
    target_id: str
    # Stores maximum pipeline volume capacity per hour
    capacity_bbl_hr: float
    # Stores fluid transfer cost per barrel
    cost_per_bbl: float