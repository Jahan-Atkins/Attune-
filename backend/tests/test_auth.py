from .conftest import signup


def test_signup_returns_token(client):
    res = client.post("/api/auth/signup", json={
        "name": "Ada Lovelace", "email": "ada@example.com", "password": "supersecret123",
    })
    assert res.status_code == 201
    body = res.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_signup_duplicate_email_rejected(client):
    payload = {"name": "Ada", "email": "dup@example.com", "password": "pw123456"}
    first = client.post("/api/auth/signup", json=payload)
    assert first.status_code == 201
    second = client.post("/api/auth/signup", json=payload)
    assert second.status_code == 400


def test_login_correct_password(client):
    signup(client, email="grace@example.com", password="mypassword")
    res = client.post("/api/auth/login", data={"username": "grace@example.com", "password": "mypassword"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password_rejected(client):
    signup(client, email="grace2@example.com", password="mypassword")
    res = client.post("/api/auth/login", data={"username": "grace2@example.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_login_unknown_email_rejected(client):
    res = client.post("/api/auth/login", data={"username": "nobody@example.com", "password": "whatever"})
    assert res.status_code == 401


def test_me_requires_token(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_returns_current_instructor(client, auth_headers):
    res = client.get("/api/auth/me", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "instructor@example.com"
