# Request → confirm matching model ✅ done

Goal (from the original ask): stop auto-matching customers to a single
instructor. Instead, broadcast a pending request to every instructor who
could plausibly take it, let the customer describe lesson length,
location, and any extra notes, and don't charge the card or add the
customer to an instructor's client list until that instructor actually
confirms the match.

This touched both booking flows (`Booking` for packages, `LessonRequest`
for scheduled lessons), added an instructor travel-distance preference,
variable lesson duration with tiered pricing, and a map view. Three
scope decisions were made explicitly before starting (asked, not
assumed):

1. **Both flows get the new model**, not just scheduled lessons —
   package bookings also go pending -> broadcast -> confirm now.
2. **Discounted per-minute pricing for longer lessons** — 30 min stayed
   $65, but 45/60/75/90 min are priced below a flat linear scale (see
   `DURATION_PRICING` in `lesson_requests.py`): $90 / $115 / $140 / $160.
3. **The map view got built now**, not deferred to a later phase.

All of it is backend-complete, frontend-complete on both apps, covered
by 34 new/rewritten backend tests (94 total, all passing), and manually
verified end to end — some of it in a real browser, the rest via direct
API calls after a mid-session environment hiccup (see the note at the
bottom) made the browser session unreliable partway through.

---

## Data model

- [x] `Instructor.max_travel_distance_km` (nullable — null = no limit)
- [x] `Booking`/`LessonRequest` both gained `paid` (bool, default False)
      and `notes` (nullable text)
- [x] `Booking.status`/`LessonRequest.status` gained a third value,
      `"pending"`, sitting between creation and `"matched"`/`"unmatched"`
- [x] `instructor_id` on both models stays `NULL` until confirmed —
      nothing is assigned at creation time anymore
- [x] Migration `cd44acd0a348` — reviewed before applying; `paid` columns
      use `server_default=false()` so they can't land in a NULL
      not-really-a-boolean state on existing rows

## Matching / broadcast logic

- [x] `within_travel_distance()` in `matching.py` — pure function,
      unit tested. Missing data never hides a request: an instructor
      with no distance preference set sees everything, and a request
      with an unknown distance (either side missing a location) is
      shown rather than silently dropped. The cap only applies when
      every value needed to compute it is actually known.
- [x] **Decision:** distance is deliberately *not* part of the
      create-time "is this a dead end" check in either
      `bookings.py`/`lesson_requests.py` — that's a per-instructor
      preference, evaluated dynamically whenever *they* browse
      (`client_requests.py`), not something that should decide whether
      a request even gets broadcast in the first place
- [x] Package bookings' create-time check: is there *any* active
      instructor offering the specialty at all (ignoring distance)?
- [x] Scheduled lesson requests' create-time check goes further: is
      there any active, specialty-matching instructor whose
      availability actually overlaps the requested window
      (`has_overlap`, reused from the scheduling feature)? Distance
      still excluded from this check, same reasoning as above.
- [x] `GET /api/client-requests` — nothing is snapshotted; every call
      recomputes which pending requests the logged-in instructor can
      currently see. Change your specialty, distance preference, or
      availability and what you see here updates immediately, no stale
      broadcast list to invalidate.

## Confirm + payment

