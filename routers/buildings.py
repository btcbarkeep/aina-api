from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from database import get_session
from core.supabase_client import get_supabase_client
from models import Building, BuildingCreate, BuildingRead
from dependencies.auth import get_current_user
from typing import List, Optional
import traceback

router = APIRouter(prefix="/api/v1/buildings", tags=["Buildings"])


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



@router.put("/supabase/{buildings_id}", tags=["Buildings"])
def update_building_supabase(building_id: str, payload: dict):
    """
    Update a building record in Supabase by ID.
    """
    result = update_record("buildings", building_id, payload)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return result["data"]


@router.delete("/supabase/{buildings_id}", tags=["Buildings"])
def delete_building_supabase(building_id: str):
    """
    Delete a building record from Supabase by ID.
    """
buildings"    result = delete_record("buildings", buildings"_id)
    if result["status"] != "ok":
        raise HTTPException(status_code=500, detail=result["detail"])
    return {"status": "deleted", "id": building_id}


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


## sync fix

@router.post("/sync/fix", summary="Auto-sync missing buildings to Supabase")
def fix_building_sync(session: Session = Depends(get_session)):
    """
    Automatically push missing local buildings to Supabase.
    Returns a summary of what was added.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # --- 1️⃣ Fetch from local DB ---
        local_buildings = session.exec(select(Building)).all()
        local_names = {b.name for b in local_buildings}

        # --- 2️⃣ Fetch from Supabase ---
        supa_result = client.table("buildings").select("name").execute()
        supa_names = {row["name"] for row in supa_result.data or []}

        # --- 3️⃣ Determine missing ones ---
        missing = [b for b in local_buildings if b.name not in supa_names]

        if not missing:
            return {
                "status": "ok",
                "message": "All buildings are already synced with Supabase.",
                "added": 0
            }

        # --- 4️⃣ Push missing to Supabase ---
        inserted = []
        for b in missing:
            payload = {
                "name": b.name,
                "address": b.address,
                "city": b.city,
                "state": b.state,
                "zip": b.zip,
                "created_at": b.created_at.isoformat()
            }
            result = client.table("buildings").insert(payload).execute()
            if result.data:
                inserted.append(b.name)

        # --- 5️⃣ Summary report ---
        return {
            "status": "ok",
            "message": f"Inserted {len(inserted)} missing buildings into Supabase.",
            "inserted": inserted
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-sync failed: {e}")


## reverse sync (from supabase to local)

@router.post("/sync/reverse", summary="Pull missing buildings from Supabase into local DB")
def reverse_building_sync(session: Session = Depends(get_session)):
    """
    Pull any building records that exist in Supabase but not in the local DB.
    Useful for keeping your local data mirror up to date.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # --- 1️⃣ Fetch from local DB ---
        local_buildings = session.exec(select(Building)).all()
        local_names = {b.name for b in local_buildings}

        # --- 2️⃣ Fetch from Supabase ---
        supa_result = client.table("buildings").select("*").execute()
        supa_data = supa_result.data or []
        supa_names = {row["name"] for row in supa_data}

        # --- 3️⃣ Identify records missing locally ---
        missing = [row for row in supa_data if row["name"] not in local_names]

        if not missing:
            return {
                "status": "ok",
                "message": "Local DB is already up to date with Supabase.",
                "added": 0
            }

        # --- 4️⃣ Insert missing buildings into local DB ---
        added = []
        for row in missing:
            new_building = Building(
                name=row.get("name"),
                address=row.get("address"),
                city=row.get("city"),
                state=row.get("state"),
                zip=row.get("zip"),
            )
            session.add(new_building)
            added.append(row.get("name"))

        session.commit()

        # --- 5️⃣ Return summary ---
        return {
            "status": "ok",
            "message": f"Inserted {len(added)} buildings from Supabase into local DB.",
            "inserted": added
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reverse sync failed: {e}")


# master sync endpoint

def run_full_building_sync(session: Session):
    """
    Internal helper for performing full sync.
    Can be safely called by scheduler or API route.
    """
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # --- 1️⃣ Fetch all buildings from both sources ---
        local_buildings = session.exec(select(Building)).all()
        local_names = {b.name for b in local_buildings}

        supa_result = client.table("buildings").select("*").execute()
        supa_data = supa_result.data or []
        supa_names = {row["name"] for row in supa_data}

        # --- 2️⃣ Detect differences ---
        missing_in_supa = [b for b in local_buildings if b.name not in supa_names]
        missing_in_local = [row for row in supa_data if row["name"] not in local_names]

        inserted_to_supa, inserted_to_local = [], []

        # --- 3️⃣ Push missing local → Supabase ---
        for b in missing_in_supa:
            payload = {
                "name": b.name,
                "address": b.address,
                "city": b.city,
                "state": b.state,
                "zip": b.zip,
                "created_at": b.created_at.isoformat(),
            }
            result = client.table("buildings").insert(payload).execute()
            if result.data:
                inserted_to_supa.append(b.name)

        # --- 4️⃣ Pull missing Supabase → local DB ---
        for row in missing_in_local:
            new_building = Building(
                name=row.get("name"),
                address=row.get("address"),
                city=row.get("city"),
                state=row.get("state"),
                zip=row.get("zip"),
            )
            session.add(new_building)
            inserted_to_local.append(row.get("name"))

        session.commit()

        # --- 5️⃣ Return unified summary ---
        return {
            "status": "ok",
            "summary": {
                "local_total": len(local_buildings),
                "supa_total": len(supa_data),
                "inserted_to_supabase": inserted_to_supa,
                "inserted_to_local": inserted_to_local,
            },
            "message": f"Sync complete — {len(inserted_to_supa)} added to Supabase, {len(inserted_to_local)} added to local DB."
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full sync failed: {e}")



@router.post("/sync/full", summary="Fully synchronize buildings between local DB and Supabase")
async def full_building_sync(session: Session = Depends(get_session)):
    """
    API route version of the full sync.
    Simply wraps the internal sync logic for Swagger/manual calls.
    """
    return run_full_building_sync(session)




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
def update_building_local(building_id: int, payload: dict, session: Session = Depends(get_session)):
    """
    Update a building record in the local database.
    Example: change name, address, or other fields.
    """
    building = session.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    # Apply updates dynamically
    for key, value in payload.items():
        if hasattr(building, key):
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

