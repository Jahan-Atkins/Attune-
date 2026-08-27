"""
/api/customer/recurring-series (customer-facing) and /api/recurring-series
(instructor-facing) — standing weekly bookings built on top of an
already-matched LessonRequest.

No cron job or background scheduler generates future occurrences — that
would be new infrastructure this learning project deliberately avoids
(see CLAUDE.md's "no extra infrastructure" pattern). Instead,
ensure_upcoming_occurrences() runs lazily at the top of the read
endpoints that need to see them (the customer's own lesson-request
history, and the instructor's own recurring-series list) and creates
whatever LessonRequest rows are missing for the next few weeks. A series
that nobody looks at for months just falls behind and catches up the
next time either side checks — that's an accepted tradeoff, not a bug.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..email import send_email
from ..security import get_current_customer, get_current_instructor

router = APIRouter(tags=["recurring-series"])

WEEKS_AHEAD = 4


def ensure_upcoming_occurrences(db: Session, series: models.RecurringSeries, weeks_ahead: int = WEEKS_AHEAD) -> None:
    if series.status != "active":
        return

    today = date.today()
    # date.weekday(): 0=Monday ... 6=Sunday — the same convention this
    # app already uses everywhere else for day_of_week.
    days_until_next = (series.day_of_week - today.weekday()) % 7
    first_occurrence = today + timedelta(days=days_until_next)
    target_dates = [first_occurrence + timedelta(weeks=i) for i in range(weeks_ahead)]

    existing_dates = {
        lr.occurrence_date
        for lr in db.query(models.LessonRequest).filter(models.LessonRequest.recurring_series_id == series.id).all()
    }

    created_any = False
    for d in target_dates:
        iso = d.isoformat()
        if iso in existing_dates:
            continue
        db.add(models.LessonRequest(
            customer_id=series.customer_id,
            instructor_id=series.instructor_id,
            specialty=series.specialty,
            duration_minutes=series.duration_minutes,
            amount_paid=series.price_per_lesson,
            paid=True,
            requested_day=series.day_of_week,
            requested_start_time=series.start_time,
            requested_end_time=series.end_time,
            matched_start_time=series.start_time,
            matched_end_time=series.end_time,
            status="matched",
            recurring_series_id=series.id,
            occurrence_date=iso,
            created_at=datetime.now(timezone.utc),
        ))
        created_any = True
    if created_any:
        db.commit()


def _notify_series(db: Session, series: models.RecurringSeries, event: str) -> None:
    """created/paused/cancelled — the three events the roadmap calls out.
    Not resumed: reactivating just picks back up where the still-existing
    series left off, not really a "new" event worth a separate email."""
    customer = db.query(models.Customer).filter(models.Customer.id == series.customer_id).first()
    instructor = db.query(models.Instructor).filter(models.Instructor.id == series.instructor_id).first()
    day_label = calendar.day_name[series.day_of_week]
    detail = f"Every {day_label}, {series.start_time}–{series.end_time}"
    if customer.email_notifications:
        send_email(
            to=customer.email,
            subject=f"Standing weekly booking {event}",
            body=f"Your recurring booking ({detail}) with {instructor.name} was {event}.",
        )
    if instructor.email_notifications:
        send_email(
            to=instructor.email,
            subject=f"Standing weekly booking {event}",
            body=f"The recurring booking ({detail}) with {customer.name} was {event}.",
        )


@router.post("/api/customer/recurring-series", response_model=schemas.RecurringSeriesOut, status_code=201)
def create_recurring_series(
    payload: schemas.RecurringSeriesCreate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    source = (
        db.query(models.LessonRequest)
        .filter(models.LessonRequest.id == payload.lesson_request_id, models.LessonRequest.customer_id == customer.id)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Lesson request not found.")
    if source.status != "matched" or not source.instructor_id:
        raise HTTPException(status_code=400, detail="You can only make a standing booking from a confirmed match.")
    if source.sessions_total != 1:
        # A multi-session package's amount_paid is the whole package's
        # price, not a per-lesson price — using it as
        # RecurringSeries.price_per_lesson would be wrong. Its sessions
        # get scheduled one at a time instead (schedule_next_session in
        # lesson_requests.py), never folded into a standing series.
        raise HTTPException(status_code=400, detail="Only a single-session request can become a standing weekly booking.")

    existing = (
        db.query(models.RecurringSeries)
        .filter(
            models.RecurringSeries.customer_id == customer.id,
            models.RecurringSeries.instructor_id == source.instructor_id,
            models.RecurringSeries.day_of_week == source.requested_day,
            models.RecurringSeries.start_time == (source.matched_start_time or source.requested_start_time),
            models.RecurringSeries.status == "active",
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="You already have a standing booking for this slot.")

    series = models.RecurringSeries(
        customer_id=customer.id,
        instructor_id=source.instructor_id,
        specialty=source.specialty,
        duration_minutes=source.duration_minutes,
        day_of_week=source.requested_day,
        start_time=source.matched_start_time or source.requested_start_time,
        end_time=source.matched_end_time or source.requested_end_time,
        price_per_lesson=source.amount_paid,
        status="active",
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    ensure_upcoming_occurrences(db, series)
    db.refresh(series)
    _notify_series(db, series, "created")
    return series


@router.get("/api/customer/recurring-series", response_model=List[schemas.RecurringSeriesOut])
def list_my_recurring_series(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    return (
        db.query(models.RecurringSeries)
        .filter(models.RecurringSeries.customer_id == customer.id)
        .order_by(models.RecurringSeries.id.desc())
        .all()
    )


def _get_owned_customer_series(series_id: int, db: Session, customer: models.Customer) -> models.RecurringSeries:
    series = (
        db.query(models.RecurringSeries)
        .filter(models.RecurringSeries.id == series_id, models.RecurringSeries.customer_id == customer.id)
        .first()
    )
    if not series:
        raise HTTPException(status_code=404, detail="Recurring booking not found.")
    return series


@router.put("/api/customer/recurring-series/{series_id}/pause", response_model=schemas.RecurringSeriesOut)
def pause_recurring_series(
    series_id: int,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    series = _get_owned_customer_series(series_id, db, customer)
    if series.status != "active":
        raise HTTPException(status_code=400, detail="Only an active recurring booking can be paused.")
    series.status = "paused"
    db.commit()
    db.refresh(series)
    _notify_series(db, series, "paused")
    return series


@router.put("/api/customer/recurring-series/{series_id}/resume", response_model=schemas.RecurringSeriesOut)
def resume_recurring_series(
    series_id: int,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    series = _get_owned_customer_series(series_id, db, customer)
    if series.status != "paused":
        raise HTTPException(status_code=400, detail="Only a paused recurring booking can be resumed.")
    series.status = "active"
    db.commit()
    db.refresh(series)
    ensure_upcoming_occurrences(db, series)
    db.refresh(series)
    return series


@router.delete("/api/customer/recurring-series/{series_id}", response_model=schemas.RecurringSeriesOut)
def cancel_recurring_series(
    series_id: int,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """A "cancel", not a real delete — past/future generated LessonRequest
    rows keep their recurring_series_id, and the series row itself sticks
    around as a record of what used to be standing."""
    series = _get_owned_customer_series(series_id, db, customer)
    series.status = "cancelled"
    db.commit()
    db.refresh(series)
    _notify_series(db, series, "cancelled")
    return series


@router.get("/api/recurring-series", response_model=List[schemas.RecurringSeriesOut])
def list_my_hosted_recurring_series(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    """The logged-in instructor's own recurring bookings — active and
    paused, not cancelled ones, matching how a cancelled series is no
    longer meaningfully "theirs" to manage."""
    series_list = (
        db.query(models.RecurringSeries)
        .filter(models.RecurringSeries.instructor_id == instructor.id, models.RecurringSeries.status != "cancelled")
        .order_by(models.RecurringSeries.id.desc())
        .all()
    )
    for series in series_list:
        ensure_upcoming_occurrences(db, series)
    return series_list


@router.put("/api/recurring-series/{series_id}/cancel", response_model=schemas.RecurringSeriesOut)
def instructor_cancel_recurring_series(
    series_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    """The instructor-side "stop hosting this" action — same soft-cancel
    as the customer's own cancel route above."""
    series = (
        db.query(models.RecurringSeries)
        .filter(models.RecurringSeries.id == series_id, models.RecurringSeries.instructor_id == instructor.id)
        .first()
    )
    if not series:
        raise HTTPException(status_code=404, detail="Recurring booking not found.")
    series.status = "cancelled"
    db.commit()
    db.refresh(series)
    _notify_series(db, series, "cancelled")
    return series
