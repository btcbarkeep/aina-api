from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError

# fallback-safe import
try:
    from src.core.config import SECRET_KEY, ALGORITHM
except ModuleNotFoundError:
    from core.config import SECRET_KEY, ALGORITHM

def get_current_user(request: Request):
    auth_header = request.headers.get("authorization")
    print("\n🔍 [DEBUG] Authorization header:", auth_header)
    print("🔍 [DEBUG] SECRET_KEY seen by app:", repr(SECRET_KEY))
    print("🔍 [DEBUG] ALGORITHM seen by app:", ALGORITHM)

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")

    token = auth_header.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("✅ [DEBUG] JWT decoded successfully:", payload)
        return payload
    except JWTError as e:
        print("❌ [DEBUG] JWT decode failed:", e)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token decode failed: {e}")

from fastapi import Depends, HTTPException, status, Request

def get_active_user(request: Request):
    """Placeholder active user dependency to satisfy router imports."""
    # For now, just return a mock user object so imports succeed.
    return {"username": "test_user", "role": "user"}
