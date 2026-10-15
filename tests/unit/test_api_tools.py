"""
Unit tests for API tools.
"""
import pytest
from unittest.mock import patch, MagicMock
from src.agent.tools.api_tools import get_route_distance_time

@patch("src.agent.tools.api_tools.requests.post")
@patch("src.agent.tools.api_tools.os.getenv")
def test_get_route_distance_time_success(mock_getenv, mock_post):
    """Test successful route calculation using Routes API v2."""
    mock_getenv.return_value = "fake_api_key"
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "routes": [
            {
                "distanceMeters": 100000,
                "duration": "4500s"
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    result = get_route_distance_time.invoke({
        "origin": "City A",
        "destination": "City B"
    })
    
    assert result["distance"] == "100.0 km"
    assert result["duration"] == "75 mins"
    assert result["source"] == "google_routes"
    assert "error" not in result
    
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert kwargs["headers"]["X-Goog-Api-Key"] == "fake_api_key"
    assert kwargs["headers"]["X-Goog-FieldMask"] == "routes.distanceMeters,routes.duration"
    assert kwargs["json"]["origin"]["address"] == "City A"
    assert kwargs["json"]["destination"]["address"] == "City B"
    assert kwargs["json"]["travelMode"] == "DRIVE"
    assert kwargs["json"]["routingPreference"] == "TRAFFIC_AWARE"

@patch("src.agent.tools.api_tools.requests.post")
@patch("src.agent.tools.api_tools.os.getenv")
def test_get_route_distance_time_no_route(mock_getenv, mock_post):
    """Test when API returns empty routes."""
    mock_getenv.return_value = "fake_api_key"
    
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "routes": []
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response
    
    result = get_route_distance_time.invoke({
        "origin": "Ocean",
        "destination": "Mountain"
    })
    
    assert "error" in result
    assert "no route found" in result["error"]
    assert result["source"] == "google_routes"

@patch("src.agent.tools.api_tools.os.getenv")
def test_get_route_distance_time_no_api_key(mock_getenv):
    """Test behavior when API key is missing."""
    mock_getenv.return_value = None
    
    result = get_route_distance_time.invoke({
        "origin": "A",
        "destination": "B"
    })
    
    assert "error" in result
    assert "GCP_API_KEY" in result["error"]

@patch("src.agent.tools.api_tools.requests.post")
@patch("src.agent.tools.api_tools.os.getenv")
def test_get_route_distance_time_http_error(mock_getenv, mock_post):
    """Test behavior on HTTP error."""
    import requests
    mock_getenv.return_value = "fake_api_key"
    
    mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
    
    result = get_route_distance_time.invoke({
        "origin": "A",
        "destination": "B"
    })
    
    assert "error" in result
    assert "HTTP Request failed" in result["error"]
