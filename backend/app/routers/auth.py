"""
/api/auth — account creation and login.

This follows FastAPI's own recommended pattern (OAuth2 "password
flow"): login takes a standard form (not JSON) with username/password
fields, which is why we use OAuth2PasswordRequestForm below. It's also
what makes the "Authorize" button in /docs work out of the box.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.Token, status_code=201)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(models.Instructor).filter(models.Instructor.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    instructor = models.Instructor(
        name=payload.name,
        email=payload.email,
        hashed_password=security.hash_password(payload.password),
    )
    db.add(instructor)
    db.commit()
    db.refresh(instructor)

    token = security.create_access_token(instructor.id, subject_type="instructor")
    return schemas.Token(access_token=token)


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm calls the email field "username" — that's
    # a fixed field name from the OAuth2 spec, not something we chose.
    instructor = db.query(models.Instructor).filter(models.Instructor.email == form_data.username).first()
    if not instructor or not security.verify_password(form_data.password, instructor.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = security.create_access_token(instructor.id, subject_type="instructor")
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.ProfileOut)
def read_current_instructor(instructor: models.Instructor = Depends(security.get_current_instructor)):
    return instructor
