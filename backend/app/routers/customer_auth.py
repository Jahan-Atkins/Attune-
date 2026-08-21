"""
/api/customer/auth — account creation and login for customers. Deliberately
mirrors app/routers/auth.py's structure so the two are easy to compare —
the only real difference is create_access_token gets subject_type="customer",
which is what keeps a customer's token from working on instructor routes.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/customer/auth", tags=["customer-auth"])


@router.post("/signup", response_model=schemas.Token, status_code=201)
def signup(payload: schemas.CustomerSignupRequest, db: Session = Depends(get_db)):
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
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.email == form_data.username).first()
    if not customer or not security.verify_password(form_data.password, customer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = security.create_access_token(customer.id, subject_type="customer")
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.CustomerOut)
def read_current_customer(customer: models.Customer = Depends(security.get_current_customer)):
    return customer
