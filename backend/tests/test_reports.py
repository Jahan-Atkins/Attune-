"""
/api/customer/reports, /api/profile/reports, and the admin list/resolve
endpoints. Reuses test_reviews.py's "sign up, book, confirm" shape to
get to a real matched pair (contact info is only ever exchanged after a
real match — see client_requests.py's _notify_match), since that's
exactly the relationship a report is about.
"""
from .conftest import create_admin_and_login, create_booking_row, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
CITY = "New York, NY"


def _make_matched_pair(client, customer_auth_headers, email="matched_instructor@example.com", name="Matched Instructor"):
    """Returns (instructor_headers, instructor_id, client_id) for a real,
    confirmed match — client_id is the Client row on the instructor's own
    practice list, the same id the frontend already has in hand on the
    Client Details page. Uses a directly-seeded Booking (no public create
    route anymore, see routers/bookings.py's module docstring) purely as
    a convenient way to reach a real match — nothing here is testing
    Booking-specific behavior."""
    token = signup_instructor_with_specialty(client, email=email, specialty="yoga", name=name)
    instructor_headers = {"Authorization": f"Bearer {token}"}
    booking_id = create_booking_row(city=CITY)
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=instructor_headers)

    instructor_id = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()["instructor"]["id"]
    clients_list = client.get("/api/clients?status=current", headers=instructor_headers).json()
    client_id = next(c["id"] for c in clients_list if c["name"] == "Test Customer")
    return instructor_headers, instructor_id, client_id


# ---- auth ----

def test_report_instructor_requires_customer_auth(client):
    res = client.post("/api/customer/reports", json={"instructor_id": 1, "reason": "no-show"})
    assert res.status_code == 401


def test_report_client_requires_instructor_auth(client):
    res = client.post("/api/profile/reports", json={"client_id": 1, "reason": "no-show"})
    assert res.status_code == 401


def test_admin_reports_require_admin_auth(client):
    assert client.get("/api/admin/reports").status_code == 401
    assert client.put("/api/admin/reports/1/resolve").status_code == 401


# ---- customer reports instructor ----

def test_customer_can_report_matched_instructor(client, customer_auth_headers):
    _, instructor_id, _ = _make_matched_pair(client, customer_auth_headers)

    res = client.post(
        "/api/customer/reports",
        json={"instructor_id": instructor_id, "reason": "no-show", "message": "Never showed up."},
        headers=customer_auth_headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["reporter_type"] == "customer"
    assert body["reporter_name"] == "Test Customer"
    assert body["reported_type"] == "instructor"
    assert body["reported_name"] == "Matched Instructor"
    assert body["resolved"] is False


def test_report_unknown_instructor_404s(client, customer_auth_headers):
    res = client.post(
        "/api/customer/reports", json={"instructor_id": 999999, "reason": "no-show"}, headers=customer_auth_headers,
    )
    assert res.status_code == 404


# ---- instructor reports client ----

def test_instructor_can_report_client(client, customer_auth_headers):
    instructor_headers, _, client_id = _make_matched_pair(client, customer_auth_headers)

    res = client.post(
        "/api/profile/reports",
        json={"client_id": client_id, "reason": "harassment", "message": "Inappropriate messages."},
        headers=instructor_headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["reporter_type"] == "instructor"
    assert body["reported_type"] == "customer"
    assert body["reported_name"] == "Test Customer"


def test_cannot_report_another_instructors_client(client, customer_auth_headers, second_auth_headers):
    _, _, client_id = _make_matched_pair(client, customer_auth_headers)

    res = client.post(
        "/api/profile/reports", json={"client_id": client_id, "reason": "harassment"}, headers=second_auth_headers,
    )
    assert res.status_code == 404


def test_cannot_report_a_hand_added_client(client, auth_headers):
    added = client.post("/api/clients", json={
        "name": "Hand Added", "initials": "HA", "avatar_variant": "c1",
    }, headers=auth_headers).json()

    res = client.post(
        "/api/profile/reports", json={"client_id": added["id"], "reason": "harassment"}, headers=auth_headers,
    )
    assert res.status_code == 400


# ---- admin ----

def test_admin_can_list_and_resolve_reports(client, customer_auth_headers):
    _, instructor_id, _ = _make_matched_pair(client, customer_auth_headers)
    report = client.post(
        "/api/customer/reports", json={"instructor_id": instructor_id, "reason": "no-show"}, headers=customer_auth_headers,
    ).json()

    admin_token = create_admin_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    listed = client.get("/api/admin/reports", headers=admin_headers)
    assert listed.status_code == 200
    assert any(r["id"] == report["id"] for r in listed.json())

    resolved = client.put(f"/api/admin/reports/{report['id']}/resolve", headers=admin_headers)
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] is True

    # The report row stays around after resolving — a persistent history,
    # unlike ClientDeletionRequest — so it still shows up filtered by
    # resolved=true instead of disappearing.
    still_listed = client.get("/api/admin/reports?resolved=true", headers=admin_headers)
    assert any(r["id"] == report["id"] for r in still_listed.json())


def test_resolve_404_for_unknown_report(client):
    admin_token = create_admin_and_login(client)
    res = client.put("/api/admin/reports/999999/resolve", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 404
