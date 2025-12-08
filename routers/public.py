# routers/public.py

from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime

from core.supabase_client import get_supabase_client

router = APIRouter(
    prefix="/public",
    tags=["Public"],
)


# ============================================================
# Helper — Get top property managers for a building
# ============================================================
def get_top_property_managers(client, building_id: str, unit_number: Optional[str] = None, limit: int = 5):
    """
    Get top property managers:
    - Individual property manager users (not tied to an organization)
    - Property manager organizations (excluding individual users tied to those orgs)
    Ranked by number of events they created.
    """
    # First, get all users who have access to this building
    access_result = (
        client.table("user_building_access")
        .select("user_id")
        .eq("building_id", building_id)
        .execute()
    )
    
    if not access_result.data:
        return []
    
    user_ids = [access["user_id"] for access in access_result.data]
    
    if not user_ids:
        return []
    
    # Get events for these users
    query = (
        client.table("events")
        .select("created_by")
        .eq("building_id", building_id)
        .not_.is_("created_by", None)
        .in_("created_by", user_ids)
    )
    
    if unit_number:
        query = query.eq("unit_number", unit_number)
    
    events_result = query.execute()
    
    if not events_result.data:
        return []
    
    # Count events by created_by
    user_event_counts = {}
    for event in events_result.data:
        user_id = event["created_by"]
        user_event_counts[user_id] = user_event_counts.get(user_id, 0) + 1
    
    # Get user details and separate into individuals and organizations
    individual_managers = []  # Users without organization
    org_event_counts = {}    # organization_name -> total event count
    org_user_ids = {}        # organization_name -> set of user_ids (to exclude from individuals)
    
    for user_id, event_count in user_event_counts.items():
        try:
            user_resp = client.auth.admin.get_user_by_id(user_id)
            if user_resp and user_resp.user:
                user = user_resp.user
                metadata = user.user_metadata or {}
                
                # Only process property_manager role
                if metadata.get("role") != "property_manager":
                    continue
                
                org_name = metadata.get("organization_name")
                
                if org_name and org_name.strip():
                    # User belongs to an organization
                    org_name = org_name.strip()
                    org_event_counts[org_name] = org_event_counts.get(org_name, 0) + event_count
                    if org_name not in org_user_ids:
                        org_user_ids[org_name] = set()
                    org_user_ids[org_name].add(user_id)
                else:
                    # Individual property manager (no organization)
                    individual_managers.append({
                        "id": user.id,
                        "email": user.email,
                        "full_name": metadata.get("full_name"),
                        "organization_name": None,
                        "phone": metadata.get("phone"),
                        "event_count": event_count,
                        "type": "individual",
                    })
        except Exception:
            # Skip if user lookup fails
            continue
    
    # Build organization entries (excluding individual users from those orgs)
    org_managers = []
    for org_name, total_events in org_event_counts.items():
        org_managers.append({
            "organization_name": org_name,
            "event_count": total_events,
            "type": "organization",
        })
    
    # Combine and sort by event_count
    all_managers = individual_managers + org_managers
    sorted_managers = sorted(all_managers, key=lambda x: x["event_count"], reverse=True)[:limit]
    
    return sorted_managers


# ============================================================
# Helper — Get AOAO info for a building
# ============================================================
def get_aoao_info(client, building_id: str, unit_number: Optional[str] = None):
    """
    Get AOAO organizations for a building (only organizations, not individual users).
    Groups AOAO users by organization_name and returns organizations with event counts.
    """
    # Get all users who have access to this building
    access_result = (
        client.table("user_building_access")
        .select("user_id")
        .eq("building_id", building_id)
        .execute()
    )
    
    if not access_result.data:
        return []
    
    user_ids = [access["user_id"] for access in access_result.data]
    
    if not user_ids:
        return []
    
    # Get events for these users
    query = (
        client.table("events")
        .select("created_by")
        .eq("building_id", building_id)
        .not_.is_("created_by", None)
        .in_("created_by", user_ids)
    )
    
    if unit_number:
        query = query.eq("unit_number", unit_number)
    
    events_result = query.execute()
    
    if not events_result.data:
        return []
    
    # Count events by created_by
    user_event_counts = {}
    for event in events_result.data:
        user_id = event["created_by"]
        user_event_counts[user_id] = user_event_counts.get(user_id, 0) + 1
    
    # Group by organization_name (only include users with organization_name)
    org_event_counts = {}    # organization_name -> total event count
    
    for user_id, event_count in user_event_counts.items():
        try:
            user_resp = client.auth.admin.get_user_by_id(user_id)
            if user_resp and user_resp.user:
                user = user_resp.user
                metadata = user.user_metadata or {}
                
                # Only process hoa or hoa_staff roles
                role = metadata.get("role")
                if role not in ["hoa", "hoa_staff"]:
                    continue
                
                org_name = metadata.get("organization_name")
                
                # Only include users that belong to an organization
                if org_name and org_name.strip():
                    org_name = org_name.strip()
                    org_event_counts[org_name] = org_event_counts.get(org_name, 0) + event_count
        except Exception:
            # Skip if user lookup fails
            continue
    
    # Build organization entries (only organizations, no individual users)
    org_aoaos = []
    for org_name, total_events in org_event_counts.items():
        org_aoaos.append({
            "organization_name": org_name,
            "event_count": total_events,
        })
    
    # Sort by event count (descending)
    org_aoaos.sort(key=lambda x: x["event_count"], reverse=True)
    
    return org_aoaos


# ============================================================
# Helper — Get top contractors for a building
# ============================================================
def get_top_contractors(client, building_id: str, unit_number: Optional[str] = None, limit: int = 5):
    """
    Get top contractors ranked by number of events for the building/unit.
    """
    query = (
        client.table("events")
        .select("contractor_id")
        .eq("building_id", building_id)
        .not_.is_("contractor_id", None)
    )
    
    if unit_number:
        query = query.eq("unit_number", unit_number)
    
    events_result = query.execute()
    
    if not events_result.data:
        return []
    
    # Count events by contractor_id
    contractor_counts = {}
    for event in events_result.data:
        contractor_id = event["contractor_id"]
        contractor_counts[contractor_id] = contractor_counts.get(contractor_id, 0) + 1
    
    # Sort by count and get top N
    sorted_contractors = sorted(contractor_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    # Get contractor details
    contractor_ids = [cid for cid, _ in sorted_contractors]
    contractors_result = (
        client.table("contractors")
        .select("*")
        .in_("id", contractor_ids)
        .execute()
    )
    
    contractor_map = {c["id"]: c for c in (contractors_result.data or [])}
    
    # Build result with counts
    result = []
    for contractor_id, event_count in sorted_contractors:
        contractor = contractor_map.get(contractor_id, {"id": contractor_id})
        contractor_info = contractor.copy()
        contractor_info["event_count"] = event_count
        result.append(contractor_info)
    
    return result


# ============================================================
# GET — Public Building Info
# ============================================================
@router.get(
    "/buildings/{building_id}/info",
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
        property_managers = []
    
    # Get top 5 contractors
    try:
        contractors = get_top_contractors(client, building_id, limit=5)
    except Exception as e:
        contractors = []
    
    # Get AOAO organizations (only organizations, not individual users)
    try:
        aoao_organizations = get_aoao_info(client, building_id)
    except Exception as e:
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
    "/buildings/{building_id}/units/{unit_number}/info",
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

