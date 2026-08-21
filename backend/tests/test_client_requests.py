from .conftest import (
    add_availability,
    set_instructor_city,
    set_instructor_max_distance,
    signup_instructor_with_specialty,
)

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1
NYC = "New York, NY"
CHICAGO = "Chicago, IL"  # ~1145 km from NYC


def _booking_payload(**overrides):
    payload = {"specialty": "yoga", "package": "single", "city": NYC, **CARD}
    payload.update(overrides)
    return payload


def _lesson_payload(**overrides):
    payload = {
        "specialty": "yoga", "city": NYC, "duration_minutes": 30,
        "requested_day": TUESDAY, "requested_start_time": "09:00", "requested_end_time": "11:00",
        **CARD,
    }
    payload.update(overrides)
    return payload


def _make_instructor(client, email, specialty="yoga", name="Test Instructor", city=None, max_distance=None, availability=None):
    token = signup_instructor_with_specialty(client, email=email, specialty=specialty, name=name)
    headers = {"Authorization": f"Bearer {token}"}
    if city:
        set_instructor_city(client, headers, city)
    if max_distance is not None:
        set_instructor_max_distance(client, headers, max_distance)
    for day, start, end in (availability or []):
        add_availability(client, headers, day, start, end)
    return headers


# ---- auth ----

def test_client_requests_require_instructor_auth(client):
    res = client.get("/api/client-requests")
    assert res.status_code == 401


def test_confirm_requires_instructor_auth(client, customer_auth_headers):
    res = client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)
    booking_id = res.json()["id"]
    res = client.put(f"/api/client-requests/bookings/{booking_id}/confirm")
    assert res.status_code == 401


# ---- booking (package) visibility ----

def test_pending_booking_visible_to_matching_instructor(client, customer_auth_headers):
    headers = _make_instructor(client, "pkg_match@example.com", specialty="yoga")
    client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)

    res = client.get("/api/client-requests", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["request_type"] == "package"
    assert body[0]["specialty"] == "yoga"
    assert body[0]["package"] == "single"
    assert body[0]["amount_due"] == 65
    assert body[0]["customer_name"] == "Test Customer"
    assert body[0]["customer_city"] == NYC


def test_pending_booking_not_visible_to_wrong_specialty(client, customer_auth_headers):
    headers = _make_instructor(client, "pkg_wrong_specialty@example.com", specialty="sound_bath")
    client.post("/api/customer/bookings", json=_booking_payload(specialty="yoga"), headers=customer_auth_headers)

    body = client.get("/api/client-requests", headers=headers).json()
    assert body == []


def test_pending_booking_not_visible_to_inactive_instructor(client, customer_auth_headers):
    headers = _make_instructor(client, "pkg_inactive@example.com", specialty="yoga")
    client.put("/api/profile", json={"active": False}, headers=headers)
    client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)

    body = client.get("/api/client-requests", headers=headers).json()
    assert body == []


def test_pending_booking_hidden_beyond_max_travel_distance(client, customer_auth_headers):
    headers = _make_instructor(client, "pkg_too_far@example.com", specialty="yoga", city=CHICAGO, max_distance=500)
    client.post("/api/customer/bookings", json=_booking_payload(city=NYC), headers=customer_auth_headers)

    body = client.get("/api/client-requests", headers=headers).json()
    assert body == []


def test_pending_booking_visible_when_within_max_travel_distance(client, customer_auth_headers):
    headers = _make_instructor(client, "pkg_close_enough@example.com", specialty="yoga", city=CHICAGO, max_distance=2000)
    client.post("/api/customer/bookings", json=_booking_payload(city=NYC), headers=customer_auth_headers)

    body = client.get("/api/client-requests", headers=headers).json()
    assert len(body) == 1
    assert body[0]["distance_km"] < 1500


# ---- booking (package) confirm ----

def test_confirm_booking_creates_client_marks_matched_and_paid(client, customer_auth_headers):
    headers = _make_instructor(client, "pkg_confirm@example.com", specialty="yoga")
    res = client.post("/api/customer/bookings", json=_booking_payload(package="pack4"), headers=customer_auth_headers)
    booking_id = res.json()["id"]

    confirm_res = client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200

    booking = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()
    assert booking["status"] == "matched"
    assert booking["paid"] is True
    assert booking["instructor"]["name"] == "Test Instructor"

    their_clients = client.get("/api/clients?status=current", headers=headers).json()
    matched = [c for c in their_clients if c["name"] == "Test Customer"]
    assert len(matched) == 1
    assert matched[0]["sessions_total"] == 4


def test_confirm_booking_removes_it_from_other_instructors_queues(client, customer_auth_headers):
    headers_a = _make_instructor(client, "pkg_race_a@example.com", specialty="yoga", name="Instructor A")
    headers_b = _make_instructor(client, "pkg_race_b@example.com", specialty="yoga", name="Instructor B")
    res = client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)
    booking_id = res.json()["id"]

    assert len(client.get("/api/client-requests", headers=headers_b).json()) == 1
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers_a)

    assert client.get("/api/client-requests", headers=headers_b).json() == []


