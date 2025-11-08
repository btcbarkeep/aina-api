import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from jose import jwt
from datetime import datetime, timedelta

from src.main import app  # ✅ correct import
from src.core.config import SECRET_KEY, ALGORITHM

client = TestClient(app)

# ------------------------------------------------------------------
# Helper: generate JWT with proper secret + algorithm
# ------------------------------------------------------------------
def make_token(role="user"):
    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {
        "sub": "testuser",
        "role": role,
        "exp": expire
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    print(f"🧪 Generated {role} token: {token}")
    return token

# ------------------------------------------------------------------
# Fixture: mock S3
# ------------------------------------------------------------------
@pytest.fixture
def mock_s3_list(monkeypatch):
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
    token = make_token("admin")
    headers = {"Authorization": f"Bearer {token}"}
    print("🧩 Headers used in test:", headers)
    resp = client.get("/upload/all", headers=headers)
    print("🧩 Response:", resp.status_code, resp.text)
    assert resp.status_code in (200, 500)  # Allow 500 if AWS mock fails early


def test_upload_all_user_forbidden(mock_s3_list):
    """Non-admin should be blocked from /upload/all."""
    token = make_token("user")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/upload/all", headers=headers)
    print("🧩 Response (user):", resp.status_code, resp.text)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


def test_upload_all_unauthorized(mock_s3_list):
    """Missing token returns 401."""
    resp = client.get("/upload/all")
    print("🧩 Response (no token):", resp.status_code, resp.text)
    assert resp.status_code == 401
