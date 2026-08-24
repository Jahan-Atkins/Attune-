"""
/api/customer/auth — account creation and login for customers. Deliberately
mirrors app/routers/auth.py's structure so the two are easy to compare —
the only real difference is create_access_token gets subject_type="customer",
which is what keeps a customer's token from working on instructor routes.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..email import send_email
from ..google_auth import verify_google_id_token
from ..rate_limit import check_rate_limit, record_failed_attempt, reset_attempts

router = APIRouter(prefix="/api/customer/auth", tags=["customer-auth"])

RESET_TOKEN_EXPIRE_MINUTES = 60


@router.post("/signup", response_model=schemas.Token, status_code=201)
def signup(payload: schemas.CustomerSignupRequest, request: Request, db: Session = Depends(get_db)):
    check_rate_limit("signup-customer", request, "signup")
    record_failed_attempt("signup-customer", request, "signup")
    existing = db.query(models.Customer).filter(models.Customer.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with that email already exists")

    customer = models.Customer(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        hashed_password=security.hash_password(payload.password),
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    token = security.create_access_token(customer.id, subject_type="customer")
    return schemas.Token(access_token=token)


@router.post("/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    check_rate_limit("login-customer", request, form_data.username)
    customer = db.query(models.Customer).filter(models.Customer.email == form_data.username).first()
    if not customer or not security.verify_password(form_data.password, customer.hashed_password):
        record_failed_attempt("login-customer", request, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    reset_attempts("login-customer", request, form_data.username)
    token = security.create_access_token(customer.id, subject_type="customer")
    return schemas.Token(access_token=token)


@router.post("/google", response_model=schemas.Token)
def login_with_google(payload: schemas.GoogleAuthRequest, db: Session = Depends(get_db)):
    """Mirrors auth.py's login_with_google — see that docstring."""
    try:
        identity = verify_google_id_token(payload.id_token)
    except RuntimeError:
        raise HTTPException(status_code=501, detail="Google sign-in isn't configured on this server yet.")
    if not identity:
        raise HTTPException(status_code=401, detail="Could not verify that Google account.")

    customer = db.query(models.Customer).filter(models.Customer.email == identity["email"]).first()
    if not customer:
        customer = models.Customer(name=identity["name"], email=identity["email"], phone="", hashed_password=None)
        db.add(customer)
        db.commit()
        db.refresh(customer)

    token = security.create_access_token(customer.id, subject_type="customer")
    return schemas.Token(access_token=token)


@router.post("/forgot-password")
def forgot_password(payload: schemas.ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Mirrors auth.py's forgot_password — see that docstring for why the
    response never reveals whether the email is on file."""
    check_rate_limit("forgot-password-customer", request, payload.email)
    record_failed_attempt("forgot-password-customer", request, payload.email)
    customer = db.query(models.Customer).filter(models.Customer.email == payload.email).first()
    if customer:
        raw_token = security.generate_reset_token()
        db.add(models.PasswordResetToken(
            account_type="customer",
            account_id=customer.id,
            token_hash=security.hash_reset_token(raw_token),
            expires_at=security.naive_utc_now() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
        ))
        db.commit()
        send_email(
            to=customer.email,
            subject="Reset your Attune password",
            body=f"Use this link within the next hour to reset your password: /customer/?reset_token={raw_token}",
        )
    return {"detail": "If an account exists for that email, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = security.hash_reset_token(payload.token)
    reset_token = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.token_hash == token_hash, models.PasswordResetToken.account_type == "customer")
        .first()
    )
    if not reset_token or reset_token.expires_at < security.naive_utc_now():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    customer = db.query(models.Customer).filter(models.Customer.id == reset_token.account_id).first()
    if not customer:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    customer.hashed_password = security.hash_password(payload.new_password)
    db.delete(reset_token)
    db.commit()
    return {"detail": "Password updated — you can now log in."}
