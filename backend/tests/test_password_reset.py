"""
/api/auth/forgot-password + /reset-password, and the customer_auth.py
mirror. The reset link is only ever "sent" via the mock email backend
(see app/email.py), so these tests capture it with capsys the same way
test_email.py does, then pull the raw token out of the printed body to
drive the rest of the flow end to end.
"""
import re

from .conftest import signup, signup_customer

TOKEN_RE = re.compile(r"reset_token=([\w-]+)")


def _extract_token(printed: str) -> str:
    match = TOKEN_RE.search(printed)
    assert match, f"no reset_token found in: {printed!r}"
    return match.group(1)


# ---- instructor ----

def test_forgot_password_always_returns_200_for_unknown_instructor_email(client):
    res = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert res.status_code == 200


def test_forgot_password_does_not_email_unknown_instructor(client, capsys):
    capsys.readouterr()
    client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    out = capsys.readouterr().out
    assert "EMAIL" not in out


def test_reset_password_instructor_end_to_end(client, capsys):
    signup(client, email="reset_me@example.com", password="oldpass123")

    capsys.readouterr()
    res = client.post("/api/auth/forgot-password", json={"email": "reset_me@example.com"})
    assert res.status_code == 200
    token = _extract_token(capsys.readouterr().out)

    reset_res = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpass456"})
    assert reset_res.status_code == 200

    old_login = client.post("/api/auth/login", data={"username": "reset_me@example.com", "password": "oldpass123"})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", data={"username": "reset_me@example.com", "password": "newpass456"})
    assert new_login.status_code == 200


def test_reset_password_token_is_single_use(client, capsys):
    signup(client, email="reuse_me@example.com", password="oldpass123")
    capsys.readouterr()
    client.post("/api/auth/forgot-password", json={"email": "reuse_me@example.com"})
    token = _extract_token(capsys.readouterr().out)

    first = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpass456"})
    assert first.status_code == 200
    second = client.post("/api/auth/reset-password", json={"token": token, "new_password": "another789"})
    assert second.status_code == 400


def test_reset_password_rejects_unknown_token(client):
    res = client.post("/api/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever123"})
    assert res.status_code == 400


# ---- customer ----

def test_forgot_password_always_returns_200_for_unknown_customer_email(client):
    res = client.post("/api/customer/auth/forgot-password", json={"email": "nobody@example.com"})
    assert res.status_code == 200


def test_reset_password_customer_end_to_end(client, capsys):
    signup_customer(client, email="reset_cust@example.com", password="oldpass123")

    capsys.readouterr()
    client.post("/api/customer/auth/forgot-password", json={"email": "reset_cust@example.com"})
    token = _extract_token(capsys.readouterr().out)

    reset_res = client.post("/api/customer/auth/reset-password", json={"token": token, "new_password": "newpass456"})
    assert reset_res.status_code == 200

    old_login = client.post("/api/customer/auth/login", data={"username": "reset_cust@example.com", "password": "oldpass123"})
    assert old_login.status_code == 401
    new_login = client.post("/api/customer/auth/login", data={"username": "reset_cust@example.com", "password": "newpass456"})
    assert new_login.status_code == 200


def test_instructor_reset_token_cannot_be_used_on_customer_endpoint(client, capsys):
    """account_type is part of the lookup filter, not just informational —
    an instructor's token should be meaningless against the customer route
    even if (by astronomically unlikely coincidence) the raw values matched."""
    signup(client, email="cross_type@example.com", password="oldpass123")
    capsys.readouterr()
    client.post("/api/auth/forgot-password", json={"email": "cross_type@example.com"})
    token = _extract_token(capsys.readouterr().out)

    res = client.post("/api/customer/auth/reset-password", json={"token": token, "new_password": "newpass456"})
    assert res.status_code == 400
