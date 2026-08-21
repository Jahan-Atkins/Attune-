from .conftest import (
    add_availability,
    create_admin_and_login,
    signup_instructor_with_specialty,
)

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


# ---- auth ----

def test_admin_login_rejects_unknown_email(client):
    res = client.post("/api/admin/auth/login", data={"username": "nobody@example.com", "password": "whatever"})
    assert res.status_code == 401


def test_admin_login_rejects_wrong_password(client):
    create_admin_and_login(client, email="wrongpw@example.com", password="correctpass1")
    res = client.post("/api/admin/auth/login", data={"username": "wrongpw@example.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_admin_routes_require_admin_token(client):
    assert client.get("/api/admin/instructors").status_code == 401
    assert client.get("/api/admin/customers").status_code == 401
    assert client.get("/api/admin/metrics").status_code == 401


def test_instructor_token_cannot_access_admin_routes(client, auth_headers):
    res = client.get("/api/admin/instructors", headers=auth_headers)
    assert res.status_code == 401


def test_customer_token_cannot_access_admin_routes(client, customer_auth_headers):
    res = client.get("/api/admin/instructors", headers=customer_auth_headers)
    assert res.status_code == 401


def test_admin_token_cannot_access_instructor_routes(client, admin_auth_headers):
    res = client.get("/api/profile", headers=admin_auth_headers)
    assert res.status_code == 401


# ---- instructors ----

def test_list_instructors_sees_everyone(client, admin_auth_headers):
    signup_instructor_with_specialty(client, email="admin_list_1@example.com", specialty="yoga")
    signup_instructor_with_specialty(client, email="admin_list_2@example.com", specialty="sound_bath")

    res = client.get("/api/admin/instructors", headers=admin_auth_headers)
    assert res.status_code == 200
    emails = {i["email"] for i in res.json()}
    assert {"admin_list_1@example.com", "admin_list_2@example.com"}.issubset(emails)


def test_get_instructor_detail_404_for_unknown_id(client, admin_auth_headers):
    res = client.get("/api/admin/instructors/999999", headers=admin_auth_headers)
    assert res.status_code == 404


def test_suspend_and_unsuspend_instructor(client, admin_auth_headers):
    signup_instructor_with_specialty(client, email="admin_suspend@example.com", specialty="yoga")
    instructor_id = next(
        i["id"] for i in client.get("/api/admin/instructors", headers=admin_auth_headers).json()
        if i["email"] == "admin_suspend@example.com"
    )

    res = client.put(
        f"/api/admin/instructors/{instructor_id}/suspend", json={"reason": "policy violation"}, headers=admin_auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["suspended"] is True
    assert res.json()["suspension_reason"] == "policy violation"

    filtered = client.get("/api/admin/instructors?suspended=true", headers=admin_auth_headers).json()
    assert any(i["id"] == instructor_id for i in filtered)

    res = client.put(f"/api/admin/instructors/{instructor_id}/unsuspend", headers=admin_auth_headers)
    assert res.status_code == 200
    assert res.json()["suspended"] is False
    assert res.json()["suspension_reason"] is None


def test_suspended_instructor_disappears_from_broadcast(client, customer_auth_headers, admin_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="admin_suspend_broadcast@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    instructor_id = next(
        i["id"] for i in client.get("/api/admin/instructors", headers=admin_auth_headers).json()
        if i["email"] == "admin_suspend_broadcast@example.com"
    )

    client.put(f"/api/admin/instructors/{instructor_id}/suspend", json={}, headers=admin_auth_headers)

    booking = client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers).json()
    # No active, non-suspended yoga instructor exists in this isolated test DB.
    assert booking["status"] == "unmatched"
    assert client.get("/api/client-requests", headers=instructor_headers).json() == []


# ---- customers ----

def test_list_and_suspend_customer(client, customer_auth_headers, admin_auth_headers):
    res = client.get("/api/admin/customers", headers=admin_auth_headers)
    assert res.status_code == 200
    customer_id = next(c["id"] for c in res.json() if c["email"] == "customer@example.com")

    suspend = client.put(
        f"/api/admin/customers/{customer_id}/suspend", json={"reason": "chargeback"}, headers=admin_auth_headers,
    )
    assert suspend.status_code == 200
    assert suspend.json()["suspended"] is True

    unsuspend = client.put(f"/api/admin/customers/{customer_id}/unsuspend", headers=admin_auth_headers)
    assert unsuspend.status_code == 200
    assert unsuspend.json()["suspended"] is False


def test_get_customer_detail_404_for_unknown_id(client, admin_auth_headers):
    res = client.get("/api/admin/customers/999999", headers=admin_auth_headers)
    assert res.status_code == 404


# ---- bookings / lesson requests ----

def test_admin_sees_bookings_across_all_customers(client, customer_auth_headers, admin_auth_headers):
    signup_instructor_with_specialty(client, email="admin_bookings@example.com", specialty="yoga")
    booking = client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers).json()

    res = client.get("/api/admin/bookings", headers=admin_auth_headers)
    assert res.status_code == 200
    assert any(b["id"] == booking["id"] and b["customer_name"] == "Test Customer" for b in res.json())


def test_admin_force_cancel_booking(client, customer_auth_headers, admin_auth_headers):
    booking = client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers).json()

    res = client.put(f"/api/admin/bookings/{booking['id']}/force-cancel", headers=admin_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_admin"

    again = client.put(f"/api/admin/bookings/{booking['id']}/force-cancel", headers=admin_auth_headers)
    assert again.status_code == 400


def test_admin_filters_bookings_by_status(client, customer_auth_headers, admin_auth_headers):
    signup_instructor_with_specialty(client, email="admin_filter@example.com", specialty="sound_bath")
    client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers)

    res = client.get("/api/admin/bookings?status=unmatched", headers=admin_auth_headers)
    assert res.status_code == 200
    assert all(b["status"] == "unmatched" for b in res.json())


