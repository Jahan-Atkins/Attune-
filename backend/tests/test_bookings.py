from .conftest import signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
CITY = "New York, NY"


def _payload(**overrides):
    payload = {"specialty": "yoga", "package": "single", "city": CITY, **CARD}
    payload.update(overrides)
    return payload


def test_list_packages_is_public_pricing(client, customer_auth_headers):
    res = client.get("/api/customer/bookings/packages", headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["single"]["sessions"] == 1
    assert body["pack4"]["sessions"] == 4
    assert body["pack8"]["sessions"] == 8


def test_bookings_require_customer_auth(client):
    res = client.post("/api/customer/bookings", json=_payload())
    assert res.status_code == 401


def test_no_booking_yet_is_404(client, customer_auth_headers):
    res = client.get("/api/customer/bookings/me", headers=customer_auth_headers)
    assert res.status_code == 404


def test_reject_bad_card_number(client, customer_auth_headers):
    res = client.post("/api/customer/bookings", json=_payload(card_number="not-a-card"), headers=customer_auth_headers)
    assert res.status_code == 400


def test_reject_unknown_specialty(client, customer_auth_headers):
    res = client.post("/api/customer/bookings", json=_payload(specialty="pilates"), headers=customer_auth_headers)
    assert res.status_code == 400


def test_reject_unknown_city(client, customer_auth_headers):
    res = client.post("/api/customer/bookings", json=_payload(city="Nowhere, XX"), headers=customer_auth_headers)
    assert res.status_code == 400


def test_booking_starts_pending_not_matched(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="instructor_yoga@example.com", specialty="yoga")

    res = client.post("/api/customer/bookings", json=_payload(package="pack4"), headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "pending"
    assert body["instructor"] is None
    assert body["paid"] is False
    assert body["sessions_total"] == 4
    assert body["amount_paid"] == 220


def test_booking_stores_notes(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="notes_test@example.com", specialty="yoga")
    res = client.post(
        "/api/customer/bookings",
        json=_payload(notes="I have a bad knee, please go easy on lunges."),
        headers=customer_auth_headers,
    )
    assert res.json()["notes"] == "I have a bad knee, please go easy on lunges."


def test_never_matches_wrong_specialty(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="sound_only@example.com", specialty="sound_bath")

    # No yoga instructor exists in this test's (fresh, isolated) database.
    res = client.post("/api/customer/bookings", json=_payload(specialty="yoga"), headers=customer_auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "unmatched"
    assert res.json()["instructor"] is None


def test_inactive_instructor_means_dead_end_unmatched(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="inactive@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    client.put("/api/profile", json={"active": False}, headers=instructor_headers)

    res = client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "unmatched"


def test_no_client_created_and_nothing_charged_until_confirmed(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="notyetconfirmed@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}

    res = client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers)
    assert res.json()["paid"] is False

    their_clients = client.get("/api/clients?status=current", headers=instructor_headers).json()
    assert all(c["name"] != "Test Customer" for c in their_clients)
