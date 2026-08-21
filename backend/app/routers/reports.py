"""
/api/customer/reports and /api/profile/reports — either side of a
matched pair can flag a trust & safety concern about the other. Spans
two resource namespaces the same way reviews.py does (see that module's
docstring) and for the same reason: a report is fundamentally one action
performed by two different account types, not one resource owned by one.

No extra "is this a real match" check beyond ownership: by the time a
customer/instructor has the other's contact info at all, a real match
already happened (see client_requests.py's _notify_match) — there's no
separate "reportable relationship" concept to validate against.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_customer, get_current_instructor

router = APIRouter(tags=["reports"])


@router.post("/api/customer/reports", response_model=schemas.ReportOut, status_code=201)
def report_instructor(
    payload: schemas.ReportInstructorRequest,
    db: Session = Depends(get_db),
    customer: models.Customer = Depends(get_current_customer),
):
    instructor = db.query(models.Instructor).filter(models.Instructor.id == payload.instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found.")

    report = models.Report(
        reporter_type="customer", reporter_id=customer.id,
        reported_type="instructor", reported_id=instructor.id,
        reason=payload.reason, message=payload.message,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return schemas.ReportOut(
        id=report.id, reporter_type="customer", reporter_name=customer.name,
        reported_type="instructor", reported_name=instructor.name,
        reason=report.reason, message=report.message, resolved=report.resolved, created_at=report.created_at,
    )


@router.post("/api/profile/reports", response_model=schemas.ReportOut, status_code=201)
def report_client(
    payload: schemas.ReportClientRequest,
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    # Scoped to this instructor's own clients — the CLAUDE.md rule that
    # applies to every clients query applies here too, since payload.client_id
    # is caller-supplied.
    client = (
        db.query(models.Client)
        .filter(models.Client.id == payload.client_id, models.Client.instructor_id == instructor.id)
        .first()
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    if not client.customer_id:
        raise HTTPException(status_code=400, detail="This client isn't linked to a real customer account, so there's no one to report.")

    report = models.Report(
        reporter_type="instructor", reporter_id=instructor.id,
        reported_type="customer", reported_id=client.customer_id,
        reason=payload.reason, message=payload.message,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return schemas.ReportOut(
        id=report.id, reporter_type="instructor", reporter_name=instructor.name,
        reported_type="customer", reported_name=client.name,
        reason=report.reason, message=report.message, resolved=report.resolved, created_at=report.created_at,
    )
