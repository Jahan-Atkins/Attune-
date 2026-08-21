from .conftest import add_availability, set_instructor_city, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


def _request_payload(**overrides):
    payload = {
        "specialty": "yoga",
        "city": "New York, NY",
        "duration_minutes": 30,
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


def test_reject_invalid_duration(client, customer_auth_headers):
    res = client.post("/api/customer/lesson-requests", json=_request_payload(duration_minutes=50), headers=customer_auth_headers)
    assert res.status_code == 400


def test_list_durations_is_public_pricing(client, customer_auth_headers):
    res = client.get("/api/customer/lesson-requests/durations", headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["30"] == 65
    assert body["90"] == 160
    # Discounted tiers: per-minute rate should drop as duration increases.
    assert body["90"] / 90 < body["30"] / 30


def test_price_scales_with_duration(client, customer_auth_headers):
    res = client.post("/api/customer/lesson-requests", json=_request_payload(duration_minutes=60), headers=customer_auth_headers)
    assert res.json()["amount_paid"] == 115


def test_lesson_request_stores_notes(client, customer_auth_headers):
    res = client.post(
        "/api/customer/lesson-requests",
        json=_request_payload(notes="First time doing a sound bath, a little nervous!"),
        headers=customer_auth_headers,
    )
    assert res.json()["notes"] == "First time doing a sound bath, a little nervous!"


def test_lesson_request_starts_pending_when_a_feasible_instructor_exists(client, customer_auth_headers):
    token = signup_instructor_with_specialty(client, email="feasible@example.com", specialty="yoga")
    headers = {"Authorization": f"Bearer {token}"}
    set_instructor_city(client, headers, "Chicago, IL")
    add_availability(client, headers, TUESDAY, "08:00", "12:00")

    res = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "pending"
    assert body["instructor"] is None
    assert body["paid"] is False
    assert body["matched_start_time"] is None


def test_no_feasible_instructor_anywhere_is_unmatched_not_a_crash(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="noavail@example.com", specialty="yoga")
    # Instructor exists and offers yoga, but has zero availability blocks —
    # no requested window could ever overlap, so this is a true dead end.
    res = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "unmatched"
    assert body["instructor"] is None


def test_get_my_latest_lesson_request(client, customer_auth_headers):
    client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers)

    res = client.get("/api/customer/lesson-requests/me", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] in ("pending", "unmatched")


def test_list_lesson_requests_requires_customer_auth(client):
    res = client.get("/api/customer/lesson-requests")
    assert res.status_code == 401


def test_list_lesson_requests_returns_full_history_newest_first(client, customer_auth_headers):
    first = client.post("/api/customer/lesson-requests", json=_request_payload(duration_minutes=30), headers=customer_auth_headers).json()
    second = client.post("/api/customer/lesson-requests", json=_request_payload(duration_minutes=60), headers=customer_auth_headers).json()

    history = client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json()
    assert [lr["id"] for lr in history] == [second["id"], first["id"]]


def _matched_instructor_id(client, customer_auth_headers, instructor_headers):
    """Books once, confirms it, and returns the matched instructor's id —
    every rebook test needs a real prior match to target."""
    token = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/lesson-requests/{token['id']}/confirm", headers=instructor_headers)
    return client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json()[0]["instructor"]["id"]


def test_rebook_targets_only_the_preferred_instructor(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="lr_rebook_target@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")
    instructor_id = _matched_instructor_id(client, customer_auth_headers, instructor_headers)

    other_token = signup_instructor_with_specialty(client, email="lr_rebook_bystander@example.com", specialty="yoga")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    add_availability(client, other_headers, TUESDAY, "08:00", "12:00")

    rebook = client.post(
        "/api/customer/lesson-requests",
        json=_request_payload(preferred_instructor_id=instructor_id, requested_start_time="10:00", requested_end_time="11:00"),
        headers=customer_auth_headers,
    )
    assert rebook.status_code == 201
    assert rebook.json()["status"] == "pending"

    assert client.get("/api/client-requests", headers=other_headers).json() == []
    assert len(client.get("/api/client-requests", headers=instructor_headers).json()) == 1


def test_rebook_confirms_normally(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="lr_rebook_confirm@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")
    instructor_id = _matched_instructor_id(client, customer_auth_headers, instructor_headers)

    rebook = client.post(
        "/api/customer/lesson-requests", json=_request_payload(preferred_instructor_id=instructor_id), headers=customer_auth_headers,
    ).json()
    confirmed = client.put(f"/api/client-requests/lesson-requests/{rebook['id']}/confirm", headers=instructor_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["customer_email"] == "customer@example.com"


def test_rebook_rejected_when_no_overlap_with_preferred_instructor(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="lr_rebook_no_overlap@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")
    instructor_id = _matched_instructor_id(client, customer_auth_headers, instructor_headers)

    res = client.post(
        "/api/customer/lesson-requests",
        json=_request_payload(preferred_instructor_id=instructor_id, requested_day=3, requested_start_time="09:00", requested_end_time="11:00"),
        headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_rebook_rejected_when_instructor_inactive(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="lr_rebook_inactive@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")
    instructor_id = _matched_instructor_id(client, customer_auth_headers, instructor_headers)

    client.put("/api/profile", json={"active": False}, headers=instructor_headers)

    res = client.post(
        "/api/customer/lesson-requests", json=_request_payload(preferred_instructor_id=instructor_id), headers=customer_auth_headers,
    )
    assert res.status_code == 400
