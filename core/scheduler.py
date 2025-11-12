# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback

from core.notifications import send_email

import asyncio
from routers.sync import run_sync

def run_scheduled_sync():
    """Runs the sync and emails the results."""
    try:
        print("[SCHEDULER] Starting full sync...")
        
        # ✅ Run the async sync function properly
        summary = asyncio.run(run_sync())

        message = (
            f"✅ Sync completed successfully.\n"
            f"Message: {summary.get('message', 'No message')}\n"
            f"Summary: {summary.get('summary', 'No summary')}"
        )

        send_email(
            subject="[Aina Protocol] Daily Sync Completed ✅",
            body=message,
        )

        print("[SCHEDULER] Sync email sent successfully.")

    except Exception as e:
        print("[SCHEDULER] Sync failed:", e)
        send_email(
            subject="[Aina Protocol] Sync Failed ❌",
            body=f"Error: {e}",
        )



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
