from .conftest import signup

CLIENT_PAYLOAD = {
    "name": "Rosa Klein", "initials": "RK", "status": "current",
    "sessions_completed": 2, "sessions_total": 10,
    "amount_paid": 80, "amount_total": 400,
}


def test_list_clients_requires_auth(client):
    res = client.get("/api/clients")
    assert res.status_code == 401


def test_create_and_fetch_client(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    assert create_res.status_code == 201
    client_id = create_res.json()["id"]

    list_res = client.get("/api/clients?status=current", headers=auth_headers)
    assert list_res.status_code == 200
    assert any(c["name"] == "Rosa Klein" for c in list_res.json())

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Rosa Klein"


def test_get_missing_client_404s(client, auth_headers):
    res = client.get("/api/clients/999", headers=auth_headers)
    assert res.status_code == 404


def test_clients_are_isolated_between_instructors(client, auth_headers, second_auth_headers):
    client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)

    mine = client.get("/api/clients?status=current", headers=auth_headers).json()
    theirs = client.get("/api/clients?status=current", headers=second_auth_headers).json()
    assert len(mine) == 1
    assert len(theirs) == 0


def test_cannot_fetch_another_instructors_client_by_id(client, auth_headers, second_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    res = client.get(f"/api/clients/{client_id}", headers=second_auth_headers)
    assert res.status_code == 404


def test_update_client(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    updated_payload = dict(CLIENT_PAYLOAD, sessions_completed=4, amount_paid=160)
    update_res = client.put(f"/api/clients/{client_id}", json=updated_payload, headers=auth_headers)
    assert update_res.status_code == 200
    assert update_res.json()["sessions_completed"] == 4


def test_delete_client_creates_a_pending_request_instead_of_deleting(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    delete_res = client.delete(f"/api/clients/{client_id}", headers=auth_headers)
    assert delete_res.status_code == 202
    assert delete_res.json()["client_id"] == client_id

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert get_res.status_code == 200
    assert get_res.json()["deletion_pending"] is True


def test_delete_client_is_idempotent_while_pending(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    first = client.delete(f"/api/clients/{client_id}", headers=auth_headers)
    second = client.delete(f"/api/clients/{client_id}", headers=auth_headers)
    assert first.json()["id"] == second.json()["id"]


def test_cannot_request_deletion_of_another_instructors_client(client, auth_headers, second_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    res = client.delete(f"/api/clients/{client_id}", headers=second_auth_headers)
    assert res.status_code == 404


def test_client_details_fields_persist(client, auth_headers):
    payload = dict(
        CLIENT_PAYLOAD,
        address="2757 Firethorne Avenue, Fullerton, California 92835",
        location_type="Client's Home",
        start_date="As soon as possible",
        lessons_per_week=3,
        available_days="0,2,3,5",
        weekday_start="10:00", weekday_end="12:00",
        weekend_start="10:00", weekend_end="12:00",
    )
    create_res = client.post("/api/clients", json=payload, headers=auth_headers)
    assert create_res.status_code == 201
    body = create_res.json()
    assert body["address"] == "2757 Firethorne Avenue, Fullerton, California 92835"
    assert body["lessons_per_week"] == 3
    assert body["available_days"] == "0,2,3,5"
    assert body["lessons"] == []


def test_add_and_list_client_lessons(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    res = client.post(
        f"/api/clients/{client_id}/lessons",
        json={"lesson_number": 1, "date": "07/09/2026", "paid": True},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["paid"] is True

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    lessons = get_res.json()["lessons"]
    assert len(lessons) == 1
    assert lessons[0]["lesson_number"] == 1


def test_delete_client_lesson(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    lesson_res = client.post(
        f"/api/clients/{client_id}/lessons",
        json={"lesson_number": 1, "date": "07/09/2026", "paid": True},
        headers=auth_headers,
    )
    lesson_id = lesson_res.json()["id"]

    delete_res = client.delete(f"/api/clients/{client_id}/lessons/{lesson_id}", headers=auth_headers)
    assert delete_res.status_code == 204

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert get_res.json()["lessons"] == []


def test_toggle_lesson_paid_status(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    lesson_res = client.post(
        f"/api/clients/{client_id}/lessons",
        json={"lesson_number": 1, "date": "07/09/2026", "paid": False},
        headers=auth_headers,
    )
    lesson_id = lesson_res.json()["id"]

    res = client.put(
        f"/api/clients/{client_id}/lessons/{lesson_id}/paid", json={"paid": True}, headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["paid"] is True

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert get_res.json()["lessons"][0]["paid"] is True

    # And back the other way — this isn't a one-shot action.
    res = client.put(
        f"/api/clients/{client_id}/lessons/{lesson_id}/paid", json={"paid": False}, headers=auth_headers,
    )
    assert res.json()["paid"] is False


def test_cannot_toggle_lesson_paid_on_another_instructors_client(client, auth_headers, second_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    lesson_res = client.post(
        f"/api/clients/{client_id}/lessons",
        json={"lesson_number": 1, "date": "07/09/2026", "paid": False},
        headers=auth_headers,
    )
    lesson_id = lesson_res.json()["id"]

    res = client.put(
        f"/api/clients/{client_id}/lessons/{lesson_id}/paid", json={"paid": True}, headers=second_auth_headers,
    )
    assert res.status_code == 404


def test_toggle_lesson_paid_404_for_unknown_lesson(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    res = client.put(f"/api/clients/{client_id}/lessons/999999/paid", json={"paid": True}, headers=auth_headers)
    assert res.status_code == 404


def test_cannot_add_lesson_to_another_instructors_client(client, auth_headers, second_auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    res = client.post(
        f"/api/clients/{client_id}/lessons",
        json={"lesson_number": 1, "date": "07/09/2026", "paid": True},
        headers=second_auth_headers,
    )
    assert res.status_code == 404


def test_requesting_deletion_of_a_client_with_lessons_does_not_delete_anything(client, auth_headers):
    """The actual cascade-delete-on-approve behavior is covered in
    test_admin.py — an instructor's own DELETE call never deletes
    anything anymore, lessons included."""
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]
    client.post(
        f"/api/clients/{client_id}/lessons",
        json={"lesson_number": 1, "date": "07/09/2026", "paid": True},
        headers=auth_headers,
    )

    delete_res = client.delete(f"/api/clients/{client_id}", headers=auth_headers)
    assert delete_res.status_code == 202

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert len(get_res.json()["lessons"]) == 1
