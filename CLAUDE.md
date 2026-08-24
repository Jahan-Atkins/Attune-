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
- **Login and forgot-password are rate-limited** (`app/rate_limit.py`) —
  5 attempts per 15 minutes, keyed by `(scope, client IP, identifier)` in
  a plain in-process dict, deliberately not Redis (this app runs as a
  single process — see `LAUNCH-ROADMAP.md`). If you add another
  brute-forceable endpoint, wire it through `check_rate_limit()` /
  `record_failed_attempt()` / `reset_attempts()` the same way the three
  login routes and two forgot-password routes already do — don't build a
  second rate-limiting mechanism. Tests share this state across a whole
  pytest run since it's a module-level dict, not the database — see
  `conftest.py`'s `fresh_rate_limits` fixture, which must stay autouse.
- **Password reset tokens are single-use and stored hashed, never raw**
  (`models.PasswordResetToken`, `security.hash_reset_token`). The
  forgot-password routes always return the same response whether or not
  the email exists — never make that response conditional, it's an
  account-enumeration leak. `PasswordResetToken.expires_at` is compared
  with `security.naive_utc_now()` on both write and read — see that
  function's docstring before changing either side to a tz-aware
  `datetime.now(timezone.utc)`, or the comparison can raise.
- **A block is stored one-directional but enforced as symmetric.**
  `models.Block` only records `blocker` → `blocked`, but
  `routers/blocks.py`'s `is_blocked()` checks both directions and is the
  one function every future-match code path calls: `client_requests.py`'s
  visibility checks and the "Book Again" `_validate_preferred_instructor`
  in both `bookings.py` and `lesson_requests.py`. If you add another path
  that can create a match (broadcast or targeted), it needs the same
  `is_blocked()` check — don't let a new code path skip it.
- **Reports are never deleted, unlike `ClientDeletionRequest`.**
  `Report.resolved` just flips to `True` — admin resolve keeps the row so
  a pattern across multiple past reports (repeat reporter, repeat
  offender) stays visible. Don't copy the deletion-request "resolving
  deletes the row" pattern here; it was a deliberate choice for that
  feature specifically, not a house style.
- Reporting/blocking a client is always keyed by that `Client`'s own
  `id`, never a raw `customer_id` — the router resolves `Client.customer_id`
  server-side and 404s if the client isn't the calling instructor's own,
  400s if it has no `customer_id` at all (a hand-added client with no
  real account behind it). Same reasoning as `ClientOut.customer_id`
  being read-only. Don't add a route that accepts a bare `customer_id`
  from an instructor.
