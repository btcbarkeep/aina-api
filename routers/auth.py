# routers/auth.py

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

from core.config import settings
from core.supabase_client import get_supabase_client
from core.auth_helpers import (
    hash_password,
    verify_password,
)

from dependencies.auth import get_current_user, CurrentUser


# -----------------------------------------------------
# Router
# -----------------------------------------------------
router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -----------------------------------------------------
# Pydantic Models
# -----------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetPasswordRequest(BaseModel):
    token: str
    password: str


# -----------------------------------------------------
# JWT Utility
# -----------------------------------------------------
def _create_access_token(email: str, role: str, user_id: str):
    """Create a signed JWT access token."""
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
# LOGIN (Supabase)
# -----------------------------------------------------
@router.post("/login", response_model=TokenResponse, summary="Authenticate user")
def login(payload: LoginRequest):
    client = get_supabase_client()

    # Fetch user
    try:
        result = (
            client.table("users")
            .select("*")
            .eq("email", payload.email)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase query failed: {e}")

    user = result.data
    if not user:
        raise HTTPException(401, "Invalid email or password")

    # Validate password
    hashed_pw = user.get("hashed_password")
    if not hashed_pw or not verify_password(payload.password, hashed_pw):
        raise HTTPException(401, "Invalid email or password")

    # Generate token
    token = _create_access_token(
        email=user["email"],
        role=user.get("role", "hoa"),
        user_id=user["id"],
    )

    return TokenResponse(access_token=token)


# -----------------------------------------------------
# DEV ADMIN LOGIN (TEMPORARY)
# -----------------------------------------------------
@router.post("/dev-login", summary="Temporary admin login (development only)")
def dev_login():
    if settings.ENV == "production":
        raise HTTPException(403, "dev-login disabled in production")

    token = jwt.encode(
        {
            "sub": "bootstrap-admin",
            "role": "admin",
            "user_id": "bootstrap",
            "exp": datetime.utcnow() + timedelta(hours=12),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


# -----------------------------------------------------
# WHO AM I? (validate token)
# -----------------------------------------------------
@router.get("/me", response_model=CurrentUser, summary="Current authenticated user")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user


# -----------------------------------------------------
# COMPLETE ACCOUNT SETUP (set password)
# -----------------------------------------------------
@router.post("/set-password", summary="Finish account setup by creating password")
def set_password(payload: SetPasswordRequest):
    client = get_supabase_client()

    # Decode the token
    try:
        decoded = jwt.decode(
            payload.token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        email = decoded.get("sub")
        if not email:
            raise Exception("No email in token")
    except JWTError:
        raise HTTPException(400, "Invalid or expired token")

    # Fetch user
    result = (
        client.table("users")
        .select("*")
        .eq("email", email)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "User not found")

    user = result.data

    # Validate token matches DB
    if not user.get("reset_token") or user["reset_token"] != payload.token:
        raise HTTPException(400, "Invalid password reset token")

    # Check expiration
    expires = user.get("reset_token_expires")
    if expires and datetime.fromisoformat(expires) < datetime.utcnow():
        raise HTTPException(400, "Reset token expired")

    # Update password
    hashed_pw = hash_password(payload.password)

    client.table("users").update({
        "hashed_password": hashed_pw,
        "reset_token": None,
        "reset_token_expires": None,
    }).eq("email", email).execute()

    return {
        "status": "success",
        "message": "Password created successfully!",
    }
