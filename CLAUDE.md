# Attune — instructor + customer marketplace

A learning project: one FastAPI + SQLAlchemy backend serving **three**
frontends from one process:

- `frontend/` (served at `/`) — the instructor side: yoga & sound bath
  instructors manage clients, session listings, their profile, reviews,
  recurring bookings, and an FAQ library.
- `frontend-customer/` (served at `/customer`) — the customer side:
  sign up, choose a package or a scheduled lesson, and send a request.
  Nothing is charged and no instructor is assigned until one of them
  confirms it (see `REQUEST-CONFIRM-ROADMAP.md`).
- `frontend-admin/` (served at `/admin`) — the platform side: metrics,
  instructor/customer suspension, force-cancelling requests, FAQ CRUD.
  No signup route anywhere for this one — see the Admin section below.

All three are vanilla HTML/CSS/JS, no build step, no framework.

Full history and rationale for design decisions lives in `README.md`.
Staged plans for what's not yet built, or records of what was:
- `ROADMAP.md` — production readiness (Postgres, deployment, polish) —
  Phases 0–3 done, Phase 4 (polish) not started
- `SCHEDULING-ROADMAP.md` — done. Time-window + nearest-instructor
  matching for scheduled lessons.
- `REQUEST-CONFIRM-ROADMAP.md` — done. The pending -> broadcast ->
  instructor-confirms model both booking flows use now, instructor
  travel-distance preference, variable lesson duration, and the Client
  Requests map.
- `CLIENT-DETAILS-ROADMAP.md` — done. Filter/Sort on Open Sessions, and
  a full Client Details page (location, recurring availability,
  itemized lesson list) beyond the original simple client card.
- `PLATFORM-EXPANSION-ROADMAP.md` — all seven parts done: contact info
  exchange in place of in-app messaging, booking/lesson-request history,
  reviews & ratings, rebooking the same instructor, recurring weekly
  bookings, email notifications, and the admin side.

Check the relevant one before assuming a feature doesn't exist yet.

## Non-negotiable constraints

- **Every `clients` and `sessions` query must be scoped to the logged-in
  instructor.** Look at `backend/app/routers/clients.py` for the pattern
  (`.filter(models.Client.instructor_id == instructor.id)`) and match it
  exactly in any new route. A route that forgets this filter leaks one
  instructor's data to another.
- **Instructor, customer, and admin tokens are not interchangeable.**
  JWTs carry a `type` claim (`"instructor"`, `"customer"`, or `"admin"`,
  see `app/security.py`), and `get_current_instructor` /
  `get_current_customer` / `get_current_admin` each check it. Never
  build a route that accepts more than one type unless that's genuinely
  the intent — it almost never is.
- **There is no admin signup route, anywhere, on purpose.** Unlike
  instructor/customer, an `Admin` account is never created by hitting an
  API endpoint — only by running `backend/create_admin.py` locally
  against whichever `DATABASE_URL` you want the account on. Don't add
  one to close a "convenience" gap; that gap is the whole point (closes
  off the obvious attack of someone hitting a hypothetical
  `/api/admin/auth/signup` and handing themselves admin access).
