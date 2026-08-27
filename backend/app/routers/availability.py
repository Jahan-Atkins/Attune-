"""
Everything under /api/availability. Every route requires a logged-in
instructor and only ever reads or writes that instructor's own blocks —
same ownership pattern as clients.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/availability", tags=["availability"])


@router.get("", response_model=List[schemas.AvailabilityBlockOut])
def list_availability(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    return (
        db.query(models.AvailabilityBlock)
        .filter(models.AvailabilityBlock.instructor_id == instructor.id)
        .order_by(models.AvailabilityBlock.day_of_week, models.AvailabilityBlock.start_time)
        .all()
    )


@router.post("", response_model=schemas.AvailabilityBlockOut, status_code=201)
def create_availability(
    payload: schemas.AvailabilityBlockCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    if payload.start_time >= payload.end_time:
        raise HTTPException(status_code=400, detail="start_time must be before end_time.")

    existing = (
        db.query(models.AvailabilityBlock)
        .filter(
            models.AvailabilityBlock.instructor_id == instructor.id,
            models.AvailabilityBlock.day_of_week == payload.day_of_week,
        )
        .all()
    )
    for block in existing:
        if payload.start_time < block.end_time and block.start_time < payload.end_time:
            raise HTTPException(status_code=400, detail="This overlaps an existing availability block.")

    block = models.AvailabilityBlock(
        instructor_id=instructor.id,
        day_of_week=payload.day_of_week,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.delete("/{block_id}", status_code=204)
def delete_availability(
    block_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    block = (
        db.query(models.AvailabilityBlock)
        .filter(models.AvailabilityBlock.id == block_id, models.AvailabilityBlock.instructor_id == instructor.id)
        .first()
    )
    if not block:
        raise HTTPException(status_code=404, detail="Availability block not found")
    db.delete(block)
    db.commit()
