from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session, create_db_and_tables
from models import Event, EventCreate, EventRead, Building

router = APIRouter(prefix="/events", tags=["events"])

@router.on_event("startup")
def startup() -> None:
    create_db_and_tables()

@router.post("", response_model=EventRead)
def create_event(payload: EventCreate, session: Session = Depends(get_session)):
    building = session.get(Building, payload.building_id)
    if not building:
        raise HTTPException(status_code=400, detail="Invalid building_id")
    e = Event.from_orm(payload)
    session.add(e)
    session.commit()
    session.refresh(e)
    return e

@router.get("", response_model=List[EventRead])
def list_events(
    building_id: Optional[int] = None,
    unit_number: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    q = select(Event)
    if building_id is not None:
        q = q.where(Event.building_id == building_id)
    if unit_number:
        q = q.where(Event.unit_number == unit_number)
    q = q.order_by(Event.occurred_at.desc()).offset(offset).limit(min(limit, 200))
    return session.exec(q).all()
