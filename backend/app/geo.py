"""
Two location systems live here side by side.

DEMO_CITIES is a fixed list of cities with real lat/lng — the instructor
profile form and instructor-created open session listings still offer
this as a dropdown, so for *those* two flows "location" just means
"which of these cities did you pick," no real geocoding involved.

The customer flow is different: geocode_address() calls OpenStreetMap's
free Nominatim API to turn whatever address/city/state a customer typed
into real coordinates, so instructor-distance matching is based on their
actual location, not a pick from a short fixed list. This is the only
external network call anywhere in this app — see geocode_address's
docstring for the usage-policy details that shaped how it's called, and
tests/conftest.py's fake_geocoding fixture for why the test suite never
actually hits the network.

haversine_distance is the real formula (not a fake one) for
great-circle distance between two lat/lng points — it's what actually
drives "nearest instructor" in the matching logic, and it works
identically regardless of which of the two systems above produced the
coordinates feeding it.
"""
import math

import httpx

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


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
# requires a real identifying User-Agent and caps unauthenticated use at
# ~1 request/second. This app only ever geocodes once per new customer
# request — nowhere near that cap — but the header is required regardless
# of volume; omitting it risks the IP getting blocked outright.
GEOCODING_USER_AGENT = "Attune-App/1.0 (https://attune-q29q.onrender.com)"


def geocode_address(address: str, city: str, state: str):
    """Real geocoding for the customer flow — combines the three fields
    into one free-form query string and asks Nominatim for the best
    match. Returns {"lat": float, "lng": float}, or None if the address
    couldn't be resolved (not found, or Nominatim unreachable/erroring) —
    callers turn None into a 400 asking the customer to check what they
    typed, same "fail fast with a clear message" pattern as the old fixed
    dropdown's unknown-city check."""
    query = ", ".join(part.strip() for part in (address, city, state) if part and part.strip())
    if not query:
        return None
    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": GEOCODING_USER_AGENT},
            timeout=8.0,
        )
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not results:
        return None
    try:
        return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}
    except (KeyError, TypeError, ValueError):
        return None


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points, in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c
