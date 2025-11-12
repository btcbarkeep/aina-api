# routers/sync.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError
from datetime import datetime

from core.auth import get_current_user  # if you already use this
from core.notifications import send_email
from core.scheduler import run_scheduled_sync  # ✅ FIXED IMPORT

router = APIRouter(
    prefix="/api/v1/sync",
    tags=["Sync"],
)

@router.post("/run")
async def trigger_full_sync(current_user: dict = Depends(get_current_user)):
    """
    Manually trigger the Supabase ↔ local database sync.
    Sends a summary email on completion.
    """
    try:
        print("[SYNC] Manual sync triggered at", datetime.utcnow())

        # Run the scheduler’s sync logic
        run_scheduled_sync()

        return JSONResponse(
            content={
                "status": "success",
                "message": "Manual sync completed successfully.",
                "summary": None
            },
            status_code=200,
        )

    except JWTError:
        raise HTTPException(status_code=403, detail="Not authenticated")

    except Exception as e:
        print("[SYNC] Sync failed:", e)
        send_email(
            subject="[Aina Protocol] Sync Failed ❌",
            body=f"Manual sync failed.\n\nError: {e}",
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
