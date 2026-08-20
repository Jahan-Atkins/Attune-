"""
/api/profile — the logged-in instructor's own bio, address,
certifications, and active status. There's no {id} in these URLs on
purpose: "your profile" is always whoever the token belongs to, never
something you pass in.
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

    # `city` isn't a real column (it's a computed property over lat/lng —
    # see models.py) so it can't go through the generic setattr loop below.
    if "city" in updates:
        city_name = updates.pop("city")
        city = geo.CITY_BY_NAME.get(city_name)
        if not city:
            raise HTTPException(status_code=400, detail="Unknown city.")
        instructor.latitude = city["lat"]
        instructor.longitude = city["lng"]

    for field, value in updates.items():
        setattr(instructor, field, value)
    db.commit()
    db.refresh(instructor)
    return instructor
