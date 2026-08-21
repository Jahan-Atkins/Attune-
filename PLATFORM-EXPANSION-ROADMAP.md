# Platform expansion — admin, reviews, recurring bookings, rebooking, notifications, contact exchange

**Status: Parts 1-3 ✅ done (contact exchange, history, reviews/ratings).
Parts 4-7 (rebooking, recurring bookings, notifications, admin) not yet
started.**

Planning document only — nothing here is built yet. Written at the same
level of detail as the roadmaps that preceded it (`SCHEDULING-ROADMAP.md`,
`REQUEST-CONFIRM-ROADMAP.md`, `CLIENT-DETAILS-ROADMAP.md`) so it can be
picked up and built the same way those were: one part at a time, migration
reviewed before applying, tests before moving on.

**Explicit decision carried through this whole doc:** no in-app messaging.
Instead, once a `Booking`/`LessonRequest` is confirmed, each side is
handed the other's email and phone number directly. That's simpler to
build and matches what you asked for — the tradeoff (worth knowing, not
necessarily worth blocking on) is that it's also less moderatable than
in-app messaging: once numbers are exchanged, anything that happens next
happens over SMS/phone, outside the platform's visibility. Fine for a
learning project; worth revisiting if this ever handles real disputes at
scale.

## Suggested build order

1. **Contact info exchange** ✅ done — smallest, and Client needs the new
   `email`/`phone` fields regardless of what else gets built
2. **Booking/lesson-request history views** ✅ done — not asked for
   directly, but both Reviews and Rebooking need "show me my past
   matches," which doesn't exist today (the API only ever returns the
   *latest* one)
3. **Reviews & ratings** ✅ done — depends on #2
4. **Rebook the same instructor** — depends on #2, and its
   `preferred_instructor_id` mechanism is reused by #5
5. **Recurring bookings** — depends on #4's targeting mechanism
6. **Notifications** — touches every feature above as a trigger point, so
   building it last means one integration pass instead of five

---

## Part 1 — Contact info exchange (replaces messaging) ✅ done

Built as designed below, with one resolved decision: phone required at
signup (the recommended option). Verified end-to-end in-browser: pending
`ClientRequestOut` never exposes customer contact info, the confirm
response includes it, `Client.email`/`Client.phone` are populated at
confirm time, and the customer's match screen shows the instructor's
contact info. Covered by 5 new tests in `test_client_requests.py`.

### Data model

- `Instructor.phone` — `String, nullable=False`. Required going forward;
  existing seeded instructors need a backfill value in the migration or a
  follow-up `seed.py` update.
- `Customer.phone` — same, `String, nullable=False`.
- `Client.email` / `Client.phone` — new nullable columns. `Client` rows
  are the instructor's permanent record of who they're working with, so
  the customer's contact info should live there too, not just flash by
  once in an API response.

### API

- `SignupRequest` (instructor) and `CustomerSignupRequest` both gain a
  required `phone: str`. Both signup routes (`auth.py`, `customer_auth.py`)
  pass it straight into the new model column.
- Add a light format check — not a real phone-validation library, just
  "digits, spaces, dashes, parens, optionally a leading +, land somewhere
  around 10-15 digits" — mirroring how `_mock_charge()` already does
  format-only validation elsewhere in this app rather than reaching for a
  new dependency.
- `InstructorPublicOut` (already the schema shown to a matched customer)
  gains `email` and `phone`. No new gating logic needed — this schema is
  already only populated once `instructor_id` is set on the
  `Booking`/`LessonRequest`, i.e. already only visible post-match. This
  is a nice case where the existing architecture already does the right
  thing for free.
- `ClientRequestOut` (shown to a *browsing, not-yet-confirmed* instructor)
  deliberately does **not** gain customer contact fields — a customer's
  email/phone shouldn't be visible to every instructor whose queue it
  passes through, only to the one who actually confirms. Add a second,
  richer response only for the moment of confirmation:
  - New schema `ClientRequestConfirmedOut(ClientRequestOut)` adds
    `customer_email` / `customer_phone`.
  - `confirm_booking`/`confirm_lesson_request` in `client_requests.py`
    return this richer schema instead of the plain one.
