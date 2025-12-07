from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.supabase_client import get_supabase_client
from core.utils import sanitize
from core.logging_config import logger
from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

router = APIRouter(
    prefix="/user-access",
    tags=["Access Management"],
)


# ============================================================
# Pydantic Models
# ============================================================
class UserBuildingAccessCreate(BaseModel):
    user_id: str
    building_id: str


class UserBuildingAccessRead(BaseModel):
    user_id: str
    building_id: str


class UserUnitAccessCreate(BaseModel):
    user_id: str
    unit_id: str


class UserUnitAccessRead(BaseModel):
    user_id: str
    unit_id: str


class AOAOOrganizationBuildingAccessCreate(BaseModel):
    building_id: str


class PMCompanyBuildingAccessCreate(BaseModel):
    building_id: str


class PMCompanyUnitAccessCreate(BaseModel):
    unit_id: str


# ============================================================
# USER ACCESS — Individual User Access Management
# ============================================================

# ============================================================
# List User Access
# ============================================================
@router.get(
    "/buildings",
    summary="List all user building access entries",
    description="[User Access] List all individual user building access grants",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_building_access():
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    try:
        result = (
            client.table("user_building_access")
            .select("user_id, building_id")
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


@router.get(
    "/units",
    summary="List all user unit access entries",
    description="[User Access] List all individual user unit access grants",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_unit_access():
    client = get_supabase_client()

    try:
        result = (
            client.table("user_units_access")
            .select("user_id, unit_id")
            .execute()
        )
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


@router.get(
    "/",
    summary="List all user access entries (buildings and units)",
    description="[User Access] List all individual user access grants (both buildings and units)",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_user_access():
    client = get_supabase_client()

    try:
        building_result = (
            client.table("user_building_access")
            .select("user_id, building_id")
            .execute()
        )
        unit_result = (
            client.table("user_units_access")
            .select("user_id, unit_id")
            .execute()
        )
        
        return {
            "buildings": building_result.data or [],
            "units": unit_result.data or [],
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Helper — Validate User & Building exist
# NEW: user validation now checks Supabase Auth
# ============================================================
def validate_user_and_building(client, user_id: str, building_id: str):
    # 1️⃣ Validate user exists in Supabase Auth
    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
        if not user_resp or not user_resp.user:
            raise HTTPException(404, f"User {user_id} not found")
    except Exception as e:
        raise HTTPException(500, f"Supabase Auth user lookup failed: {e}")

    # 2️⃣ Validate building exists (unchanged)
    building = (
        client.table("buildings")
        .select("id")
        .eq("id", building_id)
        .limit(1)
        .execute()
    )
    if not building.data:
        raise HTTPException(404, f"Building {building_id} not found")


# ============================================================
# Helper — Validate User & Unit exist
# ============================================================
def validate_user_and_unit(client, user_id: str, unit_id: str):
    # 1️⃣ Validate user exists in Supabase Auth
    try:
        user_resp = client.auth.admin.get_user_by_id(user_id)
        if not user_resp or not user_resp.user:
            raise HTTPException(404, f"User {user_id} not found")
    except Exception as e:
        raise HTTPException(500, f"Supabase Auth user lookup failed: {e}")

    # 2️⃣ Validate unit exists
    unit = (
        client.table("units")
        .select("id")
        .eq("id", unit_id)
        .limit(1)
        .execute()
    )
    if not unit.data:
        raise HTTPException(404, f"Unit {unit_id} not found")


# ============================================================
# Grant User Access
# ============================================================
@router.post(
    "/buildings",
    summary="Grant a user building access",
    description="[User Access] Grant building access to an individual user (e.g., for owners)",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_building_access(payload: UserBuildingAccessCreate):
    client = get_supabase_client()

    # Validate existence
    validate_user_and_building(client, payload.user_id, payload.building_id)

    # Prevent duplicate access
    existing = (
        client.table("user_building_access")
        .select("user_id")
        .eq("user_id", payload.user_id)
        .eq("building_id", payload.building_id)
        .execute()
    )

    if existing.data:
        raise HTTPException(400, "User already has access to this building")

    try:
        clean_payload = sanitize(payload.model_dump())

        result = (
            client.table("user_building_access")
            .insert(clean_payload, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed — no data returned")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


@router.post(
    "/units",
    summary="Grant a user unit access",
    description="[User Access] Grant unit access to an individual user (e.g., for owners)",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_unit_access(payload: UserUnitAccessCreate):
    client = get_supabase_client()

    # Validate existence
    validate_user_and_unit(client, payload.user_id, payload.unit_id)

    # Prevent duplicate access
    existing = (
        client.table("user_units_access")
        .select("user_id")
        .eq("user_id", payload.user_id)
        .eq("unit_id", payload.unit_id)
        .execute()
    )

    if existing.data:
        raise HTTPException(400, "User already has access to this unit")

    try:
        clean_payload = sanitize(payload.model_dump())

        result = (
            client.table("user_units_access")
            .insert(clean_payload, returning="representation")
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert failed — no data returned")

        return result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# Remove User Access
# ============================================================
@router.delete(
    "/buildings/{user_id}/{building_id}",
    summary="Remove building access for a user",
    description="[User Access] Remove building access from an individual user",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_building_access(user_id: str, building_id: str):
    client = get_supabase_client()
    if not client:
        logger.error("Supabase client not configured in delete_building_access")
        raise HTTPException(500, "Supabase client not configured")

    try:
        logger.info(f"Attempting to delete building access: user_id={user_id}, building_id={building_id}")
        
        # First check if record exists (faster than delete with returning)
        check_result = (
            client.table("user_building_access")
            .select("user_id")
            .eq("user_id", user_id)
            .eq("building_id", building_id)
            .limit(1)
            .execute()
        )
        
        if not check_result.data:
            logger.warning(f"Building access record not found: user_id={user_id}, building_id={building_id}")
            raise HTTPException(404, "Access record not found")
        
        # Delete without returning (faster)
        (
            client.table("user_building_access")
            .delete()
            .eq("user_id", user_id)
            .eq("building_id", building_id)
            .execute()
        )

        logger.info(f"Successfully deleted building access: user_id={user_id}, building_id={building_id}")
        return {
            "status": "deleted",
            "user_id": user_id,
            "building_id": building_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting building access: user_id={user_id}, building_id={building_id}, error={e}", exc_info=True)
        raise HTTPException(500, f"Supabase error: {e}")


@router.delete(
    "/units/{user_id}/{unit_id}",
    summary="Remove unit access for a user",
    description="[User Access] Remove unit access from an individual user",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_unit_access(user_id: str, unit_id: str):
    client = get_supabase_client()
    if not client:
        logger.error("Supabase client not configured in delete_unit_access")
        raise HTTPException(500, "Supabase client not configured")

    try:
        logger.info(f"Attempting to delete unit access: user_id={user_id}, unit_id={unit_id}")
        
        # First check if record exists (faster than delete with returning)
        check_result = (
            client.table("user_units_access")
            .select("user_id")
            .eq("user_id", user_id)
            .eq("unit_id", unit_id)
            .limit(1)
            .execute()
        )
        
        if not check_result.data:
            logger.warning(f"Unit access record not found: user_id={user_id}, unit_id={unit_id}")
            raise HTTPException(404, "Access record not found")
        
        # Delete without returning (faster)
        (
            client.table("user_units_access")
            .delete()
            .eq("user_id", user_id)
            .eq("unit_id", unit_id)
            .execute()
        )

        logger.info(f"Successfully deleted unit access: user_id={user_id}, unit_id={unit_id}")
        return {
            "status": "deleted",
            "user_id": user_id,
            "unit_id": unit_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting unit access: user_id={user_id}, unit_id={unit_id}, error={e}", exc_info=True)
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# View Own Access
# ============================================================
@router.get(
    "/me",
    summary="Get building and unit access for the authenticated user",
    description="[User Access] Get your own building and unit access (includes inherited organization access)"
)
def my_access(current_user: CurrentUser = Depends(get_current_user)):

    # Bootstrap admin = universal access, special-case
    if current_user.id == "bootstrap":
        return {
            "buildings": [{
                "building_id": "ALL",
                "note": "Bootstrap admin has universal access",
            }],
            "units": [{
                "unit_id": "ALL",
                "note": "Bootstrap admin has universal access",
            }],
        }

    client = get_supabase_client()
    user_id = current_user.auth_user_id  # Use auth_user_id for consistency

    try:
        building_result = (
            client.table("user_building_access")
            .select("building_id")
            .eq("user_id", user_id)
            .execute()
        )
        
        unit_result = (
            client.table("user_units_access")
            .select("unit_id")
            .eq("user_id", user_id)
            .execute()
        )

        return {
            "buildings": building_result.data or [],
            "units": unit_result.data or [],
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# ORGANIZATION ACCESS — Organization-Level Access Management
# ============================================================
# All users linked to an organization automatically inherit the organization's access
# ============================================================

# ============================================================
# AOAO ORGANIZATION BUILDING ACCESS
# ============================================================

@router.post(
    "/aoao-organizations/{organization_id}/buildings",
    summary="Grant building access to an AOAO organization",
    description="[Organization Access] Grant building access to an AOAO organization. All users with aoao_organization_id matching this organization will inherit this access.",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_aoao_org_building_access(
    organization_id: str,
    payload: AOAOOrganizationBuildingAccessCreate
):
    """
    Grant building access to an AOAO organization.
    All users with aoao_organization_id matching this organization will inherit this access.
    """
    client = get_supabase_client()
    
    # Validate organization exists
    org_result = (
        client.table("aoao_organizations")
        .select("id, organization_name")
        .eq("id", organization_id)
        .limit(1)
        .execute()
    )
    if not org_result.data:
        raise HTTPException(404, f"AOAO organization {organization_id} not found")
    
    # Validate building exists
    building_result = (
        client.table("buildings")
        .select("id")
        .eq("id", payload.building_id)
        .limit(1)
        .execute()
    )
    if not building_result.data:
        raise HTTPException(404, f"Building {payload.building_id} not found")
    
    # Check for duplicate
    existing = (
        client.table("aoao_organization_building_access")
        .select("id")
        .eq("aoao_organization_id", organization_id)
        .eq("building_id", payload.building_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(400, "Organization already has access to this building")
    
    try:
        result = (
            client.table("aoao_organization_building_access")
            .insert({
                "aoao_organization_id": organization_id,
                "building_id": payload.building_id
            }, returning="representation")
            .execute()
        )
        
        logger.info(f"Granted building {payload.building_id} access to AOAO organization {organization_id}")
        return result.data[0]
    except Exception as e:
        raise HTTPException(500, f"Failed to grant building access: {e}")


@router.get(
    "/aoao-organizations/{organization_id}/buildings",
    summary="List building access for an AOAO organization",
    description="[Organization Access] List all buildings an AOAO organization has access to",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_aoao_org_building_access(organization_id: str):
    """List all buildings an AOAO organization has access to."""
    client = get_supabase_client()
    
    result = (
        client.table("aoao_organization_building_access")
        .select("building_id")
        .eq("aoao_organization_id", organization_id)
        .execute()
    )
    
    return result.data or []


@router.delete(
    "/aoao-organizations/{organization_id}/buildings/{building_id}",
    summary="Remove building access from an AOAO organization",
    description="[Organization Access] Remove building access from an AOAO organization",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_aoao_org_building_access(organization_id: str, building_id: str):
    """Remove building access from an AOAO organization."""
    client = get_supabase_client()
    
    # Check if record exists
    check_result = (
        client.table("aoao_organization_building_access")
        .select("id")
        .eq("aoao_organization_id", organization_id)
        .eq("building_id", building_id)
        .limit(1)
        .execute()
    )
    
    if not check_result.data:
        raise HTTPException(404, "Access record not found")
    
    try:
        (
            client.table("aoao_organization_building_access")
            .delete()
            .eq("aoao_organization_id", organization_id)
            .eq("building_id", building_id)
            .execute()
        )
        
        logger.info(f"Removed building {building_id} access from AOAO organization {organization_id}")
        return {
            "status": "deleted",
            "organization_id": organization_id,
            "building_id": building_id
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to remove building access: {e}")


# ============================================================
# PM COMPANY BUILDING ACCESS
# ============================================================

@router.post(
    "/pm-companies/{company_id}/buildings",
    summary="Grant building access to a property management company",
    description="[Organization Access] Grant building access to a property management company. All users with pm_company_id matching this company will inherit this access.",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_pm_company_building_access(
    company_id: str,
    payload: PMCompanyBuildingAccessCreate
):
    """
    Grant building access to a property management company.
    All users with pm_company_id matching this company will inherit this access.
    """
    client = get_supabase_client()
    
    # Validate company exists
    company_result = (
        client.table("property_management_companies")
        .select("id, company_name")
        .eq("id", company_id)
        .limit(1)
        .execute()
    )
    if not company_result.data:
        raise HTTPException(404, f"Property management company {company_id} not found")
    
    # Validate building exists
    building_result = (
        client.table("buildings")
        .select("id")
        .eq("id", payload.building_id)
        .limit(1)
        .execute()
    )
    if not building_result.data:
        raise HTTPException(404, f"Building {payload.building_id} not found")
    
    # Check for duplicate
    existing = (
        client.table("pm_company_building_access")
        .select("id")
        .eq("pm_company_id", company_id)
        .eq("building_id", payload.building_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(400, "Company already has access to this building")
    
    try:
        result = (
            client.table("pm_company_building_access")
            .insert({
                "pm_company_id": company_id,
                "building_id": payload.building_id
            }, returning="representation")
            .execute()
        )
        
        logger.info(f"Granted building {payload.building_id} access to PM company {company_id}")
        return result.data[0]
    except Exception as e:
        raise HTTPException(500, f"Failed to grant building access: {e}")


@router.get(
    "/pm-companies/{company_id}/buildings",
    summary="List building access for a property management company",
    description="[Organization Access] List all buildings a property management company has access to",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_pm_company_building_access(company_id: str):
    """List all buildings a property management company has access to."""
    client = get_supabase_client()
    
    result = (
        client.table("pm_company_building_access")
        .select("building_id")
        .eq("pm_company_id", company_id)
        .execute()
    )
    
    return result.data or []


@router.delete(
    "/pm-companies/{company_id}/buildings/{building_id}",
    summary="Remove building access from a property management company",
    description="[Organization Access] Remove building access from a property management company",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_pm_company_building_access(company_id: str, building_id: str):
    """Remove building access from a property management company."""
    client = get_supabase_client()
    
    # Check if record exists
    check_result = (
        client.table("pm_company_building_access")
        .select("id")
        .eq("pm_company_id", company_id)
        .eq("building_id", building_id)
        .limit(1)
        .execute()
    )
    
    if not check_result.data:
        raise HTTPException(404, "Access record not found")
    
    try:
        (
            client.table("pm_company_building_access")
            .delete()
            .eq("pm_company_id", company_id)
            .eq("building_id", building_id)
            .execute()
        )
        
        logger.info(f"Removed building {building_id} access from PM company {company_id}")
        return {
            "status": "deleted",
            "company_id": company_id,
            "building_id": building_id
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to remove building access: {e}")


# ============================================================
# PM COMPANY UNIT ACCESS
# ============================================================

@router.post(
    "/pm-companies/{company_id}/units",
    summary="Grant unit access to a property management company",
    description="[Organization Access] Grant unit access to a property management company. All users with pm_company_id matching this company will inherit this access.",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def add_pm_company_unit_access(
    company_id: str,
    payload: PMCompanyUnitAccessCreate
):
    """
    Grant unit access to a property management company.
    All users with pm_company_id matching this company will inherit this access.
    """
    client = get_supabase_client()
    
    # Validate company exists
    company_result = (
        client.table("property_management_companies")
        .select("id, company_name")
        .eq("id", company_id)
        .limit(1)
        .execute()
    )
    if not company_result.data:
        raise HTTPException(404, f"Property management company {company_id} not found")
    
    # Validate unit exists
    unit_result = (
        client.table("units")
        .select("id")
        .eq("id", payload.unit_id)
        .limit(1)
        .execute()
    )
    if not unit_result.data:
        raise HTTPException(404, f"Unit {payload.unit_id} not found")
    
    # Check for duplicate
    existing = (
        client.table("pm_company_unit_access")
        .select("id")
        .eq("pm_company_id", company_id)
        .eq("unit_id", payload.unit_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(400, "Company already has access to this unit")
    
    try:
        result = (
            client.table("pm_company_unit_access")
            .insert({
                "pm_company_id": company_id,
                "unit_id": payload.unit_id
            }, returning="representation")
            .execute()
        )
        
        logger.info(f"Granted unit {payload.unit_id} access to PM company {company_id}")
        return result.data[0]
    except Exception as e:
        raise HTTPException(500, f"Failed to grant unit access: {e}")


@router.get(
    "/pm-companies/{company_id}/units",
    summary="List unit access for a property management company",
    description="[Organization Access] List all units a property management company has access to",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_pm_company_unit_access(company_id: str):
    """List all units a property management company has access to."""
    client = get_supabase_client()
    
    result = (
        client.table("pm_company_unit_access")
        .select("unit_id")
        .eq("pm_company_id", company_id)
        .execute()
    )
    
    return result.data or []


@router.delete(
    "/pm-companies/{company_id}/units/{unit_id}",
    summary="Remove unit access from a property management company",
    description="[Organization Access] Remove unit access from a property management company",
    dependencies=[Depends(requires_permission("user_access:write"))],
)
def delete_pm_company_unit_access(company_id: str, unit_id: str):
    """Remove unit access from a property management company."""
    client = get_supabase_client()
    
    # Check if record exists
    check_result = (
        client.table("pm_company_unit_access")
        .select("id")
        .eq("pm_company_id", company_id)
        .eq("unit_id", unit_id)
        .limit(1)
        .execute()
    )
    
    if not check_result.data:
        raise HTTPException(404, "Access record not found")
    
    try:
        (
            client.table("pm_company_unit_access")
            .delete()
            .eq("pm_company_id", company_id)
            .eq("unit_id", unit_id)
            .execute()
        )
        
        logger.info(f"Removed unit {unit_id} access from PM company {company_id}")
        return {
            "status": "deleted",
            "company_id": company_id,
            "unit_id": unit_id
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to remove unit access: {e}")


