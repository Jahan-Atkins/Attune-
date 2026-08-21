"""
/api/auth — account creation and login.

This follows FastAPI's own recommended pattern (OAuth2 "password
flow"): login takes a standard form (not JSON) with username/password
fields, which is why we use OAuth2PasswordRequestForm below. It's also
what makes the "Authorize" button in /docs work out of the box.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..email import send_email
from ..rate_limit import check_rate_limit, record_failed_attempt, reset_attempts

router = APIRouter(prefix="/api/auth", tags=["auth"])

RESET_TOKEN_EXPIRE_MINUTES = 60


@router.post("/signup", response_model=schemas.Token, status_code=201)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(models.Instructor).filter(models.Instructor.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    instructor = models.Instructor(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=security.hash_password(payload.password),
    )
    db.add(instructor)
    db.commit()
    db.refresh(instructor)

    token = security.create_access_token(instructor.id, subject_type="instructor")
    return schemas.Token(access_token=token)


@router.post("/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm calls the email field "username" — that's
    # a fixed field name from the OAuth2 spec, not something we chose.
    check_rate_limit("login-instructor", request, form_data.username)
    instructor = db.query(models.Instructor).filter(models.Instructor.email == form_data.username).first()
    if not instructor or not security.verify_password(form_data.password, instructor.hashed_password):
        record_failed_attempt("login-instructor", request, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    reset_attempts("login-instructor", request, form_data.username)
    token = security.create_access_token(instructor.id, subject_type="instructor")
    return schemas.Token(access_token=token)


@router.post("/forgot-password")
def forgot_password(payload: schemas.ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Always returns the same response whether or not the email is on
    file — a different response would let anyone probe which emails have
    an account here. See EMAIL_BACKEND's docstring for how to actually
    see the link in a dev/demo environment (console output)."""
    check_rate_limit("forgot-password-instructor", request, payload.email)
    record_failed_attempt("forgot-password-instructor", request, payload.email)
    instructor = db.query(models.Instructor).filter(models.Instructor.email == payload.email).first()
    if instructor:
        raw_token = security.generate_reset_token()
        db.add(models.PasswordResetToken(
            account_type="instructor",
            account_id=instructor.id,
            token_hash=security.hash_reset_token(raw_token),
            expires_at=security.naive_utc_now() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
        ))
        db.commit()
        send_email(
            to=instructor.email,
            subject="Reset your Attune password",
            body=f"Use this link within the next hour to reset your password: /?reset_token={raw_token}",
        )
    return {"detail": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = security.hash_reset_token(payload.token)
    reset_token = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == token_hash, models.PasswordResetToken.account_type == "instructor")
        .first()
    )
    if not reset_token or reset_token.expires_at < security.naive_utc_now():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    instructor = db.query(models.Instructor).filter(models.Instructor.id == reset_token.account_id).first()
    if not instructor:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    instructor.hashed_password = security.hash_password(payload.new_password)
    db.delete(reset_token)
    db.commit()
    return {"detail": "Password updated — you can now log in."}
