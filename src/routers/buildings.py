from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from src.database import get_session
from src.models import Building, BuildingCreate, BuildingRead
from src.routers.dependencies import get_current_user

router = APIRouter(prefix="/buildings", tags=["Buildings"])

# 🏗️ Create (admin only)
@router.post("/", response_model=BuildingRead)
def create_building(
    payload: BuildingCreate,
    session: Session = Depends(get_session),
    current_user: str = Depends(get_current_user)
):
    building = Building.from_orm(payload)
    session.add(building)
    session.commit()
    session.refresh(building)
    return building

# 🏢 List (public)
@router.get("/", response_model=List[BuildingRead])
def list_buildings(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    query = select(Building).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()

# 🏠 Get by ID (public)
@router.get("/{building_id}", response_model=BuildingRead)
def get_building(building_id: int, session: Session = Depends(get_session)):
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building
