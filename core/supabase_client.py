# core/supabase_client.py

from supabase import create_client
from core.config import settings
import supabase
import traceback

print(f"[DEBUG] Supabase SDK version: {getattr(supabase, '__version__', 'unknown')}")


# ============================================================
# Create Supabase Client (User + Admin API)
# ============================================================
def get_supabase_client():
    """
    Returns a Supabase client authenticated with the Service Role Key.
    This client can:
      - verify user sessions
      - read/write any tables
      - use admin auth functions (create user, invite user, delete user)
    """

    try:
        supabase_url = str(settings.SUPABASE_URL) if settings.SUPABASE_URL else None
        supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY  # ✅ service role key

        if not supabase_url or not supabase_key:
            print("[DEBUG] Missing Supabase credentials.")
            print("  SUPABASE_URL:", supabase_url)
            print("  SUPABASE_SERVICE_ROLE_KEY:", "SET" if supabase_key else "MISSING")
            return None

        print("[DEBUG] Initializing Supabase client with:")
        print("   URL:", supabase_url)
        print("   Key:", "Service Role Key Loaded")

        client = create_client(supabase_url, supabase_key)

        print("[DEBUG] Supabase client created successfully.")
        return client

    except Exception as e:
        print(f"[Supabase Init Error] {e}")
        traceback.print_exc()
        return None


# ============================================================
# Optional Admin Helper (Alias)
# ============================================================
def get_admin_client():
    """Alias for semantic clarity."""
    return get_supabase_client()


# ============================================================
# Ping Supabase for health checks
# ============================================================
def ping_supabase() -> dict:
    """
    Test Supabase connectivity.

    NOTE: 'auth.users' cannot be queried like normal tables.
    We only ping real business tables.
    """

    try:
        print("[DEBUG] Ping: Checking Supabase ENV variables:")
        print("  SUPABASE_URL:", settings.SUPABASE_URL)
        print("  SUPABASE_SERVICE_ROLE_KEY:", 
              "SET" if settings.SUPABASE_SERVICE_ROLE_KEY else "MISSING")

        client = get_supabase_client()
        if client is None:
            return {"service": "Supabase", "status": "not_configured"}

        test_tables = ["documents", "events", "buildings", "contractors"]
        results = {}

        for table in test_tables:
            try:
                print(f"[DEBUG] Querying '{table}'...")
                response = client.table(table).select("*").limit(1).execute()
                row_count = len(response.data or [])
                results[table] = {"status": "ok", "rows_found": row_count}
                print(f"[DEBUG]  ✓ '{table}' OK — {row_count} rows found")

            except Exception as table_error:
                print(f"[DEBUG]  ✗ Error querying '{table}': {table_error}")
                results[table] = {
                    "status": "error",
                    "detail": str(table_error),
                }

        return {
            "service": "Supabase",
            "status": "ok",
            "tables": results,
        }

    except Exception as e:
        print("[Supabase Ping Error]", e)
        traceback.print_exc()
        return {
            "service": "Supabase",
            "status": "error",
            "detail": str(e),
        }


# ============================================================
# Load-time Debug
# ============================================================
print("[DEBUG] SUPABASE_URL:", settings.SUPABASE_URL)
print("[DEBUG] SUPABASE_SERVICE_ROLE_KEY:", 
      "SET" if settings.SUPABASE_SERVICE_ROLE_KEY else "MISSING")