def test_confirm_booking_already_claimed_returns_404(client, customer_auth_headers):
    headers_a = _make_instructor(client, "pkg_claim_a@example.com", specialty="yoga", name="Instructor A")
    headers_b = _make_instructor(client, "pkg_claim_b@example.com", specialty="yoga", name="Instructor B")
    res = client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)
    booking_id = res.json()["id"]

    first = client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers_a)
    assert first.status_code == 200
    second = client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers_b)
    assert second.status_code == 404


def test_confirm_booking_rejects_wrong_specialty_instructor(client, customer_auth_headers):
    # A yoga instructor has to exist so the booking actually goes "pending"
    # rather than an immediate dead-end "unmatched" with nothing to confirm.
    _make_instructor(client, "pkg_yoga_exists@example.com", specialty="yoga")
    wrong_headers = _make_instructor(client, "pkg_wrong_confirm@example.com", specialty="sound_bath")
    res = client.post("/api/customer/bookings", json=_booking_payload(specialty="yoga"), headers=customer_auth_headers)
    booking_id = res.json()["id"]

    confirm_res = client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=wrong_headers)
    assert confirm_res.status_code == 400


# ---- lesson request (schedule) visibility ----

def test_pending_lesson_request_visible_when_overlap_exists(client, customer_auth_headers):
    headers = _make_instructor(client, "sched_match@example.com", specialty="yoga", availability=[(TUESDAY, "08:00", "12:00")])
    client.post("/api/customer/lesson-requests", json=_lesson_payload(), headers=customer_auth_headers)

    body = client.get("/api/client-requests", headers=headers).json()
    assert len(body) == 1
    assert body[0]["request_type"] == "schedule"
    assert body[0]["requested_day"] == TUESDAY
    assert body[0]["duration_minutes"] == 30


def test_pending_lesson_request_hidden_when_no_overlap(client, customer_auth_headers):
    headers = _make_instructor(client, "sched_no_overlap@example.com", specialty="yoga", availability=[(TUESDAY, "14:00", "16:00")])
    client.post("/api/customer/lesson-requests", json=_lesson_payload(), headers=customer_auth_headers)  # requests 09:00-11:00

    body = client.get("/api/client-requests", headers=headers).json()
    assert body == []


def test_pending_lesson_request_hidden_beyond_max_travel_distance(client, customer_auth_headers):
    headers = _make_instructor(
        client, "sched_too_far@example.com", specialty="yoga", city=CHICAGO, max_distance=500,
        availability=[(TUESDAY, "08:00", "12:00")],
    )
    client.post("/api/customer/lesson-requests", json=_lesson_payload(city=NYC), headers=customer_auth_headers)

    body = client.get("/api/client-requests", headers=headers).json()
    assert body == []


# ---- lesson request (schedule) confirm ----

def test_confirm_lesson_request_sets_matched_window_and_distance(client, customer_auth_headers):
    headers = _make_instructor(
        client, "sched_confirm@example.com", specialty="yoga", city=CHICAGO,
        availability=[(TUESDAY, "08:00", "12:00")],
    )
    res = client.post("/api/customer/lesson-requests", json=_lesson_payload(city=NYC), headers=customer_auth_headers)
    lesson_request_id = res.json()["id"]

    confirm_res = client.put(f"/api/client-requests/lesson-requests/{lesson_request_id}/confirm", headers=headers)
    assert confirm_res.status_code == 200

    lesson_request = client.get("/api/customer/lesson-requests/me", headers=customer_auth_headers).json()
    assert lesson_request["status"] == "matched"
    assert lesson_request["paid"] is True
    assert lesson_request["matched_start_time"] == "09:00"
    assert lesson_request["matched_end_time"] == "09:30"
    assert lesson_request["distance_km"] < 1500


def test_confirm_lesson_request_creates_client_with_next_session(client, customer_auth_headers):
    headers = _make_instructor(client, "sched_client@example.com", specialty="yoga", availability=[(TUESDAY, "08:00", "12:00")])
    res = client.post("/api/customer/lesson-requests", json=_lesson_payload(), headers=customer_auth_headers)
    lesson_request_id = res.json()["id"]

    client.put(f"/api/client-requests/lesson-requests/{lesson_request_id}/confirm", headers=headers)

    their_clients = client.get("/api/clients?status=current", headers=headers).json()
    matched = [c for c in their_clients if c["name"] == "Test Customer"]
    assert len(matched) == 1
    assert matched[0]["next_session"] == "Tuesday, 09:00"


def test_confirm_lesson_request_already_claimed_returns_404(client, customer_auth_headers):
    headers_a = _make_instructor(client, "sched_claim_a@example.com", specialty="yoga", name="A", availability=[(TUESDAY, "08:00", "12:00")])
    headers_b = _make_instructor(client, "sched_claim_b@example.com", specialty="yoga", name="B", availability=[(TUESDAY, "08:00", "12:00")])
    res = client.post("/api/customer/lesson-requests", json=_lesson_payload(), headers=customer_auth_headers)
    lesson_request_id = res.json()["id"]

    first = client.put(f"/api/client-requests/lesson-requests/{lesson_request_id}/confirm", headers=headers_a)
    assert first.status_code == 200
    second = client.put(f"/api/client-requests/lesson-requests/{lesson_request_id}/confirm", headers=headers_b)
    assert second.status_code == 404
