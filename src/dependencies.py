from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from src.core.config import SECRET_KEY, ALGORITHM

# OAuth2 token scheme (used by FastAPI to parse "Authorization: Bearer <token>")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(request: Request, token: str = Depends(oauth2_scheme)):
    """
    Validates JWT token from Authorization header.
    Returns the user dict if valid.
    """
    print("🔍 DEBUG HEADERS:", dict(request.headers))  # Temporary debug

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing token"
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "user")

        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )

        # Return a minimal user object
        return {"username": username, "role": role}

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Restricts access to users with role 'admin'."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def get_active_user(current_user: dict = Depends(get_current_user)):
    """Basic authenticated user access."""
    return current_user
