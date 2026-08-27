"""
Shared pytest fixtures.

The key trick: we set DATABASE_URL to a throwaway SQLite file *before*
importing anything from `app` — since database.py reads that variable
at import time, this makes the entire app (not just a swapped-out
dependency) talk to the test database automatically. No mocking
needed, and every route runs exactly the code it runs in production.
"""
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).resolve().parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["SECRET_KEY"] = "test-only-secret"
# Same trick, same reason: email.py/google_auth.py/stripe_connect.py each
# call load_dotenv() too (see their own comments on why), and
# python-dotenv's load_dotenv() defaults to override=False — it never
# clobbers an env var already set, so pre-setting these here (before
# `from app.main import app` triggers those imports) keeps the suite
# isolated from whatever real EMAIL_BACKEND/RESEND_API_KEY/
# GOOGLE_CLIENT_ID/STRIPE_SECRET_KEY happen to be sitting in a
# developer's actual backend/.env. Without this, a developer with real
# credentials configured locally would silently make real Resend/Stripe
# calls (and see real API responses instead of the console output or
# mocked behavior several tests assert on) just by running `pytest` —
# a real Stripe key is the highest-stakes one of these to ever leak into
# a test run by accident.
os.environ["EMAIL_BACKEND"] = "console"
os.environ["RESEND_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["STRIPE_SECRET_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal
from app import geo, models, rate_limit
from app.security import hash_password


@pytest.fixture(autouse=True)
def fresh_database():
    """Runs before and after every single test — each test starts with empty tables."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def fake_geocoding(monkeypatch):
    """create_lesson_request() calls geo.geocode_address(), a real network
    call to OpenStreetMap's Nominatim — hitting that for real on every
    test run would make the suite slow, flaky, dependent on internet
    access, and risks tripping Nominatim's ~1 request/second usage
    policy. Fake it deterministically instead: resolve "city, state"
    against the same DEMO_CITIES coordinates the old fixed dropdown used,
    so every existing distance-based assertion (which was written
    against those exact coordinates) keeps working unchanged. A
    city/state combo that isn't a known demo city (e.g. an
    invalid-address test) correctly resolves to None, the same way the
    old CITY_BY_NAME.get() did for an unknown city name."""
    def fake_geocode(city, state):
        return geo.CITY_BY_NAME.get(f"{city}, {state}")
    monkeypatch.setattr(geo, "geocode_address", fake_geocode)
    yield


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """rate_limit's attempt counts live in a plain module-level dict, not
    the database, so fresh_database's drop/create doesn't touch them —
    without this, one test's failed logins could spuriously 429 a later,
    unrelated test that happens to reuse the same email/IP."""
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()


@pytest.fixture(scope="session", autouse=True)
def _remove_test_db_file():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
def client():
    return TestClient(app)


def signup(client, email, password="testpass123", name="Test Instructor", phone="555-010-0000"):
    """Not a fixture itself — a helper the fixtures below call, so each
    test can control the email/password when it needs to (e.g. to create
    a *second* instructor for isolation tests)."""
    res = client.post("/api/auth/signup", json={"name": name, "email": email, "phone": phone, "password": password})
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.fixture
def auth_headers(client):
    """A logged-in instructor, ready to use in any test that needs one."""
    token = signup(client, email="instructor@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def second_auth_headers(client):
    """A second, different logged-in instructor — for testing data isolation."""
    token = signup(client, email="second@example.com")
    return {"Authorization": f"Bearer {token}"}


def signup_customer(client, email, password="custpass123", name="Test Customer", phone="555-010-1111"):
    res = client.post("/api/customer/auth/signup", json={"name": name, "email": email, "phone": phone, "password": password})
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


@pytest.fixture
def customer_auth_headers(client):
    """A logged-in customer, ready to use in any booking test."""
    token = signup_customer(client, email="customer@example.com")
    return {"Authorization": f"Bearer {token}"}


def signup_instructor_with_specialty(client, email, specialty, name="Test Instructor"):
    """An instructor defaults to specialty='yoga' on signup — this helper
    signs one up and then sets a specific specialty via the profile
    endpoint, for tests that need to control who matches what."""
    token = signup(client, email=email, name=name)
    headers = {"Authorization": f"Bearer {token}"}
    update_res = client.put("/api/profile", json={"specialty": specialty}, headers=headers)
    assert update_res.status_code == 200, update_res.text
    return token


def set_instructor_city(client, headers, city):
    """`city` is a "City, ST" string (e.g. "Chicago, IL") — split into the
    city_name/state_name ProfileUpdate now expects; fake_geocoding below
    resolves the pair back to the same DEMO_CITIES coordinates either way."""
    city_name, state_name = city.split(", ")
    res = client.put("/api/profile", json={"city_name": city_name, "state_name": state_name}, headers=headers)
    assert res.status_code == 200, res.text


def set_instructor_max_distance(client, headers, km):
    res = client.put("/api/profile", json={"max_travel_distance_km": km}, headers=headers)
    assert res.status_code == 200, res.text


def add_availability(client, headers, day_of_week, start_time, end_time):
    res = client.post("/api/availability", json={
        "day_of_week": day_of_week, "start_time": start_time, "end_time": end_time,
    }, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def create_admin_and_login(client, email="admin@example.com", password="adminpass123", name="Test Admin"):
    """There's no admin signup route on purpose (see models.Admin's
    docstring) — the only way to get an admin account, in production or
    in a test, is to insert one directly. Mirrors what create_admin.py
    does interactively, minus the prompts."""
    db = SessionLocal()
    try:
        db.add(models.Admin(name=name, email=email, hashed_password=hash_password(password)))
        db.commit()
    finally:
        db.close()
    res = client.post("/api/admin/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
def admin_auth_headers(client):
    token = create_admin_and_login(client)
    return {"Authorization": f"Bearer {token}"}


def create_booking_row(customer_email="customer@example.com", instructor_id=None, city=None, **overrides):
    """`Booking` has no public create route anymore (see
    routers/bookings.py's module docstring — every new customer request
    goes through lesson_requests.py now) but the whole confirm/admin/
    review side of it stays live for whatever existed at cutover, and
    deserves real test coverage. Inserts a row directly, same idea as
    create_admin_and_login above for a model with no public create route.
    `city` (optional) sets the customer's lat/lng the same way the old
    create route used to, for distance-based visibility tests."""
    db = SessionLocal()
    try:
        customer = db.query(models.Customer).filter(models.Customer.email == customer_email).first()
        if city:
            coords = geo.CITY_BY_NAME[city]
            customer.latitude = coords["lat"]
            customer.longitude = coords["lng"]
        defaults = dict(
            customer_id=customer.id, instructor_id=instructor_id,
            specialty="yoga", package="single", sessions_total=1, amount_paid=65,
            paid=False, status="pending",
        )
        defaults.update(overrides)
        booking = models.Booking(**defaults)
        db.add(booking)
        db.commit()
        db.refresh(booking)
        return booking.id
    finally:
        db.close()
