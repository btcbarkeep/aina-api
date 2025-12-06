# core/cache.py

"""
Simple in-memory caching utilities.

For production, consider using Redis or a dedicated caching service.
This implementation uses a simple in-memory cache with TTL support.
"""

from typing import Optional, Any, Callable
from datetime import datetime, timedelta
from threading import Lock
from core.logging_config import logger


class CacheEntry:
    """Represents a cached value with expiration time."""
    
    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return datetime.now() >= self.expires_at


class SimpleCache:
    """
    Simple in-memory cache with TTL support.
    
    Thread-safe for concurrent access.
    """
    
    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
        
        Returns:
            Cached value or None if not found or expired
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            if entry.is_expired():
                del self._cache[key]
                return None
            
            return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """
        Set a value in the cache with TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds (default: 5 minutes)
        """
        with self._lock:
            self._cache[key] = CacheEntry(value, ttl_seconds)
    
    def delete(self, key: str):
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
        """
        with self._lock:
            self._cache.pop(key, None)
    
    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self):
        """Remove all expired entries from the cache."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
    
    def size(self) -> int:
        """Get the number of entries in the cache."""
        with self._lock:
            return len(self._cache)


# Global cache instance
_cache = SimpleCache()


def get_cache() -> SimpleCache:
    """Get the global cache instance."""
    return _cache


def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """
    Decorator to cache function results.
    
    Args:
        ttl_seconds: Time to live in seconds
        key_prefix: Optional prefix for cache keys
    
    Example:
        @cached(ttl_seconds=600, key_prefix="buildings")
        def get_building(building_id: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
            
            # Try to get from cache
            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value
            
            # Call function and cache result
            result = func(*args, **kwargs)
            _cache.set(cache_key, result, ttl_seconds)
            logger.debug(f"Cache miss, stored: {cache_key}")
            
            return result
        
        return wrapper
    return decorator


def cache_get(key: str) -> Optional[Any]:
    """
    Get a value from the cache.
    
    Args:
        key: Cache key
    
    Returns:
        Cached value or None
    """
    return _cache.get(key)


def cache_set(key: str, value: Any, ttl_seconds: int = 300):
    """
    Set a value in the cache.
    
    Args:
        key: Cache key
        value: Value to cache
        ttl_seconds: Time to live in seconds
    """
    _cache.set(key, value, ttl_seconds)


def cache_delete(key: str):
    """
    Delete a value from the cache.
    
    Args:
        key: Cache key
    """
    _cache.delete(key)


def cache_clear():
    """Clear all cache entries."""
    _cache.clear()

