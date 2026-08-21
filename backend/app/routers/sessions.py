"""
Everything under /api/sessions.

Unlike clients, "open" session listings are a shared marketplace —
any logged-in instructor can see and create them (think of it like a
job board). Once an instructor requests one, it's tied to them via
requested_by_id, and only shows up under "requested" for that person.

Simplification worth knowing: any instructor can edit/delete any open
listing here, since we don't track a separate "posted by" field. In a
real version you'd add that and check ownership the same way
clients.py checks instructor_id.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import geo, models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _apply_city(session_listing: models.SessionListing, city_name: Optional[str]) -> None:
    if not city_name:
        return
    city = geo.CITY_BY_NAME.get(city_name)
    if not city:
        raise HTTPException(status_code=400, detail="Unknown city.")
    session_listing.latitude = city["lat"]
    session_listing.longitude = city["lng"]


@router.get("", response_model=List[schemas.SessionListingOut])
def list_sessions(
    status: Optional[str] = Query(None, description="Filter by 'open' or 'requested'"),
    days: Optional[List[int]] = Query(None, description="Filter to listings on any of these days (0=Monday...6=Sunday)"),
    max_lessons_per_week: Optional[int] = Query(None, description="Only show listings needing at most this many lessons/week"),
    sort: Optional[str] = Query(None, description="'newest' | 'oldest' | 'nearest' | 'farthest'"),
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    query = db.query(models.SessionListing)
    if status == "requested":
        query = query.filter(
            models.SessionListing.status == "requested",
            models.SessionListing.requested_by_id == instructor.id,
        )
    elif status:
        query = query.filter(models.SessionListing.status == status)

    if days:
        query = query.filter(models.SessionListing.day_of_week.in_(days))
    if max_lessons_per_week is not None:
        query = query.filter(or_(
            models.SessionListing.lessons_per_week.is_(None),
            models.SessionListing.lessons_per_week <= max_lessons_per_week,
        ))

    listings = query.all()

    if sort in ("nearest", "farthest") and instructor.latitude is not None and instructor.longitude is not None:
        # Listings with no city set have no computable distance — they
        # sort last regardless of direction, rather than landing first
        # under "farthest" just because "unknown" looks like "infinity".
        known = [l for l in listings if l.latitude is not None and l.longitude is not None]
        unknown = [l for l in listings if l.latitude is None or l.longitude is None]
        known.sort(
            key=lambda l: geo.haversine_distance(instructor.latitude, instructor.longitude, l.latitude, l.longitude),
            reverse=(sort == "farthest"),
        )
        listings = known + unknown
    elif sort == "oldest":
        listings.sort(key=lambda l: l.created_at or datetime.min)
    else:
        # "newest" or unspecified — default newest-first.
        listings.sort(key=lambda l: l.created_at or datetime.min, reverse=True)

    return listings


@router.post("", response_model=schemas.SessionListingOut, status_code=201)
def create_session(
    payload: schemas.SessionListingCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    data = payload.model_dump()
    city_name = data.pop("city", None)
    session_listing = models.SessionListing(**data)
    _apply_city(session_listing, city_name)
    db.add(session_listing)
    db.commit()
    db.refresh(session_listing)
    return session_listing


@router.put("/{session_id}", response_model=schemas.SessionListingOut)
def update_session(
    session_id: int,
    payload: schemas.SessionListingCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    session_listing = db.query(models.SessionListing).filter(models.SessionListing.id == session_id).first()
    if not session_listing:
        raise HTTPException(status_code=404, detail="Session not found")
    data = payload.model_dump()
    city_name = data.pop("city", None)
    for field, value in data.items():
        setattr(session_listing, field, value)
    _apply_city(session_listing, city_name)
    db.commit()
    db.refresh(session_listing)
    return session_listing


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    session_listing = db.query(models.SessionListing).filter(models.SessionListing.id == session_id).first()
    if not session_listing:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session_listing)
    db.commit()
    return None


@router.put("/{session_id}/request", response_model=schemas.SessionListingOut)
def request_session(
    session_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    session_listing = db.query(models.SessionListing).filter(models.SessionListing.id == session_id).first()
    if not session_listing:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_listing.status != "open":
        raise HTTPException(status_code=400, detail="This session isn't open")
    session_listing.status = "requested"
    session_listing.requested_by_id = instructor.id
    db.commit()
    db.refresh(session_listing)
    return session_listing


@router.put("/{session_id}/withdraw", response_model=schemas.SessionListingOut)
def withdraw_session(
    session_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    session_listing = (
        db.query(models.SessionListing)
        .filter(models.SessionListing.id == session_id, models.SessionListing.requested_by_id == instructor.id)
        .first()
    )
    if not session_listing:
        raise HTTPException(status_code=404, detail="Session not found")
    session_listing.status = "open"
    session_listing.requested_by_id = None
    db.commit()
    db.refresh(session_listing)
    return session_listing
