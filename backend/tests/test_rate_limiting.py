"""
Login/forgot-password brute-force protection (app/rate_limit.py). State
lives in a module-level dict, not the database — conftest.py's
fresh_rate_limits fixture clears it before/after every test so these
tests (and every other test file's login calls) can't contaminate each
other.
"""
from app.rate_limit import MAX_ATTEMPTS

from .conftest import signup, signup_customer


def test_locks_out_after_max_failed_attempts(client):
    signup(client, email="ratelimited@example.com", password="correctpass123")

    for _ in range(MAX_ATTEMPTS):
        res = client.post("/api/auth/login", data={"username": "ratelimited@example.com", "password": "wrongpass"})
        assert res.status_code == 401

    locked_out = client.post("/api/auth/login", data={"username": "ratelimited@example.com", "password": "wrongpass"})
    assert locked_out.status_code == 429
    assert "Retry-After" in locked_out.headers

    # Even the *correct* password is refused once locked out — that's the point.
    still_locked = client.post("/api/auth/login", data={"username": "ratelimited@example.com", "password": "correctpass123"})
    assert still_locked.status_code == 429


def test_successful_login_resets_the_counter(client):
    signup(client, email="resets_ok@example.com", password="correctpass123")

    for _ in range(MAX_ATTEMPTS - 1):
        res = client.post("/api/auth/login", data={"username": "resets_ok@example.com", "password": "wrongpass"})
        assert res.status_code == 401

    good = client.post("/api/auth/login", data={"username": "resets_ok@example.com", "password": "correctpass123"})
    assert good.status_code == 200

    # One more failed attempt right after a success shouldn't be anywhere
    # near the lockout threshold.
    after = client.post("/api/auth/login", data={"username": "resets_ok@example.com", "password": "wrongpass"})
    assert after.status_code == 401


def test_lockout_is_scoped_per_email(client):
    signup(client, email="victim_a@example.com", password="correctpass123")
    signup(client, email="victim_b@example.com", password="correctpass123")

    for _ in range(MAX_ATTEMPTS + 1):
        client.post("/api/auth/login", data={"username": "victim_a@example.com", "password": "wrongpass"})

    # victim_a is locked out, but victim_b's own attempts are untouched.
    res = client.post("/api/auth/login", data={"username": "victim_b@example.com", "password": "wrongpass"})
    assert res.status_code == 401


def test_customer_login_has_its_own_lockout(client):
    signup_customer(client, email="cust_ratelimited@example.com", password="correctpass123")

    for _ in range(MAX_ATTEMPTS):
        client.post("/api/customer/auth/login", data={"username": "cust_ratelimited@example.com", "password": "wrongpass"})

    res = client.post("/api/customer/auth/login", data={"username": "cust_ratelimited@example.com", "password": "wrongpass"})
    assert res.status_code == 429


def test_admin_login_has_its_own_lockout(client):
    from .conftest import create_admin_and_login
    create_admin_and_login(client, email="admin_ratelimited@example.com", password="correctpass123")

    for _ in range(MAX_ATTEMPTS):
        client.post("/api/admin/auth/login", data={"username": "admin_ratelimited@example.com", "password": "wrongpass"})

    res = client.post("/api/admin/auth/login", data={"username": "admin_ratelimited@example.com", "password": "wrongpass"})
    assert res.status_code == 429


def test_forgot_password_has_its_own_lockout_independent_of_login(client):
    signup(client, email="forgot_ratelimited@example.com", password="correctpass123")

    # Locking out the login endpoint...
    for _ in range(MAX_ATTEMPTS + 1):
        client.post("/api/auth/login", data={"username": "forgot_ratelimited@example.com", "password": "wrongpass"})

    # ...doesn't touch forgot-password's separate scope.
    res = client.post("/api/auth/forgot-password", json={"email": "forgot_ratelimited@example.com"})
    assert res.status_code == 200

    for _ in range(MAX_ATTEMPTS):
        client.post("/api/auth/forgot-password", json={"email": "forgot_ratelimited@example.com"})
    locked = client.post("/api/auth/forgot-password", json={"email": "forgot_ratelimited@example.com"})
    assert locked.status_code == 429
