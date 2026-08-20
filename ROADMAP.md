# Attune — remaining build & ship checklist

Where things stand: **Phase 0 and Phase 1 are complete**, and the
customer-facing app (a separate track from this checklist — see below)
is also built and tested. Auth, full CRUD (clients + sessions), profile
editing, and FAQ filtering are built, wired into the frontend, and
verified end to end. So is the full customer flow: signup, specialty +
package selection, mock payment, and specialty-based auto-matching
(with load balancing and a real sync into the matched instructor's
Client list). All of it is covered by a 41-test pytest suite.
`.vscode/launch.json` has debug configs for both running the app and
running the tests.

Phase 2 (production database) is done, and Phase 3 (deploy) is live and
verified — just missing the one item that needs a second real person.
Phase 4 (polish) hasn't been started. Separately, `SCHEDULING-ROADMAP.md`
covers a bigger feature — upgrading matching from specialty-only to
specialty + time-window + nearest-instructor — which is now also done
(see that file).

Check items off as you go — nothing here needs to happen in one sitting.

---

## Phase 0 — Verify what's already built ✅ done

- [x] `cd backend && python3 -m venv venv && source venv/bin/activate`
- [x] `pip install -r requirements.txt`
- [x] `alembic upgrade head`
- [x] `python seed.py` (demo login: `demo@attune.app` / `password123`)
- [x] `uvicorn app.main:app --reload`
- [x] `/docs` loads, login screen loads (not blank)
- [x] Log in — Home shows real data
- [x] Add / edit / delete a client
- [x] Add a session, request it, withdraw it
- [x] Edit profile, confirm it saves and displays
- [x] Toggle Active Profile, refresh, confirm it persisted
- [x] FAQ category chips actually filter
- [x] Log out returns to login screen
- [x] New signup starts with zero clients (data isolation confirmed)
- [x] Fixed all bugs found; re-verified from a totally clean install

---

## Phase 1 — Automated tests ✅ done

- [x] `pip install pytest httpx2` (Starlette's `TestClient` now prefers
      `httpx2` over `httpx` — see `CLAUDE.md` gotchas)
- [x] `backend/tests/conftest.py` — throwaway SQLite test DB, fresh tables
      per test, `client` fixture, `auth_headers` / `second_auth_headers`
      fixtures for isolation testing
- [x] `test_auth.py` — signup, duplicate email, correct/wrong login, `/me`
- [x] `test_clients.py` — CRUD, 404s, cross-instructor isolation
- [x] `test_sessions.py` — CRUD, request/withdraw, isolation, double-request rejected
- [x] `test_profile.py` — get/update, partial updates, active toggle
- [x] `test_faqs.py` — list and category filter
- [x] `pytest -v` — 25/25 passing, verified from a clean install
- [ ] *(optional, still open)* add `pytest-cov` and check coverage

---

## Phase 2 — Production database ✅ done

SQLite's fine for development but its file won't survive most hosts' deploys.

- [x] Pick a free Postgres provider (Render — same database this project's
      other copy already set up; reused rather than provisioning a second one)
- [x] Create a new Postgres database on it
- [x] Copy the connection string it gives you (starts with `postgresql://`)
- [x] `pip install psycopg2-binary` locally (added to `requirements.txt`)
- [x] Create `backend/.env` with `DATABASE_URL=<that connection string>`
- [x] Restart uvicorn — confirmed it's talking to Postgres, not SQLite
- [x] `alembic upgrade head` — applied the customer/booking/specialty and
      scheduling/location migrations on top of the base schema already
      there
- [x] `python seed.py` — reseeded after clearing one stale pre-migration
      instructor row (NULL specialty/city from the schema having moved on)
- [x] Spot-checked directly: all 3 instructors have correct
      specialty/city/availability, and a full lesson-request match
      (Maya Solis, Monday 09:00–09:30, 0 km away) worked end-to-end
      against the live database

---

## Phase 3 — Deploy ✅ mostly done

- [x] Create a GitHub repo and push the project (`venv/` and `*.db` are
      already gitignored) — https://github.com/Jahan-Atkins/Attune-
- [x] Create an account on your chosen host — Render
- [x] Create a new Web Service pointing at the repo, with `backend/` as
      the root directory
- [x] Set the build command: `pip install -r requirements.txt`
- [x] Start command set explicitly: `uvicorn app.main:app --host 0.0.0.0
      --port $PORT` (Procfile auto-detection was unreliable, so this was
      typed directly into Render's Start Command field)
- [x] Add environment variables on the host:
  - [x] `DATABASE_URL` — ended up on a *second* Postgres instance
        (Ohio region) after the first one (Oregon, from Phase 2) hit
        persistent `SSL connection has been closed unexpectedly` errors
        connecting from within Render. Migrated (`alembic stamp head` —
        the app's own `create_all()` safety net had already built the
        tables, so `upgrade` would have failed on "already exists") and
        reseeded this one instead. **Phase 2's `backend/.env` now points
        here too**, not the original Oregon DB.
  - [x] `SECRET_KEY` — generated fresh, not the dev default
- [x] Deploy — succeeded after the database swap above
- [x] Visit the live URL — confirms the login screen loads:
      https://attune-q29q.onrender.com
- [x] Log in with the demo account on the live site
- [x] Create a client on the live site to confirm writes work in
      production (created "Prod Write Test", confirmed it persisted,
      cleaned it back up)
- [ ] Have a friend sign up as a second instructor on the live URL and
      confirm they only see their own data — needs an actual second
      person, can't be done solo

---

## Phase 4 — Polish & harden

- [ ] In `backend/app/main.py`, change `allow_origins=["*"]` to your actual frontend URL
- [ ] Add a loading state on first load (right now the screen is blank for a beat before data arrives)
- [ ] Double check every error message shown to the user reads clearly — not a raw stack trace
- [ ] Add a favicon
- [ ] Test on a real phone browser, not just desktop — check tap targets and modal scrolling
- [ ] Confirm HTTPS is active on your deployed URL (most hosts do this automatically — check for the padlock)
- [ ] *(optional)* Add a custom domain
- [ ] *(optional)* Set up free uptime monitoring (e.g. UptimeRobot) so you know if it ever goes down
- [ ] *(optional)* Add basic structured logging so production issues are debuggable after the fact
