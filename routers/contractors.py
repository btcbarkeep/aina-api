# routers/contractors.py

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import List, Optional
from pydantic import BaseModel, Field
import os
import tempfile
from pathlib import Path as PathLib
from datetime import datetime
import uuid

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.s3_client import get_s3
from core.logging_config import logger
from core.stripe_helpers import verify_contractor_subscription, get_subscription_tier_from_stripe
from models.enums import SubscriptionTier, SubscriptionStatus


router = APIRouter(
    prefix="/contractors",
    tags=["Contractors"],
)


# ============================================================
# Helper — role-based access rules (FIXED)
# ============================================================
def ensure_contractor_access(current_user: CurrentUser, contractor_id: str):
    """
    Admin, super_admin → full access
    Contractor → only access their own contractor_id
    """
    # Only admins bypass
    if current_user.role in ["admin", "super_admin"]:
        return

    # Contractors can only access their own record
    if (
        current_user.role == "contractor"
        and getattr(current_user, "contractor_id", None) == contractor_id
    ):
        return

    raise HTTPException(403, "Insufficient permissions")


# ============================================================
# Helper — Validate role names exist in contractor_roles table
# ============================================================
def validate_role_names(role_names: List[str]) -> List[str]:
    """Validate that all role names exist in contractor_roles table. Returns list of valid role names."""
    if not role_names:
        return []
    
    client = get_supabase_client()
    
    # Get all valid role names from contractor_roles table
    roles_result = (
        client.table("contractor_roles")
        .select("name")
        .execute()
    )
    
    valid_role_names = {row["name"].lower() for row in (roles_result.data or [])}
    
    # Validate each provided role name
    validated_roles = []
    for role_name in role_names:
        if not role_name or not isinstance(role_name, str):
            continue
        role_lower = role_name.lower()
        # Check if role exists (case-insensitive)
        if role_lower in valid_role_names:
            # Find the exact case from database
            for db_role in roles_result.data:
                if db_role["name"].lower() == role_lower:
                    validated_roles.append(db_role["name"])
                    break
        else:
            raise HTTPException(400, detail={"error": f"Invalid role: {role_name}"})
    
    # Remove duplicates while preserving order
    return list(dict.fromkeys(validated_roles))


# ============================================================
# Helper — Get role IDs for role names
# ============================================================
def get_role_ids(role_names: List[str]) -> List[str]:
    """Get role IDs for given role names."""
    if not role_names:
        return []
    
    client = get_supabase_client()
    
    # Get role IDs for the validated role names
    role_names_lower = [name.lower() for name in role_names]
    roles_result = (
        client.table("contractor_roles")
        .select("id, name")
        .execute()
    )
    
    role_id_map = {}
    for row in (roles_result.data or []):
        role_id_map[row["name"].lower()] = row["id"]
    
    role_ids = []
    for role_name in role_names:
        role_lower = role_name.lower()
        if role_lower in role_id_map:
            role_ids.append(role_id_map[role_lower])
    
    return role_ids


# ============================================================
# Helper — Get roles for a contractor
# ============================================================
def get_contractor_roles(contractor_id: str) -> List[str]:
    """Get list of role names for a contractor."""
    client = get_supabase_client()
    
    # Join contractor_role_assignments → contractor_roles
    result = (
        client.table("contractor_role_assignments")
        .select("role_id, contractor_roles(name)")
        .eq("contractor_id", contractor_id)
        .execute()
    )
    
    roles = []
    if result.data:
        for row in result.data:
            if row.get("contractor_roles") and row["contractor_roles"].get("name"):
                roles.append(row["contractor_roles"]["name"])
    
    return roles


