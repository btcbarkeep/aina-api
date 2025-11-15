# routers/events.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from dependencies.auth import get_current_user
from core.auth_helpers import verify_user_building_access
from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record


# Import models
from models import (
    Event,
    EventCreate,
    EventRead,
    EventUpdate,
    Building,
    UserBuildingAccess,
)

import traceback

router = APIRouter(
    prefix="/events",
    tags=["Events"],
)

"""
Event endpoints manage building and AOAO-related events, maintenance logs,
and important updates for property records.
"""

# -----------------------------------------------------
# Supabase Integration
# -----------------------------------------------------

@router.get("/supabase", summary="List Events from Supabase")
def list_events_supabase(limit: int = 50):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        result = client.table("events").select("*").limit(limit).execute()
        return result.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


@router.post("/supabase", summary="Create Event in Supabase")
def create_event_supabase(
    payload: EventCreate,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # Permission check
    access = session.exec(
        select(UserBuildingAccess).where(
            UserBuildingAccess.username == current_user["username"],
            UserBuildingAccess.building_id == payload.building_id,
        )
    ).first()

    if not access:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to create an event for building {payload.building_id}",
        )

    try:
        result = client.table("events").insert(payload.dict()).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


@router.put("/supabase/{event_id}", summary="Update Event in Supabase")
def update_event_supabase(event_id: str, payload: EventUpdate):
    """
    Update an event record in Supabase.
    """
    update_data = payload.dict(exclude_unset=True)

    result = update_record("events", event_id, update_data)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]
    
@router.delete("/supabase/{event_id}", summary="Delete Event (Supabase)")
def delete_event_supabase(
    event_id: int,
    current_user: str = Depends(get_current_user),
):
    """
    Delete an event record from Supabase by ID.
    Also ensures that related documents are not left orphaned.
    """

    from core.supabase_client import get_supabase_client
    client = get_supabase_client()

    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # --- Optional: block delete if documents are still attached ---
    try:
        doc_result = client.table("documents").select("id").eq("event_id", event_id).execute()
        if doc_result.data:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete event: documents are still attached to this event."
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document check failed: {e}")

    # --- Delete event ---
    try:
        result = client.table("events").delete().eq("id", event_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Event not found in Supabase")

        return {
            "status": "deleted",
            "id": event_id,
            "message": f"Event {event_id} successfully deleted from Supabase.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase delete error: {e}")


# -----------------------------------------------------
# INTERNAL FULL SYNC HELPER (no route)
# -----------------------------------------------------

def run_full_event_sync(session: Session):
    """
    Internal helper for performing full bi-directional sync between local DB
    and Supabase. Called by the scheduler and sync.py.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # 1️⃣ Fetch from both local + Supabase
        local_events = session.exec(select(Event)).all()
        local_ids = {e.id for e in local_events}

        supa_result = client.table("events").select("*").execute()
        supa_data = supa_result.data or []
        supa_ids = {row["id"] for row in supa_data}

        # 2️⃣ Detect differences
        missing_in_supa = [e for e in local_events if e.id not in supa_ids]
        missing_in_local = [row for row in supa_data if row["id"] not in local_ids]

        inserted_to_supa, inserted_to_local = [], []

        # 3️⃣ Push missing → Supabase
        for e in missing_in_supa:
            payload = {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "complex": e.complex,
                "unit": e.unit,
                "category": e.category,
                "date": e.date.isoformat() if e.date else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            result = client.table("events").insert(payload).execute()
            if result.data:
                inserted_to_supa.append(e.title)

        # 4️⃣ Pull missing → Local DB
        for row in missing_in_local:
            new_event = Event(
                id=row.get("id"),
                title=row.get("title"),
                description=row.get("description"),
                complex=row.get("complex"),
                unit=row.get("unit"),
                category=row.get("category"),
                date=row.get("date"),
            )
            session.add(new_event)
            inserted_to_local.append(row.get("title"))

        session.commit()

        return {
            "status": "ok",
            "summary": {
                "local_total": len(local_events),
                "supa_total": len(supa_data),
                "inserted_to_supabase": inserted_to_supa,
                "inserted_to_local": inserted_to_local,
            },
            "message": (
                f"Sync complete — "
                f"{len(inserted_to_supa)} → Supabase, "
                f"{len(inserted_to_local)} → Local DB."
            ),
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full event sync failed: {e}")


# -----------------------------------------------------
# LOCAL EVENT CRUD
# -----------------------------------------------------

@router.post("/", response_model=EventRead, summary="Create Event (Local DB)")
def create_event(
    payload: EventCreate,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]

    access = session.exec(
        select(UserBuildingAccess).where(
            UserBuildingAccess.username == username,
            UserBuildingAccess.building_id == payload.building_id,
        )
    ).first()

    if not access:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to create an event for building {payload.building_id}",
        )

    event = Event.from_orm(payload)
    session.add(event)
    session.commit()
    session.refresh(event)

    return event


@router.put("/{event_id}", response_model=EventRead, summary="Update Event (Local DB)")
def update_event_local(
    event_id: int,
    payload: dict,
    session: Session = Depends(get_session),
):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    for key, value in payload.items():
        if hasattr(event, key):
            setattr(event, key, value)

    session.commit()
    session.refresh(event)
    return event


@router.get("/", response_model=List[Event])
def list_events(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    return session.exec(select(Event).offset(offset).limit(min(limit, 200))).all()


@router.get("/{event_id}", response_model=Event)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.delete("/{event_id}", dependencies=[Depends(get_current_user)])
def delete_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    session.delete(event)
    session.commit()
    return {"message": f"Event {event_id} deleted successfully"}


@router.get("/building-options", summary="List buildings user can post events for")
def get_user_building_options(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]

    access_rows = session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == username)
    ).all()

    building_ids = [row.building_id for row in access_rows]

    if not building_ids:
        return []

    buildings = session.exec(select(Building).where(Building.id.in_(building_ids))).all()

    return [{"id": b.id, "name": b.name} for b in buildings]
