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
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import geo, models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/profile", tags=["profile"])


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
