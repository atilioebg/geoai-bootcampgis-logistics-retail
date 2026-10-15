"""
GeoAI Swarm - Map Helper Module.
Handles dynamic WMS connection to GeoServer and folium integration.
"""
import folium
import re
from branca.element import Template, MacroElement
from sqlalchemy import text
from src.agent.db_engine import DBEngine

db = DBEngine()

# Local GeoServer Configuration
GEOSERVER_WMS_URL = "http://localhost:8080/geoserver/bootcampgis/wms"

def sanitize_cql(cql_string: str) -> str:
    """Basic Security Sanitizer to prevent CQL Injection."""
    if not cql_string:
        return ""
    
    sanitized = re.sub(r"[;]", "", cql_string)
    sanitized = re.sub(r"--", "", sanitized)
    
    if "drop " in sanitized.lower() or "delete " in sanitized.lower() or "update " in sanitized.lower():
        return ""
        
    return sanitized

def _add_legend(m: folium.Map, payload: dict):
    """Injects a floating HTML legend into the Folium map."""
    color_hex = payload.get("color", "FF0000")
    if not color_hex.startswith("#"):
        color_hex = f"#{color_hex}"

    is_logistics = "buffer_geojson" in payload or "road_geojson" in payload

    if is_logistics:
        legend_content = """
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: rgba(0,0,255,0.2); border: 1px solid blue; margin-right: 8px;"></div>
            <span>Catchment Buffer</span>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 4px; background-color: orange; margin-right: 8px;"></div>
            <span>Target Infrastructure</span>
        </div>
        <div style="display: flex; align-items: center;">
            <span style="color: green; font-size: 18px; margin-right: 8px;">★</span>
            <span>Optimal Logistics Hub</span>
        </div>
        """
    else:
        has_layer = bool(payload.get("layer"))
        has_winner_zip = bool(payload.get("winner_zip"))
        has_route = bool(payload.get("route_geojson"))
        poi_ids = payload.get("highlight_poi_ids", [])
        
        has_winner_poi = has_route and len(poi_ids) > 0
        has_benchmarks = (not has_route and len(poi_ids) > 0) or (has_route and len(poi_ids) > 1)
        has_winner = has_winner_zip or has_winner_poi

        legend_content = ""
        
        if has_layer:
            legend_content += """
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 15px; height: 15px; background-color: transparent; border: 2px solid #3388ff; margin-right: 8px;"></div>
            <span>Suggested Locations</span>
        </div>"""
        
        if has_winner:
            legend_content += """
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <span style="color: orange; font-size: 18px; margin-right: 8px;">★</span>
            <span>Top-Ranked Place (Winner)</span>
        </div>"""
        
        if has_benchmarks:
            legend_content += """
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <div style="width: 12px; height: 12px; background-color: #38AADD; border-radius: 50%; margin-right: 10px;"></div>
            <span>Existing Benchmarks</span>
        </div>"""
        
        # Add Driving Route if applicable
        if has_route:
            legend_content += """
        <div style="display: flex; align-items: center;">
            <div style="width: 15px; height: 4px; background-color: #3388ff; margin-right: 8px;"></div>
            <span>Driving Route</span>
        </div>"""

    template = f"""
    {{% macro html(this, kwargs) %}}
    <div style="
        position: fixed; 
        bottom: 50px; 
        left: 50px; 
        width: auto; 
        height: auto; 
        background-color: white; 
        color: black;
        border:2px solid grey; 
        z-index:9999; 
        font-size:14px;
        padding: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.3);
        border-radius: 5px;
        ">
        <h4 style="margin-top: 0; margin-bottom: 5px;">GeoAI Legend</h4>
        {legend_content}
    </div>
    {{% endmacro %}}
    """
    macro = MacroElement()
    macro._template = Template(template)
    m.get_root().add_child(macro)

