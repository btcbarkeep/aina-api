# routers/admin.py

from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from dependencies.auth import (
    get_current_user,
    CurrentUser,
)

from core.permission_helpers import requires_permission
from core.permissions import ROLE_PERMISSIONS
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from models.user_create import AdminCreateUser


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
# Note: AdminCreateUser is imported from models.user_create (see imports above)
# If you need to modify it, update models/user_create.py instead


class AdminUpdateUser(BaseModel):
    full_name: Optional[str] = None
    organization_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[List[str]] = None
    contractor_id: Optional[str] = None
    aoao_organization_id: Optional[str] = None
    pm_company_id: Optional[str] = None


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
    if desired_role not in ALLOWED_ROLES:
        raise HTTPException(400, f"Invalid role: {desired_role}")

    client = get_supabase_client()

    try:
        raw = client.auth.admin.list_users()
        all_users = extract_user_list(raw)
    except Exception as e:
        raise HTTPException(500, f"Error reading Supabase users: {e}")

    super_admin_ids = [
        u.id for u in all_users if (u.user_metadata or {}).get("role") == "super_admin"
    ]

    # Only super_admin can assign admin or super_admin
    if desired_role in ("admin", "super_admin") and requestor.role != "super_admin":
        raise HTTPException(
            403, "Only a super_admin may assign admin or super_admin roles."
        )

    # Check demotion of super_admin
    if target_user_id is not None:
        target_user = next((u for u in all_users if u.id == target_user_id), None)

        if not target_user:
            raise HTTPException(404, "Target user not found")

        target_role = (target_user.user_metadata or {}).get("role", "aoao")

        if (
            target_role == "super_admin"
            and desired_role != "super_admin"
            and len(super_admin_ids) == 1
        ):
            raise HTTPException(400, "Cannot demote the last remaining super_admin.")

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
        u.id for u in all_users if (u.user_metadata or {}).get("role") == "super_admin"
    ]

    if user_id in super_admin_ids and len(super_admin_ids) == 1:
        raise HTTPException(400, "Cannot delete the last remaining super_admin.")


# -----------------------------------------------------
# 1️⃣ CREATE USER
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
    
    # Validate organization IDs exist if provided
    if payload.contractor_id:
        contractor_check = (
            client.table("contractors")
            .select("id")
            .eq("id", payload.contractor_id)
            .limit(1)
            .execute()
        )
        if not contractor_check.data:
            raise HTTPException(400, f"Contractor {payload.contractor_id} does not exist")
    
    if payload.aoao_organization_id:
        org_check = (
            client.table("aoao_organizations")
            .select("id")
            .eq("id", payload.aoao_organization_id)
            .limit(1)
            .execute()
        )
        if not org_check.data:
            raise HTTPException(400, f"AOAO organization {payload.aoao_organization_id} does not exist")
    
    if payload.pm_company_id:
        pm_check = (
            client.table("property_management_companies")
            .select("id")
            .eq("id", payload.pm_company_id)
            .limit(1)
            .execute()
        )
        if not pm_check.data:
            raise HTTPException(400, f"Property management company {payload.pm_company_id} does not exist")

    metadata = {
        "full_name": payload.full_name,
        "organization_name": payload.organization_name,
        "phone": payload.phone,
        "role": payload.role,
        "contractor_id": payload.contractor_id,
        "aoao_organization_id": payload.aoao_organization_id,
        "pm_company_id": payload.pm_company_id,
        "permissions": payload.permissions or [],
    }
    
    # Merge any additional metadata if provided
    if payload.metadata:
        metadata.update(payload.metadata)

    create_payload = {
        "email": payload.email,
        "email_confirm": False,
        "user_metadata": metadata,
    }

    try:
        user_resp = client.auth.admin.create_user(create_payload)
    except Exception as e:
        raise HTTPException(500, f"Supabase user creation failed: {e}")

    # RESP FIX: user_resp.user is an object, not dict
    new_user_id = getattr(user_resp.user, "id", None)

    # Invite
    try:
        client.auth.admin.invite_user_by_email(payload.email)
    except Exception as e:
        msg = str(e).lower()
        if "already registered" not in msg:
            raise HTTPException(500, f"Failed to send invite email: {e}")

    return {"success": True, "data": {"user_id": new_user_id, "email": payload.email}}



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
        u_role = meta.get("role", "aoao")

        if role is None or u_role == role:
            results.append({
                "id": u.id,
                "email": u.email,
                "full_name": meta.get("full_name"),
                "organization_name": meta.get("organization_name"),
                "phone": meta.get("phone"),
                "role": u_role,
                "contractor_id": meta.get("contractor_id"),
                "aoao_organization_id": meta.get("aoao_organization_id"),
                "pm_company_id": meta.get("pm_company_id"),
                "permissions": meta.get("permissions", []),
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
            "aoao_organization_id": meta.get("aoao_organization_id"),
            "pm_company_id": meta.get("pm_company_id"),
            "permissions": meta.get("permissions", []),
            "created_at": getattr(u, "created_at", None),
        },
    }


