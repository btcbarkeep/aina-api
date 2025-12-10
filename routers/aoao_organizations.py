# routers/aoao_organizations.py

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel
import os
import tempfile
from pathlib import Path as PathLib
from datetime import datetime
import uuid

from dependencies.auth import get_current_user, CurrentUser, requires_permission
from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.logging_config import logger
from core.errors import handle_supabase_error
from core.s3_client import get_s3
from models.aoao_organization import (
    AOAOOrganizationCreate,
    AOAOOrganizationUpdate,
    AOAOOrganizationRead
)
from models.enums import SubscriptionTier, SubscriptionStatus
from core.stripe_helpers import verify_contractor_subscription

router = APIRouter(
    prefix="/aoao-organizations",
    tags=["AOAO Organizations"],
)


# ============================================================
# Helper — role-based access rules
# ============================================================
def ensure_aoao_org_access(current_user: CurrentUser, organization_id: str):
    """
    Admin, super_admin → full access
    AOAO user → only access their own organization
    """
    if current_user.role in ["admin", "super_admin"]:
        return
    
    if current_user.role == "aoao":
        user_org_id = getattr(current_user, "aoao_organization_id", None)
        if user_org_id == organization_id:
            return
    
    raise HTTPException(403, "Insufficient permissions")


# ============================================================
# LIST AOAO ORGANIZATIONS
# ============================================================
@router.get("", response_model=List[AOAOOrganizationRead])
def list_aoao_organizations(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of organizations to return (1-1000)"),
    search: Optional[str] = Query(None, description="Search organizations by name (case-insensitive)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    List all AOAO organizations.
    
    Admin only.
    """
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admins can list AOAO organizations")
    
    client = get_supabase_client()
    query = client.table("aoao_organizations").select("*")
    
    if search:
        query = query.ilike("organization_name", f"%{search}%")
    
    query = query.order("organization_name").limit(limit)
    result = query.execute()
    
    return result.data or []


# ============================================================
# GET AOAO ORGANIZATION
# ============================================================
@router.get("/{organization_id}", response_model=AOAOOrganizationRead)
def get_aoao_organization(
    organization_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get a specific AOAO organization.
    
    Admin only, or users linked to this organization.
    """
    client = get_supabase_client()
    
    ensure_aoao_org_access(current_user, organization_id)
    
    rows = (
        client.table("aoao_organizations")
        .select("*")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    ).data
    
    if not rows:
        raise HTTPException(404, "AOAO organization not found")
    
    return rows[0]


# ============================================================
# CREATE AOAO ORGANIZATION
# ============================================================
@router.post(
    "",
    response_model=AOAOOrganizationRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def create_aoao_organization(payload: AOAOOrganizationCreate):
    """
    Create a new AOAO organization.
    
    Admin only.
    """
    client = get_supabase_client()
    
    # Check for duplicate organization name (case-insensitive)
    org_name = payload.organization_name.strip()
    existing = (
        client.table("aoao_organizations")
        .select("id, organization_name")
        .ilike("organization_name", org_name)
        .limit(1)
        .execute()
    )
    
    if existing.data:
        raise HTTPException(
            400,
            f"AOAO organization with name '{org_name}' already exists. Organization names must be unique."
        )
    
    # Prepare data
    data = sanitize(payload.model_dump())
    
    # Convert enum fields to strings for database
    if "subscription_tier" in data and data["subscription_tier"]:
        data["subscription_tier"] = str(data["subscription_tier"])
    if "subscription_status" in data and data["subscription_status"]:
        data["subscription_status"] = str(data["subscription_status"])
    
    try:
        insert_res = client.table("aoao_organizations").insert(data).execute()
        if not insert_res.data:
            raise HTTPException(500, "Failed to create AOAO organization")
        return insert_res.data[0]
    except Exception as e:
        handle_supabase_error(e, "Failed to create AOAO organization")


# ============================================================
# UPDATE AOAO ORGANIZATION
# ============================================================
@router.patch(
    "/{organization_id}",
    response_model=AOAOOrganizationRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_aoao_organization(
    organization_id: str,
    payload: AOAOOrganizationUpdate
):
    """
    Update an AOAO organization.
    
    Admin only.
    """
    client = get_supabase_client()
    
    # Check if organization exists
    existing = (
        client.table("aoao_organizations")
        .select("id")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    
    if not existing.data:
        raise HTTPException(404, "AOAO organization not found")
    
    # Check for duplicate name if updating
    if payload.organization_name:
        org_name = payload.organization_name.strip()
        duplicate = (
            client.table("aoao_organizations")
            .select("id, organization_name")
            .ilike("organization_name", org_name)
            .neq("id", organization_id)
            .limit(1)
            .execute()
        )
        
        if duplicate.data:
            raise HTTPException(
                400,
                f"AOAO organization with name '{org_name}' already exists."
            )
    
    # Prepare update data
    updates = sanitize(payload.model_dump(exclude_unset=True))
    
    # Convert enum fields to strings
    if "subscription_tier" in updates and updates["subscription_tier"]:
        updates["subscription_tier"] = str(updates["subscription_tier"])
    if "subscription_status" in updates and updates["subscription_status"]:
        updates["subscription_status"] = str(updates["subscription_status"])
    
    if not updates:
        raise HTTPException(400, "No fields provided to update")
    
    try:
        update_res = (
            client.table("aoao_organizations")
            .update(updates)
            .eq("id", organization_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update AOAO organization")
        
        return update_res.data[0]
    except Exception as e:
        handle_supabase_error(e, "Failed to update AOAO organization")


# ============================================================
# DELETE AOAO ORGANIZATION
# ============================================================
@router.delete(
    "/{organization_id}",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def delete_aoao_organization(organization_id: str):
    """
    Delete an AOAO organization.
    
    Admin only.
    """
    client = get_supabase_client()
    
    try:
        result = (
            client.table("aoao_organizations")
            .delete()
            .eq("id", organization_id)
            .execute()
        )
        
        return {"success": True, "message": "AOAO organization deleted"}
    except Exception as e:
        handle_supabase_error(e, "Failed to delete AOAO organization")


# ============================================================
# SYNC SUBSCRIPTION STATUS FROM STRIPE
# ============================================================
@router.post(
    "/{organization_id}/sync-subscription",
    summary="Sync subscription status from Stripe",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def sync_aoao_org_subscription(
    organization_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Manually sync an AOAO organization's subscription status from Stripe.
    
    This endpoint:
    - Verifies the subscription status with Stripe
    - Updates the organization's subscription record
    - Returns the updated subscription data
    
    **Use cases:**
    - Manual sync when subscription changes
    - Troubleshooting subscription issues
    - Verifying subscription status after webhook delays
    """
    ensure_aoao_org_access(current_user, organization_id)
    
    client = get_supabase_client()
    
    # Get organization
    org_res = (
        client.table("aoao_organizations")
        .select("id, organization_name, stripe_customer_id, stripe_subscription_id, subscription_tier, subscription_status")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    
    if not org_res.data:
        raise HTTPException(404, "AOAO organization not found")
    
    org = org_res.data[0]
    stripe_customer_id = org.get("stripe_customer_id")
    stripe_subscription_id = org.get("stripe_subscription_id")
    
    if not stripe_customer_id and not stripe_subscription_id:
        raise HTTPException(
            400,
            "AOAO organization does not have a Stripe customer ID or subscription ID. Cannot sync subscription."
        )
    
    # Verify subscription with Stripe
    is_active, subscription_status, error_message = verify_contractor_subscription(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id
    )
    
    if error_message:
        logger.warning(f"Error syncing subscription for AOAO organization {organization_id}: {error_message}")
        raise HTTPException(400, f"Failed to verify subscription: {error_message}")
    
    # Determine subscription tier
    subscription_tier = "paid" if is_active else "free"
    
    # Update organization
    try:
        update_res = (
            client.table("aoao_organizations")
            .update({
                "subscription_tier": subscription_tier,
                "subscription_status": subscription_status
            })
            .eq("id", organization_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update AOAO organization subscription")
        
        logger.info(f"Synced subscription status for AOAO organization {organization_id}: tier={subscription_tier}, status={subscription_status}")
        
        return {
            "success": True,
            "organization_id": organization_id,
            "organization_name": org.get("organization_name"),
            "subscription_tier": subscription_tier,
            "subscription_status": subscription_status
        }
    except Exception as e:
        from core.errors import handle_supabase_error
        raise handle_supabase_error(e, "Failed to sync subscription status", 500)



# ============================================================
# UPLOAD AOAO ORGANIZATION LOGO
# ============================================================
class LogoUploadResponse(BaseModel):
    success: bool
    logo_url: str
    s3_key: str
    message: str


@router.post(
    "/{organization_id}/logo",
    summary="Upload AOAO organization logo",
    description="Upload a logo image for an AOAO organization. Supported formats: JPG, PNG, GIF, WebP. Max file size: 5MB.",
    response_model=LogoUploadResponse,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
async def upload_aoao_org_logo(
    organization_id: str,
    file: UploadFile = File(...),
    update_organization: bool = Form(True, description="Automatically update organization's logo_url field"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload a logo image for an AOAO organization.
    
    The image is uploaded to S3 and optionally updates the organization's logo_url field.
    """
    # Check access
    ensure_aoao_org_access(current_user, organization_id)
    
    # Validate organization exists
    client = get_supabase_client()
    org_check = (
        client.table("aoao_organizations")
        .select("id, organization_name")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    
    if not org_check.data:
        raise HTTPException(404, f"AOAO organization '{organization_id}' not found")
    
    # Validate file type
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    file_extension = PathLib(file.filename or "").suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            400,
            f"Invalid file type. Allowed formats: {', '.join(allowed_extensions)}"
        )
    
    # Validate file size (5MB max)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File size exceeds maximum of {MAX_FILE_SIZE / 1024 / 1024}MB")
    
    # Get S3 client
    try:
        s3, bucket, region = get_s3()
    except RuntimeError as e:
        logger.error(f"S3 configuration error: {e}")
        raise HTTPException(500, "File storage not configured")
    
    # Generate S3 key
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    safe_org_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in org_check.data[0]["organization_name"])[:50]
    s3_key = f"aoao-organizations/logos/{organization_id}/{safe_org_name}_{timestamp}_{unique_id}{file_extension}"
    
    # Upload to S3
    temp_file_path = None
    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file_path = temp_file.name
            temp_file.write(content)
            temp_file.flush()
        
        # Upload to S3 with public-read ACL for permanent access
        try:
            content_type = file.content_type or "image/jpeg"
            s3.upload_file(
                Filename=temp_file_path,
                Bucket=bucket,
                Key=s3_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ACL": "public-read"  # Make logo publicly accessible
                },
            )
            logger.info(f"Uploaded AOAO organization logo to S3: {s3_key}")
        except Exception as e:
            logger.error(f"S3 upload error: {e}")
            raise HTTPException(500, f"Failed to upload logo: {e}")
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_file_path}: {e}")
    
    # Generate permanent public URL (no expiration)
    try:
        # Public URL format: https://{bucket}.s3.{region}.amazonaws.com/{key}
        if region == "us-east-1":
            # us-east-1 uses a different URL format
            logo_url = f"https://{bucket}.s3.amazonaws.com/{s3_key}"
        else:
            logo_url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
    except Exception as e:
        logger.error(f"Failed to generate public URL: {e}")
        raise HTTPException(500, "Failed to generate logo URL")
    
    # Optionally update organization's logo_url field
    if update_organization:
        try:
            client.table("aoao_organizations").update({
                "logo_url": logo_url
            }).eq("id", organization_id).execute()
            logger.info(f"Updated AOAO organization {organization_id} logo_url")
        except Exception as e:
            logger.warning(f"Failed to update organization logo_url: {e}")
            # Don't fail the request if update fails - logo is still uploaded
    
    return {
        "success": True,
        "logo_url": logo_url,
        "s3_key": s3_key,
        "message": "Logo uploaded successfully" + (" and organization updated" if update_organization else "")
    }
