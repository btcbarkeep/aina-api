from fastapi import Depends, HTTPException, Request, status
from jose import jwt, JWTError
from src.core.config import SECRET_KEY, ALGORITHM

def get_current_user(request: Request):
    """
    Validate JWT from the Authorization header and return the user payload.
    Expected header: Authorization: Bearer <token>
    """
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )

    token = auth_header.split(" ", 1)[1].strip()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")

        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")

        return {"username": username, "role": role}

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_active_user(current_user: dict = Depends(get_current_user)):
    """Allow any authenticated user."""
    return current_user


def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Restrict access to admin users only."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user



def get_active_user(current_user: dict = Depends(get_current_user)):
    """Any authenticated user."""
    return current_user
