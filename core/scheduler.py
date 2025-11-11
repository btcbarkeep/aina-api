# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback

from core.notifications import send_email

def scheduled_full_sync():
    from routers.sync import run_sync  # local import to avoid circular deps
    try:
        summary = run_full_sync()
        print("✅ Sync completed successfully:", summary)

        # Send email summary
        subject = "Aina Protocol – Daily Sync Summary"
        body = f"""
        ✅ Sync Completed Successfully!

        Local Records Updated: {summary.get('local_updated', 0)}
        Supabase Records Updated: {summary.get('supabase_updated', 0)}
        New Records: {summary.get('new_records', 0)}
        Errors: {summary.get('errors', 0)}
        """
        send_email(subject, body)

    except Exception as e:
        print("❌ Sync failed:", e)
        send_email("❌ Aina Protocol Sync Failed", str(e))



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