- [x] `PUT /api/client-requests/bookings/{id}/confirm` and
      `.../lesson-requests/{id}/confirm` — instructor-only, and
      re-validates the same specialty/distance/(overlap) rules
      server-side rather than trusting that the list the client rendered
      is still accurate (an instructor could otherwise hand-craft a PUT
      to a request they shouldn't be able to claim)
- [x] Race handled the same way `sessions.py`'s existing
      request/withdraw already does in this codebase: fetch filtered by
      `status == "pending"`, 404 if that's no longer true. No new
      concurrency pattern introduced.
- [x] **Decision: no card data is persisted, ever.** `_mock_charge()`
      still validates card format at submission time (instant feedback,
      same UX as before) but nothing about the card is stored — "charging"
      at confirm time is nothing more than flipping `paid` to True, which
      is honest about what a mock gateway can actually do and avoids
      storing card-shaped data for no reason
- [x] Confirming still creates a real `Client` row, same as the old
      auto-match flow did — it just moved from the create route to the
      confirm route, and now belongs to whichever instructor confirmed
- [x] No explicit "decline" action — matches this codebase's existing
      convention for `SessionListing` (instructors browsing open
      sessions don't get a reject button either). An instructor just
      doesn't confirm what they don't want; it stays visible to others.

## Variable lesson duration

- [x] Customer picks 30/45/60/75/90 minutes (`DURATION_PRICING` in
      `lesson_requests.py`); `GET /api/customer/lesson-requests/durations`
      exposes it the same way `/packages` already does, so frontend and
      backend can't drift
- [x] `has_overlap()` already took `duration_minutes` as a parameter
      from the original scheduling feature — no signature change needed,
      just stopped hardcoding 30

## Frontend — instructor app

- [x] Session Preferences screen: "Maximum travel distance (km)" field,
      blank = no limit, saves through the existing `/api/profile` PUT
- [x] Sessions screen gained a third subtab, **Client Requests** (now
      the default one shown), rendering pay, location + live distance,
      requested practice, schedule (scheduled requests) or package tier
      (package requests), and notes — exactly the fields asked for —
      with a Confirm Match button per card
- [x] The **MAP VIEW** button (previously a dead stub already sitting in
      the Sessions screen) now opens a Leaflet map in the existing modal,
      pinned at each pending request's real demo-city coordinates, with
      a popup showing name/specialty/pay. Leaflet loads from a CDN
      (`unpkg.com`) with `defer` — no build step added, per CLAUDE.md's
      frontend constraints

## Frontend — customer app

- [x] Package flow: added a city step and a notes textarea to the
      payment screen (packages never collected location before this —
      distance-based instructor filtering needed one)
- [x] Schedule flow: added a duration picker (with live tiered pricing)
      alongside the existing day/time-window pickers, plus a notes
      textarea
- [x] Both payment screens: copy updated from "Confirm & Get Matched" to
      "Send Request", and the mock-payment banner now says the card is
      only charged once an instructor confirms
- [x] Match screen now handles three states instead of two: pending
      (new — "waiting for an instructor", nothing charged yet, a "Check
      for updates" button to re-poll `/me`), matched, and unmatched
- [x] Landing page and booking-type card copy updated — it used to
      promise "the nearest available instructor" and "matched whenever
      one's available," which described the old auto-match behavior and
      would've been actively misleading under the new one

## Verification

- [x] 34 new/rewritten tests across `test_bookings.py`,
      `test_lesson_requests.py`, and a new `test_client_requests.py`
      (visibility filtering by specialty/distance/overlap, confirm
      success, already-claimed race, wrong-instructor rejection,
      auth requirements) — **94/94 passing**
- [x] Full browser click-through of the scheduled-lesson flow: signed up
      a customer, picked Yoga -> Schedule a Lesson -> 60 min -> Monday
      9-11am -> New York, added a note, sent the request, saw the
      pending state render correctly ("$115 due once confirmed")
- [x] Instructor side, same browser session: logged in as Maya, saw the
      request in Client Requests with every field correct (pay,
      schedule, ~0 km away, the note in quotes), opened the map and
      confirmed the pin/popup matched, hit Confirm Match, watched it
      disappear from the queue and the client appear on the Clients tab
      with the right price and next-session string
- [x] Distance-preference filtering verified directly against the API
      after the browser session became unreliable (see below): an
      instructor in Austin with a 500 km limit correctly does **not**
      see a request from Seattle (~2500 km away); an instructor with no
      limit does, with the correct computed distance

### A mid-session environment hiccup, for the record

Partway through manual verification, macOS revoked (then, after the
user re-granted it, restored) this session's filesystem access to
`~/Downloads` — not an app bug, but worth noting because it also broke
the *already-running* local `uvicorn` dev server, which had the old
permission state cached for its process lifetime and needed a restart
to pick up the restored access. If a local dev server starts throwing
`PermissionError` on static file reads out of nowhere, that's the first
thing to check — restart it before assuming the code changed anything.
