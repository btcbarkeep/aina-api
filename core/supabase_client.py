# core/supabase_client.py

from supabase import create_client, Client
from core.config import settings
import traceback


# ============================================================
# Supabase Client Factory (ALWAYS service role)
# ============================================================

def get_supabase_client() -> Client:
    """
    Creates a Supabase client using the SERVICE ROLE KEY.
    REQUIRED for:
        - auth.admin.create_user
        - auth.admin.invite_user_by_email
        - auth.admin.update_user_by_id
        - full read/write on all tables
    """
    try:
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY  # MUST be service-role

        if not supabase_url or not supabase_key:
            print("❌ Missing Supabase credentials")
            print("   URL:", supabase_url)
            print("   SERVICE ROLE KEY:", "SET" if supabase_key else "MISSING")
            return None

        # Create client
        client = create_client(supabase_url, supabase_key)
        return client

    except Exception as e:
        print("❌ [Supabase Init Error]", e)
        traceback.print_exc()
        return None


# ============================================================
# Alias: Admin Client
# ============================================================

def get_admin_client() -> Client:
    """Alias for readability."""
    return get_supabase_client()


# ============================================================
# Ping Supabase for health checks
# ============================================================

def ping_supabase() -> dict:
    """
    Simple connectivity check.
    Does NOT query auth tables (by design).
    """
    try:
        client = get_supabase_client()
        if client is None:
            return {"service": "Supabase", "status": "not_configured"}

        tables = ["documents", "events", "buildings", "contractors"]
        results = {}

        for t in tables:
            try:
                res = client.table(t).select("*").limit(1).execute()
                results[t] = {
                    "status": "ok",
                    "rows_found": len(res.data or [])
                }
            except Exception as err:
                results[t] = {"status": "error", "detail": str(err)}

        return {
            "service": "Supabase",
            "status": "ok",
            "tables": results,
        }

    except Exception as e:
        print("❌ [Supabase Ping Error]", e)
        traceback.print_exc()
        return {"service": "Supabase", "status": "error", "detail": str(e)}
