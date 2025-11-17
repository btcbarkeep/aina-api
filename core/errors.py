# core/errors.py

from fastapi import HTTPException


def extract_supabase_error(error: Exception) -> str:
    """
    Safely extract readable details from Supabase Python client errors.
    Handles:
      • PostgREST errors
      • GoTrue (Auth) errors
      • Generic Python exceptions
    """

    # Case 1 — Supabase Auth / GoTrue errors
    if hasattr(error, "message"):
        try:
            return str(error.message)
        except Exception:
            pass

    # Case 2 — Supabase errors with args (common)
    if hasattr(error, "args") and error.args:
        try:
            return str(error.args[0])
        except Exception:
            pass

    # Case 3 — Plain string fallback
    try:
        return str(error)
    except Exception:
        return "Unknown Supabase error"


def supabase_error(error: Exception, message: str = "Supabase error"):
    """
    Convert Supabase / database errors into clean HTTPExceptions.
    Always raises — caller should wrap with try/except.
    """

    detail = extract_supabase_error(error)

    raise HTTPException(
        status_code=500,
        detail=f"{message}: {detail}"
    )