- `_create_client_from_booking`/`_create_client_from_lesson_request`
  (already in `client_requests.py`) now also copy `customer.email` and
  `customer.phone` onto the new `Client` row, so the contact info is
  visible on the Client Details page going forward, not just in the
  one-time confirm response.

### Frontend

- Both signup forms (`frontend/index.html` instructor signup,
  `frontend-customer/index.html`) add a required Phone field.
- Instructor app: `confirmClientRequest()`'s success path surfaces the
  customer's email/phone (e.g. a modal or inline banner right after
  confirming — "You're matched with Jamie Rivera — jamie@email.com,
  (555) 010-1234"). The Client Details page (`renderClientDetail`) also
  displays it permanently, alongside the existing Location section.
- Customer app: `renderMatch()`'s matched branch adds the instructor's
  email/phone next to the existing bio/certifications.

### Decision to make before building

Phone required at signup (simplest, but raises signup friction and means
existing seeded/live accounts need backfilling) vs. required only before
a first booking/request can be submitted (softer onboarding, more
validation branches). Recommend signup-time — it's one field, and every
account eventually needs one anyway under this design.

---

## Part 2 — Booking/lesson-request history (prerequisite for Parts 3-4) ✅ done

Built as designed below. The customer app's History screen merges both
lists client-side, sorted newest-first by `created_at`. Covered by tests
in `test_bookings.py`/`test_lesson_requests.py` (auth required, full
history returned, isolated between customers).

Not one of the five you asked for, but both Reviews and Rebooking need a
customer to look back at *past* matches, and today the API only ever
returns the single latest `Booking`/`LessonRequest` via `/me`.

### API

- `GET /api/customer/bookings` — list, not singular; supports the same
  shape `ClientOut` list endpoints already use in `clients.py`, scoped to
  `customer.id` the same way clients are scoped to `instructor.id`.
- `GET /api/customer/lesson-requests` — same idea.
- Both ordered newest-first.

### Frontend

- Customer app gains a "My Bookings" or "History" screen (new nav
  affordance — the customer app currently has no persistent nav beyond
  Log In/Log Out, so this needs a small structural addition, e.g. a
  "History" link in the top bar once logged in) listing past matches,
  each showing status, instructor name once matched, and — once Parts 3-4
  exist — "Leave a Review" / "Book Again" actions per past entry.

---

## Part 3 — Reviews & ratings ✅ done

Built as designed below, with the recommended decision: reviewable as
soon as `status == "matched"` (no dependency on `ClientLesson.date`
becoming a real date field). `average_rating`/`review_count` are computed
live via `object_session()` on the `Instructor` model, same pattern as
the existing `city` computed property — nothing is stored or can drift
out of sync. Instructor app gained a "My Reviews" screen and a rating
summary on Profile; customer app's History cards expand inline into a
star-picker + comment form (no modal system exists in that app, so this
avoids building one). Covered by 15 new tests in `test_reviews.py`.

### Data model

- New `Review` model: `id`, `instructor_id` (FK), `customer_id` (FK),
  `booking_id` (nullable FK), `lesson_request_id` (nullable FK), `rating`
  (Integer, 1-5), `comment` (Text, nullable), `created_at`. Exactly one
  of `booking_id`/`lesson_request_id` is set per review — same
  package-vs-schedule duality `client_requests.py` already handles.
- A unique constraint on `(customer_id, booking_id)` and
  `(customer_id, lesson_request_id)` so a customer can't review the same
  match twice.
- **Decision to make:** reviewable as soon as `status == "matched"`, or
  only after the session's actual date has passed? The matched-immediately
  option is simpler and is what's recommended here — this app doesn't
  track "did the session actually happen yet" as a distinct state
  (`ClientLesson.date` is free text, not a real date the backend could
  compare against `now()`), so enforcing "only after it happened" would
  need that to become a real date field first. Worth revisiting once/if
  `ClientLesson.date` becomes structured.

