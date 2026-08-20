# Attune — instructor + customer marketplace

A learning project: one FastAPI + SQLAlchemy backend serving **two**
frontends from one process:

- `frontend/` (served at `/`) — the instructor side: yoga & sound bath
  instructors manage clients, session listings, their profile, and an
  FAQ library.
- `frontend-customer/` (served at `/customer`) — the customer side:
  sign up, choose a specialty and package, pay (simulated), and get
  auto-matched with an instructor.

Both are vanilla HTML/CSS/JS, no build step, no framework.

Full history and rationale for design decisions lives in `README.md`.
Two staged plans for what's not yet built:
- `ROADMAP.md` — production readiness (Postgres, deployment, polish)
- `SCHEDULING-ROADMAP.md` — the next big feature: time-window + nearest-
  instructor matching for a single scheduled lesson, replacing today's
  specialty-only matching for that flow

Check the relevant one before assuming a feature doesn't exist yet.

## Non-negotiable constraints

- **Every `clients` and `sessions` query must be scoped to the logged-in
  instructor.** Look at `backend/app/routers/clients.py` for the pattern
  (`.filter(models.Client.instructor_id == instructor.id)`) and match it
  exactly in any new route. A route that forgets this filter leaks one
  instructor's data to another.
- **Instructor and customer tokens are not interchangeable.** JWTs carry
  a `type` claim (`"instructor"` or `"customer"`, see `app/security.py`),
  and `get_current_instructor` / `get_current_customer` each check it.
  Never build a route that accepts either type unless that's genuinely
  the intent — it almost never is.
- Schema changes go through Alembic, never by editing the database by
  hand or relying on `Base.metadata.create_all` alone:
  ```
  alembic revision --autogenerate -m "describe the change"
  alembic upgrade head
  ```
  Always read the generated migration before running it.
- Pydantic schemas (`app/schemas.py`) stay separate from SQLAlchemy models
  (`app/models.py`) — the API contract and the database shape are allowed
  to diverge on purpose.
- Neither frontend has a build step or a framework. Keep it that way
  unless explicitly asked to add one — deliberate simplicity, not an
  oversight.
- `localStorage` is fine for JWTs in both frontends (`TOKEN_KEY` in each
  `app.js`) — this app is served by its own backend, not a sandboxed
  iframe, so Claude's hosted-artifact `localStorage` restrictions don't
  apply here. The two apps use *different* localStorage keys
  (`attune_token` vs `attune_customer_token`) on purpose, since both run
  under the same origin and would otherwise clobber each other's session.
- When a customer's booking gets matched, `bookings.py` also creates a
  real `Client` row for that instructor. That's intentional — it's what
  makes the new customer show up in the instructor's own "Current
  Clients" list instead of the two apps feeling disconnected. Don't
  "simplify" this away.

## Commands

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python seed.py           # see logins below
uvicorn app.main:app --reload
pytest                    # 75 tests in backend/tests/ — run after any route change
```

Instructor app: http://127.0.0.1:8000
Customer app: http://127.0.0.1:8000/customer
API docs: http://127.0.0.1:8000/docs

Seeded logins (all password `password123`):
- `demo@attune.app` — Maya Solis — yoga + sound bath
- `kai@attune.app` — Kai Bennett — sound bath only
- `priya@attune.app` — Priya Anand — yoga only

(Three different specialty combos on purpose, so matching has real
variety to demonstrate — see `backend/app/routers/bookings.py`.)

VS Code users: `.vscode/launch.json` has debug configs for both running
the server and running the test suite (Run and Debug panel → pick from
the dropdown).

## Known gotchas

- `passlib`'s bcrypt backend breaks against recent `bcrypt` releases —
  `requirements.txt` pins `bcrypt==4.0.1` on purpose. Don't let `pip` drift
  it to latest.
- Starlette's `TestClient` requires the `httpx` package (not `httpx2`, which
  is a separate, unrelated PyPI package that doesn't provide it) —
  `requirements.txt` pins `httpx>=0.27.0`. An earlier version of this file
  said the opposite; that was wrong.
- `backend/tests/conftest.py` sets `DATABASE_URL` to a throwaway SQLite file
  *before* importing anything from `app` — that's what makes the whole app
  (not just a swapped dependency) run against the test database. Don't
  import `app.main` at the top of a test file above that env var being set.
- A `StaticFiles` mount only auto-serves `index.html` at a *trailing-slash*
  path. `app/main.py` has an explicit `@app.get("/customer")` redirect to
  `/customer/` for exactly this reason — if you add a third frontend later,
  it'll need the same treatment or the bare URL will 404.
- Matching in `bookings.py` (the package flow) filters by `specialty` (a
  comma-separated string column — `.contains()`, not an exact match) and
  `active`, then load-balances by current match count. It does **not**
  consider time or location — that's `lesson_requests.py`'s job (the
  scheduled-lesson flow), which additionally requires a
  `has_overlap()` match (`app/matching.py`) and sorts by
  `haversine_distance()` (`app/geo.py`). The two flows are intentionally
  separate matching functions, not a shared one with a time param bolted
  on — see `LessonRequest`'s docstring in `models.py` for why.

## Current status

**Done:** instructor auth/CRUD/profile/FAQs (Phase 0–1 in `ROADMAP.md`),
the full customer app — signup, specialty + package selection, mock
payment, and specialty-based auto-matching with load balancing — and now
the full scheduling feature from `SCHEDULING-ROADMAP.md`: instructor
weekly availability, a fake demo-city location system, and a second
customer request type (`LessonRequest`, alongside the original package
`Booking` flow) that matches on specialty + time-window overlap +
nearest distance, with the same Client-row sync into the matched
instructor's app. 75 passing tests cover all of it.

**Not started:** Postgres/deployment/polish (`ROADMAP.md` Phases 2–4).
