from .conftest import set_instructor_city


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


def test_reject_unknown_city_on_session(client, auth_headers):
    res = client.post("/api/sessions", json={"title": "Bad City Session", "city": "Nowhere, XX"}, headers=auth_headers)
    assert res.status_code == 400


def test_session_city_resolves_and_reports_back(client, auth_headers):
    res = client.post("/api/sessions", json={"title": "NYC Session", "city": "New York, NY"}, headers=auth_headers)
    assert res.status_code == 201
    assert res.json()["city"] == "New York, NY"


def test_filter_sessions_by_day(client, auth_headers):
    client.post("/api/sessions", json={"title": "Monday Class", "day_of_week": 0}, headers=auth_headers)
    client.post("/api/sessions", json={"title": "Friday Class", "day_of_week": 4}, headers=auth_headers)

    res = client.get("/api/sessions?days=0", headers=auth_headers)
    titles = [s["title"] for s in res.json()]
    assert "Monday Class" in titles
    assert "Friday Class" not in titles


def test_filter_sessions_by_max_lessons_per_week(client, auth_headers):
    client.post("/api/sessions", json={"title": "Light Load", "lessons_per_week": 2}, headers=auth_headers)
    client.post("/api/sessions", json={"title": "Heavy Load", "lessons_per_week": 6}, headers=auth_headers)
    client.post("/api/sessions", json={"title": "Unspecified Load"}, headers=auth_headers)

    res = client.get("/api/sessions?max_lessons_per_week=3", headers=auth_headers)
    titles = [s["title"] for s in res.json()]
    assert "Light Load" in titles
    assert "Unspecified Load" in titles  # unknown never gets excluded by a max filter
    assert "Heavy Load" not in titles


def test_sort_sessions_oldest_vs_newest(client, auth_headers):
    first = client.post("/api/sessions", json={"title": "First Posted"}, headers=auth_headers).json()
    second = client.post("/api/sessions", json={"title": "Second Posted"}, headers=auth_headers).json()

    newest = client.get("/api/sessions?sort=newest", headers=auth_headers).json()
    oldest = client.get("/api/sessions?sort=oldest", headers=auth_headers).json()
    assert newest[0]["id"] == second["id"]
    assert oldest[0]["id"] == first["id"]


def test_sort_sessions_nearest_farthest(client, auth_headers):
    set_instructor_city(client, auth_headers, "New York, NY")

    near = client.post("/api/sessions", json={"title": "Near Listing", "city": "New York, NY"}, headers=auth_headers).json()
    far = client.post("/api/sessions", json={"title": "Far Listing", "city": "Los Angeles, CA"}, headers=auth_headers).json()

    nearest = client.get("/api/sessions?sort=nearest", headers=auth_headers).json()
    farthest = client.get("/api/sessions?sort=farthest", headers=auth_headers).json()
    assert nearest[0]["id"] == near["id"]
    assert farthest[0]["id"] == far["id"]
