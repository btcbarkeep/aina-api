# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback

from core.notifications import send_email
from database import get_session
from routers.buildings import run_full_building_sync


def run_scheduled_sync():
    """Runs the full building sync and emails the results."""
    start_time = datetime.utcnow()
    try:
        print("[SCHEDULER] Starting full sync...")

        # ✅ Create a database session manually
        session_gen = get_session()
        session = next(session_gen)

        # ✅ Run the unified sync logic
        result = run_full_building_sync(session)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # ✅ Build formatted summary text
        summary_data = result.get("summary", {})
        summary_text = (
            f"🗓️ **Sync Summary**\n"
            f"- Start Time (UTC): {start_time}\n"
            f"- End Time (UTC): {end_time}\n"
            f"- Duration: {duration:.2f} seconds\n\n"
            f"📊 **Details:**\n"
            f"Local total: {summary_data.get('local_total', 'N/A')}\n"
            f"Supabase total: {summary_data.get('supa_total', 'N/A')}\n"
            f"Inserted to Supabase: {len(summary_data.get('inserted_to_supabase', []))}\n"
            f"Inserted to Local: {len(summary_data.get('inserted_to_local', []))}\n\n"
            f"💬 **Message:**\n{result.get('message', 'No message returned')}\n"
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
