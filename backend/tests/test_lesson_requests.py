from .conftest import add_availability, set_instructor_city, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


def _request_payload(**overrides):
    payload = {
        "specialty": "yoga",
        "city": "New York, NY",
        "requested_day": TUESDAY,
        "requested_start_time": "09:00",
        "requested_end_time": "11:00",
        **CARD,
    }
    payload.update(overrides)
    return payload


def test_lesson_requests_require_customer_auth(client):
    res = client.post("/api/customer/lesson-requests", json=_request_payload())
    assert res.status_code == 401


def test_no_lesson_request_yet_is_404(client, customer_auth_headers):
    res = client.get("/api/customer/lesson-requests/me", headers=customer_auth_headers)
    assert res.status_code == 404


def test_reject_unknown_specialty(client, customer_auth_headers):
    res = client.post("/api/customer/lesson-requests", json=_request_payload(specialty="pilates"), headers=customer_auth_headers)
    assert res.status_code == 400


def test_reject_unknown_city(client, customer_auth_headers):
    res = client.post("/api/customer/lesson-requests", json=_request_payload(city="Nowhere, XX"), headers=customer_auth_headers)
    assert res.status_code == 400


def test_reject_invalid_time_range(client, customer_auth_headers):
    res = client.post(
        "/api/customer/lesson-requests",
        json=_request_payload(requested_start_time="11:00", requested_end_time="09:00"),
        headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_reject_bad_card(client, customer_auth_headers):
    res = client.post(
        "/api/customer/lesson-requests",
        json=_request_payload(card_number="not-a-card"),
        headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_no_availability_anywhere_is_unmatched_not_a_crash(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="noavail@example.com", specialty="yoga")
    # Instructor exists but has no city and no availability blocks at all.
    res = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "unmatched"
    assert body["instructor"] is None


def test_nearer_instructor_with_overlap_wins_over_farther(client, customer_auth_headers):
    near_token = signup_instructor_with_specialty(client, email="near@example.com", specialty="yoga", name="Near Instructor")
    near_headers = {"Authorization": f"Bearer {near_token}"}
    set_instructor_city(client, near_headers, "Chicago, IL")  # ~1145 km from NYC
    add_availability(client, near_headers, TUESDAY, "08:00", "12:00")

    far_token = signup_instructor_with_specialty(client, email="far@example.com", specialty="yoga", name="Far Instructor")
    far_headers = {"Authorization": f"Bearer {far_token}"}
    set_instructor_city(client, far_headers, "Los Angeles, CA")  # ~3936 km from NYC
    add_availability(client, far_headers, TUESDAY, "08:00", "12:00")

    res = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "matched"
    assert body["instructor"]["name"] == "Near Instructor"
    assert body["matched_start_time"] == "09:00"
    assert body["matched_end_time"] == "09:30"
    assert body["distance_km"] < 1500


def test_farther_but_available_instructor_beats_nearer_but_unavailable(client, customer_auth_headers):
    near_token = signup_instructor_with_specialty(client, email="near2@example.com", specialty="yoga", name="Near Instructor")
    near_headers = {"Authorization": f"Bearer {near_token}"}
    set_instructor_city(client, near_headers, "Chicago, IL")
    add_availability(client, near_headers, TUESDAY, "14:00", "16:00")  # doesn't overlap 09:00-11:00

    far_token = signup_instructor_with_specialty(client, email="far2@example.com", specialty="yoga", name="Far Instructor")
    far_headers = {"Authorization": f"Bearer {far_token}"}
    set_instructor_city(client, far_headers, "Los Angeles, CA")
    add_availability(client, far_headers, TUESDAY, "08:00", "12:00")  # overlaps

    res = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "matched"
    assert body["instructor"]["name"] == "Far Instructor"


def test_instructor_without_city_is_excluded_from_matching(client, customer_auth_headers):
    token = signup_instructor_with_specialty(client, email="nocity@example.com", specialty="yoga")
    headers = {"Authorization": f"Bearer {token}"}
    add_availability(client, headers, TUESDAY, "08:00", "12:00")
    # No set_instructor_city call — latitude/longitude stay null.

    res = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "unmatched"


def test_lesson_request_creates_a_real_client_for_the_matched_instructor(client, customer_auth_headers):
    token = signup_instructor_with_specialty(client, email="sync@example.com", specialty="yoga")
    headers = {"Authorization": f"Bearer {token}"}
    set_instructor_city(client, headers, "Chicago, IL")
    add_availability(client, headers, TUESDAY, "08:00", "12:00")

    client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)

    their_clients = client.get("/api/clients?status=current", headers=headers).json()
    matched = [c for c in their_clients if c["name"] == "Test Customer"]
    assert len(matched) == 1
    assert matched[0]["next_session"] == "Tuesday, 09:00"


def test_get_my_latest_lesson_request(client, customer_auth_headers):
    token = signup_instructor_with_specialty(client, email="latest@example.com", specialty="yoga")
    headers = {"Authorization": f"Bearer {token}"}
    set_instructor_city(client, headers, "Chicago, IL")
    add_availability(client, headers, TUESDAY, "08:00", "12:00")

    client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)

    res = client.get("/api/customer/lesson-requests/me", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "matched"
