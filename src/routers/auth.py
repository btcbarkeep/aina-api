from datetime import datetime, timedelta
from typing import Optional
import os
from fastapi import APIRouter, Depends, Form, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

# -----------------------------------------------------
#  JWT CONFIGURATION
# -----------------------------------------------------
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecret")  # ⚠️ Replace this in Render env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours

security = HTTPBearer()

# -----------------------------------------------------
#  TOKEN CREATION
# -----------------------------------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Creates a JWT access token with an expiration time.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# -----------------------------------------------------
#  VERIFY CURRENT USER
# -----------------------------------------------------
def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    Decodes and verifies JWT tokens for protected routes.
    Returns a dict with 'username' and 'role'.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")

        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return {"username": username, "role": role}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# -----------------------------------------------------
#  AUTH ROUTES
# -----------------------------------------------------
router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    """
    Demo login route.
    Later

