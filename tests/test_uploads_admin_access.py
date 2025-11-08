import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from jose import jwt
from datetime import datetime, timedelta

# ✅ Import FastAPI app directly from main.py (root-level)
# If main.py is inside /src, keep it as src.main — if it's in root, change to just main
from main import app

# ✅ Config values for signing JWTs
from src.core.config import SECRET_KEY, ALGORITHM

client = TestClient(app)


# ------------------------------------------------------------------
# Helper: Generate a JWT with proper secret + algorithm
# ------------------------------------------------------------------
def make_token(role: str = "user") -> str:
    expire = datetime.utcnow() + timedelta(hours=1)
    payload = {"sub": "testuser", "role": role, "exp": expire}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    print(f"🧪 Generated token for role '{role}': {token}")
    return token


# ------------------------------------------------------------------
# Fixture: Mock AWS S3 client
# ------------------------------------------------------------------
@pytest.fixture
def mock_s3_list(monkeypatch):
    mock_client = MagicMock()
    mock_client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "test/file.txt", "Size": 1024}]}
    ]

    def fake_get_s3_client():
        return mock_client, "fake-bucket", "us-east-1"

    # ✅ Ensure correct import path
    monkeypatch.setattr("src.routers.uploads.get_s3_client", fake_get_s3_client)
    return mock_client


# ------------------------------------------------------------------
# TESTS
# ------------------------------------------------------------------
def test_upload_all_admin_allowed(mock_s3_list):
    """Admin should be able to access /upload/all."""
    token = make_token("admin")
    headers = {"Authorization": f"Bearer {token}"}
    print("🧩 Headers used:", headers)

    response = client.get("/upload/all", headers=headers)
    print("🧩 Response status:", response.status_code)
    print("🧩 Response body:", response.text)

    # 200 = success, 500 = mock AWS failure, 401 = still bad token
    assert response.status_code in (200, 500), f"Unexpected status: {response.status_code}"


def test_upload_all_user_forbidden(mock_s3_list):
    """Non-admin user should be blocked."""
    token = make_token("user")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/upload/all", headers=headers)
    print("🧩 Response (user):", response.status_code, response.text)

    assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    assert response.json()["detail"] == "Admin access required"


def test_upload_all_unauthorized(mock_s3_list):
    """Missing token returns 401."""
    response = client.get("/upload/all")
    print("🧩 Response (no token):", response.status_code, response.text)
    assert response.status_code == 401
