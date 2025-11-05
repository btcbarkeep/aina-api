from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session, create_db_and_tables
from models import Event, EventCreate, EventRead

router = APIRouter()

@router.post("", response_model=EventRead)
def create_event(payload: EventCreate, session: Session = Depends(get_session)):
    e = Event.from_orm(payload)
    session.add(e)
    session.commit()
    session.refresh(e)
    return e

@router.get("", response_model=List[EventRead])
def list_events(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    q = select(Event).offset(offset).limit(min(limit, 200))
    return session.exec(q).all()

@router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: int, session: Session = Depends(get_session)):
    e = session.get(Event, event_id)
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    return e
