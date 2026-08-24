"""
PUT /api/customer/bookings/{id}/cancel and
PUT /api/customer/lesson-requests/{id}/cancel — the customer's own
self-cancel, mirroring admin.py's force_cancel_booking/
force_cancel_lesson_request with a parallel "cancelled_by_customer"
status value instead of "cancelled_by_admin".
"""
from .conftest import add_availability, create_booking_row, signup_customer, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


def _window(day=TUESDAY, start="09:00", end="12:00"):
    return {"day_of_week": day, "start_time": start, "end_time": end}


def _request_payload(package="single", windows=None, **overrides):
    payload = {
        "specialty": "yoga", "package": package, "address": "123 Main St", "city": "New York", "state": "NY", "duration_minutes": 30,
        "availability_windows": windows if windows is not None else [_window()],
        **CARD,
    }
    payload.update(overrides)
    return payload


def _matched_lesson_request(client, customer_auth_headers, package="single", email="cancel_matched@example.com"):
    """Signs up an instructor, submits and confirms a request — returns
    (instructor_headers, lesson_request_id)."""
    token = signup_instructor_with_specialty(client, email=email, specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")
    lr = client.post("/api/customer/lesson-requests", json=_request_payload(package=package), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
    return instructor_headers, lr["id"]


# ---- Bookings ----

def test_cancel_booking_requires_customer_auth(client):
    res = client.put("/api/customer/bookings/1/cancel")
    assert res.status_code == 401


def test_cancel_pending_booking(client, customer_auth_headers):
    booking_id = create_booking_row(status="pending")
    res = client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_customer"


def test_cancel_matched_booking_notifies_instructor(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="cancel_booking_matched@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking_id = create_booking_row(city="New York, NY")
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=instructor_headers)

    capsys.readouterr()
    res = client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=customer_auth_headers)
    out = capsys.readouterr().out

    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_customer"
    assert "to=cancel_booking_matched@example.com" in out


def test_cancel_matched_booking_respects_instructor_notification_setting_off(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="cancel_booking_notify_off@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking_id = create_booking_row(city="New York, NY")
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=instructor_headers)
    client.put("/api/profile", json={"email_notifications": False}, headers=instructor_headers)

    capsys.readouterr()
    res = client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=customer_auth_headers)
    out = capsys.readouterr().out

    assert res.status_code == 200
    assert "to=cancel_booking_notify_off@example.com" not in out


def test_cancel_already_cancelled_booking_rejected(client, customer_auth_headers):
    booking_id = create_booking_row(status="pending")
    client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=customer_auth_headers)
    res = client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=customer_auth_headers)
    assert res.status_code == 400


def test_cancel_unmatched_booking_rejected(client, customer_auth_headers):
    booking_id = create_booking_row(status="unmatched")
    res = client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=customer_auth_headers)
    assert res.status_code == 400


