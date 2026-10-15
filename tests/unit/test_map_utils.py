import pytest
import folium
from src.frontend.map_utils import render_dynamic_map, sanitize_cql, get_legend_url

def test_render_empty_payload():
    """Unit Test: Verifies empty payload defaults to Florida."""
    m = render_dynamic_map({})
    
    assert isinstance(m, folium.Map)
    assert m.location == [27.99, -81.76]
    
    # Check that no WmsTileLayer was added
    # m._children contains the layers
    wms_layers = [child for child in m._children.values() if isinstance(child, folium.raster_layers.WmsTileLayer)]
    assert len(wms_layers) == 0

def test_render_valid_payload():
    """Integration Test: Verifies WMS layer is appended correctly."""
    payload = {
        "layer": "test_layer",
        "cql_filter": "pop > 100",
        "color": "0000FF"
    }
    m = render_dynamic_map(payload)
    
    wms_layers = [child for child in m._children.values() if isinstance(child, folium.raster_layers.WmsTileLayer)]
    assert len(wms_layers) == 1
    
    wms_layer = wms_layers[0]
    assert wms_layer.options["layers"] == "test_layer"
    assert "pop > 100" in str(wms_layer.options)
    assert "color:0000FF" in str(wms_layer.options)

def test_cql_sanitizer():
    """Security Test: Verifies malicious SQL/CQL is sanitized or rejected."""
    # Semicolons should be stripped (benign example)
    assert sanitize_cql("pop > 100;") == "pop > 100"
    
    # Outright malicious commands should return empty string (reject)
    assert sanitize_cql("pop > 100; DROP TABLE users") == ""
    
    # Test valid CQL
    assert sanitize_cql("income >= 50000") == "income >= 50000"
    
    # Test SQL injection dashes
    assert sanitize_cql("name = 'test' --") == "name = 'test' "
    
    # Test Delete and Update
    assert sanitize_cql("DELETE FROM users") == ""
    assert sanitize_cql("UPDATE layers SET") == ""

def test_get_legend_url():
    url = get_legend_url({"layer": "my_layer"})
    assert "REQUEST=GetLegendGraphic" in url
    assert "LAYER=my_layer" in url
    assert get_legend_url({}) == ""
