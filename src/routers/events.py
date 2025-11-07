from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from src.database import get_session
from src.models import Event
from src.routers.dependencies import get_current_user

router = APIRouter(prefix="/events", tags=["Events"])

# 🟢 Create (admin only)
@router.post("/", response_model=Event)
def create_event(event: Event, session: Session = Depends(get_session), current_user: str = Depends(get_current_user)):
    session.add(event)
    session.commit()
    session.refresh(event)
    return event

# 🟣 List (public)
@router.get("/", response_model=List[Event])
def list_events(
    complex_name: Optional[str] = Query(None),
    unit: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session)
):
    query = select(Event)
    if complex_name:
        query = query.where(Event.complex == complex_name)
    if unit:
        query = query.where(Event.unit == unit)
    if category:
        query = query.where(Event.category == category)
    query = query.offset(offset).limit(min(limit, 200))
    return session.exec(query).all()

# 🔵 Get by ID (public)
@router.get("/{event_id}", response_model=Event)
def get_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

# 🔴 Delete (admin only)
@router.delete("/{event_id}")
def delete_event(event_id: int, session: Session = Depends(get_session), current_user: str = Depends(get_current_user)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()
    return {"message": f"Event {event_id} deleted successfully"}
