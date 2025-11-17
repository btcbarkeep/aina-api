# core/supabase_helpers.py

from core.utils import sanitize
from core.errors import supabase_error
from core.supabase_client import get_supabase_client


# =================================================================
#  SAFE SELECT / INSERT / UPDATE — UNCHANGED FOR ALL NORMAL TABLES
# =================================================================
# These helpers must NOT be used for auth.users.
# They continue working for:
#   - buildings
#   - events
#   - documents
#   - contractors
#   - signup_requests
#   - user_building_access
#   - ANY custom table except users
# =================================================================

def safe_select(table: str, filters: dict = None, *, single=False):
    """Safe table SELECT (not for auth.users)."""
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


def safe_insert(table: str, data: dict):
    """Safe INSERT for non-auth tables."""
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


def safe_update(table: str, filters: dict, data: dict):
    """Safe UPDATE for non-auth tables."""
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


# =================================================================
#  SUPABASE AUTH ADMIN HELPERS — NEW
# =================================================================
# These replace:
#   - create_user_no_password
#   - update user.role in users table
#   - user metadata management
#
# They MUST be used instead of CRUD on users table.
# =================================================================

def create_supabase_user(email: str, password: str = None, metadata: dict = None):
    """
    Create a user via Supabase Auth Admin API.
    Password may be omitted (for email invite flow).
    """
    client = get_supabase_client()

    try:
        result = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": False,
                "user_metadata": metadata or {},
            }
        )
        return result.user

    except Exception as e:
        supabase_error(e, "Failed to create Supabase Auth user")


def update_user_metadata(user_id: str, metadata: dict):
    """
    Merge metadata into existing user_metadata.
    Example:
        update_user_metadata(user_id, {"role": "manager"})
    """
    client = get_supabase_client()

    try:
        result = client.auth.admin.update_user_by_id(
            user_id,
            {
                "user_metadata": metadata
            }
        )
        return result.user

    except Exception as e:
        supabase_error(e, "Failed to update Supabase user metadata")


def supabase_get_user(user_id: str):
    """
    Fetch a Supabase Auth user by ID.
    Replaces SELECT from custom users table.
    """
    client = get_supabase_client()

    try:
        result = client.auth.admin.get_user_by_id(user_id)
        return result.user

    except Exception as e:
        supabase_error(e, "Failed to fetch Supabase user")
