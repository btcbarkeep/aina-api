# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from dependencies.auth import get_current_user
from core.supabase_client import get_supabase_client
from core.auth_helpers import create_user_no_password, generate_password_setup_token
from core.email_utils import send_password_setup_email
from database import get_session
from models import UserBuildingAccess


# -------------------------
# Router (NO double prefix)
# -------------------------
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(get_current_user)]
)


# -------------------------
# Require admin utility
# -------------------------
def require_admin(user):
    if getattr(user, "role", None) not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admins only")


# -------------------------
# PAYLOAD MODEL for create-user ❗️❗️❗️
# -------------------------
class AdminCreateUser(BaseModel):
    full_name: str | None = None
    email: EmailStr
    organization_name: str | None = None
    phone: str | None = None
    role: str = "user"


# -------------------------
# 1️⃣ Create user (FIXED)
# -------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    # Create user in Supabase
    try:
        supa_user = create_user_no_password(
            full_name=payload.full_name,
            email=payload.email,
            organization_name=payload.organization_name,
            phone=payload.phone,
            role=payload.role,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase create error: {str(e)}")

    # Create password setup token
    token = generate_password_setup_token(payload.email)

    # Send setup email
    send_password_setup_email(payload.email, token)

    return {
        "status": "success",
        "message": f"Account created for {payload.email}. Password setup email sent.",
        "debug_token": token,
    }


# -------------------------
# 2️⃣ List users (FIXED client API)
# -------------------------
@router.get("/users", summary="Admin: List all users")
def list_users(current_user=Depends(get_current_user)):
    require_admin(current_user)

    client = get_supabase_client()

    try:
        result = client.table("users").select("*").execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")

    return result.data or []


# -------------------------
# 3️⃣ Get user building access
# -------------------------
@router.get("/users/{user_id}/access", summary="Admin: Get building access for a user")
def get_user_access(
    user_id: str,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    email = result.data[0]["email"]

    # Local DB lookup
    rows = session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == email)
    ).all()

    return rows


# -------------------------
# 4️⃣ Update user
# -------------------------
class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    role: str | None = None
    phone: str | None = None


@router.patch("/users/{user_id}", summary="Admin: Update user")
def update_user(
    user_id: str,
    payload: AdminUpdateUser,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    client = get_supabase_client()

    update_data = {k: v for k, v in payload.dict().items() if v is not None}
    update_data["updated_at"] = "now()"

    try:
        result = client.table("users").update(update_data).eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase error: {str(e)}")

    return {"status": "updated", "user": result.data}


# -------------------------
# 5️⃣ Delete user
# -------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(
    user_id: str,
    session: Session = Depends(get_session),
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    client = get_supabase_client()

    # Fetch user first
    result = (
        client.table("users").select("*").eq("id", user_id).execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    email = result.data[0]["email"]

    try:
        client.table("users").delete().eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase delete error: {str(e)}")

    # Cleanup building access locally
    session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == email)
    )
    session.commit()

    return {"status": "deleted", "email": email}


# -------------------------
# 6️⃣ Resend password setup email
# -------------------------
@router.post("/users/{user_id}/resend-password", summary="Admin: Re-send password setup email")
def resend_password_setup(
    user_id: str,
    current_user=Depends(get_current_user),
):
    require_admin(current_user)

    client = get_supabase_client()

    result = (
        client.table("users").select("*").eq("id", user_id).execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    email = result.data[0]["email"]

    token = generate_password_setup_token(email)
    send_password_setup_email(email, token)

    return {"status": "email_sent", "email": email, "debug_token": token}
