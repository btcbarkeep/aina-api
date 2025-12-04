# routers/buildings.py

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import (
    requires_permission,
    is_admin,
    require_building_access,
    get_user_accessible_building_ids,
)

from core.supabase_client import get_supabase_client
from core.utils import sanitize

from models.building import BuildingCreate, BuildingUpdate, BuildingRead


# -----------------------------------------------------
# Helper — Enrich contractor with roles (centralized)
# -----------------------------------------------------
from core.contractor_helpers import enrich_contractor_with_roles


router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)


# ============================================================
# LIST BUILDINGS
# ============================================================
@router.get(
    "",
    summary="List Buildings",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def list_buildings(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of buildings to return (1-1000)"),
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    try:
        query = client.table("buildings").select("*").limit(limit)

        # Apply permission-based filtering for non-admin users
        if not is_admin(current_user):
            accessible_building_ids = get_user_accessible_building_ids(current_user)
            if accessible_building_ids is not None:
                query = query.in_("id", accessible_building_ids)

        if name:
            query = query.ilike("name", f"%{name}%")
        if city:
            query = query.ilike("city", f"%{city}%")
        if state:
            query = query.ilike("state", f"%{state}%")

        res = query.execute()
        return {"success": True, "data": res.data or []}

    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# ============================================================
# CREATE BUILDING
# ============================================================
@router.post(
    "",
    response_model=BuildingRead,
    summary="Create Building",
    dependencies=[Depends(requires_permission("buildings:write"))],
)
def create_building(payload: BuildingCreate):
    client = get_supabase_client()
    data = sanitize(payload.model_dump())

    try:
        insert_res = client.table("buildings").insert(data).execute()

        if not insert_res.data:
            raise HTTPException(500, "Insert returned no data")

        building_id = insert_res.data[0]["id"]

        fetch_res = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .execute()
        )

        if not fetch_res.data:
            raise HTTPException(500, "Inserted building not found")

        return fetch_res.data[0]

    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower():
            raise HTTPException(400, f"Building '{payload.name}' already exists.")
        raise HTTPException(500, f"Supabase insert error: {msg}")


# ============================================================
# UPDATE BUILDING
# ============================================================
@router.put(
    "/{building_id}",
    response_model=BuildingRead,
    summary="Update Building",
    dependencies=[Depends(requires_permission("buildings:write"))],
)
def update_building(building_id: str, payload: BuildingUpdate, current_user: CurrentUser = Depends(get_current_user)):
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)
    
    client = get_supabase_client()
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    try:
        update_res = (
            client.table("buildings")
            .update(update_data)
            .eq("id", building_id)
            .execute()
        )

        if not update_res.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        fetch_res = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .execute()
        )

        if not fetch_res.data:
            raise HTTPException(500, "Updated building not found")

        return fetch_res.data[0]

    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")


# ============================================================
# DELETE BUILDING
# ============================================================
@router.delete(
    "/{building_id}",
    summary="Delete Building",
    dependencies=[Depends(requires_permission("buildings:write"))],
)
def delete_building(building_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)
    
    client = get_supabase_client()

    try:
        delete_res = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .execute()
        )

        if not delete_res.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return {"success": True, "deleted_id": building_id}

    except Exception as e:
        raise HTTPException(500, f"Delete failed: {e}")


