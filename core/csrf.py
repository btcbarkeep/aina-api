# core/csrf.py

"""
CSRF (Cross-Site Request Forgery) protection middleware.

This module provides CSRF protection for state-changing operations (POST, PUT, DELETE, PATCH).
For API-only applications, CSRF protection may not be necessary if:
- All requests use Bearer token authentication
- SameSite cookies are used
- CORS is properly configured

However, this middleware provides an additional layer of security for web clients.
"""

from fastapi import Request, HTTPException, status
from typing import Optional
from core.logging_config import logger
import secrets


# CSRF token storage (in production, use Redis or session storage)
_csrf_tokens: dict[str, str] = {}


def generate_csrf_token() -> str:
    """
    Generate a secure CSRF token.
    
    Returns:
        A cryptographically secure random token
    """
    return secrets.token_urlsafe(32)


def get_csrf_token(session_id: Optional[str] = None) -> str:
    """
    Get or generate a CSRF token for a session.
    
    Args:
        session_id: Optional session identifier (defaults to generating a new token)
    
    Returns:
        CSRF token string
    """
    if session_id and session_id in _csrf_tokens:
        return _csrf_tokens[session_id]
    
    token = generate_csrf_token()
    if session_id:
        _csrf_tokens[session_id] = token
    
    return token


def validate_csrf_token(request: Request, token: Optional[str] = None) -> bool:
    """
    Validate a CSRF token from the request.
    
    Checks:
    1. X-CSRF-Token header
    2. csrf_token form field
    3. csrf_token query parameter
    
    Args:
        request: FastAPI Request object
        token: Optional token to validate (if not provided, extracts from request)
    
    Returns:
        True if token is valid, False otherwise
    """
    if token is None:
        # Try to get token from header first
        token = request.headers.get("X-CSRF-Token")
        
        # If not in header, try form data
        if not token and hasattr(request, "form"):
            try:
                form_data = request.form()
                token = form_data.get("csrf_token")
            except Exception:
                pass
        
        # If still not found, try query parameters
        if not token:
            token = request.query_params.get("csrf_token")
    
    if not token:
        return False
    
    # Validate token exists in our store
    # In production, validate against session storage
    return token in _csrf_tokens.values()


def require_csrf_token(request: Request):
    """
    Middleware dependency to require CSRF token for state-changing operations.
    
    This should be used as a dependency on POST, PUT, DELETE, PATCH endpoints
    that are accessed by web browsers.
    
    Args:
        request: FastAPI Request object
    
    Raises:
        HTTPException: 403 Forbidden if CSRF token is missing or invalid
    
    Note:
        For API-only applications using Bearer tokens, CSRF protection may not be necessary.
        This is primarily for web form submissions.
    """
    # Skip CSRF check for API requests with Bearer tokens
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # Bearer token authentication - CSRF not needed
        return
    
    # Skip CSRF check for GET, HEAD, OPTIONS requests
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return
    
    # For state-changing operations from web browsers, require CSRF token
    if not validate_csrf_token(request):
        logger.warning(f"CSRF token validation failed: {request.method} {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing or invalid. Please refresh the page and try again."
        )


def get_csrf_token_endpoint(request: Request) -> dict:
    """
    Endpoint helper to return a CSRF token for the client.
    
    This should be called by the frontend to get a CSRF token before
    making state-changing requests.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        Dictionary with csrf_token
    """
    # In production, use a proper session ID
    session_id = request.headers.get("X-Session-ID") or "default"
    token = get_csrf_token(session_id)
    
    return {"csrf_token": token}

