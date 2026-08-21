"""
/api/admin/auth — login only, deliberately. See models.Admin's docstring
for why there's no signup route here: admin accounts only ever come from
running create_admin.py locally, never from an API call.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db
from ..rate_limit import check_rate_limit, record_failed_attempt, reset_attempts

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    check_rate_limit("login-admin", request, form_data.username)
    admin = db.query(models.Admin).filter(models.Admin.email == form_data.username).first()
    if not admin or not security.verify_password(form_data.password, admin.hashed_password):
        record_failed_attempt("login-admin", request, form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    reset_attempts("login-admin", request, form_data.username)
    token = security.create_access_token(admin.id, subject_type="admin")
    return schemas.Token(access_token=token)