# ============================================================
# Helper — Create role assignments
# ============================================================
def create_role_assignments(contractor_id: str, role_names: List[str]):
    """Create role assignments for a contractor."""
    if not role_names:
        return
    
    validated_roles = validate_role_names(role_names)
    role_ids = get_role_ids(validated_roles)
    
    if not role_ids:
        return
    
    client = get_supabase_client()
    
    # Insert role assignments
    for role_id in role_ids:
        try:
            client.table("contractor_role_assignments").insert({
                "contractor_id": contractor_id,
                "role_id": role_id
            }).execute()
        except Exception as e:
            # Ignore duplicate key errors (unique constraint)
            if "duplicate" not in str(e).lower():
                raise HTTPException(500, f"Failed to create role assignment: {e}")


# ============================================================
# Helper — Update role assignments (delete old, create new)
# ============================================================
def update_role_assignments(contractor_id: str, role_names: List[str]):
    """Update role assignments by deleting old ones and creating new ones."""
    client = get_supabase_client()
    
    # Delete existing role assignments
    client.table("contractor_role_assignments").delete().eq("contractor_id", contractor_id).execute()
    
    # Create new role assignments
    create_role_assignments(contractor_id, role_names)


# ============================================================
# Helper — Enrich contractor with roles
# Note: This router has its own get_contractor_roles function
# but we use the centralized enrich_contractor_with_roles for consistency
# ============================================================
from core.contractor_helpers import enrich_contractor_with_roles


# ============================================================
# Pydantic Models
# ============================================================
class ContractorBase(BaseModel):
    """
    Base contractor model matching the database schema.
    
    Required fields:
    - company_name
    
    Optional fields:
    - phone, email, website, license_number, insurance_info, address
    - city, state, zip_code (location details)
    - contact_person, contact_phone, contact_email (primary contact info)
    - notes (additional information)
    - logo_url (use POST /contractors/{id}/logo to upload)
    - subscription_tier: "free" or "paid" (defaults to "free")
    - stripe_customer_id: Stripe customer ID (for paid subscriptions)
    - stripe_subscription_id: Stripe subscription ID (for paid subscriptions)
    - subscription_status: Stripe subscription status (e.g., "active", "canceled")
    """
    company_name: str = Field(..., description="Company name (required)")
    phone: Optional[str] = Field(None, description="Company phone number")
    email: Optional[str] = Field(None, description="Company email address")
    website: Optional[str] = Field(None, description="Company website URL")
    license_number: Optional[str] = Field(None, description="Business license number")
    insurance_info: Optional[str] = Field(None, description="Insurance information")
    address: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State/Province")
    zip_code: Optional[str] = Field(None, description="ZIP/Postal code")
    contact_person: Optional[str] = Field(None, description="Primary contact person name")
    contact_phone: Optional[str] = Field(None, description="Primary contact phone number")
    contact_email: Optional[str] = Field(None, description="Primary contact email address")
    notes: Optional[str] = Field(None, description="Additional notes about the contractor")
    logo_url: Optional[str] = Field(None, description="URL to contractor logo (use POST /contractors/{id}/logo to upload)")
    subscription_tier: Optional[SubscriptionTier] = Field(SubscriptionTier.free, description="Subscription tier: 'free' or 'paid' (defaults to 'free')")
    stripe_customer_id: Optional[str] = Field(None, description="Stripe customer ID (for paid subscriptions)")
    stripe_subscription_id: Optional[str] = Field(None, description="Stripe subscription ID (for paid subscriptions)")
    subscription_status: Optional[SubscriptionStatus] = Field(None, description="Stripe subscription status (e.g., 'active', 'canceled', 'past_due')")


class ContractorCreate(ContractorBase):
    """Roles are required when creating a contractor."""
    roles: List[str] = Field(..., description="List of role names (e.g., ['plumber', 'electrician'])", example=["plumber"])
    
    class Config:
        json_schema_extra = {
            "example": {
                "company_name": "Burger's Plumbing",
                "phone": "(808) 555-1234",
                "email": "info@burgersplumbing.com",
                "website": "https://burgersplumbing.com",
                "license_number": "PL-12345",
                "insurance_info": "General Liability: $1M",
                "address": "123 Main St",
                "city": "Honolulu",
                "state": "HI",
                "zip_code": "96815",
                "contact_person": "John Burger",
                "contact_phone": "(808) 555-1234",
                "contact_email": "john@burgersplumbing.com",
                "notes": "Specializes in commercial plumbing",
                "roles": ["plumber"]
            }
        }


