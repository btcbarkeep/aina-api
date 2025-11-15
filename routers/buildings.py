from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
import traceback

from database import get_session
from dependencies.auth import get_current_user

from models import (
    Building,
    BuildingCreate,
    BuildingRead,
    BuildingUpdate,
)

from core.supabase_client import get_supabase_client
from core.supabase_helpers import update_record, delete_record


router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
)


"""
Building endpoints manage AOAO property data, including creation,
Supabase sync endpoints, and clean CRUD for local DB usage.
"""


# -----------------------------------------------------
# SUPABASE INTEGRATION
# -----------------------------------------------------

@router.get("/supabase", summary="List Buildings from Supabase")
def list_buildings_supabase(
    limit: int = 50,
    name: str | None = None,
    city: str | None = None,
    state: str | None = None,
):
    """
    Fetch buildings directly from Supabase for debugging.
    Supports optional filters.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        query = client.table("buildings").select("*").limit(limit)

        if name:
            query = query.ilike("name", f"%{name}%")
        if city:
            query = query.ilike("city", f"%{city}%")
        if state:
            query = query.ilike("state", f"%{state}%")

        result = query.execute()
        return result.data or []

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase fetch error: {e}")


@router.post(
    "/supabase",
    response_model=BuildingRead,
    summary="Create or Upsert Building in Supabase",
)
def create_building_supabase(payload: BuildingCreate):
    """
    Insert or update a building in Supabase (protect against duplicates).
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        data = payload.dict()

        result = client.table("buildings").upsert(
            data,
            on_conflict="name"
        ).execute()

        if not result.data:
            return {
                "status": "warning",
                "message": f"Building '{payload.name}' already exists.",
            }

        return result.data[0]

    except Exception as e:
        msg = str(e)
        if "duplicate key value" in msg.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Building '{payload.name}' already exists in Supabase."
            )
        raise HTTPException(status_code=500, detail=f"Supabase upsert error: {msg}")


@router.put("/supabase/{building_id}", summary="Update Building in Supabase")
def update_building_supabase(building_id: str, payload: BuildingUpdate):
    update_data = payload.dict(exclude_unset=True)

    result = update_record("buildings", building_id, update_data)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return result["data"]


@router.delete("/supabase/{building_id}", summary="Delete Building in Supabase")
def delete_building_supabase(building_id: str):
    result = delete_record("buildings", building_id)

    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])

    return {"status": "deleted", "id": building_id}


# -----------------------------------------------------
# LOCAL DATABASE CRUD
# -----------------------------------------------------

@router.post(
    "/",
    response_model=BuildingRead,
    dependencies=[Depends(get_current_user)],
    summary="Create Building (Local DB)"
)
def create_building_local(payload: BuildingCreate, session: Session = Depends(get_session)):
    existing = session.exec(
        select(Building).where(Building.name == payload.name)
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Building '{payload.name}' already exists."
        )

    building = Building.from_orm(payload)
    session.add(building)
    session.commit()
    session.refresh(building)
    return building


@router.put(
    "/{building_id}",
    response_model=BuildingRead,
    summary="Update Building (Local DB)"
)
def update_building_local(
    building_id: int,
    payload: BuildingUpdate,
    session: Session = Depends(get_session)
):
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(building, key, value)

    session.commit()
    session.refresh(building)

    return building


@router.get("/", response_model=List[BuildingRead], summary="List Local Buildings")
def list_buildings_local(
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session)
):
    return session.exec(
        select(Building).offset(offset).limit(min(limit, 200))
    ).all()


@router.get("/{building_id}", response_model=BuildingRead, summary="Get Building by ID")
def get_building(building_id: int, session: Session = Depends(get_session)):
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building


# -----------------------------------------------------
# SYNC ENTRYPOINT FOR FUTURE USE (clean + optional)
# -----------------------------------------------------

@router.post(
    "/sync",
    response_model=BuildingRead,
    summary="Create Building (Local + Supabase Sync)",
    tags=["Sync"]
)
def create_building_sync(payload: BuildingCreate, session: Session = Depends(get_session)):
    """
    Create in local DB and sync to Supabase.
    Clean, optional, and ONLY used for controlled migrations.
    """
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # local insert
        building = Building.from_orm(payload)
        session.add(building)
        session.commit()
        session.refresh(building)

        # supabase sync
        result = client.table("buildings").insert(payload.dict()).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Supabase sync failed")

        return building

    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
