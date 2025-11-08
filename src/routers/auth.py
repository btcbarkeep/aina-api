from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from jose import jwt
from src.core.config import SECRET_KEY, ALGORITHM

router = APIRouter(prefix="/auth", tags=["Auth"])

# ------------------------------------------------------------------
# Dummy login route (for testing)
# ------------------------------------------------------------------
@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = None):
    """
    Issue a JWT token for testing purposes.
    Accepts 'username' and 'password' in the form body.
    """
    username = form_data.username if form_data else "testuser"
    role = "admin" if username == "admin" else "user"

    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {"sub": username, "role": role, "exp": expire}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return {"access_token": token, "token_type": "bearer"}
