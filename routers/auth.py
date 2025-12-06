from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
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
