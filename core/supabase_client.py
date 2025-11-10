# core/supabase_client.py
from supabase import create_client, Client
from core.config import settings

def get_supabase_client() -> Client:
    """
    Create and return a Supabase client using URL + service key.
    """
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def ping_supabase() -> dict:
    """
    Test Supabase connectivity by selecting 1 record from the 'users' table.
    Adjust table name if necessary.
    """
    try:
        supabase = get_supabase_client()
        result = supabase.table("users").select("*").limit(1).execute()
        count = len(result.data) if result.data else 0
        return {"status": "ok", "rows_found": count}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
