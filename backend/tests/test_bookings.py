from .conftest import signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}


def test_list_packages_is_public_pricing(client, customer_auth_headers):
    res = client.get("/api/customer/bookings/packages", headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["single"]["sessions"] == 1
    assert body["pack4"]["sessions"] == 4
    assert body["pack8"]["sessions"] == 8


def test_bookings_require_customer_auth(client):
    res = client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "single", **CARD})
    assert res.status_code == 401


def test_no_booking_yet_is_404(client, customer_auth_headers):
    res = client.get("/api/customer/bookings/me", headers=customer_auth_headers)
    assert res.status_code == 404


def test_reject_bad_card_number(client, customer_auth_headers):
    bad_card = dict(CARD, card_number="not-a-card")
    res = client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "single", **bad_card}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_reject_unknown_specialty(client, customer_auth_headers):
    res = client.post("/api/customer/bookings", json={"specialty": "pilates", "package": "single", **CARD}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_successful_booking_matches_instructor(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="instructor_yoga@example.com", specialty="yoga")

    res = client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "pack4", **CARD}, headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "matched"
    assert body["instructor"]["name"] == "Test Instructor"
    assert body["sessions_total"] == 4
    assert body["amount_paid"] == 220


def test_booking_creates_a_real_client_for_the_matched_instructor(client, customer_auth_headers):
    """The integration that ties the two apps together."""
    instructor_token = signup_instructor_with_specialty(client, email="instructor_yoga2@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}

    client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "single", **CARD}, headers=customer_auth_headers)

    their_clients = client.get("/api/clients?status=current", headers=instructor_headers).json()
    assert any(c["name"] == "Test Customer" for c in their_clients)


def test_never_matches_wrong_specialty(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="sound_only@example.com", specialty="sound_bath")

    # No yoga instructor exists in this test's (fresh, isolated) database.
    res = client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "single", **CARD}, headers=customer_auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "unmatched"
    assert res.json()["instructor"] is None


def test_inactive_instructor_is_never_matched(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="inactive@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    client.put("/api/profile", json={"active": False}, headers=instructor_headers)

    res = client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "single", **CARD}, headers=customer_auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "unmatched"


def test_load_balances_across_multiple_matching_instructors(client):
    signup_instructor_with_specialty(client, email="lb1@example.com", specialty="yoga", name="Instructor One")
    signup_instructor_with_specialty(client, email="lb2@example.com", specialty="yoga", name="Instructor Two")

    matched_names = set()
    for i in range(4):
        signup_res = client.post("/api/customer/auth/signup", json={
            "name": f"Customer {i}", "email": f"lbcust{i}@example.com", "password": "custpass123",
        })
        headers = {"Authorization": f"Bearer {signup_res.json()['access_token']}"}
        res = client.post("/api/customer/bookings", json={"specialty": "yoga", "package": "single", **CARD}, headers=headers)
        matched_names.add(res.json()["instructor"]["name"])

    assert matched_names == {"Instructor One", "Instructor Two"}
