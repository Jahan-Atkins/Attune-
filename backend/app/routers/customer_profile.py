"""
/api/customer/profile — the logged-in customer's own name/phone/email
and notification preference. Mirrors app/routers/profile.py's shape
(no {id} in the URL — "your profile" is always whoever the token
belongs to), with one deliberate difference: email/city_name/state_name/
address_line are read-only here. Unlike an instructor's profile, a
customer's email doubles as their login identity, and their city/address
come from the geocoded availability step (lesson_requests.py), not a
bare profile edit — so only name/phone/email_notifications are accepted
by CustomerProfileUpdate at all.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..security import get_current_customer

router = APIRouter(prefix="/api/customer/profile", tags=["customer-profile"])


@router.get("", response_model=schemas.CustomerProfileOut)
def get_profile(customer: models.Customer = Depends(get_current_customer)):
    return customer


@router.put("", response_model=schemas.CustomerProfileOut)
def update_profile(
    payload: schemas.CustomerProfileUpdate,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("", status_code=200)
def delete_profile(
    payload: schemas.DeleteAccountRequest,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    """Hard-deletes the account — bookings/lesson_requests/reviews_given/
    recurring_series all cascade (see models.Customer's relationships).
    Requires the current password as a confirmation step, same reasoning
    as auth.py's change_password, skipped only for a Google-only account
    (nothing to check)."""
    if customer.hashed_password:
        if not payload.current_password or not security.verify_password(payload.current_password, customer.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
    db.delete(customer)
    db.commit()
    return {"detail": "Account deleted."}
