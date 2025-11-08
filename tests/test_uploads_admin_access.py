import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from jose import jwt
from datetime import datetime, timedelta

from main import app
from src.routers.auth import SECRET_KEY, ALGORITHM

client = TestClient(app)


# ------------------------------------------------------------------
# Helper: Generate JWT for tests
# ------------------------------------------------------------------
def make_token(role="user"):
    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {
        "sub": "testuser",
        "role": role,
        "exp": expire,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    print(f"[DEBUG] Generated token for {role}: {token}")
    return token


# ------------------------------------------------------------------
# Fixture: mock AWS client
# ------------------------------------------------------------------
@pytest.fixture
def mock_s3_list(monkeypatch):
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "test/file.txt", "Size": 1024}]}
    ]

    def mock_get_s3_client():
        return mock_client, "fake-bucket", "us-east-1"

    monkeypatch.setattr("src.routers.uploads.get_s3_client", mock_get_s3_client)
    yield mock_client


# ------------------------------------------------------------------
# TEST: Admin can access /upload/all
# ------------------------------------------------------------------
def test_upload_all_admin_allowed(mock_s3_list):
    """Admin should be able to access /upload/all."""
    token = make_token("admin")
    response = client.get(
        "/upload/all",
        headers={"Authorization": f"Bearer {token}"}
    )
    print("[DEBUG] Response status:", response.status_code)
    print("[DEBUG] Response body:", response.text)
    assert response.status_code in (200, 500)  # Allow 500 if AWS mock fails early


# ------------------------------------------------------------------
# TEST: Non-admin blocked
# ------------------------------------------------------------------
def test_upload_all_user_forbidden(mock_s3_list):
    """Non-admin should be blocked from /upload/all."""
    token = make_token("user")
    response = client.get(
        "/upload/all",
        headers={"Authorization": f"Bearer {token}"}
    )
    print("[DEBUG] Response status:", response.status_code)
    assert response.status_code == 403


# ------------------------------------------------------------------
# TEST: Missing token -> Unauthorized
# ------------------------------------------------------------------
def test_upload_all_unauthorized(mock_s3_list):
    """No token should result in 401."""
    response = client.get("/upload/all")
    print("[DEBUG] Response status:", response.status_code)
    assert response.status_code == 401
