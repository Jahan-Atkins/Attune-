"""
The SECRET_KEY fallback in app/security.py is public (it's sitting in
this open-source repo), so a production deploy that ever runs on it
would let anyone forge a valid token for any account. See
test_email.py for the same print()-plus-capsys pattern used here.
"""
from app import security


def test_warns_when_secret_key_is_the_default(monkeypatch, capsys):
    monkeypatch.setattr(security, "SECRET_KEY", "dev-only-secret-change-me")
    security._warn_if_default_secret_key()
    out = capsys.readouterr().out
    assert "SECURITY WARNING" in out
    assert "SECRET_KEY" in out


def test_no_warning_when_secret_key_is_set(monkeypatch, capsys):
    monkeypatch.setattr(security, "SECRET_KEY", "a-real-production-secret")
    security._warn_if_default_secret_key()
    out = capsys.readouterr().out
    assert out == ""
