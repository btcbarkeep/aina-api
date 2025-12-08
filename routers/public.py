# routers/public.py

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from core.supabase_client import get_supabase_client
from services.report_generator import (
    generate_building_report,
    generate_unit_report,
)

router = APIRouter(
    prefix="/reports/public",
    tags=["Ainareports.com Public Router"],
)


# ============================================================
# GET — Public Search
# ============================================================
@router.get(
    "/search",
    summary="Search buildings, units, and addresses (public)",
)
def search_public(query: Optional[str] = None):
    """
    Public search endpoint for buildings, units, and addresses.
    Designed for autocomplete/autopopulate functionality.
    Searches across:
    - Building names
    - Building addresses
    - Unit numbers (combined with building info)
    - Cities and states
    
    Returns matching buildings and units that can be accessed via the public endpoints.
    
    Query parameter is optional - if not provided or too short (< 2 chars), returns empty results.
    """
    client = get_supabase_client()
    
    # Handle empty or missing query
    if not query or len(query.strip()) < 2:
        return {
            "success": True,
            "query": query or "",
            "buildings": [],
            "units": [],
        }
    
    search_term = query.strip()
    results = {
        "buildings": [],
        "units": [],
    }
    
    # Search buildings by name, address, city, state
    try:
        all_buildings = {}
        building_ids_seen = set()
        
        # Search by name
        try:
            name_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("name", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in name_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        # Search by address
        try:
            address_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("address", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in address_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        # Search by city
        try:
            city_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("city", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in city_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        # Search by state
        try:
            state_results = (
                client.table("buildings")
                .select("id, name, address, city, state, zip, slug")
                .ilike("state", f"%{search_term}%")
                .limit(20)
                .execute()
            ).data or []
            for b in state_results:
                if b["id"] not in building_ids_seen:
                    all_buildings[b["id"]] = b
                    building_ids_seen.add(b["id"])
        except Exception:
            pass
        
        results["buildings"] = list(all_buildings.values())[:20]
    except Exception as e:
        print(f"Error searching buildings: {e}")
        results["buildings"] = []
    
    # Search units by unit_number (and include building info)
    try:
        # First, try to find units by unit_number
        units_query = (
            client.table("units")
            .select("id, unit_number, floor, building_id, owner_name")
            .ilike("unit_number", f"%{search_term}%")
            .limit(20)
            .execute()
        )
        
        if units_query.data:
            # Get building info for these units
            building_ids = list(set(u.get("building_id") for u in units_query.data if u.get("building_id")))
            
            if building_ids:
                buildings_for_units = (
                    client.table("buildings")
                    .select("id, name, address, city, state, zip, slug")
                    .in_("id", building_ids)
                    .execute()
                ).data or []
                
                building_map = {b["id"]: b for b in buildings_for_units}
                
                # Combine unit and building info
                for unit in units_query.data:
                    building_id = unit.get("building_id")
                    building = building_map.get(building_id)
                    if building:
                        results["units"].append({
                            **unit,
                            "building": building,
                        })
    except Exception as e:
        print(f"Error searching units: {e}")
        results["units"] = []
    
    return {
        "success": True,
        "query": query,
        "buildings": results["buildings"],
        "units": results["units"],
    }


# ============================================================
# Helper — Get top property managers for a building
# ============================================================
def get_top_property_managers(
    client,
    building_id: str,
    unit_number: Optional[str] = None,
    unit_id: Optional[str] = None,
    limit: int = 5,
):
    """
    Get property managers:
    - Individual property manager users (not tied to an organization)
    - Property manager organizations (excluding individual users tied to those orgs)
    Ranked by number of events they've created for the building/unit.
    Includes all property managers who have building/unit access.
    """
    # Get PM companies with building/unit access
    try:
        pm_company_ids = set()
        
        resolved_unit_id = unit_id
        if not resolved_unit_id and unit_number:
            # First, find the unit_id for this unit_number and building_id (legacy support)
            unit_result = (
                client.table("units")
                .select("id")
                .eq("building_id", building_id)
                .eq("unit_number", unit_number)
                .single()
                .execute()
            )
            
            if not unit_result.data:
                print(f"DEBUG: Unit {unit_number} not found for building {building_id}")
                return []
            
            resolved_unit_id = unit_result.data.get("id")
        
        if resolved_unit_id:
            pm_access_result = (
                client.table("pm_company_unit_access")
                .select("pm_company_id")
                .eq("unit_id", resolved_unit_id)
                .execute()
            )
            
            pm_company_ids = {access["pm_company_id"] for access in (pm_access_result.data or [])}
        else:
            # Building level: get both building-level and unit-level access
            # 1. Get PM companies with building-level access
            pm_building_access = (
                client.table("pm_company_building_access")
                .select("pm_company_id")
                .eq("building_id", building_id)
                .execute()
            )
            pm_company_ids = {access["pm_company_id"] for access in (pm_building_access.data or [])}
            
            # 2. Get all units for this building
            units_result = (
                client.table("units")
                .select("id")
                .eq("building_id", building_id)
                .execute()
            )
            
            if units_result.data:
                unit_ids = [unit["id"] for unit in units_result.data]
                
                # 3. Get PM companies with unit-level access for any unit in this building
                if unit_ids:
                    pm_unit_access = (
                        client.table("pm_company_unit_access")
                        .select("pm_company_id")
                        .in_("unit_id", unit_ids)
                        .execute()
                    )
                    
                    unit_pm_ids = {access["pm_company_id"] for access in (pm_unit_access.data or [])}
                    pm_company_ids = pm_company_ids.union(unit_pm_ids)
        
        print(f"DEBUG: Found {len(pm_company_ids)} PM companies with access for building {building_id}")
    except Exception as e:
        print(f"DEBUG: Error querying PM access tables: {e}")
        import traceback
        traceback.print_exc()
        pm_company_ids = set()
    
    if not pm_company_ids:
        print(f"DEBUG: No PM companies found in access tables for building {building_id}")
        return []
    
    # Get PM company details
    try:
        pm_companies_result = (
            client.table("property_management_companies")
            .select("*")
            .in_("id", list(pm_company_ids))
            .execute()
        )
        
        pm_companies = {c["id"]: c for c in (pm_companies_result.data or [])}
    except Exception as e:
        print(f"Error fetching PM companies: {e}")
        pm_companies = {}
    
    # Get all events for the building/unit
    events_result = None
    if resolved_unit_id:
        event_units_result = (
            client.table("event_units")
            .select("event_id")
            .eq("unit_id", resolved_unit_id)
            .execute()
        )
        event_ids = [row.get("event_id") for row in (event_units_result.data or []) if row.get("event_id")]
        if event_ids:
            events_result = (
                client.table("events")
                .select("id, created_by")
                .in_("id", event_ids)
                .execute()
            )
        else:
            events_result = type("Result", (), {"data": []})()
    else:
        events_query = (
            client.table("events")
            .select("created_by")
            .eq("building_id", building_id)
        )
        
        if unit_number:
            events_query = events_query.eq("unit_number", unit_number)
        
        events_result = events_query.execute()
    
    # Filter out events with null created_by in Python
    if events_result.data:
        events_result.data = [e for e in events_result.data if e.get("created_by")]
    
    # Get all users who created events and map them to PM companies
    user_to_pm_company = {}  # user_id -> pm_company_id
    user_ids = set()
    
    if events_result.data:
        user_ids = {e.get("created_by") for e in events_result.data if e.get("created_by")}
    
    # Map users to PM companies by matching organization_name
    if user_ids:
        for user_id in user_ids:
            try:
                user_resp = client.auth.admin.get_user_by_id(user_id)
                if user_resp and user_resp.user:
                    metadata = user_resp.user.user_metadata or {}
                    if metadata.get("role", "").lower() == "property_manager":
                        org_name = metadata.get("organization_name")
                        if org_name:
                            # Find PM company by name
                            for pm_id, pm_company in pm_companies.items():
                                pm_name = pm_company.get("name") or pm_company.get("company_name")
                                if pm_name and pm_name.strip() == org_name.strip():
                                    user_to_pm_company[user_id] = pm_id
                                    break
            except Exception:
                continue
    
    # Count events per PM company
    pm_event_counts = {}
    
    if events_result.data:
        for event in events_result.data:
            user_id = event.get("created_by")
            if user_id in user_to_pm_company:
                pm_id = user_to_pm_company[user_id]
                pm_event_counts[pm_id] = pm_event_counts.get(pm_id, 0) + 1
    
    # Build results - PM companies (organizations)
    # Always include all PM companies with access, even if 0 events
    org_managers = []
    for pm_id in pm_company_ids:
        pm_company = pm_companies.get(pm_id, {"id": pm_id})
        event_count = pm_event_counts.get(pm_id, 0)
        
        org_managers.append({
            "id": pm_id,
            "organization_name": pm_company.get("name") or pm_company.get("company_name") or f"PM Company {pm_id[:8]}",
            "event_count": event_count,
            "type": "organization",
            # Include all other PM company fields
            "phone": pm_company.get("phone"),
            "email": pm_company.get("email"),
            "website": pm_company.get("website"),
            "address": pm_company.get("address"),
            "city": pm_company.get("city"),
            "state": pm_company.get("state"),
            "zip_code": pm_company.get("zip_code"),
            "contact_person": pm_company.get("contact_person"),
            "contact_phone": pm_company.get("contact_phone"),
            "contact_email": pm_company.get("contact_email"),
            "notes": pm_company.get("notes"),
            "created_at": pm_company.get("created_at"),
            "updated_at": pm_company.get("updated_at"),
        })
    
    # Also get individual property managers (users not in a PM company but with role property_manager)
    individual_managers = []
    if events_result.data:
        processed_users = set()
        
        for event in events_result.data:
            user_id = event.get("created_by")
            if user_id and user_id not in user_to_pm_company and user_id not in processed_users:
                processed_users.add(user_id)
                try:
                    user_resp = client.auth.admin.get_user_by_id(user_id)
                    if user_resp and user_resp.user:
                        metadata = user_resp.user.user_metadata or {}
                        if metadata.get("role", "").lower() == "property_manager":
                            org_name = metadata.get("organization_name")
                            if not org_name or not org_name.strip():
                                # Individual property manager
                                event_count = sum(1 for e in events_result.data if e.get("created_by") == user_id)
                                
                                individual_managers.append({
                                    "id": user_id,
                                    "email": user_resp.user.email,
                                    "full_name": metadata.get("full_name"),
                                    "organization_name": None,
                                    "phone": metadata.get("phone"),
                                    "event_count": event_count,
                                    "type": "individual",
                                })
                except Exception:
                    continue
    
    # Combine and sort by event_count
    all_managers = individual_managers + org_managers
    sorted_managers = sorted(all_managers, key=lambda x: x.get("event_count", 0), reverse=True)
    
    return sorted_managers


# ============================================================
# Helper — Get AOAO info for a building
# ============================================================
def get_aoao_info(client, building_id: str, unit_number: Optional[str] = None):
    """
    Get AOAO organizations for a building (only organizations, not individual users).
    Returns organizations ranked by number of events they've created for the building/unit.
    Includes all AOAO organizations that have building/unit access.
    """
    # Get AOAO organizations with building/unit access
    aoao_org_ids = set()
    
    if unit_number:
        # First, find the unit_id for this unit_number and building_id
        unit_result = (
            client.table("units")
            .select("id")
            .eq("building_id", building_id)
            .eq("unit_number", unit_number)
            .single()
            .execute()
        )
        
        if not unit_result.data:
            print(f"DEBUG: Unit {unit_number} not found for building {building_id}")
            return []
        
        unit_id = unit_result.data.get("id")
        
        aoao_access_result = (
            client.table("aoao_organization_unit_access")
            .select("aoao_organization_id")
            .eq("unit_id", unit_id)
            .execute()
        )
        
        aoao_org_ids = {access["aoao_organization_id"] for access in (aoao_access_result.data or [])}
    else:
        # Building-level: gather AOAO orgs via unit access (no building-access table exists)
        units_result = (
            client.table("units")
            .select("id")
            .eq("building_id", building_id)
            .execute()
        )
        
        if units_result.data:
            unit_ids = [unit["id"] for unit in units_result.data]
            
            if unit_ids:
                aoao_unit_access = (
                    client.table("aoao_organization_unit_access")
                    .select("aoao_organization_id")
                    .in_("unit_id", unit_ids)
                    .execute()
                )
                
                aoao_org_ids = {access["aoao_organization_id"] for access in (aoao_unit_access.data or [])}
    
    print(f"DEBUG: Found {len(aoao_org_ids)} AOAO organizations with access for building {building_id}")
    
    if not aoao_org_ids:
        print(f"DEBUG: No AOAO organizations found in access tables for building {building_id}")
        return []
    
    # Get AOAO organization details
    try:
        aoao_orgs_result = (
            client.table("aoao_organizations")
            .select("*")
            .in_("id", list(aoao_org_ids))
            .execute()
        )
        
        aoao_orgs = {o["id"]: o for o in (aoao_orgs_result.data or [])}
    except Exception as e:
        print(f"Error fetching AOAO organizations: {e}")
        aoao_orgs = {}
    
    # Get all events for the building/unit
    events_query = (
        client.table("events")
        .select("created_by")
        .eq("building_id", building_id)
    )
    
    if unit_number:
        events_query = events_query.eq("unit_number", unit_number)
    
    events_result = events_query.execute()
    
    # Filter out events with null created_by in Python
    if events_result.data:
        events_result.data = [e for e in events_result.data if e.get("created_by")]
    
    # Get all users who created events and map them to AOAO organizations
    user_to_aoao_org = {}  # user_id -> aoao_org_id
    user_ids = set()
    
    if events_result.data:
        user_ids = {e.get("created_by") for e in events_result.data if e.get("created_by")}
    
    # Map users to AOAO organizations by matching organization_name
    if user_ids:
        for user_id in user_ids:
            try:
                user_resp = client.auth.admin.get_user_by_id(user_id)
                if user_resp and user_resp.user:
                    metadata = user_resp.user.user_metadata or {}
                    role = metadata.get("role", "").lower()
                    if role in ["hoa", "hoa_staff"]:
                        org_name = metadata.get("organization_name")
                        if org_name:
                            # Find AOAO organization by name
                            for aoao_id, aoao_org in aoao_orgs.items():
                                aoao_name = aoao_org.get("name") or aoao_org.get("organization_name")
                                if aoao_name and aoao_name.strip() == org_name.strip():
                                    user_to_aoao_org[user_id] = aoao_id
                                    break
            except Exception:
                continue
    
    # Count events per AOAO organization
    aoao_event_counts = {}
    
    if events_result.data:
        for event in events_result.data:
            user_id = event.get("created_by")
            if user_id in user_to_aoao_org:
                aoao_id = user_to_aoao_org[user_id]
                aoao_event_counts[aoao_id] = aoao_event_counts.get(aoao_id, 0) + 1
    
    # Build organization entries
    # Always include all AOAO orgs with access, even if 0 events
    org_aoaos = []
    for aoao_id in aoao_org_ids:
        aoao_org = aoao_orgs.get(aoao_id, {"id": aoao_id})
        event_count = aoao_event_counts.get(aoao_id, 0)
        
        org_aoaos.append({
            "id": aoao_id,
            "organization_name": aoao_org.get("name") or aoao_org.get("organization_name") or f"AOAO {aoao_id[:8]}",
            "event_count": event_count,
            # Include all other AOAO organization fields
            "phone": aoao_org.get("phone"),
            "email": aoao_org.get("email"),
            "website": aoao_org.get("website"),
            "address": aoao_org.get("address"),
            "city": aoao_org.get("city"),
            "state": aoao_org.get("state"),
            "zip_code": aoao_org.get("zip_code"),
            "contact_person": aoao_org.get("contact_person"),
            "contact_phone": aoao_org.get("contact_phone"),
            "contact_email": aoao_org.get("contact_email"),
            "notes": aoao_org.get("notes"),
            "created_at": aoao_org.get("created_at"),
            "updated_at": aoao_org.get("updated_at"),
        })
    
    # Sort by event_count (descending)
    org_aoaos.sort(key=lambda x: x.get("event_count", 0), reverse=True)
    
    return org_aoaos


# ============================================================
# Helper — Get top contractors for a building
# ============================================================
def get_top_contractors(client, building_id: str, unit_number: Optional[str] = None, limit: int = 5):
    """
    Get all contractors who have events for the building/unit.
    Ranked by number of events.
    Uses contractor_id column from events table (contractors can be assigned to events).
    """
    # Get all events for the building/unit with contractor_id
    try:
        query = (
            client.table("events")
            .select("contractor_id")
            .eq("building_id", building_id)
        )
        
        if unit_number:
            query = query.eq("unit_number", unit_number)
        
        events_result = query.execute()
        
        print(f"DEBUG: Found {len(events_result.data or [])} total events for building {building_id}")
        
        # Filter out events with null contractor_id in Python
        if events_result.data:
            events_with_contractors = [e for e in events_result.data if e.get("contractor_id")]
            print(f"DEBUG: Found {len(events_with_contractors)} events with contractor_id")
            events_result.data = events_with_contractors
        else:
            events_result.data = []
        
    except Exception as e:
        print(f"DEBUG: Error querying events for contractors: {e}")
        import traceback
        traceback.print_exc()
        # If contractor_id column doesn't exist yet, return empty list
        return []
    
    if not events_result.data:
        print(f"DEBUG: No events with contractor_id found for building {building_id}")
        return []
    
    # Count events by contractor_id
    contractor_counts = {}
    contractor_ids = set()
    
    for event in events_result.data:
        contractor_id = event.get("contractor_id")
        if contractor_id:
            contractor_counts[contractor_id] = contractor_counts.get(contractor_id, 0) + 1
            contractor_ids.add(contractor_id)
    
    print(f"DEBUG: Found {len(contractor_ids)} unique contractors with events")
    
    if not contractor_ids:
        return []
    
    # Get contractor details
    try:
        contractors_result = (
            client.table("contractors")
            .select("*")
            .in_("id", list(contractor_ids))
            .execute()
        )
        
        contractor_map = {c["id"]: c for c in (contractors_result.data or [])}
        print(f"DEBUG: Fetched {len(contractor_map)} contractor details from database")
    except Exception as e:
        print(f"DEBUG: Error fetching contractor details: {e}")
        import traceback
        traceback.print_exc()
        contractor_map = {}
    
    # Get contractor roles for each contractor
    contractor_roles_map = {}
    try:
        if contractor_ids:
            role_assignments = (
                client.table("contractor_role_assignments")
                .select("contractor_id, role_id")
                .in_("contractor_id", list(contractor_ids))
                .execute()
            ).data or []
            
            if role_assignments:
                role_ids = list(set(a.get("role_id") for a in role_assignments if a.get("role_id")))
                
                if role_ids:
                    roles = (
                        client.table("contractor_roles")
                        .select("*")
                        .in_("id", role_ids)
                        .execute()
                    ).data or []
                    
                    role_map = {r["id"]: r for r in roles}
                    
                    # Map contractors to their roles
                    for assignment in role_assignments:
                        contractor_id = assignment.get("contractor_id")
                        role_id = assignment.get("role_id")
                        if contractor_id and role_id:
                            if contractor_id not in contractor_roles_map:
                                contractor_roles_map[contractor_id] = []
                            if role_id in role_map:
                                contractor_roles_map[contractor_id].append(role_map[role_id])
    except Exception as e:
        print(f"DEBUG: Error fetching contractor roles: {e}")
        # Continue without roles
    
    # Build result with counts (include all contractor fields + roles)
    result = []
    for contractor_id in contractor_ids:
        contractor = contractor_map.get(contractor_id)
        if contractor:
            contractor_info = contractor.copy()
            contractor_info["event_count"] = contractor_counts.get(contractor_id, 0)
            contractor_info["roles"] = contractor_roles_map.get(contractor_id, [])
            result.append(contractor_info)
        else:
            # Contractor not found in database, but has events - include with minimal info
            print(f"DEBUG: Warning: Contractor {contractor_id} has events but not found in contractors table")
            result.append({
                "id": contractor_id,
                "company_name": f"Contractor {contractor_id[:8]}",
                "event_count": contractor_counts.get(contractor_id, 0),
                "roles": contractor_roles_map.get(contractor_id, []),
            })
    
    # Sort by event_count (descending)
    result.sort(key=lambda x: x.get("event_count", 0), reverse=True)
    
    print(f"DEBUG: Returning {len(result)} contractors")
    
    return result


# ============================================================
# GET — Public Building Info
# ============================================================
@router.get(
    "/building/{building_id}",
    summary="Get public building information (last 5 documents, last 5 events, top 5 property managers, top 5 contractors, AOAO info)",
)
async def get_building_info(building_id: str):
    """
    Public endpoint to get free information about a building.
    Uses the same data logic as the report generator (public context).
    """
    try:
        report = await generate_building_report(
            building_id=building_id,
            user=None,
            context_role="public",
            internal=False,
            format="json",
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate building info: {str(e)}")
    
    data = report.data or {}
    # Keep backward-compatible top-level fields where possible
    return {
        "success": True,
        "building_id": building_id,
        **data,
        "generated_at": data.get("generated_at", datetime.utcnow().isoformat()),
    }


# ============================================================
# GET — Public Unit Info
# ============================================================
@router.get(
    "/building/{building_id}/unit/{unit_number}",
    summary="Get public unit information (last 5 documents, last 5 events, top 5 property managers, top 5 contractors, AOAO info)",
)
async def get_unit_info(building_id: str, unit_number: str):
    """
    Public endpoint to get free information about a specific unit.
    Uses the same data logic as the report generator (public context).
    """
    try:
        # generate_unit_report expects unit_id; look up by building+unit_number first
        client = get_supabase_client()
        unit_result = (
            client.table("units")
            .select("id")
            .eq("building_id", building_id)
            .eq("unit_number", unit_number)
            .single()
            .execute()
        )
        if not unit_result.data:
            raise HTTPException(404, "Unit not found")
        unit_id = unit_result.data.get("id")
        
        report = await generate_unit_report(
            unit_id=unit_id,
            user=None,
            context_role="public",
            internal=False,
            format="json",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate unit info: {str(e)}")
    
    data = report.data or {}
    return {
        "success": True,
        "building_id": building_id,
        "unit_number": unit_number,
        **data,
        "generated_at": data.get("generated_at", datetime.utcnow().isoformat()),
    }
