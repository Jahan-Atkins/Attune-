from .conftest import add_availability


def test_availability_requires_instructor_auth(client):
    res = client.post("/api/availability", json={"day_of_week": 1, "start_time": "09:00", "end_time": "11:00"})
    assert res.status_code == 401


def test_create_and_list_availability(client, auth_headers):
    add_availability(client, auth_headers, 1, "09:00", "11:00")

    res = client.get("/api/availability", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["day_of_week"] == 1
    assert body[0]["start_time"] == "09:00"
    assert body[0]["end_time"] == "11:00"


def test_reject_invalid_time_range(client, auth_headers):
    res = client.post("/api/availability", json={"day_of_week": 1, "start_time": "11:00", "end_time": "09:00"}, headers=auth_headers)
    assert res.status_code == 400


def test_reject_invalid_day_of_week(client, auth_headers):
    res = client.post("/api/availability", json={"day_of_week": 9, "start_time": "09:00", "end_time": "11:00"}, headers=auth_headers)
    assert res.status_code == 422


def test_reject_overlapping_block_same_day(client, auth_headers):
    add_availability(client, auth_headers, 1, "09:00", "11:00")
    res = client.post("/api/availability", json={"day_of_week": 1, "start_time": "10:00", "end_time": "12:00"}, headers=auth_headers)
    assert res.status_code == 400


def test_non_overlapping_block_same_day_is_allowed(client, auth_headers):
    add_availability(client, auth_headers, 1, "09:00", "11:00")
    res = client.post("/api/availability", json={"day_of_week": 1, "start_time": "11:00", "end_time": "13:00"}, headers=auth_headers)
    assert res.status_code == 201


def test_delete_availability(client, auth_headers):
    block = add_availability(client, auth_headers, 1, "09:00", "11:00")
    delete_res = client.delete(f"/api/availability/{block['id']}", headers=auth_headers)
    assert delete_res.status_code == 204

    res = client.get("/api/availability", headers=auth_headers)
    assert res.json() == []


def test_cannot_delete_another_instructors_availability(client, auth_headers, second_auth_headers):
    block = add_availability(client, auth_headers, 1, "09:00", "11:00")
    res = client.delete(f"/api/availability/{block['id']}", headers=second_auth_headers)
    assert res.status_code == 404


def test_availability_is_isolated_between_instructors(client, auth_headers, second_auth_headers):
    add_availability(client, auth_headers, 1, "09:00", "11:00")
    res = client.get("/api/availability", headers=second_auth_headers)
    assert res.json() == []
