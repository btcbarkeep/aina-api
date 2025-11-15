# core/auth_helpers.py

from fastapi import HTTPException
from datetime import datetime, timedelta
from uuid import uuid4
from jose import jwt
from passlib.context import CryptContext

from core.config import settings
from core.supabase_client import get_supabase_client


SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================
# 🔐 BUILDING ACCESS CHECK (still uses SQLModel access table)
# ============================================================
def verify_user_building_access(session, username: str, building_id: int) -> None:
    """
    Building permissions are still stored locally for now.
    """
    from models import UserBuildingAccess

    # Contractor = global access
    contractor = session.exec(
        select(UserBuildingAccess)
        .where(UserBuildingAccess.username == username)
        .where(UserBuildingAccess.role == "contractor")
    ).first()

    if contractor:
        return

    # Standard building access check
    allowed = session.exec(
        select(UserBuildingAccess)
        .where(UserBuildingAccess.username == username)
        .where(UserBuildingAccess.building_id == building_id)
    ).first()

    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=f"User '{username}' is not authorized to access building {building_id}.",
        )


# ============================================================
# 👤 CREATE USER *IN SUPABASE* (NO PASSWORD)
# ============================================================
def create_user_no_password(
    full_name: str,
    email: str,
    organization_name: str,
    phone: str | None = None,
    role: str = "hoa",
):
    """
    Creates a user in the Supabase 'users' table without a password.
    Compatible with Supabase Python client 2.x.
    """

    client = get_supabase_client()

    # -------------------------------
    # 1️⃣ Check if user already exists
    # -------------------------------
    try:
        existing = (
            client.table("users")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase lookup failed: {str(e)}")

    if existing.data:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    # -------------------------------
    # 2️⃣ Insert new user
    # -------------------------------
    user_id = str(uuid4())
    now = datetime.utcnow().isoformat()

    user_payload = {
        "id": user_id,
        "email": email,
        "username": email,
        "full_name": full_name,
        "organization_name": organization_name,
        "phone": phone,
        "role": role,
        "hashed_password": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = (
            client.table("users")
            .insert(user_payload)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase create error: {str(e)}")

    # Supabase returns a list under result.data
    if not result.data:
        raise HTTPException(
            status_code=500,
            detail="Supabase insert returned no data (unexpected).",
        )

    return result.data[0]  # Return created user



# ============================================================
# 🔑 CREATE PASSWORD RESET TOKEN (IN SUPABASE)
# ============================================================
def create_password_token(email: str, expires_minutes: int = 60):
    """
    Store a password reset token in the Supabase users table.
    """

    client = get_supabase_client()

    token = uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)

    result = client.table("users").update({
        "reset_token": token,
        "reset_token_expires": expires_at.isoformat()
    }).eq("email", email).execute()

    if result.error:
        raise HTTPException(status_code=500, detail=f"Supabase error: {result.error}")

    return token


# ============================================================
# 🔍 FETCH USER FROM SUPABASE
# ============================================================
def get_user_by_email(email: str):
    client = get_supabase_client()

    result = client.table("users").select("*").eq("email", email).maybe_single().execute()

    if result.error:
        raise HTTPException(status_code=500, detail="Supabase query failed.")

    return result.data


# ============================================================
# 🔐 PASSWORD HASHING / VERIFYING
# ============================================================
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


# ============================================================
# 📧 JWT — PASSWORD SETUP TOKEN (emailed)
# ============================================================
def generate_password_setup_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_setup_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
