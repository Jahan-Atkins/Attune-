"""
Fake location system for a learning project — no real geocoding API.

DEMO_CITIES is a fixed list of cities with real lat/lng. Both the
instructor profile form and the customer scheduling flow offer this same
list as a dropdown, so "location" in this app just means "which of these
cities did you pick" rather than a real address lookup.

haversine_distance is the real formula (not a fake one) for
great-circle distance between two lat/lng points — it's what actually
drives "nearest instructor" in the matching logic, so it needs to be
correct even though the coordinates feeding it are demo data.
"""
import math

DEMO_CITIES = [
    {"name": "New York, NY", "lat": 40.7128, "lng": -74.0060},
    {"name": "Los Angeles, CA", "lat": 34.0522, "lng": -118.2437},
    {"name": "Chicago, IL", "lat": 41.8781, "lng": -87.6298},
    {"name": "Austin, TX", "lat": 30.2672, "lng": -97.7431},
    {"name": "Seattle, WA", "lat": 47.6062, "lng": -122.3321},
    {"name": "Denver, CO", "lat": 39.7392, "lng": -104.9903},
]

CITY_BY_NAME = {city["name"]: city for city in DEMO_CITIES}

EARTH_RADIUS_KM = 6371.0


def city_name_for_coords(lat, lng):
    """Reverse lookup back to a demo city's display name. Coordinates in
    this app only ever come from DEMO_CITIES in the first place (picked
    from a dropdown, never geocoded), so an exact match always succeeds
    for real data — this returns None only for unset/None coordinates."""
    if lat is None or lng is None:
        return None
    for city in DEMO_CITIES:
        if city["lat"] == lat and city["lng"] == lng:
            return city["name"]
    return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points, in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c
