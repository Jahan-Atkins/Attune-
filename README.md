# Attune — Instructor + Customer Marketplace

A gig-work marketplace concept for yoga & sound bath instructors, built as a
learning project: one FastAPI backend with real auth and a database,
serving **two** frontends — an instructor app (sessions, clients, profile,
resource library) and a customer app (sign up, pick a specialty and
package, pay, get matched with an instructor).

```
attune-app/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app: routers + both frontends, one process
│   │   ├── database.py      # SQLAlchemy engine/session setup (SQLite)
│   │   ├── models.py        # Instructor, Client, SessionListing, FAQ, Customer, Booking
│   │   ├── schemas.py       # Pydantic request/response shapes
│   │   ├── security.py      # Password hashing, JWTs, get_current_instructor / get_current_customer
│   │   └── routers/
│   │       ├── auth.py           # /api/auth — instructor signup, login, me
│   │       ├── clients.py        # /api/clients — full CRUD, scoped to the logged-in instructor
│   │       ├── sessions.py       # /api/sessions — CRUD + request/withdraw
│   │       ├── profile.py        # /api/profile — get/update your own profile (incl. specialty)
│   │       ├── faqs.py           # /api/faqs — Learn screen content
│   │       ├── customer_auth.py  # /api/customer/auth — customer signup, login, me
│   │       └── bookings.py       # /api/customer/bookings — packages, mock payment, matching
│   ├── alembic/              # Database migrations (see Phase 2 below)
│   ├── tests/                # pytest suite — 41 tests: auth, CRUD, isolation, matching
│   ├── pytest.ini
│   ├── seed.py                # Demo data + 3 instructor logins with different specialties
│   ├── requirements.txt
│   ├── .env.example
│   └── Procfile               # for deployment
├── frontend/                  # instructor app — served at /
│   ├── index.html             # login screen, reusable modal, 5-tab nav
│   ├── style.css
│   └── app.js                 # auth, fetch() calls, all CRUD form logic
├── frontend-customer/         # customer app — served at /customer
│   ├── index.html             # landing → auth → specialty → package → payment → match
│   ├── style.css
│   └── app.js
├── .vscode/launch.json        # debug configs for the server and the test suite
├── CLAUDE.md                  # project brief Claude Code reads automatically
├── ROADMAP.md                 # production-readiness checklist (Postgres, deploy, polish)
├── SCHEDULING-ROADMAP.md       # next feature: time-window + nearest-instructor matching
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
  sign up as a new customer, pick a specialty and package, and get matched.
  Watch the matched instructor's Clients list in the instructor app — the
  new customer shows up there too (see "How the pieces connect" below).

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

The two apps are more than visually related: when a customer's booking
gets matched (`app/routers/bookings.py`), the backend also creates a real
`Client` row for that instructor — so the new customer immediately shows
up in the matched instructor's own "Current Clients" list. One booking,
one write to each side, no separate sync step.

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

There's a real pytest suite in `backend/tests/` — 41 tests covering
instructor auth, full CRUD on clients and sessions, the request/withdraw
flow, profile updates, FAQ filtering, customer auth, package pricing, the
mock-payment format checks, specialty-based matching (including that it
never matches the wrong specialty, skips inactive instructors, and load-
balances across ties), and — importantly — that one instructor genuinely
can't see another instructor's data, and that instructor/customer tokens
can't be used on each other's routes.

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
specialty (which the matching engine actually reads), and Active Profile
persists. The customer app's full flow works end to end: sign up, pick a
specialty and package, "pay" (simulated), get matched with a real
instructor, and that match creates a real Client row on the instructor's
side. A 41-test suite covers all of it.

**Good next steps, roughly in order of difficulty:**
1. Wire up "Contact us" on the instructor Learn screen to actually send a
   message somewhere.
2. Add password reset (forgot-password email flow) for both account types.
3. Build the schedule + nearest-instructor matching upgrade — see
   `SCHEDULING-ROADMAP.md` for the full, granular plan.
4. Replace SQLite with Postgres for production (see below).
5. Add pagination once client/session/customer lists get long.
6. Swap the mock payment for real Stripe test-mode integration.

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
3. Deploy `backend/` as a web service. A `Procfile` is already included
   (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`), which Render,
   Railway, and Heroku-style platforms pick up automatically.
4. Run `alembic upgrade head` once against the production database (most
   hosts let you run a one-off command, or you can point your local
   `DATABASE_URL` at it temporarily and run it from your machine).
5. Because FastAPI is already serving both `frontend/` and
   `frontend-customer/` itself, that's the whole deploy — one service, two
   apps, one URL. (If you'd rather host a frontend separately on something
   like Netlify or Vercel, change `API_BASE`/`TOKEN_KEY` usage in that
   app's `app.js` to point at your backend's full URL, and tighten the
   CORS middleware in `main.py` to that specific origin instead of `"*"`.)