### API

- `POST /api/customer/reviews` — body: `booking_id` or `lesson_request_id`,
  `rating`, `comment`. Validates the customer owns that booking/request
  and it's `status == "matched"`, and that no review already exists for it.
- `GET /api/instructors/{id}/reviews` — public, paginated list (no auth
  required, matches how `InstructorPublicOut` is already semi-public
  info).
- `InstructorPublicOut` gains `average_rating` (nullable float, None if
  zero reviews) and `review_count` — computed at query time
  (`AVG`/`COUNT` over `Review`), not stored, consistent with how this app
  already prefers computed values (e.g. `ClientRequestOut.distance_km`)
  over ones that could drift out of sync.
- Instructor-side: `GET /api/profile/reviews` — the logged-in
  instructor's own reviews, for a "My Reviews" screen.

### Frontend

- Customer app: on each past-matched entry in the new History screen
  (Part 2), a "Leave a Review" button opens a simple star-rating +
  comment form.
- Instructor app: Profile screen shows `average_rating`/`review_count`
  next to the specialty badges; a new "Reviews" list screen (reachable
  from Profile) shows individual reviews.

---

## Part 4 — Rebook the same instructor

The cleanest of the five to build, because it reuses the entire existing
pending/broadcast/confirm machinery rather than needing a parallel path.

### Data model

- `Booking` and `LessonRequest` both gain `preferred_instructor_id`
  (nullable FK to `instructors.id`).

### Matching logic

- In `bookings.py`/`lesson_requests.py`'s create routes: if
  `preferred_instructor_id` is set, validate that instructor is active
  and still offers the specialty (and, for lesson requests, still has an
  overlapping availability block) before accepting the request — if not,
  return a 400 telling the customer to submit a normal (broadcast)
  request instead.
- In `client_requests.py`'s `_instructor_sees_booking`/
  `_instructor_sees_lesson_request`: add one condition — if
  `preferred_instructor_id` is set on the request, it's only visible to
  that instructor, not broadcast to everyone else who'd otherwise match.
  Everything else (distance check, overlap check, confirm flow, payment
  timing) stays identical — a "rebook" is just a `Booking`/`LessonRequest`
  targeted at one instructor instead of broadcast to all of them.

### API

- `BookingCreate`/`LessonRequestCreate` gain an optional
  `preferred_instructor_id: Optional[int] = None`.

### Frontend

- On each past-matched entry in the History screen (Part 2), a "Book
  Again with [Instructor Name]" button. For a package rebooking, this
  pre-selects the same specialty and skips straight to package choice;
  for a lesson-request rebooking, it pre-selects specialty and duration
  and goes straight to picking a new day/time (the old day/time doesn't
  necessarily still work). Both silently include `preferred_instructor_id`
  in the final submit payload — the customer doesn't need to see that
  field, it's implied by which button they tapped.

---

## Part 5 — Recurring bookings

The most architecturally involved of the five. Builds directly on Part
4's targeting mechanism.

### Data model

- New `RecurringSeries` model: `id`, `customer_id` (FK), `instructor_id`
  (FK — already known, no broadcast needed since the relationship already
  exists), `specialty`, `duration_minutes`, `day_of_week`, `start_time`,
  `end_time` (the recurring weekly slot, copied from the
  `LessonRequest` that spawned it), `price_per_lesson` (locked in at
  creation from `DURATION_PRICING`, so a later price-tier change doesn't
  retroactively affect an existing series), `status`
  (`"active"`/`"paused"`/`"cancelled"`), `created_at`.
- `LessonRequest` gains a nullable `recurring_series_id` (FK) — occurrences
  generated from a series are still real `LessonRequest` rows (so
  everything downstream — Client Details' lesson history, confirm-time
  Client sync, reviews — keeps working unmodified), just tagged with
  which series spawned them.

### Generation strategy

