from app.routers import customer_auth as customer_auth_module

from .conftest import create_booking_row, signup_instructor_with_specialty

MAX_ATTEMPTS = 5  # mirrors rate_limit.py's default, same constant every other lockout test hardcodes


def test_profile_requires_auth(client):
    res = client.get("/api/customer/profile")
    assert res.status_code == 401


def test_get_profile_defaults(client, customer_auth_headers):
    res = client.get("/api/customer/profile", headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "customer@example.com"
    assert body["email_notifications"] is True
    assert body["has_password"] is True


def test_update_profile_partial(client, customer_auth_headers):
    res = client.put("/api/customer/profile", json={"phone": "555-999-8888"}, headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["phone"] == "555-999-8888"
    assert res.json()["name"] == "Test Customer"  # unchanged


def test_update_profile_ignores_email(client, customer_auth_headers):
    # CustomerProfileUpdate has no email field at all — sending one should
    # be silently ignored (extra fields), not change the login identity.
    res = client.put("/api/customer/profile", json={"email": "hijacked@example.com"}, headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "customer@example.com"


def test_toggle_email_notifications(client, customer_auth_headers):
    res = client.put("/api/customer/profile", json={"email_notifications": False}, headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["email_notifications"] is False

    fetched = client.get("/api/customer/profile", headers=customer_auth_headers)
    assert fetched.json()["email_notifications"] is False


def test_confirm_booking_respects_customer_notification_setting_off(client, customer_auth_headers, capsys):
    client.put("/api/customer/profile", json={"email_notifications": False}, headers=customer_auth_headers)
    instructor_token = signup_instructor_with_specialty(client, email="notify_customer_off@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    booking_id = create_booking_row(city="New York, NY")

    capsys.readouterr()
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=instructor_headers)
    out = capsys.readouterr().out

    assert "to=customer@example.com" not in out
    assert "to=notify_customer_off@example.com" in out  # the instructor's own send is unaffected


def test_change_password_happy_path(client, customer_auth_headers):
    res = client.post(
        "/api/customer/auth/change-password",
        json={"current_password": "custpass123", "new_password": "newcustpass456"},
        headers=customer_auth_headers,
    )
    assert res.status_code == 200

    relogin = client.post("/api/customer/auth/login", data={"username": "customer@example.com", "password": "newcustpass456"})
    assert relogin.status_code == 200


def test_change_password_wrong_current(client, customer_auth_headers):
    res = client.post(
        "/api/customer/auth/change-password",
        json={"current_password": "wrongpass", "new_password": "newcustpass456"},
        headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_change_password_rejected_for_google_only_account(client, monkeypatch):
    monkeypatch.setattr(customer_auth_module, "verify_google_id_token", lambda id_token: {"email": "google_customer@example.com", "name": "Google Customer"})
    res = client.post("/api/customer/auth/google", json={"id_token": "fake-token"})
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    change_res = client.post(
        "/api/customer/auth/change-password",
        json={"current_password": "anything", "new_password": "newcustpass456"},
        headers=headers,
    )
    assert change_res.status_code == 400


def test_change_password_has_its_own_lockout(client, customer_auth_headers):
    for _ in range(MAX_ATTEMPTS):
        res = client.post(
            "/api/customer/auth/change-password",
            json={"current_password": "wrongpass", "new_password": "newcustpass456"},
            headers=customer_auth_headers,
        )
        assert res.status_code == 400

    locked_out = client.post(
        "/api/customer/auth/change-password",
        json={"current_password": "custpass123", "new_password": "newcustpass456"},
        headers=customer_auth_headers,
    )
    assert locked_out.status_code == 429


def test_delete_account_requires_password(client, customer_auth_headers):
    res = client.request("DELETE", "/api/customer/profile", json={"current_password": "wrongpass"}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_delete_account_happy_path(client, customer_auth_headers):
    res = client.request("DELETE", "/api/customer/profile", json={"current_password": "custpass123"}, headers=customer_auth_headers)
    assert res.status_code == 200

    # The token is now for a deleted account — every authenticated route
    # should reject it, not 500 on a missing row.
    fetched = client.get("/api/customer/profile", headers=customer_auth_headers)
    assert fetched.status_code in (401, 404)


def test_delete_account_cascades_bookings(client, customer_auth_headers):
    create_booking_row(city="New York, NY")
    res = client.request("DELETE", "/api/customer/profile", json={"current_password": "custpass123"}, headers=customer_auth_headers)
    assert res.status_code == 200  # no FK-constraint error from the orphaned booking row
