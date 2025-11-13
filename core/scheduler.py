# core/scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
import traceback

from core.notifications import send_email
from database import get_session
from routers.buildings import run_full_building_sync
from routers.events import run_full_event_sync  # ✅ Added

def run_scheduled_sync():
    """Runs full sync for buildings + events and emails the results."""
    start_time = datetime.utcnow()
    try:
        print("[SCHEDULER] Starting full sync (buildings + events)...")

        # ✅ Create a database session manually
        session_gen = get_session()
        session = next(session_gen)

        # -------------------------------------------------
        # 1️⃣ Run Buildings Sync
        # -------------------------------------------------
        building_result = run_full_building_sync(session)
        building_summary = building_result.get("summary", {})

        # -------------------------------------------------
        # 2️⃣ Run Events Sync
        # -------------------------------------------------
        event_result = run_full_event_sync(session)
        event_summary = event_result.get("summary", {})

        # -------------------------------------------------
        # 3️⃣ Build Summary Report
        # -------------------------------------------------
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        summary_text = (
            f"📋 **Aina Protocol Sync Report**\n\n"
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
            f"💬 **Messages**\n"
            f"• Buildings: {building_result.get('message', 'No message returned')}\n"
            f"• Events: {event_result.get('message', 'No message returned')}\n"
        )

        # -------------------------------------------------
        # 4️⃣ Send Report Email
        # -------------------------------------------------
        send_email(
            subject="[Aina Protocol] Daily Sync Completed ✅",
            body=f"✅ Sync completed successfully.\n\n{summary_text}",
        )

        print("[SCHEDULER] ✅ Buildings + Events sync completed successfully and email sent.")

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
