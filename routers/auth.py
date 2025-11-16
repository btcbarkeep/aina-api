# routers/auth.py

from fastapi import APIRouter, HTTPException, Depends
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
# Router Setup
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
# Helper: Create JWT Access Token
# -----------------------------------------------------
def _create_access_token(email: str, role: str, user_id: str):
    expiration = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": email,
        "role": role,
        "user_id": user_id,
        "exp": expiration,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# -----------------------------------------------------
# LOGIN
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

    hashed_pw = user.get("hashed_password")
    if not hashed_pw:
        raise HTTPException(
            401,
            "Password not set — complete setup link first.",
        )

    if not verify_password(payload.password, hashed_pw):
        raise HTTPException(401, "Invalid email or password")

    # Issue token with user's real role from DB
    token = _create_access_token(
        email=user["email"],
        role=user.get("role", "hoa"),
        user_id=user["id"],
    )

    return TokenResponse(access_token=token)


# -----------------------------------------------------
# DEV-ONLY ADMIN LOGIN (safe for development only)
# -----------------------------------------------------
@router.post("/dev-login", summary="Temporary admin login (development only)")
def dev_login():
    if settings.ENV == "production":
        raise HTTPException(403, "dev-login disabled in production")

    token = jwt.encode(
        {
            "sub": "dev-admin@ainaprotocol.com",
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
# CURRENT USER
# -----------------------------------------------------
@router.get("/me", response_model=CurrentUser, summary="Current authenticated user")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user


# -----------------------------------------------------
# SET PASSWORD AFTER ADMIN CREATED ACCOUNT
# -----------------------------------------------------
@router.post("/set-password", summary="Finish account setup by creating password")
def set_password(payload: SetPasswordRequest):
    client = get_supabase_client()

    # Decode token safely
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
        raise HTTPException(400, "Invalid or expired setup token")

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

    # Validate reset token & expiration
    stored_token = user.get("reset_token")
    if not stored_token or stored_token != payload.token:
        raise HTTPException(400, "Invalid reset token")

    expires = user.get("reset_token_expires")
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.utcnow():
                raise HTTPException(400, "Reset token expired")
        except Exception:
            raise HTTPException(400, "Invalid expiration format")

    # Store hashed password
    hashed_pw = hash_password(payload.password)

    client.table("users").update(
        {
            "hashed_password": hashed_pw,
            "reset_token": None,
            "reset_token_expires": None,
        }
    ).eq("email", email).execute()

    return {
        "status": "success",
        "message": "Password created successfully!",
    }
