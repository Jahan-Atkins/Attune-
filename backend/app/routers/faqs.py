"""
/api/faqs — read-only content for the Learn screen. Requires login
just like everything else here, mostly for consistency; there's no
per-instructor data involved.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models, schemas
from ..database import get_db
from ..security import get_current_instructor

router = APIRouter(prefix="/api/faqs", tags=["faqs"])


@router.get("", response_model=List[schemas.FAQOut])
def list_faqs(
    category: Optional[str] = Query(None, description="'app use', 'payments', or 'cancellations'"),
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    query = db.query(models.FAQ)
    if category and category != "all":
        query = query.filter(models.FAQ.category == category)
    return query.all()