No task scheduler/cron dependency — deliberately, to match this app's
"no extra infrastructure" pattern. Instead, a helper function
(`ensure_upcoming_occurrences(db, series, weeks_ahead=4)`) runs at the
top of the relevant list endpoints (the customer's lesson-request history,
and whatever instructor-side schedule view surfaces recurring
commitments) and lazily creates any missing `LessonRequest` occurrences
for the next `weeks_ahead` weeks. Occurrences from an active series skip
the pending/broadcast state entirely — they're created directly as
`status="matched"`, `instructor_id` already set, `paid=True` (mock-charged
immediately, same as everything else pre-Stripe), since the instructor
already committed to the standing slot once.

### API

- `POST /api/customer/recurring-series` — body: the source
  `lesson_request_id` of an already-matched lesson request to base the
  series on. Copies instructor/specialty/day/time/duration/price from it.
- `GET /api/customer/recurring-series` — the customer's own series.
- `PUT /api/customer/recurring-series/{id}/pause`,
  `.../resume`, and a cancel (DELETE) — pausing/cancelling stops future
  occurrence generation but never touches past `LessonRequest` rows that
  already happened.
- `GET /api/recurring-series` (instructor-facing) — the logged-in
  instructor's own active series, read-mostly, with a "stop hosting this"
  cancel action (ends the series the same as the customer cancelling it —
  worth deciding whether an instructor-initiated cancellation should
  notify the customer differently than a customer-initiated one once
  Part 6 notifications exist).

### Frontend

- Customer app: on an already-matched lesson request (in History, or
  right on the match confirmation screen), a "Make this a standing weekly
  booking" button creates the series. A new "My Recurring Bookings"
  screen lists active series with pause/cancel controls.
- Instructor app: the Client Details page gains a small "Recurring: every
  Tuesday 5:00 PM" indicator when a client has an active series, with a
  cancel action there.

---

## Part 6 — Notifications

### Infrastructure

- New `app/email.py` with a single `send_email(to, subject, body)`
  function. Default/local backend just logs the email to the console —
  same "mock now, real gateway later" pattern already used for payments,
  so this is fully testable without a real email provider account. A
  `EMAIL_BACKEND` env var swaps in a real provider (SendGrid/Postmark/SES)
  for production, same shape as `DATABASE_URL` already switching between
  SQLite and Postgres.
- This is also the natural place to finally build the password-reset
  flow already flagged as missing in `LAUNCH-ROADMAP.md` — same
  underlying infrastructure.

### Trigger points

- `client_requests.py`'s confirm routes: email both the customer and
  instructor with match details **and each other's contact info** (Part
  1) — this is the main event this feature exists for.
- `RecurringSeries` created/paused/cancelled (Part 5): email both sides.
- New review received (Part 3): email the instructor.
- Password reset request: email a reset link/code.

### Frontend

None directly — this is a backend-only feature. The one UI implication:
signup and profile-edit forms should make clear that the email address
provided is where these notifications land, since it's now doing double
duty (login identity + notification address).

---

## Testing notes (apply to all six parts)

