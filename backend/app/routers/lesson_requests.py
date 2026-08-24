"""
/api/customer/lesson-requests — the single entry point for every new
customer request, package or not. A customer submits a package
(single/pack4/pack8/pack12/pack16, same session counts as bookings.py's
legacy PACKAGE_PRICING) plus a *set* of candidate availability windows
and a duration; create_lesson_request() validates the card format (no
charge yet), geocodes the customer's typed city/state into real
coordinates (geo.geocode_address — a live call to OpenStreetMap's
Nominatim, the only external network dependency in this app; the street
address is stored for display only, not geocoded — see geo.py's
docstring for why), and sets "pending" as long as at least one active
instructor could fulfill at least one submitted window.
Whether any *particular* instructor actually sees it also depends on
their own travel-distance preference and which of the submitted windows
(if any) overlaps their own availability blocks — both evaluated
dynamically in client_requests.py, not decided here.

For a multi-session package, only the first session goes through this
broadcast/confirm lifecycle (session_number=1, the "root"). Sessions
2..N are scheduled afterward, one at a time, via schedule_next_session()
below — no re-broadcast, no repayment, since the instructor is already
fixed once the root is matched.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from .. import geo, models, schemas
from ..database import get_db
from ..email import send_email
from ..matching import has_overlap_any
from ..security import get_current_customer
from .blocks import is_blocked
from .bookings import PACKAGE_PRICING, _mock_charge
from .recurring_series import ensure_upcoming_occurrences

router = APIRouter(prefix="/api/customer/lesson-requests", tags=["lesson-requests"])

VALID_SPECIALTIES = ("yoga", "sound_bath")
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Discounted per-minute rate for longer lessons — a 90-minute lesson
# costs less than 3x a 30-minute one, rewarding customers who book longer.
DURATION_PRICING = {
    30: 65,
    45: 90,
    60: 115,
    75: 140,
    90: 160,
}

# Per-session discount for a multi-session package, derived exactly from
# bookings.py's legacy PACKAGE_PRICING (see that file's comment for the
# discount curve and rounding convention) so the numbers scale
# consistently for any duration, not just the 30-minute baseline — a
# package isn't a flat price, it's a real per-session discount applied to
# whatever duration price the customer picked.
PACKAGE_DISCOUNT = {key: info["price"] / (info["sessions"] * DURATION_PRICING[30]) for key, info in PACKAGE_PRICING.items()}


def _price_for(package: str, duration_minutes: int) -> float:
    sessions_total = PACKAGE_PRICING[package]["sessions"]
    per_session = round(DURATION_PRICING[duration_minutes] * PACKAGE_DISCOUNT[package])
    return per_session * sessions_total


@router.get("/durations")
def list_durations():
    """The frontend fetches this instead of hardcoding prices, same
    reasoning as bookings.py's /packages."""
    return DURATION_PRICING


def _validate_windows(windows: List) -> None:
    if not windows:
        raise HTTPException(status_code=400, detail="Submit at least one availability window.")
    for w in windows:
        if not (0 <= w.day_of_week <= 6):
            raise HTTPException(status_code=400, detail="day_of_week must be 0-6 (Monday-Sunday).")
        if w.start_time >= w.end_time:
            raise HTTPException(status_code=400, detail="start_time must be before end_time in every window.")


def _any_active_instructor_can_fulfill(
    db: Session, specialty: str, windows: List, duration_minutes: int,
) -> bool:
    """
    Unlike a specialty-only dead-end check, a scheduled request also
    needs a real time-overlap somewhere — specialty alone doesn't tell
    you whether any submitted window could ever be filled. Distance is
    deliberately NOT checked here: that's an instructor preference that
    can differ (and change) per instructor, evaluated dynamically when
    *they* browse (client_requests.py) — not something that should
    decide whether this request even gets broadcast at all.
    """
    window_tuples = [(w.day_of_week, w.start_time, w.end_time) for w in windows]
    candidates = (
        db.query(models.Instructor)
        .filter(models.Instructor.active.is_(True))
        .filter(models.Instructor.suspended.is_(False))
        .filter(models.Instructor.specialty.contains(specialty))
        .all()
    )
    for instructor in candidates:
        blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
        if has_overlap_any(window_tuples, blocks, duration_minutes) is not None:
            return True
    return False


def _validate_preferred_instructor(
    db: Session, instructor_id: int, specialty: str, windows: List, duration_minutes: int, customer_id: int,
) -> None:
    """Same "fail fast with a 400" reasoning as bookings.py's legacy
    version — a targeted rebook that can't work should tell the customer
    to try a regular request instead, not silently land as "unmatched".
    A block between this customer and instructor (either direction)
    fails the same way — see models.Block's docstring."""
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if (
        not instructor
        or not instructor.active
        or instructor.suspended
        or specialty not in [s.strip() for s in (instructor.specialty or "").split(",") if s.strip()]
        or is_blocked(db, customer_id, instructor_id)
    ):
        raise HTTPException(
            status_code=400,
            detail="This instructor can't currently take this request. Try a regular request instead.",
        )
    window_tuples = [(w.day_of_week, w.start_time, w.end_time) for w in windows]
    blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
    if has_overlap_any(window_tuples, blocks, duration_minutes) is None:
        raise HTTPException(
            status_code=400,
            detail="This instructor doesn't have any of those times open. Try different windows or a regular request instead.",
        )