class ContractorRead(ContractorBase):
    id: str
    created_at: Optional[str] = None
    roles: List[str] = Field(default_factory=list, description="List of role names assigned to this contractor", example=["plumber", "inspector"])
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "company_name": "Burger's Plumbing",
                "roles": ["plumber", "inspector"]
            }
        }


class ContractorUpdate(BaseModel):
    """
    Update contractor model - all fields optional.
    Update only the fields you want to change.
    """
    company_name: Optional[str] = Field(None, description="Company name")
    phone: Optional[str] = Field(None, description="Company phone number")
    email: Optional[str] = Field(None, description="Company email address")
    website: Optional[str] = Field(None, description="Company website URL")
    license_number: Optional[str] = Field(None, description="Business license number")
    insurance_info: Optional[str] = Field(None, description="Insurance information")
    address: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State/Province")
    zip_code: Optional[str] = Field(None, description="ZIP/Postal code")
    contact_person: Optional[str] = Field(None, description="Primary contact person name")
    contact_phone: Optional[str] = Field(None, description="Primary contact phone number")
    contact_email: Optional[str] = Field(None, description="Primary contact email address")
    notes: Optional[str] = Field(None, description="Additional notes about the contractor")
    logo_url: Optional[str] = Field(None, description="URL to contractor logo (use POST /contractors/{id}/logo to upload)")
    roles: Optional[List[str]] = Field(None, description="List of role names to assign (replaces existing roles)", example=["plumber", "electrician"])
    subscription_tier: Optional[SubscriptionTier] = Field(None, description="Subscription tier: 'free' or 'paid'")
    stripe_customer_id: Optional[str] = Field(None, description="Stripe customer ID (for paid subscriptions)")
    stripe_subscription_id: Optional[str] = Field(None, description="Stripe subscription ID (for paid subscriptions)")
    subscription_status: Optional[SubscriptionStatus] = Field(None, description="Stripe subscription status (e.g., 'active', 'canceled', 'past_due')")


class LogoUploadResponse(BaseModel):
    success: bool
    logo_url: str
    s3_key: str
    message: str


# ============================================================
# Helper — Apply contractor filters
# ============================================================
def apply_contractor_filters(query, params: dict):
    """Apply filtering to contractors query based on provided parameters."""
    client = get_supabase_client()
    
    # role filter (via contractor_role_assignments junction table)
    if params.get("role"):
        # Validate role exists in contractor_roles table
        role_result = (
            client.table("contractor_roles")
            .select("id, name")
            .ilike("name", params["role"])
            .limit(1)
            .execute()
        )
        
        if not role_result.data:
            raise HTTPException(400, detail={"error": "Invalid role filter"})
        
        role_id = role_result.data[0]["id"]
        
        # Get contractor IDs that have this role
        assignments_result = (
            client.table("contractor_role_assignments")
            .select("contractor_id")
            .eq("role_id", role_id)
            .execute()
        )
        
        contractor_ids = [row["contractor_id"] for row in (assignments_result.data or [])]
        
        if contractor_ids:
            query = query.in_("id", contractor_ids)
        else:
            # No contractors match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # building_id filter (via event_contractors → events)
    if params.get("building_id"):
        # First get all events in this building
        events_result = (
            client.table("events")
            .select("id")
            .eq("building_id", params["building_id"])
            .execute()
        )
        event_ids = [row["id"] for row in (events_result.data or [])]
        
        if event_ids:
            # Get contractor IDs from these events
            event_contractors_result = (
                client.table("event_contractors")
                .select("contractor_id")
                .in_("event_id", event_ids)
                .execute()
            )
            contractor_ids = list(set([row["contractor_id"] for row in (event_contractors_result.data or [])]))
            if contractor_ids:
                query = query.in_("id", contractor_ids)
            else:
                # No contractors match, return empty result
                query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
        else:
            # No events match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # unit_id filter (via event_contractors → events → event_units)
    if params.get("unit_id"):
        # Get contractor IDs from events that have this unit
        # First get event IDs with this unit
        event_units_result = (
            client.table("event_units")
            .select("event_id")
            .eq("unit_id", params["unit_id"])
            .execute()
        )
        event_ids = [row["event_id"] for row in (event_units_result.data or [])]
        
        if event_ids:
            # Get contractor IDs from these events
            event_contractors_result = (
                client.table("event_contractors")
                .select("contractor_id")
                .in_("event_id", event_ids)
                .execute()
            )
            contractor_ids = list(set([row["contractor_id"] for row in (event_contractors_result.data or [])]))
            if contractor_ids:
                query = query.in_("id", contractor_ids)
            else:
                # No contractors match, return empty result
                query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
        else:
            # No events match, return empty result
            query = query.eq("id", "00000000-0000-0000-0000-000000000000")  # Non-existent ID
    
    # search filter (ILike on company_name)
    if params.get("search"):
        search_term = params["search"]
        query = query.ilike("company_name", f"%{search_term}%")
    
    return query


