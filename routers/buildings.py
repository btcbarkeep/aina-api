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


# Supabase integration
from core.supabase_helpers import fetch_all, insert_record, update_record, delete_record


@router.get("/supabase", summary="List Buildings Supabase")
def list_buildings_supabase(
    limit: int = 50,
    name: str | None = None,
    city: str | None = None,
    state: str | None = None,
):
    """
    Fetch building data directly from Supabase for verification and debugging.
    Supports optional filters for name, city, and state.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        query = client.table("buildings").select("*").limit(limit)

        # Optional filters
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



@router.post("/supabase", response_model=BuildingRead, summary="Create Building Supabase")
def create_building_supabase(payload: BuildingCreate):
    """
    Insert a new building record directly into Supabase.
    Uses the same BuildingCreate schema for consistent input.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        result = client.table("buildings").insert(payload.dict()).execute()
        if not result.data:
            raise HTTPException(status_code=500, detail="Insert failed")

        return result.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase insert error: {e}")


@router.put("/supabase/{building_id}", tags=["Buildings"])
def update_building_supabase(building_id: str, payload: dict):
    """
    Update a building record in Supabase by ID.
    """
    result = update_record("buildings", building_id, payload)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return result["data"]


@router.delete("/supabase/{building_id}", tags=["Buildings"])
def delete_building_supabase(building_id: str):
    """
    Delete a building record from Supabase by ID.
    """
    result = delete_record("buildings", building_id)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return {"status": "deleted", "id": building_id}

## Local Database Routes


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


## sync function add to both databases for future migration

@router.post("/sync", response_model=BuildingRead, summary="Create Building (Local + Supabase Sync)")
def create_building_sync(payload: BuildingCreate, session: Session = Depends(get_session)):
    """
    Create a new building and automatically sync to Supabase.
    Ensures both databases are updated or rolls back on failure.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # --- 1️⃣ Create building locally ---
        building = Building.from_orm(payload)
        session.add(building)
        session.commit()
        session.refresh(building)

        # --- 2️⃣ Sync to Supabase ---
        supa_result = client.table("buildings").insert(payload.dict()).execute()

        if not supa_result.data:
            raise HTTPException(status_code=500, detail="Supabase sync failed")

        print(f"[SYNC OK] Local + Supabase record for: {building.name}")
        return building

    except Exception as e:
        # --- 3️⃣ Rollback on failure ---
        session.rollback()
        print(f"[SYNC ERROR] Rolling back local insert: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

## sync checker

@router.get("/sync", summary="Compare Local vs Supabase Buildings")
def compare_building_sync(session: Session = Depends(get_session)):
    """
    Compare local and Supabase building tables to verify synchronization.
    Returns which records exist only in one source.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # --- 1️⃣ Fetch from local database ---
        local_buildings = session.exec(select(Building)).all()
        local_names = {b.name for b in local_buildings}

        # --- 2️⃣ Fetch from Supabase ---
        supa_result = client.table("buildings").select("name").execute()
        supa_names = {row["name"] for row in supa_result.data or []}

        # --- 3️⃣ Compare sets ---
        local_only = sorted(list(local_names - supa_names))
        supabase_only = sorted(list(supa_names - local_names))
        synced = sorted(list(local_names & supa_names))

        # --- 4️⃣ Return sync report ---
        return {
            "status": "ok",
            "summary": {
                "local_count": len(local_names),
                "supabase_count": len(supa_names),
                "synced_count": len(synced),
                "local_only_count": len(local_only),
                "supabase_only_count": len(supabase_only),
            },
            "local_only": local_only,
            "supabase_only": supabase_only,
            "synced": synced,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync comparison failed: {e}")



