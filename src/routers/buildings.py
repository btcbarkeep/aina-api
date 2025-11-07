from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from src.database import get_session
from src.models import Building, BuildingCreate, BuildingRead

router = APIRouter(tags=["Buildings"])

# 🏗️ Create a new building
@router.post("/", response_model=BuildingRead)
def create_building(payload: BuildingCreate, session: Session = Depends(get_session)):
    """
    Create a new building record in the database.
    """
    building = Building.from_orm(payload)
    session.add(building)
    session.commit()
    session.refresh(building)
    return building


# 🏢 List all buildings
@router.get("/", response_model=List[BuildingRead])
def list_buildings(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    """
    Retrieve a paginated list of all buildings.
    """
    query = select(Building).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


# 🏠 Get a single building by ID
@router.get("/{building_id}", response_model=BuildingRead)
def get_building(building_id: int, session: Session = Depends(get_session)):
    """
    Retrieve a single building by its ID.
    """
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building
