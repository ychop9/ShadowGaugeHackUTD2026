# Import os module for directory and file path manipulations
import os
# Import glob module to search for files matching patterns
import glob
# Import FastAPI framework classes and HTTP exceptions
from fastapi import FastAPI, HTTPException, status, Depends
# Import CORS middleware for frontend connection support
from fastapi.middleware.cors import CORSMiddleware
# Import data loading and analytics functions from local module
from app.analytics import load_system_state, analyze_system_status
# Import optimizer logic from local optimizer module
from app.optimizer import find_lowest_cost_reroute
# Import authentication functions and user database from auth module
from app.auth import LoginRequest, verify_password, create_access_token, USERS_DB

# Function to search for network and telemetry files automatically
def find_dataset_files():
    # Search for any network.json file inside data directory subfolders
    network_files = glob.glob(os.path.join("data", "**", "network.json"), recursive=True)
    # Search for any telemetry.csv file inside data directory subfolders
    telemetry_files = glob.glob(os.path.join("data", "**", "telemetry.csv"), recursive=True)
    
    # Check if network file was found
    if not network_files:
        # Raise error if no network.json exists anywhere in data folder
        raise FileNotFoundError("Could not locate network.json anywhere inside data directory.")
    # Check if telemetry file was found
    if not telemetry_files:
        # Raise error if no telemetry.csv exists anywhere in data folder
        raise FileNotFoundError("Could not locate telemetry.csv anywhere inside data directory.")
        
    # Return first matching network path and first matching telemetry path
    return network_files[0], telemetry_files[0]

# Initialize FastAPI application instance
app = FastAPI(title="EOG Avon Oilfield Operator API")

# Add CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    # Allow request connections from any origin
    allow_origins=["*"],
    # Allow authorization credentials
    allow_credentials=True,
    # Allow all HTTP request methods
    allow_methods=["*"],
    # Allow all request headers
    allow_headers=["*"],
)

# Find active dataset file paths dynamically
NETWORK_PATH, TELEMETRY_PATH = find_dataset_files()

# Load initial system state objects on startup
TANKS_DATA, PUMPS_DATA, PIPELINES_DATA = load_system_state(NETWORK_PATH, TELEMETRY_PATH)

# Root endpoint for server status verification
@app.get("/")
def read_root():
    # Return simple status response
    return {"status": "online", "system": "EOG Operations Backend"}

# Login API endpoint for user authentication
@app.post("/api/v1/auth/login")
def login(credentials: LoginRequest):
    # Fetch user account record from database using username
    user = USERS_DB.get(credentials.username)
    # Check if user exists and if entered password matches hash
    if not user or not verify_password(credentials.password, user["hashed_password"]):
        # Raise 401 unauthorized exception for invalid credentials
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token carrying username subject claim
    access_token = create_access_token(data={"sub": user["username"]})
    # Return bearer token payload and user profile details to frontend
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }

# Endpoint returning active system alerts and warnings
@app.get("/api/v1/system/status")
def get_system_status():
    # Fetch current file locations dynamically
    net_p, tel_p = find_dataset_files()
    # Load updated state from dataset files
    tanks, pumps, _ = load_system_state(net_p, tel_p)
    # Perform status and alert calculations
    result = analyze_system_status(tanks, pumps)
    # Return computed alerts payload
    return result

# Endpoint returning tank overflow time predictions
@app.get("/api/v1/system/predictions")
def get_predictions():
    # Fetch current file locations dynamically
    net_p, tel_p = find_dataset_files()
    # Load updated state from dataset files
    tanks, pumps, _ = load_system_state(net_p, tel_p)
    # Perform analysis calculations
    result = analyze_system_status(tanks, pumps)
    # Return predictions list payload
    return {"predictions": result["time_predictions"]}

# Endpoint returning lowest cost pipeline rerouting action
@app.post("/api/v1/optimize/reroute")
def optimize_reroute(source_tank_id: str, volume_bbl: float):
    # Fetch current file locations dynamically
    net_p, tel_p = find_dataset_files()
    # Load updated graph state from dataset files
    tanks, _, pipelines = load_system_state(net_p, tel_p)
    # Run optimization routing calculation
    recommendation = find_lowest_cost_reroute(source_tank_id, volume_bbl, tanks, pipelines)
    # Return optimal path response payload
    return recommendation