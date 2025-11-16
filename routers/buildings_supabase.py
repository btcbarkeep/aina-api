# routers/buildings_supabase.py

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from datetime import datetime

from dependencies.auth import (
    get_current_user,
    requires_role,
    CurrentUser,
)

from core.supabase_client import get_supabase_client
from models.building import BuildingCreate, BuildingUpdate, BuildingRead


router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)

# ============================================================
# Helper — normalize payload ("" → None)
# ============================================================
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# ============================================================
# GET — LIST BUILDINGS
# roles: ANY authenticated user
# ============================================================
@router.get("/supabase", summary="List Buildings")
def list_buildings_supabase(
    limit: int = 100,
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    try:
        query = client.table("buildings").select("*").limit(limit)

        if name:
            query = query.ilike("name", f"%{name}%")
        if city:
            query = query.ilike("city", f"%{city}%")
        if state:
            query = query.ilike("state", f"%{state}%")

        result = query.execute()
        return result.data or []

    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# ============================================================
# POST — CREATE BUILDING
# roles: admin, manager
# (allows HOA managers to create their own buildings)
# ============================================================
@router.post(
    "/supabase",
    response_model=BuildingRead,
    dependencies=[Depends(requires_role(["admin", "manager"]))],
    summary="Create Building",
)
def create_building_supabase(payload: BuildingCreate):
    client = get_supabase_client()
    data = sanitize(payload.model_dump())

    try:
        insert_result = (
            client.table("buildings")
            .insert(data, returning="representation")
            .execute()
        )

        if not insert_result.data:
            raise HTTPException(500, "Insert failed")

        building_id = insert_result.data[0]["id"]

        # Re-fetch final row
        fetch_result = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .single()
            .execute()
        )

        return fetch_result.data

    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower():
            raise HTTPException(400, f"Building '{payload.name}' already exists.")
        raise HTTPException(500, msg)


# ============================================================
# PUT — UPDATE BUILDING
# roles: admin, manager
# ============================================================
@router.put(
    "/supabase/{building_id}",
    response_model=BuildingRead,
    dependencies=[Depends(requires_role(["admin", "manager"]))],
    summary="Update Building"
)
def update_building_supabase(
    building_id: str,
    payload: BuildingUpdate,
):
    client = get_supabase_client()
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    try:
        update_result = (
            client.table("buildings")
            .update(update_data, returning="representation")
            .eq("id", building_id)
            .execute()
        )

        if not update_result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return update_result.data[0]

    except Exception as e:
        raise HTTPException(500, f"Update failed: {e}")


# ============================================================
# DELETE — DELETE BUILDING
# roles: admin only
# ============================================================
@router.delete(
    "/supabase/{building_id}",
    dependencies=[Depends(requires_role(["admin"]))],
    summary="Delete Building",
)
def delete_building(building_id: str):
    client = get_supabase_client()

    try:
        delete_result = (
            client.table("buildings")
            .delete(returning="representation")
            .eq("id", building_id)
            .execute()
        )

        if not delete_result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return {"status": "deleted", "id": building_id}

    except Exception as e:
        raise HTTPException(500, f"Delete failed: {e}")


# ============================================================
# GET — EVENTS FOR BUILDING
# roles: ANY authenticated user
# ============================================================
@router.get(
    "/supabase/{building_id}/events",
    summary="List events for a building"
)
def get_building_events(
    building_id: str,
    unit: Optional[str] = None,
    event_type: Optional[str] = None,
    contractor_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    query = (
        client.table("events")
        .select("*")
        .eq("building_id", building_id)
        .order("occurred_at", desc=True)
    )

    if unit:
        query = query.eq("unit_number", unit)
    if event_type:
        query = query.eq("event_type", event_type)
    if contractor_id:
        query = query.eq("created_by", contractor_id)
    if severity:
        query = query.eq("severity", severity)
    if status:
        query = query.eq("status", status)

    return query.execute().data or []


# ============================================================
# GET — UNIT LIST (inferred from events)
# roles: ANY authenticated user
# ============================================================
@router.get(
    "/supabase/{building_id}/units",
    summary="List units inferred from events"
)
def get_building_units(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    events = (
        client.table("events")
        .select("unit_number")
        .eq("building_id", building_id)
        .not_.is_("unit_number", "null")  # correct null check
        .execute()
    ).data or []

    units = sorted({e["unit_number"] for e in events if e["unit_number"]})

    return {
        "building_id": building_id,
        "units": units,
        "unit_count": len(units),
    }


# ============================================================
# GET — CONTRACTORS FOR BUILDING
# roles: ANY authenticated user
# ============================================================
@router.get(
    "/supabase/{building_id}/contractors",
    summary="Contractors who worked on this building"
)
def get_building_contractors(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    # Events referencing a contractor
    events = (
        client.table("events")
        .select("created_by, event_type, created_at")
        .eq("building_id", building_id)
        .not_.is_("created_by", "null")
        .execute()
    ).data or []

    if not events:
        return []

    contractor_ids = list({e["created_by"] for e in events})

    # Fetch contractor rows (from users table, not a contractors table)
    contractors = (
        client.table("users")
        .select("*")
        .in_("id", contractor_ids)
        .execute()
    ).data or []

    contractor_map = {c["id"]: c for c in contractors}

    summary = {}

    for e in events:
        cid = e["created_by"]
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
        item = data["contractor"].copy() if data["contractor"] else {"id": cid}
        item.update({
            "event_count": data["event_count"],
            "event_types": list(data["event_types"]),
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
        })
        output.append(item)

    return output


# ============================================================
# GET — FULL BUILDING REPORT
# roles: ANY authenticated user
# ============================================================
@router.get(
    "/supabase/{building_id}/report",
    summary="Full building report (events, contractors, units)"
)
def get_building_report(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()

    building = (
        client.table("buildings")
        .select("*")
        .eq("id", building_id)
        .single()
        .execute()
    ).data

    if not building:
        raise HTTPException(404, "Building not found")

    events = (
        client.table("events")
        .select("*")
        .eq("building_id", building_id)
        .order("occurred_at", desc=True)
        .execute()
    ).data or []

    units = sorted({e["unit_number"] for e in events if e["unit_number"]})

    contractors = get_building_contractors(building_id, current_user)

    stats = {
        "total_events": len(events),
        "unique_units": len(units),
        "unique_contractors": len(contractors),
        "severity_counts": {},
    }

    for e in events:
        sev = e.get("severity", "unknown")
        stats["severity_counts"][sev] = stats["severity_counts"].get(sev, 0) + 1

    return {
        "building": building,
        "stats": stats,
        "units": units,
        "events": events,
        "contractors": contractors,
        "generated_at": datetime.utcnow().isoformat(),
    }
