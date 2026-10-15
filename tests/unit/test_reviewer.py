import pytest
from src.agent.agents.reviewer import _validate_gis_agent

def test_sensor_rejects_empty_payload():
    errors = _validate_gis_agent({})
    assert len(errors) == 1
    assert "No spatial tool was executed" in errors[0]

def test_sensor_rejects_failed_status():
    payload = {"status": "error", "message": "DB disconnected"}
    errors = _validate_gis_agent(payload)
    assert len(errors) == 1
    assert "failed with status 'error'" in errors[0]

def test_sensor_rejects_empty_viable_tracts():
    payload = {"status": "success", "viable_tracts": []}
    errors = _validate_gis_agent(payload)
    assert len(errors) == 1
    assert "Database returned empty result" in errors[0]

def test_sensor_rejects_missing_coordinates():
    payload = {"status": "success", "lat": None, "lon": -82.45}
    errors = _validate_gis_agent(payload)
    assert len(errors) == 1
    assert "Missing coordinates" in errors[0]

def test_sensor_approves_valid_payload():
    payload1 = {"status": "success", "viable_tracts": ["Tract 101"]}
    payload2 = {"status": "success", "lat": 27.95, "lon": -82.45}
    
    assert len(_validate_gis_agent(payload1)) == 0
    assert len(_validate_gis_agent(payload2)) == 0