# ============================================================
# LIST CONTRACTORS (FIXED: managers should NOT have global view)
# ============================================================
@router.get("", response_model=List[ContractorRead])
def list_contractors(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of contractors to return (1-1000)"),
    role: Optional[str] = Query(None, description="Filter by contractor role name"),
    building_id: Optional[str] = Query(None, description="Filter by building ID (contractors who worked on events in this building)"),
    unit_id: Optional[str] = Query(None, description="Filter by unit ID (contractors who worked on events for this unit)"),
    search: Optional[str] = Query(None, description="Search contractors by company name (case-insensitive)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(403, "Only admin roles can list all contractors.")

    client = get_supabase_client()
    
    query = client.table("contractors").select("*")
    
    # Apply filters
    filter_params = {
        "role": role,
        "building_id": building_id,
        "unit_id": unit_id,
        "search": search,
    }
    
    query = apply_contractor_filters(query, filter_params)
    query = query.order("company_name").limit(limit)

    result = query.execute()
    contractors = result.data or []
    
    # Batch enrich all contractors with roles (prevents N+1 queries)
    from core.contractor_helpers import batch_enrich_contractors_with_roles
    enriched_contractors = batch_enrich_contractors_with_roles(contractors)
    
    return enriched_contractors


# ============================================================
# GET CONTRACTOR — SAFE (NO .single())
# ============================================================
@router.get("/{contractor_id}", response_model=ContractorRead)
def get_contractor(contractor_id: str, current_user: CurrentUser = Depends(get_current_user)):
    ensure_contractor_access(current_user, contractor_id)

    client = get_supabase_client()
    rows = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Contractor not found")

    contractor = rows[0]
    
    # Enrich with roles
    contractor = enrich_contractor_with_roles(contractor)

    return contractor


# ============================================================
# CREATE CONTRACTOR — 2-STEP INSERT
# ============================================================
@router.post(
    "",
    response_model=ContractorRead,
    summary="Create Contractor",
    description="""
    Create a new contractor.
    
    **Required Fields:**
    - `company_name`: Company name (required, must be unique - case-insensitive)
    - `roles`: List of role names (required, at least one)
    
    **Validation:**
    - Company names must be unique (case-insensitive, whitespace trimmed)
    - If a contractor with the same company name exists, a 400 error will be returned
    
    **Optional Fields:**
    - Contact info: `phone`, `email`, `website`
    - Business info: `license_number`, `insurance_info`
    - Location: `address`, `city`, `state`, `zip_code`
    - Contact person: `contact_person`, `contact_phone`, `contact_email`
    - Additional: `notes`, `logo_url` (use POST /contractors/{id}/logo to upload logo)
    
    **Example Minimal Request:**
    ```json
    {
      "company_name": "Burger's Plumbing",
      "roles": ["plumber"]
    }
    ```
    
    **Example Complete Request:**
    ```json
    {
      "company_name": "Burger's Plumbing",
      "phone": "(808) 555-1234",
      "email": "info@burgersplumbing.com",
      "website": "https://burgersplumbing.com",
      "license_number": "PL-12345",
      "insurance_info": "General Liability: $1M",
      "address": "123 Main St",
      "city": "Honolulu",
      "state": "HI",
      "zip_code": "96815",
      "contact_person": "John Burger",
      "contact_phone": "(808) 555-1234",
      "contact_email": "john@burgersplumbing.com",
      "notes": "Specializes in commercial plumbing",
      "roles": ["plumber"]
    }
    ```
    """,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def create_contractor(payload: ContractorCreate):
    client = get_supabase_client()
    
    # Extract roles before sanitizing (roles don't go to contractors table)
    roles = payload.roles or []
    
    # Validate roles exist
    if not roles:
        raise HTTPException(400, "At least one role is required when creating a contractor.")
    
    validated_roles = validate_role_names(roles)
    
    # Check for duplicate company name (case-insensitive)
    company_name = payload.company_name.strip()
    existing_contractor = (
        client.table("contractors")
        .select("id, company_name")
        .ilike("company_name", company_name)
        .limit(1)
        .execute()
    )
    
    if existing_contractor.data:
        raise HTTPException(
            400,
            f"Contractor with company name '{company_name}' already exists. Company names must be unique."
        )
    
    # Prepare contractor data (exclude roles - they go to junction table)
    data = sanitize(payload.model_dump(exclude={"roles"}))
    
    # Convert enum fields to strings for database
    if "subscription_tier" in data and data["subscription_tier"]:
        data["subscription_tier"] = str(data["subscription_tier"])
    if "subscription_status" in data and data["subscription_status"]:
        data["subscription_status"] = str(data["subscription_status"])

    # Step 1 — Insert contractor
    try:
        insert_res = client.table("contractors").insert(data).execute()
    except Exception as e:
        from core.errors import handle_supabase_error
        error_detail = str(e).lower()
        if "duplicate" in error_detail or "unique" in error_detail:
            raise HTTPException(400, f"Contractor with company name '{company_name}' already exists.")
        raise handle_supabase_error(e, "Failed to create contractor", 500)

    if not insert_res.data:
        raise HTTPException(500, "Insert returned no data")

    contractor_id = insert_res.data[0]["id"]

    # Step 2 — Create role assignments
    create_role_assignments(contractor_id, validated_roles)

    # Step 3 — Fetch created contractor with roles
    fetch_res = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Created contractor not found")

    contractor = fetch_res.data[0]
    
    # Enrich with roles
    contractor = enrich_contractor_with_roles(contractor)

    return contractor


# ============================================================
# UPDATE CONTRACTOR — 2-STEP UPDATE
# ============================================================
@router.put(
    "/{contractor_id}",
    response_model=ContractorRead,
    summary="Update Contractor",
    description="""
    Update an existing contractor.
    
    **All fields are optional** - only include the fields you want to update.
    
    **Available Fields:**
    - Company info: `company_name` (must be unique - case-insensitive), `phone`, `email`, `website`
    - Business info: `license_number`, `insurance_info`
    - Location: `address`, `city`, `state`, `zip_code`
    - Contact person: `contact_person`, `contact_phone`, `contact_email`
    - Additional: `notes`, `logo_url` (use POST /contractors/{id}/logo to upload logo)
    - Roles: `roles` (replaces all existing roles)
    
    **Validation:**
    - If updating `company_name`, it must be unique (case-insensitive, whitespace trimmed)
    - If another contractor with the same name exists, a 400 error will be returned
    
    **Note:** To update the logo, use the `POST /contractors/{contractor_id}/logo` endpoint.
    """,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_contractor(contractor_id: str, payload: ContractorUpdate):
    client = get_supabase_client()
    
    # Extract roles if provided (roles don't go to contractors table)
    roles = payload.roles
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"roles"}))
    
    # Convert enum fields to strings for database
    if "subscription_tier" in update_data and update_data["subscription_tier"]:
        update_data["subscription_tier"] = str(update_data["subscription_tier"])
    if "subscription_status" in update_data and update_data["subscription_status"]:
        update_data["subscription_status"] = str(update_data["subscription_status"])
    
    # Check for duplicate company name if company_name is being updated
    if "company_name" in update_data:
        company_name = update_data["company_name"].strip()
        # Check if another contractor (excluding current one) has this name
        existing_contractor = (
            client.table("contractors")
            .select("id, company_name")
            .ilike("company_name", company_name)
            .neq("id", contractor_id)  # Exclude the current contractor
            .limit(1)
            .execute()
        )
        
        if existing_contractor.data:
            raise HTTPException(
                400,
                f"Contractor with company name '{company_name}' already exists. Company names must be unique."
            )
        
        # Update the sanitized data with trimmed name
        update_data["company_name"] = company_name

    # Step 1 — Update contractor (if any fields changed)
    if update_data:
        try:
            update_res = (
                client.table("contractors")
                .update(update_data)
                .eq("id", contractor_id)
                .execute()
            )
        except Exception as e:
            from core.errors import handle_supabase_error
            error_detail = str(e).lower()
            if "duplicate" in error_detail or "unique" in error_detail:
                raise HTTPException(400, f"Contractor with company name '{update_data.get('company_name', 'this name')}' already exists.")
            raise handle_supabase_error(e, "Failed to update contractor", 500)

        if not update_res.data:
            raise HTTPException(404, "Contractor not found")

    # Step 2 — Update role assignments if roles were provided
    if roles is not None:
        if roles:
            validated_roles = validate_role_names(roles)
            update_role_assignments(contractor_id, validated_roles)
        else:
            # Empty list means remove all roles
            client.table("contractor_role_assignments").delete().eq("contractor_id", contractor_id).execute()

    # Step 3 — Fetch updated contractor with roles
    fetch_res = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .execute()
    )

    if not fetch_res.data:
        raise HTTPException(500, "Updated contractor not found")

    contractor = fetch_res.data[0]
    
    # Enrich with roles
    contractor = enrich_contractor_with_roles(contractor)

    return contractor


