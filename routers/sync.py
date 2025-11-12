# routers/sync.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError
from datetime import datetime
import traceback

from dependencies.auth import get_current_user
from core.notifications import send_email

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

        # ✅ Import here to avoid circular import
        from routers.buildings import full_building_sync  

        # Example sync process
        summary = await full_building_sync()

        print("[SYNC] Sync completed successfully.")

        return {
            "status": "success",
            "message": "Sync completed successfully.",
            "summary": summary or "No summary returned."
        }

    except Exception as e:
        print("[SYNC] Sync failed:", e)
        return {
            "status": "error",
            "message": str(e),
            "summary": traceback.format_exc(),
        }


@router.post("/run")
async def trigger_full_sync(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger the Supabase ↔ local database sync.
    Returns a summary and sends an email.
    """
    try:
        print("[SYNC] Manual sync triggered at", datetime.utcnow())

        # Run the main logic directly
        result = await perform_sync_logic()

        # Send email notification
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
