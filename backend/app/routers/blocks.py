"""
/api/customer/blocks and /api/profile/blocks — either side of a matched
pair can block the other from ever being matched again. Same two-
namespace shape as reports.py (see that module's docstring).

is_blocked() below is the one check every future-match code path needs —
client_requests.py's visibility checks, and the "Book Again" preferred-
instructor validation in bookings.py and lesson_requests.py — imported
directly the same way bookings.py's _mock_charge is already imported
into lesson_requests.py, rather than introducing a new shared-utils
module for one function.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_customer, get_current_instructor

router = APIRouter(tags=["blocks"])


def is_blocked(db: Session, customer_id: int, instructor_id: int) -> bool:
    """True if either side has blocked the other — see models.Block's
    docstring for why a one-directional row is treated as a symmetric stop."""
    return (
        db.query(models.Block)
        .filter(
            or_(
                and_(
                    models.Block.blocker_type == "customer", models.Block.blocker_id == customer_id,
                    models.Block.blocked_type == "instructor", models.Block.blocked_id == instructor_id,
                ),
                and_(
                    models.Block.blocker_type == "instructor", models.Block.blocker_id == instructor_id,
                    models.Block.blocked_type == "customer", models.Block.blocked_id == customer_id,
                ),
            )
        )
        .first()
        is not None
    )


# ---- Customer blocking an instructor ----

@router.post("/api/customer/blocks", response_model=schemas.BlockedInstructorOut, status_code=201)
def block_instructor(
    payload: schemas.BlockInstructorRequest,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    instructor = db.query(models.Instructor).filter(models.Instructor.id == payload.instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found.")

    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_type == "customer", models.Block.blocker_id == customer.id,
            models.Block.blocked_type == "instructor", models.Block.blocked_id == instructor.id,
        )
        .first()
    )
    if not block:
        block = models.Block(
            blocker_type="customer", blocker_id=customer.id,
            blocked_type="instructor", blocked_id=instructor.id,
        )
        db.add(block)
        db.commit()
        db.refresh(block)
    return schemas.BlockedInstructorOut(instructor_id=instructor.id, name=instructor.name, created_at=block.created_at)


@router.delete("/api/customer/blocks/{instructor_id}", status_code=204)
def unblock_instructor(
    instructor_id: int,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_type == "customer", models.Block.blocker_id == customer.id,
            models.Block.blocked_type == "instructor", models.Block.blocked_id == instructor_id,
        )
        .first()
    )
    if block:
        db.delete(block)
        db.commit()
    return None


@router.get("/api/customer/blocks", response_model=List[schemas.BlockedInstructorOut])
def list_blocked_instructors(
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    blocks = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_type == "customer", models.Block.blocker_id == customer.id,
            models.Block.blocked_type == "instructor",
        )
        .all()
    )
    out = []
    for b in blocks:
        instructor = db.query(models.Instructor).filter(models.Instructor.id == b.blocked_id).first()
        if instructor:
            out.append(schemas.BlockedInstructorOut(instructor_id=instructor.id, name=instructor.name, created_at=b.created_at))
    return out


# ---- Instructor blocking a client's underlying customer account ----
# Keyed by Client id, not a raw customer_id — see reports.py's report_client
# for the identical reasoning.

@router.post("/api/profile/blocks", response_model=schemas.BlockedClientOut, status_code=201)
def block_client(
    payload: schemas.BlockClientRequest,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = (
        db.query(models.Client)
        .filter(models.Client.id == payload.client_id, models.Client.instructor_id == instructor.id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    if not client.customer_id:
        raise HTTPException(status_code=400, detail="This client isn't linked to a real customer account, so there's no one to block.")

    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_type == "instructor", models.Block.blocker_id == instructor.id,
            models.Block.blocked_type == "customer", models.Block.blocked_id == client.customer_id,
        )
        .first()
    )
    if not block:
        block = models.Block(
            blocker_type="instructor", blocker_id=instructor.id,
            blocked_type="customer", blocked_id=client.customer_id,
        )
        db.add(block)
        db.commit()
        db.refresh(block)
    return schemas.BlockedClientOut(client_id=client.id, name=client.name, created_at=block.created_at)


@router.delete("/api/profile/blocks/{client_id}", status_code=204)
def unblock_client(
    client_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.instructor_id == instructor.id)
        .first()
    )
    if not client or not client.customer_id:
        return None
    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_type == "instructor", models.Block.blocker_id == instructor.id,
            models.Block.blocked_type == "customer", models.Block.blocked_id == client.customer_id,
        )
        .first()
    )
    if block:
        db.delete(block)
        db.commit()
    return None


@router.get("/api/profile/blocks", response_model=List[schemas.BlockedClientOut])
def list_blocked_clients(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    blocks = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_type == "instructor", models.Block.blocker_id == instructor.id,
            models.Block.blocked_type == "customer",
        )
        .all()
    )
    out = []
    for b in blocks:
        client = (
            db.query(models.Client)
            .filter(models.Client.instructor_id == instructor.id, models.Client.customer_id == b.blocked_id)
            .first()
        )
        if client:
            out.append(schemas.BlockedClientOut(client_id=client.id, name=client.name, created_at=b.created_at))
    return out
