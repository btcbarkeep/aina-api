# routers/buildings.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from database import get_session
from models import Building, BuildingCreate, BuildingRead
from dependencies.auth import get_current_user

router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"],
)

"""
Building endpoints manage property data for AOAOs and complexes, including creation,
listing, and retrieval of registered building information.
"""



@router.post("/", response_model=BuildingRead, dependencies=[Depends(get_current_user)])
def create_building(payload: BuildingCreate, session: Session = Depends(get_session)):
    """Create a new building (protected)."""
    building = Building.from_orm(payload)
    session.add(building)
    session.commit()
    session.refresh(building)
    return building


@router.get("/", response_model=List[BuildingRead])
def list_buildings(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    """List all buildings (public)."""
    query = select(Building).offset(offset).limit(min(limit, 200))
    return session.exec(query).all()


@router.get("/{building_id}", response_model=BuildingRead)
def get_building(building_id: int, session: Session = Depends(get_session)):
    """Get a building by ID (public)."""
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building


# Supabase integration
from core.supabase_helpers import fetch_all, insert_record, update_record, delete_record


@router.get("/supabase", tags=["Supabase Buildings"])
def list_buildings_supabase(limit: int = 50):
    """
    Fetch building data directly from Supabase.
    This is useful for debugging and verifying Supabase sync.
    """
    result = fetch_all("buildings", limit=limit)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return result["data"]


@router.post("/supabase", tags=["Supabase Buildings"])
def create_building_supabase(payload: dict):
    """
    Insert a new building record into Supabase.
    """
    result = insert_record("buildings", payload)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return result["data"]


@router.put("/supabase/{building_id}", tags=["Supabase Buildings"])
def update_building_supabase(building_id: str, payload: dict):
    """
    Update a building record in Supabase by ID.
    """
    result = update_record("buildings", building_id, payload)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return result["data"]


@router.delete("/supabase/{building_id}", tags=["Supabase Buildings"])
def delete_building_supabase(building_id: str):
    """
    Delete a building record from Supabase by ID.
    """
    result = delete_record("buildings", building_id)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return {"status": "deleted", "id": building_id}

