# routers/sync.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from jose import JWTError
from datetime import datetime
import traceback

from dependencies.auth import get_current_user
from core.notifications import send_email
from database import get_session

router = APIRouter(
    prefix="/api/v1/sync",
    tags=["Sync"],
)


async def perform_sync_logic():
    """
    Runs full sync for Buildings, Events, and Documents.
    Returns unified summary used by both scheduler and manual trigger.
    """
    try:
        print("[SYNC] Running full sync logic (buildings + events + documents)...")

        from routers.buildings import run_full_building_sync
        from routers.events import run_full_event_sync
        from routers.documents import run_full_document_sync

        # ✅ Create a real session (not Depends)
        session_gen = get_session()
        session = next(session_gen)

        # --- Run all syncs ---
        building_result = run_full_building_sync(session)
        event_result = run_full_event_sync(session)
        document_result = run_full_document_sync(session)

        print("[SYNC] ✅ Full sync (all modules) completed successfully.")

        return {
            "status": "success",
            "message": "Full sync completed successfully.",
            "summary": {
                "buildings": building_result.get("summary", {}),
                "events": event_result.get("summary", {}),
                "documents": document_result.get("summary", {}),
            },
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
    Returns a unified summary and sends a formatted email like the daily sync.
    """
    try:
        start_time = datetime.utcnow()
        print("[SYNC] Manual sync triggered at", start_time)

        result = await perform_sync_logic()
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # --- Success Case ---
        if result["status"] == "success":
            summary = result.get("summary", {})

            building_summary = summary.get("buildings", {})
            event_summary = summary.get("events", {})
            document_summary = summary.get("documents", {})

            formatted_summary = (
                f"📋 **Aina Protocol Manual Sync Report**\n\n"
                f"🕒 **Summary**\n"
                f"• Start: {start_time}\n"
                f"• End: {end_time}\n"
                f"• Duration: {duration:.2f} seconds\n\n"
                f"🏢 **Buildings Sync**\n"
                f"• Local: {building_summary.get('local_total', 'N/A')}\n"
                f"• Supabase: {building_summary.get('supa_total', 'N/A')}\n"
                f"• Added → Supabase: {len(building_summary.get('inserted_to_supabase', []))}\n"
                f"• Added → Local: {len(building_summary.get('inserted_to_local', []))}\n\n"
                f"📅 **Events Sync**\n"
                f"• Local: {event_summary.get('local_total', 'N/A')}\n"
                f"• Supabase: {event_summary.get('supa_total', 'N/A')}\n"
                f"• Added → Supabase: {len(event_summary.get('inserted_to_supabase', []))}\n"
                f"• Added → Local: {len(event_summary.get('inserted_to_local', []))}\n\n"
                f"📄 **Documents Sync**\n"
                f"• Local: {document_summary.get('local_total', 'N/A')}\n"
                f"• Supabase: {document_summary.get('supa_total', 'N/A')}\n"
                f"• Added → Supabase: {len(document_summary.get('inserted_to_supabase', []))}\n"
                f"• Added → Local: {len(document_summary.get('inserted_to_local', []))}\n\n"
                f"💬 **Message**\n"
                f"{result.get('message', 'Sync completed successfully.')}\n"
            )

            send_email(
                subject="[Aina Protocol] Manual Sync Completed ✅",
                body=f"✅ Manual sync completed successfully.\n\n{formatted_summary}",
            )

            print("[SYNC] ✅ Manual sync email sent successfully.")

        # --- Failure Case ---
        else:
            send_email(
                subject="[Aina Protocol] Manual Sync Failed ❌",
                body=(
                    f"❌ Manual sync failed.\n\n"
                    f"Error: {result.get('message', 'Unknown error')}\n\n"
                    f"Traceback:\n{result.get('summary', '')}"
                ),
            )
            print("[SYNC] ❌ Manual sync failed — email sent with error details.")

        return JSONResponse(content=result, status_code=200)

    except JWTError:
        raise HTTPException(status_code=403, detail="Not authenticated")

    except Exception as e:
        print("[SYNC] 💥 Unexpected error:", e)
        send_email(
            subject="[Aina Protocol] Sync Failed ❌",
            body=f"Manual sync failed unexpectedly.\n\nError: {e}",
        )
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
