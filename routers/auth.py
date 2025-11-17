# routers/auth.py

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import jwt
from core.config import settings
from core.supabase_client import get_supabase_client
from dependencies.auth import get_current_user, CurrentUser


# ============================================================
# Router Setup
# ============================================================
router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


# ============================================================
# Pydantic Models
# ============================================================
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PasswordSetupRequest(BaseModel):
    email: str


# ============================================================
# LOGIN (Supabase Auth)
# ============================================================
@router.post("/login", response_model=TokenResponse, summary="Authenticate user")
def login(payload: LoginRequest):
    """
    Authenticate user using Supabase Auth.
    """

    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    # Try to sign in
    try:
        response = client.auth.sign_in_with_password(
            {
                "email": payload.email,
                "password": payload.password,
            }
        )
    except Exception as e:
        raise HTTPException(401, f"Invalid email or password: {e}")

    if not response.session or not response.session.access_token:
        raise HTTPException(401, "Invalid email or password")

    return TokenResponse(access_token=response.session.access_token)


# ============================================================
# DEV-ONLY LOGIN (SAFEGUARDED)
# ============================================================
@router.post("/dev-login", summary="Temporary admin login (development only)")
def dev_login():
    if settings.ENV == "production":
        raise HTTPException(403, "dev-login disabled in production")

    token = jwt.encode(
        {
            "sub": "dev-admin@ainaprotocol.com",
            "role": "super_admin",
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


# ============================================================
# CURRENT USER ENDPOINT
# ============================================================
@router.get("/me", response_model=CurrentUser, summary="Current authenticated user")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user


# ============================================================
# INITIATE PASSWORD SETUP / RESET
# (Supabase sends magic link to complete password setup/reset)
# ============================================================
@router.post("/initiate-password-setup", summary="Send password setup/recovery email")
def initiate_password_setup(payload: PasswordSetupRequest):
    """
    Sends a Supabase password recovery email. This covers:
    - new account password setup
    - forgotten password reset
    """

    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

    try:
        client.auth.reset_password_for_email(payload.email)
        return {
            "success": True,
            "message": "Password setup/reset email sent.",
        }
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")
