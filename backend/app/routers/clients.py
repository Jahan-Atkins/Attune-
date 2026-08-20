"""
Everything under /api/clients. Every route here requires a logged-in
instructor (via Depends(get_current_instructor)) and only ever reads
or writes that instructor's own clients — that's the `instructor_id`
filter you'll see on every query below.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=List[schemas.ClientOut])
def list_clients(
    status: Optional[str] = Query(None, description="Filter by 'current' or 'past'"),
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    query = db.query(models.Client).filter(models.Client.instructor_id == instructor.id)
    if status:
        query = query.filter(models.Client.status == status)
    return query.all()


def _get_owned_client(client_id: int, db: Session, instructor: models.Instructor) -> models.Client:
    client = (
        db.query(models.Client)
        .filter(models.Client.id == client_id, models.Client.instructor_id == instructor.id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/{client_id}", response_model=schemas.ClientOut)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    return _get_owned_client(client_id, db, instructor)


@router.post("", response_model=schemas.ClientOut, status_code=201)
def create_client(
    payload: schemas.ClientCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = models.Client(**payload.model_dump(), instructor_id=instructor.id)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.put("/{client_id}", response_model=schemas.ClientOut)
def update_client(
    client_id: int,
    payload: schemas.ClientCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = _get_owned_client(client_id, db, instructor)
    for field, value in payload.model_dump().items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = _get_owned_client(client_id, db, instructor)
    db.delete(client)
    db.commit()
    return None
