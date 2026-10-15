"""
GeoAI Tools for Spatial Database Operations.
"""
import os
import sys

# Add the project root to sys.path so 'src' module can be found when run directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from langchain_core.tools import tool
from sqlalchemy import text
from src.agent.db_engine import DBEngine
from pydantic import Field
import json

db = DBEngine()

@tool
def calculate_optimal_logistics_hub(
    road_name: str = Field(..., description="The name of the target road (e.g., 'Interstate 4')."),
    radius: float = Field(..., gt=0, description="Radius magnitude."),
    unit: str = Field(..., description="Unit of the radius (e.g., 'miles', 'km', 'meters').")
) -> dict:
    """
    Solves Logistics Location, Centroid Snapping, and Facility Placement problems.
    Calculates the count of POIs within a given radius of a road network centroid.
    """
    import re
    # Deterministic Unit Conversion
    unit_lower = unit.lower()
    if "mile" in unit_lower or "mi" in unit_lower:
        radius_km = radius * 1.60934
    elif "meter" in unit_lower and "kilometer" not in unit_lower and "km" not in unit_lower:
        radius_km = radius / 1000.0
    else:
        radius_km = radius

    # Normalize input to match DB format (strip spaces around hyphens)
    clean_road = re.sub(r'\s*-\s*', '-', road_name)
    if not clean_road.startswith('%'): clean_road = f"%{clean_road}"
    if not clean_road.endswith('%'): clean_road = f"{clean_road}%"

    sql_query = text("""
        WITH road_segments AS (
            SELECT ST_Union(geometry) AS geom
            FROM spatial_tiger_71000_edges
            WHERE fullname ILIKE :road_name
        ),
        road_centroid AS (
            SELECT ST_Centroid(geom) AS point FROM road_segments
        ),
        snapped_hub AS (
            SELECT ST_ClosestPoint(s.geom, c.point) AS geom
            FROM road_segments s, road_centroid c
        ),
        catchment_buffer AS (
            SELECT ST_Buffer(geom::geography, :radius_m)::geometry AS geom
            FROM snapped_hub
        )
        SELECT 
            ST_AsGeoJSON(s.geom) AS road_geojson,
            ST_AsGeoJSON(b.geom) AS buffer_geojson,
            ST_Y(ST_Transform(h.geom, 4326)) AS hub_lat,
            ST_X(ST_Transform(h.geom, 4326)) AS hub_lng,
            (SELECT COUNT(*) FROM gmap_places p, catchment_buffer cb WHERE ST_Intersects(p.geom, cb.geom)) AS poi_count
        FROM road_segments s, snapped_hub h, catchment_buffer b
    """)
    bind_params = {"road_name": clean_road, "radius_m": radius_km * 1000.0}
    
    try:
        with db.get_engine().connect() as conn:
            result = conn.execute(sql_query, bind_params).fetchone()
            if not result or not result.hub_lat:
                return {"status": "success", "results": []}
                
            return {
                "status": "success",
                "hub_lat": float(result.hub_lat),
                "hub_lng": float(result.hub_lng),
                "poi_count": int(result.poi_count),
                "road_geojson": json.loads(result.road_geojson) if result.road_geojson else None,
                "buffer_geojson": json.loads(result.buffer_geojson) if result.buffer_geojson else None,
                "results": [{"poi_count": int(result.poi_count)}] # Append compatible results format
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@tool
def find_geomarketing_gaps(
    target_category: str = Field(..., description="The exact base category of the business (e.g., 'restaurant', 'gym')."),
    target_income: float = Field(..., gt=0, description="The minimum income threshold for the target demographic."),
    find_absence: bool = Field(True, description="True for gap/absence analysis (underserved). False for presence analysis (overserved)."),
    city_name: str = Field("Tampa", description="The city name to limit the spatial search.")
) -> dict:
    """
    Handles Geomarketing Expansion, Gap Analysis, and Spatial Intersections.
    Finds ZIP codes intersecting with wealthy census tracts and specific business categories.
    """
    if find_absence:
        sql_query = text("""
            WITH city_boundary AS (
                SELECT geometry FROM spatial_tiger_71000_place WHERE feature_name = :city_name LIMIT 1
            ),
            valid_zctas AS (
                SELECT z.zcta5ce20, z.geometry
                FROM spatial_tiger_71000_zcta5 z, city_boundary cb
                WHERE ST_Area(z.geometry) > 0 AND ST_Intersects(z.geometry, cb.geometry)
            ),
            high_income_zctas AS (
                SELECT DISTINCT z.zcta5ce20
                FROM valid_zctas z
                JOIN spatial_tiger_71000_tract t ON ST_Intersects(z.geometry, t.geometry)
                JOIN demographics_acs_tract_tampa_2023 d ON t.geoid = d."GEOID"::text
                WHERE d.median_household_income > :target_income
            ),
            category_zctas AS (
                SELECT DISTINCT z.zcta5ce20
                FROM valid_zctas z
                JOIN gmap_places p ON ST_Intersects(z.geometry, p.geom)
                JOIN gmap_reviews_enriched r ON p.gmap_id = r.gmap_id
                WHERE r.category ILIKE :target_category
            )
            SELECT h.zcta5ce20
            FROM high_income_zctas h
            LEFT JOIN category_zctas c ON h.zcta5ce20 = c.zcta5ce20
            WHERE c.zcta5ce20 IS NULL
        """)
    else:
        sql_query = text("""
            WITH city_boundary AS (
                SELECT geometry FROM spatial_tiger_71000_place WHERE feature_name = :city_name LIMIT 1
            ),
            valid_zctas AS (
                SELECT z.zcta5ce20, z.geometry
                FROM spatial_tiger_71000_zcta5 z, city_boundary cb
                WHERE ST_Area(z.geometry) > 0 AND ST_Intersects(z.geometry, cb.geometry)
            )
            SELECT DISTINCT z.zcta5ce20
            FROM valid_zctas z
            JOIN spatial_tiger_71000_tract t ON ST_Intersects(z.geometry, t.geometry)
            JOIN demographics_acs_tract_tampa_2023 d ON t.geoid = d."GEOID"::text
            JOIN gmap_places p ON ST_Intersects(z.geometry, p.geom)
            JOIN gmap_reviews_enriched r ON p.gmap_id = r.gmap_id
            WHERE d.median_household_income > :target_income
            AND r.category ILIKE :target_category
        """)
        
    bind_params = {
        "target_income": target_income,
        "target_category": f"%{target_category}%",
        "city_name": city_name
    }
    
    try:
        with db.get_engine().connect() as conn:
            result = conn.execute(sql_query, bind_params)
            rows = [dict(row._mapping) for row in result.fetchall()]
            
            zips = [row['zcta5ce20'] for row in rows if row.get('zcta5ce20')]
            if zips:
                cql_in = "'" + "', '".join(zips) + "'"
                cql_filter = f"zcta5ce20 IN ({cql_in})"
            else:
                cql_filter = "zcta5ce20 = 'NONE'"
                
            return {
                "status": "success",
                "layer": "bootcampgis:spatial_tiger_71000_zcta5",
                "cql_filter": cql_filter,
                "color": "FF0000" if find_absence else "00FF00",
                "results": rows
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    print("Testing Spatial Tools Execution...")
    
    print("\n--- Test: find_geomarketing_gaps (Absence) ---")
    gaps_result = find_geomarketing_gaps.invoke({"target_category": "restaurant", "target_income": 75000, "find_absence": True, "city_name": "Tampa"})
    print(f"Result: {gaps_result}")
    
    print("\n--- Test: calculate_optimal_logistics_hub ---")
    logistics_result = calculate_optimal_logistics_hub.invoke({"road_name": "I-4", "radius": 5.0, "unit": "miles"})
    print(f"Result: Keys -> {logistics_result.keys()}")
