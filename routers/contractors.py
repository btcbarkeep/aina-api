# routers/contractors.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel, Field

from dependencies.auth import (
    get_current_user,
    CurrentUser,
    requires_permission,
)

from core.supabase_client import get_supabase_client
from core.utils import sanitize


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
# ============================================================
def enrich_contractor_with_roles(contractor: dict) -> dict:
    """Add roles array to contractor dict."""
    contractor_id = contractor.get("id")
    if not contractor_id:
        contractor["roles"] = []
        return contractor
    
    contractor["roles"] = get_contractor_roles(contractor_id)
    return contractor


# ============================================================
# Pydantic Models
# ============================================================
class ContractorBase(BaseModel):
    company_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    license_number: Optional[str] = None
    insurance_info: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None


class ContractorCreate(ContractorBase):
    """Roles are required when creating a contractor."""
    roles: List[str] = Field(..., description="List of role names (e.g., ['plumber', 'electrician'])", example=["plumber"])
    
    class Config:
        json_schema_extra = {
            "example": {
                "company_name": "Burger's Plumbing",
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
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    license_number: Optional[str] = None
    insurance_info: Optional[str] = None
    address: Optional[str] = None
    logo_url: Optional[str] = None
    roles: Optional[List[str]] = Field(None, description="List of role names to assign (replaces existing roles)", example=["plumber", "electrician"])


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
    query = query.order("company_name")

    result = query.execute()
    contractors = result.data or []
    
    # Enrich each contractor with roles
    enriched_contractors = [enrich_contractor_with_roles(c) for c in contractors]
    
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
    
    # Prepare contractor data (exclude roles - they go to junction table)
    data = sanitize(payload.model_dump(exclude={"roles"}))

    # Step 1 — Insert contractor
    try:
        insert_res = client.table("contractors").insert(data).execute()
    except Exception as e:
        raise HTTPException(500, f"Supabase insert error: {e}")

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
    dependencies=[Depends(requires_permission("contractors:write"))],
)
def update_contractor(contractor_id: str, payload: ContractorUpdate):
    client = get_supabase_client()
    
    # Extract roles if provided (roles don't go to contractors table)
    roles = payload.roles
    update_data = sanitize(payload.model_dump(exclude_unset=True, exclude={"roles"}))

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
            raise HTTPException(500, f"Supabase update error: {e}")

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
