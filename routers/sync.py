# routers/sync.py
from fastapi import APIRouter, Depends, HTTPException
from dependencies.auth import get_current_user, CurrentUser
from core.scheduler import scheduled_full_sync

router = APIRouter(
    prefix="/sync",
    tags=["Sync"],
)

@router.post("/run", summary="Run full sync now (manual trigger)")
async def run_sync(current_user: CurrentUser = Depends(get_current_user)):
    """
    Manually trigger the Supabase ↔ local database sync.
    Requires admin authentication.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")

    try:
        summary = scheduled_full_sync()
        return {
            "status": "success",
            "message": "Manual sync completed successfully.",
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
