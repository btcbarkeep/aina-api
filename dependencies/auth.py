from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from core.config import settings
from core.supabase_client import get_supabase_client

bearer_scheme = HTTPBearer()


# ============================================================
# Current User returned to backend + frontend
# ============================================================
class CurrentUser(BaseModel):
    id: str
    email: str
    role: str
    full_name: Optional[str] = None
    organization_name: Optional[str] = None


# ============================================================
# Decode token + resolve user
# ============================================================
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> CurrentUser:

    token = credentials.credentials

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # -------------------------------------------------
    # Decode JWT
    # -------------------------------------------------
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": True},
        )
    except JWTError:
        raise unauthorized

    email = payload.get("sub")
    role_from_token = payload.get("role")

    # -------------------------------------------------
    # ⭐ CRON TOKEN OVERRIDE — bypass Supabase
    # -------------------------------------------------
    if payload.get("cron") is True:
        return CurrentUser(
            id="cron",
            email=email or "cron@ainaprotocol.com",
            role="admin",
            full_name="Cron Job",
            organization_name="System",
        )

    # -------------------------------------------------
    # BOOTSTRAP ADMIN OVERRIDE
    # -------------------------------------------------
    if payload.get("bootstrap_admin") is True:
        return CurrentUser(
            id="bootstrap",
            email=email or "bootstrap@ainaprotocol.com",
            role="admin",
            full_name="Bootstrap Admin",
            organization_name="System",
        )

    # -------------------------------------------------
    # Standard authentication path
    # -------------------------------------------------
    if not email:
        raise unauthorized

    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("email", email)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")

    user = result.data
    if not user:
        raise unauthorized

    role = user.get("role") or role_from_token or "hoa"

    return CurrentUser(
        id=user["id"],
        email=user["email"],
        role=role,
        full_name=user.get("full_name"),
        organization_name=user.get("organization_name"),
    )


# ============================================================
# Role Requirement Wrapper
# ============================================================
def requires_role(allowed_roles: list[str]):
    def checker(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {allowed_roles}",
            )
        return current_user
    return checker
