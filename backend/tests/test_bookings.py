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


def test_list_bookings_requires_customer_auth(client):
    res = client.get("/api/customer/bookings")
    assert res.status_code == 401


def test_list_bookings_returns_full_history_newest_first(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="history_test@example.com", specialty="yoga")
    first = client.post("/api/customer/bookings", json=_payload(package="single"), headers=customer_auth_headers).json()
    second = client.post("/api/customer/bookings", json=_payload(package="pack4"), headers=customer_auth_headers).json()

    history = client.get("/api/customer/bookings", headers=customer_auth_headers).json()
    assert [b["id"] for b in history] == [second["id"], first["id"]]


def test_list_bookings_isolated_between_customers(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="history_iso@example.com", specialty="yoga")
    client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers)

    other_token = client.post("/api/customer/auth/signup", json={
        "name": "Other Customer", "email": "other_history@example.com", "phone": "555-010-4444", "password": "custpass123",
    }).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert len(client.get("/api/customer/bookings", headers=customer_auth_headers).json()) == 1
    assert len(client.get("/api/customer/bookings", headers=other_headers).json()) == 0


def test_rebook_targets_only_the_preferred_instructor(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rebook_target@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    first = client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/bookings/{first['id']}/confirm", headers=instructor_headers)
    # ClientRequestConfirmedOut describes the *request*, not the instructor
    # — fetch the matched instructor's id from the booking's own record.
    instructor_id = client.get("/api/customer/bookings", headers=customer_auth_headers).json()[0]["instructor"]["id"]

    # A second, otherwise-eligible instructor exists but should never see
    # a request targeted at someone else.
    other_token = signup_instructor_with_specialty(client, email="rebook_bystander@example.com", specialty="yoga")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    rebook = client.post(
        "/api/customer/bookings", json=_payload(preferred_instructor_id=instructor_id), headers=customer_auth_headers,
    )
    assert rebook.status_code == 201
    assert rebook.json()["status"] == "pending"

    assert client.get("/api/client-requests", headers=other_headers).json() == []
    mine = client.get("/api/client-requests", headers=instructor_headers).json()
    assert len(mine) == 1
    assert mine[0]["customer_name"] == "Test Customer"


def test_rebook_confirms_normally(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rebook_confirm@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    first = client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/bookings/{first['id']}/confirm", headers=instructor_headers)
    instructor_id = client.get("/api/customer/bookings", headers=customer_auth_headers).json()[0]["instructor"]["id"]

    rebook = client.post(
        "/api/customer/bookings", json=_payload(preferred_instructor_id=instructor_id), headers=customer_auth_headers,
    ).json()
    confirmed = client.put(f"/api/client-requests/bookings/{rebook['id']}/confirm", headers=instructor_headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["customer_email"] == "customer@example.com"


def test_rebook_rejected_when_instructor_no_longer_offers_specialty(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rebook_dropped@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    first = client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/bookings/{first['id']}/confirm", headers=instructor_headers)
    instructor_id = client.get("/api/customer/bookings", headers=customer_auth_headers).json()[0]["instructor"]["id"]

    client.put("/api/profile", json={"specialty": "sound_bath"}, headers=instructor_headers)

    res = client.post(
        "/api/customer/bookings", json=_payload(preferred_instructor_id=instructor_id), headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_rebook_rejected_when_instructor_inactive(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rebook_inactive@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    first = client.post("/api/customer/bookings", json=_payload(), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/bookings/{first['id']}/confirm", headers=instructor_headers)
    instructor_id = client.get("/api/customer/bookings", headers=customer_auth_headers).json()[0]["instructor"]["id"]

    client.put("/api/profile", json={"active": False}, headers=instructor_headers)

    res = client.post(
        "/api/customer/bookings", json=_payload(preferred_instructor_id=instructor_id), headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_rebook_rejected_for_unknown_instructor_id(client, customer_auth_headers):
    res = client.post(
        "/api/customer/bookings", json=_payload(preferred_instructor_id=999999), headers=customer_auth_headers,
    )
    assert res.status_code == 400
