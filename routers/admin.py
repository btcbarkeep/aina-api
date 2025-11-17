# routers/admin.py

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

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
)


# -----------------------------------------------------
# Allowed System Roles
# -----------------------------------------------------
ALLOWED_ROLES = list(ROLE_PERMISSIONS.keys())


# -----------------------------------------------------
# Payloads
# -----------------------------------------------------
class AdminCreateUser(BaseModel):
    full_name: Optional[str] = None
    email: EmailStr
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "hoa"
    # ⭐ NEW — optional per-user overrides at create time
    permissions: Optional[List[str]] = None


class AdminUpdateUser(BaseModel):
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    # ⭐ NEW — optional per-user overrides at update time
    permissions: Optional[List[str]] = None


# -----------------------------------------------------
# Helper: Prevent dangerous role changes
# (uses Supabase Auth users)
# -----------------------------------------------------
def validate_role_change(requestor: CurrentUser, desired_role: str):
    if desired_role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role: {desired_role}")

    client = get_supabase_client()

    # List super_admins from Supabase Auth
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

    # Prevent demoting the last super_admin
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
        # ⭐ include per-user overrides if provided
        "permissions": payload.permissions or [],
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

    if role is not None and role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role filter: {role}")

    try:
        users = client.auth.admin.list_users()
    except Exception as e:
        raise HTTPException(500, f"Supabase list users failed: {e}")

    filtered = []
    for u in users.users or []:
        meta = u.user_metadata or {}
        u_role = meta.get("role", "hoa")
        u_perms = meta.get("permissions", [])

        if role is None or u_role == role:
            filtered.append({
                "id": u.id,
                "email": u.email,
                "full_name": meta.get("full_name"),
                "organization_name": meta.get("organization_name"),
                "phone": meta.get("phone"),
                "role": u_role,
                "contractor_id": meta.get("contractor_id"),
                "permissions": u_perms,
                "created_at": getattr(u, "created_at", None),
            })

    # Sort by Supabase creation date desc (if available)
    filtered.sort(key=lambda u: u.get("created_at") or "", reverse=True)

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
            "permissions": meta.get("permissions", []),
            "created_at": getattr(u, "created_at", None),
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

    # Only keep fields that were actually provided
    update_meta = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_meta:
        raise HTTPException(400, "No valid fields to update")

    # Fetch existing metadata to MERGE instead of overwrite
    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
    except Exception as e:
        raise HTTPException(500, f"Supabase read error: {e}")

    if not user_resp.user:
        raise HTTPException(404, "User not found")

    existing_meta = user_resp.user.user_metadata or {}

    # If role is changing, validate it
    new_role = update_meta.get("role", existing_meta.get("role", "hoa"))
    validate_role_change(current_user, new_role)

    # Merge metadata (existing + updates)
    merged_meta = {**existing_meta, **update_meta}
    merged_meta["role"] = new_role  # ensure final role is set

    try:
        client.auth.admin.update_user_by_id(
            user_id,
            {
                "user_metadata": merged_meta,
            },
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    return {"success": True, "data": merged_meta}


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
