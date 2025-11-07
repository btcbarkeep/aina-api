from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from datetime import datetime

from src.database import get_session
from src.models import Event, EventCreate, EventRead

router = APIRouter(prefix="/events", tags=["Events"])

# 🟢 CREATE event
@router.post("/", response_model=EventRead)
def create_event(event_data: EventCreate, session: Session = Depends(get_session)):
    """
    Creates a new event in the database.
    """
    event = Event.from_orm(event_data)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


# 🟣 LIST events (filterable by building/unit/category)
@router.get("/", response_model=List[EventRead])
def list_events(
    building_id: Optional[int] = Query(None, description="Filter by building ID"),
    unit_number: Optional[str] = Query(None, description="Filter by unit number"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(50, ge=1, le=200, description="Max number of results to return"),
    offset: int = Query(0, ge=0, description="Results offset for pagination"),
    session: Session = Depends(get_session)
):
    """
    Returns a filtered list of events.
    """
    query = select(Event)
    if building_id:
        query = query.where(Event.building_id == building_id)
    if unit_number:
        query = query.where(Event.unit_number == unit_number)
    if event_type:
        query = query.where(Event.event_type == event_type)

    query = query.offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


# 🔵 GET single event by ID
@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, session: Session = Depends(get_session)):
    """
    Fetch a single event by ID.
    """
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


# 🔴 DELETE event
@router.delete("/{event_id}")
def delete_event(event_id: int, session: Session = Depends(get_session)):
    """
    Deletes an event by ID.
    """
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()
    return {"message": f"Event {event_id} deleted successfully"}
