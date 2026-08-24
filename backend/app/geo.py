"""
Two location systems live here side by side.

DEMO_CITIES is a fixed list of cities with real lat/lng — only
instructor-created open session listings still offer this as a dropdown
(routers/sessions.py), so for *that* flow "location" just means "which
of these cities did you pick," no real geocoding involved.

Everywhere else — the customer availability step and the instructor's
own profile — geocode_address() calls OpenStreetMap's free Nominatim API
to turn whatever city/state someone typed into real coordinates, so
instructor-distance matching is based on real locations, not a pick from
a short fixed list. This is the only external network dependency
anywhere in this app; see geocode_address's docstring for the usage-
policy details (User-Agent, rate throttle, result cache) that shaped how
it's called, and tests/conftest.py's fake_geocoding fixture for why the
test suite never actually hits the network.

haversine_distance is the real formula (not a fake one) for
great-circle distance between two lat/lng points — it's what actually
drives "nearest instructor" in the matching logic, and it works
identically regardless of which of the two systems above produced the
coordinates feeding it.
"""
import math
import time
from threading import Lock

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
# ~1 request/second — omitting the header, or calling faster than that,
# risks the IP getting blocked outright. GEOCODE_THROTTLE_SECONDS/
# _last_call_at enforce the second half of that below.
GEOCODING_USER_AGENT = "Attune-App/1.0 (https://attune-q29q.onrender.com)"

# A simple in-process, global throttle — not per-user like rate_limit.py's
# login/forgot-password limiter (there's no "identifier" here; it's this
# server's own outbound call rate to someone else's API, not a per-user
# attempt count), but the same "plain module-level state, no new infra"
# spirit: a single process is all this deployment has, so a Lock-guarded
# timestamp is enough. Blocks (briefly, via sleep) rather than rejecting —
# a geocode is a small, synchronous part of request creation/profile
# update, not a hot path worth failing fast on.
GEOCODE_THROTTLE_SECONDS = 1.0
_last_call_at = 0.0
_throttle_lock = Lock()

# Also a plain module-level dict, same reasoning — many customers and
# instructors will share a handful of real cities, and Nominatim's usage
# policy explicitly discourages repeat lookups for the same query.
# Unbounded, but the realistic key space (distinct "city, state" strings
# actually typed) stays small for an app this size; revisit if that
# stops being true. Only successful lookups are cached — a transient
# network hiccup or Nominatim outage shouldn't permanently blacklist a
# real city for the rest of the process's life.
_geocode_cache = {}
_geocode_cache_lock = Lock()


def _throttle() -> None:
    global _last_call_at
    with _throttle_lock:
        wait = GEOCODE_THROTTLE_SECONDS - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


def geocode_address(city: str, state: str):
    """Real geocoding — resolves city+state to real coordinates via
    Nominatim. Used by both the customer availability step and the
    instructor's own profile. Deliberately city-level, not full-street-
    address-level: tried querying a complete street address first, and
    found Nominatim's free public index has patchy house-number-level
    coverage — a real test query for a famous, unambiguous Manhattan
    address returned a same-named street in a small town 240km away,
    silently, with no error. City-level geocoding doesn't have that
    failure mode (cities are reliably well-covered), and this app's
    matching logic only ever needs city-scale precision (haversine
    distance for "nearest instructor," not real delivery routing) — so
    trading street-level precision for reliability is the right call. A
    customer's street address is still collected and stored for display
    (see Customer.address_line) — it's just not part of what determines
    location; don't feed it back into this query without re-solving the
    accuracy problem above. Returns {"lat": float, "lng": float}, or None
    if the city/state couldn't be resolved — callers turn None into a 400
    asking the customer to check what they typed, same "fail fast with a
    clear message" pattern as the old fixed dropdown's unknown-city check.
    Results are cached (see _geocode_cache) and outbound calls are
    throttled to Nominatim's ~1/second usage-policy cap (see _throttle)."""
    query = ", ".join(part.strip() for part in (city, state) if part and part.strip())
    if not query:
        return None

    cache_key = query.lower()
    with _geocode_cache_lock:
        cached = _geocode_cache.get(cache_key)
    if cached is not None:
        return cached

    _throttle()
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
        coords = {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}
    except (KeyError, TypeError, ValueError):
        return None

    with _geocode_cache_lock:
        _geocode_cache[cache_key] = coords
    return coords


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lng points, in kilometers."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c
