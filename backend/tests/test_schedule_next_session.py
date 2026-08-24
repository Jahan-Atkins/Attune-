"""
POST /api/customer/lesson-requests/{id}/schedule-next — scheduling
sessions 2..N of an already-matched multi-session package. No
re-broadcast (the instructor is already fixed) and no repayment (the
whole package was already charged when the root session was confirmed).
"""
from .conftest import add_availability, signup_customer, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1
WEDNESDAY = 2


def _window(day=TUESDAY, start="09:00", end="12:00"):
    return {"day_of_week": day, "start_time": start, "end_time": end}


def _package_payload(package="pack4", windows=None, **overrides):
    payload = {
        "specialty": "yoga", "package": package, "address": "123 Main St", "city": "New York", "state": "NY", "duration_minutes": 30,
        "availability_windows": windows if windows is not None else [_window()],
        **CARD,
    }
    payload.update(overrides)
    return payload


def _make_matched_package(client, customer_auth_headers, package="pack4", email="package_instructor@example.com", name="Package Instructor"):
    """Signs up an instructor, submits and confirms a multi-session
    package — returns (instructor_headers, root_id, instructor_id)."""
    token = signup_instructor_with_specialty(client, email=email, specialty="yoga", name=name)
    instructor_headers = {"Authorization": f"Bearer {token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")

    root = client.post("/api/customer/lesson-requests", json=_package_payload(package=package), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/lesson-requests/{root['id']}/confirm", headers=instructor_headers)
    instructor_id = client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json()[0]["instructor"]["id"]
    return instructor_headers, root["id"], instructor_id


def test_schedule_next_requires_customer_auth(client):
    res = client.post("/api/customer/lesson-requests/1/schedule-next", json={})
    assert res.status_code == 401


def test_schedule_next_404_for_unknown_request(client, customer_auth_headers):
    res = client.post("/api/customer/lesson-requests/999999/schedule-next", json={}, headers=customer_auth_headers)
    assert res.status_code == 404


def test_schedule_next_requires_a_matched_root(client, customer_auth_headers):
    pending = client.post("/api/customer/lesson-requests", json=_package_payload(package="pack4"), headers=customer_auth_headers).json()
    res = client.post(f"/api/customer/lesson-requests/{pending['id']}/schedule-next", json={}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_schedule_next_uses_original_windows_by_default(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers)

    res = client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "matched"
    assert body["session_number"] == 2
    assert body["package_request_id"] == root_id
    assert body["requested_day"] == TUESDAY


def test_schedule_next_accepts_fresh_windows(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers)
    add_availability(client, instructor_headers, WEDNESDAY, "13:00", "15:00")

    res = client.post(
        f"/api/customer/lesson-requests/{root_id}/schedule-next",
        json={"availability_windows": [_window(day=WEDNESDAY, start="13:00", end="15:00")]},
        headers=customer_auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["requested_day"] == WEDNESDAY


def test_schedule_next_rejects_when_nothing_fits(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers)

    res = client.post(
        f"/api/customer/lesson-requests/{root_id}/schedule-next",
        json={"availability_windows": [_window(day=WEDNESDAY, start="13:00", end="15:00")]},
        headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_schedule_next_does_not_charge_again(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers)
    res = client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)
    assert res.json()["amount_paid"] == 0
    assert res.json()["paid"] is True


def test_schedule_next_updates_client_next_session(client, customer_auth_headers):
    instructor_headers, root_id, instructor_id = _make_matched_package(client, customer_auth_headers)
    client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)

    clients = client.get("/api/clients?status=current", headers=instructor_headers).json()
    matched = next(c for c in clients if c["customer_id"] is not None)
    assert "Tuesday" in matched["next_session"]


def test_schedule_next_rejects_once_fully_scheduled(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers, package="pack4")
    # Root = session 1. pack4 = 4 total, so 3 more schedule-next calls fill it.
    for _ in range(3):
        res = client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)
        assert res.status_code == 201

    over = client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)
    assert over.status_code == 400


def test_schedule_next_session_never_appears_in_pending_client_requests(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers)
    client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)

    # Created directly as "matched" — never enters any instructor's broadcast queue.
    assert client.get("/api/client-requests", headers=instructor_headers).json() == []


def test_sessions_scheduled_reflects_progress(client, customer_auth_headers):
    instructor_headers, root_id, _ = _make_matched_package(client, customer_auth_headers, package="pack4")
    root = client.get("/api/customer/lesson-requests/me", headers=customer_auth_headers).json()
    assert root["sessions_scheduled"] == 1

    client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)
    history = client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json()
    updated_root = next(lr for lr in history if lr["id"] == root_id)
    assert updated_root["sessions_scheduled"] == 2


def test_cannot_schedule_next_for_another_customers_package(client, customer_auth_headers):
    _, root_id, _ = _make_matched_package(client, customer_auth_headers)

    other_token = signup_customer(client, email="other_customer@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res = client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=other_headers)
    assert res.status_code == 404
