"""
/api/admin/* — every route here requires a valid admin token
(Depends(get_current_admin)). Unlike clients.py's instructor-scoping or
bookings.py's customer-scoping, there's no ownership filter to apply:
an admin sees everything, platform-wide, by design.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---- Instructors ----

@router.get("/instructors", response_model=List[schemas.InstructorAdminOut])
def list_instructors(
    active: Optional[bool] = Query(None),
    suspended: Optional[bool] = Query(None),
    specialty: Optional[str] = Query(None, description="'yoga' or 'sound_bath' — substring match, an instructor can offer both"),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    query = db.query(models.Instructor)
    if active is not None:
        query = query.filter(models.Instructor.active == active)
    if suspended is not None:
        query = query.filter(models.Instructor.suspended == suspended)
    if specialty:
        query = query.filter(models.Instructor.specialty.contains(specialty))
    return query.order_by(models.Instructor.id).all()


@router.get("/instructors/{instructor_id}", response_model=schemas.InstructorAdminOut)
def get_instructor(instructor_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found.")
    return instructor


@router.put("/instructors/{instructor_id}/suspend", response_model=schemas.InstructorAdminOut)
def suspend_instructor(
    instructor_id: int, payload: schemas.SuspendRequest,
    db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin),
):
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found.")
    instructor.suspended = True
    instructor.suspension_reason = payload.reason
    db.commit()
    db.refresh(instructor)
    return instructor


@router.put("/instructors/{instructor_id}/unsuspend", response_model=schemas.InstructorAdminOut)
def unsuspend_instructor(instructor_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found.")
    instructor.suspended = False
    instructor.suspension_reason = None
    db.commit()
    db.refresh(instructor)
    return instructor


# ---- Customers ----

@router.get("/customers", response_model=List[schemas.CustomerAdminOut])
def list_customers(
    suspended: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    query = db.query(models.Customer)
    if suspended is not None:
        query = query.filter(models.Customer.suspended == suspended)
    return query.order_by(models.Customer.id).all()


@router.get("/customers/{customer_id}", response_model=schemas.CustomerAdminOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return customer


@router.put("/customers/{customer_id}/suspend", response_model=schemas.CustomerAdminOut)
def suspend_customer(
    customer_id: int, payload: schemas.SuspendRequest,
    db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin),
):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    customer.suspended = True
    customer.suspension_reason = payload.reason
    db.commit()
    db.refresh(customer)
    return customer


@router.put("/customers/{customer_id}/unsuspend", response_model=schemas.CustomerAdminOut)
def unsuspend_customer(customer_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    customer.suspended = False
    customer.suspension_reason = None
    db.commit()
    db.refresh(customer)
    return customer


# ---- Bookings / lesson requests ----

def _booking_admin_out(booking: models.Booking) -> schemas.BookingAdminOut:
    return schemas.BookingAdminOut(
        id=booking.id,
        customer_name=booking.customer.name,
        instructor_name=booking.instructor.name if booking.instructor else None,
        specialty=booking.specialty,
        package=booking.package,
        amount_paid=booking.amount_paid,
        paid=booking.paid,
        status=booking.status,
        created_at=booking.created_at,
    )


def _lesson_request_admin_out(lesson_request: models.LessonRequest) -> schemas.LessonRequestAdminOut:
    return schemas.LessonRequestAdminOut(
        id=lesson_request.id,
        customer_name=lesson_request.customer.name,
        instructor_name=lesson_request.instructor.name if lesson_request.instructor else None,
        specialty=lesson_request.specialty,
        duration_minutes=lesson_request.duration_minutes,
        amount_paid=lesson_request.amount_paid,
        paid=lesson_request.paid,
        status=lesson_request.status,
        requested_day=lesson_request.requested_day,
        requested_start_time=lesson_request.requested_start_time,
        requested_end_time=lesson_request.requested_end_time,
        created_at=lesson_request.created_at,
    )


@router.get("/bookings", response_model=List[schemas.BookingAdminOut])
def list_all_bookings(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    query = db.query(models.Booking)
    if status:
        query = query.filter(models.Booking.status == status)
    bookings = query.order_by(models.Booking.id.desc()).all()
    return [_booking_admin_out(b) for b in bookings]


@router.put("/bookings/{booking_id}/force-cancel", response_model=schemas.BookingAdminOut)
def force_cancel_booking(booking_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status == "cancelled_by_admin":
        raise HTTPException(status_code=400, detail="Already cancelled.")
    booking.status = "cancelled_by_admin"
    db.commit()
    db.refresh(booking)
    return _booking_admin_out(booking)


@router.get("/lesson-requests", response_model=List[schemas.LessonRequestAdminOut])
def list_all_lesson_requests(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    query = db.query(models.LessonRequest)
    if status:
        query = query.filter(models.LessonRequest.status == status)
    lesson_requests = query.order_by(models.LessonRequest.id.desc()).all()
    return [_lesson_request_admin_out(lr) for lr in lesson_requests]


@router.put("/lesson-requests/{lesson_request_id}/force-cancel", response_model=schemas.LessonRequestAdminOut)
def force_cancel_lesson_request(lesson_request_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    lesson_request = db.query(models.LessonRequest).filter(models.LessonRequest.id == lesson_request_id).first()
    if not lesson_request:
        raise HTTPException(status_code=404, detail="Lesson request not found.")
    if lesson_request.status == "cancelled_by_admin":
        raise HTTPException(status_code=400, detail="Already cancelled.")
    lesson_request.status = "cancelled_by_admin"
    db.commit()
    db.refresh(lesson_request)
    return _lesson_request_admin_out(lesson_request)


# ---- FAQs ----
# The CRUD that, before this, only ever existed via direct edits to seed.py.

@router.get("/faqs", response_model=List[schemas.FAQOut])
def list_faqs_admin(db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    return db.query(models.FAQ).order_by(models.FAQ.id).all()


@router.post("/faqs", response_model=schemas.FAQOut, status_code=201)
def create_faq(payload: schemas.FAQCreate, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    faq = models.FAQ(question=payload.question, category=payload.category)
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.put("/faqs/{faq_id}", response_model=schemas.FAQOut)
def update_faq(faq_id: int, payload: schemas.FAQCreate, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    faq.question = payload.question
    faq.category = payload.category
    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/faqs/{faq_id}", status_code=204)
def delete_faq(faq_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found.")
    db.delete(faq)
    db.commit()
    return None


# ---- Metrics ----

@router.get("/metrics", response_model=schemas.MetricsOut)
def get_metrics(db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    def _counts_by_status(model):
        rows = db.query(model.status, func.count(model.id)).group_by(model.status).all()
        return {status: count for status, count in rows}

    total_instructors = db.query(models.Instructor).count()
    active_instructors = db.query(models.Instructor).filter(models.Instructor.active.is_(True)).count()
    total_customers = db.query(models.Customer).count()
    active_customers = db.query(models.Customer).filter(models.Customer.suspended.is_(False)).count()

    since = datetime.now(timezone.utc) - timedelta(days=30)
    confirmed = (
        db.query(models.Booking).filter(models.Booking.status == "matched", models.Booking.created_at >= since).count()
        + db.query(models.LessonRequest).filter(models.LessonRequest.status == "matched", models.LessonRequest.created_at >= since).count()
    )
    unmatched = (
        db.query(models.Booking).filter(models.Booking.status == "unmatched", models.Booking.created_at >= since).count()
        + db.query(models.LessonRequest).filter(models.LessonRequest.status == "unmatched", models.LessonRequest.created_at >= since).count()
    )
    match_rate = round(confirmed / (confirmed + unmatched), 3) if (confirmed + unmatched) > 0 else None

    return schemas.MetricsOut(
        total_instructors=total_instructors,
        active_instructors=active_instructors,
        total_customers=total_customers,
        active_customers=active_customers,
        bookings_by_status=_counts_by_status(models.Booking),
        lesson_requests_by_status=_counts_by_status(models.LessonRequest),
        match_rate_30d=match_rate,
    )
