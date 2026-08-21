"""
Everything auth-related lives here so it's easy to find in one place:
- hashing passwords (never store them in plain text)
- issuing and reading JWTs (JSON Web Tokens)
- FastAPI dependencies that any route can request to find out who's
  logged in: get_current_instructor and get_current_customer

There are now three kinds of accounts — Instructor, Customer, and Admin
— sharing one auth scheme. A token carries a "type" claim ("instructor",
"customer", or "admin") so a customer's token can never be used to call
an instructor-only route (or an admin-only one), even though all three
are just JWTs signed with the same SECRET_KEY. Skipping that check would
be a real, exploitable bug — this is a good example of why "is the token
valid" and "is the token allowed *here*" are two different questions.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import get_db

# In a real deployment this MUST be set via an environment variable —
# never commit a real secret key. This fallback only exists so the
# app runs out of the box for learning.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # a week, generous for a learning project

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Separate schemes so /docs shows separate "Authorize" flows per account
# type — purely a docs/UX nicety, all three produce identically-shaped JWTs.
oauth2_scheme_instructor = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_customer = OAuth2PasswordBearer(tokenUrl="/api/customer/auth/login")
oauth2_scheme_admin = OAuth2PasswordBearer(tokenUrl="/api/admin/auth/login")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject_id: int, subject_type: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(subject_id), "type": subject_type, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode(token: str, expected_type: str) -> int:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject_id = payload.get("sub")
        subject_type = payload.get("type")
        if subject_id is None or subject_type != expected_type:
            raise credentials_error
    except JWTError:
        raise credentials_error
    return int(subject_id)


def get_current_instructor(
    token: str = Depends(oauth2_scheme_instructor),
    db: Session = Depends(get_db),
) -> models.Instructor:
    """Any route that adds `instructor: Instructor = Depends(get_current_instructor)`
    to its signature automatically requires a valid *instructor* token."""
    instructor_id = _decode(token, expected_type="instructor")
    instructor = db.query(models.Instructor).filter(models.Instructor.id == instructor_id).first()
    if instructor is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return instructor


def get_current_customer(
    token: str = Depends(oauth2_scheme_customer),
    db: Session = Depends(get_db),
) -> models.Customer:
    """Same idea as get_current_instructor, but for customer-facing routes."""
    customer_id = _decode(token, expected_type="customer")
    customer = db.query(models.Customer).filter(models.Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return customer


def get_current_admin(
    token: str = Depends(oauth2_scheme_admin),
    db: Session = Depends(get_db),
) -> models.Admin:
    """Same idea again, for admin-only routes. There's no public signup
    for this account type — see models.Admin's docstring."""
    admin_id = _decode(token, expected_type="admin")
    admin = db.query(models.Admin).filter(models.Admin.id == admin_id).first()
    if admin is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return admin
