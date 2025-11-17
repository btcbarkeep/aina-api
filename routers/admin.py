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
    permissions: Optional[List[str]] = None


class AdminUpdateUser(BaseModel):
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None


# -----------------------------------------------------
# Normalize Supabase list_users() result
# -----------------------------------------------------
def extract_user_list(result):
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "users" in result:
        return result["users"]
    users_attr = getattr(result, "users", None)
    if users_attr is not None:
        return users_attr
    return []


# -----------------------------------------------------
# Helper: Validate role change
# -----------------------------------------------------
def validate_role_change(
    requestor: CurrentUser,
    desired_role: str,
    target_user_id: Optional[str] = None,
):
    """
    requestor = the person making the request
    desired_role = the role being assigned
    target_user_id = None → user creation (no demotion check)
    target_user_id != None → editing existing user
    """

    if desired_role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role: {desired_role}")

    client = get_supabase_client()

    try:
        raw = client.auth.admin.list_users()
        all_users = extract_user_list(raw)
    except Exception as e:
        raise HTTPException(500, f"Error reading Supabase users: {e}")

    # Who are current super_admins?
    super_admin_ids = [
        u.id
        for u in all_users
        if (u.user_metadata or {}).get("role") == "super_admin"
    ]

    # -------------------------------------------------
    # 1) ONLY super_admin may assign admin/super_admin roles
    # -------------------------------------------------
    if desired_role in ("admin", "super_admin") and requestor.role != "super_admin":
        raise HTTPException(
            403, "Only a super_admin may assign admin or super_admin roles."
        )

    # -------------------------------------------------
    # 2) DEMOTION CHECK — ONLY for updating existing users
    # -------------------------------------------------
    if target_user_id is not None:
        # Find target user's current role
        target_user = next((u for u in all_users if u.id == target_user_id), None)

        if not target_user:
            raise HTTPException(404, "Target user not found")

        target_role = (target_user.user_metadata or {}).get("role", "hoa")

        # If target is a super_admin and we try to change them to any other role
        if (
            target_role == "super_admin"
            and desired_role != "super_admin"
            and len(super_admin_ids) == 1
        ):
            raise HTTPException(400, "Cannot demote the last remaining super_admin.")

    # If creating a new user — no demotion logic applies.
    return


# -----------------------------------------------------
# Prevent deleting last super_admin
# -----------------------------------------------------
def prevent_deleting_last_super_admin(user_id: str):
    client = get_supabase_client()

    try:
        raw = client.auth.admin.list_users()
        all_users = extract_user_list(raw)
    except Exception as e:
        raise HTTPException(500, f"Supabase read error: {e}")

    super_admin_ids = [
        u.id
        for u in all_users
        if (u.user_metadata or {}).get("role") == "super_admin"
    ]

    if user_id in super_admin_ids and len(super_admin_ids) == 1:
        raise HTTPException(400, "Cannot delete the last remaining super_admin.")


# -----------------------------------------------------
# 1️⃣ CREATE USER (FIXED)
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
        "permissions": payload.permissions or [],
    }

    # 1️⃣ Create the user
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

    # 2️⃣ Send invite (unless user exists)
    try:
        client.auth.admin.invite_user_by_email(payload.email)

    except Exception as e:
        msg = str(e).lower()
        if "already been registered" in msg or "already registered" in msg:
            # Safe to ignore
            pass
        else:
            raise HTTPException(500, f"Failed to send invite email: {e}")

    return {
        "success": True,
        "data": {
            "user_id": user_resp.user.id,
            "email": payload.email,
        },
    }


# -----------------------------------------------------
# 2️⃣ LIST USERS
# -----------------------------------------------------
@router.get(
    "/users",
    summary="Admin: List users",
    dependencies=[Depends(requires_permission("users:read"))],
)
def list_users(role: str | None = None):
    client = get_supabase_client()

    if role and role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role filter: {role}")

    try:
        raw = client.auth.admin.list_users()
        users = extract_user_list(raw)
    except Exception as e:
        raise HTTPException(500, f"Supabase list users failed: {e}")

    results = []
    for u in users:
        meta = u.user_metadata or {}
        u_role = meta.get("role", "hoa")
        u_permissions = meta.get("permissions", [])

        if role is None or u_role == role:
            results.append({
                "id": u.id,
                "email": u.email,
                "full_name": meta.get("full_name"),
                "organization_name": meta.get("organization_name"),
                "phone": meta.get("phone"),
                "role": u_role,
                "contractor_id": meta.get("contractor_id"),
                "permissions": u_permissions,
                "created_at": getattr(u, "created_at", None),
            })

    results.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return {"success": True, "data": results}


# -----------------------------------------------------
# 3️⃣ GET USER
# -----------------------------------------------------
@router.get(
    "/users/{user_id}",
    summary="Admin: Get user",
    dependencies=[Depends(requires_permission("users:read"))],
)
def get_user(user_id: str):
    client = get_supabase_client()

    try:
        resp = client.auth.admin.get_user_by_id(user_id)
    except Exception as e:
        raise HTTPException(500, f"Supabase read error: {e}")

    if not resp.user:
        raise HTTPException(404, "User not found")

    u = resp.user
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
# 4️⃣ UPDATE USER (uses new demotion logic)
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

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields provided to update.")

    try:
        resp = client.auth.admin.get_user_by_id(user_id)
    except Exception as e:
        raise HTTPException(500, f"Supabase read error: {e}")

    if not resp.user:
        raise HTTPException(404, "User not found")

    current_meta = resp.user.user_metadata or {}

    new_role = updates.get("role", current_meta.get("role", "hoa"))

    # NEW: Validate demotion properly for existing users
    validate_role_change(current_user, new_role, target_user_id=user_id)

    merged = {**current_meta, **updates, "role": new_role}

    try:
        client.auth.admin.update_user_by_id(
            user_id,
            {"user_metadata": merged}
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    return {"success": True, "data": merged}


# -----------------------------------------------------
# 5️⃣ DELETE USER
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
# 6️⃣ RESEND PASSWORD SETUP
# -----------------------------------------------------
@router.post(
    "/users/{user_id}/resend-password",
    summary="Admin: Resend password setup email",
    dependencies=[Depends(requires_permission("users:update"))],
)
def resend_password_setup(user_id: str):
    client = get_supabase_client()

    try:
        resp = client.auth.admin.get_user_by_id(user_id)
    except Exception:
        raise HTTPException(404, "User not found")

    email = resp.user.email

    try:
        client.auth.admin.invite_user_by_email(email)
    except Exception as e:
        raise HTTPException(500, f"Error sending invite email: {e}")

    return {"success": True, "data": {"email": email}}