- **`Booking` no longer has a create route — `POST /api/customer/bookings`
  is gone.** Every new customer request, package-sized or not, goes
  through `POST /api/customer/lesson-requests` now (it carries its own
  `package`/`sessions_total`, alongside the availability windows —
  there's no more separate "package vs. schedule" fork in the frontend).
  `Booking`'s table, model, and the *entire* confirm/admin/review side of
  it (`client_requests.py`'s Booking handling, `admin.py`'s Booking
  views, `Review.booking_id`) stay live and untouched on purpose — a
  `Booking` can be sitting at `status="pending"` when this shipped, and
  ripping out anything past creation would strand it with no way to ever
  complete. It's self-draining: once every pre-cutover pending `Booking`
  is confirmed or admin-cancelled, that code just stops firing. Don't
  "clean this up" by deleting it, and don't resurrect a `POST` route on
  `bookings.py` — new code belongs in `lesson_requests.py`.
- **A `LessonRequest` now carries a *set* of candidate availability
  windows** (`LessonRequestAvailabilityWindow`, the
  `availability_windows` relationship), not one `requested_day`/`start`/
  `end` triple — a customer submits several ("Mon 9-11am, Wed 2-4pm..."),
  and `matching.has_overlap_any()` tries each in order against a
  candidate instructor's blocks. Consequently `requested_day`/
  `requested_start_time`/`requested_end_time` are nullable and mean
  something different now: they stay `NULL` while pending (there's no
  single "the" window until one specific instructor confirms one) and
  only get set at match time, to whichever window actually matched. Any
  code reading these three fields must handle `None` — see
  `frontend-customer/app.js`'s `renderMatch()` and
  `frontend-admin/app.js`'s `requestRowHTML()` for the pattern. A row
  created directly as `"matched"` (a `RecurringSeries` occurrence, or a
  `schedule_next_session` row) still sets them immediately, same as before.
- **A multi-session package schedules one session at a time, not all at
  once.** `session_number=1` (the "root") is the only row that goes
  through the normal broadcast/confirm lifecycle; sessions 2..N are
  created later via `POST /api/customer/lesson-requests/{id}/schedule-next`,
  directly as `"matched"`, `amount_paid=0` (the whole package was already
  charged on the root), against the *already-fixed* instructor's own
  availability — no re-broadcast, no repayment. `package_request_id`
  points a child session back at its root; `LessonRequest.sessions_scheduled`
  (computed, not stored) counts how many are matched so far. Because of
  this, `RecurringSeries` creation now rejects any source with
  `sessions_total != 1` — folding a multi-session package into a
  standing weekly series would use the package's total price as a
  per-lesson price, which is wrong. Don't relax that guard without also
  fixing the price math.
- **Package pricing is duration-scaled, not flat, and the discount grows
  with package size.** A `"single"`/`"pack4"`/`"pack8"`/`"pack12"`/`"pack16"`
  price depends on the chosen lesson length: `lesson_requests.py`'s
  `PACKAGE_DISCOUNT` (derived from `bookings.py`'s legacy `PACKAGE_PRICING`
  at the 30-minute baseline, computed generically for every key via a
  dict comprehension — not hand-listed per package) multiplies
  `DURATION_PRICING[duration]`. `frontend-customer/app.js`'s
  `estimatedPackagePrice()` mirrors this formula client-side so the
  customer sees the real total *before* paying, not just on the match
  screen after submitting — if the backend formula changes, update both.
  The discount curve is 0% for single/pack4, ~5% for pack8, ~8% for
  pack12, ~12% for pack16 — set by choosing `PACKAGE_PRICING`'s `price`
  values (whole-dollar per-session price at the 30-min baseline, rounded
  *before* multiplying by session count, matching how `_price_for()`
  rounds at every other duration), never by hand-editing `PACKAGE_DISCOUNT`
  directly. The actual discount lands a fraction of a point off the
  named target (pack8 is really 4.62%, not exactly 5%) because of that
  whole-dollar rounding — expected, not a bug. To change the discount
  curve, change the `price` numbers in `bookings.py`'s `PACKAGE_PRICING`
  comment/dict, which is the single source of truth both here and on the
  frontend derive from.
- **`ClientRequestOut.request_type` ("package"/"schedule") is not a proxy
  for which underlying model (`Booking` vs `LessonRequest`) a row is —
  use `.source` ("booking"/"lesson_request") for that instead.** Before
  the package+availability merge, every real "schedule" request really
  was a `LessonRequest` and every "package" request really was a
  `Booking`, so `frontend/app.js`'s `clientRequestCardHTML` used
  `request_type === 'schedule'` to pick the confirm route. Once package
  selection became mandatory for every new request, `_lesson_request_out`
  started returning `request_type="package"` for virtually all
  `LessonRequest` rows too — silently routing every "Confirm Match" click
  at a *new* request to the dead `/client-requests/bookings/{id}/confirm`
  route (404, since no `Booking` with that id exists). Caught by manual
  browser testing, not by the test suite — `test_pending_lesson_request_visible_when_overlap_exists`
  in `test_client_requests.py` now asserts `source == "lesson_request"`
  specifically to catch a regression here. If you add another place that
  needs to know "which table does this row's id belong to," use `source`,
  never `request_type`.
- **Both the customer flow and the instructor's own profile use real
  geocoding now; only instructor-created open session listings still
  use the fixed dropdown.** `geo.geocode_address(city, state)` calls
  OpenStreetMap's free Nominatim API to turn whatever city/state someone
  types into real coordinates — the only external network dependency
  anywhere in this app. `routers/lesson_requests.py`'s
  `create_lesson_request` (customer availability step) and
  `routers/profile.py`'s `update_profile` (instructor's own city) both
  call it. `routers/sessions.py`'s open-session-listing city field is the
  one deliberate holdout: still a dropdown over the fixed `DEMO_CITIES`
  list, no geocoding — don't convert that too without being asked, and
  don't assume `geo.CITY_BY_NAME`/`DEMO_CITIES` are dead code just
  because the other two flows stopped using them for their own location.
  - **Geocoding is deliberately city/state-level, not full-street-address-
    level, even though the customer also types a street address.** A real
    test query for `geo.geocode_address` with the *complete* street
    address included (a famous, unambiguous Manhattan address) silently
    returned a same-named street in a small town 240km away — Nominatim's
    free index has patchy house-number-level coverage. City-level
    geocoding doesn't have that failure mode, and this app's matching
    logic only ever needs city-scale precision anyway (haversine distance
    for "nearest instructor," not real delivery routing). The customer's
    street address is still required, still stored
    (`Customer.address_line`), and still shown to a confirming instructor
    — it's just not part of what determines location. Don't feed it into
    the geocoding query without re-solving the accuracy problem above;
    see geo.py's `geocode_address` docstring for the full story.
  - **`geocode_address` caches successful lookups and throttles outbound
    calls to Nominatim's ~1-request/second usage-policy cap** —
    `_geocode_cache` (a plain module-level dict, unbounded but small in
    practice — same "single process, no Redis" reasoning as
    `rate_limit.py`) and `_throttle()`/`_last_call_at` (a global,
    `Lock`-guarded timestamp gate that sleeps rather than rejects, since
    this is a small synchronous part of request creation, not a hot
    path). Only *successful* lookups are cached — a transient network
    hiccup or Nominatim outage must never permanently blacklist a real
    city for the rest of the process's life. Both are exercised directly
    in `tests/test_geo.py`, which deliberately undoes `fake_geocoding`'s
    patch (`monkeypatch.undo()` — safe because both fixtures share the
    same function-scoped `monkeypatch` instance) to test the *real*
    implementation instead of the test double.
  - `Customer` stores what was typed in `address_line`/`city_name`/
    `state_name` (real columns) plus the geocoded `latitude`/`longitude`;
    `Instructor` mirrors this with `city_name`/`state_name` (its
    `address` column predates this and stays purely decorative — never
    geocoded). Both models' `city` stays a *computed property*, not a
    column — it combines `city_name`+`state_name` for display, but falls
    back to the old `geo.city_name_for_coords()` reverse lookup for a
    row that predates this change and has no `city_name`/`state_name` set
    (a customer from the legacy pre-cutover `Booking` flow, or any
    instructor seeded/created before their profile went through the new
    geocoded update path — `seed.py`'s demo instructors are exactly this
    case, and rely on the fallback to still show a city). Don't collapse
    that fallback away on either model —
    `test_pending_booking_visible_to_matching_instructor` depends on it
    for `Customer`.
  - `tests/conftest.py`'s `fake_geocoding` fixture (autouse) monkeypatches
    `geo.geocode_address` for the entire suite, resolving `"city, state"`
    against the same `CITY_BY_NAME` coordinates the old dropdown used —
    so every existing distance-based assertion keeps working unchanged,
    and the suite never makes a real network call (slow, flaky, and
    Nominatim's usage policy caps unauthenticated use at ~1 req/second —
    a real call per test would risk tripping that). If you add a test
    that needs geocoding to fail, use a city/state pair that isn't one of
    the six `DEMO_CITIES` names. `conftest.py`'s `set_instructor_city`
    helper takes a `"City, ST"` string and splits it into
    `city_name`/`state_name` internally — its call sites didn't need to
    change when the profile endpoint's payload shape did.
  - A failed/unresolvable geocode is a 400 ("Couldn't find that city.
    Please check it and try again."), not a crash or a silent fallback —
    keep it that way; don't guess coordinates for a city Nominatim
    couldn't find. On the instructor profile, `city_name`/`state_name`
    must be sent together or not at all (`routers/profile.py` 400s on a
    half-filled pair) — there's no way to geocode just one.
- **A `LessonRequest` also carries an optional `lessons_per_week`** — a
  stated preference, not an enforced constraint, same unvalidated-integer
  role `Client.lessons_per_week`/`SessionListing.lessons_per_week` already
  play elsewhere in this app. It's set at request-creation time, copied
  onto the new `Client` at confirm time (`_create_client_from_lesson_request`),
  and never checked against anything — don't add scheduling logic that
  enforces it without an explicit ask.
- **The customer wizard order is specialty -> availability -> package ->
  payment** — availability (duration + day/window picks + lessons-per-week)
  comes *before* package on purpose, so the package screen can show real
  duration-scaled prices (`loadPackages()` calls `estimatedPackagePrice()`
  with the already-chosen `selectedDuration`) instead of a 30-min baseline
  placeholder. `selectSpecialty()`/`rebookRequest()` now call
  `initAvailabilityStep()` and go to `screen-availability`;
  `submitAvailabilitySelection()` (the availability step's "Continue")
  computes the windows and goes to `screen-package`; `selectPackage()`
  builds the payment summary and goes to `screen-payment`. If you reorder
  steps again, update all three of those, the `step-label`s, and every
  screen's `back-link` target in `index.html` together — they're not
  driven by one shared source of truth.
- **The availability day/window pickers (main screen and the "Schedule
  Next Session" mini-picker) have no separate "add" step or confirmation
  chip list** — clicking a day or window button toggles its own highlight
  directly, and that highlighted state *is* the selection; there's nothing
  else to look at. The actual submitted windows are computed once, at
  submit time, as the full cross product of every currently-highlighted
  day × every currently-highlighted window (`submitAvailabilitySelection()`
  / `submitScheduleNext()`). This used to be a two-phase stage-then-"+ Add
  N Windows"-then-chip-list flow; it was simplified because the chips read
  as "little popups" cluttering the screen. Don't reintroduce a staging
  Set or an Add button here — if the cross-product-of-everything-highlighted
  semantics ever needs to support multiple independent batches (e.g. "Mon
  mornings" and "Fri evenings" without also implying "Mon evenings"), that's
  a deliberate redesign, not a bug fix. `TIME_WINDOWS`
  (`frontend-customer/app.js`) is eight 2-hour windows spanning 6am-10pm —
  if you change the windows, update it in one place only; the mini-picker
  maps over the same constant, it doesn't have its own copy.

## Commands

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python seed.py           # see logins below
python create_admin.py   # optional — prompts for name/email/password, no default account
uvicorn app.main:app --reload
pytest                    # 240 tests in backend/tests/ — run after any route change
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

- **Nominatim geocoding is a real network call with no retry and an
  8-second timeout** (`geo.geocode_address()`) — if it's slow, rate-limited,
  or unreachable, the caller (`create_lesson_request` for a customer,
  `update_profile` for an instructor) returns the same 400 as a genuinely
  unresolvable city ("Couldn't find that city..."). There's no way from
  that response alone to tell "bad city name" apart from "Nominatim had a
  bad moment" — if someone reports this happening on a city that
  obviously exists, that's the first thing to suspect, not a bug in the
  parsing. A repeat lookup for the *same* city/state is cached
  (`_geocode_cache`) and won't re-hit the network or the timeout at all —
  only a genuinely new query can fail this way.

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

**Done:** instructor auth/CRUD/profile/FAQs, a unified customer request
flow (specialty -> multiple availability windows (multi-select day/time
pickers, 2-hour windows spanning 6am-10pm, direct toggle-highlight, no
add step or chip list) + an optional lessons-per-week preference ->
package (shown at real duration-scaled prices, since duration's already
picked by then) -> payment, one model — `LessonRequest` —
going through a pending -> broadcast -> instructor-confirms lifecycle,
not auto-matching; the old separate "package" vs. "schedule" fork and
its `Booking`-create path are retired, see the non-negotiables above),
multi-session packages scheduled one session at a time after the first
match (including a "Schedule Next Session" mini-picker with the same
multi-select behavior as the main flow), instructor weekly availability
+ a travel-distance preference, real address geocoding (OpenStreetMap
Nominatim, cached and rate-throttled) for both the customer flow and the
instructor's own profile city, alongside the still-fake demo-city
dropdown open session listings use, five package tiers (single/pack4/
pack8/pack12/pack16, a growing per-session discount from 0% up to ~12%
at pack16) with duration- and package-scaled pricing, a Client
Requests map (Leaflet via CDN), Postgres + deployment (Render, live), a
PWA (manifest + service worker) for both the instructor and customer
frontends, Filter/Sort on Open Sessions, a full Client Details page
(location, recurring availability, itemized lesson list), and all seven
parts of `PLATFORM-EXPANSION-ROADMAP.md`: contact info exchange, booking
history, reviews & ratings, rebooking the same instructor, recurring
weekly bookings, email notifications, and a full admin side
(`frontend-admin/`, suspension, force-cancel, FAQ CRUD, metrics), a
client-deletion approval workflow (instructor requests, admin
approves/denies), and three launch-readiness items: rate limiting on
login/forgot-password, self-serve password reset for instructors and
customers, and a reporting/blocking mechanism between matched
instructors and customers. 240 passing tests cover all of it. See
`SCHEDULING-ROADMAP.md`,
`REQUEST-CONFIRM-ROADMAP.md`, `CLIENT-DETAILS-ROADMAP.md`, and
`PLATFORM-EXPANSION-ROADMAP.md` for how each piece got built, and
`ROADMAP.md` for the deploy history.

**Not started:** `ROADMAP.md` Phase 4 (polish — CORS origin lock-down,
loading states, favicon, mobile testing), one manual verification step
(a second real person signing up to confirm data isolation live), and
the items `PLATFORM-EXPANSION-ROADMAP.md` Part 7 explicitly called out
of scope (2FA for admin accounts, an audit log of admin actions,
admin-initiated password resets).

**Production migration pending:** production Postgres on Render is at
`a40d49d2c976` (the package+availability merge) — fully caught up except
for the newest local migration, `0c48e670ce65` (adds
`lesson_requests.lessons_per_week`, a single nullable column with no new
table, so this one deploy won't hit the create_all()-vs-migration race
described above).
