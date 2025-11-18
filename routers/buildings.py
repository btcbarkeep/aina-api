# routers/buildings.py

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from datetime import datetime

from dependencies.auth import get_current_user, CurrentUser
from core.permission_helpers import requires_permission

from core.supabase_client import get_supabase_client
from core.utils import sanitize

from models.building import BuildingCreate, BuildingUpdate, BuildingRead


router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)


# ============================================================
# GET — LIST BUILDINGS
# Requires: buildings:read
# ============================================================
@router.get(
    "",
    summary="List Buildings",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def list_buildings(
    limit: int = 100,
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
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

        res = query.execute()
        return {"success": True, "data": res.data or []}

    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")


# ============================================================
# POST — CREATE BUILDING
# Requires: buildings:write
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
        result = (
            client.table("buildings")
            .insert(data)
            .select("*")   # <-- FIX: replaces .single()
            .execute()
        )

        if not result.data:
            raise HTTPException(500, "Insert returned no data")

        return result.data[0]

    except Exception as e:
        msg = str(e)
        if "duplicate" in msg.lower():
            raise HTTPException(400, f"Building '{payload.name}' already exists.")
        raise HTTPException(500, f"Supabase insert error: {msg}")


# ============================================================
# PUT — UPDATE BUILDING
# Requires: buildings:write
# ============================================================
@router.put(
    "/{building_id}",
    response_model=BuildingRead,
    summary="Update Building",
    dependencies=[Depends(requires_permission("buildings:write"))],
)
def update_building(building_id: str, payload: BuildingUpdate):
    client = get_supabase_client()
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    try:
        result = (
            client.table("buildings")
            .update(update_data)
            .eq("id", building_id)
            .select("*")   # <-- FIX: replaces .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Supabase update error: {e}")

    if not result.data:
        raise HTTPException(404, f"Building '{building_id}' not found")

    return result.data[0]


# ============================================================
# DELETE — DELETE BUILDING
# Requires: buildings:write
# ============================================================
@router.delete(
    "/{building_id}",
    summary="Delete Building",
    dependencies=[Depends(requires_permission("buildings:write"))],
)
def delete_building(building_id: str):
    client = get_supabase_client()

    try:
        res = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .select("*")   # <-- FIX: replaces .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {e}")

    if not res.data:
        raise HTTPException(404, f"Building '{building_id}' not found")

    return {"success": True, "deleted_id": building_id}


# ============================================================
# GET — EVENTS FOR BUILDING
# Requires: buildings:read
# ============================================================
@router.get(
    "/{building_id}/events",
    summary="List events for a building",
    dependencies=[Depends(requires_permission("buildings:read"))],
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

    try:
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
# GET — UNIT LIST (from events)
# Requires: buildings:read
# ============================================================
@router.get(
    "/{building_id}/units",
    summary="List units inferred from events",
    dependencies=[Depends(requires_permission("buildings:read"))],
)
def get_building_units(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    client = get_supabase_client()

    try:
        rows = (
            client.table("events")
            .select("unit_number")
            .eq("building_id", building_id)
            .not_.is_("unit_number", None)
            .execute()
        ).data or []

        units = sorted({e["unit_number"] for e in rows if e["unit_number"]})

        return {
            "success": True,
            "building_id": building_id,
            "units": units,
            "unit_count": len(units),
        }
    except Exception as e:
        raise HTTPException(500, f"Supabase error: {e}")


# ============================================================
# GET — CONTRACTORS WHO WORKED ON A BUILDING
# Requires: buildings:read
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
    client = get_supabase_client()

    try:
        events = (
            client.table("events")
            .select("contractor_id, event_type, created_at")
            .eq("building_id", building_id)
            .not_.is_("contractor_id", None)
            .execute()
        ).data or []

        if not events:
            return {"success": True, "data": []}

        contractor_ids = list({e["contractor_id"] for e in events})

        contractors = (
            client.table("contractors")
            .select("*")
            .in_("id", contractor_ids)
            .execute()
        ).data or []

        contractor_map = {c["id"]: c for c in contractors}
        summary = {}

        for e in events:
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
# GET — FULL BUILDING REPORT
# Requires: buildings:read
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

    # Building lookup (replace .single())
    try:
        building_rows = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .limit(1)
            .execute()
        ).data
    except Exception as e:
        raise HTTPException(500, f"Supabase fetch error: {e}")

    if not building_rows:
        raise HTTPException(404, "Building not found")

    building = building_rows[0]

    # Events
    events = (
        client.table("events")
        .select("*")
        .eq("building_id", building_id)
        .order("occurred_at", desc=True)
        .execute()
    ).data or []

    units = sorted({e["unit_number"] for e in events if e["unit_number"]})
    contractors = get_building_contractors(building_id, current_user)["data"]

    # Stats
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
        "success": True,
        "data": {
            "building": building,
            "stats": stats,
            "units": units,
            "events": events,
            "contractors": contractors,
            "generated_at": datetime.utcnow().isoformat(),
        }
    }
