# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

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


# -----------------------------------------------------
# Router — ADMIN ONLY
# -----------------------------------------------------
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(requires_role(["admin", "super_admin"]))],
)


# -----------------------------------------------------
# Payload Models
# -----------------------------------------------------
class AdminCreateUser(BaseModel):
    full_name: str | None = None
    email: EmailStr
    organization_name: str | None = None
    phone: str | None = None
    role: str = "hoa"  # default non-admin user


class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    phone: str | None = None
    role: str | None = None


# -----------------------------------------------------
# 1️⃣ CREATE USER
# -----------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Creates a user in Supabase (no password yet),
    and sends password-setup email.
    """

    # Step 1 — Create Supabase user
    try:
        supa_user = create_user_no_password(
            full_name=payload.full_name,
            email=payload.email,
            organization_name=payload.organization_name,
            phone=payload.phone,
            role=payload.role,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase user creation failed: {e}",
        )

    # Step 2 — Generate password setup token
    token = generate_password_setup_token(payload.email)

    # Step 3 — Email user
    try:
        send_password_setup_email(payload.email, token)
    except Exception as e:
        raise HTTPException(500, f"Failed to send password email: {e}")

    return {
        "status": "success",
        "user_id": supa_user.get("id"),
        "email": payload.email,
        "debug_token": token,
    }


# -----------------------------------------------------
# 2️⃣ LIST USERS
# -----------------------------------------------------
@router.get("/users", summary="Admin: List all users")
def list_users():
    client = get_supabase_client()

    try:
        result = client.table("users").select("*").order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# -----------------------------------------------------
# 3️⃣ GET ONE USER
# -----------------------------------------------------
@router.get("/users/{user_id}", summary="Admin: Get one user")
def get_user(user_id: str):
    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")

    if not result.data:
        raise HTTPException(404, "User not found")

    return result.data


# -----------------------------------------------------
# 4️⃣ UPDATE USER
# -----------------------------------------------------
@router.patch("/users/{user_id}", summary="Admin: Update user")
def update_user(
    user_id: str, 
    payload: AdminUpdateUser,
    current_user: CurrentUser = Depends(get_current_user),
):
    update_data = {k: v for k, v in payload.dict().items() if v is not None}

    if not update_data:
        raise HTTPException(400, "No valid fields to update")

    update_data["updated_at"] = "now()"

    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .update(update_data)
            .eq("id", user_id)
            .select("*")
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not result.data:
        raise HTTPException(404, "User not found")

    return {"status": "updated", "user": result.data[0]}


# -----------------------------------------------------
# 5️⃣ DELETE USER
# -----------------------------------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Prevent deleting yourself
    if user_id == current_user.user_id:
        raise HTTPException(400, "Admins cannot delete their own account.")

    # Verify user exists
    try:
        existing = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase fetch failed: {e}")

    if not existing.data:
        raise HTTPException(404, "User not found")

    email = existing.data["email"]

    # Delete
    try:
        client.table("users").delete().eq("id", user_id).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase delete failed: {e}")

    return {"status": "deleted", "email": email, "user_id": user_id}


# -----------------------------------------------------
# 6️⃣ RESEND PASSWORD SETUP EMAIL
# -----------------------------------------------------
@router.post("/users/{user_id}/resend-password", summary="Admin: Resend password email")
def resend_password_setup(user_id: str):

    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")

    if not result.data:
        raise HTTPException(404, "User not found")

    email = result.data["email"]

    token = generate_password_setup_token(email)

    try:
        send_password_setup_email(email, token)
    except Exception as e:
        raise HTTPException(500, f"Failed sending email: {e}")

    return {"status": "email_sent", "email": email, "debug_token": token}
