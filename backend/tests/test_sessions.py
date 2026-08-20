def test_create_session_defaults_to_open(client, auth_headers):
    res = client.post("/api/sessions", json={"title": "Sunrise Flow"}, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["status"] == "open"


def test_request_and_withdraw_session(client, auth_headers):
    create_res = client.post("/api/sessions", json={
        "title": "Sunrise Flow", "date": "Sat, 8:00 AM", "location": "Ocean Park", "pay_rate": "$55",
    }, headers=auth_headers)
    session_id = create_res.json()["id"]

    request_res = client.put(f"/api/sessions/{session_id}/request", headers=auth_headers)
    assert request_res.status_code == 200
    assert request_res.json()["status"] == "requested"

    open_list = client.get("/api/sessions?status=open", headers=auth_headers).json()
    requested_list = client.get("/api/sessions?status=requested", headers=auth_headers).json()
    assert all(s["id"] != session_id for s in open_list)
    assert any(s["id"] == session_id for s in requested_list)

    withdraw_res = client.put(f"/api/sessions/{session_id}/withdraw", headers=auth_headers)
    assert withdraw_res.status_code == 200
    assert withdraw_res.json()["status"] == "open"


def test_requested_sessions_are_isolated_between_instructors(client, auth_headers, second_auth_headers):
    create_res = client.post("/api/sessions", json={"title": "Evening Bath"}, headers=auth_headers)
    session_id = create_res.json()["id"]
    client.put(f"/api/sessions/{session_id}/request", headers=auth_headers)

    mine = client.get("/api/sessions?status=requested", headers=auth_headers).json()
    theirs = client.get("/api/sessions?status=requested", headers=second_auth_headers).json()
    assert any(s["id"] == session_id for s in mine)
    assert all(s["id"] != session_id for s in theirs)


def test_cannot_request_an_already_requested_session(client, auth_headers, second_auth_headers):
    create_res = client.post("/api/sessions", json={"title": "Full Moon Sound Bath"}, headers=auth_headers)
    session_id = create_res.json()["id"]
    client.put(f"/api/sessions/{session_id}/request", headers=auth_headers)

    second_attempt = client.put(f"/api/sessions/{session_id}/request", headers=second_auth_headers)
    assert second_attempt.status_code == 400


def test_delete_session(client, auth_headers):
    create_res = client.post("/api/sessions", json={"title": "Temp Session"}, headers=auth_headers)
    session_id = create_res.json()["id"]

    delete_res = client.delete(f"/api/sessions/{session_id}", headers=auth_headers)
    assert delete_res.status_code == 204
