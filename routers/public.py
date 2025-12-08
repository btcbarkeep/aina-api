# routers/public.py

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from core.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/reports/public",
    tags=["Public"],
)


# ============================================================
# Helper — Get top property managers for a building
# ============================================================
def get_top_property_managers(client, building_id: str, unit_number: Optional[str] = None, limit: int = 5):
    """
    Get property managers:
    - Individual property manager users (not tied to an organization)
    - Property manager organizations (excluding individual users tied to those orgs)
    Ranked by number of events they've created for the building/unit.
    Includes all property managers who have building/unit access.
    """
    # Get PM companies with building/unit access
    try:
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
            
            pm_access_result = (
                client.table("pm_company_unit_access")
                .select("pm_company_id")
                .eq("unit_id", unit_id)
                .execute()
            )
        else:
            pm_access_result = (
                client.table("pm_company_building_access")
                .select("pm_company_id")
                .eq("building_id", building_id)
                .execute()
            )
        
        pm_company_ids = {access["pm_company_id"] for access in (pm_access_result.data or [])}
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
    events_query = (
        client.table("events")
        .select("created_by")
        .eq("building_id", building_id)
        .not_.is_("created_by", None)
    )
    
    if unit_number:
        events_query = events_query.eq("unit_number", unit_number)
    
    events_result = events_query.execute()
    
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
            "organization_name": pm_company.get("name") or pm_company.get("company_name") or f"PM Company {pm_id[:8]}",
            "event_count": event_count,
            "type": "organization",
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
    try:
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
        else:
            aoao_access_result = (
                client.table("aoao_organization_building_access")
                .select("aoao_organization_id")
                .eq("building_id", building_id)
                .execute()
            )
        
        aoao_org_ids = {access["aoao_organization_id"] for access in (aoao_access_result.data or [])}
        print(f"DEBUG: Found {len(aoao_org_ids)} AOAO organizations with access for building {building_id}")
    except Exception as e:
        print(f"DEBUG: Error querying AOAO access tables: {e}")
        import traceback
        traceback.print_exc()
        aoao_org_ids = set()
    
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
        .not_.is_("created_by", None)
    )
    
    if unit_number:
        events_query = events_query.eq("unit_number", unit_number)
    
    events_result = events_query.execute()
    
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
            "organization_name": aoao_org.get("name") or aoao_org.get("organization_name") or f"AOAO {aoao_id[:8]}",
            "event_count": event_count,
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
    """
    # Get all events for the building/unit with contractor_id
    try:
        query = (
            client.table("events")
            .select("contractor_id")
            .eq("building_id", building_id)
            .not_.is_("contractor_id", None)
        )
        
        if unit_number:
            query = query.eq("unit_number", unit_number)
        
        events_result = query.execute()
        
        print(f"DEBUG: Found {len(events_result.data or [])} events with contractor_id for building {building_id}")
    except Exception as e:
        print(f"DEBUG: Error querying events for contractors: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    if not events_result.data:
        print(f"DEBUG: No events with contractor_id found for building {building_id}")
        return []
    
    # Count events by contractor_id
    contractor_counts = {}
    contractor_ids = set()
    
    if events_result.data:
        for event in events_result.data:
            contractor_id = event.get("contractor_id")
            if contractor_id:
                contractor_counts[contractor_id] = contractor_counts.get(contractor_id, 0) + 1
                contractor_ids.add(contractor_id)
    
    if not contractor_ids:
        return []
    
    # Get contractor details
    contractors_result = (
        client.table("contractors")
        .select("*")
        .in_("id", list(contractor_ids))
        .execute()
    )
    
    contractor_map = {c["id"]: c for c in (contractors_result.data or [])}
    
    # Build result with counts
    result = []
    for contractor_id in contractor_ids:
        contractor = contractor_map.get(contractor_id, {"id": contractor_id})
        contractor_info = contractor.copy()
        contractor_info["event_count"] = contractor_counts.get(contractor_id, 0)
        result.append(contractor_info)
    
    # Sort by event_count (descending)
    result.sort(key=lambda x: x.get("event_count", 0), reverse=True)
    
    return result


# ============================================================
# GET — Public Building Info
# ============================================================
@router.get(
    "/building/{building_id}",
    summary="Get public building information (last 5 documents, last 5 events, top 5 property managers, top 5 contractors, AOAO info)",
)
def get_building_info(building_id: str):
    """
    Public endpoint to get free information about a building:
    - Last 5 documents
    - Last 5 events
    - Top 5 property managers (by event count)
    - Top 5 contractors (by event count)
    - AOAO organizations (only organizations tied to the building)
    """
    client = get_supabase_client()
    
    # Verify building exists
    try:
        building = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .single()
            .execute()
        ).data
    except Exception as e:
        raise HTTPException(404, f"Building not found: {str(e)}")
    
    if not building:
        raise HTTPException(404, "Building not found")
    
    # Get last 5 documents
    try:
        documents = (
            client.table("documents")
            .select("*")
            .eq("building_id", building_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        ).data or []
    except Exception as e:
        documents = []
    
    # Get last 5 events
    try:
        events = (
            client.table("events")
            .select("*")
            .eq("building_id", building_id)
            .order("occurred_at", desc=True)
            .limit(5)
            .execute()
        ).data or []
    except Exception as e:
        events = []
    
    # Get top 5 property managers
    try:
        property_managers = get_top_property_managers(client, building_id, limit=5)
    except Exception as e:
        import traceback
        print(f"Error getting property managers: {e}")
        traceback.print_exc()
        property_managers = []
    
    # Get top 5 contractors
    try:
        contractors = get_top_contractors(client, building_id, limit=5)
    except Exception as e:
        import traceback
        print(f"Error getting contractors: {e}")
        traceback.print_exc()
        contractors = []
    
    # Get AOAO organizations (only organizations, not individual users)
    try:
        aoao_organizations = get_aoao_info(client, building_id)
    except Exception as e:
        import traceback
        print(f"Error getting AOAO organizations: {e}")
        traceback.print_exc()
        aoao_organizations = []
    
    return {
        "success": True,
        "building_id": building_id,
        "building": {
            "id": building["id"],
            "name": building.get("name"),
            "address": building.get("address"),
            "city": building.get("city"),
            "state": building.get("state"),
            "zip": building.get("zip"),
        },
        "documents": documents,
        "events": events,
        "property_managers": property_managers,
        "contractors": contractors,
        "aoao_organizations": aoao_organizations,
        "generated_at": datetime.utcnow().isoformat(),
    }


# ============================================================
# GET — Public Unit Info
# ============================================================
@router.get(
    "/building/{building_id}/unit/{unit_number}",
    summary="Get public unit information (last 5 documents, last 5 events, top 5 property managers, top 5 contractors, AOAO info)",
)
def get_unit_info(building_id: str, unit_number: str):
    """
    Public endpoint to get free information about a specific unit:
    - Last 5 documents (for this unit)
    - Last 5 events (for this unit)
    - Top 5 property managers (by event count for this unit)
    - Top 5 contractors (by event count for this unit)
    - AOAO organizations (only organizations tied to the building for this unit)
    """
    client = get_supabase_client()
    
    # Verify building exists
    try:
        building = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .single()
            .execute()
        ).data
    except Exception as e:
        raise HTTPException(404, f"Building not found: {str(e)}")
    
    if not building:
        raise HTTPException(404, "Building not found")
    
    # Get last 5 documents for this unit
    # Documents are linked to events, so we get documents via unit events
    try:
        # First get events for this unit
        unit_events = (
            client.table("events")
            .select("id")
            .eq("building_id", building_id)
            .eq("unit_number", unit_number)
            .execute()
        ).data or []
        
        event_ids = [e["id"] for e in unit_events]
        
        if event_ids:
            # Get documents linked to these events
            documents = (
                client.table("documents")
                .select("*")
                .in_("event_id", event_ids)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            ).data or []
        else:
            # No events for this unit, so no documents
            documents = []
    except Exception as e:
        documents = []
    
    # Get last 5 events for this unit
    try:
        events = (
            client.table("events")
            .select("*")
            .eq("building_id", building_id)
            .eq("unit_number", unit_number)
            .order("occurred_at", desc=True)
            .limit(5)
            .execute()
        ).data or []
    except Exception as e:
        events = []
    
    # Get top 5 property managers for this unit
    try:
        property_managers = get_top_property_managers(client, building_id, unit_number=unit_number, limit=5)
    except Exception as e:
        property_managers = []
    
    # Get top 5 contractors for this unit
    try:
        contractors = get_top_contractors(client, building_id, unit_number=unit_number, limit=5)
    except Exception as e:
        contractors = []
    
    # Get AOAO organizations for this unit (only organizations, not individual users)
    try:
        aoao_organizations = get_aoao_info(client, building_id, unit_number=unit_number)
    except Exception as e:
        aoao_organizations = []
    
    return {
        "success": True,
        "building_id": building_id,
        "unit_number": unit_number,
        "building": {
            "id": building["id"],
            "name": building.get("name"),
            "address": building.get("address"),
            "city": building.get("city"),
            "state": building.get("state"),
            "zip": building.get("zip"),
        },
        "documents": documents,
        "events": events,
        "property_managers": property_managers,
        "contractors": contractors,
        "aoao_organizations": aoao_organizations,
        "generated_at": datetime.utcnow().isoformat(),
    }