Following this project's existing convention: pure logic (contact-format
validation, `ensure_upcoming_occurrences`'s date math, average-rating
computation) gets unit tests with no DB; each new route gets integration
tests for the happy path, ownership/isolation (a customer can't review or
rebook through another customer's booking), and the specific new
guardrails each part introduces (no duplicate review, `preferred_instructor_id`
narrows visibility to exactly one instructor, a paused series generates
no new occurrences).

## Migration notes

Six parts, six potential migrations — recommend actually applying them
one at a time as each part is built and tested, not batched into one
giant migration at the end, matching how every prior feature in this
project was migrated. Remember the now-documented Render gotcha in
`CLAUDE.md`: a `git push` triggers a restart (and `create_all()`) before
`alembic upgrade head` gets a chance to run by hand, so expect to
manually patch in whatever columns `create_all()` skipped before
`alembic stamp head`, same as the last two deploys.

---

## Part 7 — Admin side

Broader in kind than Parts 1-6: this isn't a customer/instructor-facing
feature, it's an entirely new role with its own auth, its own frontend,
and real power (suspending accounts, force-cancelling matches). Treated
as its own top-level part rather than folded into the numbering above.

### Data model

- New `Admin` model: `id`, `name`, `email` (unique), `hashed_password`,
  `created_at`. **No public signup route, ever** — unlike Instructor/
  Customer, admin accounts are never created by hitting an API endpoint
  from the outside. They're created by a small script
  (`create_admin.py`, run the same way `seed.py` already is — locally
  against `DATABASE_URL`, whether that's pointed at local SQLite or
  production Postgres) that prompts for name/email/password and inserts
  directly via the ORM. This closes off the obvious attack of someone
  hitting a hypothetical `/api/admin/auth/signup` and handing themselves
  admin access.
- `Instructor` and `Customer` both gain `suspended` (Boolean, default
  False) and `suspension_reason` (nullable Text) — deliberately distinct
  from `Instructor.active`, which is instructor-controlled ("I'm choosing
  not to accept new clients right now"). `suspended` is platform-
  controlled and an instructor/customer can't toggle it themselves; every
  route that currently checks `active` for matching purposes should also
  check `not suspended`.

### Auth

- Third JWT `type` claim: `"admin"`, alongside the existing
  `"instructor"`/`"customer"` split in `security.py`. Same
  `get_current_admin` dependency pattern as the other two — admin tokens
  must be just as cryptographically incompatible with instructor/customer
  routes as those two already are with each other. This is the same
  non-negotiable pattern already documented in `CLAUDE.md` for the
  existing two account types, just extended to three.
- `POST /api/admin/auth/login` only — no signup route, per above.

### API (new router, `admin.py`, prefix `/api/admin`, every route behind `get_current_admin`)

- `GET /api/admin/instructors` — list all, with search/filter (by
  active/suspended status, specialty, city).
- `GET /api/admin/instructors/{id}` — full detail.
- `PUT /api/admin/instructors/{id}/suspend` / `/unsuspend` — body includes
  a reason for suspension (stored in `suspension_reason`).
- `GET /api/admin/customers`, `GET /api/admin/customers/{id}`,
  suspend/unsuspend — same shape.
- `GET /api/admin/bookings` and `GET /api/admin/lesson-requests` — list
  all, filterable by status, with a `PUT .../force-cancel` action (sets
  status to a new `"cancelled_by_admin"` value; once real payments exist
  via Stripe, this is also where a refund would be triggered).
- `GET /api/admin/faqs`, `POST`, `PUT`, `DELETE` — the FAQ CRUD that
  currently only exists via direct edits to `seed.py`.
- `GET /api/admin/metrics` — the numbers `LAUNCH-ROADMAP.md` says to
  watch weekly: total/active instructor and customer counts, booking and
  lesson-request counts by status, and a computed match rate (confirmed
  ÷ (confirmed + unmatched) over a configurable window, e.g. last 30
  days) — this is the number that's currently impossible to see without
  someone (so far, me) hand-writing a Python script against the database.

### Frontend

- A third static frontend, `frontend-admin/`, served at `/admin` —
  same architecture as the existing two (`main.py` already mounts two
  `StaticFiles` dirs plus the API; this is a third, following the exact
  same pattern, including the same trailing-slash redirect gotcha already
  documented in `CLAUDE.md` for `/customer`). Vanilla HTML/CSS/JS, no
  build step, consistent with the rest of the app.
- Screens: Login, Dashboard (the metrics from above, likely the most-used
  screen day to day), Instructors (list + detail + suspend), Customers
  (list + detail + suspend), Bookings/Lesson Requests (list, filter by
  status, force-cancel), FAQs (CRUD).

### Explicitly out of scope for a first version (call out, don't build)

- Two-factor auth for admin accounts — worth real consideration before
  this app has real users and real money, but is its own scoped addition,
  not bundled here.
- An audit log of admin actions (who suspended whom, when) — valuable
  once there's more than one admin account, adds a new model and touches
  every admin write route, better as a deliberate follow-up than
  something quietly bundled in.
- Admin-initiated password resets for instructors/customers — depends on
  Part 6's email infrastructure existing first.