# ============================================================
# LIST EVENTS FOR BUILDING (unit-aware)
# ============================================================
@router.get(
    "/{building_id}/events",
    summary="List events for a building",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def get_building_events(
    building_id: str,
    unit_id: Optional[str] = None,
    event_type: Optional[str] = None,
    contractor_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)
    
    client = get_supabase_client()

    try:
        query = (
            client.table("events")
            .select("*")
            .eq("building_id", building_id)
            .order("occurred_at", desc=True)
        )

        if unit_id:
            query = query.eq("unit_id", unit_id)
        if event_type:
            query = query.eq("event_type", event_type)
        if contractor_id:
            query = query.eq("contractor_id", contractor_id)
        if severity:
            query = query.eq("severity", severity)
        if status:
            query = query.eq("status", status)

        res = query.execute()
        return {"success": True, "data": res.data or []}

    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# ============================================================
# LIST UNITS FOR BUILDING (from units table)
# ============================================================
@router.get(
    "/{building_id}/units",
    summary="List units for a building",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def get_building_units(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)
    
    client = get_supabase_client()

    try:
        query = (
            client.table("units")
            .select("*")
            .eq("building_id", building_id)
        )
        
        # For non-admin users, filter to only units they have access to
        if not is_admin(current_user):
            from core.permission_helpers import get_user_accessible_unit_ids
            accessible_unit_ids = get_user_accessible_unit_ids(current_user)
            if accessible_unit_ids is not None:
                query = query.in_("id", accessible_unit_ids)
        
        result = query.order("unit_number").execute()
        rows = result.data or []

        return {
            "success": True,
            "building_id": building_id,
            "units": rows,
            "unit_count": len(rows),
        }

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# CONTRACTORS WHO WORKED ON A BUILDING
# ============================================================
@router.get(
    "/{building_id}/contractors",
    summary="Contractors who worked on this building",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def get_building_contractors(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    # Permission check: ensure user has access to this building
    if not is_admin(current_user):
        require_building_access(current_user, building_id)
    client = get_supabase_client()

    try:
        # Fetch all events first
        event_rows = (
            client.table("events")
            .select("contractor_id, event_type, created_at")
            .eq("building_id", building_id)
            .execute()
        ).data or []

        # Only events with contractor_id
        contractor_events = [e for e in event_rows if e.get("contractor_id")]

        if not contractor_events:
            return {"success": True, "data": []}

        ids = list({e["contractor_id"] for e in contractor_events})

        contractors = (
            client.table("contractors")
            .select("*")
            .in_("id", ids)
            .execute()
        ).data or []

        # Enrich contractors with roles
        for i, contractor in enumerate(contractors):
            contractors[i] = enrich_contractor_with_roles(contractor)

        contractor_map = {c["id"]: c for c in contractors}

        summary = {}

        for e in contractor_events:
            cid = e["contractor_id"]

            if cid not in summary:
                summary[cid] = {
                    "contractor": contractor_map.get(cid),
                    "event_count": 0,
                    "event_types": set(),
                    "first_seen": e["created_at"],
                    "last_seen": e["created_at"],
                }

            summary[cid]["event_count"] += 1
            summary[cid]["event_types"].add(e["event_type"])

            if e["created_at"] < summary[cid]["first_seen"]:
                summary[cid]["first_seen"] = e["created_at"]
            if e["created_at"] > summary[cid]["last_seen"]:
                summary[cid]["last_seen"] = e["created_at"]

        output = []
        for cid, data in summary.items():
            out = data["contractor"].copy() if data["contractor"] else {"id": cid}
            out.update({
                "event_count": data["event_count"],
                "event_types": list(data["event_types"]),
                "first_seen": data["first_seen"],
                "last_seen": data["last_seen"],
            })
            output.append(out)

        return {"success": True, "data": output}

    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# FULL BUILDING REPORT (unit-aware)
# ============================================================
@router.get(
    "/{building_id}/report",
    summary="Full building report",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def get_building_report(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    # Fetch building
    rows = (
        client.table("buildings")
        .select("*")
        .eq("id", building_id)
        .limit(1)
        .execute()
    ).data

    if not rows:
        raise HTTPException(404, "Building not found")

    building = rows[0]

    # Fetch events
    events = (
        client.table("events")
        .select("*")
        .eq("building_id", building_id)
        .order("occurred_at", desc=True)
        .execute()
    ).data or []

    # Fetch units
    unit_rows = (
        client.table("units")
        .select("*")
        .eq("building_id", building_id)
        .order("unit_number")
        .execute()
    ).data or []

    contractors = get_building_contractors(building_id, current_user)["data"]

    stats = {
        "total_events": len(events),
        "unit_count": len(unit_rows),
        "unique_contractors": len(contractors),
        "severity_counts": {},
    }

    for e in events:
        sev = e.get("severity", "unknown")
        stats["severity_counts"][sev] = stats["severity_counts"].get(sev, 0) + 1

    return {
        "success": True,
        "data": {
            "building": building,
            "stats": stats,
            "units": unit_rows,
            "events": events,
            "contractors": contractors,
            "generated_at": datetime.utcnow().isoformat(),
        }
    }
