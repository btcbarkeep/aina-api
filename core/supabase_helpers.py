# core/supabase_helpers.py
from core.supabase_client import get_supabase_client
import traceback


def fetch_all(table_name: str, limit: int = 100):
    """Fetch all records from a table (default 100)."""
    try:
        client = get_supabase_client()
        if not client:
            return {"status": "error", "detail": "Supabase not configured"}

        result = client.table(table_name).select("*").limit(limit).execute()
        return {"status": "ok", "data": result.data or []}

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}


def insert_record(table_name: str, record: dict):
    """Insert a single record into a table."""
    try:
        client = get_supabase_client()
        if not client:
            return {"status": "error", "detail": "Supabase not configured"}

        result = client.table(table_name).insert(record).execute()
        return {"status": "ok", "data": result.data}

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}


def update_record(table_name: str, record_id: str, updates: dict):
    """Update a record by its 'id' field."""
    try:
        client = get_supabase_client()
        if not client:
            return {"status": "error", "detail": "Supabase not configured"}

        result = client.table(table_name).update(updates).eq("id", record_id).execute()
        return {"status": "ok", "data": result.data}

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}


def delete_record(table_name: str, record_id: str):
    """Delete a record by its 'id'."""
    try:
        client = get_supabase_client()
        if not client:
            return {"status": "error", "detail": "Supabase not configured"}

        result = client.table(table_name).delete().eq("id", record_id).execute()
        return {"status": "ok", "data": result.data}

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "detail": str(e)}
