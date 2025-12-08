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
    Get top property managers:
    - Individual property manager users (not tied to an organization)
    - Property manager organizations (excluding individual users tied to those orgs)
    Ranked by total count of events + documents they've created/uploaded.
    Includes all property managers who have building access, even if they have 0 events/documents.
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
    
    user_ids_with_access = {access["user_id"] for access in access_result.data}
    
    # Get all events for the building/unit to count events per user
    events_query = (
        client.table("events")
        .select("created_by")
        .eq("building_id", building_id)
        .not_.is_("created_by", None)
    )
    
    if unit_number:
        events_query = events_query.eq("unit_number", unit_number)
    
    events_result = events_query.execute()
    
    # Count events by created_by, but only for users with building access
    user_event_counts = {}
    if events_result.data:
        for event in events_result.data:
            user_id = event["created_by"]
            if user_id in user_ids_with_access:
                user_event_counts[user_id] = user_event_counts.get(user_id, 0) + 1
    
    # Get all documents for the building/unit to count documents per user
    # Documents can be linked to events (via event_id) or directly to building
    # For unit-level, we need documents linked to unit events
    documents_query = (
        client.table("documents")
        .select("event_id, building_id")
        .eq("building_id", building_id)
    )
    
    documents_result = documents_query.execute()
    
    # Get event IDs for this unit if filtering by unit
    unit_event_ids = set()
    if unit_number and events_result.data:
        unit_events = [e for e in events_result.data if e.get("created_by") in user_ids_with_access]
        # We need to get the actual event IDs, not just created_by
        unit_events_query = (
            client.table("events")
            .select("id")
            .eq("building_id", building_id)
            .eq("unit_number", unit_number)
            .execute()
        )
        if unit_events_query.data:
            unit_event_ids = {e["id"] for e in unit_events_query.data}
    
    # Count documents by event creator (via event_id -> events.created_by)
    # For documents directly linked to building (no event_id), we can't attribute them to a user
    user_document_counts = {}
    if documents_result.data:
        # Get all events to map event_id -> created_by
        all_events = (
            client.table("events")
            .select("id, created_by")
            .eq("building_id", building_id)
            .not_.is_("created_by", None)
            .execute()
        )
        event_to_creator = {}
        if all_events.data:
            event_to_creator = {e["id"]: e["created_by"] for e in all_events.data}
        
        for doc in documents_result.data:
            # If filtering by unit, only count documents linked to unit events
            if unit_number:
                if doc.get("event_id") not in unit_event_ids:
                    continue
            
            event_id = doc.get("event_id")
            if event_id and event_id in event_to_creator:
                creator_id = event_to_creator[event_id]
                if creator_id in user_ids_with_access:
                    user_document_counts[creator_id] = user_document_counts.get(creator_id, 0) + 1
    
    # Get user details for all users with building access
    individual_managers = []  # Users without organization
    org_total_counts = {}    # organization_name -> total count (events + documents)
    org_user_ids = set()     # Track which users belong to organizations
    
    for user_id in user_ids_with_access:
        try:
            user_resp = client.auth.admin.get_user_by_id(user_id)
            if user_resp and user_resp.user:
                user = user_resp.user
                metadata = user.user_metadata or {}
                
                # Only process property_manager role
                if metadata.get("role") != "property_manager":
                    continue
                
                event_count = user_event_counts.get(user_id, 0)
                document_count = user_document_counts.get(user_id, 0)
                total_count = event_count + document_count
                
                org_name = metadata.get("organization_name")
                
                if org_name and org_name.strip():
                    # User belongs to an organization
                    org_name = org_name.strip()
                    org_total_counts[org_name] = org_total_counts.get(org_name, 0) + total_count
                    org_user_ids.add(user_id)
                else:
                    # Individual property manager (no organization)
                    individual_managers.append({
                        "id": user.id,
                        "email": user.email,
                        "full_name": metadata.get("full_name"),
                        "organization_name": None,
                        "phone": metadata.get("phone"),
                        "event_count": event_count,
                        "document_count": document_count,
                        "total_count": total_count,
                        "type": "individual",
                    })
        except Exception:
            # Skip if user lookup fails
            continue
    
    # Build organization entries (excluding individual users from those orgs)
    org_managers = []
    for org_name, total_count in org_total_counts.items():
        org_managers.append({
            "organization_name": org_name,
            "event_count": 0,  # We don't track per-org event counts separately
            "document_count": 0,  # We don't track per-org document counts separately
            "total_count": total_count,
            "type": "organization",
        })
    
    # Combine and sort by total_count (events + documents)
    all_managers = individual_managers + org_managers
    sorted_managers = sorted(all_managers, key=lambda x: x.get("total_count", 0), reverse=True)
    
    # Return all, not just top limit (user wants everyone with access)
    return sorted_managers


