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
# 🔐 RBAC — REQUIRE ADMIN ROLE
# ============================================================
def require_admin_role(current_user: dict):
    """
    Ensures the current user is an admin.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required for this action."
        )


# ============================================================
# 🔐 Supabase RBAC — Check building access
# ============================================================
def verify_user_building_access_supabase(user_id: str, building_id: str):
    """
    Checks if user has access to a specific building.
    Supabase table: user_building_access
    """

    client = get_supabase_client()

    try:
        result = (
            client.table("user_building_access")
            .select("id")
            .eq("user_id", user_id)
            .eq("building_id", building_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase access lookup failed: {e}")

    if not result.data:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this building."
        )


# ============================================================
# 🔐 Helper: Resolve event_id → building_id
# ============================================================
def get_event_building_id(event_id: str) -> str:
    """
    Fetches the building_id for a given event.
    """
    client = get_supabase_client()

    try:
        result = (
            client.table("events")
            .select("building_id")
            .eq("id", event_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase lookup failed: {e}")

    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found.")

    return result.data["building_id"]


# ============================================================
# 🔐 Combined helper — can this user modify this event?
# ============================================================
def verify_user_event_permission(user_id: str, event_id: str):
    """
    Confirms user has access to the building associated with this event.
    """

    building_id = get_event_building_id(event_id)
    verify_user_building_access_supabase(user_id, building_id)


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
    Creates a user in the Supabase 'users' table.
    Password is not set until they visit set-password page.
    """

    client = get_supabase_client()

    # 1️⃣ Check if user already exists
    try:
        existing = (
            client.table("users")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase lookup failed: {e}")

    if existing.data:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")

    # 2️⃣ Insert new user
    user_id = str(uuid4())
    now = datetime.utcnow().isoformat()

    payload = {
        "id": user_id,
        "email": email,
        "username": email,
        "full_name": full_name,
        "organization_name": organization_name,
        "phone": phone,
        "role": role,  # HOA, contractor, admin, etc.
        "hashed_password": None,
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = client.table("users").insert(payload).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert failed: {e}")

    if not result.data:
        raise HTTPException(status_code=500, detail="Supabase returned no data.")

    return result.data[0]


# ============================================================
# 🔑 CREATE PASSWORD RESET TOKEN
# ============================================================
def create_password_token(email: str, expires_minutes: int = 60):
    """
    Stores reset_token + expiration in Supabase.
    """

    client = get_supabase_client()

    token = uuid4().hex
    expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)

    try:
        result = (
            client.table("users")
            .update({
                "reset_token": token,
                "reset_token_expires": expires_at.isoformat()
            })
            .eq("email", email)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase update failed: {e}")

    return token


# ============================================================
# 🔍 FETCH USER BY EMAIL
# ============================================================
def get_user_by_email(email: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("email", email)
            .maybe_single()
            .execute()
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Supabase query failed.")

    return result.data


# ============================================================
# 🔐 PASSWORD HASHING
# ============================================================
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    return pwd_context.verify(plain, hashed)


# ============================================================
# 📧 PASSWORD SETUP TOKEN
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
