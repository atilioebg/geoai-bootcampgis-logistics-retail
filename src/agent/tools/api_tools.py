"""
GeoAI Tools for interacting with external APIs.
"""
import os
import requests
import json
from dotenv import load_dotenv
from langchain_core.tools import tool

# Ensure environment variables are loaded
load_dotenv()

def decode_polyline(polyline_str: str) -> list:
    """Decodes a Google polyline string into a list of [lng, lat] coordinates."""
    index, lat, lng = 0, 0, 0
    coordinates = []
    length = len(polyline_str)
    
    while index < length:
        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat
        
        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng
        
        coordinates.append([lng / 1e5, lat / 1e5])
    return coordinates

def _parse_location(loc_str: str) -> dict:
    """Parses a location string into either an address or latLng object."""
    loc_str = str(loc_str).strip()
    if "," in loc_str:
        parts = loc_str.split(",")
        try:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}
        except ValueError:
            pass
    return {"address": loc_str}

@tool
def get_route_distance_time(origin: str, destination: str) -> dict:
    """
    Calculates the real driving distance and estimated time of arrival (ETA) 
    between two text addresses using the Google Routes API v2.
    """
    api_key = os.getenv("GCP_API_KEY")
    if not api_key:
        return {"error": "GCP_API_KEY environment variable not found.", "source": "google_routes"}
        
    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
    }
    payload = {
        "origin": _parse_location(origin),
        "destination": _parse_location(destination),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("routes"):
            route = data["routes"][0]
            dist_meters = route.get("distanceMeters", 0)
            dist_km = round(dist_meters / 1000.0, 2)
            
            dur_str = route.get("duration", "0s")
            dur_seconds = int(dur_str.rstrip('s'))
            dur_mins = round(dur_seconds / 60.0)
            
            polyline_str = route.get("polyline", {}).get("encodedPolyline", "")
            route_geojson = None
            if polyline_str:
                coordinates = decode_polyline(polyline_str)
                route_geojson = {
                    "type": "LineString",
                    "coordinates": coordinates
                }
            
            return {
                "distance": f"{dist_km} km",
                "duration": f"{dur_mins} mins",
                "route_geojson": route_geojson,
                "source": "google_routes"
            }
        else:
            return {
                "error": "API Error or no route found.",
                "source": "google_routes"
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "error": f"HTTP Request failed: {str(e)}",
            "source": "google_routes"
        }
    except Exception as e:
        return {
            "error": f"Failed to parse response: {str(e)}",
            "source": "google_routes"
        }

if __name__ == "__main__":
    print("--- Testing get_route_distance_time tool ---")
    
    print("\nInvoking tool with coordinates...")
    result = get_route_distance_time.invoke({
        "origin": "27.9506, -82.4572", # Tampa coordinates
        "destination": "Orlando, FL"
    })
    
    print("\nResult Keys:")
    print(result.keys())
