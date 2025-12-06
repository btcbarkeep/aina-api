# tests/test_auth.py

"""
Tests for authentication endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


def test_login_success(client: TestClient):
    """Test successful login."""
    with patch("routers.auth.get_supabase_client") as mock_supabase:
        mock_client = Mock()
        mock_session = Mock()
        mock_session.access_token = "test-token"
        mock_response = Mock()
        mock_response.session = mock_session
        mock_client.auth.sign_in_with_password.return_value = mock_response
        mock_supabase.return_value = mock_client
        
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "password123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] == "test-token"


def test_login_invalid_credentials(client: TestClient):
    """Test login with invalid credentials."""
    with patch("routers.auth.get_supabase_client") as mock_supabase:
        mock_client = Mock()
        mock_client.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")
        mock_supabase.return_value = mock_client
        
        response = client.post(
            "/auth/login",
            json={"email": "test@example.com", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401
        assert "Invalid email or password" in response.json()["detail"]


def test_password_reset_rate_limiting(client: TestClient):
    """Test password reset rate limiting."""
    with patch("routers.auth.get_supabase_client") as mock_supabase:
        mock_client = Mock()
        mock_client.auth.reset_password_for_email.return_value = None
        mock_supabase.return_value = mock_client
        
        # Make 5 requests (should succeed)
        for i in range(5):
            response = client.post(
                "/auth/initiate-password-setup",
                json={"email": "test@example.com"}
            )
            assert response.status_code == 200
        
        # 6th request should be rate limited
        response = client.post(
            "/auth/initiate-password-setup",
            json={"email": "test@example.com"}
        )
        assert response.status_code == 429

