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
from ..security import get_current_customer

router = APIRouter(prefix="/api/customer/bookings", tags=["bookings"])

PACKAGE_PRICING = {
    "single": {"sessions": 1, "price": 65},
    "pack4": {"sessions": 4, "price": 220},
    "pack8": {"sessions": 8, "price": 400},
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
