# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback
import asyncio

from core.notifications import send_email


async def perform_sync_  logic():
    """
    Centralized sync logic. Called by both the scheduler and /sync/run endpoint.
    """
    from routers.sync import trigger_full_sync  # lazy import to prevent circular import
    print("[SCHEDULER] Running sync logic via perform_sync_logic()")
    result = await trigger_full_sync()
    return result


def run_scheduled_sync():
    """Runs the sync and emails the results (safe for async contexts)."""
    start_time = datetime.utcnow()
    try:
        print("[SCHEDULER] Starting full sync...")

        # Get current event loop if running, otherwise create a new one
        try:
            loop = asyncio.get_running_loop()
            print("[SCHEDULER] Using existing asyncio loop...")
            result = loop.create_task(perform_sync_logic())
        except RuntimeError:
            print("[SCHEDULER] Creating new asyncio loop...")
            result = asyncio.run(perform_sync_logic())

        # If a task object is returned (running inside FastAPI loop), wait for completion
        if asyncio.isfuture(result) or isinstance(result, asyncio.Task):
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(result)

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

    scheduler.add_job(
        run_scheduled_sync,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_sync_job",
        replace_existing=True,
    )

    scheduler.start()
    print("⏰ Scheduler started. Daily sync set for 03:00 UTC.")


if __name__ == "__main__":
    # Manual run mode (for local testing)
    print("🧪 Running scheduler manually...")
    start_scheduler()

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped.")
