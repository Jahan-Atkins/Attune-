from datetime import datetime, timedelta

from app.database import SessionLocal
from app import models

from .conftest import create_booking_row


def _instructor_id(email="instructor@example.com"):
    db = SessionLocal()
    try:
        return db.query(models.Instructor).filter(models.Instructor.email == email).first().id
    finally:
        db.close()


def test_summary_requires_auth(client):
    res = client.get("/api/summary")
    assert res.status_code == 401


def test_earned_this_week_defaults_to_zero(client, auth_headers):
    res = client.get("/api/summary", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["earned_this_week"] == 0


def test_earned_this_week_sums_paid_bookings(client, auth_headers, customer_auth_headers):
    instructor_id = _instructor_id()
    create_booking_row(instructor_id=instructor_id, paid=True, status="matched", amount_paid=65)
    create_booking_row(instructor_id=instructor_id, paid=True, status="matched", amount_paid=220)
    res = client.get("/api/summary", headers=auth_headers)
    assert res.json()["earned_this_week"] == 285


def test_earned_this_week_excludes_unpaid(client, auth_headers, customer_auth_headers):
    instructor_id = _instructor_id()
    create_booking_row(instructor_id=instructor_id, paid=False, status="pending", amount_paid=65)
    res = client.get("/api/summary", headers=auth_headers)
    assert res.json()["earned_this_week"] == 0


def test_earned_this_week_excludes_other_instructors(client, auth_headers, second_auth_headers, customer_auth_headers):
    other_instructor_id = _instructor_id("second@example.com")
    create_booking_row(instructor_id=other_instructor_id, paid=True, status="matched", amount_paid=65)
    res = client.get("/api/summary", headers=auth_headers)
    assert res.json()["earned_this_week"] == 0


def test_earned_this_week_excludes_last_week(client, auth_headers, customer_auth_headers):
    instructor_id = _instructor_id()
    create_booking_row(
        instructor_id=instructor_id, paid=True, status="matched", amount_paid=65,
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    res = client.get("/api/summary", headers=auth_headers)
    assert res.json()["earned_this_week"] == 0
