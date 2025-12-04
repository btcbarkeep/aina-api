# core/rate_limiter.py

from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from collections import defaultdict
import time


# Simple in-memory rate limiter
# For production, consider using Redis or a dedicated rate limiting service
_rate_limit_store: Dict[str, list] = defaultdict(list)


def check_rate_limit(
    identifier: str,
    max_requests: int = 10,
    window_seconds: int = 60,
    clear_expired: bool = True
) -> Tuple[bool, int]:
    """
    Check if a request should be rate limited.
    
    Args:
        identifier: Unique identifier (IP address, user ID, etc.)
        max_requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
        clear_expired: Whether to clean up expired entries
    
    Returns:
        Tuple of (allowed: bool, remaining: int)
    """
    now = time.time()
    window_start = now - window_seconds
    
    # Get request timestamps for this identifier
    requests = _rate_limit_store[identifier]
    
    # Remove expired entries
    if clear_expired:
        _rate_limit_store[identifier] = [
            ts for ts in requests if ts > window_start
        ]
        requests = _rate_limit_store[identifier]
    
    # Check if limit exceeded
    if len(requests) >= max_requests:
        return False, 0
    
    # Add current request
    requests.append(now)
    _rate_limit_store[identifier] = requests
    
    remaining = max_requests - len(requests)
    return True, remaining


def get_rate_limit_identifier(request: Request, user_id: Optional[str] = None) -> str:
    """
    Get a unique identifier for rate limiting.
    Prefers user_id if available, otherwise uses IP address.
    
    Args:
        request: FastAPI Request object
        user_id: Optional user ID
    
    Returns:
        Unique identifier string
    """
    if user_id:
        return f"user:{user_id}"
    
    # Get client IP
    client_ip = request.client.host if request.client else "unknown"
    
    # Check for forwarded IP (common behind proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        client_ip = forwarded_for.split(",")[0].strip()
    
    return f"ip:{client_ip}"


def require_rate_limit(
    request: Request,
    identifier: Optional[str] = None,
    max_requests: int = 10,
    window_seconds: int = 60
):
    """
    Rate limit decorator/helper that raises HTTPException if limit exceeded.
    
    Args:
        request: FastAPI Request object
        identifier: Optional custom identifier (defaults to IP or user)
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
    
    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded
    """
    if identifier is None:
        identifier = get_rate_limit_identifier(request)
    
    allowed, remaining = check_rate_limit(identifier, max_requests, window_seconds)
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds.",
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Window": str(window_seconds),
                "Retry-After": str(window_seconds),
            }
        )
    
    return remaining

