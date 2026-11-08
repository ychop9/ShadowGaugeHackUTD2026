# Import json module to read network configuration files
import json
# Import pandas to read telemetry sensor CSV files
import pandas as pd
# Import typing annotations for structure definitions
from typing import List, Dict, Any
# Import data models from local models file
from app.models import Tank, Pump, Pipeline

# Function to load system state from JSON and CSV files
def load_system_state(network_json_path: str, telemetry_csv_path: str):
    # Open and read the network configuration file
    with open(network_json_path, 'r') as f:
        # Parse JSON payload into python dictionary
        network = json.load(f)

    # Read telemetry dataset into pandas dataframe
    telemetry_df = pd.read_csv(telemetry_csv_path)

    # Empty dictionary to store parsed Tank objects
    tanks = {}
    # Loop across all nodes defined in network structure
    for node in network.get('nodes', []):
        # Normalize node type string to lowercase for matching
        node_type = str(node.get('type', '')).lower()
        # Accept node if type is tank or if node contains capacity keys
        if node_type == 'tank' or 'capacity' in str(node).lower() or 'max_capacity_bbl' in node:
            # Extract node identifier string
            t_id = str(node['id'])
            # Filter telemetry dataframe matching this node ID
            t_data = telemetry_df[telemetry_df['id'].astype(str) == t_id]
            
            # Extract row if telemetry record exists
            row = t_data.iloc[0] if not t_data.empty else {}

            # Extract current volume or default to 0
            curr_vol = float(row.get('current_volume_bbl', row.get('volume', 0.0)))
            # Extract max capacity from node or telemetry
            max_cap = float(node.get('max_capacity_bbl', node.get('capacity', row.get('max_capacity_bbl', 1000.0))))
            # Extract inflow rate or default to 0
            in_rate = float(row.get('inflow_rate_bbl_hr', row.get('inflow', 0.0)))
            # Extract outflow rate or default to 0
            out_rate = float(row.get('outflow_rate_bbl_hr', row.get('outflow', 0.0)))

            # Build and store Tank object in dictionary
            tanks[t_id] = Tank(
                id=t_id,
                name=str(node.get('name', t_id)),
                current_volume_bbl=curr_vol,
                max_capacity_bbl=max_cap,
                inflow_rate_bbl_hr=in_rate,
                outflow_rate_bbl_hr=out_rate
            )

    # Empty dictionary to store parsed Pump objects
    pumps = {}
    # Empty list to store parsed Pipeline objects
    pipelines = []
    
    # Loop across all edges defined in network structure
    for edge in network.get('edges', []):
        # Extract edge identifier string
        e_id = str(edge['id'])
        # Filter telemetry dataframe matching this edge ID
        e_data = telemetry_df[telemetry_df['id'].astype(str) == e_id]
        
        # Determine status string from telemetry or network edge
        if not e_data.empty and 'status' in e_data.columns:
            status = str(e_data.iloc[0]['status']).upper()
        else:
            status = str(edge.get('status', 'OPERATIONAL')).upper()

        # Build and store Pump object in dictionary
        pumps[e_id] = Pump(
            id=e_id,
            source_tank_id=str(edge.get('source', edge.get('from', ''))),
            target_tank_id=str(edge.get('target', edge.get('to', ''))),
            flow_capacity_bbl_hr=float(edge.get('capacity_bbl_hr', edge.get('capacity', 100.0))),
            status=status,
            power_cost_per_hr=float(edge.get('power_cost_per_hr', edge.get('power_cost', 5.0))),
            maintenance_cost=float(edge.get('maintenance_cost', 500.0))
        )

        # Build and store Pipeline object in list
        pipelines.append(Pipeline(
            id=e_id,
            source_id=str(edge.get('source', edge.get('from', ''))),
            target_id=str(edge.get('target', edge.get('to', ''))),
            capacity_bbl_hr=float(edge.get('capacity_bbl_hr', edge.get('capacity', 100.0))),
            cost_per_bbl=float(edge.get('cost_per_bbl', edge.get('cost', 0.5)))
        ))

    # Return parsed tanks, pumps, and pipelines
    return tanks, pumps, pipelines

# Function to run anomaly analysis and overflow predictions
def analyze_system_status(tanks: Dict[str, Tank], pumps: Dict[str, Pump]) -> Dict[str, Any]:
    # Empty list to store generated system alerts
    alerts = []
    # Empty list to store tank predictions
    predictions = []

    # Loop over pumps to check for non-operational status
    for pump_id, pump in pumps.items():
        # Check if pump status string indicates failure or degradation
        if pump.status in ["FAILED", "DEGRADED", "OFFLINE", "ERROR"]:
            # Append pump error record to alerts list
            alerts.append({
                "severity": "CRITICAL" if pump.status in ["FAILED", "OFFLINE"] else "WARNING",
                "component_type": "PUMP",
                "component_id": pump_id,
                "message": f"Pump {pump_id} is currently {pump.status}."
            })

    # Loop over tanks to calculate fill percentages and predictions
    for tank_id, tank in tanks.items():
        # Calculate net flow rate per hour
        net_flow = tank.net_flow_rate
        # Calculate current percentage of capacity filled
        fill_pct = (tank.current_volume_bbl / tank.max_capacity_bbl) * 100 if tank.max_capacity_bbl > 0 else 0.0

        # Compute time to overflow if net flow is positive
        if net_flow > 0:
            # Calculate remaining hours before tank overflows
            time_to_overflow_hrs = tank.headroom_bbl / net_flow
        else:
            # Set to 999.0 hours if tank level is stable or decreasing
            time_to_overflow_hrs = 999.0

        # Determine if tank state requires critical flag
        is_critical = time_to_overflow_hrs < 4.0 or fill_pct >= 90.0

        # Append prediction metrics to predictions list
        predictions.append({
            "tank_id": tank_id,
            "tank_name": tank.name,
            "current_fill_pct": round(fill_pct, 2),
            "net_flow_rate_bbl_hr": round(net_flow, 2),
            "time_to_overflow_hrs": round(time_to_overflow_hrs, 2) if time_to_overflow_hrs != 999.0 else "STABLE",
            "is_critical": is_critical
        })

        # Add tank alert if fill is above 90 percent or overflow is under 4 hours
        if is_critical:
            # Append high severity alert record to alerts list
            alerts.append({
                "severity": "HIGH",
                "component_type": "TANK",
                "component_id": tank_id,
                "message": f"Tank {tank.name} at {round(fill_pct, 1)}% capacity."
            })

    # Return summary dict containing alerts and predictions
    return {
        "active_alerts": alerts,
        "time_predictions": predictions
    }