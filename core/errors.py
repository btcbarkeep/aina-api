# core/errors.py

from fastapi import HTTPException

def supabase_error(error: Exception, message: str = "Supabase error"):
    """
    Extracts and formats Supabase Python client errors into
    a readable, consistent HTTPException message.
    """

    try:
        # Supabase errors often have .message or .args
        detail = str(error)
    except Exception:
        detail = "Unknown Supabase error"

    raise HTTPException(
        status_code=500,
        detail=f"{message}: {detail}"
    )
