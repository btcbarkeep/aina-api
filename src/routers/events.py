from fastapi import APIRouter, HTTPException, Query, Depends
from sqlmodel import Session, select
from database.events_model import Event
from database import engine
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/events", tags=["Events"])

# Dependency to get DB session
def get_session():
    with Session(engine) as session:
        yield session

# 🟢 CREATE new event
@router.post("/", response_model=Event)
def create_event(event: Event, session: Session = Depends(get_session)):
    session.add(event)
    session.commit()
    session.refresh(event)
    return event

# 🟣 GET list of events (filterable)
@router.get("/", response_model=List[Event])
def list_events(
    complex_name: Optional[str] = Query(None),
    unit: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    session: Session = Depends(get_session)
):
    query = select(Event)
    if complex_name:
        query = query.where(Event.complex == complex_name)
    if unit:
        query = query.where(Event.unit == unit)
    if category:
        query = query.where(Event.category == category)
    results = session.exec(query).all()
    return results

# 🔴 DELETE event (admin-only later)
@router.delete("/{event_id}")
def delete_event(event_id: int, session: Session = Depends(get_session)):
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()
    return {"message": f"Event {event_id} deleted"}
