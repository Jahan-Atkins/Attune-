# Attune — Instructor + Customer Marketplace

A gig-work marketplace concept for yoga & sound bath instructors, built as a
learning project: one FastAPI backend with real auth and a database,
serving **two** frontends — an instructor app (sessions, clients, profile,
resource library) and a customer app (sign up, request a package or a
scheduled lesson, and get matched once an instructor confirms).

## Live demo

- **Instructor app:** https://attune-q29q.onrender.com — log in with
  `demo@attune.app` / `password123` (or `kai@attune.app` / `priya@attune.app`,
  same password)
- **Customer app:** https://attune-q29q.onrender.com/customer — click
  "Get Started" to sign up and send a request (see "How the pieces
  connect" below for why that isn't instant)
- **API docs:** https://attune-q29q.onrender.com/docs

(The URLs later in this README under "Run it" are `localhost` ones for
running the project on your own machine — they only work while you have
the server running locally, not as links to a hosted copy.)

```
attune-app/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app: routers + both frontends, one process
│   │   ├── database.py      # SQLAlchemy engine/session setup (SQLite locally, Postgres in prod)
│   │   ├── models.py        # Instructor, Client, SessionListing, FAQ, Customer, Booking, LessonRequest, AvailabilityBlock
│   │   ├── schemas.py       # Pydantic request/response shapes
│   │   ├── security.py      # Password hashing, JWTs, get_current_instructor / get_current_customer
│   │   ├── geo.py           # demo city list + haversine distance
│   │   ├── matching.py      # pure functions: time-overlap check, travel-distance check
│   │   └── routers/
│   │       ├── auth.py             # /api/auth — instructor signup, login, me
│   │       ├── clients.py          # /api/clients — full CRUD, scoped to the logged-in instructor
│   │       ├── sessions.py         # /api/sessions — CRUD + request/withdraw (gig listings, unrelated to customer matching)
│   │       ├── profile.py          # /api/profile — get/update your own profile (specialty, city, travel distance)
│   │       ├── availability.py     # /api/availability — instructor's weekly bookable windows
│   │       ├── faqs.py             # /api/faqs — Learn screen content
│   │       ├── customer_auth.py    # /api/customer/auth — customer signup, login, me
│   │       ├── bookings.py         # /api/customer/bookings — package requests (pending, not matched)
│   │       ├── lesson_requests.py  # /api/customer/lesson-requests — scheduled-lesson requests (pending, not matched)
│   │       └── client_requests.py  # /api/client-requests — instructor-facing: browse + confirm pending requests
│   ├── alembic/              # Database migrations (see Phase 2 below)
│   ├── tests/                # pytest suite — 94 tests: auth, CRUD, isolation, scheduling, request/confirm flow
│   ├── pytest.ini
│   ├── seed.py                # Demo data + 3 instructor logins with different specialties/cities/availability
│   ├── requirements.txt
│   ├── .env.example
│   └── Procfile               # for deployment
├── frontend/                  # instructor app — served at /
│   ├── index.html             # login screen, reusable modal, 6-tab nav, Leaflet map (CDN)
│   ├── style.css
│   └── app.js                 # auth, fetch() calls, all CRUD form logic
├── frontend-customer/         # customer app — served at /customer
│   ├── index.html             # landing → auth → specialty → package-or-schedule → request sent
│   ├── style.css
│   └── app.js
├── .vscode/launch.json        # debug configs for the server and the test suite
├── CLAUDE.md                  # project brief Claude Code reads automatically
├── ROADMAP.md                 # production-readiness checklist (Postgres, deploy, polish)
├── SCHEDULING-ROADMAP.md       # done — time-window + nearest-instructor matching for scheduled lessons
├── REQUEST-CONFIRM-ROADMAP.md  # done — pending/broadcast/confirm model, travel distance, variable duration, map
└── README.md
```

## 1. Open it in VS Code

Unzip the project and open the **attune-app** folder (not a subfolder) in
VS Code: `File → Open Folder…`. Install the **Python** extension if you
don't already have it.

## 2. Set up the backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

VS Code may prompt "Select a Python Interpreter" — choose the one inside
`backend/venv`.

## 3. Create the database and seed some demo data

```bash
alembic upgrade head
python seed.py
```

`alembic upgrade head` creates the tables (see "Migrations" below for why
this is better than the old `create_all` approach). `seed.py` adds three
ready-to-use instructor logins with different specialties (so the customer
app's matching has real variety to demonstrate), two demo clients, and
some FAQ content:

```
demo@attune.app  / password123   (Maya Solis — yoga + sound bath)
kai@attune.app   / password123   (Kai Bennett — sound bath only)
priya@attune.app / password123   (Priya Anand — yoga only)
```

## 4. Run it

```bash
uvicorn app.main:app --reload
```

- **Instructor app:** http://127.0.0.1:8000 — log in with any of the three
  accounts above.
- **Customer app:** http://127.0.0.1:8000/customer — click "Get Started" to
  sign up, then choose a package or schedule a specific lesson. Either way
  this sends a *request*, not an instant match — nothing is charged yet.
  Log in as one of the instructor accounts above, go to Sessions → Client
  Requests, and confirm it. Only then does the card "charge" and the
  customer show up in that instructor's Clients list (see "How the pieces
  connect" below).

Also open **http://127.0.0.1:8000/docs** for FastAPI's interactive API
explorer. There are two separate "Authorize" flows there now — one for
instructor tokens, one for customer tokens — matching the two `/api/auth`
and `/api/customer/auth` namespaces.

## How the pieces connect

Each frontend stores its own JWT in `localStorage` under its own key
(`attune_token` for the instructor app, `attune_customer_token` for the
customer app — see each `app.js`) and attaches it to every request as an
`Authorization: Bearer <token>` header via an `apiFetch()` wrapper. On the
backend, a route declaring `instructor: Instructor =
Depends(get_current_instructor)` or `customer: Customer =
Depends(get_current_customer)` (see `app/security.py`) automatically
requires the matching token type — a customer's token is cryptographically
rejected on instructor routes and vice versa, not just conventionally kept
apart.

The two apps are more than visually related: a customer's package or
scheduled-lesson request starts out `"pending"`, visible to every
instructor it matches on specialty (and, for scheduled lessons, an
actual time overlap) within their own travel-distance preference — see
`app/routers/client_requests.py`. Nothing is assigned or charged until
an instructor confirms it; confirming is what creates a real `Client`
row for that instructor, so the new customer immediately shows up in
their "Current Clients" list. Full rationale in
`REQUEST-CONFIRM-ROADMAP.md`.

## Migrations (Alembic)

Early versions of this project used `Base.metadata.create_all()` to build
the database, which only works for *creating* tables — it can't safely
change a table that already has data in it. Alembic tracks schema changes
as versioned scripts instead. After changing a model in `models.py`, the
workflow is:

```bash
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

Always read the generated migration in `alembic/versions/` before running
it — autogenerate is good but not perfect, especially with column renames.

## Testing

There's a real pytest suite in `backend/tests/` — 94 tests covering
instructor auth, full CRUD on clients and sessions, the request/withdraw
flow, profile updates, FAQ filtering, customer auth, package pricing, the
mock-payment format checks, instructor availability, geo/distance math,
scheduling overlap logic, and the pending -> broadcast -> confirm flow
itself (visibility filtering by specialty/distance/time-overlap, confirm
success, an already-claimed race, a wrong-instructor confirm attempt) —
plus, importantly, that one instructor genuinely can't see another
instructor's data, and that instructor/customer tokens can't be used on
each other's routes.

```bash
cd backend
pytest
```

Each test runs against a throwaway SQLite file (`tests/test.db`, deleted
automatically when the suite finishes) with fresh, empty tables — so tests
never touch your real `attune.db` and never affect each other. Look at
`tests/conftest.py` first; it explains the one trick (setting `DATABASE_URL`
before importing the app) that makes the rest of the suite simple.

Run this any time you change a route — it's much faster than manually
re-clicking through login → add client → edit → delete → etc. every time,
and it'll catch it immediately if a change breaks something that used to work.

## What's already wired up vs. good next exercises

**Working now:** Full login/signup for both instructors and customers.
Full create/edit/delete for clients and sessions from the instructor UI
(not just the API) — try **+ Add Client** and **+ Add Session**. Sessions
have a request/withdraw flow. Instructor profile is editable, including
specialty, city, and a travel-distance preference (all of which the
Client Requests broadcast actually reads), and Active Profile persists.
Session Preferences also manages weekly availability blocks. The
customer app's full flow works end to end for both request types —
package or scheduled lesson, including lesson length and a notes field —
and an instructor confirming one from their Client Requests queue (map
view included) is what charges the mock card and creates a real Client
row. A 94-test suite covers all of it.

**Good next steps, roughly in order of difficulty:**
1. Wire up "Contact us" on the instructor Learn screen to actually send a
   message somewhere.
2. Add password reset (forgot-password email flow) for both account types.
3. Add an explicit "decline" action for an instructor on a Client Request
   they don't want to see again (today they just don't confirm it, and it
   stays visible to everyone else — see `REQUEST-CONFIRM-ROADMAP.md`).
4. Add pagination once client/session/customer lists get long.
5. Swap the mock payment for real Stripe test-mode integration (the
   pending/confirm split was actually designed with this in mind — a real
   gateway's authorize-then-capture maps naturally onto it).
6. `ROADMAP.md` Phase 4 — CORS origin lock-down, loading states, favicon,
   mobile testing pass.

## Deploying it

SQLite is great for learning but its file lives on local disk, which
doesn't survive redeploys on most hosts. The common path:

1. Push this project to a GitHub repo.
2. Create a free Postgres database (Render, Railway, Neon, and Supabase
   all have simple free tiers) and put its connection string in a
   `DATABASE_URL` environment variable on your host — `database.py`
   already reads that variable, so no code changes needed. Also set a real
   `SECRET_KEY` environment variable (see `.env.example`) — don't reuse the
   development default.
3. Deploy `backend/` as a web service (root directory `backend/`, build
   command `pip install -r requirements.txt`). A `Procfile` is included
   (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`) that
   Heroku-style platforms are supposed to pick up automatically — in
   practice, Render's autodetection was unreliable, so just paste that
   same command into the host's "Start Command" field directly rather
   than counting on it.
4. Run `alembic upgrade head` once against the production database (most
   hosts let you run a one-off command, or you can point your local
   `DATABASE_URL` at it temporarily and run it from your machine).
5. Because FastAPI is already serving both `frontend/` and
   `frontend-customer/` itself, that's the whole deploy — one service, two
   apps, one URL. (If you'd rather host a frontend separately on something
   like Netlify or Vercel, change `API_BASE`/`TOKEN_KEY` usage in that
   app's `app.js` to point at your backend's full URL, and tighten the
   CORS middleware in `main.py` to that specific origin instead of `"*"`.)

