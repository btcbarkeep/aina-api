from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from core.supabase_client import get_supabase_client
from models import Building, BuildingCreate, BuildingRead
from dependencies.auth import get_current_user
from typing import List, Optional
import traceback

router = APIRouter(
    prefix="/buildings",
    tags=["Buildings"]
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



@router.post("/supabase", response_model=BuildingRead, summary="Create or Upsert Building in Supabase")
def create_building_supabase(payload: BuildingCreate):
    """
    Insert or update a building record directly into Supabase.
    Prevents duplicates and provides clear feedback.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        data = payload.dict()

        # ✅ Use upsert on "name" to prevent duplicates
        result = client.table("buildings").upsert(data, on_conflict="name").execute()

        if not result.data:
            return {
                "status": "warning",
                "message": f"Building '{payload.name}' already exists or no changes detected.",
            }

        inserted = result.data[0]
        print(f"[SUPABASE] ✅ Buildings synced: {inserted['name']} (ID: {inserted.get('id', 'unknown')})")

        return inserted

    except Exception as e:
        error_msg = str(e)
        print(f"[SUPABASE] ❌ Error upserting building: {error_msg}")

        if "duplicate key value" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail=f"Building '{payload.name}' already exists in Supabase."
            )

        raise HTTPException(status_code=500, detail=f"Supabase upsert error: {error_msg}")



@router.put("/supabase/{building_id}", tags=["Buildings"])
def update_building_supabase(building_id: str, payload: BuildingUpdate):
    """
    Update a building record in Supabase by ID.
    """
    update_data = payload.dict(exclude_unset=True)

    result = update_record("buildings", building_id, update_data)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    
    return result["data"]



@router.delete("/supabase/{building_id}")
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
    """Create a new building (protected). Prevents duplicates by name."""
    # ✅ Check if a building with the same name already exists
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


@router.put("/{building_id}", response_model=BuildingRead, summary="Update Building (Local DB)")
def update_building_local(
    building_id: int,
    payload: BuildingUpdate,
    session: Session = Depends(get_session)
):
    """
    Update a building record in the local database.
    Example: change name, address, or other fields.
    """
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    # Apply updates
    update_data = payload.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(building, key, value)

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

@router.post("/sync", response_model=BuildingRead, summary="Create Building (Local + Supabase Sync)", tags=["Sync"])
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

