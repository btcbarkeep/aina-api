# dependencies/auth.py

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from core.config import settings
from core.supabase_client import get_supabase_client

bearer_scheme = HTTPBearer()


# -----------------------------------------------------
# Authenticated user object
# -----------------------------------------------------
class CurrentUser(BaseModel):
    user_id: str
    email: str
    role: str
    full_name: Optional[str] = None
    organization_name: Optional[str] = None


# -----------------------------------------------------
# Decode JWT → Validate user (with bootstrap override)
# -----------------------------------------------------
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> CurrentUser:

    token = credentials.credentials

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # -------------------------
    # Decode JWT
    # -------------------------
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        raise unauthorized

    email = payload.get("sub")
    role = payload.get("role")
    user_id = payload.get("user_id")

    if not email or not user_id:
        raise unauthorized

    # -------------------------
    # Allow bootstrap admin
    # -------------------------
    if user_id == "bootstrap" and role == "admin":
        return CurrentUser(
            user_id="bootstrap",
            email=email,
            role="admin",
            full_name="Bootstrap Admin",
            organization_name="System"
        )

    # -------------------------
    # Look up user in Supabase
    # -------------------------
    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase error during user lookup: {str(e)}"
        )

    if not result.data:
        raise unauthorized

    user = result.data[0]

    return CurrentUser(
        user_id=user["id"],
        email=user["email"],
        role=user.get("role", role),
        full_name=user.get("full_name"),
        organization_name=user.get("organization_name"),
    )


# -----------------------------------------------------
# Role-based guard
# -----------------------------------------------------
def requires_role(required_role: str):
    def checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{required_role}' role",
            )
        return current_user

    return checker
