# routers/dev_auth.py

from fastapi import APIRouter
from datetime import datetime, timedelta
from jose import jwt

from core.config import settings

router = APIRouter(
    prefix="/auth",
    tags=["Auth (Dev Only)"]
)

SECRET = settings.SECRET_KEY
ALGO = settings.ALGORITHM


@router.post("/dev-login", summary="DEV: Get an instant admin token")
def dev_login():
    """
    ⚠️ DEV ONLY — Returns a hard-coded admin JWT.
    Use this for testing Swagger.
    """

    payload = {
        "sub": "dev-admin",
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(days=7),
    }

    token = jwt.encode(payload, SECRET, algorithm=ALGO)

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "admin",
        "expires_in_days": 7,
    }
