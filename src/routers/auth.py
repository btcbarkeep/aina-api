from fastapi import APIRouter, HTTPException, Depends, status, Form
from datetime import datetime, timedelta
from jose import JWTError, jwt
import os
from src.models import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

# Secret key (you can store this securely in Render environment variables)
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


# -----------------------------------------------------
#  Generate JWT token
# -----------------------------------------------------
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# -----------------------------------------------------
#  Login Endpoint
# -----------------------------------------------------
@router.post("/login", response_model=TokenResponse)
def login(login_data: LoginRequest):
    """
    Authenticate user and return a JWT access token.
    """

    # Replace this with your own authentication logic (database, etc.)
    # For now, we'll use a static demo account for testing:
    DEMO_USERNAME = os.getenv("DEMO_USER", "admin")
    DEMO_PASSWORD = os.getenv("DEMO_PASS", "password123")

    if login_data.username != DEMO_USERNAME or login_data.password != DEMO_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": login_data.username})
    return TokenResponse(access_token=access_token)
