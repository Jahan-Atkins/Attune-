# Scheduling + nearest-instructor matching — granular build plan ✅ done

Goal: a customer picks yoga, picks a day/time window that works for them,
submits the request, and gets matched with the *nearest* active yoga
instructor who has an *overlapping* availability slot for a 30-minute
lesson.

This is meaningfully different from what's built today — today's matching
only checks specialty + active + load balance. This adds two entirely new
dimensions (time and geography), so nothing here can be skipped or
reordered much; each part depends on the one before it.

**Decision made before Part G** (per the note that used to live here):
a scheduled 30-minute request became its **own request type** —
`LessonRequest`, separate from `Booking` — alongside the existing package
flow, not a replacement for it. See `backend/app/models.py`'s
`LessonRequest` docstring for why.

All parts (A–I) are built, wired into both frontends, covered by 34 new
backend tests (75 total, all passing), and manually clicked through end
to end in a real browser — including the "nobody available in that
window" unmatched state.

---

## Part A — Data model ✅ done

- [x] Added `latitude` / `longitude` (floats) to `Instructor`
- [x] Added `latitude` / `longitude` (floats) to `Customer`
- [x] Created `AvailabilityBlock`: `id`, `instructor_id` (FK),
      `day_of_week` (0–6), `start_time`, `end_time`
- [x] **Decision:** `start_time`/`end_time` are plain `"HH:MM"` strings,
      not a `Time` column — simplest for a learning project, documented
      in `models.py`
- [x] Made scheduling its own model — `LessonRequest` — rather than
      extending `Booking` (see decision note above); it carries
      `duration_minutes` (fixed 30), `requested_day`/`requested_start_time`/
      `requested_end_time` (what the customer proposed), and
      `matched_start_time`/`matched_end_time` (the confirmed slot)
- [x] `alembic revision --autogenerate -m "add scheduling and location"`
      → `backend/alembic/versions/8db11c1fa3fb_add_scheduling_and_location.py`
- [x] Read the generated migration before applying it
- [x] `alembic upgrade head`, confirmed the new tables/columns exist

---

## Part B — Instructor availability API ✅ done

- [x] `backend/app/routers/availability.py`
- [x] `GET /api/availability` — list the logged-in instructor's blocks
- [x] `POST /api/availability` — add a block (validates `start_time <
      end_time`, `day_of_week` in range)
- [x] `DELETE /api/availability/{id}` — remove a block (ownership-checked,
      same pattern as `clients.py`)
- [x] Rejects a new block that overlaps an existing one for the same
      instructor/day
- [x] Pytest coverage in `tests/test_availability.py`: create, list,
      delete, ownership check, invalid time range, invalid day, overlap
      rejection, isolation between instructors

---

## Part C — Instructor availability UI (instructor app) ✅ done

- [x] Lives under Profile → **Session Preferences** (that row is now
      wired up for real)
- [x] Flat list of "Monday 09:00 – 12:00 [Remove]" rows
      (`screen-availability` in `frontend/index.html`)
- [x] "+ Add Availability" form (day dropdown + two `type="time"` inputs),
      reusing the existing modal pattern in `app.js`
- [x] Wired to the Part B endpoints
- [x] Seeded demo availability blocks for Maya, Kai, and Priya in
      `seed.py` so matching has real data to work against
- [x] *(bonus)* added a **City** dropdown to the same profile-edit modal
      (Part D), backed by a computed `city` property on `Instructor`
      (see Part D)

---

## Part D — Fake location system ✅ done

- [x] Fixed list of 6 demo cities with real lat/lng in `backend/app/geo.py`
      (`DEMO_CITIES`) — no geocoding API
- [x] City dropdown on the instructor profile edit form
- [x] City dropdown in the customer flow — placed **right before
      submitting a lesson request** (the roadmap's suggested alternative
      to putting it at signup), since it's the only flow that needs it
- [x] Seeded Maya (New York), Kai (Chicago), and Priya (Austin) with
      different demo cities
- [x] `haversine_distance(lat1, lon1, lat2, lon2)` in `app/geo.py` — pure
      function, no dependencies
- [x] Unit tested against known reference distances (NYC↔LA, Chicago↔Denver)
      in `tests/test_geo.py`

---

## Part E — The matching logic itself ✅ done

