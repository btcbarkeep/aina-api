# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback
import asyncio

from core.notifications import send_email

def run_scheduled_sync():
    """Runs the sync and emails the results."""
    start_time = datetime.utcnow()
    try:
        print("[SCHEDULER] Starting full sync...")

        # ✅ Lazy import to avoid circular dependency
        from routers import sync  

        # Run the async sync function properly
        result = asyncio.run(sync.run_sync())

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Build summary report
        summary_text = (
            f"🗓️ **Sync Summary**\n"
            f"- Start Time (UTC): {start_time}\n"
            f"- End Time (UTC): {end_time}\n"
            f"- Duration: {duration:.2f} seconds\n\n"
            f"📊 **Details:**\n"
            f"{result.get('summary', 'No summary provided')}\n\n"
            f"💬 **Message:**\n"
            f"{result.get('message', 'No message returned')}\n"
        )

        send_email(
            subject="[Aina Protocol] Daily Sync Completed ✅",
            body=f"✅ Sync completed successfully.\n\n{summary_text}",
        )

        print("[SCHEDULER] ✅ Sync completed successfully and email sent.")

    except Exception as e:
        print("[SCHEDULER] ❌ Sync failed:", e)
        send_email(
            subject="[Aina Protocol] Sync Failed ❌",
            body=f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}",
        )

def start_scheduler():
    """
    Initialize the APScheduler background process.
    Runs the sync job daily at 03:00 UTC (adjust as needed).
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    # Schedule job daily at 03:00 UTC (midnight HST = 13:00 UTC)
    scheduler.add_job(
        run_scheduled_sync,  # ✅ corrected function name
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