@router.post("", response_model=schemas.LessonRequestOut, status_code=201)
def create_lesson_request(
    payload: schemas.LessonRequestCreate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    if payload.specialty not in VALID_SPECIALTIES:
        raise HTTPException(status_code=400, detail="Unknown specialty.")
    if payload.package not in PACKAGE_PRICING:
        raise HTTPException(status_code=400, detail="Unknown package.")
    if payload.duration_minutes not in DURATION_PRICING:
        raise HTTPException(status_code=400, detail="Lesson length must be 30-90 minutes, in 15-minute steps.")
    _validate_windows(payload.availability_windows)
    coords = geo.geocode_address(payload.city, payload.state)
    if not coords:
        raise HTTPException(status_code=400, detail="Couldn't find that city. Please check it and try again.")
    if payload.preferred_instructor_id is not None:
        _validate_preferred_instructor(
            db, payload.preferred_instructor_id, payload.specialty,
            payload.availability_windows, payload.duration_minutes, customer.id,
        )

    _mock_charge(payload.card_number, payload.card_expiry, payload.card_cvc)

    customer.address_line = payload.address
    customer.city_name = payload.city
    customer.state_name = payload.state
    customer.latitude = coords["lat"]
    customer.longitude = coords["lng"]

    sessions_total = PACKAGE_PRICING[payload.package]["sessions"]
    price = _price_for(payload.package, payload.duration_minutes)
    has_any_candidate = payload.preferred_instructor_id is not None or _any_active_instructor_can_fulfill(
        db, payload.specialty, payload.availability_windows, payload.duration_minutes,
    )

    lesson_request = models.LessonRequest(
        customer_id=customer.id,
        instructor_id=None,
        preferred_instructor_id=payload.preferred_instructor_id,
        specialty=payload.specialty,
        duration_minutes=payload.duration_minutes,
        package=payload.package,
        sessions_total=sessions_total,
        session_number=1,
        lessons_per_week=payload.lessons_per_week,
        amount_paid=price,
        paid=False,
        notes=payload.notes,
        requested_day=None,
        requested_start_time=None,
        requested_end_time=None,
        matched_start_time=None,
        matched_end_time=None,
        distance_km=None,
        status="pending" if has_any_candidate else "unmatched",
    )
    lesson_request.availability_windows = [
        models.LessonRequestAvailabilityWindow(day_of_week=w.day_of_week, start_time=w.start_time, end_time=w.end_time)
        for w in payload.availability_windows
    ]
    db.add(lesson_request)
    db.commit()
    db.refresh(lesson_request)
    return lesson_request


def _notify_session_scheduled(customer: models.Customer, instructor: models.Instructor, session: models.LessonRequest) -> None:
    when = f"{DAY_NAMES[session.requested_day]}, {session.matched_start_time}–{session.matched_end_time}"
    body = f"Session {session.session_number} of {session.sessions_total} is scheduled for {when}."
    send_email(to=customer.email, subject="Next session scheduled", body=body)
    send_email(to=instructor.email, subject=f"Next session scheduled with {customer.name}", body=body)


@router.post("/{lesson_request_id}/schedule-next", response_model=schemas.LessonRequestOut, status_code=201)
def schedule_next_session(
    lesson_request_id: int,
    payload: schemas.ScheduleNextSessionRequest,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """Schedules the next not-yet-scheduled session of an already-matched
    multi-session package — no re-broadcast (the instructor is already
    fixed) and no repayment (the whole package was already charged when
    the root session was confirmed)."""
    root = (
        db.query(models.LessonRequest)
        .filter(
            models.LessonRequest.id == lesson_request_id,
            models.LessonRequest.customer_id == customer.id,
            models.LessonRequest.session_number == 1,
        )
        .first()
    )
    if not root:
        raise HTTPException(status_code=404, detail="Lesson request not found.")
    if root.status != "matched" or not root.instructor_id:
        raise HTTPException(status_code=400, detail="This package hasn't been matched with an instructor yet.")

    scheduled_count = (
        db.query(models.LessonRequest)
        .filter(
            or_(models.LessonRequest.id == root.id, models.LessonRequest.package_request_id == root.id),
            models.LessonRequest.status == "matched",
        )
        .count()
    )
    if scheduled_count >= root.sessions_total:
        raise HTTPException(status_code=400, detail="All sessions in this package are already scheduled.")

    windows = payload.availability_windows if payload.availability_windows else root.availability_windows
    _validate_windows(windows)
    window_tuples = [(w.day_of_week, w.start_time, w.end_time) for w in windows]

    instructor = root.instructor
    blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
    match = has_overlap_any(window_tuples, blocks, root.duration_minutes)
    if match is None:
        raise HTTPException(status_code=400, detail="None of these windows currently fit this instructor's availability. Try different times.")
    (day, _window_start, _window_end), (matched_start, matched_end) = match

    session = models.LessonRequest(
        customer_id=customer.id,
        instructor_id=instructor.id,
        specialty=root.specialty,
        duration_minutes=root.duration_minutes,
        package=root.package,
        sessions_total=root.sessions_total,
        session_number=scheduled_count + 1,
        package_request_id=root.id,
        amount_paid=0.0,
        paid=True,
        requested_day=day,
        requested_start_time=matched_start,
        requested_end_time=matched_end,
        matched_start_time=matched_start,
        matched_end_time=matched_end,
        status="matched",
    )
    db.add(session)

    client = (
        db.query(models.Client)
        .filter(models.Client.instructor_id == instructor.id, models.Client.customer_id == customer.id)
        .first()
    )
    if client:
        client.next_session = f"{DAY_NAMES[day]}, {matched_start}"

    db.commit()
    db.refresh(session)
    _notify_session_scheduled(customer, instructor, session)
    return session


@router.get("", response_model=List[schemas.LessonRequestOut])
def list_my_lesson_requests(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """Full history, newest first — used for "past matches" (leave a
    review, book again), not just the single latest one /me returns.
    Same shape as bookings.py's legacy list endpoint. Also lazily
    generates any due occurrences for this customer's own active
    recurring series before returning — see recurring_series.py's
    module docstring."""
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
