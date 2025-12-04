from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from core.supabase_client import get_supabase_client
from core.rate_limiter import require_rate_limit, get_rate_limit_identifier
from dependencies.auth import get_current_user, CurrentUser


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


# ============================================================
# MODELS
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
# LOGIN (SUPABASE AUTH)
# ============================================================
@router.post("/login", response_model=TokenResponse, summary="Authenticate user")
def login(payload: LoginRequest, request: Request):

    email = payload.email.strip().lower()

    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    try:
        response = client.auth.sign_in_with_password(
            {"email": email, "password": payload.password}
        )
    except Exception as e:
        # Log the error for debugging but don't expose details to user
        from core.logging_config import logger
        logger.warning(f"Login attempt failed for {email}: {type(e).__name__}")
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not response.session or not response.session.access_token:
        raise HTTPException(401, "Invalid email or password")

    return TokenResponse(access_token=response.session.access_token)


# ============================================================
# CURRENT USER
# ============================================================
@router.get("/me", response_model=CurrentUser, summary="Current authenticated user")
def read_me(current_user: CurrentUser = Depends(get_current_user)):
    return current_user


# ============================================================
# INITIATE PASSWORD SETUP / RESET
# ============================================================
@router.post(
    "/initiate-password-setup",
    summary="Send password setup or reset email via Supabase"
)
def initiate_password_setup(payload: PasswordSetupRequest):

    email = payload.email.strip().lower()

    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

    try:
        client.auth.reset_password_for_email(email)
        return {
            "success": True,
            "message": "Password setup/reset email sent."
        }
    except Exception as e:
        from core.logging_config import logger
        logger.error(f"Failed to send password reset email to {email}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to send password setup/reset email. Please try again later."
        )
