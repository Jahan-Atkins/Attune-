"""
Notification trigger points — see app/email.py's module docstring for
why these are testable with plain capsys instead of mocking a provider:
the only backend right now just prints, so asserting on stdout IS
asserting on the behavior.
"""
from .conftest import add_availability, create_admin_and_login, create_booking_row, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


def _lesson_payload(**overrides):
    payload = {
        "specialty": "yoga", "package": "single", "city": "New York, NY", "duration_minutes": 30,
        "availability_windows": [{"day_of_week": TUESDAY, "start_time": "09:00", "end_time": "11:00"}],
        **CARD,
    }
    payload.update(overrides)
    return payload


def test_send_email_prints_to_console(capsys):
    from app.email import send_email
    send_email(to="someone@example.com", subject="Hello", body="World")
    out = capsys.readouterr().out
    assert "someone@example.com" in out
    assert "Hello" in out


def test_confirm_booking_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_booking@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking_id = create_booking_row(city="New York, NY")

    capsys.readouterr()  # discard anything printed by setup above
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=instructor_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_booking@example.com" in out


def test_confirm_lesson_request_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_schedule@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "09:00", "11:00")
    lr = client.post("/api/customer/lesson-requests", json=_lesson_payload(), headers=customer_auth_headers).json()

    capsys.readouterr()
    client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_schedule@example.com" in out


def test_new_review_notifies_instructor(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_review@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking_id = create_booking_row(city="New York, NY")
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=instructor_headers)

    capsys.readouterr()
    res = client.post(
        "/api/customer/reviews", json={"booking_id": booking_id, "rating": 5, "comment": "Lovely session"},
        headers=customer_auth_headers,
    )
    out = capsys.readouterr().out

    assert res.status_code == 201
    assert "notify_review@example.com" in out
    assert "Lovely session" in out


def _matched_lesson_request(client, customer_auth_headers, instructor_headers):
    add_availability(client, instructor_headers, TUESDAY, "09:00", "11:00")
    lr = client.post("/api/customer/lesson-requests", json=_lesson_payload(), headers=customer_auth_headers).json()
    client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
    return lr["id"]


def test_schedule_next_session_notifies_both_sides(client, customer_auth_headers, capsys):
    instructor_token = signup_instructor_with_specialty(client, email="notify_schedule_next@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "08:00", "12:00")
    root = client.post(
        "/api/customer/lesson-requests", json=_lesson_payload(package="pack4"), headers=customer_auth_headers,
    ).json()
    client.put(f"/api/client-requests/lesson-requests/{root['id']}/confirm", headers=instructor_headers)

    capsys.readouterr()
    client.post(f"/api/customer/lesson-requests/{root['id']}/schedule-next", json={}, headers=customer_auth_headers)
    out = capsys.readouterr().out

    assert "customer@example.com" in out
    assert "notify_schedule_next@example.com" in out


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


def test_approving_client_deletion_notifies_instructor(client, auth_headers, capsys):
    admin_token = create_admin_and_login(client, email="notify_admin_approve@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    client_res = client.post("/api/clients", json={"name": "Rosa Klein", "initials": "RK"}, headers=auth_headers)
    request_id = client.delete(f"/api/clients/{client_res.json()['id']}", headers=auth_headers).json()["id"]

    capsys.readouterr()
    client.put(f"/api/admin/client-deletion-requests/{request_id}/approve", headers=admin_headers)
    out = capsys.readouterr().out

    assert "instructor@example.com" in out
    assert "approved" in out
    assert "Rosa Klein" in out


def test_denying_client_deletion_notifies_instructor(client, auth_headers, capsys):
    admin_token = create_admin_and_login(client, email="notify_admin_deny@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    client_res = client.post("/api/clients", json={"name": "Rosa Klein", "initials": "RK"}, headers=auth_headers)
    request_id = client.delete(f"/api/clients/{client_res.json()['id']}", headers=auth_headers).json()["id"]

    capsys.readouterr()
    client.put(f"/api/admin/client-deletion-requests/{request_id}/deny", headers=admin_headers)
    out = capsys.readouterr().out

    assert "instructor@example.com" in out
    assert "denied" in out
    assert "Rosa Klein" in out
