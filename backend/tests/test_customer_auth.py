from app.routers import customer_auth as customer_auth_module


def _fake_google_identity(email="newgooglecust@example.com", name="Jordan Google"):
    return lambda id_token: {"email": email, "name": name}


def test_customer_signup_returns_token(client):
    res = client.post("/api/customer/auth/signup", json={
        "name": "Jordan Lee", "email": "jordan@example.com", "phone": "555-010-3333", "password": "custpass123",
    })
    assert res.status_code == 201
    assert "access_token" in res.json()


def test_customer_signup_duplicate_email_rejected(client):
    payload = {"name": "Jordan Lee", "email": "dupcust@example.com", "phone": "555-010-3333", "password": "custpass123"}
    assert client.post("/api/customer/auth/signup", json=payload).status_code == 201
    assert client.post("/api/customer/auth/signup", json=payload).status_code == 400


def test_customer_login(client):
    client.post("/api/customer/auth/signup", json={
        "name": "Jordan Lee", "email": "jordan2@example.com", "phone": "555-010-3333", "password": "custpass123",
    })
    res = client.post("/api/customer/auth/login", data={"username": "jordan2@example.com", "password": "custpass123"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_customer_login_wrong_password(client):
    client.post("/api/customer/auth/signup", json={
        "name": "Jordan Lee", "email": "jordan3@example.com", "phone": "555-010-3333", "password": "custpass123",
    })
    res = client.post("/api/customer/auth/login", data={"username": "jordan3@example.com", "password": "wrong"})
    assert res.status_code == 401


def test_instructor_token_rejected_on_customer_route(client, auth_headers):
    """auth_headers (from conftest) is an *instructor* token — it must not work here."""
    res = client.get("/api/customer/bookings/me", headers=auth_headers)
    assert res.status_code == 401


def test_customer_token_rejected_on_instructor_route(client):
    signup_res = client.post("/api/customer/auth/signup", json={
        "name": "Jordan Lee", "email": "jordan4@example.com", "phone": "555-010-3333", "password": "custpass123",
    })
    customer_headers = {"Authorization": f"Bearer {signup_res.json()['access_token']}"}
    res = client.get("/api/clients", headers=customer_headers)
    assert res.status_code == 401


def test_customer_google_sign_in_creates_new_account(client, monkeypatch):
    monkeypatch.setattr(customer_auth_module, "verify_google_id_token", _fake_google_identity())
    res = client.post("/api/customer/auth/google", json={"id_token": "fake-token"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_customer_google_sign_in_logs_into_existing_account_by_email(client, monkeypatch):
    client.post("/api/customer/auth/signup", json={
        "name": "Jordan Lee", "email": "custgoogle@example.com", "phone": "555-010-3333", "password": "custpass123",
    })
    monkeypatch.setattr(customer_auth_module, "verify_google_id_token", _fake_google_identity(email="custgoogle@example.com"))
    res = client.post("/api/customer/auth/google", json={"id_token": "fake-token"})
    assert res.status_code == 200

    res2 = client.post("/api/customer/auth/login", data={"username": "custgoogle@example.com", "password": "custpass123"})
    assert res2.status_code == 200


def test_customer_google_sign_in_rejects_unverifiable_token(client, monkeypatch):
    monkeypatch.setattr(customer_auth_module, "verify_google_id_token", lambda id_token: None)
    res = client.post("/api/customer/auth/google", json={"id_token": "bad-token"})
    assert res.status_code == 401
