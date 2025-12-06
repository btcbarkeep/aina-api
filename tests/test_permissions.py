# tests/test_permissions.py

"""
Tests for permission checks and access control.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


def test_contractor_access_own_data(client: TestClient, mock_contractor_user):
    """Test that contractors can only access their own data."""
    with patch("routers.contractors.get_current_user", return_value=mock_contractor_user):
        with patch("routers.contractors.get_supabase_client") as mock_supabase:
            mock_client = Mock()
            mock_query = Mock()
            mock_query.eq.return_value = mock_query
            mock_query.execute.return_value = Mock(data=[
                {"id": "contractor-123", "name": "Test Contractor"}
            ])
            mock_client.table.return_value.select.return_value = mock_query
            mock_supabase.return_value = mock_client
            
            # Contractor should be able to access their own data
            response = client.get("/contractors/contractor-123")
            assert response.status_code == 200


def test_contractor_access_other_data_forbidden(client: TestClient, mock_contractor_user):
    """Test that contractors cannot access other contractors' data."""
    with patch("routers.contractors.get_current_user", return_value=mock_contractor_user):
        # Contractor trying to access different contractor's data
        response = client.get("/contractors/other-contractor-id")
        assert response.status_code == 403


def test_admin_access_all_data(client: TestClient, mock_current_user):
    """Test that admins can access all data."""
    with patch("routers.buildings.get_current_user", return_value=mock_current_user):
        with patch("routers.buildings.get_supabase_client") as mock_supabase:
            mock_client = Mock()
            mock_query = Mock()
            mock_query.limit.return_value = mock_query
            mock_query.execute.return_value = Mock(data=[
                {"id": "1", "name": "Building 1"},
                {"id": "2", "name": "Building 2"}
            ])
            mock_client.table.return_value.select.return_value = mock_query
            mock_supabase.return_value = mock_client
            
            response = client.get("/buildings")
            assert response.status_code == 200
            data = response.json()
            assert len(data["data"]) == 2

