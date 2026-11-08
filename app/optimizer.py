#This module finds the lowest-cost pipeline rerouting path when a pump fails or a tank gets close to capacity.
# Import heapq library for priority queue graph searches
import heapq
# Import typing helpers for signatures
from typing import Dict, List, Any
# Import Tank and Pipeline models
from app.models import Tank, Pipeline

# Function to compute lowest cost rerouting path
def find_lowest_cost_reroute(
    source_tank_id: str, 
    volume_to_divert: float, 
    tanks: Dict[str, Tank], 
    pipelines: List[Pipeline]
) -> Dict[str, Any]:
    # Initialize adjacency map graph representation
    graph = {}
    # Loop over every pipeline to build connection graph
    for pipe in pipelines:
        # Initialize list if source node is missing
        if pipe.source_id not in graph:
            graph[pipe.source_id] = []
        # Append pipeline record to source entry list
        graph[pipe.source_id].append(pipe)

    # Priority queue stores tuples of cost, current node ID, and path list
    queue = [(0.0, source_tank_id, [source_tank_id])]
    # Tracks minimum cost found to reach each node
    min_costs = {source_tank_id: 0.0}
    # Variable to hold output answer when found
    best_option = None

    # Loop while elements remain in priority queue
    while queue:
        # Pop path with lowest current cost
        current_cost, current_node, path = heapq.heappop(queue)

        # Skip check for origin node itself
        if current_node != source_tank_id:
            # Fetch receiver tank object from dictionary
            target_tank = tanks.get(current_node)
            # Check if target tank exists and has room for volume
            if target_tank and target_tank.headroom_bbl >= volume_to_divert:
                # Calculate total financial cost for whole volume
                total_action_cost = current_cost * volume_to_divert
                # Construct result output dict
                best_option = {
                    "destination_tank_id": current_node,
                    "destination_tank_name": target_tank.name,
                    "route_path": path,
                    "cost_per_bbl": round(current_cost, 2),
                    "total_action_cost": round(total_action_cost, 2),
                    "volume_diverted_bbl": volume_to_divert
                }
                # Stop search since lowest cost path is found
                break

        # Iterate over all outgoing connections from current node
        for pipe in graph.get(current_node, []):
            # Calculate updated total path cost per barrel
            new_cost = current_cost + pipe.cost_per_bbl
            # Check if path gives cheaper cost to reach target node
            if pipe.target_id not in min_costs or new_cost < min_costs[pipe.target_id]:
                # Store lower cost value into tracking dict
                min_costs[pipe.target_id] = new_cost
                # Push new route tuple into priority queue
                heapq.heappush(queue, (new_cost, pipe.target_id, path + [pipe.target_id]))

    # Return solution or fallback error dictionary
    return best_option or {"error": "No viable reroute path found with enough capacity."}