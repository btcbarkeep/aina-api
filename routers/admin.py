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
# Router — ADMIN + SUPER ADMIN ONLY
# -----------------------------------------------------
router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(requires_role(["admin", "super_admin", "manager"]))],
)


# -----------------------------------------------------
# Allowed Roles
# -----------------------------------------------------
ALLOWED_ROLES = ["super_admin", "admin", "manager", "contractor", "hoa", "viewer"]


# -----------------------------------------------------
# Payload Models
# -----------------------------------------------------
class AdminCreateUser(BaseModel):
    full_name: str | None = None
    email: EmailStr
    organization_name: str | None = None
    phone: str | None = None
    role: str = "hoa"  # default lowest role


class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    phone: str | None = None
    role: str | None = None


# -----------------------------------------------------
# Helper — Ensure role assignment is allowed
# -----------------------------------------------------
def validate_role_change(requestor: CurrentUser, desired_role: str):
    """Ensure the logged-in admin has permission to assign the chosen role."""

    if desired_role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role: {desired_role}")

    # Only super_admin can assign privileged roles
    privileged = ["super_admin", "admin", "manager"]

    if desired_role in privileged and requestor.role != "super_admin":
        raise HTTPException(
            403,
            detail=f"Only super_admin can assign role '{desired_role}'"
        )


# -----------------------------------------------------
# 1️⃣ CREATE USER
# -----------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    current_user: CurrentUser = Depends(get_current_user),
):
    # Role validation
    validate_role_change(current_user, payload.role)

    try:
        supa_user = create_user_no_password(
            full_name=payload.full_name,
            email=payload.email,
            organization_name=payload.organization_name,
            phone=payload.phone,
            role=payload.role,
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase user creation failed: {e}")

    token = generate_password_setup_token(payload.email)

    try:
        send_password_setup_email(payload.email, token)
    except Exception as e:
        raise HTTPException(500, f"Failed to send password setup email: {e}")

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
def list_users(role: str | None = None):
    client = get_supabase_client()

    query = client.table("users").select("*")

    if role:
        query = query.eq("role", role)

    result = query.order("created_at", desc=True).execute()

    return result.data or []


# -----------------------------------------------------
# 3️⃣ GET ONE USER
# -----------------------------------------------------
@router.get("/users/{user_id}", summary="Admin: Get one user")
def get_user(user_id: str):
    client = get_supabase_client()

    result = (
        client.table("users")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )

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
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(400, "No valid fields to update")

    # Prevent role assignment unless allowed
    if "role" in update_data:
        validate_role_change(current_user, update_data["role"])

    update_data["updated_at"] = "now()"

    client = get_supabase_client()

    result = (
        client.table("users")
        .update(update_data, returning="representation")
        .eq("id", user_id)
        .execute()
    )

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

    # Fix: use current_user.id, not current_user.user_id
    if user_id == current_user.id:
        raise HTTPException(400, "Admins cannot delete their own account.")

    existing = (
        client.table("users")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(404, "User not found")

    email = existing.data["email"]

    result = (
        client.table("users")
        .delete(returning="representation")
        .eq("id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "User not found")

    return {"status": "deleted", "email": email, "user_id": user_id}


# -----------------------------------------------------
# 6️⃣ RESEND PASSWORD SETUP EMAIL
# -----------------------------------------------------
@router.post("/users/{user_id}/resend-password", summary="Admin: Resend password email")
def resend_password_setup(user_id: str):
    client = get_supabase_client()

    result = (
        client.table("users")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(404, "User not found")

    email = result.data["email"]
    token = generate_password_setup_token(email)

    try:
        send_password_setup_email(email, token)
    except Exception as e:
        raise HTTPException(500, f"Failed sending email: {e}")

    return {"status": "email_sent", "email": email, "debug_token": token}
