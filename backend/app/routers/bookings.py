"""
/api/customer/bookings — where a paid signup turns into a real match.

The interesting logic is in create_booking() below: it (1) does a
format-only mock "payment" check (no real payment gateway — see
PACKAGE_PRICING and the card validation), (2) finds active instructors
who offer the requested specialty, (3) picks the one with the fewest
current matches (simple load balancing so bookings don't all pile onto
one instructor), and (4) — the part that ties the two apps together —
creates a real Client row for that instructor, so the new customer
immediately shows up in the instructor's own "Current Clients" list.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from .. import models, schemas
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
    Simulated payment — format checks only, no real payment gateway.
    Raises HTTPException the same way a real gateway's rejection would,
    so swapping this out for Stripe later doesn't change any caller code.
    """
    digits = card_number.replace(" ", "")
    if not digits.isdigit() or not (12 <= len(digits) <= 19):
        raise HTTPException(status_code=400, detail="That card number doesn't look right.")
    if "/" not in card_expiry:
        raise HTTPException(status_code=400, detail="Expiry should be in MM/YY format.")
    if not card_cvc.isdigit() or not (3 <= len(card_cvc) <= 4):
        raise HTTPException(status_code=400, detail="That security code doesn't look right.")


def _find_match(db: Session, specialty: str) -> Optional[models.Instructor]:
    candidates = (
        db.query(models.Instructor)
        .filter(models.Instructor.active.is_(True))
        .filter(models.Instructor.specialty.contains(specialty))
        .all()
    )
    if not candidates:
        return None
    # Load-balance: whoever currently has the fewest matched bookings gets the next one.
    load = {
        i.id: db.query(models.Booking)
        .filter(models.Booking.instructor_id == i.id, models.Booking.status == "matched")
        .count()
        for i in candidates
    }
    return min(candidates, key=lambda i: load[i.id])


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

    _mock_charge(payload.card_number, payload.card_expiry, payload.card_cvc)

    pricing = PACKAGE_PRICING[payload.package]
    matched_instructor = _find_match(db, payload.specialty)

    booking = models.Booking(
        customer_id=customer.id,
        instructor_id=matched_instructor.id if matched_instructor else None,
        specialty=payload.specialty,
        package=payload.package,
        sessions_total=pricing["sessions"],
        amount_paid=pricing["price"],
        status="matched" if matched_instructor else "unmatched",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    if matched_instructor:
        initials = "".join(word[0].upper() for word in customer.name.split()[:2]) or "CU"
        db.add(models.Client(
            instructor_id=matched_instructor.id,
            name=customer.name,
            initials=initials,
            avatar_variant="c1",
            status="current",
            next_session=None,
            sessions_completed=0,
            sessions_total=pricing["sessions"],
            amount_paid=pricing["price"],
            amount_total=pricing["price"],
        ))
        db.commit()

    return booking


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