def test_admin_force_cancel_lesson_request(client, customer_auth_headers, admin_auth_headers):
    lr = client.post("/api/customer/lesson-requests", json={
        "specialty": "yoga", "city": "New York, NY", "duration_minutes": 30,
        "requested_day": TUESDAY, "requested_start_time": "09:00", "requested_end_time": "11:00", **CARD,
    }, headers=customer_auth_headers).json()

    res = client.put(f"/api/admin/lesson-requests/{lr['id']}/force-cancel", headers=admin_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled_by_admin"


# ---- FAQs ----

def test_admin_faq_crud(client, admin_auth_headers):
    create = client.post(
        "/api/admin/faqs", json={"question": "Do you offer refunds?", "category": "payments"}, headers=admin_auth_headers,
    )
    assert create.status_code == 201
    faq_id = create.json()["id"]

    listed = client.get("/api/admin/faqs", headers=admin_auth_headers).json()
    assert any(f["id"] == faq_id for f in listed)

    updated = client.put(
        f"/api/admin/faqs/{faq_id}", json={"question": "Do you offer refunds within 24h?", "category": "payments"},
        headers=admin_auth_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["question"] == "Do you offer refunds within 24h?"

    deleted = client.delete(f"/api/admin/faqs/{faq_id}", headers=admin_auth_headers)
    assert deleted.status_code == 204
    assert all(f["id"] != faq_id for f in client.get("/api/admin/faqs", headers=admin_auth_headers).json())


def test_admin_faq_update_404_for_unknown_id(client, admin_auth_headers):
    res = client.put("/api/admin/faqs/999999", json={"question": "x", "category": "app use"}, headers=admin_auth_headers)
    assert res.status_code == 404


# ---- metrics ----

def test_metrics_shape_and_counts(client, customer_auth_headers, admin_auth_headers):
    signup_instructor_with_specialty(client, email="admin_metrics@example.com", specialty="yoga")
    client.post("/api/customer/bookings", json={
        "specialty": "yoga", "package": "single", "city": "New York, NY", **CARD,
    }, headers=customer_auth_headers)

    res = client.get("/api/admin/metrics", headers=admin_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["total_instructors"] >= 1
    assert body["active_instructors"] >= 1
    assert body["total_customers"] >= 1
    assert "pending" in body["bookings_by_status"] or "matched" in body["bookings_by_status"]
    assert body["match_rate_30d"] is None or 0 <= body["match_rate_30d"] <= 1


# ---- client deletion requests ----

CLIENT_PAYLOAD = {"name": "Rosa Klein", "initials": "RK", "avatar_variant": "c1"}


def test_deletion_requests_require_admin_auth(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    client.delete(f"/api/clients/{client_id}", headers=auth_headers)

    assert client.get("/api/admin/client-deletion-requests").status_code == 401
    assert client.get("/api/admin/client-deletion-requests", headers=auth_headers).status_code == 401


def test_list_shows_client_and_instructor_names(client, auth_headers, admin_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    client.delete(f"/api/clients/{client_id}", headers=auth_headers)

    res = client.get("/api/admin/client-deletion-requests", headers=admin_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["client_name"] == "Rosa Klein"
    assert body[0]["instructor_name"] == "Test Instructor"


def test_approve_deletes_client_and_cascades_lessons(client, auth_headers, admin_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    client.post(
        f"/api/clients/{client_id}/lessons", json={"lesson_number": 1, "date": "07/09/2026", "paid": True},
        headers=auth_headers,
    )
    request_id = client.delete(f"/api/clients/{client_id}", headers=auth_headers).json()["id"]

    res = client.put(f"/api/admin/client-deletion-requests/{request_id}/approve", headers=admin_auth_headers)
    assert res.status_code == 200
    assert res.json()["client_name"] == "Rosa Klein"

    assert client.get(f"/api/clients/{client_id}", headers=auth_headers).status_code == 404
    assert client.get("/api/admin/client-deletion-requests", headers=admin_auth_headers).json() == []


def test_deny_keeps_client_and_clears_pending_state(client, auth_headers, admin_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    request_id = client.delete(f"/api/clients/{client_id}", headers=auth_headers).json()["id"]

    res = client.put(f"/api/admin/client-deletion-requests/{request_id}/deny", headers=admin_auth_headers)
    assert res.status_code == 200

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["deletion_pending"] is False
    assert client.get("/api/admin/client-deletion-requests", headers=admin_auth_headers).json() == []


def test_can_request_deletion_again_after_a_denial(client, auth_headers, admin_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    request_id = client.delete(f"/api/clients/{client_id}", headers=auth_headers).json()["id"]
    client.put(f"/api/admin/client-deletion-requests/{request_id}/deny", headers=admin_auth_headers)

    second = client.delete(f"/api/clients/{client_id}", headers=auth_headers)
    assert second.status_code == 202
    assert client.get(f"/api/clients/{client_id}", headers=auth_headers).json()["deletion_pending"] is True


def test_approve_404_for_unknown_request(client, admin_auth_headers):
    res = client.put("/api/admin/client-deletion-requests/999999/approve", headers=admin_auth_headers)
    assert res.status_code == 404


def test_deny_404_for_unknown_request(client, admin_auth_headers):
    res = client.put("/api/admin/client-deletion-requests/999999/deny", headers=admin_auth_headers)
    assert res.status_code == 404
