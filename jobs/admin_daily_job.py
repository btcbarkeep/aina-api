# jobs/admin_daily_job.py

from core.supabase_client import get_supabase_client
from core.notifications import send_email
from routers.admin_daily import get_daily_snapshot, format_daily_email

def run():
    """
    CLI entry point for the daily admin report.
    This is what Render's Cron Job / Job will call.
    """
    # Make sure Supabase is configured (env vars present)
    client = get_supabase_client()
    if not client:
        raise RuntimeError("Supabase not configured")

    snapshot = get_daily_snapshot()
    body = format_daily_email(snapshot)

    # This send_email helper already knows your default admin recipient(s)
    # If you want to hard-code your email, you can pass `to="you@example.com"`
    send_email(
        subject="Aina Protocol — Daily Update",
        body=body,
    )

if __name__ == "__main__":
    run()
