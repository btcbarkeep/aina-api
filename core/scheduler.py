# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback

from core.notifications import send_email
from core.utils.sync_formatter import format_sync_summary  # ✅ NEW IMPORT
from database import get_session
from routers.buildings import run_full_building_sync
from routers.events import run_full_event_sync
from routers.documents import run_full_document_sync


def run_scheduled_sync():
    """Runs full sync for Buildings, Events, and Documents, then emails the results."""
    start_time = datetime.utcnow()
    try:
        print("[SCHEDULER] Starting full sync (Buildings + Events + Documents)...")

        # ✅ Create a database session manually
        session_gen = get_session()
        session = next(session_gen)

        # -------------------------------------------------
        # Run each sync module
        # -------------------------------------------------
        building_result = run_full_building_sync(session)
        event_result = run_full_event_sync(session)
        document_result = run_full_document_sync(session)

        # -------------------------------------------------
        # Build summary dictionary
        # -------------------------------------------------
        summary = {
            "buildings": building_result.get("summary", {}),
            "events": event_result.get("summary", {}),
            "documents": document_result.get("summary", {}),
        }

        # -------------------------------------------------
        # Build unified report using shared formatter
        # -------------------------------------------------
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        formatted_summary = format_sync_summary(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            title="Daily Sync"
        )

        # -------------------------------------------------
        # Send Report Email
        # -------------------------------------------------
        send_email(
            subject="[Aina Protocol] Daily Sync Completed ✅",
            body=f"✅ Daily sync completed successfully.\n\n{formatted_summary}",
        )

        print("[SCHEDULER] ✅ Daily sync completed successfully and email sent.")

    except Exception as e:
        print("[SCHEDULER] ❌ Sync failed:", e)
        send_email(
            subject="[Aina Protocol] Daily Sync Failed ❌",
            body=f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}",
        )

    finally:
        # ✅ Always close session
        try:
            session.close()
        except Exception:
            pass


def start_scheduler():
    """
    Initialize the APScheduler background process.
    Runs the sync job daily at 03:00 UTC (midnight HST ≈ 17:00 HST).
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    # 🗓️ Schedule job daily
    scheduler.add_job(
        run_scheduled_sync,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_sync_job",
        replace_existing=True,
    )

    # 🧪 Optional: Run once immediately on startup (for testing)
    scheduler.add_job(run_scheduled_sync, trigger='date', run_date=datetime.utcnow())

    scheduler.start()
    print("⏰ Scheduler started. Daily sync set for 03:00 UTC.")


if __name__ == "__main__":
    print("🧪 Running scheduler manually...")
    run_scheduled_sync()

    # Keep alive for local manual testing
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped.")
