from .conftest import create_admin_and_login, signup_instructor_with_specialty


def test_cannot_add_gated_specialty_directly(client, auth_headers):
    res = client.put("/api/profile", json={"specialty": "yoga,massage"}, headers=auth_headers)
    assert res.status_code == 400


def test_can_drop_a_specialty_freely(client):
    token = signup_instructor_with_specialty(client, email="drop@example.com", specialty="yoga,sound_bath")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.put("/api/profile", json={"specialty": "yoga"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["specialty"] == "yoga"


def test_can_add_meditation_directly(client, auth_headers):
    # meditation isn't gated — same self-service path as yoga/sound_bath.
    res = client.put("/api/profile", json={"specialty": "yoga,meditation"}, headers=auth_headers)
    assert res.status_code == 200
    assert "meditation" in res.json()["specialty"]


def test_request_verification_rejects_ungated_specialty(client, auth_headers):
    res = client.post("/api/profile/specialty-verifications", json={"specialty": "yoga"}, headers=auth_headers)
    assert res.status_code == 400


def test_request_verification_happy_path(client, auth_headers):
    res = client.post(
        "/api/profile/specialty-verifications",
        json={"specialty": "massage", "certification_note": "LMT license #12345"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["status"] == "pending"

    listed = client.get("/api/profile/specialty-verifications", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_cannot_request_same_specialty_twice_while_pending(client, auth_headers):
    client.post("/api/profile/specialty-verifications", json={"specialty": "massage"}, headers=auth_headers)
    res = client.post("/api/profile/specialty-verifications", json={"specialty": "massage"}, headers=auth_headers)
    assert res.status_code == 400


def test_admin_approve_adds_specialty_and_notifies(client, auth_headers, capsys):
    client.post("/api/profile/specialty-verifications", json={"specialty": "acupuncture"}, headers=auth_headers)
    request_id = client.get("/api/profile/specialty-verifications", headers=auth_headers).json()[0]["id"]
    admin_token = create_admin_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    capsys.readouterr()
    res = client.put(f"/api/admin/specialty-verifications/{request_id}/approve", headers=admin_headers)
    out = capsys.readouterr().out
    assert res.status_code == 200
    assert res.json()["status"] == "approved"
    assert "to=instructor@example.com" in out

    profile = client.get("/api/profile", headers=auth_headers)
    assert "acupuncture" in profile.json()["specialty"]


def test_admin_deny_does_not_add_specialty(client, auth_headers):
    client.post("/api/profile/specialty-verifications", json={"specialty": "pelvic_floor_therapy"}, headers=auth_headers)
    request_id = client.get("/api/profile/specialty-verifications", headers=auth_headers).json()[0]["id"]
    admin_token = create_admin_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.put(
        f"/api/admin/specialty-verifications/{request_id}/deny",
        json={"admin_note": "License number didn't check out."},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"
    assert res.json()["admin_note"] == "License number didn't check out."

    profile = client.get("/api/profile", headers=auth_headers)
    assert "pelvic_floor_therapy" not in profile.json()["specialty"]


def test_cannot_review_the_same_request_twice(client, auth_headers):
    client.post("/api/profile/specialty-verifications", json={"specialty": "massage"}, headers=auth_headers)
    request_id = client.get("/api/profile/specialty-verifications", headers=auth_headers).json()[0]["id"]
    admin_token = create_admin_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    client.put(f"/api/admin/specialty-verifications/{request_id}/approve", headers=admin_headers)
    res = client.put(f"/api/admin/specialty-verifications/{request_id}/deny", headers=admin_headers)
    assert res.status_code == 400


def test_admin_can_filter_by_status(client, auth_headers):
    client.post("/api/profile/specialty-verifications", json={"specialty": "massage"}, headers=auth_headers)
    admin_token = create_admin_and_login(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res = client.get("/api/admin/specialty-verifications?status=pending", headers=admin_headers)
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["instructor_name"] == "Test Instructor"


def test_customer_can_request_meditation(client, customer_auth_headers):
    from .conftest import add_availability
    instructor_token = signup_instructor_with_specialty(client, email="med_instructor@example.com", specialty="meditation")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, 1, "09:00", "11:00")

    res = client.post(
        "/api/customer/lesson-requests",
        json={
            "specialty": "meditation", "package": "single", "address": "123 Main St", "city": "New York", "state": "NY",
            "duration_minutes": 30, "availability_windows": [{"day_of_week": 1, "start_time": "09:00", "end_time": "11:00"}],
            "card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123",
        },
        headers=customer_auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["status"] == "pending"
