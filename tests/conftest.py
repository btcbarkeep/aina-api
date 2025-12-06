# tests/conftest.py

"""
Pytest configuration and shared fixtures for testing.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from typing import Generator

from main import create_app
from dependencies.auth import CurrentUser


@pytest.fixture(scope="function")
def app():
    """Create a test FastAPI application instance."""
    return create_app()


@pytest.fixture(scope="function")
def client(app) -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_current_user():
    """Create a mock current user for testing."""
    return CurrentUser(
        id="test-user-id",
        email="test@example.com",
        role="admin",
        permissions=["buildings:read", "buildings:write"],
        contractor_id=None
    )


@pytest.fixture
def mock_contractor_user():
    """Create a mock contractor user for testing."""
    return CurrentUser(
        id="contractor-user-id",
        email="contractor@example.com",
        role="contractor",
        permissions=[],
        contractor_id="contractor-123"
    )


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    mock_client = Mock()
    mock_table = Mock()
    mock_client.table.return_value = mock_table
    return mock_client


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset cache before each test."""
    from core.cache import cache_clear
    cache_clear()
    yield
    cache_clear()

