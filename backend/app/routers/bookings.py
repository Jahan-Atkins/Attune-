"""
/api/customer/bookings — where a package selection becomes a pending
request. This does NOT auto-match or charge anymore: create_booking()
(1) does a format-only mock "card" check (no real payment gateway, and
critically no actual charge — the card is only charged once an
instructor confirms, see routers/client_requests.py), (2) resolves the
customer's chosen city to lat/lng, and (3) sets status "pending" as long
as at least one active instructor offers the specialty at all — the true
"unmatched" dead end is reserved for when literally none do, since
whether any *particular* instructor sees this request depends on their
own travel-distance preference, evaluated dynamically when they browse
(client_requests.py), not decided here.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import geo, models, schemas
from ..database import get_db
from ..security import get_current_customer

router = APIRouter(prefix="/api/customer/bookings", tags=["bookings"])

PACKAGE_PRICING = {
    "single": {"sessions": 1, "price": 65},
    "pack4": {"sessions": 4, "price": 220},
    "pack8": {"sessions": 8, "price": 400},
}

VALID_SPECIALTIES = ("yoga", "sound_bath")


@router.get("/packages")
def list_packages():
    """The frontend fetches this instead of hardcoding prices, so the two
    never drift out of sync."""
    return PACKAGE_PRICING


def _mock_charge(card_number: str, card_expiry: str, card_cvc: str) -> None:
    """
    Simulated payment — format checks only, no real payment gateway, and
    (as of the request/confirm flow) no actual charge either: this just
    validates the card looks well-formed so the customer gets instant
    feedback, the same way a real gateway's format validation would. The
    real "charge" is nothing more than flipping `paid` to True once an
    instructor confirms — there's no card data to re-run at that point,
    which is why none is persisted here.
    """
    digits = card_number.replace(" ", "")
    if not digits.isdigit() or not (12 <= len(digits) <= 19):
        raise HTTPException(status_code=400, detail="That card number doesn't look right.")
    if "/" not in card_expiry:
        raise HTTPException(status_code=400, detail="Expiry should be in MM/YY format.")
    if not card_cvc.isdigit() or not (3 <= len(card_cvc) <= 4):
        raise HTTPException(status_code=400, detail="That security code doesn't look right.")


def _any_active_instructor_offers(db: Session, specialty: str) -> bool:
    return (
        db.query(models.Instructor)
        .filter(models.Instructor.active.is_(True))
        .filter(models.Instructor.suspended.is_(False))
        .filter(models.Instructor.specialty.contains(specialty))
        .first()
        is not None
    )


def _validate_preferred_instructor(db: Session, instructor_id: int, specialty: str) -> None:
    """
    A "Book Again" request targets one specific instructor instead of
    broadcasting — so unlike the normal dead-end check, an instructor who
    can't currently take it fails the request outright (400) rather than
    silently landing as "unmatched", since the frontend can offer a
    regular (broadcast) request as the next step.
    """
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if (
        not instructor
        or not instructor.active
        or instructor.suspended
        or specialty not in [s.strip() for s in (instructor.specialty or "").split(",") if s.strip()]
    ):
        raise HTTPException(
            status_code=400,
            detail="This instructor can't currently take this request — try a regular request instead.",
        )


@router.post("", response_model=schemas.BookingOut, status_code=201)
def create_booking(
    payload: schemas.BookingCreate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    if payload.specialty not in VALID_SPECIALTIES:
        raise HTTPException(status_code=400, detail="Unknown specialty.")
    if payload.package not in PACKAGE_PRICING:
        raise HTTPException(status_code=400, detail="Unknown package.")
    city = geo.CITY_BY_NAME.get(payload.city)
    if not city:
        raise HTTPException(status_code=400, detail="Unknown city.")
    if payload.preferred_instructor_id is not None:
        _validate_preferred_instructor(db, payload.preferred_instructor_id, payload.specialty)

    _mock_charge(payload.card_number, payload.card_expiry, payload.card_cvc)

    customer.latitude = city["lat"]
    customer.longitude = city["lng"]

    pricing = PACKAGE_PRICING[payload.package]
    has_any_candidate = payload.preferred_instructor_id is not None or _any_active_instructor_offers(db, payload.specialty)

    booking = models.Booking(
        customer_id=customer.id,
        instructor_id=None,
        preferred_instructor_id=payload.preferred_instructor_id,
        specialty=payload.specialty,
        package=payload.package,
        sessions_total=pricing["sessions"],
        amount_paid=pricing["price"],
        paid=False,
        notes=payload.notes,
        status="pending" if has_any_candidate else "unmatched",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("", response_model=List[schemas.BookingOut])
def list_my_bookings(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """Full history, newest first — used for "past matches" (leave a
    review, book again), not just the single latest one /me returns."""
    return (
        db.query(models.Booking)
        .filter(models.Booking.customer_id == customer.id)
        .order_by(models.Booking.id.desc())
        .all()
    )


@router.get("/me", response_model=schemas.BookingOut)
def get_my_latest_booking(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    booking = (
        db.query(models.Booking)
        .filter(models.Booking.customer_id == customer.id)
        .order_by(models.Booking.id.desc())
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="No booking yet")
    return booking
