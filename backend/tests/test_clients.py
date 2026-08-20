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


def test_delete_client(client, auth_headers):
    create_res = client.post("/api/clients", json=CLIENT_PAYLOAD, headers=auth_headers)
    client_id = create_res.json()["id"]

    delete_res = client.delete(f"/api/clients/{client_id}", headers=auth_headers)
    assert delete_res.status_code == 204

    get_res = client.get(f"/api/clients/{client_id}", headers=auth_headers)
    assert get_res.status_code == 404
