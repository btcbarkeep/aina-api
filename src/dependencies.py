from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

# --- Auth Config ---
try:
    # Normal import when running locally or tests
    from src.core.config import SECRET_KEY, ALGORITHM
except ModuleNotFoundError:
    # Fallback for Render or when src is already in sys.path
    from core.config import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# --- Mock user store for demo/testing ---
users_db = {
    "admin": {"username": "admin", "role": "admin"},
    "user": {"username": "user", "role": "user"},
}

# --- Verify JWT token ---
def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Validates JWT token from Authorization header.
    Returns the username if valid, else raises HTTPException.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials.",
            )
        return users_db.get(username, {"username": username, "role": "user"})
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )


def get_active_user(current_user: dict = Depends(get_current_user)):
    """
    Ensures the user is active. Placeholder for real validation.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Inactive user.")
    return current_user


def get_admin_user(current_user: dict = Depends(get_current_user)):
    """
    Restricts access to admin-only endpoints.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return current_user
