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

from core.supabase_helpers import safe_select, safe_update
from dependencies.auth import get_current_user, CurrentUser


# ============================================================
# Router Setup
# ============================================================
router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================
# Pydantic Models
# ============================================================
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetPasswordRequest(BaseModel):
    token: str
    password: str


# ============================================================
# Helper: Create JWT Access Token
# ============================================================
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


# ============================================================
# LOGIN ENDPOINT
# ============================================================
@router.post("/login", response_model=TokenResponse, summary="Authenticate user")
def login(payload: LoginRequest):
    # Fetch user
    user = safe_select("users", {"email": payload.email}, single=True)
    if not user:
        raise HTTPException(401, "Invalid email or password")

    # Optional: Prevent login without password being set
    hashed_pw = user.get("hashed_password")
    if not hashed_pw:
        raise HTTPException(
            401,
            "Password not set — please complete your setup email.",
        )

    # Optional: Support disabled accounts
    if user.get("disabled") is True:
        raise HTTPException(403, "Account disabled — contact administrator.")

    # Verify password
    if not verify_password(payload.password, hashed_pw):
        raise HTTPException(401, "Invalid email or password")

    # Issue token with user's DB role
    token = _create_access_token(
        email=user["email"],
        role=user.get("role", "hoa"),
        user_id=user["id"],
    )

    return TokenResponse(access_token=token)


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
# SET PASSWORD AFTER ADMIN CREATED ACCOUNT
# ============================================================
@router.post("/set-password", summary="Finish account setup by creating password")
def set_password(payload: SetPasswordRequest):
    # Decode token
    try:
        decoded = jwt.decode(
            payload.token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        email = decoded.get("sub")
        if not email:
            raise Exception("Missing email")
    except JWTError:
        raise HTTPException(400, "Invalid or expired setup token")

    # Fetch user
    user = safe_select("users", {"email": email}, single=True)
    if not user:
        raise HTTPException(404, "User not found")

    # Validate stored token
    stored_token = user.get("reset_token")
    if not stored_token or stored_token != payload.token:
        raise HTTPException(400, "Invalid reset token")

    # Validate expiration
    expires = user.get("reset_token_expires")
    if expires:
        try:
            if datetime.fromisoformat(expires) < datetime.utcnow():
                raise HTTPException(400, "Reset token expired")
        except Exception:
            raise HTTPException(400, "Invalid token expiration format")

    # Save hashed password and clear token
    hashed_pw = hash_password(payload.password)

    updated = safe_update(
        "users",
        {"email": email},
        {
            "hashed_password": hashed_pw,
            "reset_token": None,
            "reset_token_expires": None,
            "updated_at": "now()",
        },
    )

    if not updated:
        raise HTTPException(500, "Failed storing password")

    return {
        "success": True,
        "message": "Password created successfully!",
    }