- [x] `has_overlap(requested_day, requested_start, requested_end,
      duration_minutes, availability_blocks)` in `app/matching.py` — pure
      function, unit tested in isolation (`tests/test_matching.py`)
      before being wired into a route
- [x] **Overlap rule, decided and documented in code:** a match exists
      only if a full `duration_minutes` slot fits inside the
      *intersection* of the customer's window and the instructor's block
      — not just "the windows touch"
- [x] Candidate query in `lesson_requests.py`: `active == True` AND
      specialty contains the requested one AND `has_overlap(...)` is true
      for at least one block on the requested day
- [x] Remaining candidates sorted by `haversine_distance` ascending
- [x] Tie-break: fewest current matched `LessonRequest`s (load balance,
      same idea as `bookings.py`'s rule, applied to this flow's own load)
- [x] On match: stores `matched_start_time`/`matched_end_time` (the start
      of the overlap, i.e. the earliest slot that satisfies both sides)
      and `distance_km`
- [x] "Nobody matches" handled cleanly — `status: "unmatched"`, same
      pattern as the specialty-only flow, no crash

---

## Part F — API contract ✅ done

- [x] `LessonRequestCreate` schema: `specialty`, `city`,
      `requested_day`, `requested_start_time`, `requested_end_time`,
      plus the same mock-card fields `BookingCreate` uses
- [x] `LessonRequestOut`: `matched_start_time`, `matched_end_time`,
      `distance_km`, plus the shared fields
- [x] `AvailabilityBlockCreate`/`AvailabilityBlockOut`
- [x] Own router, `lesson_requests.py`, following `bookings.py`'s shape
      (and reusing its `_mock_charge` + `PACKAGE_PRICING["single"]`
      rather than duplicating pricing logic)

---

## Part G — Customer frontend ✅ done

- [x] Day-of-week picker (7 buttons) — `frontend-customer/index.html`,
      `#schedule-day-picker`
- [x] Time-window picker — 4 predefined 2-hour blocks ("9–11am",
      "11am–1pm", "1–3pm", "3–5pm"), not a free-form time input
- [x] **Decision:** duration is fixed at 30 minutes, not selectable —
      just displayed in the result
- [x] Wired to the Part F endpoint (`submitSchedulePayment` in `app.js`)
- [x] Added a **booking-type fork** screen ("Choose a Package" vs
      "Schedule a Lesson") right after specialty selection, since this
      flow now lives *alongside* the package flow rather than replacing
      it — not explicitly listed as a roadmap checkbox, but required to
      make Part G's Part-A decision actually reachable in the UI
- [x] Match/confirmation screen shows the confirmed day + time slot and
      the matched instructor's distance (`renderMatch()` now handles
      both a `Booking` and a `LessonRequest` result shape)

---

## Part H — Testing ✅ done

- [x] Unit tests for `has_overlap`: exact overlap, partial overlap
      (with/without room for the full duration), no overlap,
      adjacent-but-not-touching, wrong day, multiple candidate blocks
- [x] Unit tests for `haversine_distance` against known reference values,
      symmetry, and the demo-city round-trip lookup
- [x] Integration test: two yoga instructors, different locations —
      confirms the nearer one with a real overlap wins
- [x] Integration test: nearer instructor has no overlap, farther one
      does — confirms the farther-but-available one is matched
- [x] Integration test: no instructor overlaps at all — confirms a clean
      `unmatched` result, no crash
- [x] Full suite green: **75/75 passing** (`backend/tests/`)

---

## Part I — Polish ✅ done

- [x] **Timezones:** explicitly out of scope for this version — everyone
      is assumed to be in the same timezone, documented in
      `models.py`/`matching.py` rather than silently assumed. A
      spans-midnight request (e.g. `22:00`–`02:00`) is rejected outright
      by the same `start_time < end_time` validation used everywhere
      else, since the `"HH:MM"` string model can't represent it
- [x] Friendly copy for "nothing available in that window" — distinct
      from the package flow's unmatched copy, and verified in a real
      browser (see below)
- [x] Manually clicked through the full flow in a real browser: signed
      up a customer, scheduled a lesson, got matched with the nearest
      overlapping instructor, confirmed the match synced a real `Client`
      row on the instructor side, confirmed reload-to-resume works, and
      confirmed the unmatched state renders cleanly for an uncoverable
      slot (Sunday, nobody has weekend availability in the seed data)
