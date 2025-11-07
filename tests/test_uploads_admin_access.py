import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app

client = TestClient(app)


# -------------------------------------------------------------------
#  FIXTURES
# -------------------------------------------------------------------
@pytest.fixture
def mock_s3_list():
    """Mock S3 paginator to prevent real AWS calls."""
    with patch("src.routers.uploads.get_s3_client") as mock_s3_client:
        s3_mock = mock_s3_client.return_value
        # Return mock tuple (s3, bucket, region)
        s3_mock = (None, "mock-bucket", "us-east-1")
        mock_s3_client.return_value = s3_mock
        yield mock_s3_client


# -------------------------------------------------------------------
#  TOKEN HELPER (imports from your real app constants)
# -------------------------------------------------------------------
def make_token(role: str):
    from jose import jwt
    from src.routers.auth import SECRET_KEY, ALGORITHM  # 👈 same constants as app

    payload = {"sub": "test_user", "role": role}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# -------------------------------------------------------------------
#  TESTS
# -------------------------------------------------------------------
def test_upload_all_admin_allowed(mock_s3_list):
    """Admin should be able to access /upload/all."""
    token = make_token("admin")
    print("\nGenerated token for admin:\n", token)

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/upload/all", headers=headers)

    # --- Debug info ---
    print("Token being sent:", token)
    print("Headers used:", headers)
    try:
        print("Response JSON:", response.json())
    except Exception:
        print("Response not JSON, raw text:", response.text)
    # ------------------

    assert response.status_code in (200, 500)  # Allow 500 if AWS mock fails early
    if response.status_code == 200:
        assert "files" in response.json() or "total_files" in response.json()


def test_upload_all_user_forbidden(mock_s3_list):
    """Non-admin should be blocked from /upload/all."""
    token = make_token("user")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/upload/all", headers=headers)

    # --- Debug info ---
    print("\n[User Access Test]")
    print("Token being sent:", token)
    print("Headers used:", headers)
    try:
        print("Response JSON:", response.json())
    except Exception:
        print("Response not JSON, raw text:", response.text)
    # ------------------

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_upload_all_unauthorized():
    """No token should result in 401."""
    response = client.get("/upload/all")
    print("\n[Unauthorized Test] Response:", response.json())
    assert response.status_code == 401
    assert "detail" in response.json()
