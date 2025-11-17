# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

# NEW permission system
from core.permission_helpers import requires_permission
from core.permissions import ROLE_PERMISSIONS

# Supabase helpers
from core.supabase_helpers import safe_select, safe_insert, safe_update
from core.supabase_client import get_supabase_client

# Email / auth helpers
from core.auth_helpers import (
    create_user_no_password,
    generate_password_setup_token,
)
from core.email_utils import send_password_setup_email


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    # Admin panel requires admin or super_admin permissions
    dependencies=[Depends(requires_permission("users:write"))],
)


# -----------------------------------------------------
# Allowed System Roles (derived from your RBAC model)
# -----------------------------------------------------
ALLOWED_ROLES = list(ROLE_PERMISSIONS.keys())


# -----------------------------------------------------
# Payloads
# -----------------------------------------------------
class AdminCreateUser(BaseModel):
    full_name: str | None = None
    email: EmailStr
    organization_name: str | None = None
    phone: str | None = None
    role: str = "hoa"


class AdminUpdateUser(BaseModel):
    full_name: str | None = None
    organization_name: str | None = None
    phone: str | None = None
    role: str | None = None


# -----------------------------------------------------
# Helper — Validate role changes
# -----------------------------------------------------
def validate_role_change(requestor: CurrentUser, desired_role: str):
    """
    Enforces:
    - Only super_admin may assign super_admin
    - Only roles in ALLOWED_ROLES may be assigned
    """

    if desired_role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role: {desired_role}")

    # Only super_admin can create or assign other super_admins
    if desired_role == "super_admin" and requestor.role != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Only super_admin can assign or modify 'super_admin' accounts."
        )

    # Admin CANNOT assign an admin role (only super_admin should)
    if desired_role == "admin" and requestor.role != "super_admin":
        raise HTTPException(
            403,
            "Only super_admin may assign admin-level roles."
        )


# -----------------------------------------------------
# 1️⃣ CREATE USER
# -----------------------------------------------------
@router.post("/create-account", summary="Admin: Create a user account")
def admin_create_account(
    payload: AdminCreateUser,
    current_user: CurrentUser = Depends(get_current_user),
):
    validate_role_change(current_user, payload.role)

    try:
        created = create_user_no_password(
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
        "success": True,
        "data": {
            "user_id": created.get("id"),
            "email": payload.email,
        },
        "debug_token": token,
    }


# -----------------------------------------------------
# 2️⃣ LIST USERS
# -----------------------------------------------------
@router.get("/users", summary="Admin: List all users")
def list_users(role: str | None = None):
    client = get_supabase_client()

    try:
        query = client.table("users").select("*")
        if role:
            query = query.eq("role", role)
        result = query.order("created_at", desc=True).execute()
    except Exception as e:
        raise HTTPException(500, f"Failed fetching users: {e}")

    return {"success": True, "data": result.data or []}


# -----------------------------------------------------
# 3️⃣ GET ONE USER
# -----------------------------------------------------
@router.get("/users/{user_id}", summary="Admin: Get one user")
def get_user(user_id: str):
    result = safe_select("users", {"id": user_id}, single=True)

    if not result:
        raise HTTPException(404, "User not found")

    return {"success": True, "data": result}


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

    # If updating role → validate
    if "role" in update_data:
        validate_role_change(current_user, update_data["role"])

    update_data["updated_at"] = "now()"

    updated = safe_update("users", {"id": user_id}, update_data)

    if not updated:
        raise HTTPException(404, "User not found")

    return {"success": True, "data": updated}


# -----------------------------------------------------
# 5️⃣ DELETE USER
# -----------------------------------------------------
@router.delete("/users/{user_id}", summary="Admin: Delete user")
def delete_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    # Prevent self-delete
    if user_id == current_user.id:
        raise HTTPException(400, "You cannot delete your own account.")

    existing = safe_select("users", {"id": user_id}, single=True)
    if not existing:
        raise HTTPException(404, "User not found")

    email = existing["email"]

    client = get_supabase_client()

    try:
        result = (
            client.table("users")
            .delete(returning="representation")
            .eq("id", user_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not result.data:
        raise HTTPException(404, "User not found after deletion")

    return {"success": True, "data": {"email": email, "user_id": user_id}}


# -----------------------------------------------------
# 6️⃣ RESEND PASSWORD SETUP EMAIL
# -----------------------------------------------------
@router.post(
    "/users/{user_id}/resend-password",
    summary="Admin: Resend password setup email"
)
def resend_password_setup(user_id: str):

    existing = safe_select("users", {"id": user_id}, single=True)
    if not existing:
        raise HTTPException(404, "User not found")

    email = existing["email"]
    token = generate_password_setup_token(email)

    try:
        send_password_setup_email(email, token)
    except Exception as e:
        raise HTTPException(500, f"Failed sending email: {e}")

    return {
        "success": True,
        "data": {"email": email},
        "debug_token": token
    }
