from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from datetime import datetime

from src.database import get_session
from src.models import Event

router = APIRouter(tags=["Events"])

# 🟢 CREATE event
@router.post("/", response_model=Event)
def create_event(event: Event, session: Session = Depends(get_session)):
    """
    Creates a new event in the database.
    """
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


# 🟣 LIST events (filterable by complex/unit/category)
@router.get("/", response_model=List[Event])
def list_events(
    complex_name: Optional[str] = Query(None, description="Filter by complex name"),
    unit: Optional[str] = Query(None, description="Filter by unit number"),
    category: Optional[str] = Query(None, description="Filter by event category"),
    limit: int = Query(50, ge=1, le=200, description="Max number of results to return"),
    offset: int = Query(0, ge=0, description="Results offset for pagination"),
    session: Session = Depends(get_session)
):
    """
    Returns a filtered list of events.
    """
    query = select(Event)
    if complex_name:
        query = query.where(Event.complex == complex_name)
    if unit:
        query = query.where(Event.unit == unit)
    if category:
        query = query.where(Event.category == category)

    query = query.offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


# 🔵 GET single event by ID
@router.get("/{event_id}", response_model=Event)
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
