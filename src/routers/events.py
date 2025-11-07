from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from datetime import datetime

from src.database import get_session
from src.models import Event

router = APIRouter(prefix="/events", tags=["Events"])

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
    offset: int = Query(0,
