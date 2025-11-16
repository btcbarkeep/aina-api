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
    dependencies=[Depends(requires_role(["admin"]))],
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
    role: str | None = None  # Allow promoting/demoting users


# -----------------------------------------------------
# 1️⃣ Create User
# -----------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(payload: AdminCreateUser):
    """
    Creates a user in Supabase (no password yet),
    sends password-setup email.
    """

    # Step 1 — Create user record in Supabase
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
            detail=f"Supabase user creation failed: {str(e)}",
        )

    # Step 2 — Generate password token
    token = generate_password_setup_token(payload.email)

    # Step 3 — Send password setup email
    try:
        send_password_setup_email(payload.email, token)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed sending password email: {str(e)}",
        )

    return {
        "status": "success",
        "user_id": supa_user.get("id"),
        "email": payload.email,
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
        return result.data or []
    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# -----------------------------------------------------
# 3️⃣ Get Single User
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
# 4️⃣ Update User
# -----------------------------------------------------
@router.patch("/users/{user_id}", summary="Admin: Update user")
def update_user(user_id: str, payload: AdminUpdateUser):

    update_data = {
        k: v for k, v in payload.dict().items()
        if v is not None
    }

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
        raise HTTPException(500, f"Supabase error: {e}")

    if not result.data:
        raise HTTPException(404, "User not found")

    return {"status": "updated", "user": result.data[0]}


# -----------------------------------------------------
# 5️⃣ Delete User
# -----------------------------------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(user_id: str):
    client = get_supabase_client()

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

    # Building access is stored in Supabase now — no SQL cleanup

    return {"status": "deleted", "email": email, "user_id": user_id}


# -----------------------------------------------------
# 6️⃣ Resend Password Setup Email
# -----------------------------------------------------
@router.post(
    "/users/{user_id}/resend-password",
    summary="Admin: Re-send new user password setup email"
)
def resend_password_setup(user_id: str):

    client = get_supabase_client()

    # Get user record
    try:
        res = (
            client.table("users")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")

    if not res.data:
        raise HTTPException(404, "User not found")

    email = res.data["email"]

    # Generate token
    token = generate_password_setup_token(email)

    # Send email
    try:
        send_password_setup_email(email, token)
    except Exception as e:
        raise HTTPException(500, f"Failed sending email: {e}")

    return {"status": "email_sent", "email": email, "debug_token": token}
