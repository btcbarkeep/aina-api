from datetime import timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError
from pydantic import BaseModel
import os

# Secret key for JWT (use Render env var in production)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

router = APIRouter(prefix="/auth", tags=["Auth"])

# ------------------------
# Models
# ------------------------
class Token(BaseModel):
    access_token: str
    token_type: str


# ------------------------
# Helpers
# ------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ------------------------
# Routes
# ------------------------
@router.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 login route used by Swagger UI"""
    DEMO_USER = os.getenv("DEMO_USER", "admin")
    DEMO_PASS = os.getenv("DEMO_PASS", "password123")

    if form_data.username != DEMO_USER or form_data.password != DEMO_PASS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token({"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
