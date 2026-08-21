"""
/api/customer/lesson-requests — the scheduled-lesson counterpart to
bookings.py's package flow. Same pending -> broadcast -> instructor-
confirms lifecycle (see bookings.py's module docstring for the full
rationale) — create_lesson_request() validates the card format (no
charge yet), resolves the customer's city, and sets "pending" as long as
at least one active instructor offers the specialty at all. Whether any
*particular* instructor actually sees it also depends on their own
travel-distance preference and whether they have an overlapping
availability block — both evaluated dynamically in client_requests.py,
not decided here.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import geo, models, schemas
from ..database import get_db
from ..matching import has_overlap
from ..security import get_current_customer
from .bookings import _mock_charge
from .recurring_series import ensure_upcoming_occurrences

router = APIRouter(prefix="/api/customer/lesson-requests", tags=["lesson-requests"])

VALID_SPECIALTIES = ("yoga", "sound_bath")

# Discounted per-minute rate for longer lessons — a 90-minute lesson
# costs less than 3x a 30-minute one, rewarding customers who book longer.
DURATION_PRICING = {
    30: 65,
    45: 90,
    60: 115,
    75: 140,
    90: 160,
}


@router.get("/durations")
def list_durations():
    """The frontend fetches this instead of hardcoding prices, same
    reasoning as bookings.py's /packages."""
    return DURATION_PRICING


def _any_active_instructor_can_fulfill(
    db: Session, specialty: str, requested_day: int, requested_start: str, requested_end: str, duration_minutes: int,
) -> bool:
    """
    Unlike bookings.py's specialty-only dead-end check, a scheduled
    request also needs a real time-overlap somewhere — specialty alone
    doesn't tell you whether the requested window could ever be filled.
    Distance is deliberately NOT checked here: that's an instructor
    preference that can differ (and change) per instructor, evaluated
    dynamically when *they* browse (client_requests.py) — not something
    that should decide whether this request even gets broadcast at all.
    """
    candidates = (
        db.query(models.Instructor)
        .filter(models.Instructor.active.is_(True))
        .filter(models.Instructor.specialty.contains(specialty))
        .all()
    )
    for instructor in candidates:
        blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
        if has_overlap(requested_day, requested_start, requested_end, duration_minutes, blocks) is not None:
            return True
    return False


def _validate_preferred_instructor(
    db: Session, instructor_id: int, specialty: str,
    requested_day: int, requested_start: str, requested_end: str, duration_minutes: int,
) -> None:
    """Same "fail fast with a 400" reasoning as bookings.py's version —
    a targeted rebook that can't work should tell the customer to try a
    regular request instead, not silently land as "unmatched"."""
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if (
        not instructor
        or not instructor.active
        or specialty not in [s.strip() for s in (instructor.specialty or "").split(",") if s.strip()]
    ):
        raise HTTPException(
            status_code=400,
            detail="This instructor can't currently take this request — try a regular request instead.",
        )
    blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
    if has_overlap(requested_day, requested_start, requested_end, duration_minutes, blocks) is None:
        raise HTTPException(
            status_code=400,
            detail="This instructor doesn't have that time open — try a different day/time or a regular request instead.",
        )


@router.post("", response_model=schemas.LessonRequestOut, status_code=201)
def create_lesson_request(
    payload: schemas.LessonRequestCreate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    if payload.specialty not in VALID_SPECIALTIES:
        raise HTTPException(status_code=400, detail="Unknown specialty.")
    if payload.duration_minutes not in DURATION_PRICING:
        raise HTTPException(status_code=400, detail="Lesson length must be 30-90 minutes, in 15-minute steps.")
    if not (0 <= payload.requested_day <= 6):
        raise HTTPException(status_code=400, detail="requested_day must be 0-6 (Monday-Sunday).")
    if payload.requested_start_time >= payload.requested_end_time:
        raise HTTPException(status_code=400, detail="requested_start_time must be before requested_end_time.")
    city = geo.CITY_BY_NAME.get(payload.city)
    if not city:
        raise HTTPException(status_code=400, detail="Unknown city.")
    if payload.preferred_instructor_id is not None:
        _validate_preferred_instructor(
            db, payload.preferred_instructor_id, payload.specialty,
            payload.requested_day, payload.requested_start_time, payload.requested_end_time, payload.duration_minutes,
        )

    _mock_charge(payload.card_number, payload.card_expiry, payload.card_cvc)

    customer.latitude = city["lat"]
    customer.longitude = city["lng"]

    price = DURATION_PRICING[payload.duration_minutes]
    has_any_candidate = payload.preferred_instructor_id is not None or _any_active_instructor_can_fulfill(
        db, payload.specialty, payload.requested_day,
        payload.requested_start_time, payload.requested_end_time, payload.duration_minutes,
    )

    lesson_request = models.LessonRequest(
        customer_id=customer.id,
        instructor_id=None,
        preferred_instructor_id=payload.preferred_instructor_id,
        specialty=payload.specialty,
        duration_minutes=payload.duration_minutes,
        amount_paid=price,
        paid=False,
        notes=payload.notes,
        requested_day=payload.requested_day,
        requested_start_time=payload.requested_start_time,
        requested_end_time=payload.requested_end_time,
        matched_start_time=None,
        matched_end_time=None,
        distance_km=None,
        status="pending" if has_any_candidate else "unmatched",
    )
    db.add(lesson_request)
    db.commit()
    db.refresh(lesson_request)
    return lesson_request


@router.get("", response_model=List[schemas.LessonRequestOut])
def list_my_lesson_requests(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """Full history, newest first — used for "past matches" (leave a
    review, book again), not just the single latest one /me returns.
    Same shape as bookings.py's list endpoint. Also lazily generates any
    due occurrences for this customer's own active recurring series
    before returning — see recurring_series.py's module docstring."""
    active_series = (
        db.query(models.RecurringSeries)
        .filter(models.RecurringSeries.customer_id == customer.id, models.RecurringSeries.status == "active")
        .all()
    )
    for series in active_series:
        ensure_upcoming_occurrences(db, series)

    return (
        db.query(models.LessonRequest)
        .filter(models.LessonRequest.customer_id == customer.id)
        .order_by(models.LessonRequest.id.desc())
        .all()
    )


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
