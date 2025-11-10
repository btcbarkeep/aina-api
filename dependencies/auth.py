# dependencies/auth.py
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from core.config import settings  # ✅ import from your config

# Use HTTP Bearer (no OAuth2 password form)
bearer_scheme = HTTPBearer()


class CurrentUser(BaseModel):
    username: str
    role: str = "admin"


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> CurrentUser:
    """
    Validate JWT from the Authorization header.
    Example header: Authorization: Bearer <token>
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        username: Optional[str] = payload.get("sub")
        role: str = payload.get("role", "admin")

        if username is None:
            raise credentials_exception

        return CurrentUser(username=username, role=role)

    except JWTError:
        raise credentials_exception


# -----------------------------------------------------
#  ROLE-BASED ACCESS CONTROL
# -----------------------------------------------------
def requires_role(required_role: str):
    """Dependency decorator for role-based access control."""
    def role_dependency(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User requires '{required_role}' role",
            )
        return current_user
    return role_dependency
