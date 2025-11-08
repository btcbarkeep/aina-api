# src/dependencies/auth.py
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from core.config import settings

# NOTE: this should match the REAL login endpoint path
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class CurrentUser(BaseModel):
    username: str
    role: str = "admin"


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
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


def requires_role(*roles: str):
    """
    Role-based guard implemented as a dependency factory.

    Usage example:

        @router.get("/admin-only")
        async def admin_only(
            current_user: CurrentUser = Depends(requires_role("admin"))
        ):
            return {"hello": current_user.username}

    You can also use it as a global dependency on a route:

        @router.get("/reports", dependencies=[Depends(requires_role("admin"))])
        async def get_reports():
            ...
    """

    async def _role_checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if roles and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
            )
        return current_user

    return _role_checker
