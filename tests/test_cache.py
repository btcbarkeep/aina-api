# tests/test_cache.py

"""
Tests for caching functionality.
"""

import pytest
from core.cache import cache_get, cache_set, cache_clear, SimpleCache


def test_cache_set_and_get():
    """Test setting and getting values from cache."""
    cache_clear()
    
    cache_set("test_key", "test_value", ttl_seconds=60)
    value = cache_get("test_key")
    
    assert value == "test_value"


def test_cache_expiration():
    """Test that cache entries expire correctly."""
    cache_clear()
    
    cache_set("expiring_key", "expired_value", ttl_seconds=1)
    
    # Value should be available immediately
    assert cache_get("expiring_key") == "expired_value"
    
    # Wait for expiration (in real test, use time mocking)
    import time
    time.sleep(2)
    
    # Value should be expired
    assert cache_get("expiring_key") is None


def test_cache_delete():
    """Test deleting cache entries."""
    cache_clear()
    
    cache_set("delete_key", "delete_value")
    assert cache_get("delete_key") == "delete_value"
    
    from core.cache import cache_delete
    cache_delete("delete_key")
    
    assert cache_get("delete_key") is None


def test_cache_clear():
    """Test clearing all cache entries."""
    cache_set("key1", "value1")
    cache_set("key2", "value2")
    
    cache_clear()
    
    assert cache_get("key1") is None
    assert cache_get("key2") is None

