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
    description="[User Access] List all individual user building access grants (includes both direct access and inherited organization access)",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_building_access():
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase client not configured")

    try:
        # Get direct user building access
        direct_access_result = (
            client.table("user_building_access")
            .select("user_id, building_id")
            .execute()
        )
        direct_access = direct_access_result.data or []
        
        # Helper to extract user list from Supabase response (same pattern as admin.py)
        def extract_user_list(result):
            """Extract user list from Supabase response."""
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "users" in result:
                return result["users"]
            users_attr = getattr(result, "users", None)
            if users_attr is not None:
                return users_attr
            return []
        
        # Get all users from Supabase Auth to check their organization assignments
        try:
            all_users_raw = client.auth.admin.list_users()
            users_list = extract_user_list(all_users_raw)
        except Exception as e:
            logger.warning(f"Failed to fetch all users for inherited access: {e}")
            users_list = []
        
        # Build a set of direct access for quick lookup
        direct_access_set = {(entry["user_id"], entry["building_id"]) for entry in direct_access}
        
        # Get inherited access from AOAO organizations
        aoao_building_access = {}
        try:
            aoao_access_result = (
                client.table("aoao_organization_building_access")
                .select("aoao_organization_id, building_id")
                .execute()
            )
            for entry in (aoao_access_result.data or []):
                org_id = entry["aoao_organization_id"]
                building_id = entry["building_id"]
                if org_id not in aoao_building_access:
                    aoao_building_access[org_id] = []
                aoao_building_access[org_id].append(building_id)
        except Exception as e:
            logger.warning(f"Failed to fetch AOAO organization building access: {e}")
        
        # Get inherited access from PM companies
        pm_building_access = {}
        try:
            pm_access_result = (
                client.table("pm_company_building_access")
                .select("pm_company_id, building_id")
                .execute()
            )
            for entry in (pm_access_result.data or []):
                company_id = entry["pm_company_id"]
                building_id = entry["building_id"]
                if company_id not in pm_building_access:
                    pm_building_access[company_id] = []
                pm_building_access[company_id].append(building_id)
        except Exception as e:
            logger.warning(f"Failed to fetch PM company building access: {e}")
        
        # Get all building IDs (needed for contractors who have access to all buildings)
        all_building_ids = []
        try:
            buildings_result = (
                client.table("buildings")
                .select("id")
                .execute()
            )
            all_building_ids = [b["id"] for b in (buildings_result.data or [])]
        except Exception as e:
            logger.warning(f"Failed to fetch all buildings: {e}")
        
        # Add inherited access for users assigned to organizations
        inherited_access = []
        for user in users_list:
            user_id = user.id
            user_meta = user.user_metadata or {}
            user_role = user_meta.get("role", "")
            
            # Check AOAO organization access
            aoao_org_id = user_meta.get("aoao_organization_id")
            if aoao_org_id and aoao_org_id in aoao_building_access:
                for building_id in aoao_building_access[aoao_org_id]:
                    # Only add if not already in direct access (avoid duplicates)
                    if (user_id, building_id) not in direct_access_set:
                        inherited_access.append({
                            "user_id": user_id,
                            "building_id": building_id,
                            "access_type": "inherited_aoao"
                        })
            
            # Check PM company access
            pm_company_id = user_meta.get("pm_company_id")
            if pm_company_id and pm_company_id in pm_building_access:
                for building_id in pm_building_access[pm_company_id]:
                    # Only add if not already in direct access (avoid duplicates)
                    if (user_id, building_id) not in direct_access_set:
                        inherited_access.append({
                            "user_id": user_id,
                            "building_id": building_id,
                            "access_type": "inherited_pm"
                        })
            
            # Check Contractor access (contractors have access to all buildings by default)
            contractor_id = user_meta.get("contractor_id")
            if contractor_id and user_role in ["contractor", "contractor_staff"]:
                # Contractors have access to all buildings
                for building_id in all_building_ids:
                    # Only add if not already in direct access (avoid duplicates)
                    if (user_id, building_id) not in direct_access_set:
                        inherited_access.append({
                            "user_id": user_id,
                            "building_id": building_id,
                            "access_type": "inherited_contractor"
                        })
        
        # Combine direct and inherited access
        # Add access_type to direct access entries
        direct_with_type = [
            {**entry, "access_type": "direct"} 
            for entry in direct_access
        ]
        
        return direct_with_type + inherited_access

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