# ============================================================
# UPLOAD CONTRACTOR LOGO
# ============================================================
@router.post(
    "/{contractor_id}/logo",
    summary="Upload contractor logo",
    description="Upload a logo image for a contractor. Supported formats: JPG, PNG, GIF, WebP. Max file size: 5MB.",
    response_model=LogoUploadResponse,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
async def upload_contractor_logo(
    contractor_id: str,
    file: UploadFile = File(...),
    update_contractor: bool = Form(True, description="Automatically update contractor's logo_url field"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload a logo image for a contractor.
    
    The image is uploaded to S3 and optionally updates the contractor's logo_url field.
    """
    # Validate contractor exists
    client = get_supabase_client()
    contractor_check = (
        client.table("contractors")
        .select("id, company_name")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    )
    
    if not contractor_check.data:
        raise HTTPException(404, f"Contractor '{contractor_id}' not found")
    
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
    safe_company_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in contractor_check.data[0]["company_name"])[:50]
    s3_key = f"contractors/logos/{contractor_id}/{safe_company_name}_{timestamp}_{unique_id}{file_extension}"
    
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
            logger.info(f"Uploaded contractor logo to S3: {s3_key}")
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
    
    # Optionally update contractor's logo_url field
    if update_contractor:
        try:
            client.table("contractors").update({
                "logo_url": logo_url
            }).eq("id", contractor_id).execute()
            logger.info(f"Updated contractor {contractor_id} logo_url")
        except Exception as e:
            logger.warning(f"Failed to update contractor logo_url: {e}")
            # Don't fail the request if update fails - logo is still uploaded
    
    return {
        "success": True,
        "logo_url": logo_url,
        "s3_key": s3_key,
        "message": "Logo uploaded successfully" + (" and contractor updated" if update_contractor else "")
    }


# ============================================================
# DELETE CONTRACTOR — SAFE 2-STEP DELETE
# ============================================================
@router.delete(
    "/{contractor_id}",
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def delete_contractor(contractor_id: str):
    client = get_supabase_client()

    # Prevent deletion if referenced by events (via event_contractors junction table)
    event_contractors = (
        client.table("event_contractors")
        .select("event_id")
        .eq("contractor_id", contractor_id)
        .limit(1)
        .execute()
    )

    if event_contractors.data:
        raise HTTPException(400, "Cannot delete contractor — events reference this contractor.")
    
    # Prevent deletion if referenced by documents (via document_contractors junction table)
    document_contractors = (
        client.table("document_contractors")
        .select("document_id")
        .eq("contractor_id", contractor_id)
        .limit(1)
        .execute()
    )

    if document_contractors.data:
        raise HTTPException(400, "Cannot delete contractor — documents reference this contractor.")

    # Step 1 — delete
    try:
        delete_res = (
            client.table("contractors")
            .delete()
            .eq("id", contractor_id)
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")

    if not delete_res.data:
        raise HTTPException(404, "Contractor not found")

    return {"status": "deleted", "id": contractor_id}


# ============================================================
# SYNC SUBSCRIPTION STATUS FROM STRIPE
# ============================================================
@router.post(
    "/{contractor_id}/sync-subscription",
    summary="Sync subscription status from Stripe",
    description="""
    Manually sync a contractor's subscription status from Stripe.
    
    This endpoint:
    1. Verifies the subscription status with Stripe
    2. Updates the contractor's `subscription_tier`, `subscription_status` fields
    3. Returns the updated contractor data
    
    **Use Cases:**
    - Manual sync when subscription changes
    - Admin verification of subscription status
    - Testing subscription status updates
    
    **Note:** For automatic updates, use the Stripe webhook endpoint instead.
    """,
    response_model=ContractorRead,
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def sync_contractor_subscription(
    contractor_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Sync contractor subscription status from Stripe.
    """
    ensure_contractor_access(current_user, contractor_id)
    
    client = get_supabase_client()
    
    # Fetch contractor
    contractor_res = (
        client.table("contractors")
        .select("*")
        .eq("id", contractor_id)
        .limit(1)
        .execute()
    )
    
    if not contractor_res.data:
        raise HTTPException(404, "Contractor not found")
    
    contractor = contractor_res.data[0]
    stripe_customer_id = contractor.get("stripe_customer_id")
    stripe_subscription_id = contractor.get("stripe_subscription_id")
    
    if not stripe_customer_id and not stripe_subscription_id:
        raise HTTPException(
            400,
            "Contractor does not have a Stripe customer ID or subscription ID. Cannot sync subscription."
        )
    
    # Verify subscription with Stripe
    is_active, subscription_status, error_message = verify_contractor_subscription(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id
    )
    
    if error_message:
        logger.warning(f"Error syncing subscription for contractor {contractor_id}: {error_message}")
        raise HTTPException(400, f"Failed to verify subscription: {error_message}")
    
    # Determine subscription tier
    subscription_tier = "paid" if is_active else "free"
    
    # Update contractor with subscription info
    update_data = {
        "subscription_tier": subscription_tier,
        "subscription_status": subscription_status
    }
    
    try:
        update_res = (
            client.table("contractors")
            .update(update_data)
            .eq("id", contractor_id)
            .execute()
        )
        
        if not update_res.data:
            raise HTTPException(500, "Failed to update contractor subscription status")
        
        updated_contractor = update_res.data[0]
        
        # Enrich with roles
        updated_contractor = enrich_contractor_with_roles(updated_contractor)
        
        logger.info(f"Synced subscription status for contractor {contractor_id}: tier={subscription_tier}, status={subscription_status}")
        
        return updated_contractor
        
    except Exception as e:
        from core.errors import handle_supabase_error
        raise handle_supabase_error(e, "Failed to sync subscription status", 500)
