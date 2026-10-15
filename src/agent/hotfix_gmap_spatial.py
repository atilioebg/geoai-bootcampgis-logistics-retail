"""
Hotfix: Create a Spatial Dimension table for Google Maps Reviews.
Extracts unique places, geocodes their coordinates using Google Maps API,
and loads them into a new PostGIS table `gmap_places`.
"""

import os
import sys
import json
import kagglehub
import pandas as pd
import geopandas as gpd
import googlemaps
from dotenv import load_dotenv
from tqdm import tqdm
from sqlalchemy import text

from src.agent.db_engine import DBEngine

load_dotenv()

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
CACHE_FILE = os.path.join(PROJECT_ROOT, "data", "complementary_lessons_materials", ".geocoding_cache.json")

def load_geocoding_cache() -> dict:
    """Load previously geocoded locations to save time and API quota."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_geocoding_cache(cache: dict):
    """Save geocoded locations to local disk."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f)

def run_hotfix():
    print("[1/4] Extracting unique places from Kaggle dataset...")
    # Download dataset
    path = kagglehub.dataset_download("betianalopezandueza/gmap-state-florida")
    
    # Find the CSV file in the downloaded path
    csv_files = [f for f in os.listdir(path) if f.endswith('.csv')]
    if not csv_files:
        raise FileNotFoundError(f"No CSV file found in {path}")
    
    csv_path = os.path.join(path, csv_files[0])
    df = pd.read_csv(csv_path)
    
    # Extract unique places
    # Assuming 'name_x' and 'gmap_id' are the columns based on instructions
    unique_places = df[['gmap_id', 'name_x']].drop_duplicates().dropna(subset=['gmap_id', 'name_x'])
    print(f"  Found {len(unique_places)} unique places.")

    print("\n[2/4] Geocoding places using Google Maps API...")
    api_key = os.getenv("GCP_API_KEY")
    if not api_key:
        raise ValueError("GCP_API_KEY not found in environment variables.")
    
    gmaps = googlemaps.Client(key=api_key)
    cache = load_geocoding_cache()
    
    results_list = []
    
    # Only geocode what isn't in cache
    new_geocodes = 0
    for _, row in tqdm(unique_places.iterrows(), total=len(unique_places), desc="Geocoding"):
        gmap_id = row['gmap_id']
        name = row['name_x']
        
        if gmap_id in cache:
            lat, lng = cache[gmap_id]['lat'], cache[gmap_id]['lng']
        else:
            # Add "Florida, USA" to improve accuracy
            query = f"{name}, Florida, USA"
            try:
                geocode_result = gmaps.geocode(query)
                if geocode_result:
                    location = geocode_result[0]['geometry']['location']
                    lat, lng = location['lat'], location['lng']
                else:
                    # Fallback if not found
                    lat, lng = None, None
                
                cache[gmap_id] = {'lat': lat, 'lng': lng}
                new_geocodes += 1
                
                # Save cache periodically
                if new_geocodes % 100 == 0:
                    save_geocoding_cache(cache)
                    
            except Exception as e:
                print(f"Error geocoding {name}: {e}")
                lat, lng = None, None
                
        if lat is not None and lng is not None:
            results_list.append({
                'gmap_id': gmap_id,
                'name': name,
                'latitude': lat,
                'longitude': lng
            })
            
    if new_geocodes > 0:
        save_geocoding_cache(cache)
        
    print(f"  Geocoded {len(results_list)} places successfully.")
    
    print("\n[3/4] Transforming to GeoDataFrame...")
    places_df = pd.DataFrame(results_list)
    gdf = gpd.GeoDataFrame(
        places_df, 
        geometry=gpd.points_from_xy(places_df.longitude, places_df.latitude),
        crs="EPSG:4326"
    )
    
    # Rename default 'geometry' column to 'geom' for PostGIS consistency
    gdf.rename_geometry('geom', inplace=True)
    
    print("\n[4/4] Loading to PostGIS (gmap_places)...")
    db = DBEngine()
    engine = db.get_engine()
    
    # We use GeoAlchemy2 under the hood in geopandas.to_postgis
    gdf.to_postgis("gmap_places", engine, if_exists="replace", index=False)
    
    print("  ✅ Table 'gmap_places' created successfully.")
    return db

if __name__ == "__main__":
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
            
    print("=" * 60)
    print("  STARTING HOTFIX: gmap_places Spatial Dimension")
    print("=" * 60)
    
    db = run_hotfix()
    engine = db.get_engine()
    
    print("\n" + "=" * 60)
    print("  VALIDATION")
    print("=" * 60)
    
    with engine.connect() as conn:
        # 1. Total unique places loaded
        count_res = conn.execute(text("SELECT COUNT(*) FROM gmap_places")).scalar()
        print(f"  Total unique places loaded: {count_res}")
        
        # 2. Spatial Data Validation (SRID = 4326 and not null)
        invalid_res = conn.execute(
            text("SELECT COUNT(*) FROM gmap_places WHERE ST_SRID(geom) != 4326 OR geom IS NULL;")
        ).scalar()
        
        assert invalid_res == 0, f"Spatial validation failed: {invalid_res} rows have invalid/null geometries."
        print("  ✅ Spatial Data Validation: PASS (All places have valid 4326 geometries)")
        
    print("\n  🎉 Hotfix applied successfully!")
