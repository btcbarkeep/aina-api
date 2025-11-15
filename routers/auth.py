# routers/auth.py

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

from core.config import settings
from core.supabase_client import get_supabase_client
from dependencies.auth import CurrentUser

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
    responses={401: {"description": "Unauthorized"}},
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -----------------------------------------------------
# Request/Response Models
# -----------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# -----------------------------------------------------
# JWT Utility
# -----------------------------------------------------
def _create_access_token(email: str, role: str, user_id: str):
    expires = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": email,
        "role": role,
        "user_id": user_id,
        "exp": expires,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# -----------------------------------------------------
# LOGIN (Supabase-native)
# -----------------------------------------------------
@router.post("/login", response_model=TokenResponse, summary="Authenticate user")
def login(payload: LoginRequest):
    client = get_supabase_client()

    # 1. Fetch user by email
    result = (
        client.table("users")
        .select("*")
        .eq("email", payload.email)
        .maybe_single()
        .execute()
    )

    if result.error or not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user = result.data

    # 2. Validate password (bcrypt)
    hashed_pw = user.get("hashed_password")

    if not hashed_pw or not pwd_context.verify(payload.password, hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # 3. Generate JWT
    token = _create_access_token(
        email=user["email"],
        role=user.get("role", "user"),
        user_id=user["id"],
    )

    return TokenResponse(access_token=token)


# -----------------------------------------------------
# VALIDATE TOKEN → returns CurrentUser
# -----------------------------------------------------
@router.get("/me", response_model=CurrentUser)
def read_me(current_user: CurrentUser = Depends(lambda: None)):
    return current_user
