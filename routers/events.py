# routers/events.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from core.supabase_client import get_supabase_client
from models import Event
from dependencies.auth import get_current_user
from typing import List
from core.auth_helpers import verify_user_building_access
import traceback

router = APIRouter(prefix="/api/v1/events", tags=["Events"])

"""
Event endpoints manage building and AOAO-related events, maintenance logs,
and important updates for property records.
"""

# -----------------------------------------------------
# Supabase Integration
# -----------------------------------------------------

@router.get("/supabase", summary="List Events from Supabase")
def list_events_supabase(limit: int = 50):
    """
    Fetch events directly from Supabase for verification/debugging.
    """
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
        select(UserBuildingAccess)
        .where(
            UserBuildingAccess.username == current_user["username"],
            UserBuildingAccess.building_id == payload.building_id
        )
    ).first()

    if not access:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to create an event for building {payload.building_id}"
        )

    try:
        result = client.table("events").insert(payload.dict()).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")




# -----------------------------------------------------
# SYNC CHECKERS
# -----------------------------------------------------

@router.get("/sync", summary="Compare Local vs Supabase Events")
def compare_event_sync(session: Session = Depends(get_session)):
    """
    Compare local and Supabase event tables to verify synchronization.
    Returns which records exist only in one source.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_events = session.exec(select(Event)).all()
        local_ids = {e.id for e in local_events}

        supa_result = client.table("events").select("id").execute()
        supa_ids = {row["id"] for row in supa_result.data or []}

        local_only = sorted(list(local_ids - supa_ids))
        supabase_only = sorted(list(supa_ids - local_ids))
        synced = sorted(list(local_ids & supa_ids))

        return {
            "status": "ok",
            "summary": {
                "local_count": len(local_ids),
                "supabase_count": len(supa_ids),
                "synced_count": len(synced),
                "local_only_count": len(local_only),
                "supabase_only_count": len(supabase_only),
            },
            "local_only": local_only,
            "supabase_only": supabase_only,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Event sync comparison failed: {e}")


# -----------------------------------------------------
# FULL SYNC (Bi-directional)
# -----------------------------------------------------

def run_full_event_sync(session: Session):
    """
    Internal helper for performing full bi-directional sync between local DB and Supabase.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # --- 1️⃣ Fetch from both sources ---
        local_events = session.exec(select(Event)).all()
        local_ids = {e.id for e in local_events}

        supa_result = client.table("events").select("*").execute()
        supa_data = supa_result.data or []
        supa_ids = {row["id"] for row in supa_data}

        # --- 2️⃣ Detect differences ---
        missing_in_supa = [e for e in local_events if e.id not in supa_ids]
        missing_in_local = [row for row in supa_data if row["id"] not in local_ids]

        inserted_to_supa, inserted_to_local = [], []

        # --- 3️⃣ Push missing local → Supabase ---
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

        # --- 4️⃣ Pull missing Supabase → local ---
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
            "message": f"Sync complete — {len(inserted_to_supa)} added to Supabase, {len(inserted_to_local)} added to local DB.",
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full event sync failed: {e}")


@router.post("/sync/full", summary="Fully synchronize events between local DB and Supabase")
async def full_event_sync(session: Session = Depends(get_session)):
    """
    API route version of the full sync.
    Simply wraps the internal sync logic for Swagger/manual calls.
    """
    return run_full_event_sync(session)


# -----------------------------------------------------
# LOCAL EVENT CRUD
# -----------------------------------------------------

@router.post("/", response_model=EventRead, summary="Create Event (Local DB)")
def create_event(
    payload: EventCreate,
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    username = current_user["username"]

    # Verify building permissions
    access = session.exec(
        select(UserBuildingAccess)
        .where(
            UserBuildingAccess.username == username,
            UserBuildingAccess.building_id == payload.building_id
        )
    ).first()

    if not access:
        raise HTTPException(
            status_code=403,
            detail=f"You do not have permission to create an event for building {payload.building_id}"
        )

    # Create event
    event = Event.from_orm(payload)
    session.add(event)
    session.commit()
    session.refresh(event)

    return event




@router.put("/{event_id}", response_model=Event, summary="Update Event (Local DB)")
def update_event(event_id: int, payload: dict, session: Session = Depends(get_session)):
    """Update an event record in the local database."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    for key, value in payload.items():
        if hasattr(event, key):
            setattr(event, key, value)

    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("/", response_model=List[Event])
def list_events(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    """List all events (public)."""
    query = select(Event).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


@router.get("/{event_id}", response_model=Event)
def get_event(event_id: int, session: Session = Depends(get_session)):
    """Get an event by ID (public)."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.delete("/{event_id}", dependencies=[Depends(get_current_user)])
def delete_event(event_id: int, session: Session = Depends(get_session)):
    """Delete event (protected)."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()
    return {"message": f"Event {event_id} deleted successfully"}


@router.get("/building-options", summary="List buildings the user can post events for")
def get_user_building_options(
    session: Session = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    username = current_user["username"]

    access_rows = session.exec(
        select(UserBuildingAccess).where(UserBuildingAccess.username == username)
    ).all()

    building_ids = [row.building_id for row in access_rows]

    if not building_ids:
        return []

    buildings = session.exec(
        select(Building).where(Building.id.in_(building_ids))
    ).all()

    return [
        {"id": b.id, "name": b.name}
        for b in buildings
    ]