def render_dynamic_map(payload: dict) -> folium.Map:
    """
    Renders a Folium map based on the AI payload.
    Processes WMS layers, GeoJSON lines/polygons, and markers.
    """
    # Default map centered on Tampa
    m = folium.Map(location=[27.9506, -82.4572], zoom_start=11, tiles=None)
    
    # Add reliable Google Maps Tiles without watermarks
    folium.TileLayer(
        tiles='http://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Maps',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Add Google Satellite Tiles
    folium.TileLayer(
        tiles='http://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    if not payload:
        return m
        
    bounds = []
    
    # 1. WMS Layer (Geomarketing)
    layer = payload.get("layer")
    cql_filter = payload.get("cql_filter", "")
    
    if layer:
        safe_cql = sanitize_cql(cql_filter)
        
        wms_kwargs = {}
        if safe_cql:
            wms_kwargs["cql_filter"] = safe_cql # Must be lowercase
            
        folium.raster_layers.WmsTileLayer(
            url=GEOSERVER_WMS_URL,
            name=f"GeoAI: {layer}",
            layers=layer,
            fmt="image/png",
            transparent=True,
            styles="style_geomarketing",
            **wms_kwargs
        ).add_to(m)
        
    # 2. GeoJSON Layers (Logistics / Routing)
    buffer_geojson = payload.get("buffer_geojson")
    road_geojson = payload.get("road_geojson")
    route_geojson = payload.get("route_geojson")
    
    if buffer_geojson:
        folium.GeoJson(
            buffer_geojson,
            name="Catchment Buffer",
            style_function=lambda x: {'fillColor': 'blue', 'color': 'blue', 'weight': 1, 'fillOpacity': 0.2}
        ).add_to(m)
        
    if road_geojson:
        folium.GeoJson(
            road_geojson,
            name="Target Infrastructure",
            style_function=lambda x: {'color': 'orange', 'weight': 5, 'opacity': 0.8}
        ).add_to(m)
        
    if route_geojson:
        folium.GeoJson(
            route_geojson,
            name="Driving Route",
            style_function=lambda x: {'color': '#3388ff', 'weight': 6, 'opacity': 0.9}
        ).add_to(m)
        
    # 3. POI Markers
    highlight_ids = payload.get("highlight_poi_ids", [])
    if highlight_ids:
        try:
            placeholders = ', '.join([f"'{str(pid).replace('\'', '\'\'')}'" for pid in highlight_ids])
            sql = text(f"""
                SELECT gmap_id, name, ST_Y(geom) as lat, ST_X(geom) as lng
                FROM gmap_places
                WHERE gmap_id IN ({placeholders})
            """)
            with db.get_engine().connect() as conn:
                res = conn.execute(sql).fetchall()
                # Create a lookup dict to preserve the order of highlight_ids
                poi_dict = {row.gmap_id: row for row in res}
                
                for i, pid in enumerate(highlight_ids):
                    row = poi_dict.get(pid)
                    if row and row.lat and row.lng:
                        bounds.append([row.lat, row.lng])
                        
                        # If it's a routing query, the first POI is the winner/destination
                        if i == 0 and route_geojson:
                            folium.Marker(
                                location=[row.lat, row.lng],
                                popup=f"🏆 Winner: {row.name}",
                                icon=folium.Icon(color="orange", icon="star")
                            ).add_to(m)
                        else:
                            folium.Marker(
                                location=[row.lat, row.lng],
                                popup=row.name,
                                icon=folium.Icon(color="blue", icon="info-sign")
                            ).add_to(m)
        except Exception as e:
            print(f"Error fetching POI markers: {e}")
            
    # 4. Logistics Hub Marker
    hub_lat = payload.get("hub_lat")
    hub_lng = payload.get("hub_lng")
    if hub_lat and hub_lng:
        bounds.append([hub_lat, hub_lng])
        folium.Marker(
            location=[hub_lat, hub_lng],
            popup="Optimal Logistics Hub",
            icon=folium.Icon(color="green", icon="star")
        ).add_to(m)
        
    # 5. Winner ZIP Highlight
    winner_zip = payload.get("winner_zip")
    if winner_zip:
        sql = text("""
            SELECT ST_Y(ST_Transform(ST_Centroid(geometry), 4326)) AS lat,
                   ST_X(ST_Transform(ST_Centroid(geometry), 4326)) AS lng
            FROM spatial_tiger_71000_zcta5
            WHERE zcta5ce20 = :zip
        """)
        try:
            with db.get_engine().connect() as conn:
                res = conn.execute(sql, {"zip": winner_zip}).fetchone()
                if res and res.lat:
                    bounds.append([res.lat, res.lng])
                    folium.Marker(
                        location=[res.lat, res.lng],
                        popup=f"🏆 Winner: {winner_zip}",
                        icon=folium.Icon(color="orange", icon="star")
                    ).add_to(m)
        except Exception as e:
            print(f"Error highlighting winner zip: {e}")
        
    # 6. Fit Bounds safely
    if bounds:
        m.fit_bounds(bounds, padding=(30, 30))
        
    _add_legend(m, payload)
    folium.LayerControl().add_to(m)
    return m
