# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback

from core.notifications import send_email, send_webhook_message
from routers.buildings import full_building_sync
from database import get_session


def scheduled_full_sync():
    """
    Daily scheduled sync job.
    Pulls data from local + Supabase and syncs both directions.
    Sends a summary notification after each run.
    """
    print(f"[SYNC JOB] Running scheduled sync at {datetime.utcnow().isoformat()}")
    try:
        # Open session
        with next(get_session()) as session:
            result = full_building_sync(session=session)

        # Create readable summary
        summary = (
            f"✅ **Aina Protocol Daily Sync Completed**\n\n"
            f"**Local Total:** {result['summary']['local_total']}\n"
            f"**Supabase Total:** {result['summary']['supa_total']}\n"
            f"**Added → Supabase:** {len(result['summary']['inserted_to_supabase'])}\n"
            f"**Added → Local:** {len(result['summary']['inserted_to_local'])}\n"
            f"\n🕒 Timestamp: {datetime.utcnow().isoformat()} UTC"
        )

        print("[SYNC JOB] ✅ Sync successful. Sending notifications...")
        send_webhook_message(summary)
        send_email("Aina Protocol Sync ✅", summary)

    except Exception as e:
        print("[SYNC JOB] ❌ Sync failed:", e)
        traceback.print_exc()

        error_summary = f"❌ Aina Protocol Sync Failed:\n\n{e}"
        send_webhook_message(error_summary)
        send_email("Aina Protocol Sync ❌ FAILED", error_summary)


def start_scheduler():
    """
    Initialize the APScheduler background process.
    Runs the sync job daily at 03:00 UTC (adjust as needed).
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    # Schedule job daily at 03:00 UTC (midnight HST = 13:00 UTC)
    scheduler.add_job(
        scheduled_full_sync,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_sync_job",
        replace_existing=True,
    )

    scheduler.start()
    print("⏰ Scheduler started. Daily sync set for 03:00 UTC.")


if __name__ == "__main__":
    # Manual run mode (for testing)
    print("🧪 Running scheduler manually...")
    start_scheduler()

    # Keep process alive for testing local runs
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped.")
