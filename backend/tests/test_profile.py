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
