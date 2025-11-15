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

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("email", payload.email)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Supabase query failed: {str(e)}",
        )

    # result.data will be a list or None
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Get the first user (maybe_single no longer works the same)
    user = result.data[0]

    # Validate password
    hashed_pw = user.get("hashed_password")
    if not hashed_pw or not pwd_context.verify(payload.password, hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate JWT
    token = _create_access_token(
        email=user["email"],
        role=user.get("role", "user"),
        user_id=user["id"],
    )

    return TokenResponse(access_token=token)

@router.post("/dev-login", summary="Temporary admin login")
def dev_login():
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

    return {"access_token": token, "token_type": "bearer"}


# -----------------------------------------------------
# VALIDATE TOKEN → returns CurrentUser
# -----------------------------------------------------
@router.get("/me", response_model=CurrentUser)
def read_me(current_user: CurrentUser = Depends(lambda: None)):
    return current_user


## password backend endpoint

class SetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/set-password", summary="Finish account setup by creating password")
def set_password(payload: SetPasswordRequest):
    client = get_supabase_client()

    # Decode email from token
    try:
        email = jwt.decode(
            payload.token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )["sub"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Hash the password
    hashed_pw = pwd_context.hash(payload.password)

    # Save password to Supabase
    result = (
        client.table("users")
        .update({
            "hashed_password": hashed_pw,
            "reset_token": None,
            "reset_token_expires": None,
        })
        .eq("email", email)
        .execute()
    )

    if result.error:
        raise HTTPException(status_code=500, detail="Failed to set password")

    return {"status": "success", "message": "Password created successfully!"}

