from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from src.routers.auth import SECRET_KEY, ALGORITHM

def get_current_user(request: Request):
    """
    Simplified auth: manually extract the Bearer token from Authorization header.
    """
    auth_header = request.headers.get("authorization")
    print("🔍 [DEBUG] Auth header received:", auth_header)

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header.split("Bearer ")[-1].strip()
    print("🔍 [DEBUG] Extracted token:", token)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("🔍 [DEBUG] Decoded payload:", payload)
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return {"username": username, "role": role}
    except JWTError as e:
        print("❌ [DEBUG] JWTError:", e)
        raise HTTPException(status_code=401, detail="Could not validate token")

def get_admin_user(current_user: dict = Depends(get_current_user)):
    """
    Restricts access to users with role 'admin'.
    """
    print("🔍 [DEBUG] Current user:", current_user)
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user

get_active_user = get_current_user
