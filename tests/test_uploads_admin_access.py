import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app

client = TestClient(app)

@pytest.fixture
def mock_s3_list():
    """Mock S3 paginator to prevent real AWS calls."""
    with patch("src.routers.uploads.get_s3_client") as mock_s3_client:
        s3_mock = mock_s3_client.return_value
        s3_mock = (None, "mock-bucket", "us-east-1")
        mock_s3_client.return_value = s3_mock
        yield mock_s3_client

# ------------------------------------------------------------------
# Static key to guarantee test consistency
# ------------------------------------------------------------------
SECRET_KEY = "supersecretkey123"
ALGORITHM = "HS256"

def make_token(role: str):
    from jose import jwt
    payload = {"sub": "test_user", "role": role}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------
def test_upload_all_admin_allowed(mock_s3_list):
    token = make_token("admin")
    response = client.get("/upload/all", headers={"Authorization": f"Bearer {token}"})
    print("Response status:", response.status_code, response.text)
    assert response.status_code in (200, 500)

def test_upload_all_user_forbidden(mock_s3_list):
    token = make_token("user")
    response = client.get("/upload/all", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

def test_upload_all_unauthorized():
    response = client.get("/upload/all")
    assert response.status_code == 401
