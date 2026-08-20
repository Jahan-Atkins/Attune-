"""
/api/customer/lesson-requests — the scheduled-lesson counterpart to
bookings.py's package flow. Same shape of idea (mock payment, then
match, then sync a Client row to the matched instructor) but matching
here also has to satisfy a specific day/time window, not just specialty.

create_lesson_request() does, in order: (1) resolve the customer's
chosen city to lat/lng and save it on their account, (2) the same
format-only mock "payment" check bookings.py uses, (3) find active
instructors who offer the specialty AND have an availability block that
overlaps the requested window for a full-duration slot (has_overlap, in
matching.py), (4) among those, pick the nearest by haversine distance,
tie-breaking by whoever currently has fewer matched lesson requests, and
(5) sync a real Client row to that instructor, same as bookings.py.
"""
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import geo, models, schemas
from ..database import get_db
from ..matching import has_overlap
from ..security import get_current_customer
from .bookings import PACKAGE_PRICING, _mock_charge

router = APIRouter(prefix="/api/customer/lesson-requests", tags=["lesson-requests"])

VALID_SPECIALTIES = ("yoga", "sound_bath")
LESSON_DURATION_MINUTES = 30  # fixed, not selectable — see SCHEDULING-ROADMAP.md Part G
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _find_lesson_match(
    db: Session, specialty: str, requested_day: int, requested_start: str, requested_end: str,
    customer_lat: float, customer_lng: float,
) -> Optional[Tuple[models.Instructor, str, str, float]]:
    candidates = (
        db.query(models.Instructor)
        .filter(models.Instructor.active.is_(True))
        .filter(models.Instructor.specialty.contains(specialty))
        .all()
    )

    fits = []
    for instructor in candidates:
        # Can't rank by distance without a location — a candidate with no
        # city set is treated as unmatchable for this scheduled flow.
        if instructor.latitude is None or instructor.longitude is None:
            continue
        blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
        matched_window = has_overlap(requested_day, requested_start, requested_end, LESSON_DURATION_MINUTES, blocks)
        if matched_window is None:
            continue
        distance_km = geo.haversine_distance(customer_lat, customer_lng, instructor.latitude, instructor.longitude)
        fits.append((instructor, matched_window, distance_km))

    if not fits:
        return None

    def _load(instructor: models.Instructor) -> int:
        return (
            db.query(models.LessonRequest)
            .filter(models.LessonRequest.instructor_id == instructor.id, models.LessonRequest.status == "matched")
            .count()
        )

    instructor, (matched_start, matched_end), distance_km = min(fits, key=lambda f: (f[2], _load(f[0])))
    return instructor, matched_start, matched_end, distance_km


@router.post("", response_model=schemas.LessonRequestOut, status_code=201)
def create_lesson_request(
    payload: schemas.LessonRequestCreate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    if payload.specialty not in VALID_SPECIALTIES:
        raise HTTPException(status_code=400, detail="Unknown specialty.")
    if not (0 <= payload.requested_day <= 6):
        raise HTTPException(status_code=400, detail="requested_day must be 0-6 (Monday-Sunday).")
    if payload.requested_start_time >= payload.requested_end_time:
        raise HTTPException(status_code=400, detail="requested_start_time must be before requested_end_time.")
    city = geo.CITY_BY_NAME.get(payload.city)
    if not city:
        raise HTTPException(status_code=400, detail="Unknown city.")

    _mock_charge(payload.card_number, payload.card_expiry, payload.card_cvc)

    customer.latitude = city["lat"]
    customer.longitude = city["lng"]

    pricing = PACKAGE_PRICING["single"]  # a scheduled request is always exactly one lesson
    match = _find_lesson_match(
        db, payload.specialty, payload.requested_day,
        payload.requested_start_time, payload.requested_end_time,
        city["lat"], city["lng"],
    )

    lesson_request = models.LessonRequest(
        customer_id=customer.id,
        instructor_id=match[0].id if match else None,
        specialty=payload.specialty,
        duration_minutes=LESSON_DURATION_MINUTES,
        amount_paid=pricing["price"],
        requested_day=payload.requested_day,
        requested_start_time=payload.requested_start_time,
        requested_end_time=payload.requested_end_time,
        matched_start_time=match[1] if match else None,
        matched_end_time=match[2] if match else None,
        distance_km=round(match[3], 1) if match else None,
        status="matched" if match else "unmatched",
    )
    db.add(lesson_request)
    db.commit()
    db.refresh(lesson_request)

    if match:
        matched_instructor = match[0]
        initials = "".join(word[0].upper() for word in customer.name.split()[:2]) or "CU"
        next_session = f"{DAY_NAMES[payload.requested_day]}, {match[1]}"
        db.add(models.Client(
            instructor_id=matched_instructor.id,
            name=customer.name,
            initials=initials,
            avatar_variant="c1",
            status="current",
            next_session=next_session,
            sessions_completed=0,
            sessions_total=pricing["sessions"],
            amount_paid=pricing["price"],
            amount_total=pricing["price"],
        ))
        db.commit()

    return lesson_request


@router.get("/me", response_model=schemas.LessonRequestOut)
def get_my_latest_lesson_request(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    lesson_request = (
        db.query(models.LessonRequest)
        .filter(models.LessonRequest.customer_id == customer.id)
        .order_by(models.LessonRequest.id.desc())
        .first()
    )
    if not lesson_request:
        raise HTTPException(status_code=404, detail="No lesson request yet")
    return lesson_request
