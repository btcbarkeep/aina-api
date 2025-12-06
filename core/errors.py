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


def handle_supabase_error(error: Exception, operation: str = "Database operation", status_code: int = 500) -> HTTPException:
    """
    Handle Supabase errors with consistent formatting.
    Returns HTTPException (doesn't raise) so caller can customize or re-raise.
    
    Args:
        error: The exception that occurred
        operation: Description of what operation failed (e.g., "Failed to create document")
        status_code: HTTP status code (default 500)
    
    Returns:
        HTTPException with standardized error message
    """
    from core.logging_config import logger
    
    error_detail = extract_supabase_error(error)
    logger.error(f"{operation}: {error_detail}")
    
    # Provide user-friendly messages for common errors
    error_lower = error_detail.lower()
    if "duplicate" in error_lower or "unique" in error_lower:
        return HTTPException(status_code=400, detail=f"{operation}: Record already exists")
    elif "foreign key" in error_lower or "violates foreign key" in error_lower:
        return HTTPException(status_code=400, detail=f"{operation}: Invalid reference")
    elif "not found" in error_lower or "does not exist" in error_lower:
        return HTTPException(status_code=404, detail=f"{operation}: Resource not found")
    else:
        return HTTPException(status_code=status_code, detail=f"{operation} failed")
