def test_profile_requires_auth(client):
    res = client.get("/api/profile")
    assert res.status_code == 401


def test_get_profile_defaults(client, auth_headers):
    res = client.get("/api/profile", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["active"] is True


def test_update_profile_partial(client, auth_headers):
    # ProfileUpdate allows partial updates — only bio should change here,
    # everything else should stay at its previous value.
    res = client.put("/api/profile", json={"bio": "New bio"}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["bio"] == "New bio"
    assert res.json()["name"] == "Test Instructor"  # unchanged


def test_toggle_active(client, auth_headers):
    res = client.put("/api/profile", json={"active": False}, headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["active"] is False


def test_update_profile_geocodes_city(client, auth_headers):
    res = client.put("/api/profile", json={"city_name": "Chicago", "state_name": "IL"}, headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["city"] == "Chicago, IL"
    assert body["city_name"] == "Chicago"
    assert body["state_name"] == "IL"


def test_update_profile_rejects_city_without_state(client, auth_headers):
    res = client.put("/api/profile", json={"city_name": "Chicago"}, headers=auth_headers)
    assert res.status_code == 400


def test_update_profile_rejects_unresolvable_city(client, auth_headers):
    res = client.put("/api/profile", json={"city_name": "Nowhere", "state_name": "ZZ"}, headers=auth_headers)
    assert res.status_code == 400
