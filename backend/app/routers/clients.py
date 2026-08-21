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


@router.post("/{client_id}/lessons", response_model=schemas.ClientLessonOut, status_code=201)
def add_client_lesson(
    client_id: int,
    payload: schemas.ClientLessonCreate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = _get_owned_client(client_id, db, instructor)
    lesson = models.ClientLesson(client_id=client.id, **payload.model_dump())
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def _get_owned_lesson(client: models.Client, lesson_id: int, db: Session) -> models.ClientLesson:
    lesson = (
        db.query(models.ClientLesson)
        .filter(models.ClientLesson.id == lesson_id, models.ClientLesson.client_id == client.id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


@router.delete("/{client_id}/lessons/{lesson_id}", status_code=204)
def delete_client_lesson(
    client_id: int,
    lesson_id: int,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    client = _get_owned_client(client_id, db, instructor)
    lesson = _get_owned_lesson(client, lesson_id, db)
    db.delete(lesson)
    db.commit()
    return None


@router.put("/{client_id}/lessons/{lesson_id}/paid", response_model=schemas.ClientLessonOut)
def set_client_lesson_paid(
    client_id: int,
    lesson_id: int,
    payload: schemas.ClientLessonPaidUpdate,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    """Flips one lesson's paid status. Previously there was no way to
    change this after adding the lesson — the Paid/Unpaid checkbox on
    "+ Add Lesson" set it once and that was permanent."""
    client = _get_owned_client(client_id, db, instructor)
    lesson = _get_owned_lesson(client, lesson_id, db)
    lesson.paid = payload.paid
    db.commit()
    db.refresh(lesson)
    return lesson
