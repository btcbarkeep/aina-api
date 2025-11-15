# routers/sync.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError
from datetime import datetime
import traceback

from dependencies.auth import get_current_user
from core.notifications import send_email
from core.utils.sync_formatter import format_sync_summary
from database import get_session

from sqlmodel import Session, select
from models import Building

router = APIRouter(
    prefix="/api/v1/sync",
    tags=["Sync"],
)

# --------------------------------------------------------
# BUILDINGS SYNC (COMPARE / FIX / REVERSE)
# --------------------------------------------------------

@router.get("/buildings", summary="Compare Local vs Supabase Buildings")
def compare_building_sync(session: Session = Depends(get_session)):
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()

    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local = session.exec(select(Building)).all()
        local_names = {b.name for b in local}

        supabase = client.table("buildings").select("name").execute()
        supa_names = {row["name"] for row in (supabase.data or [])}

        return {
            "status": "ok",
            "summary": {
                "local_only": sorted(list(local_names - supa_names)),
                "supabase_only": sorted(list(supa_names - local_names)),
                "synced": sorted(list(local_names & supa_names)),
            },
            "local_total": len(local_names),
            "supabase_total": len(supa_names),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync comparison failed: {e}")


@router.post("/buildings/fix", summary="Push missing local buildings → Supabase")
def fix_building_sync(session: Session = Depends(get_session)):
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()

    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_rows = session.exec(select(Building)).all()
        local_names = {b.name for b in local_rows}

        supa_data = client.table("buildings").select("name").execute().data or []
        supa_names = {row["name"] for row in supa_data}

        missing = [b for b in local_rows if b.name not in supa_names]

        inserted = []
        for b in missing:
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
                inserted.append(b.name)

        return {"status": "ok", "inserted": inserted, "count": len(inserted)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-sync failed: {e}")


@router.post("/buildings/reverse", summary="Pull missing Supabase buildings → Local DB")
def reverse_building_sync(session: Session = Depends(get_session)):
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()

    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_rows = session.exec(select(Building)).all()
        local_names = {b.name for b in local_rows}

        supa_rows = client.table("buildings").select("*").execute().data or []
        supa_names = {row["name"] for row in supa_rows}

        missing = [row for row in supa_rows if row["name"] not in local_names]

        added = []
        for row in missing:
            new_b = Building(
                name=row["name"],
                address=row.get("address"),
                city=row.get("city"),
                state=row.get("state"),
                zip=row.get("zip"),
            )
            session.add(new_b)
            added.append(row["name"])

        session.commit()

        return {"status": "ok", "inserted": added, "count": len(added)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reverse sync failed: {e}")


# --------------------------------------------------------
# INTERNAL MASTER SYNC FOR BUILDINGS
# --------------------------------------------------------

def run_full_building_sync(session: Session):
    from core.supabase_client import get_supabase_client
    client = get_supabase_client()

    if not client:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        local_rows = session.exec(select(Building)).all()
        local_names = {b.name for b in local_rows}

        supa_rows = client.table("buildings").select("*").execute().data or []
        supa_names = {row["name"] for row in supa_rows}

        missing_supa = [b for b in local_rows if b.name not in supa_names]
        missing_local = [row for row in supa_rows if row["name"] not in local_names]

        inserted_supa = []
        inserted_local = []

        # local → supabase
        for b in missing_supa:
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
                inserted_supa.append(b.name)

        # supabase → local
        for row in missing_local:
            new_b = Building(
                name=row["name"],
                address=row.get("address"),
                city=row.get("city"),
                state=row.get("state"),
                zip=row.get("zip"),
            )
            session.add(new_b)
            inserted_local.append(row["name"])

        session.commit()

        return {
            "status": "ok",
            "summary": {
                "inserted_to_supabase": inserted_supa,
                "inserted_to_local": inserted_local,
            },
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Full sync failed: {e}")


# --------------------------------------------------------
# EVENTS + DOCUMENTS SYNC (imported helpers ONLY)
# --------------------------------------------------------

from routers.events import run_full_event_sync
from routers.documents import run_full_document_sync


# --------------------------------------------------------
# GLOBAL FULL SYNC (BUILDINGS + EVENTS + DOCUMENTS)
# --------------------------------------------------------

async def perform_sync_logic():
    try:
        print("[SYNC] Running full sync logic...")

        session_gen = get_session()
        session = next(session_gen)

        building_result = run_full_building_sync(session)
        event_result = run_full_event_sync(session)
        document_result = run_full_document_sync(session)

        return {
            "status": "success",
            "summary": {
                "buildings": building_result.get("summary", {}),
                "events": event_result.get("summary", {}),
                "documents": document_result.get("summary", {}),
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "summary": traceback.format_exc(),
        }

    finally:
        try:
            session.close()
        except:
            pass


@router.post("/run", summary="Trigger FULL sync (Buildings + Events + Documents)")
async def trigger_full_sync(current_user: dict = Depends(get_current_user)):
    start_time = datetime.utcnow()
    result = await perform_sync_logic()
    end_time = datetime.utcnow()

    duration = (end_time - start_time).total_seconds()

    if result["status"] == "success":
        formatted = format_sync_summary(
            summary=result["summary"],
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            title="Manual Sync",
        )

        send_email(
            subject="[Aina Protocol] Manual Sync Completed",
            body=f"Sync completed successfully.\n\n{formatted}",
        )

    else:
        send_email(
            subject="[Aina Protocol] Sync Failed ❌",
            body=f"Error: {result.get('message')}\n\nTraceback:\n{result.get('summary')}",
        )

    return JSONResponse(content=result)
