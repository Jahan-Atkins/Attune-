from app import google_auth


def test_config_reports_no_google_client_id_by_default(client, monkeypatch):
    monkeypatch.setattr(google_auth, "GOOGLE_CLIENT_ID", None)
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.json()["google_client_id"] is None


def test_config_reports_google_client_id_when_configured(client, monkeypatch):
    monkeypatch.setattr(google_auth, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.json()["google_client_id"] == "test-client-id.apps.googleusercontent.com"
