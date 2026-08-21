"""
Notification trigger points — see app/email.py's module docstring for
why these are testable with plain capsys instead of mocking a provider:
the only backend right now just prints, so asserting on stdout IS
asserting on the behavior.
"""
from .conftest import add_availability, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


def test_send_email_prints_to_console(capsys):
    from app.email import send_email
    send_email(to="someone@example.com", subject="Hello", body="World")
    out = capsys.readouterr().out
    assert "someone@example.com" in out
    assert "Hello" in out


def test_confirm_booking_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_booking@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking = client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers).json()

    capsys.readouterr()  # discard anything printed by setup above
    client.put(f"/api/client-requests/bookings/{booking['id']}/confirm", headers=instructor_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_booking@example.com" in out


def test_confirm_lesson_request_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_schedule@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "09:00", "11:00")
    lr = client.post("/api/customer/lesson-requests", json={
        "specialty": "yoga", "city": "New York, NY", "duration_minutes": 30,
        "requested_day": TUESDAY, "requested_start_time": "09:00", "requested_end_time": "11:00", **CARD,
    }, headers=customer_auth_headers).json()

    capsys.readouterr()
    client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_schedule@example.com" in out


def test_new_review_notifies_instructor(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_review@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking = client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/bookings/{booking['id']}/confirm", headers=instructor_headers)

    capsys.readouterr()
    res = client.post(
        "/api/customer/reviews", json={"booking_id": booking["id"], "rating": 5, "comment": "Lovely session"},
        headers=customer_auth_headers,
    )
    out = capsys.readouterr().out

    assert res.status_code == 201
    assert "notify_review@example.com" in out
    assert "Lovely session" in out


def _matched_lesson_request(client, customer_auth_headers, instructor_headers):
    add_availability(client, instructor_headers, TUESDAY, "09:00", "11:00")
    lr = client.post("/api/customer/lesson-requests", json={
        "specialty": "yoga", "city": "New York, NY", "duration_minutes": 30,
        "requested_day": TUESDAY, "requested_start_time": "09:00", "requested_end_time": "11:00", **CARD,
    }, headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
    return lr["id"]


def test_recurring_series_created_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_series_create@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)

    capsys.readouterr()
    client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_series_create@example.com" in out
    assert "created" in out


def test_recurring_series_paused_and_cancelled_notify_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_series_lifecycle@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()

    capsys.readouterr()
    client.put(f"/api/customer/recurring-series/{series['id']}/pause", headers=customer_auth_headers)
    assert "paused" in capsys.readouterr().out

    client.delete(f"/api/customer/recurring-series/{series['id']}", headers=customer_auth_headers)
    out = capsys.readouterr().out
    assert "cancelled" in out
    assert "notify_series_lifecycle@example.com" in out


def test_instructor_cancel_recurring_series_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_series_instr_cancel@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()

    capsys.readouterr()
    client.put(f"/api/recurring-series/{series['id']}/cancel", headers=instructor_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_series_instr_cancel@example.com" in out
    assert "cancelled" in out
