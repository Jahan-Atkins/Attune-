from app.routers import profile as profile_module


def test_status_requires_auth(client):
    res = client.get("/api/profile/stripe-connect/status")
    assert res.status_code == 401


def test_status_reports_unconfigured_when_no_key_set(client, auth_headers):
    # conftest.py forces STRIPE_SECRET_KEY="" for the whole suite — this
    # is the real, honest state of a fresh checkout with no key set yet.
    res = client.get("/api/profile/stripe-connect/status", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body == {"configured": False, "connected": False, "transfers_enabled": False}


def test_start_rejects_when_unconfigured(client, auth_headers):
    res = client.post("/api/profile/stripe-connect/start", headers=auth_headers)
    assert res.status_code == 501


def test_start_creates_account_and_returns_onboarding_url(client, auth_headers, monkeypatch):
    monkeypatch.setattr(profile_module.stripe_connect, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(profile_module.stripe_connect, "create_connect_account", lambda email: "acct_fake123")
    monkeypatch.setattr(
        profile_module.stripe_connect, "create_onboarding_link",
        lambda account_id, return_url, refresh_url: f"https://connect.stripe.com/setup/{account_id}",
    )
    monkeypatch.setattr(profile_module.stripe_connect, "transfers_enabled", lambda account_id: False)

    res = client.post("/api/profile/stripe-connect/start", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["onboarding_url"] == "https://connect.stripe.com/setup/acct_fake123"

    profile = client.get("/api/profile/stripe-connect/status", headers=auth_headers)
    assert profile.json()["configured"] is True
    assert profile.json()["connected"] is True


def test_start_reuses_existing_account_id(client, auth_headers, monkeypatch):
    monkeypatch.setattr(profile_module.stripe_connect, "STRIPE_SECRET_KEY", "sk_test_fake")
    calls = []
    monkeypatch.setattr(profile_module.stripe_connect, "create_connect_account", lambda email: calls.append(1) or "acct_fake123")
    monkeypatch.setattr(profile_module.stripe_connect, "create_onboarding_link", lambda account_id, return_url, refresh_url: "https://example.com/link")

    client.post("/api/profile/stripe-connect/start", headers=auth_headers)
    client.post("/api/profile/stripe-connect/start", headers=auth_headers)
    assert len(calls) == 1  # second call reused the existing account id, didn't create a new one


def test_status_reflects_live_transfers_enabled_check(client, auth_headers, monkeypatch):
    monkeypatch.setattr(profile_module.stripe_connect, "STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(profile_module.stripe_connect, "create_connect_account", lambda email: "acct_fake123")
    monkeypatch.setattr(profile_module.stripe_connect, "create_onboarding_link", lambda account_id, return_url, refresh_url: "https://example.com/link")
    client.post("/api/profile/stripe-connect/start", headers=auth_headers)

    monkeypatch.setattr(profile_module.stripe_connect, "transfers_enabled", lambda account_id: True)
    res = client.get("/api/profile/stripe-connect/status", headers=auth_headers)
    assert res.json()["transfers_enabled"] is True

    # Not cached-forever — a later check reflecting Stripe reporting it
    # disabled again should be trusted over the previously cached value.
    monkeypatch.setattr(profile_module.stripe_connect, "transfers_enabled", lambda account_id: False)
    res = client.get("/api/profile/stripe-connect/status", headers=auth_headers)
    assert res.json()["transfers_enabled"] is False
