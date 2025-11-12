# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import traceback
import asyncio

from core.notifications import send_email

# --- GLOBAL FLAG to prevent double runs ---
is_sync_running = False


async def perform_sync_logic():
    """Centralized sync logic called by both scheduler and /sync/run endpoint."""
    from routers.sync import trigger_full_sync  # lazy import to prevent circular import
    print("[SCHEDULER] Running sync logic via perform_sync_logic()")
    result = await trigger_full_sync()
    return result


def run_scheduled_sync():
    """Safely executes the sync process once and sends summary email."""
    global is_sync_running

    if is_sync_running:
        print("[SCHEDULER] ⚠️ Sync already running, skipping duplicate job.")
        return

    is_sync_running = True
    start_time = datetime.utcnow()

    # core/scheduler.py  (update _inner function)
async def _inner():
    try:
        print("[SCHEDULER] Starting full sync...")

        result = await perform_sync_logic()

        # 🧩 Handle both FastAPI JSONResponse and dict outputs
        if hasattr(result, "body"):
            import json
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


        except Exception as e:
            print("[SCHEDULER] ❌ Sync failed:", e)
            send_email(
                subject="[Aina Protocol] Sync Failed ❌",
                body=f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}",
            )
        finally:
            global is_sync_running
            is_sync_running = False

    # ✅ Run safely in the active event loop
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_inner())
    except RuntimeError:
        asyncio.run(_inner())


def start_scheduler():
    """
    Initialize APScheduler in the background.
    Runs the sync once daily at 03:00 UTC.
    """
    scheduler = BackgroundScheduler(timezone="UTC")

    scheduler.add_job(
        run_scheduled_sync,
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_sync_job",
        replace_existing=True,
        max_instances=1,  # ✅ ensures only one run at a time
    )

    scheduler.start()
    print("⏰ Scheduler started. Daily sync set for 03:00 UTC.")


if __name__ == "__main__":
    print("🧪 Running scheduler manually...")
    start_scheduler()

    # Keep process alive for testing
    import time
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Scheduler stopped.")