# -----------------------------------------------------
# 4️⃣ UPDATE USER (SAFE)
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

    new_role = updates.get("role", current_meta.get("role", "aoao"))

    validate_role_change(current_user, new_role, target_user_id=user_id)
    
    # Helper function to validate UUID format and filter out placeholders
    def is_valid_uuid(value: str) -> bool:
        """Check if a string is a valid UUID format (not a placeholder like 'string')."""
        if not value or value.lower() == "string":
            return False
        try:
            uuid.UUID(str(value))
            return True
        except (ValueError, AttributeError, TypeError):
            return False
    
    # Filter out placeholder values from organization IDs before validation
    if "contractor_id" in updates and updates["contractor_id"]:
        if not is_valid_uuid(updates["contractor_id"]):
            # Remove placeholder values like "string" from updates
            updates.pop("contractor_id")
        else:
            contractor_id = updates["contractor_id"]
            contractor_check = (
                client.table("contractors")
                .select("id")
                .eq("id", contractor_id)
                .limit(1)
                .execute()
            )
            if not contractor_check.data:
                raise HTTPException(400, f"Contractor {contractor_id} does not exist")
    
    if "aoao_organization_id" in updates and updates["aoao_organization_id"]:
        if not is_valid_uuid(updates["aoao_organization_id"]):
            # Remove placeholder values like "string" from updates
            updates.pop("aoao_organization_id")
        else:
            aoao_id = updates["aoao_organization_id"]
            org_check = (
                client.table("aoao_organizations")
                .select("id")
                .eq("id", aoao_id)
                .limit(1)
                .execute()
            )
            if not org_check.data:
                raise HTTPException(400, f"AOAO organization {aoao_id} does not exist")
    
    if "pm_company_id" in updates and updates["pm_company_id"]:
        pm_id = updates["pm_company_id"]
        if not is_valid_uuid(pm_id):
            raise HTTPException(400, f"Invalid pm_company_id format: {pm_id}. Must be a valid UUID.")
        pm_check = (
            client.table("property_management_companies")
            .select("id")
            .eq("id", pm_id)
            .limit(1)
            .execute()
        )
        if not pm_check.data:
            raise HTTPException(400, f"Property management company {pm_id} does not exist")

    # Build merged metadata: start with current, then apply updates
    # Ensure we have a dict to work with (current_meta might be None)
    merged = dict(current_meta) if current_meta else {}
    
    # Apply updates (excluding organization IDs which are handled separately)
    for key, value in updates.items():
        if key not in ["contractor_id", "aoao_organization_id", "pm_company_id", "permissions"]:
            merged[key] = value
    
    # Handle organization IDs: only update if explicitly provided
    if "contractor_id" in updates:
        merged["contractor_id"] = updates["contractor_id"]
    if "aoao_organization_id" in updates:
        merged["aoao_organization_id"] = updates["aoao_organization_id"]
    if "pm_company_id" in updates:
        merged["pm_company_id"] = updates["pm_company_id"]
    
    # Handle permissions: only update if explicitly provided
    if "permissions" in updates:
        merged["permissions"] = updates["permissions"]
    elif "permissions" not in merged:
        merged["permissions"] = []
    
    # Always set role
    merged["role"] = new_role

    try:
        # Log what we're about to send for debugging
        logger.info(f"Updating user {user_id} with metadata: {merged}")
        client.auth.admin.update_user_by_id(
            user_id,
            {"user_metadata": merged}
        )
    except Exception as e:
        error_msg = str(e)
        # Log the full error for debugging
        logger.error(f"Failed to update user {user_id}: {error_msg}. Metadata being sent: {merged}")
        raise HTTPException(500, f"Supabase update error: {error_msg}")

    return {"success": True, "data": merged}


# -----------------------------------------------------
# 5️⃣ DELETE USER — SAFE
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

    # DELETE building access rows FIRST
    try:
        client.table("user_building_access").delete().eq("user_id", user_id).execute()
    except Exception:
        pass

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