# ============================================================
# Helper — Get AOAO info for a building
# ============================================================
def get_aoao_info(client, building_id: str, unit_number: Optional[str] = None):
    """
    Get AOAO organizations for a building (only organizations, not individual users).
    Groups AOAO users by organization_name and returns organizations ranked by total count of events + documents.
    Includes all AOAO organizations that have building access, even if they have 0 events/documents.
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
    
    user_ids_with_access = {access["user_id"] for access in access_result.data}
    
    # Get all events for the building/unit to count events per user
    events_query = (
        client.table("events")
        .select("created_by")
        .eq("building_id", building_id)
        .not_.is_("created_by", None)
    )
    
    if unit_number:
        events_query = events_query.eq("unit_number", unit_number)
    
    events_result = events_query.execute()
    
    # Count events by created_by, but only for users with building access
    user_event_counts = {}
    if events_result.data:
        for event in events_result.data:
            user_id = event["created_by"]
            if user_id in user_ids_with_access:
                user_event_counts[user_id] = user_event_counts.get(user_id, 0) + 1
    
    # Get all documents for the building/unit to count documents per user
    documents_query = (
        client.table("documents")
        .select("event_id, building_id")
        .eq("building_id", building_id)
    )
    
    documents_result = documents_query.execute()
    
    # Get event IDs for this unit if filtering by unit
    unit_event_ids = set()
    if unit_number and events_result.data:
        unit_events_query = (
            client.table("events")
            .select("id")
            .eq("building_id", building_id)
            .eq("unit_number", unit_number)
            .execute()
        )
        if unit_events_query.data:
            unit_event_ids = {e["id"] for e in unit_events_query.data}
    
    # Count documents by event creator (via event_id -> events.created_by)
    user_document_counts = {}
    if documents_result.data:
        # Get all events to map event_id -> created_by
        all_events = (
            client.table("events")
            .select("id, created_by")
            .eq("building_id", building_id)
            .not_.is_("created_by", None)
            .execute()
        )
        event_to_creator = {}
        if all_events.data:
            event_to_creator = {e["id"]: e["created_by"] for e in all_events.data}
        
        for doc in documents_result.data:
            # If filtering by unit, only count documents linked to unit events
            if unit_number:
                if doc.get("event_id") not in unit_event_ids:
                    continue
            
            event_id = doc.get("event_id")
            if event_id and event_id in event_to_creator:
                creator_id = event_to_creator[event_id]
                if creator_id in user_ids_with_access:
                    user_document_counts[creator_id] = user_document_counts.get(creator_id, 0) + 1
    
    # Group by organization_name (only include users with organization_name)
    org_total_counts = {}    # organization_name -> total count (events + documents)
    
    for user_id in user_ids_with_access:
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
                    event_count = user_event_counts.get(user_id, 0)
                    document_count = user_document_counts.get(user_id, 0)
                    total_count = event_count + document_count
                    org_total_counts[org_name] = org_total_counts.get(org_name, 0) + total_count
        except Exception:
            # Skip if user lookup fails
            continue
    
    # Build organization entries (only organizations, no individual users)
    org_aoaos = []
    for org_name, total_count in org_total_counts.items():
        org_aoaos.append({
            "organization_name": org_name,
            "event_count": 0,  # We don't track per-org event counts separately
            "document_count": 0,  # We don't track per-org document counts separately
            "total_count": total_count,
        })
    
    # Sort by total_count (descending)
    org_aoaos.sort(key=lambda x: x.get("total_count", 0), reverse=True)
    
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

