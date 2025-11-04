from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from database import get_session, create_db_and_tables
from models import Building, BuildingCreate, BuildingRead

router = APIRouter(prefix="/buildings", tags=["buildings"])

@router.on_event("startup")
def startup() -> None:
    create_db_and_tables()

@router.post("", response_model=BuildingRead)
def create_building(payload: BuildingCreate, session: Session = Depends(get_session)):
    b = Building.from_orm(payload)
    session.add(b)
    session.commit()
    session.refresh(b)
    return b

@router.get("/{building_id}", response_model=BuildingRead)
def get_building(building_id: int, session: Session = Depends(get_session)):
    b = session.get(Building, building_id)
    if not b:
        raise HTTPException(status_code=404, detail="Building not found")
    return b

@router.get("", response_model=List[BuildingRead])
def list_buildings(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    q = select(Building).offset(offset).limit(min(limit, 200))
    return session.exec(q).all()