- **`Instructor.active` (self-controlled) and `Instructor`/`Customer`
  `.suspended` (admin-controlled) are different flags — check both.**
  `active` is "I'm choosing not to accept new clients right now";
  `suspended` is a platform action nobody but an admin can toggle. Every
  matching/broadcast query that filters on `active` must also filter on
  `not suspended` (see `bookings.py`, `lesson_requests.py`,
  `client_requests.py`) — don't let a suspended instructor keep matching
  just because a new route forgot the second check.
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
- When an instructor confirms a pending `Booking`/`LessonRequest`,
  `client_requests.py`'s confirm routes also create a real `Client` row
  for that instructor. That's intentional — it's what makes the new
  customer show up in the instructor's own "Current Clients" list
  instead of the two apps feeling disconnected. Don't "simplify" this
  away. (This used to happen at request-creation time, under the old
  auto-match model — it moved here when that model changed. If you're
  reading old code/docs that say `bookings.py` does this, that's stale.)
- **Nothing is charged and no `Client` row exists until an instructor
  confirms.** `Booking`/`LessonRequest` start `status="pending"` with
  `instructor_id=None` and `paid=False`. The confirm routes in
  `client_requests.py` are the *only* place either of those flips —
  don't add matching/assignment logic to the customer-facing create
  routes in `bookings.py`/`lesson_requests.py` again.
- The confirm routes re-check specialty/distance/(overlap) eligibility
  server-side before letting an instructor confirm — never trust that
  whatever a `GET /api/client-requests` response rendered client-side is
  still an accurate or authorized view by the time a confirm request
  arrives. Same reasoning as the instructor-scoping rule above: don't
  let a client's belief about what it's allowed to do stand in for a
  server-side check.
- **An instructor can't delete a `Client` outright.** `DELETE /api/clients/{id}`
  no longer deletes anything — it creates a `ClientDeletionRequest` (or
  returns the existing pending one) and returns 202, not 204. Only an
  admin's approve (`PUT /api/admin/client-deletion-requests/{id}/approve`)
  actually deletes the client (cascading to their lessons); deny just
  clears the request. `Client.deletion_pending` reflects the state to the
  frontend, which shows "Pending" on the Delete button instead of the
  normal label while one exists. Don't reintroduce a direct-delete path
  for instructors — that's the entire point of this workflow.
- No card details are ever persisted, in either flow. `_mock_charge()` in
  `bookings.py` validates format only and returns; nothing about the
  card is written to the database. "Charging" at confirm time is just
  `paid = True`. Don't add card storage to make a future feature easier
  — there's no real gateway behind this, so there's nothing legitimate
  to store it for.
- **No in-app messaging, by explicit design decision.** Once a
  `Booking`/`LessonRequest` is confirmed, each side gets the other's
  email/phone directly (`ClientRequestConfirmedOut`, `InstructorPublicOut`)
  instead of a chat/messaging system. Don't add one — see
  `PLATFORM-EXPANSION-ROADMAP.md`'s intro for the reasoning and tradeoffs.
- A customer's contact info (`ClientRequestConfirmedOut.customer_email`/
  `customer_phone`) is only ever returned by the *confirm* routes in
  `client_requests.py`, never by the pending-list `GET`
  (`ClientRequestOut`) — every instructor whose queue a pending request
  passes through can see the request, but only the one who actually
  confirms it learns who the customer is. Don't add contact fields to
  the base `ClientRequestOut` schema.
- `Instructor.average_rating`/`review_count` (and the analogous fields on
  `InstructorPublicOut`) are computed live via `object_session()` +
  a query, not stored columns — same "compute fresh, never let it drift"
  pattern as the existing `city` property and `ClientRequestOut.distance_km`.
  If you add another aggregate like this, follow the same pattern rather
  than caching it on the model.
- **No cron job or background scheduler, anywhere, on purpose** — this
  project deliberately avoids that infrastructure. `RecurringSeries`
  occurrences are generated lazily, on read: `ensure_upcoming_occurrences()`
  (`app/routers/recurring_series.py`) runs at the top of the read
  endpoints that need to see them and backfills whatever's missing for
  the next few weeks. A series nobody's checked on in months just falls
  behind and catches up next time either side looks — that's accepted,
  not a bug. Don't "fix" this by adding a scheduled task.
- A `LessonRequest` row generated by a `RecurringSeries` is created
  directly as `status="matched"`, `paid=True`, with `recurring_series_id`
  and a real `occurrence_date` ("YYYY-MM-DD") set — it never goes through
  the pending/broadcast/confirm lifecycle every other `LessonRequest`
  does. `occurrence_date` is the *only* place this app stores a real
  calendar date for a lesson; every other `LessonRequest` only ever
  stores a day-of-week.
