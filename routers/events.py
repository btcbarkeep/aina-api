# routers/events.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime

from database import get_session
from models import Event
from dependencies.auth import get_current_user

router = APIRouter(prefix="/events", tags=["Events"])


@router.post("/", response_model=Event, dependencies=[Depends(get_current_user)])  # ✅ FIXED
def create_event(event: Event, session: Session = Depends(get_session)):
    """Create a new event (protected)."""
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.get("/", response_model=List[Event])
def list_events(
    complex_name: Optional[str] = Query(None),
    unit: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    """List all events (public)."""
    query = select(Event)
    if complex_name:
        query = query.where(Event.complex == complex_name)
    if unit:
        query = query.where(Event.unit == unit)
    if category:
        query = query.where(Event.category == category)
    return session.exec(query).all()


@router.delete("/{event_id}", dependencies=[Depends(get_current_user)])  # ✅ FIXED
def delete_event(event_id: int, session: Session = Depends(get_session)):
    """Delete event (protected)."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()
    return {"message": f"Event {event_id} deleted successfully"}
