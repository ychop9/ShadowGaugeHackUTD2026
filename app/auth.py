# Import hashlib for built-in secure password hashing
import hashlib
# Import datetime module to handle token expiration timestamps
from datetime import datetime, timedelta, timezone
# Import typing helpers for optional string fields
from typing import Optional
# Import jose module to generate and encode JSON Web Tokens
from jose import jwt
# Import Pydantic BaseModel for JSON request body validation
from pydantic import BaseModel

# Secret key string used to sign JWT security tokens
SECRET_KEY = "avon_super_secret_eog_hackathon_key_change_in_production"
# Specify hashing algorithm used for signing tokens
ALGORITHM = "HS256"
# Set token expiration duration to 60 minutes
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Function to generate SHA-256 hash string from raw password
def get_password_hash(password: str) -> str:
    # Encode password to bytes and calculate hex digest
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

# Function to verify plain password against hashed password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Hash entered plain password and compare against stored hash
    return get_password_hash(plain_password) == hashed_password

# Hardcoded user database using native SHA-256 hash
USERS_DB = {
    # Demo admin account credentials record
    "admin": {
        "username": "admin",
        # Hash for clear text password: "password123"
        "hashed_password": get_password_hash("password123"),
        "role": "Field Operator",
        "full_name": "Avon Operator"
    }
}

# Pydantic data model for login request payload
class LoginRequest(BaseModel):
    # Username string field sent by login screen
    username: str
    # Password string field sent by login screen
    password: str

# Function to create signed JWT access token string
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    # Copy input data dictionary into local variable
    to_encode = data.copy()
    # Check if custom expiration delta was provided
    if expires_delta:
        # Compute expire timestamp from current time plus delta
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default expire timestamp to 60 minutes from now
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add expiration timestamp key to token data dictionary
    to_encode.update({"exp": expire})
    # Encode token dictionary into JWT string using secret key
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    # Return finished JWT token string
    return encoded_jwt