- Email notifications (`app/email.py`) use plain `print()`, not the
  `logging` module — deliberately. A `logger.info()` version passed
  every test (pytest's `caplog` overrides the level) but was silently
  invisible in the real running app, since nothing here configures
  Python logging and the root logger defaults to WARNING. If you touch
  `send_email()`, keep using `print()` (or fix logging configuration
  project-wide first) — don't reintroduce a notification that looks like
  it works but never actually shows up anywhere.

## Commands

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python seed.py           # see logins below
python create_admin.py   # optional — prompts for name/email/password, no default account
uvicorn app.main:app --reload
pytest                    # 190 tests in backend/tests/ — run after any route change
```

Instructor app: http://127.0.0.1:8000
Customer app: http://127.0.0.1:8000/customer
Admin app: http://127.0.0.1:8000/admin (needs `create_admin.py` run first — no seeded account)
API docs: http://127.0.0.1:8000/docs

Seeded logins (all password `password123`):
- `demo@attune.app` — Maya Solis — yoga + sound bath
- `kai@attune.app` — Kai Bennett — sound bath only
- `priya@attune.app` — Priya Anand — yoga only

(Three different specialty combos, cities, and availability windows on
purpose — Priya also has a 500km travel-distance cap, the other two
don't — so the Client Requests broadcast/filtering has real variety to
demonstrate. See `backend/seed.py`.)

VS Code users: `.vscode/launch.json` has debug configs for both running
the server and running the test suite (Run and Debug panel → pick from
the dropdown).

## Known gotchas

- **`backend/.env` may point at production Postgres, not local SQLite.**
  It gets pointed there deliberately during a deploy (see the Render
  gotcha below — "point your local `DATABASE_URL` at it temporarily and
  run it from your machine"), and it's easy to forget to point it back.
  `database.py`'s `load_dotenv()` reads it automatically, so a plain
  `uvicorn app.main:app --reload` with no explicit `DATABASE_URL` env var
  silently runs against whatever `.env` currently has — this has already
  once created and had to manually clean up a stray row on production
  during local testing. Before any local dev/testing session, check
  `backend/.env`'s current value, or just always override it explicitly:
  `DATABASE_URL="sqlite:///./attune.db" uvicorn app.main:app --reload`.

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
- `bookings.py`/`lesson_requests.py` don't match anyone to anything
  anymore — they only validate the request and mark it `"pending"` (or
  the dead-end `"unmatched"` if literally no active instructor could
  ever take it). All the actual matching — specialty (`.contains()` on
  a comma-separated column), the instructor's own `active` flag and
  `max_travel_distance_km`, and for scheduled lessons a real
  `has_overlap()` check (`app/matching.py`) — lives in
  `client_requests.py`, computed fresh on every `GET`, never
  snapshotted. See `REQUEST-CONFIRM-ROADMAP.md` for the full shape.
- A local dev server (`uvicorn`) caches OS-level filesystem permissions
  for its process lifetime. If macOS revokes and you re-grant Downloads-
  folder access mid-session, any `uvicorn` process already running will
  keep throwing `PermissionError` on static file reads until you restart
  it — the restored permission doesn't apply to an already-running
  process. Restart the server before assuming a code change broke
  something.
- **Deploying a new migration to Render is a two-step race, every time.**
  `main.py`'s `models.Base.metadata.create_all(bind=engine)` runs on
  every app startup as a safety net — and a `git push` triggers Render
  to restart the app *before* you've had a chance to run
  `alembic upgrade head` by hand. `create_all()` only creates tables
  that don't exist yet; it never adds columns to a table that's already
  there. So a migration that both adds a new table *and* adds columns to
  an existing one lands in a half-applied state: `alembic upgrade head`
  then fails with "relation already exists" on the new table, while the
  existing tables are still missing their new columns. Fix: inspect the
  live schema (`sqlalchemy.inspect(engine).get_columns(...)`), manually
  `ALTER TABLE ... ADD COLUMN` whatever `create_all()` skipped, then
  `alembic stamp head` (not `upgrade`) once the schema actually matches
  `models.py`. This has happened on every Render deploy so far — expect
  it again next time, don't be surprised by the error.

## Current status

**Done:** instructor auth/CRUD/profile/FAQs, the full customer app (two
request types — packages and scheduled lessons — both going through a
pending -> broadcast -> instructor-confirms model, not auto-matching),
instructor weekly availability + a travel-distance preference, a fake
demo-city location system, variable lesson duration with tiered
pricing, a Client Requests map (Leaflet via CDN), Postgres + deployment
(Render, live), Filter/Sort on Open Sessions, a full Client Details page
(location, recurring availability, itemized lesson list), and all seven
parts of `PLATFORM-EXPANSION-ROADMAP.md`: contact info exchange, booking
history, reviews & ratings, rebooking the same instructor, recurring
weekly bookings, email notifications, and a full admin side
(`frontend-admin/`, suspension, force-cancel, FAQ CRUD, metrics). 176
passing tests cover all of it. See `SCHEDULING-ROADMAP.md`,
`REQUEST-CONFIRM-ROADMAP.md`, `CLIENT-DETAILS-ROADMAP.md`, and
`PLATFORM-EXPANSION-ROADMAP.md` for how each piece got built, and
`ROADMAP.md` for the deploy history.

**Not started:** `ROADMAP.md` Phase 4 (polish — CORS origin lock-down,
loading states, favicon, mobile testing), one manual verification step
(a second real person signing up to confirm data isolation live), and
the items `PLATFORM-EXPANSION-ROADMAP.md` Part 7 explicitly called out
of scope (2FA for admin accounts, an audit log of admin actions,
admin-initiated password resets).

**Production migration pending:** local SQLite is fully migrated through
`da39efd1e412` (admin role + suspension fields); production Postgres on
Render still needs `61908be0a3e1` (rebooking), `eec36154bc48` (recurring
bookings), and `da39efd1e412` applied — deploying will hit the
create_all()-vs-migration race documented above, same as every prior
deploy.
