# tests/test_buildings.py

"""
Tests for building endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock


def test_list_buildings_success(client: TestClient, mock_current_user):
    """Test successful building list retrieval."""
    with patch("routers.buildings.get_current_user", return_value=mock_current_user):
        with patch("routers.buildings.get_supabase_client") as mock_supabase:
            mock_client = Mock()
            mock_query = Mock()
            mock_query.limit.return_value = mock_query
            mock_query.in_.return_value = mock_query
            mock_query.execute.return_value = Mock(data=[
                {"id": "1", "name": "Test Building", "city": "Honolulu"}
            ])
            mock_client.table.return_value.select.return_value = mock_query
            mock_supabase.return_value = mock_client
            
            response = client.get("/buildings?limit=10")
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "data" in data


def test_get_building_not_found(client: TestClient, mock_current_user):
    """Test getting a non-existent building."""
    with patch("routers.buildings.get_current_user", return_value=mock_current_user):
        with patch("routers.buildings.get_supabase_client") as mock_supabase:
            mock_client = Mock()
            mock_query = Mock()
            mock_query.eq.return_value = mock_query
            mock_query.execute.return_value = Mock(data=[])
            mock_client.table.return_value.select.return_value = mock_query
            mock_supabase.return_value = mock_client
            
            response = client.get("/buildings/non-existent-id")
            
            assert response.status_code == 404


def test_create_building_duplicate(client: TestClient, mock_current_user):
    """Test creating a duplicate building."""
    with patch("routers.buildings.get_current_user", return_value=mock_current_user):
        with patch("routers.buildings.get_supabase_client") as mock_supabase:
            mock_client = Mock()
            mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("duplicate key")
            mock_supabase.return_value = mock_client
            
            response = client.post(
                "/buildings",
                json={"name": "Duplicate Building", "city": "Honolulu", "state": "HI"}
            )
            
            assert response.status_code == 400

