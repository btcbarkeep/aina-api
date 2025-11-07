from fastapi import APIRouter, HTTPException, status
from datetime import datetime, timedelta
from jose import jwt
from pydantic import BaseModel
import os

router = APIRouter(prefix="/auth", tags=["Auth"])

# -----------------------------------------------------
#  CONFIG
# -----------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET", "supersecretkey")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours

# -----------------------------------------------------
#  MODELS
# -----------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# -----------------------------------------------------
#  TOKEN CREATION
# -----------------------------------------------------
def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# -----------------------------------------------------
#  LOGIN
# -----------------------------------------------------
@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest):
    DEMO_USER = os.getenv("DEMO_USER", "admin")
    DEMO_PASS = os.getenv("DEMO_PASS", "password123")

    if credentials.username != DEMO_USER or credentials.password != DEMO_PASS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = create_access_token({"sub": credentials.username})
    return TokenResponse(access_token=token)
