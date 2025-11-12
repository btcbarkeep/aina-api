# routers/sync.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError
from datetime import datetime
import traceback

from dependencies.auth import get_current_user
from core.notifications import send_email
from database import get_session  # ✅ add this

router = APIRouter(
    prefix="/api/v1/sync",
    tags=["Sync"],
)


async def perform_sync_logic():
    """
    Core sync logic used by both the scheduler and manual trigger.
    Returns a dictionary summarizing the sync.
    """
    try:
        print("[SYNC] Running full sync logic...")

        from routers.buildings import run_full_building_sync  # ✅ use the non-async version

        # ✅ Create a real session (not Depends)
        session_gen = get_session()
        session = next(session_gen)

        summary = run_full_building_sync(session)

        print("[SYNC] ✅ Sync completed successfully.")

        return {
            "status": "success",
            "message": "Sync completed successfully.",
            "summary": summary or "No summary returned."
        }

    except Exception as e:
        print("[SYNC] ❌ Sync failed:", e)
        return {
            "status": "error",
            "message": f"500: {str(e)}",
            "summary": traceback.format_exc(),
        }

    finally:
        # ✅ Always close the session
        try:
            session.close()
        except Exception:
            pass


@router.post("/run")
async def trigger_full_sync(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger the Supabase ↔ local database sync.
    Returns a summary and sends an email.
    """
    try:
        print("[SYNC] Manual sync triggered at", datetime.utcnow())

        result = await perform_sync_logic()

        # ✅ Email summary
        if result["status"] == "success":
            send_email(
                subject="[Aina Protocol] Manual Sync Completed ✅",
                body=(
                    f"✅ Manual sync completed successfully.\n\n"
                    f"🗓️ Time: {datetime.utcnow()}\n\n"
                    f"📊 Summary:\n{result.get('summary', 'No summary')}"
                ),
            )
        else:
            send_email(
                subject="[Aina Protocol] Manual Sync Failed ❌",
                body=(
                    f"❌ Manual sync failed.\n\n"
                    f"Error: {result.get('message', 'Unknown error')}\n\n"
                    f"Traceback:\n{result.get('summary', '')}"
                ),
            )

        return JSONResponse(content=result, status_code=200)

    except JWTError:
        raise HTTPException(status_code=403, detail="Not authenticated")

    except Exception as e:
        print("[SYNC] Unexpected error:", e)
        send_email(
            subject="[Aina Protocol] Sync Failed ❌",
            body=f"Manual sync failed.\n\nError: {e}",
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
