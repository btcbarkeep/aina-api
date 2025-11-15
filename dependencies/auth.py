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
# Shape of the authenticated user
# -----------------------------------------------------
class CurrentUser(BaseModel):
    user_id: str
    email: str
    role: str
    full_name: Optional[str] = None
    organization_name: Optional[str] = None


# -----------------------------------------------------
# Decode JWT → Fetch user from Supabase
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

    try:
        # Decode JWT
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        email = payload.get("sub")
        role = payload.get("role")
        user_id = payload.get("user_id")

        if not email or not user_id:
            raise unauthorized

    except JWTError:
        raise unauthorized

    # -----------------------------------------------------
    # Fetch user from Supabase to validate + enrich object
    # -----------------------------------------------------
    client = get_supabase_client()

    result = (
        client.table("users")
        .select("*")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )

    if result.error or not result.data:
        raise unauthorized

    user = result.data

    return CurrentUser(
        user_id=user["id"],
        email=user["email"],
        role=user.get("role", role),
        full_name=user.get("full_name"),
        organization_name=user.get("organization_name"),
    )


# -----------------------------------------------------
# Role-based decorator
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
