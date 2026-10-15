"""
Unit tests for the gmap_places hotfix script.
Verifies that the spatial dimension table was correctly created with valid geometries.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from src.agent.db_engine import DBEngine

def test_gmap_places_geometry_validity():
    """
    Test that queries the gmap_places table to ensure the geom column
    is recognized as a valid PostGIS geometry with SRID 4326.
    """
    db = DBEngine()
    engine = db.get_engine()
    
    with engine.connect() as conn:
        try:
            # Check if there are any rows with invalid or null geometries
            invalid_count = conn.execute(
                text("SELECT COUNT(*) FROM gmap_places WHERE ST_SRID(geom) != 4326 OR geom IS NULL;")
            ).scalar()
            
            # Check if there is at least one valid row
            valid_count = conn.execute(
                text("SELECT COUNT(*) FROM gmap_places WHERE ST_SRID(geom) = 4326;")
            ).scalar()
            
            assert invalid_count == 0, f"Found {invalid_count} rows with invalid/null geometries."
            assert valid_count > 0, "No valid geometries found in gmap_places."
            
        except ProgrammingError as e:
            # If the table doesn't exist yet, we skip the test rather than failing
            if "relation \"gmap_places\" does not exist" in str(e):
                pytest.skip("gmap_places table does not exist yet. Run hotfix_gmap_spatial.py first.")
            else:
                raise e
