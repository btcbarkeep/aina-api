# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email
from database import get_session
from models import UserBuildingAccess


# -----------------------------------------------------
# Router
# -----------------------------------------------------
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(requires_role(["admin", "super_admin"]))],
)


# -----------------------------------------------------
# Payload Model
# -----------------------------------------------------
class AdminCreateUser(BaseModel):
    full_name: str | None = None
    email: EmailStr
    organization_name: str | None = None
    phone: str | None = None
    role: str = "user"


# -----------------------------------------------------
# 1️⃣ Create User
# -----------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
):
    # Supabase user creation
    try:
        supa_user = create_user_no_password(
            full_name=payload.full_name,
            email=payload.email,
            organization_name=payload.organization_name,
            phone=payload.phone,
            role=payload.role,
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase create error: {e}")

    # Password setup token + email
    token = generate_password_setup_token(payload.email)
    send_password_setup_email(payload.email, token)

    return {
        "status": "success",
        "message": f"Account created for {payload.email}. Password setup email sent.",
        "debug_token": token,
    }


# -----------------------------------------------------
# 2️⃣ List Users
# -----------------------------------------------------
@router.get("/users", summary="Admin: List all users")
def list_users():
    client = get_supabase_client()

    try:
        result = client.table("users").select("*").execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")

    return result.data or []


# -----------------------------------------------------
# 3️⃣ Get User Building Access
# -----------------------------------------------------
@router.get("/users/{user_id}/access", summary="Admin: Get building access for a user")
def get_user_access(
    user_id: str,
    session: Session = Depends(get_session),
):
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
        raise HTTPException(500, f"Supabase error: {e}")

    if not result.data:
        raise HTTPException(404, "User not found")

    email = result.data[0]["email"]

    rows = session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == email)
    ).all()

    return rows


# -----------------------------------------------------
# 4️⃣ Update User
# -----------------------------------------------------
class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    role: str | None = None
    phone: str | None = None


@router.patch("/users/{user_id}", summary="Admin: Update user")
def update_user(
    user_id: str,
    payload: AdminUpdateUser,
):
    client = get_supabase_client()

    update_data = {
        k: v for k, v in payload.dict().items()
        if v is not None
    }
    update_data["updated_at"] = "now()"

    try:
        result = (
            client.table("users")
            .update(update_data)
            .eq("id", user_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")

    return {"status": "updated", "user": result.data}


# -----------------------------------------------------
# 5️⃣ Delete User
# -----------------------------------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(
    user_id: str,
    session: Session = Depends(get_session),
):
    client = get_supabase_client()

    result = (
        client.table("users")
        .select("*")
        .eq("id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "User not found")

    email = result.data[0]["email"]

    try:
        client.table("users").delete().eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    # Local DB cleanup
    session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == email)
    )
    session.commit()

    return {"status": "deleted", "email": email}


# -----------------------------------------------------
# 6️⃣ Resend Password Setup Email
# -----------------------------------------------------
@router.post("/users/{user_id}/resend-password", summary="Admin: Resend password setup email")
def resend_password_setup(
    user_id: str,
):
    client = get_supabase_client()

    result = (
        client.table("users").select("*").eq("id", user_id).execute()
    )

    if not result.data:
        raise HTTPException(404, "User not found")

    email = result.data[0]["email"]

    token = generate_password_setup_token(email)
    send_password_setup_email(email, token)

    return {"status": "email_sent", "email": email, "debug_token": token}
