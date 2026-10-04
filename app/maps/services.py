import math
import requests
from flask import current_app

METERS_PER_MILE = 1609.344

def _haversine_meters(lat1, lng1, lat2, lng2):
    radius = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))

def get_driving_route(start_lat, start_lng, end_lat, end_lng):
    base = current_app.config["OSRM_BASE_URL"].rstrip("/")
    coordinates = f"{start_lng},{start_lat};{end_lng},{end_lat}"
    url = f"{base}/route/v1/driving/{coordinates}"
    params = {"overview": "full", "geometries": "geojson", "steps": "true"}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") == "Ok" and payload.get("routes"):
            route = payload["routes"][0]
            distance = float(route["distance"])
            duration = float(route["duration"])
            return {
                "provider": "osrm",
                "is_fallback": False,
                "distance_meters": round(distance, 1),
                "distance_miles": round(distance / METERS_PER_MILE, 2),
                "duration_seconds": round(duration),
                "duration_minutes": round(duration / 60.0, 1),
                "geometry": route["geometry"],
                "legs": route.get("legs", []),
            }
    except Exception as exc:
        current_app.logger.warning("OSRM routing failed: %s", exc)

    direct_distance = _haversine_meters(start_lat, start_lng, end_lat, end_lng)
    estimated_road_distance = direct_distance * 1.22
    estimated_duration = max(60.0, estimated_road_distance / 11.176)
    return {
        "provider": "fallback",
        "is_fallback": True,
        "distance_meters": round(estimated_road_distance, 1),
        "distance_miles": round(estimated_road_distance / METERS_PER_MILE, 2),
        "duration_seconds": round(estimated_duration),
        "duration_minutes": round(estimated_duration / 60.0, 1),
        "geometry": {
            "type": "LineString",
            "coordinates": [[start_lng, start_lat], [end_lng, end_lat]],
        },
        "legs": [],
    }

def get_route_estimate(pickup_lat, pickup_lng, destination_lat, destination_lng):
    return get_driving_route(pickup_lat, pickup_lng, destination_lat, destination_lng)
