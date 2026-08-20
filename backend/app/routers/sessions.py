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
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=List[schemas.SessionListingOut])
def list_sessions(
    status: Optional[str] = Query(None, description="Filter by 'open' or 'requested'"),
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
    return query.all()


@router.post("", response_model=schemas.SessionListingOut, status_code=201)
def create_session(
    payload: schemas.SessionListingCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    session_listing = models.SessionListing(**payload.model_dump())
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
    for field, value in payload.model_dump().items():
        setattr(session_listing, field, value)
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
