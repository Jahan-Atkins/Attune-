"""
/api/client-requests — the instructor-facing side of the pending-request
broadcast. A pending Booking or LessonRequest isn't assigned to anyone;
instead, every GET here recomputes which pending requests the logged-in
instructor is currently eligible to see (specialty + active + their own
travel-distance preference, and for schedule requests, a real time-
overlap against their availability blocks). Nothing is snapshotted, so
if an instructor changes their specialty, distance preference, or
availability, what they see here updates immediately.

Confirming a request (PUT .../confirm) is where the two flows this app
has been building toward finally converge: it's the only place a
Booking/LessonRequest actually gets an instructor_id, its card gets
"charged" (paid=True — there's no real gateway, see bookings.py), and a
real Client row is created for the confirming instructor. Both create
routes (bookings.py, lesson_requests.py) deliberately do none of that
anymore.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import geo, models, schemas
from ..database import get_db
from ..matching import has_overlap, within_travel_distance
from ..security import get_current_instructor

router = APIRouter(prefix="/api/client-requests", tags=["client-requests"])

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _my_specialties(instructor: models.Instructor) -> List[str]:
    return [s.strip() for s in (instructor.specialty or "").split(",") if s.strip()]


def _instructor_sees_booking(instructor: models.Instructor, booking: models.Booking) -> bool:
    if not instructor.active:
        return False
    if booking.specialty not in _my_specialties(instructor):
        return False
    customer = booking.customer
    return within_travel_distance(
        instructor.max_travel_distance_km, instructor.latitude, instructor.longitude,
        customer.latitude, customer.longitude,
    )


def _instructor_sees_lesson_request(instructor: models.Instructor, lesson_request: models.LessonRequest) -> bool:
    if not instructor.active:
        return False
    if lesson_request.specialty not in _my_specialties(instructor):
        return False
    customer = lesson_request.customer
    if not within_travel_distance(
        instructor.max_travel_distance_km, instructor.latitude, instructor.longitude,
        customer.latitude, customer.longitude,
    ):
        return False
    blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
    return has_overlap(
        lesson_request.requested_day, lesson_request.requested_start_time,
        lesson_request.requested_end_time, lesson_request.duration_minutes, blocks,
    ) is not None


def _distance_or_none(instructor: models.Instructor, customer: models.Customer) -> Optional[float]:
    if instructor.latitude is None or instructor.longitude is None:
        return None
    if customer.latitude is None or customer.longitude is None:
        return None
    return round(geo.haversine_distance(instructor.latitude, instructor.longitude, customer.latitude, customer.longitude), 1)


def _booking_out(instructor: models.Instructor, booking: models.Booking) -> schemas.ClientRequestOut:
    return schemas.ClientRequestOut(
        id=booking.id,
        request_type="package",
        specialty=booking.specialty,
        package=booking.package,
        sessions_total=booking.sessions_total,
        duration_minutes=None,
        amount_due=booking.amount_paid,
        customer_name=booking.customer.name,
        customer_city=booking.customer.city,
        customer_lat=booking.customer.latitude,
        customer_lng=booking.customer.longitude,
        distance_km=_distance_or_none(instructor, booking.customer),
        requested_day=None,
        requested_start_time=None,
        requested_end_time=None,
        notes=booking.notes,
        created_at=booking.created_at.isoformat() if booking.created_at else None,
    )


def _lesson_request_out(instructor: models.Instructor, lesson_request: models.LessonRequest) -> schemas.ClientRequestOut:
    return schemas.ClientRequestOut(
        id=lesson_request.id,
        request_type="schedule",
        specialty=lesson_request.specialty,
        package=None,
        sessions_total=1,
        duration_minutes=lesson_request.duration_minutes,
        amount_due=lesson_request.amount_paid,
        customer_name=lesson_request.customer.name,
        customer_city=lesson_request.customer.city,
        customer_lat=lesson_request.customer.latitude,
        customer_lng=lesson_request.customer.longitude,
        distance_km=_distance_or_none(instructor, lesson_request.customer),
        requested_day=lesson_request.requested_day,
        requested_start_time=lesson_request.requested_start_time,
        requested_end_time=lesson_request.requested_end_time,
        notes=lesson_request.notes,
        created_at=lesson_request.created_at.isoformat() if lesson_request.created_at else None,
    )


@router.get("", response_model=List[schemas.ClientRequestOut])
def list_client_requests(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    pending_bookings = db.query(models.Booking).filter(models.Booking.status == "pending").all()
    pending_lesson_requests = db.query(models.LessonRequest).filter(models.LessonRequest.status == "pending").all()

    results = [_booking_out(instructor, b) for b in pending_bookings if _instructor_sees_booking(instructor, b)]
    results += [_lesson_request_out(instructor, lr) for lr in pending_lesson_requests if _instructor_sees_lesson_request(instructor, lr)]
    results.sort(key=lambda r: r.created_at or "", reverse=True)
    return results


def _create_client_from_booking(db: Session, instructor: models.Instructor, booking: models.Booking) -> None:
    customer = booking.customer
    initials = "".join(word[0].upper() for word in customer.name.split()[:2]) or "CU"
    db.add(models.Client(
        instructor_id=instructor.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        initials=initials,
        avatar_variant="c1",
        status="current",
        next_session=None,
        sessions_completed=0,
        sessions_total=booking.sessions_total,
        amount_paid=booking.amount_paid,
        amount_total=booking.amount_paid,
    ))


def _create_client_from_lesson_request(db: Session, instructor: models.Instructor, lesson_request: models.LessonRequest) -> None:
    customer = lesson_request.customer
    initials = "".join(word[0].upper() for word in customer.name.split()[:2]) or "CU"
    next_session = f"{DAY_NAMES[lesson_request.requested_day]}, {lesson_request.matched_start_time}"
    db.add(models.Client(
        instructor_id=instructor.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        initials=initials,
        avatar_variant="c1",
        status="current",
        next_session=next_session,
        sessions_completed=0,
        sessions_total=1,
        amount_paid=lesson_request.amount_paid,
        amount_total=lesson_request.amount_paid,
    ))


def _booking_confirmed_out(instructor: models.Instructor, booking: models.Booking) -> schemas.ClientRequestConfirmedOut:
    base = _booking_out(instructor, booking)
    return schemas.ClientRequestConfirmedOut(
        **base.model_dump(),
        customer_email=booking.customer.email,
        customer_phone=booking.customer.phone,
    )


def _lesson_request_confirmed_out(instructor: models.Instructor, lesson_request: models.LessonRequest) -> schemas.ClientRequestConfirmedOut:
    base = _lesson_request_out(instructor, lesson_request)
    return schemas.ClientRequestConfirmedOut(
        **base.model_dump(),
        customer_email=lesson_request.customer.email,
        customer_phone=lesson_request.customer.phone,
    )


@router.put("/bookings/{booking_id}/confirm", response_model=schemas.ClientRequestConfirmedOut)
def confirm_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id, models.Booking.status == "pending").first()
    if not booking:
        raise HTTPException(status_code=404, detail="This request is no longer available.")
    if not _instructor_sees_booking(instructor, booking):
        raise HTTPException(status_code=400, detail="This request doesn't match your specialty or travel distance.")

    booking.instructor_id = instructor.id
    booking.status = "matched"
    booking.paid = True
    _create_client_from_booking(db, instructor, booking)
    db.commit()
    db.refresh(booking)
    return _booking_confirmed_out(instructor, booking)


@router.put("/lesson-requests/{lesson_request_id}/confirm", response_model=schemas.ClientRequestConfirmedOut)
def confirm_lesson_request(
    lesson_request_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    lesson_request = (
        db.query(models.LessonRequest)
        .filter(models.LessonRequest.id == lesson_request_id, models.LessonRequest.status == "pending")
        .first()
    )
    if not lesson_request:
        raise HTTPException(status_code=404, detail="This request is no longer available.")
    if not _instructor_sees_lesson_request(instructor, lesson_request):
        raise HTTPException(status_code=400, detail="This request no longer fits your specialty, availability, or travel distance.")

    blocks = [(b.day_of_week, b.start_time, b.end_time) for b in instructor.availability_blocks]
    matched_window = has_overlap(
        lesson_request.requested_day, lesson_request.requested_start_time,
        lesson_request.requested_end_time, lesson_request.duration_minutes, blocks,
    )
    # _instructor_sees_lesson_request already checked this is not None.
    matched_start, matched_end = matched_window

    lesson_request.instructor_id = instructor.id
    lesson_request.status = "matched"
    lesson_request.paid = True
    lesson_request.matched_start_time = matched_start
    lesson_request.matched_end_time = matched_end
    lesson_request.distance_km = _distance_or_none(instructor, lesson_request.customer)
    _create_client_from_lesson_request(db, instructor, lesson_request)
    db.commit()
    db.refresh(lesson_request)
    return _lesson_request_confirmed_out(instructor, lesson_request)
