from supabase import create_client
from core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

def ping():
    try:
        data = supabase.table("users").select("*").limit(1).execute()
        return {"status": "ok", "count": len(data.data)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
