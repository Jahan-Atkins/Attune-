from app.geo import haversine_distance, city_name_for_coords, DEMO_CITIES


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
