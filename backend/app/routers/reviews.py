"""
Reviews span two different resource namespaces (a customer submitting
one, an instructor's own reviews list), so unlike most routers here this
one doesn't set a single router-level prefix — each route spells out its
own full path instead. A matched customer already sees an instructor's
average_rating/review_count via InstructorPublicOut, and there's no
instructor-browse feature yet, so there's deliberately no public
GET /api/instructors/{id}/reviews route — add one if a browse feature
ever needs it.

A review is reviewable as soon as its Booking/LessonRequest reaches
"matched" — see models.Review's docstring for why that's the gate
instead of "the session actually happened," and why that's a documented
simplification rather than an oversight.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..email import send_email
from ..security import get_current_customer, get_current_instructor

router = APIRouter(tags=["reviews"])


@router.post("/api/customer/reviews", response_model=schemas.ReviewOut, status_code=201)
def create_review(
    payload: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    if payload.booking_id is None and payload.lesson_request_id is None:
        raise HTTPException(status_code=400, detail="A review must reference a booking or lesson request.")
    if payload.booking_id is not None and payload.lesson_request_id is not None:
        raise HTTPException(status_code=400, detail="A review can only reference one booking or lesson request, not both.")
    if not (1 <= payload.rating <= 5):
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5.")

    if payload.booking_id is not None:
        booking = (
            db.query(models.Booking)
            .filter(models.Booking.id == payload.booking_id, models.Booking.customer_id == customer.id)
            .first()
        )
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found.")
        if booking.status != "matched":
            raise HTTPException(status_code=400, detail="You can only review a confirmed match.")
        already = (
            db.query(models.Review)
            .filter(models.Review.customer_id == customer.id, models.Review.booking_id == booking.id)
            .first()
        )
        if already:
            raise HTTPException(status_code=400, detail="You've already reviewed this booking.")
        instructor_id = booking.instructor_id
    else:
        lesson_request = (
            db.query(models.LessonRequest)
            .filter(models.LessonRequest.id == payload.lesson_request_id, models.LessonRequest.customer_id == customer.id)
            .first()
        )
        if not lesson_request:
            raise HTTPException(status_code=404, detail="Lesson request not found.")
        if lesson_request.status != "matched":
            raise HTTPException(status_code=400, detail="You can only review a confirmed match.")
        already = (
            db.query(models.Review)
            .filter(models.Review.customer_id == customer.id, models.Review.lesson_request_id == lesson_request.id)
            .first()
        )
        if already:
            raise HTTPException(status_code=400, detail="You've already reviewed this lesson.")
        instructor_id = lesson_request.instructor_id

    review = models.Review(
        instructor_id=instructor_id,
        customer_id=customer.id,
        booking_id=payload.booking_id,
        lesson_request_id=payload.lesson_request_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if instructor.email_notifications:
        send_email(
            to=instructor.email,
            subject=f"New {review.rating}-star review from {customer.name}",
            body=review.comment or "(no comment left)",
        )
    return review


@router.get("/api/profile/reviews", response_model=List[schemas.ReviewOut])
def list_my_reviews(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    return (
        db.query(models.Review)
        .filter(models.Review.instructor_id == instructor.id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
