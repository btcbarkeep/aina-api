"""
database.py — simplified Supabase-only version

All SQLModel + engine logic has been removed.
This file now serves only as a compatibility layer so imports do not break.
"""

from typing import Generator


def create_db_and_tables() -> None:
    """
    Deprecated — no-op.
    Supabase handles all persistence.
    """
    print("⚠️ create_db_and_tables() called — NO-OP (using Supabase)")


def get_session() -> Generator[None, None, None]:
    """
    Deprecated — no-op generator so dependency injections do not break.
    """
    yield None
