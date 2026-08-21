"""
/api/customer/blocks, /api/profile/blocks, and their real effect: hiding
future matches from both the broadcast queue (client_requests.py) and
"Book Again" (bookings.py/lesson_requests.py's preferred_instructor_id).
Reuses test_reports.py's _make_matched_pair to get a real matched pair
to block, since blocking makes the most sense once two people already
have each other's contact info.
"""
from .test_reports import _make_matched_pair

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
CITY = "New York, NY"


# ---- auth ----

def test_block_instructor_requires_customer_auth(client):
    res = client.post("/api/customer/blocks", json={"instructor_id": 1})
    assert res.status_code == 401


def test_block_client_requires_instructor_auth(client):
    res = client.post("/api/profile/blocks", json={"client_id": 1})
    assert res.status_code == 401


# ---- customer blocks instructor ----

def test_customer_can_block_and_unblock_instructor(client, customer_auth_headers):
    _, instructor_id, _ = _make_matched_pair(client, customer_auth_headers)

    blocked = client.post("/api/customer/blocks", json={"instructor_id": instructor_id}, headers=customer_auth_headers)
    assert blocked.status_code == 201
    assert blocked.json()["instructor_id"] == instructor_id

    listed = client.get("/api/customer/blocks", headers=customer_auth_headers).json()
    assert any(b["instructor_id"] == instructor_id for b in listed)

    unblocked = client.delete(f"/api/customer/blocks/{instructor_id}", headers=customer_auth_headers)
    assert unblocked.status_code == 204
    listed_after = client.get("/api/customer/blocks", headers=customer_auth_headers).json()
    assert listed_after == []


def test_blocking_instructor_is_idempotent(client, customer_auth_headers):
    _, instructor_id, _ = _make_matched_pair(client, customer_auth_headers)
    first = client.post("/api/customer/blocks", json={"instructor_id": instructor_id}, headers=customer_auth_headers)
    second = client.post("/api/customer/blocks", json={"instructor_id": instructor_id}, headers=customer_auth_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    listed = client.get("/api/customer/blocks", headers=customer_auth_headers).json()
    assert len(listed) == 1


# ---- blocking hides future matches ----

def test_blocked_instructor_no_longer_sees_customers_new_requests(client, customer_auth_headers):
    instructor_headers, instructor_id, _ = _make_matched_pair(client, customer_auth_headers, email="blocker_test@example.com")
    client.post("/api/customer/blocks", json={"instructor_id": instructor_id}, headers=customer_auth_headers)

    # A brand new request from the same (now-blocking) customer.
    client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": CITY, **CARD,
    }, headers=customer_auth_headers)

    visible = client.get("/api/client-requests", headers=instructor_headers).json()
    assert visible == []


def test_unblocking_restores_visibility(client, customer_auth_headers):
    instructor_headers, instructor_id, _ = _make_matched_pair(client, customer_auth_headers, email="unblock_test@example.com")
    client.post("/api/customer/blocks", json={"instructor_id": instructor_id}, headers=customer_auth_headers)
    client.delete(f"/api/customer/blocks/{instructor_id}", headers=customer_auth_headers)

    client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": CITY, **CARD,
    }, headers=customer_auth_headers)

    visible = client.get("/api/client-requests", headers=instructor_headers).json()
    assert len(visible) == 1


def test_blocking_prevents_book_again_with_that_instructor(client, customer_auth_headers):
    instructor_headers, instructor_id, _ = _make_matched_pair(client, customer_auth_headers, email="rebook_blocked@example.com")
    client.post("/api/customer/blocks", json={"instructor_id": instructor_id}, headers=customer_auth_headers)

    res = client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": CITY, "preferred_instructor_id": instructor_id, **CARD,
    }, headers=customer_auth_headers)
    assert res.status_code == 400


# ---- instructor blocks client ----

def test_instructor_can_block_and_unblock_client(client, customer_auth_headers):
    instructor_headers, _, client_id = _make_matched_pair(client, customer_auth_headers, email="client_blocker@example.com")

    blocked = client.post("/api/profile/blocks", json={"client_id": client_id}, headers=instructor_headers)
    assert blocked.status_code == 201
    assert blocked.json()["client_id"] == client_id

    listed = client.get("/api/profile/blocks", headers=instructor_headers).json()
    assert any(b["client_id"] == client_id for b in listed)

    unblocked = client.delete(f"/api/profile/blocks/{client_id}", headers=instructor_headers)
    assert unblocked.status_code == 204
    assert client.get("/api/profile/blocks", headers=instructor_headers).json() == []


def test_cannot_block_a_hand_added_client(client, auth_headers):
    added = client.post("/api/clients", json={
        "name": "Hand Added", "initials": "HA", "avatar_variant": "c1",
    }, headers=auth_headers).json()

    res = client.post("/api/profile/blocks", json={"client_id": added["id"]}, headers=auth_headers)
    assert res.status_code == 400


def test_cannot_block_another_instructors_client(client, customer_auth_headers, second_auth_headers):
    _, _, client_id = _make_matched_pair(client, customer_auth_headers, email="not_yours@example.com")

    res = client.post("/api/profile/blocks", json={"client_id": client_id}, headers=second_auth_headers)
    assert res.status_code == 404


def test_instructor_block_also_hides_that_customers_requests_from_them(client, customer_auth_headers):
    """A block is symmetric in effect regardless of which side initiated
    it — see models.Block's docstring."""
    instructor_headers, _, client_id = _make_matched_pair(client, customer_auth_headers, email="symmetric_test@example.com")
    client.post("/api/profile/blocks", json={"client_id": client_id}, headers=instructor_headers)

    client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": CITY, **CARD,
    }, headers=customer_auth_headers)

    visible = client.get("/api/client-requests", headers=instructor_headers).json()
    assert visible == []
