# dependencies/auth.py
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from core.config import settings  # ✅ import from your new structure

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class CurrentUser(BaseModel):
    username: str
    role: str = "admin"


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    """Decode JWT and return the current authenticated user."""
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
    """Decorator dependency for role-based access control."""
    def role_dependency(current_user: CurrentUser = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User requires '{required_role}' role",
            )
        return current_user
    return role_dependency
