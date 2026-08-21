"""
App entrypoint. Run this with:

    uvicorn app.main:app --reload

...from inside the backend/ folder.

This one process now serves three things:
- the instructor app at              /
- the customer signup/booking app at /customer
- the JSON API at                    /api/...
That's a deliberate choice for a learning project — one deploy, one URL,
no CORS setup needed between the pieces. A larger app would likely split
these into separate services; see README.md's deploy section for how
you'd do that later without changing much backend code.
"""
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from . import geo, models, schemas
from .database import engine, get_db
from .security import get_current_instructor
from .routers import auth, clients, sessions, profile, faqs, customer_auth, bookings, availability, lesson_requests, client_requests

# Creates all tables defined in models.py if they don't exist yet.
# Once you're using Alembic day to day (see backend/alembic/), this
# line becomes mostly a safety net rather than your main tool for
# schema changes.
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Attune API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(sessions.router)
app.include_router(profile.router)
app.include_router(faqs.router)
app.include_router(customer_auth.router)
app.include_router(bookings.router)
app.include_router(availability.router)
app.include_router(lesson_requests.router)
app.include_router(client_requests.router)


@app.get("/api/cities")
def list_cities():
    """Both frontends fetch this instead of hardcoding the demo city list,
    so the dropdown and the backend's DEMO_CITIES never drift apart."""
    return [city["name"] for city in geo.DEMO_CITIES]


@app.get("/api/summary", response_model=schemas.Summary)
def get_summary(
    db: Session = Depends(get_db),
    instructor: models.Instructor = Depends(get_current_instructor),
):
    """Powers the instructor Home screen: greeting, earnings, and a preview of one current client."""
    current_client = (
        db.query(models.Client)
        .filter(models.Client.instructor_id == instructor.id, models.Client.status == "current")
        .first()
    )
    return schemas.Summary(
        greeting_name=instructor.name.split(" ")[0],
        earned_this_week=0,
        current_client_name=current_client.name if current_client else None,
        current_client_initials=current_client.initials if current_client else None,
    )


# --- Serve both frontends ---
# StaticFiles mounts only serve index.html at a *trailing-slash* path
# (/customer/), so the bare path people actually type (/customer) needs
# an explicit redirect — registered before the mount so it's matched first.
@app.get("/customer", include_in_schema=False)
def redirect_to_customer_app():
    return RedirectResponse(url="/customer/")


# Order matters: specific paths are registered before the root catch-all,
# and FastAPI/Starlette matches routes in the order they were added — so
# /api/... (above) and /customer (above) are always matched before the
# "/" mount has a chance to swallow everything.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
app.mount("/customer", StaticFiles(directory=str(BASE_DIR / "frontend-customer"), html=True), name="customer-frontend")
app.mount("/", StaticFiles(directory=str(BASE_DIR / "frontend"), html=True), name="frontend")
