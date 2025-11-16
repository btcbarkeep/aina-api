# routers/buildings_supabase.py

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List

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

# ---------------------------------------------------------
# Helper — normalize payloads ("" -> None)
# ---------------------------------------------------------
def sanitize(data: dict) -> dict:
    clean = {}
    for k, v in data.items():
        if isinstance(v, str) and v.strip() == "":
            clean[k] = None
        else:
            clean[k] = v
    return clean


# ---------------------------------------------------------
# LIST — Any authenticated user
# ---------------------------------------------------------
@router.get("/supabase", summary="List Buildings")
def list_buildings_supabase(
    limit: int = 100,
    name: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user)
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(500, "Supabase not configured")

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
        raise HTTPException(500, f"Supabase fetch error: {str(e)}")


# ---------------------------------------------------------
# CREATE — Admin only
# ---------------------------------------------------------
@router.post(
    "/supabase",
    response_model=BuildingRead,
    summary="Create Building",
    dependencies=[Depends(requires_role(["admin"]))]
)
def create_building_supabase(payload: BuildingCreate):
    client = get_supabase_client()
    data = sanitize(payload.model_dump())

    try:
        insert_result = client.table("buildings").insert(data).execute()

        if not insert_result.data:
            raise HTTPException(500, "Insert succeeded but returned no data")

        building_id = insert_result.data[0]["id"]

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
        raise HTTPException(500, f"Supabase insert error: {msg}")


# ---------------------------------------------------------
# UPDATE — Admin or Manager
# ---------------------------------------------------------
@router.put(
    "/supabase/{building_id}",
    response_model=BuildingRead,
    summary="Update Building",
    dependencies=[Depends(requires_role(["admin", "manager"]))]
)
def update_building_supabase(
    building_id: str,
    payload: BuildingUpdate,
):
    client = get_supabase_client()
    update_data = sanitize(payload.model_dump(exclude_unset=True))

    try:
        client.table("buildings").update(update_data).eq("id", building_id).execute()

        fetch_result = (
            client.table("buildings")
            .select("*")
            .eq("id", building_id)
            .single()
            .execute()
        )

        if not fetch_result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return fetch_result.data

    except Exception as e:
        raise HTTPException(500, f"Supabase update failed: {e}")


# ---------------------------------------------------------
# DELETE — Admin only
# ---------------------------------------------------------
@router.delete(
    "/supabase/{building_id}",
    summary="Delete Building",
    dependencies=[Depends(requires_role(["admin"]))]
)
def delete_building(building_id: str):
    client = get_supabase_client()

    try:
        delete_result = (
            client.table("buildings")
            .delete()
            .eq("id", building_id)
            .execute()
        )

        if not delete_result.data:
            raise HTTPException(404, f"Building '{building_id}' not found")

        return {"status": "deleted", "id": building_id}

    except Exception as e:
        raise HTTPException(500, f"Supabase delete error: {e}")


# =====================================================================
# 🆕 NEW: BUILDING → CONTRACTOR SUMMARY ENDPOINT
# =====================================================================
@router.get(
    "/supabase/{building_id}/contractors",
    summary="List contractors who have worked on this building"
)
def get_building_contractors(
    building_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Returns contractors that have events in this building,
    including event counts and first/last seen dates.
    """

    client = get_supabase_client()

    events_query = (
        client.table("events")
        .select("contractor_id, event_type, created_at")
        .eq("building_id", building_id)
        .not_.is_("contractor_id", None)
        .execute()
    )

    events = events_query.data or []

    if not events:
        return []  # building has no contractor work yet

    contractor_ids = list({e["contractor_id"] for e in events if e["contractor_id"]})
    if not contractor_ids:
        return []

    contractors_query = (
        client.table("contractors")
        .select("*")
        .in_("id", contractor_ids)
        .execute()
    )

    contractors = {c["id"]: c for c in (contractors_query.data or [])}

    summary = {}
    for e in events:
        cid = e["contractor_id"]
        if not cid:
            continue

        if cid not in summary:
            summary[cid] = {
                "contractor": contractors.get(cid),
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

    # Convert sets to lists for JSON
    return [
        {
            **data["contractor"],
            "event_count": data["event_count"],
            "event_types": list(data["event_types"]),
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
        }
        for cid, data in summary.items()
    ]
