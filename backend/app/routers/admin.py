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
from ..email import send_email
from ..security import get_current_admin
from .clients import deletion_request_out

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
        package=lesson_request.package,
        sessions_total=lesson_request.sessions_total,
        session_number=lesson_request.session_number,
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


# ---- Client deletion requests ----
# An instructor can no longer delete a client outright (see
# clients.py's delete_client) — every request lands here for an admin
# to approve (really deletes the client) or deny (client stays, request
# just goes away). Both notify the requesting instructor by email since
# there's no other way for them to learn the outcome short of reopening
# the Client Details page.

@router.get("/client-deletion-requests", response_model=List[schemas.ClientDeletionRequestOut])
def list_client_deletion_requests(db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    requests = db.query(models.ClientDeletionRequest).order_by(models.ClientDeletionRequest.id).all()
    return [deletion_request_out(r) for r in requests]


def _get_deletion_request(request_id: int, db: Session) -> models.ClientDeletionRequest:
    request = db.query(models.ClientDeletionRequest).filter(models.ClientDeletionRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Deletion request not found.")
    return request


@router.put("/client-deletion-requests/{request_id}/approve", response_model=schemas.ClientDeletionRequestOut)
def approve_client_deletion(request_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    request = _get_deletion_request(request_id, db)
    out = deletion_request_out(request)  # built before the delete — the client won't be there to read from after
    instructor_email = request.instructor.email
    db.delete(request.client)  # cascades to lessons and the request row itself (Client.deletion_requests)
    db.commit()
    send_email(
        to=instructor_email,
        subject=f"Client deletion approved: {out.client_name}",
        body=f"An admin approved your request to delete {out.client_name}. This client has been removed.",
    )
    return out


@router.put("/client-deletion-requests/{request_id}/deny", response_model=schemas.ClientDeletionRequestOut)
def deny_client_deletion(request_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    request = _get_deletion_request(request_id, db)
    out = deletion_request_out(request)
    instructor_email = request.instructor.email
    db.delete(request)
    db.commit()
    send_email(
        to=instructor_email,
        subject=f"Client deletion denied: {out.client_name}",
        body=f"An admin denied your request to delete {out.client_name}. This client remains on your practice.",
    )
    return out


# ---- Reports ----
# Unlike client deletion requests, a report is never deleted when
# resolved — see models.Report's docstring for why a persistent history
# matters here specifically.

def _resolve_name(db: Session, account_type: str, account_id: int) -> str:
    model = models.Instructor if account_type == "instructor" else models.Customer
    account = db.query(model).filter(model.id == account_id).first()
    return account.name if account else "(deleted account)"


def _report_out(db: Session, report: models.Report) -> schemas.ReportOut:
    return schemas.ReportOut(
        id=report.id,
        reporter_type=report.reporter_type,
        reporter_name=_resolve_name(db, report.reporter_type, report.reporter_id),
        reported_type=report.reported_type,
        reported_name=_resolve_name(db, report.reported_type, report.reported_id),
        reason=report.reason,
        message=report.message,
        resolved=report.resolved,
        created_at=report.created_at,
    )


@router.get("/reports", response_model=List[schemas.ReportOut])
def list_reports(
    resolved: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    admin: models.Admin = Depends(get_current_admin),
):
    query = db.query(models.Report)
    if resolved is not None:
        query = query.filter(models.Report.resolved == resolved)
    reports = query.order_by(models.Report.id.desc()).all()
    return [_report_out(db, r) for r in reports]


@router.put("/reports/{report_id}/resolve", response_model=schemas.ReportOut)
def resolve_report(report_id: int, db: Session = Depends(get_db), admin: models.Admin = Depends(get_current_admin)):
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    report.resolved = True
    db.commit()
    db.refresh(report)
    return _report_out(db, report)
