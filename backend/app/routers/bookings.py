"""
/api/customer/bookings — legacy, read-only. Package selection used to
create a `Booking` here with no scheduling at all; every new customer
request now goes through routers/lesson_requests.py instead, which
carries a `package`/`sessions_total` of its own alongside the
availability windows the customer submits (see that file's module
docstring). This router keeps only what still needs to work for
`Booking` rows that already existed at cutover: `list_packages` (price
lookup lesson_requests.py's create route also reuses), `_mock_charge`
(imported by lesson_requests.py too), and the two read routes so a
customer can still see an old Booking in their history.

Deliberately NOT deleted: `client_requests.py`'s entire Booking-handling
side (visibility, confirm, Client creation) and `admin.py`'s Booking
views. A `Booking` can be sitting at status="pending" — mid-broadcast —
when this cutover ships; ripping out anything downstream of creation
would strand it with no way to ever complete. It's self-draining: once
every pre-cutover pending Booking is confirmed or admin-cancelled, that
code simply stops firing, at zero ongoing cost. Don't "clean this up"
by deleting it.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..email import send_email
from ..security import get_current_customer

router = APIRouter(prefix="/api/customer/bookings", tags=["bookings"])

# The per-session discount grows with package size: 0% for single/pack4,
# ~5% for pack8, ~8% for pack12, ~12% for pack16. Each `price` here is
# round(DURATION_PRICING[30] x (1 - discount)) x sessions — per-session
# rounded to a whole dollar *before* multiplying, matching how
# lesson_requests.py's _price_for() rounds at every other duration too —
# so the actual discount lands a fraction of a point off the target
# percentage (e.g. pack8 is 4.62%, not exactly 5%); that's expected, not
# a bug. lesson_requests.py's PACKAGE_DISCOUNT is derived from these
# numbers, not the other way around — change the discount by changing
# `price` here, not by hand-editing a ratio there.
PACKAGE_PRICING = {
    "single": {"sessions": 1, "price": 65},
    "pack4": {"sessions": 4, "price": 260},
    "pack8": {"sessions": 8, "price": 496},
    "pack12": {"sessions": 12, "price": 720},
    "pack16": {"sessions": 16, "price": 912},
}


@router.get("/packages")
def list_packages():
    """The frontend fetches this instead of hardcoding prices, so the two
    never drift out of sync. Also used by lesson_requests.py's pricing
    formula now — see PACKAGE_DISCOUNT there."""
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


@router.put("/{booking_id}/cancel", response_model=schemas.BookingOut)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """Customer-side self-cancel — same status-flag convention as
    admin.py's force_cancel_booking, just "cancelled_by_customer" instead
    of "cancelled_by_admin" so the two leave a distinguishable trail of
    who actually cancelled."""
    booking = (
        db.query(models.Booking)
        .filter(models.Booking.id == booking_id, models.Booking.customer_id == customer.id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status in ("cancelled_by_admin", "cancelled_by_customer"):
        raise HTTPException(status_code=400, detail="Already cancelled.")
    if booking.status == "unmatched":
        raise HTTPException(status_code=400, detail="This request was never matched — there's nothing to cancel.")

    was_matched = booking.status == "matched"
    instructor = booking.instructor
    booking.status = "cancelled_by_customer"
    db.commit()
    db.refresh(booking)
    if was_matched and instructor and instructor.email_notifications:
        # A matched booking already blocked real calendar time for the
        # instructor — they need to know it's freed up again.
        send_email(
            to=instructor.email,
            subject=f"Booking cancelled by {customer.name}",
            body=f"{customer.name} cancelled their booking with you.",
        )
    return booking
