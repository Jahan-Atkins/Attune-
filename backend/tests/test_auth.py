from app.routers import auth as auth_module

from .conftest import signup


def _fake_google_identity(email="newgoogle@example.com", name="Ada Google"):
    return lambda id_token: {"email": email, "name": name}


def test_signup_returns_token(client):
    res = client.post("/api/auth/signup", json={
        "name": "Ada Lovelace", "email": "ada@example.com", "phone": "555-010-2222", "password": "supersecret123",
    })
    assert res.status_code == 201
    body = res.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_signup_duplicate_email_rejected(client):
    payload = {"name": "Ada", "email": "dup@example.com", "phone": "555-010-2222", "password": "pw123456"}
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


def test_google_sign_in_creates_new_account(client, monkeypatch):
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_google_identity())
    res = client.post("/api/auth/google", json={"id_token": "fake-token"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_google_sign_in_logs_into_existing_account_by_email(client, monkeypatch):
    signup(client, email="already@example.com", password="mypassword")
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_google_identity(email="already@example.com"))
    res = client.post("/api/auth/google", json={"id_token": "fake-token"})
    assert res.status_code == 200

    # Confirm it's the SAME account, not a duplicate.
    res2 = client.post("/api/auth/login", data={"username": "already@example.com", "password": "mypassword"})
    assert res2.status_code == 200


def test_google_sign_in_rejects_unverifiable_token(client, monkeypatch):
    monkeypatch.setattr(auth_module, "verify_google_id_token", lambda id_token: None)
    res = client.post("/api/auth/google", json={"id_token": "bad-token"})
    assert res.status_code == 401


def test_google_sign_in_not_configured_returns_501(client, monkeypatch):
    def _raise_not_configured(id_token):
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured.")
    monkeypatch.setattr(auth_module, "verify_google_id_token", _raise_not_configured)
    res = client.post("/api/auth/google", json={"id_token": "irrelevant"})
    assert res.status_code == 501


def test_google_only_account_cannot_log_in_with_a_password(client, monkeypatch):
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_google_identity(email="nopass@example.com"))
    client.post("/api/auth/google", json={"id_token": "fake-token"})
    res = client.post("/api/auth/login", data={"username": "nopass@example.com", "password": "anything"})
    assert res.status_code == 401


def test_change_password_requires_auth(client):
    res = client.post("/api/auth/change-password", json={"current_password": "a", "new_password": "newpass123"})
    assert res.status_code == 401


def test_change_password_success(client):
    token = signup(client, email="changepw@example.com", password="oldpass123")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "newpass456"},
        headers=headers,
    )
    assert res.status_code == 200

    # Old password no longer works, new one does.
    old = client.post("/api/auth/login", data={"username": "changepw@example.com", "password": "oldpass123"})
    assert old.status_code == 401
    new = client.post("/api/auth/login", data={"username": "changepw@example.com", "password": "newpass456"})
    assert new.status_code == 200


def test_change_password_rejects_wrong_current_password(client):
    token = signup(client, email="changepw2@example.com", password="oldpass123")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "totallywrong", "new_password": "newpass456"},
        headers=headers,
    )
    assert res.status_code == 400

    still_old = client.post("/api/auth/login", data={"username": "changepw2@example.com", "password": "oldpass123"})
    assert still_old.status_code == 200


def test_change_password_rejected_for_google_only_account(client, monkeypatch):
    monkeypatch.setattr(auth_module, "verify_google_id_token", _fake_google_identity(email="googleonly@example.com"))
    google_res = client.post("/api/auth/google", json={"id_token": "fake-token"})
    headers = {"Authorization": f"Bearer {google_res.json()['access_token']}"}
    res = client.post(
        "/api/auth/change-password",
        json={"current_password": "anything", "new_password": "newpass456"},
        headers=headers,
    )
    assert res.status_code == 400
