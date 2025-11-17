# routers/admin.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

from core.permission_helpers import requires_permission
from core.permissions import ROLE_PERMISSIONS

from core.supabase_client import get_supabase_client


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(requires_permission("users:write"))],
)


# -----------------------------------------------------
# Allowed System Roles
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
# Helper: Prevent dangerous role changes
# (now uses Supabase Auth user list)
# -----------------------------------------------------
def validate_role_change(requestor: CurrentUser, desired_role: str):
    if desired_role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role: {desired_role}")

    client = get_supabase_client()

    # List super admins from Supabase auth
    try:
        users = client.auth.admin.list_users()
    except Exception as e:
        raise HTTPException(500, f"Error reading Supabase users: {e}")

    super_admin_ids = [
        u.id for u in users.users
        if (u.user_metadata or {}).get("role") == "super_admin"
    ]

    # Cannot assign admin/super_admin unless YOU are super_admin
    if desired_role in ("admin", "super_admin") and requestor.role != "super_admin":
        raise HTTPException(
            403,
            "Only a super_admin may assign admin or super_admin roles."
        )

    # Prevent demoting last super_admin
    if desired_role != "super_admin" and requestor.id in super_admin_ids and len(super_admin_ids) == 1:
        raise HTTPException(400, "Cannot demote the last remaining super_admin.")


# -----------------------------------------------------
# Prevent deleting last super_admin
# -----------------------------------------------------
def prevent_deleting_last_super_admin(user_id: str):
    client = get_supabase_client()

    try:
        users = client.auth.admin.list_users()
    except Exception as e:
        raise HTTPException(500, f"Supabase read error: {e}")

    super_admin_ids = [
        u.id for u in users.users
        if (u.user_metadata or {}).get("role") == "super_admin"
    ]

    if user_id in super_admin_ids and len(super_admin_ids) == 1:
        raise HTTPException(400, "Cannot delete the last remaining super_admin.")


# -----------------------------------------------------
# 1️⃣ CREATE USER (Supabase Auth)
# -----------------------------------------------------
@router.post(
    "/create-account",
    summary="Admin: Create user account",
    dependencies=[Depends(requires_permission("users:create"))],
)
def admin_create_account(
    payload: AdminCreateUser,
    current_user: CurrentUser = Depends(get_current_user),
):
    validate_role_change(current_user, payload.role)

    client = get_supabase_client()

    metadata = {
        "full_name": payload.full_name,
        "organization_name": payload.organization_name,
        "phone": payload.phone,
        "role": payload.role,
        "contractor_id": None,
    }

    # Create user in Supabase Auth
    try:
        user_resp = client.auth.admin.create_user(
            {
                "email": payload.email,
                "email_confirm": True,
                "user_metadata": metadata,
            }
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase user creation failed: {e}")

    # Send invite (password setup)
    try:
        client.auth.admin.invite_user_by_email(payload.email)
    except Exception as e:
        raise HTTPException(500, f"Failed to send Supabase invite email: {e}")

    return {
        "success": True,
        "data": {
            "user_id": user_resp.user.id,
            "email": payload.email,
        },
    }


# -----------------------------------------------------
# 2️⃣ LIST USERS (Supabase Auth)
# -----------------------------------------------------
@router.get(
    "/users",
    summary="Admin: List users",
    dependencies=[Depends(requires_permission("users:read"))],
)
def list_users(role: str | None = None):
    client = get_supabase_client()

    try:
        users = client.auth.admin.list_users()
    except Exception as e:
        raise HTTPException(500, f"Supabase list users failed: {e}")

    # Filter by role in metadata
    filtered = []
    for u in users.users:
        meta = u.user_metadata or {}
        if role is None or meta.get("role") == role:
            filtered.append({
                "id": u.id,
                "email": u.email,
                "full_name": meta.get("full_name"),
                "organization_name": meta.get("organization_name"),
                "phone": meta.get("phone"),
                "role": meta.get("role"),
                "contractor_id": meta.get("contractor_id"),
            })

    # Sort by creation date descending
    filtered.sort(key=lambda u: u.get("created_at", ""), reverse=True)

    return {"success": True, "data": filtered}


# -----------------------------------------------------
# 3️⃣ GET ONE USER
# -----------------------------------------------------
@router.get(
    "/users/{user_id}",
    summary="Admin: Get one user",
    dependencies=[Depends(requires_permission("users:read"))],
)
def get_user(user_id: str):
    client = get_supabase_client()

    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
    except Exception as e:
        raise HTTPException(500, f"Supabase read error: {e}")

    if not user_resp.user:
        raise HTTPException(404, "User not found")

    u = user_resp.user
    meta = u.user_metadata or {}

    return {
        "success": True,
        "data": {
            "id": u.id,
            "email": u.email,
            "full_name": meta.get("full_name"),
            "organization_name": meta.get("organization_name"),
            "phone": meta.get("phone"),
            "role": meta.get("role"),
            "contractor_id": meta.get("contractor_id"),
        },
    }


# -----------------------------------------------------
# 4️⃣ UPDATE USER (Supabase Auth)
# -----------------------------------------------------
@router.patch(
    "/users/{user_id}",
    summary="Admin: Update user",
    dependencies=[Depends(requires_permission("users:update"))],
)
def update_user(
    user_id: str,
    payload: AdminUpdateUser,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    update_meta = {k: v for k, v in payload.model_dump().items() if v is not None}

    if not update_meta:
        raise HTTPException(400, "No valid fields to update")

    if "role" in update_meta:
        validate_role_change(current_user, update_meta["role"])

    try:
        user_resp = client.auth.admin.update_user_by_id(
            user_id,
            {
                "user_metadata": update_meta,
            },
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    return {"success": True, "data": update_meta}


# -----------------------------------------------------
# 5️⃣ DELETE USER (Supabase Auth)
# -----------------------------------------------------
@router.delete(
    "/users/{user_id}",
    summary="Admin: Delete user",
    dependencies=[Depends(requires_permission("users:delete"))],
)
def delete_user(
    user_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):

    if user_id == current_user.id:
        raise HTTPException(400, "You cannot delete your own account.")

    prevent_deleting_last_super_admin(user_id)

    client = get_supabase_client()

    try:
        client.auth.admin.delete_user(user_id)
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    return {"success": True, "data": {"user_id": user_id}}


# -----------------------------------------------------
# 6️⃣ RESEND PASSWORD SETUP (Supabase)
# -----------------------------------------------------
@router.post(
    "/users/{user_id}/resend-password",
    summary="Admin: Resend password setup email",
    dependencies=[Depends(requires_permission("users:update"))],
)
def resend_password_setup(user_id: str):
    client = get_supabase_client()

    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
    except Exception:
        raise HTTPException(404, "User not found")

    email = user_resp.user.email

    try:
        client.auth.admin.invite_user_by_email(email)
    except Exception as e:
        raise HTTPException(500, f"Error sending invite email: {e}")

    return {"success": True, "data": {"email": email}}
