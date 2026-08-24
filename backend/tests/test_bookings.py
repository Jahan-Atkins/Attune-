"""
`Booking` has no public create route anymore — every new customer
request goes through lesson_requests.py now (see routers/bookings.py's
module docstring). These tests cover what's still live: pricing lookup,
and reading/history for whatever Booking rows already exist, seeded
directly via conftest's create_booking_row helper.
"""
from .conftest import create_booking_row, signup_customer


def test_list_packages_is_public_pricing(client, customer_auth_headers):
    res = client.get("/api/customer/bookings/packages", headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["single"]["sessions"] == 1
    assert body["pack4"]["sessions"] == 4
    assert body["pack8"]["sessions"] == 8
    assert body["pack12"]["sessions"] == 12
    assert body["pack16"]["sessions"] == 16


def test_no_booking_yet_is_404(client, customer_auth_headers):
    res = client.get("/api/customer/bookings/me", headers=customer_auth_headers)
    assert res.status_code == 404


def test_list_bookings_requires_customer_auth(client):
    res = client.get("/api/customer/bookings")
    assert res.status_code == 401


def test_list_bookings_returns_full_history_newest_first(client, customer_auth_headers):
    first = create_booking_row(package="single")
    second = create_booking_row(package="pack4", sessions_total=4, amount_paid=220)

    history = client.get("/api/customer/bookings", headers=customer_auth_headers).json()
    assert [b["id"] for b in history] == [second, first]


def test_list_bookings_isolated_between_customers(client, customer_auth_headers):
    create_booking_row()

    other_token = signup_customer(client, email="other_history@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert len(client.get("/api/customer/bookings", headers=customer_auth_headers).json()) == 1
    assert len(client.get("/api/customer/bookings", headers=other_headers).json()) == 0