def test_cancel_someone_elses_booking_is_404(client, customer_auth_headers):
    booking_id = create_booking_row(status="pending")
    other_token = signup_customer(client, email="other_cancel_booking@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res = client.put(f"/api/customer/bookings/{booking_id}/cancel", headers=other_headers)
    assert res.status_code == 404


# ---- Lesson requests ----

def test_cancel_lesson_request_requires_customer_auth(client):
    res = client.put("/api/customer/lesson-requests/1/cancel")
    assert res.status_code == 401


def test_cancel_pending_lesson_request(client, customer_auth_headers):
    # A feasible (but not yet confirming) instructor must exist, or the
    # request lands "unmatched" instead of "pending" — see
    # create_lesson_request's has_any_candidate check.
    token = signup_instructor_with_specialty(client, email="cancel_lr_pending@example.com", specialty="yoga")
    add_availability(client, {"Authorization": f"Bearer {token}"}, TUESDAY, "08:00", "12:00")

    lr = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers).json()
    assert lr["status"] == "pending"
    res = client.put(f"/api/customer/lesson-requests/{lr['id']}/cancel", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_customer"


def test_cancel_matched_lesson_request_notifies_instructor(client, customer_auth_headers, capsys):
    _, lr_id = _matched_lesson_request(client, customer_auth_headers, email="cancel_lr_matched@example.com")

    capsys.readouterr()
    res = client.put(f"/api/customer/lesson-requests/{lr_id}/cancel", headers=customer_auth_headers)
    out = capsys.readouterr().out

    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_customer"
    assert "to=cancel_lr_matched@example.com" in out


def test_cancel_matched_lesson_request_respects_instructor_notification_setting_off(client, customer_auth_headers, capsys):
    instructor_headers, lr_id = _matched_lesson_request(client, customer_auth_headers, email="cancel_lr_notify_off@example.com")
    client.put("/api/profile", json={"email_notifications": False}, headers=instructor_headers)

    capsys.readouterr()
    res = client.put(f"/api/customer/lesson-requests/{lr_id}/cancel", headers=customer_auth_headers)
    out = capsys.readouterr().out

    assert res.status_code == 200
    assert "to=cancel_lr_notify_off@example.com" not in out


def test_cancel_already_cancelled_lesson_request_rejected(client, customer_auth_headers):
    token = signup_instructor_with_specialty(client, email="cancel_lr_twice@example.com", specialty="yoga")
    add_availability(client, {"Authorization": f"Bearer {token}"}, TUESDAY, "08:00", "12:00")

    lr = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers).json()
    first = client.put(f"/api/customer/lesson-requests/{lr['id']}/cancel", headers=customer_auth_headers)
    assert first.status_code == 200
    res = client.put(f"/api/customer/lesson-requests/{lr['id']}/cancel", headers=customer_auth_headers)
    assert res.status_code == 400


def test_cancel_unmatched_lesson_request_rejected(client, customer_auth_headers):
    # No active instructor at all -> the request lands "unmatched" immediately.
    lr = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers).json()
    assert lr["status"] == "unmatched"
    res = client.put(f"/api/customer/lesson-requests/{lr['id']}/cancel", headers=customer_auth_headers)
    assert res.status_code == 400


def test_cancel_someone_elses_lesson_request_is_404(client, customer_auth_headers):
    lr = client.post("/api/customer/lesson-requests", json=_request_payload(), headers=customer_auth_headers).json()
    other_token = signup_customer(client, email="other_cancel_lr@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res = client.put(f"/api/customer/lesson-requests/{lr['id']}/cancel", headers=other_headers)
    assert res.status_code == 404


def test_cancel_recurring_occurrence_rejected(client, customer_auth_headers):
    instructor_headers, lr_id = _matched_lesson_request(client, customer_auth_headers, email="cancel_lr_recurring@example.com")
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()
    occurrences = [
        lr for lr in client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json()
        if lr["recurring_series_id"] == series["id"]
    ]
    assert occurrences  # ensure_upcoming_occurrences generated at least one

    res = client.put(f"/api/customer/lesson-requests/{occurrences[0]['id']}/cancel", headers=customer_auth_headers)
    assert res.status_code == 400


def test_cancel_package_root_with_scheduled_sessions_rejected(client, customer_auth_headers):
    instructor_headers, root_id = _matched_lesson_request(client, customer_auth_headers, package="pack4", email="cancel_lr_pkg_blocked@example.com")
    client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers)

    res = client.put(f"/api/customer/lesson-requests/{root_id}/cancel", headers=customer_auth_headers)
    assert res.status_code == 400


def test_cancel_package_root_with_no_extra_scheduled_sessions_allowed(client, customer_auth_headers):
    _, root_id = _matched_lesson_request(client, customer_auth_headers, package="pack4", email="cancel_lr_pkg_ok@example.com")

    res = client.put(f"/api/customer/lesson-requests/{root_id}/cancel", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_customer"


def test_cancel_individual_session_row_allowed(client, customer_auth_headers):
    instructor_headers, root_id = _matched_lesson_request(client, customer_auth_headers, package="pack4", email="cancel_lr_session@example.com")
    session = client.post(f"/api/customer/lesson-requests/{root_id}/schedule-next", json={}, headers=customer_auth_headers).json()
    assert session["session_number"] == 2

    res = client.put(f"/api/customer/lesson-requests/{session['id']}/cancel", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_customer"
