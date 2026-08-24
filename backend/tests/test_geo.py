import time

import httpx

from app import geo
from app.geo import haversine_distance, city_name_for_coords, DEMO_CITIES


class _FakeGeocodeResponse:
    """Stands in for httpx's Response — just enough surface for
    geocode_address to consume (raise_for_status/json)."""
    def __init__(self, results):
        self._results = results

    def raise_for_status(self):
        pass

    def json(self):
        return self._results


def _real_geocode_address(monkeypatch):
    """conftest.py's fake_geocoding fixture (autouse) replaces
    geo.geocode_address for every test, since a real network call would
    make the suite slow/flaky/internet-dependent. These tests are
    specifically about that real implementation's caching/throttling, so
    they undo that one patch to get the real function back, then supply
    their own fake httpx.get instead — monkeypatch is function-scoped, so
    this reuses the same instance fake_geocoding already patched with,
    and only undoes that patch, nothing else."""
    monkeypatch.undo()
    geo._geocode_cache.clear()
    geo._last_call_at = 0.0
    return geo.geocode_address


def test_same_point_is_zero_distance():
    assert haversine_distance(40.7128, -74.0060, 40.7128, -74.0060) == 0


def test_distance_matches_known_reference_nyc_to_la():
    # Real-world great-circle distance NYC <-> LA is ~3936 km.
    distance = haversine_distance(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3900 < distance < 3970


def test_distance_matches_known_reference_chicago_to_denver():
    # Real-world great-circle distance Chicago <-> Denver is ~1478 km.
    distance = haversine_distance(41.8781, -87.6298, 39.7392, -104.9903)
    assert 1450 < distance < 1500


def test_distance_is_symmetric():
    a, b = DEMO_CITIES[0], DEMO_CITIES[1]
    forward = haversine_distance(a["lat"], a["lng"], b["lat"], b["lng"])
    backward = haversine_distance(b["lat"], b["lng"], a["lat"], a["lng"])
    assert forward == backward


def test_city_name_for_coords_round_trips_demo_cities():
    for city in DEMO_CITIES:
        assert city_name_for_coords(city["lat"], city["lng"]) == city["name"]


def test_city_name_for_coords_returns_none_for_missing_coords():
    assert city_name_for_coords(None, None) is None


def test_geocode_address_caches_repeat_lookups(monkeypatch):
    real_geocode = _real_geocode_address(monkeypatch)
    call_count = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        call_count["n"] += 1
        return _FakeGeocodeResponse([{"lat": "12.34", "lon": "56.78"}])

    monkeypatch.setattr(httpx, "get", fake_get)

    first = real_geocode("Testville", "TS")
    second = real_geocode("Testville", "TS")
    assert first == {"lat": 12.34, "lng": 56.78}
    assert second == first
    assert call_count["n"] == 1  # second lookup served from cache, no new HTTP request


def test_geocode_address_does_not_cache_failed_lookups(monkeypatch):
    real_geocode = _real_geocode_address(monkeypatch)
    call_count = {"n": 0}

    def fake_get_empty(url, params=None, headers=None, timeout=None):
        call_count["n"] += 1
        return _FakeGeocodeResponse([])  # Nominatim found nothing

    monkeypatch.setattr(httpx, "get", fake_get_empty)

    first = real_geocode("Bogus City", "ZZ")
    second = real_geocode("Bogus City", "ZZ")
    assert first is None
    assert second is None
    assert call_count["n"] == 2  # a failed lookup is never cached, so both retried


def test_geocode_address_throttles_consecutive_calls(monkeypatch):
    real_geocode = _real_geocode_address(monkeypatch)

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeGeocodeResponse([{"lat": "1.0", "lon": "2.0"}])

    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.monotonic()
    real_geocode("First City", "AA")
    real_geocode("Second City", "BB")  # a different query, so not cache-served
    elapsed = time.monotonic() - start
    assert elapsed >= geo.GEOCODE_THROTTLE_SECONDS
