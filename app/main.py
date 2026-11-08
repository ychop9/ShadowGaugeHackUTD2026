# Import os module for file path operations
import os
# Import glob module to search directory paths recursively
import glob
# Import FastAPI class to build web server
from fastapi import FastAPI
# Import CORS middleware for frontend connection access
from fastapi.middleware.cors import CORSMiddleware
# Import processing functions from local analytics module
from app.analytics import load_system_state, analyze_system_status
# Import optimizer function from local optimizer module
from app.optimizer import find_lowest_cost_reroute

# Function to dynamically locate dataset files in nested folders
def find_dataset_files():
    # Find all network.json files in data directory
    network_files = glob.glob(os.path.join("data", "**", "network.json"), recursive=True)
    # Find all telemetry.csv files in data directory
    telemetry_files = glob.glob(os.path.join("data", "**", "telemetry.csv"), recursive=True)
    
    # Check if network JSON file exists
    if not network_files:
        # Raise error if network file is missing
        raise FileNotFoundError("Could not locate network.json in data folder.")
    # Check if telemetry CSV file exists
    if not telemetry_files:
        # Raise error if telemetry file is missing
        raise FileNotFoundError("Could not locate telemetry.csv in data folder.")
        
    # Return path of first network file and first telemetry file
    return network_files[0], telemetry_files[0]

# IMPORTANT: Define the app variable for ASGI server loading
app = FastAPI(title="EOG Avon Oilfield Operator API")

# Add CORS middleware to permit frontend API calls
app.add_middleware(
    CORSMiddleware,
    # Allow request origins from any frontend server
    allow_origins=["*"],
    # Allow credential authorization headers
    allow_credentials=True,
    # Allow all HTTP request methods
    allow_methods=["*"],
    # Allow all request header types
    allow_headers=["*"],
)

# Locate dataset paths dynamically on load
NETWORK_PATH, TELEMETRY_PATH = find_dataset_files()

# Root sanity check endpoint
@app.get("/")
def read_root():
    # Return server online status message
    return {"status": "online", "system": "EOG Operations Backend"}

# Endpoint to fetch system alerts and anomalies
@app.get("/api/v1/system/status")
def get_system_status():
    # Find dataset file locations
    net_p, tel_p = find_dataset_files()
    # Read latest state from parsed dataset files
    tanks, pumps, _ = load_system_state(net_p, tel_p)
    # Compute active alarms and overflow timeline analysis
    result = analyze_system_status(tanks, pumps)
    # Return computed analysis output
    return result

# Endpoint to fetch time to overflow predictions
@app.get("/api/v1/system/predictions")
def get_predictions():
    # Find dataset file locations
    net_p, tel_p = find_dataset_files()
    # Read state from dataset files
    tanks, pumps, _ = load_system_state(net_p, tel_p)
    # Perform status analysis calculations
    result = analyze_system_status(tanks, pumps)
    # Return time predictions array
    return {"predictions": result["time_predictions"]}

# Endpoint to optimize pipeline rerouting paths
@app.post("/api/v1/optimize/reroute")
def optimize_reroute(source_tank_id: str, volume_bbl: float):
    # Find dataset file locations
    net_p, tel_p = find_dataset_files()
    # Load tanks and pipelines graph representation
    tanks, _, pipelines = load_system_state(net_p, tel_p)
    # Run Dijkstra cost optimization algorithm
    recommendation = find_lowest_cost_reroute(source_tank_id, volume_bbl, tanks, pipelines)
    # Return path calculation output payload
    return recommendation