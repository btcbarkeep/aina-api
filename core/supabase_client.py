# core/supabase_client.py
from supabase import create_client
from core.config import settings
import supabase
import traceback

print(f"[DEBUG] Supabase SDK version: {getattr(supabase, '__version__', 'unknown')}")

def get_supabase_client():
    """
    Safely create and return a Supabase client using URL + service key.
    Returns None if either value is missing.
    """
    try:
        supabase_url = str(settings.SUPABASE_URL) if settings.SUPABASE_URL else None
        supabase_key = settings.SUPABASE_API_KEY  # ✅ Corrected field name

        if not supabase_url or not supabase_key:
            print("[DEBUG] Missing Supabase credentials.")
            return None

        print("[DEBUG] Attempting Supabase client init with:")
        print("   URL:", supabase_url)
        print("   KEY:", "SET" if supabase_key else "MISSING")

        # Try to create the Supabase client
        client = create_client(supabase_url, supabase_key)
        print("[DEBUG] Client created successfully:", client)
        return client

    except Exception as e:
        print(f"[Supabase Init Error] {e}")
        traceback.print_exc()
        return None


def ping_supabase() -> dict:
    """
    Test Supabase connectivity by selecting 1 record from multiple tables.
    Helps verify if the Supabase client and key are working properly.
    """
    try:
        print("[DEBUG] Live ENV check (from settings):")
        print("  SUPABASE_URL:", settings.SUPABASE_URL)
        print("  SUPABASE_API_KEY:", "SET" if settings.SUPABASE_API_KEY else "MISSING")

        client = get_supabase_client()
        if client is None:
            print("[DEBUG] No Supabase client returned → 'not_configured'")
            return {"service": "Supabase", "status": "not_configured"}

        # Try querying multiple tables to help isolate issues
        test_tables = ["users", "documents", "events", "buildings"]
        results = {}

        for table in test_tables:
            try:
                print(f"[DEBUG] Querying table '{table}'...")
                response = client.table(table).select("*").limit(1).execute()
                row_count = len(response.data or [])
                print(f"[DEBUG] ✅ Table '{table}' OK — rows found: {row_count}")
                results[table] = {"status": "ok", "rows_found": row_count}
            except Exception as table_error:
                print(f"[DEBUG] ❌ Error querying '{table}': {table_error}")
                results[table] = {"status": "error", "detail": str(table_error)}

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



# Debugging logs on startup
print("[DEBUG] SUPABASE_URL:", settings.SUPABASE_URL)
print("[DEBUG] SUPABASE_API_KEY:", "SET" if settings.SUPABASE_API_KEY else "MISSING")
