# core/supabase_helpers.py

from core.utils import sanitize
from core.errors import supabase_error
from core.supabase_client import get_supabase_client


# -----------------------------------------------------
# SELECT
# -----------------------------------------------------
def safe_select(table: str, filters: dict = None, *, single=False):
    client = get_supabase_client()

    try:
        query = client.table(table).select("*")
        if filters:
            for key, val in filters.items():
                query = query.eq(key, val)

        result = query.maybe_single().execute() if single else query.execute()
        return result.data
    except Exception as e:
        supabase_error(e, f"Failed to fetch from {table}")


# -----------------------------------------------------
# INSERT
# -----------------------------------------------------
def safe_insert(table: str, data: dict):
    client = get_supabase_client()
    cleaned = sanitize(data)

    try:
        result = (
            client.table(table)
            .insert(cleaned, returning="representation")
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        supabase_error(e, f"Failed to insert into {table}")


# -----------------------------------------------------
# UPDATE
# -----------------------------------------------------
def safe_update(table: str, filters: dict, data: dict):
    client = get_supabase_client()
    cleaned = sanitize(data)

    try:
        query = client.table(table).update(
            cleaned, returning="representation"
        )
        for key, val in filters.items():
            query = query.eq(key, val)

        result = query.execute()
        return result.data[0] if result.data else None
    except Exception as e:
        supabase_error(e, f"Failed to update {table}")
