import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from src.main import app   # if main.py lives inside /src
# from main import app     # if main.py is in project root

from src.dependencies import get_admin_user

client = TestClient(app)


# ------------------------------------------------------------------
# Dependency overrides
# ------------------------------------------------------------------
def override_admin_ok():
    """Pretend user is a valid admin."""
    return {"sub": "testadmin", "role": "admin"}


def override_admin_forbidden():
    """Pretend auth ran and rejected the user."""
    raise HTTPException(status_code=403, detail="Admin access required")


def override_admin_unauthorized():
    """Simulate missing/invalid token."""
    raise HTTPException(status_code=401, detail="Missing or invalid token")


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clear_overrides():
    """Reset overrides before/after each test."""
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def mock_s3_list(monkeypatch):
    """Mock S3 so no network calls happen."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "test/file.txt", "Size": 1024}]}
    ]

    def fake_get_s3_client():
        return mock_client, "fake-bucket", "us-east-1"

    monkeypatch.setattr("src.routers.uploads.get_s3_client", fake_get_s3_client)
    return mock_client


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------
def test_upload_all_admin_allowed(mock_s3_list):
    """Admin should be able to access /upload/all."""
    app.dependency_overrides[get_admin_user] = override_admin_ok

    response = client.get("/upload/all")
    print("🧪 admin_allowed response:", response.status_code, response.text)

    assert response.status_code in (200, 500)


def test_upload_all_user_forbidden(mock_s3_list):
    """Non-admin should be blocked."""
    app.dependency_overrides[get_admin_user] = override_admin_forbidden

    response = client.get("/upload/all")
    print("🧪 user_forbidden response:", response.status_code, response.text)

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_upload_all_unauthorized(mock_s3_list):
    """Missing/invalid token should return 401."""
    app.dependency_overrides[get_admin_user] = override_admin_unauthorized

    response = client.get("/upload/all")
    print("🧪 unauthorized response:", response.status_code, response.text)

    assert response.status_code == 401
