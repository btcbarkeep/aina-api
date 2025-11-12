# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio
import time
import traceback
import json

from core.notifications import send_email


def run_scheduled_sync():
    """Runs the sync and emails the results."""
    start_time = datetime.utcnow()

    async def _inner():
        from routers.sync import perform_sync_logic  # ✅ Lazy import to avoid circular issues
        print("[SCHEDULER] Starting full sync...")

        result = await perform_sync_logic()

        # 🧩 Handle JSONResponse or dict
        if hasattr(result, "body"):
            result = json.loads(result.body.decode())

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

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

    try:
        # 🔄 Properly handle existing event loop (Render runs inside uvicorn loop)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                print("[SCHEDULER] Using existing asyncio loop.")
                task = loop.create_task(_inner())
                return task
            else:
                print("[SCHEDULER] Starting new asyncio loop.")
                return loop.run_until_complete(_inner())
        except RuntimeError:
            print("[SCHEDULER] Creating new loop (no active event loop).")
            asyncio.run(_inner())

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

    # Daily job at 03:00 UTC (midnight HST)
    scheduler.add_job(
        run_scheduled_sync,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_sync_job",
        replace_existing=True,
    )

    # 🧪 Optional: Run once immediately after deployment for testing
    scheduler.add_job(run_scheduled_sync, trigger='date', run_date=datetime.utcnow())

    scheduler.start()
    print("⏰ Scheduler started. Daily sync set for 03:00 UTC.")


if __name__ == "__main__":
    print("🧪 Running scheduler manually...")
    start_scheduler()

    # Keep process alive for manual testing
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped.")
