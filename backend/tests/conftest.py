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

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine


@pytest.fixture(autouse=True)
def fresh_database():
    """Runs before and after every single test — each test starts with empty tables."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _remove_test_db_file():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture
def client():
    return TestClient(app)


def signup(client, email, password="testpass123", name="Test Instructor"):
    """Not a fixture itself — a helper the fixtures below call, so each
    test can control the email/password when it needs to (e.g. to create
    a *second* instructor for isolation tests)."""
    res = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
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


def signup_customer(client, email, password="custpass123", name="Test Customer"):
    res = client.post("/api/customer/auth/signup", json={"name": name, "email": email, "password": password})
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
    res = client.put("/api/profile", json={"city": city}, headers=headers)
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
