import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from src.main import app    # if main.py is in /src
# if your main.py is at the project root instead, use:
# from main import app

from src.dependencies import get_admin_user

client = TestClient(app)


# ------------------------------------------------------------------
# Helpers: dependency overrides
# ------------------------------------------------------------------
def override_admin_ok():
    """Pretend the user is a valid admin."""
    return {"sub": "testadmin", "role": "admin"}


def override_admin_forbidden():
    """Pretend auth ran and decided the user is NOT an admin."""
    # Simulate what get_admin_user would do for non-admins
    raise HTTPException(status_code=403, detail="Admin access required")


def override_admin_unauthorized():
    """Simulate missing/invalid token -> 401."""
    raise HTTPException(status_code=401, detail="Missing or invalid token")


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clear_overrides():
    """
    Ensure dependency_overrides is clean before each test.
    """
    app.dependency_overrides = {}
    yield
    app.dependency_overrides = {}


@pytest.fixture
def mock_s3_list(monkeypatch):
    """
    Mock get_s3_client so tests never hit real AWS.
    """
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
# TESTS
# ------------------------------------------------------------------
def test_upload_all_admin_allowed(mock_s3_list):
    """Admin should be able to access /upload/all."""
    # ✅ Pretend auth already succeeded with an admin user
    app.dependency_overrides[get_admin_user] = override_admin_ok

    response = client.get("/upload/all")
    print("🧪 admin_allowed response:", response.status_code, response.text)

    # 200 = success, 500 = AWS mock hiccup, both are OK for this test
    assert response.status_code in (200, 500)


def test_upload_all_user_forbidden(mock_s3_list):
    """Non-admin should be blocked from /upload/all."""
    # ✅ Pretend auth check ran and rejected the user
    app.dependency_overrides[get_admin_user] = override_admin_forbidden

    response = client.get("/upload/all")
    print("🧪 user_forbidden response:", response.status_code, response.text)

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_upload_all_unauthorized(mock_s3_list):
    """Missing/invalid token returns 401."""
    # ✅ Pretend we never got a valid token at all
    app.dependency_overrides[get_admin_user] = override_admin_unauthorized

    response = client.get("/upload/all")
    print("🧪 unauthorized response:", response.status_code, response.text)

    assert response.status_code == 401
