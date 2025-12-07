from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from core.supabase_client import get_supabase_client
from core.rate_limiter import require_rate_limit, get_rate_limit_identifier
from dependencies.auth import get_current_user, CurrentUser
from core.logging_config import logger


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


class ProfileUpdate(BaseModel):
    """Profile update model for self-service editing."""
    full_name: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/me", response_model=CurrentUser, summary="Update current user profile")
def update_profile(
    payload: ProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Update the current user's profile (self-service).
    
    Users can update their own full_name and phone.
    Other fields (role, organization IDs, etc.) must be updated by admins.
    """
    client = get_supabase_client()
    
    # Build update payload
    update_metadata = {}
    
    if payload.full_name is not None:
        update_metadata["full_name"] = payload.full_name.strip() if payload.full_name else None
    
    if payload.phone is not None:
        update_metadata["phone"] = payload.phone.strip() if payload.phone else None
    
    if not update_metadata:
        # No changes, return current user
        return current_user
    
    try:
        # Get current user metadata
        resp = client.auth.admin.get_user_by_id(current_user.auth_user_id)
        if not resp.user:
            raise HTTPException(404, "User not found")
        
        current_meta = resp.user.user_metadata or {}
        
        # Merge updates
        updated_meta = {**current_meta, **update_metadata}
        
        # Update user metadata
        client.auth.admin.update_user_by_id(
            current_user.auth_user_id,
            {"user_metadata": updated_meta}
        )
        
        logger.info(f"User {current_user.auth_user_id} updated their profile")
        
        # Return updated user
        updated_resp = client.auth.admin.get_user_by_id(current_user.auth_user_id)
        if not updated_resp.user:
            raise HTTPException(500, "Failed to retrieve updated user")
        
        updated_meta = updated_resp.user.user_metadata or {}
        
        return CurrentUser(
            id=updated_resp.user.id,
            auth_user_id=updated_resp.user.id,
            email=updated_resp.user.email,
            role=updated_meta.get("role", "aoao"),
            full_name=updated_meta.get("full_name"),
            organization_name=updated_meta.get("organization_name"),
            phone=updated_meta.get("phone"),
            contractor_id=updated_meta.get("contractor_id"),
            aoao_organization_id=updated_meta.get("aoao_organization_id"),
            pm_company_id=updated_meta.get("pm_company_id"),
            permissions=updated_meta.get("permissions", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}")
        raise HTTPException(500, f"Failed to update profile: {str(e)}")


# ============================================================
# INITIATE PASSWORD SETUP / RESET
# ============================================================
@router.post(
    "/initiate-password-setup",
    summary="Send password setup or reset email via Supabase",
    description="""
    Initiates a password setup or reset flow by sending an email with a secure token.
    
    **Security Features:**
    - Rate limited to prevent abuse (5 requests per 15 minutes per IP/email)
    - All attempts are logged for security monitoring
    - Tokens expire after a set time (handled by Supabase)
    
    **Note:** This endpoint always returns success to prevent email enumeration attacks.
    """,
    responses={
        200: {"description": "Email sent successfully (or email not found, for security)"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"}
    }
)
def initiate_password_setup(payload: PasswordSetupRequest, request: Request):
    """
    Send password setup or reset email.
    
    This endpoint is rate-limited and logs all attempts for security monitoring.
    For security reasons, it always returns success even if the email doesn't exist.
    """
    email = payload.email.strip().lower()
    
    # Rate limiting: 5 requests per 15 minutes per email/IP
    identifier = get_rate_limit_identifier(request, user_id=email)
    require_rate_limit(request, identifier=identifier, max_requests=5, window_seconds=900)
    
    # Log password reset attempt for security monitoring
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    logger.info(f"Password reset attempt: email={email}, ip={client_ip}")

    client = get_supabase_client()
    if not client:
        logger.error("Supabase not configured for password reset")
        raise HTTPException(500, "Service temporarily unavailable")

    try:
        client.auth.reset_password_for_email(email)
        logger.info(f"Password reset email sent successfully: email={email}")
        return {
            "success": True,
            "message": "If an account exists with this email, a password reset link has been sent."
        }
    except Exception as e:
        # Log error but don't expose details to prevent email enumeration
        logger.error(f"Failed to send password reset email to {email}: {type(e).__name__}: {str(e)}")
        # Always return success to prevent email enumeration attacks
        return {
            "success": True,
            "message": "If an account exists with this email, a password reset link has been sent."
        }
