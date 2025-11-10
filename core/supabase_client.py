# core/supabase_client.py
from supabase import create_client, Client
from core.config import settings


def get_supabase_client() -> Client | None:
    """
    Safely create and return a Supabase client using URL + service key.
    Returns None if either value is missing.
    """
    try:
        supabase_url = str(settings.SUPABASE_URL) if settings.SUPABASE_URL else None
        supabase_key = settings.SUPABASE_KEY

        if not supabase_url or not supabase_key:
            return None

        return create_client(supabase_url, supabase_key)

    except Exception as e:
        print(f"[Supabase Init Error] {e}")
        return None


def ping_supabase() -> dict:
    """
    Test Supabase connectivity by selecting 1 record from the 'users' table.
    Adjust the table name if necessary.
    """
    try:
        client = get_supabase_client()
        if client is None:
            return {"service": "Supabase", "status": "not_configured"}

        result = client.table("users").select("*").limit(1).execute()
        count = len(result.data) if result.data else 0

        return {
            "service": "Supabase",
            "status": "ok",
            "rows_found": count,
        }

    except Exception as e:
        return {
            "service": "Supabase",
            "status": "error",
            "detail": str(e),
        }


print("[DEBUG] SUPABASE_URL:", settings.SUPABASE_URL)
print("[DEBUG] SUPABASE_KEY:", "SET" if settings.SUPABASE_KEY else "MISSING")

