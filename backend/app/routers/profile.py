"""
/api/profile — the logged-in instructor's own bio, address,
certifications, and active status. There's no {id} in these URLs on
purpose: "your profile" is always whoever the token belongs to, never
something you pass in.

city_name/state_name are geocoded via geo.geocode_address() (the same
real Nominatim call the customer flow uses, not the fixed DEMO_CITIES
dropdown instructor-created session listings still use) — travel-
distance matching depends on this instructor's real latitude/longitude,
so it's worth the real network call, same reasoning as
lesson_requests.py's create_lesson_request.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import geo, models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _current_specialties(instructor: models.Instructor) -> set:
    return {s.strip() for s in (instructor.specialty or "").split(",") if s.strip()}


@router.get("", response_model=schemas.ProfileOut)
def get_profile(instructor: models.Instructor = Depends(get_current_instructor)):
    return instructor


@router.put("", response_model=schemas.ProfileOut)
def update_profile(
    payload: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    updates = payload.model_dump(exclude_unset=True)  # only touch fields that were actually sent

    # A gated specialty (models.GATED_SPECIALTIES) can only ever be added
    # to this column by an approved SpecialtyVerification — see
    # admin.py's approve_specialty_verification, the only other writer of
    # this field. A plain profile edit may freely drop one (an instructor
    # choosing to stop offering something they were approved for needs no
    # re-approval to opt back in later — the approval row still exists),
    # but never add one that isn't already present.
    if "specialty" in updates:
        newly_added = {s.strip() for s in updates["specialty"].split(",") if s.strip()} - _current_specialties(instructor)
        gated_addition = newly_added & set(models.GATED_SPECIALTIES)
        if gated_addition:
            raise HTTPException(
                status_code=400,
                detail=f"{models.SPECIALTY_LABELS[next(iter(gated_addition))]} requires admin verification — submit a verification request instead of adding it directly.",
            )

    # city_name/state_name are geocoded together, not set via the generic
    # setattr loop below — same reasoning as lesson_requests.py's
    # create_lesson_request for the customer side.
    if "city_name" in updates or "state_name" in updates:
        city_name = updates.pop("city_name", None)
        state_name = updates.pop("state_name", None)
        if not city_name or not state_name:
            raise HTTPException(status_code=400, detail="Enter both city and state.")
        coords = geo.geocode_address(city_name, state_name)
        if not coords:
            raise HTTPException(status_code=400, detail="Couldn't find that city. Please check it and try again.")
        instructor.city_name = city_name
        instructor.state_name = state_name
        instructor.latitude = coords["lat"]
        instructor.longitude = coords["lng"]

    for field, value in updates.items():
        setattr(instructor, field, value)
    db.commit()
    db.refresh(instructor)
    return instructor


@router.get("/specialty-verifications", response_model=List[schemas.SpecialtyVerificationOut])
def list_my_specialty_verifications(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    return (
        db.query(models.SpecialtyVerification)
        .filter(models.SpecialtyVerification.instructor_id == instructor.id)
        .order_by(models.SpecialtyVerification.created_at.desc())
        .all()
    )


@router.post("/specialty-verifications", response_model=schemas.SpecialtyVerificationOut, status_code=201)
def request_specialty_verification(
    payload: schemas.SpecialtyVerificationCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    if payload.specialty not in models.GATED_SPECIALTIES:
        raise HTTPException(status_code=400, detail="That specialty doesn't require verification.")
    if payload.specialty in _current_specialties(instructor):
        raise HTTPException(status_code=400, detail="You're already verified for this specialty.")
    existing_pending = (
        db.query(models.SpecialtyVerification)
        .filter(
            models.SpecialtyVerification.instructor_id == instructor.id,
            models.SpecialtyVerification.specialty == payload.specialty,
            models.SpecialtyVerification.status == "pending",
        )
        .first()
    )
    if existing_pending:
        raise HTTPException(status_code=400, detail="You already have a pending request for this specialty.")

    request = models.SpecialtyVerification(
        instructor_id=instructor.id,
        specialty=payload.specialty,
        certification_note=payload.certification_note,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request