@router.get(
    "/units",
    summary="List all user unit access entries",
    description="[User Access] List all individual user unit access grants (includes both direct access and inherited organization access)",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_unit_access():
    client = get_supabase_client()

    try:
        # Get direct user unit access
        direct_access_result = (
            client.table("user_units_access")
            .select("user_id, unit_id")
            .execute()
        )
        direct_access = direct_access_result.data or []
        
        # Helper to extract user list from Supabase response (same pattern as admin.py)
        def extract_user_list(result):
            """Extract user list from Supabase response."""
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "users" in result:
                return result["users"]
            users_attr = getattr(result, "users", None)
            if users_attr is not None:
                return users_attr
            return []
        
        # Get all users from Supabase Auth to check their organization assignments
        try:
            all_users_raw = client.auth.admin.list_users()
            users_list = extract_user_list(all_users_raw)
        except Exception as e:
            logger.warning(f"Failed to fetch all users for inherited unit access: {e}")
            users_list = []
        
        # Build a set of direct access for quick lookup
        direct_access_set = {(entry["user_id"], entry["unit_id"]) for entry in direct_access}
        
        # Track inherited access to avoid duplicates
        inherited_access_set = set()
        
        # Get inherited access from AOAO organizations (direct unit access)
        aoao_unit_access = {}
        try:
            aoao_access_result = (
                client.table("aoao_organization_unit_access")
                .select("aoao_organization_id, unit_id")
                .execute()
            )
            for entry in (aoao_access_result.data or []):
                org_id = entry["aoao_organization_id"]
                unit_id = entry["unit_id"]
                if org_id not in aoao_unit_access:
                    aoao_unit_access[org_id] = []
                aoao_unit_access[org_id].append(unit_id)
        except Exception as e:
            logger.warning(f"Failed to fetch AOAO organization unit access: {e}")
        
        # Get AOAO organization building access (grants access to all units in those buildings)
        aoao_building_access = {}
        try:
            aoao_building_result = (
                client.table("aoao_organization_building_access")
                .select("aoao_organization_id, building_id")
                .execute()
            )
            for entry in (aoao_building_result.data or []):
                org_id = str(entry["aoao_organization_id"])  # Normalize to string
                building_id = str(entry["building_id"])  # Normalize to string
                if org_id not in aoao_building_access:
                    aoao_building_access[org_id] = []
                aoao_building_access[org_id].append(building_id)
        except Exception as e:
            logger.warning(f"Failed to fetch AOAO organization building access: {e}")
        
        # Get all units grouped by building_id (for efficient lookup)
        # Normalize building_ids to strings to ensure consistent lookups
        units_by_building = {}
        try:
            all_units_result = (
                client.table("units")
                .select("id, building_id")
                .execute()
            )
            for unit in (all_units_result.data or []):
                building_id = str(unit["building_id"])  # Normalize to string
                unit_id = str(unit["id"])  # Normalize to string
                if building_id not in units_by_building:
                    units_by_building[building_id] = []
                units_by_building[building_id].append(unit_id)
        except Exception as e:
            logger.warning(f"Failed to fetch units by building: {e}")
        
        # Get inherited access from PM companies (direct unit access)
        pm_unit_access = {}
        try:
            pm_access_result = (
                client.table("pm_company_unit_access")
                .select("pm_company_id, unit_id")
                .execute()
            )
            for entry in (pm_access_result.data or []):
                company_id = entry["pm_company_id"]
                unit_id = entry["unit_id"]
                if company_id not in pm_unit_access:
                    pm_unit_access[company_id] = []
                pm_unit_access[company_id].append(unit_id)
        except Exception as e:
            logger.warning(f"Failed to fetch PM company unit access: {e}")
        
        # Get PM company building access (grants access to all units in those buildings)
        pm_building_access = {}
        try:
            pm_building_result = (
                client.table("pm_company_building_access")
                .select("pm_company_id, building_id")
                .execute()
            )
            for entry in (pm_building_result.data or []):
                company_id = str(entry["pm_company_id"])  # Normalize to string
                building_id = str(entry["building_id"])  # Normalize to string
                if company_id not in pm_building_access:
                    pm_building_access[company_id] = []
                pm_building_access[company_id].append(building_id)
        except Exception as e:
            logger.warning(f"Failed to fetch PM company building access: {e}")
        
        # Get all unit IDs (needed for contractors who have access to all units)
        all_unit_ids = []
        try:
            units_result = (
                client.table("units")
                .select("id")
                .execute()
            )
            all_unit_ids = [u["id"] for u in (units_result.data or [])]
        except Exception as e:
            logger.warning(f"Failed to fetch all units: {e}")
        
        # Add inherited access for users assigned to organizations
        inherited_access = []
        for user in users_list:
            user_id = user.id
            user_meta = user.user_metadata or {}
            user_role = user_meta.get("role", "")
            
            # Check AOAO organization access
            aoao_org_id = user_meta.get("aoao_organization_id")
            if aoao_org_id:
                aoao_org_id = str(aoao_org_id)  # Normalize to string
                # Add direct unit access
                if aoao_org_id in aoao_unit_access:
                    for unit_id in aoao_unit_access[aoao_org_id]:
                        # Only add if not already in direct or inherited access (avoid duplicates)
                        access_key = (user_id, unit_id)
                        if access_key not in direct_access_set and access_key not in inherited_access_set:
                            inherited_access.append({
                                "user_id": user_id,
                                "unit_id": unit_id,
                                "access_type": "inherited_aoao"
                            })
                            inherited_access_set.add(access_key)
                
                # Add units from buildings the organization has access to
                if aoao_org_id in aoao_building_access:
                    for building_id in aoao_building_access[aoao_org_id]:
                        # Get all units in this building
                        building_units = units_by_building.get(building_id, [])
                        for unit_id in building_units:
                            # Only add if not already in direct or inherited access (avoid duplicates)
                            access_key = (user_id, unit_id)
                            if access_key not in direct_access_set and access_key not in inherited_access_set:
                                inherited_access.append({
                                    "user_id": user_id,
                                    "unit_id": unit_id,
                                    "access_type": "inherited_aoao_building"
                                })
                                inherited_access_set.add(access_key)
            
            # Check PM company access
            pm_company_id = user_meta.get("pm_company_id")
            if pm_company_id:
                pm_company_id = str(pm_company_id)  # Normalize to string
                # Add direct unit access
                if pm_company_id in pm_unit_access:
                    for unit_id in pm_unit_access[pm_company_id]:
                        # Only add if not already in direct or inherited access (avoid duplicates)
                        access_key = (user_id, unit_id)
                        if access_key not in direct_access_set and access_key not in inherited_access_set:
                            inherited_access.append({
                                "user_id": user_id,
                                "unit_id": unit_id,
                                "access_type": "inherited_pm"
                            })
                            inherited_access_set.add(access_key)
                
                # Add units from buildings the company has access to
                if pm_company_id in pm_building_access:
                    for building_id in pm_building_access[pm_company_id]:
                        # Get all units in this building
                        building_units = units_by_building.get(building_id, [])
                        for unit_id in building_units:
                            # Only add if not already in direct or inherited access (avoid duplicates)
                            access_key = (user_id, unit_id)
                            if access_key not in direct_access_set and access_key not in inherited_access_set:
                                inherited_access.append({
                                    "user_id": user_id,
                                    "unit_id": unit_id,
                                    "access_type": "inherited_pm_building"
                                })
                                inherited_access_set.add(access_key)
            
            # Check Contractor access (contractors have access to all units by default)
            contractor_id = user_meta.get("contractor_id")
            if contractor_id and user_role in ["contractor", "contractor_staff"]:
                # Contractors have access to all units
                for unit_id in all_unit_ids:
                    # Only add if not already in direct or inherited access (avoid duplicates)
                    access_key = (user_id, unit_id)
                    if access_key not in direct_access_set and access_key not in inherited_access_set:
                        inherited_access.append({
                            "user_id": user_id,
                            "unit_id": unit_id,
                            "access_type": "inherited_contractor"
                        })
                        inherited_access_set.add(access_key)
        
        # Combine direct and inherited access
        # Add access_type to direct access entries
        direct_with_type = [
            {**entry, "access_type": "direct"} 
            for entry in direct_access
        ]
        
        return direct_with_type + inherited_access

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


@router.get(
    "/",
    summary="List all user access entries (buildings and units)",
    description="[User Access] List all individual user access grants (both buildings and units, includes inherited organization access)",
    dependencies=[Depends(requires_permission("user_access:read"))],
)
def list_user_access():
    """
    List all user access entries for both buildings and units.
    This includes both direct access and inherited access from organizations.
    """
    # Reuse the logic from the individual endpoints
    # Get building access (includes inherited)
    try:
        building_access = list_building_access()
    except Exception as e:
        logger.error(f"Failed to get building access: {e}")
        building_access = []
    
    # Get unit access (includes inherited)
    try:
        unit_access = list_unit_access()
    except Exception as e:
        logger.error(f"Failed to get unit access: {e}")
        unit_access = []
    
    return {
        "buildings": building_access,
        "units": unit_access,
    }


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


