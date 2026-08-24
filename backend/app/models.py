"""
ORM models — these classes describe database tables. SQLAlchemy turns
each one into a real SQL table and lets us work with rows as normal
Python objects instead of writing raw SQL.

Instructor is the "owner" of client/session data — clients and requested
sessions are scoped to whichever instructor is logged in.

Customer is a second, separate account type (see security.py for how a
JWT's "type" claim keeps instructor and customer tokens from being
usable on each other's routes). A Customer's Booking links them to a
matched Instructor — and matching also creates a real Client row for
that instructor, which is what makes the two apps feel like one system
instead of two disconnected demos.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey, DateTime, UniqueConstraint, func, or_
from sqlalchemy.orm import relationship, object_session
from .database import Base
from . import geo


class Instructor(Base):
    __tablename__ = "instructors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=False, server_default="")
    # Nullable because an account created via "Sign in with Google" (see
    # routers/auth.py's login_with_google) has no password at all — Google
    # verifying the email IS the credential. security.verify_password()
    # guards this: a None hashed_password always fails password login,
    # rather than erroring or (worse) matching any input.
    hashed_password = Column(String, nullable=True)

    bio = Column(Text, default="")
    address = Column(String, default="")
    certifications = Column(String, default="")  # comma-separated for simplicity
    specialty = Column(String, default="yoga")  # comma-separated: "yoga", "sound_bath", or both
    active = Column(Boolean, default=True)
    # Same "self-controlled, defaults on" shape as `active` — a single
    # on/off switch, not per-notification-type granularity, matching this
    # app's general preference for the simplest thing that actually works.
    # Checked before every send_email() call that targets this instructor
    # (new match, review, recurring-series change, client-deletion
    # decision) — never before one that targets a customer.
    email_notifications = Column(Boolean, default=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # What the instructor actually typed on their profile form, geocoded
    # into the lat/lng above via geo.geocode_address() — same "raw text
    # for display, city stays a computed property" split as Customer's
    # city_name/state_name; see that model for the full reasoning.
    city_name = Column(String, nullable=True)
    state_name = Column(String, nullable=True)
    max_travel_distance_km = Column(Float, nullable=True)  # null = no limit

    # Platform-controlled, unlike `active` (which the instructor toggles
    # themselves — "I'm choosing not to accept new clients right now").
    # An instructor can't flip this on themselves; only an admin can.
    suspended = Column(Boolean, default=False)
    suspension_reason = Column(Text, nullable=True)

    clients = relationship("Client", back_populates="instructor", cascade="all, delete-orphan")
    requested_sessions = relationship("SessionListing", back_populates="requested_by")
    # foreign_keys= is required on both of these now that Booking/LessonRequest
    # each have a *second* FK to instructors (preferred_instructor_id, for
    # "Book Again" rebooking) — without it SQLAlchemy can't tell which FK
    # this relationship should join on.
    matched_bookings = relationship("Booking", back_populates="instructor", foreign_keys="Booking.instructor_id")
    availability_blocks = relationship("AvailabilityBlock", back_populates="instructor", cascade="all, delete-orphan")
    matched_lesson_requests = relationship("LessonRequest", back_populates="instructor", foreign_keys="LessonRequest.instructor_id")
    reviews_received = relationship("Review", back_populates="instructor", cascade="all, delete-orphan")

    @property
    def city(self):
        """Display string for wherever this instructor is — e.g. the
        admin's instructor list. Prefers city_name/state_name (what they
        actually typed via geo.geocode_address()); falls back to the old
        DEMO_CITIES reverse lookup for an instructor whose location was
        set before this app used real geocoding here and who hasn't
        touched their profile city since. Same fallback shape as
        Customer.city — see that property's docstring for the full
        reasoning."""
        if self.city_name:
            return f"{self.city_name}, {self.state_name}" if self.state_name else self.city_name
        return geo.city_name_for_coords(self.latitude, self.longitude)

    @property
    def average_rating(self):
        """Computed fresh via the session this instance is already
        attached to (object_session) — same "don't store what you can
        compute" preference as `city` above and as distance_km elsewhere
        in this app. Returns None (not 0) with zero reviews, so the
        frontend can distinguish "no rating yet" from "rated 0"."""
        session = object_session(self)
        if session is None:
            return None
        avg = session.query(func.avg(Review.rating)).filter(Review.instructor_id == self.id).scalar()
        return round(avg, 1) if avg is not None else None

    @property
    def review_count(self):
        session = object_session(self)
        if session is None:
            return 0
        return session.query(Review).filter(Review.instructor_id == self.id).count()


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=False)

    name = Column(String, nullable=False)
    initials = Column(String, nullable=False)
    avatar_variant = Column(String, default="c1")
    status = Column(String, default="current")  # "current" or "past"
    next_session = Column(String, nullable=True)
    sessions_completed = Column(Integer, default=0)
    sessions_total = Column(Integer, default=0)
    amount_paid = Column(Float, default=0)
    amount_total = Column(Float, default=0)

    # Contact info, copied from the Customer record at confirm time (see
    # client_requests.py) — nullable because a client added by hand via
    # "+ Add Client" was never a real Customer account with these on file.
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    # Same story as email/phone: set only when this Client came from a
    # real matched Booking/LessonRequest, not a hand-added one. Lets the
    # Client Details page look up whether this customer has an active
    # RecurringSeries with this instructor (see RecurringSeries below) —
    # email/phone alone aren't a safe join key since an instructor can
    # freely edit them via "Edit Client".
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    # Client Details page fields — all optional since older/simpler clients
    # (e.g. ones added by hand via "+ Add Client") never fill these in.
    address = Column(String, nullable=True)
    location_type = Column(String, nullable=True)  # e.g. "Client's Home", "Studio Visit", "Virtual"
    start_date = Column(String, nullable=True)  # free text, e.g. "As soon as possible" or a real date
    lessons_per_week = Column(Integer, nullable=True)
    available_days = Column(String, nullable=True)  # comma-separated day-of-week ints, "0,2,3,5" — 0=Monday
    weekday_start = Column(String, nullable=True)  # "HH:MM"
    weekday_end = Column(String, nullable=True)
    weekend_start = Column(String, nullable=True)
    weekend_end = Column(String, nullable=True)

    instructor = relationship("Instructor", back_populates="clients")
    lessons = relationship("ClientLesson", back_populates="client", cascade="all, delete-orphan", order_by="ClientLesson.lesson_number")
    deletion_requests = relationship("ClientDeletionRequest", back_populates="client", cascade="all, delete-orphan")

    @property
    def deletion_pending(self):
        """A row existing in client_deletion_requests *is* "pending" — see
        that model's docstring for why there's no separate status column."""
        session = object_session(self)
        if session is None:
            return False
        return session.query(ClientDeletionRequest).filter(ClientDeletionRequest.client_id == self.id).first() is not None


class ClientLesson(Base):
    """
    One entry in a Client's itemized lesson history, shown on the Client
    Details page's "Lessons Schedule" list — separate from the aggregate
    `sessions_completed`/`sessions_total` counters on Client itself,
    which stay manually editable summary numbers rather than being
    derived from this list, to avoid a larger refactor of the existing
    Add/Edit Client form.
    """
    __tablename__ = "client_lessons"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    lesson_number = Column(Integer, nullable=False)
    date = Column(String, nullable=True)
    paid = Column(Boolean, default=False)

    client = relationship("Client", back_populates="lessons")


class ClientDeletionRequest(Base):
    """
    An instructor can no longer delete a Client outright — see
    routers/clients.py's delete_client, which now creates one of these
    instead of actually deleting anything. Only an admin's approve
    (routers/admin.py) performs the real deletion.

    Deliberately no `status` column: this table only ever holds *pending*
    requests. Resolving one (approve or deny) deletes the row — approve
    deletes the Client too, deny just clears the request and the Client
    stays. There's no history kept past that point, on purpose, matching
    the "no audit log" boundary already set for the admin side in
    PLATFORM-EXPANSION-ROADMAP.md Part 7.
    """
    __tablename__ = "client_deletion_requests"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=False)
    requested_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    client = relationship("Client", back_populates="deletion_requests")
    instructor = relationship("Instructor")


class SessionListing(Base):
    """
    A bookable session opportunity. Anyone logged in can see "open"
    listings (like a job board); once an instructor requests one, it's
    tied to them via requested_by_id and only they see it under
    "requested".
    """
    __tablename__ = "session_listings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    status = Column(String, default="open")  # "open" or "requested"
    date = Column(String, nullable=True)
    location = Column(String, nullable=True)
    pay_rate = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    # Filter/sort fields — all optional. day_of_week/lessons_per_week
    # drive the Filter modal; latitude/longitude (resolved from a demo
    # city, same as everywhere else in this app) drive Nearest/Farthest
    # sort. `date`/`location` above stay free text for display — these
    # are the structured counterparts filtering/sorting actually reads.
    day_of_week = Column(Integer, nullable=True)  # 0=Monday ... 6=Sunday
    lessons_per_week = Column(Integer, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    requested_by_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)
    requested_by = relationship("Instructor", back_populates="requested_sessions")

    @property
    def city(self):
        return geo.city_name_for_coords(self.latitude, self.longitude)


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(Text, nullable=False)
    category = Column(String, default="app use")  # "app use" | "payments" | "cancellations"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=False, server_default="")
    # Nullable for the same reason as Instructor.hashed_password above —
    # a Google-only account has no password.
    hashed_password = Column(String, nullable=True)
    # Same "self-controlled, defaults on" shape as Instructor.email_notifications
    # above — checked before every send_email() call that targets this
    # customer (match confirmed, next session scheduled, recurring series
    # created/paused/cancelled), never before one that targets an instructor.
    email_notifications = Column(Boolean, default=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # What the customer actually typed on the availability step, geocoded
    # into the lat/lng above via geo.geocode_address() — stored verbatim
    # for display. Named _name/_line rather than plain city/state/address
    # because `city` below stays a computed property, not a column — see
    # its docstring for why.
    address_line = Column(String, nullable=True)
    city_name = Column(String, nullable=True)
    state_name = Column(String, nullable=True)

    # Same platform-controlled suspension as Instructor above.
    suspended = Column(Boolean, default=False)
    suspension_reason = Column(Text, nullable=True)

    bookings = relationship("Booking", back_populates="customer", cascade="all, delete-orphan")
    lesson_requests = relationship("LessonRequest", back_populates="customer", cascade="all, delete-orphan")
    reviews_given = relationship("Review", back_populates="customer", cascade="all, delete-orphan")
    # cascade so deleting a customer's own account doesn't strand a
    # RecurringSeries pointing at a now-nonexistent customer_id (which
    # ensure_upcoming_occurrences would otherwise keep expanding forever).
    recurring_series = relationship("RecurringSeries", back_populates="customer", cascade="all, delete-orphan")

    @property
    def city(self):
        """Display string for wherever this customer is — shown to
        instructors reviewing a pending request. Prefers city_name/
        state_name (what they actually typed during the new geocoded
        lesson-request flow); falls back to a demo-city reverse lookup
        for a customer who only ever went through the old pre-cutover
        Booking flow, whose latitude/longitude were set directly from a
        DEMO_CITIES pick and who has no city_name/state_name at all. Same
        "don't break what already worked" reasoning as everywhere else
        Booking stays supported after the cutover — see routers/bookings.py."""
        if self.city_name:
            return f"{self.city_name}, {self.state_name}" if self.state_name else self.city_name
        return geo.city_name_for_coords(self.latitude, self.longitude)

    @property
    def has_password(self):
        """True unless this is a Google-only account — see hashed_password's
        docstring above. Lets the customer Profile screen hide the Change
        Password form for an account with nothing to change."""
        return self.hashed_password is not None


class Booking(Base):
    """
    One signup+package-selection event. This is a *request*, not an
    instant match: it starts "pending" and is broadcast (dynamically —
    see routers/bookings.py's candidate query, nothing is snapshotted
    here) to every active instructor offering the specialty within their
    own travel-distance preference. `instructor_id` stays null and the
    card is never charged (`paid` stays False) until one of those
    instructors confirms it — see the `/confirm` route. `status` becomes
    "unmatched" immediately, with no broadcast, only in the true dead-end
    case: no active instructor anywhere offers the specialty at all.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)
    # Set only by a "Book Again" rebooking request — narrows the broadcast
    # to this one instructor instead of every eligible one. See
    # routers/bookings.py's create route and client_requests.py's
    # visibility check.
    preferred_instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    package = Column(String, nullable=False)  # "single" | "pack4" | "pack8"
    sessions_total = Column(Integer, nullable=False)
    amount_paid = Column(Float, nullable=False)  # the price the customer will owe, not necessarily charged yet — see `paid`
    paid = Column(Boolean, default=False)  # flips True only when an instructor confirms
    notes = Column(Text, nullable=True)  # anything extra the customer wants the instructor to see
    status = Column(String, default="pending")  # "pending" | "matched" | "unmatched"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="bookings")
    instructor = relationship("Instructor", back_populates="matched_bookings", foreign_keys=[instructor_id])


class AvailabilityBlock(Base):
    """
    A recurring weekly window when an instructor is bookable, e.g.
    "Tuesdays 9:00-11:00". day_of_week follows Python's date.weekday()
    convention: 0=Monday ... 6=Sunday.

    start_time/end_time are stored as plain "HH:MM" strings rather than a
    real SQL Time column. That's a deliberate simplification for a
    learning project — string comparison ("09:00" < "11:00") works fine
    for same-day, no-timezone times and avoids pulling in datetime.time
    parsing/serialization edge cases that don't teach anything new here.
    """
    __tablename__ = "availability_blocks"

    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    start_time = Column(String, nullable=False)  # "HH:MM", 24-hour
    end_time = Column(String, nullable=False)  # "HH:MM", 24-hour

    instructor = relationship("Instructor", back_populates="availability_blocks")


class LessonRequest(Base):
    """
    A customer's request for a scheduled lesson (30/45/60/75/90 minutes,
    in 15-minute steps). Same pending -> broadcast -> instructor-confirms
    lifecycle as Booking (see that model's docstring) — the only
    difference here is the broadcast/visibility query also requires a
    time-overlap match (has_overlap/has_overlap_any in matching.py), not
    just specialty + distance.

    `package` ("single"|"pack4"|"pack8"|"pack12"|"pack16") + `sessions_total` replace the
    old Booking-only package concept — every new customer request now
    goes through this model regardless of session count (see
    routers/bookings.py's module docstring for why Booking itself stays
    read-only rather than being deleted). `session_number`/
    `package_request_id` track a multi-session package's sessions: the
    row with `session_number == 1` is the one that actually goes through
    the broadcast/confirm lifecycle below; sessions 2..N are scheduled
    afterward one at a time against the now-fixed instructor (see
    routers/lesson_requests.py's schedule_next_session), created
    directly as "matched" the same way a RecurringSeries occurrence is,
    and point back at the root via `package_request_id`.

    `requested_day`/`requested_start_time`/`requested_end_time` are
    nullable and mean something different than they used to: a customer
    now submits a *set* of candidate windows (see
    LessonRequestAvailabilityWindow below), so there's no single "the"
    window until a specific instructor actually confirms one — these
    three columns stay NULL while pending and get populated at match
    time with whichever submitted window matched, same "don't store what
    isn't real yet" spirit as this file's other computed/deferred
    fields. A row created directly as "matched" (a RecurringSeries
    occurrence, or a schedule_next_session row) populates them
    immediately, same as before.
    """
    __tablename__ = "lesson_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)
    # Set only by a "Book Again" rebooking request — see Booking's
    # identical field above for the full rationale.
    preferred_instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    duration_minutes = Column(Integer, default=30, nullable=False)  # 30-90, 15-minute steps
    amount_paid = Column(Float, nullable=False)  # the price the customer will owe, not necessarily charged yet — see `paid`
    paid = Column(Boolean, default=False)  # flips True only when an instructor confirms
    notes = Column(Text, nullable=True)  # anything extra the customer wants the instructor to see

    package = Column(String, nullable=True)  # "single" | "pack4" | "pack8" | "pack12" | "pack16" — null only on pre-migration legacy rows
    sessions_total = Column(Integer, nullable=False, default=1, server_default="1")
    session_number = Column(Integer, nullable=False, default=1, server_default="1")  # 1 = broadcast/matched root; 2..N = later package sessions
    package_request_id = Column(Integer, ForeignKey("lesson_requests.id"), nullable=True)  # set only when session_number >= 2
    # A stated preference, not an enforced constraint — same "just a
    # number, nothing validates against it" role as Client.lessons_per_week
    # already plays elsewhere in this app. Copied onto the new Client at
    # confirm time (see client_requests.py's _create_client_from_lesson_request).
    lessons_per_week = Column(Integer, nullable=True)

    # The window that actually matched — NULL while pending on a
    # multi-window request. See the class docstring.
    requested_day = Column(Integer, nullable=True)  # 0=Monday ... 6=Sunday
    requested_start_time = Column(String, nullable=True)  # "HH:MM"
    requested_end_time = Column(String, nullable=True)  # "HH:MM"

    # The actual confirmed slot, set only once matched.
    matched_start_time = Column(String, nullable=True)
    matched_end_time = Column(String, nullable=True)
    distance_km = Column(Float, nullable=True)

    status = Column(String, default="pending")  # "pending" | "matched" | "unmatched"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Set only on a row generated by RecurringSeries.ensure_upcoming_occurrences
    # (see that model) — such a row is created directly as "matched", skipping
    # the pending/broadcast lifecycle entirely, since the instructor already
    # committed to the standing slot once. occurrence_date ("YYYY-MM-DD") is
    # what makes otherwise-identical weekly rows distinguishable — every other
    # LessonRequest only ever stores a day-of-week, never a real calendar date.
    recurring_series_id = Column(Integer, ForeignKey("recurring_series.id"), nullable=True)
    occurrence_date = Column(String, nullable=True)

    customer = relationship("Customer", back_populates="lesson_requests")
    instructor = relationship("Instructor", back_populates="matched_lesson_requests", foreign_keys=[instructor_id])
    # The set of candidate windows submitted with this request — see
    # LessonRequestAvailabilityWindow. Ordered earliest-first so "first
    # window that has room" (matching.has_overlap_any) means "earliest
    # window that has room" for free, no sorting needed at call sites.
    availability_windows = relationship(
        "LessonRequestAvailabilityWindow", back_populates="lesson_request",
        cascade="all, delete-orphan",
        order_by="LessonRequestAvailabilityWindow.day_of_week, LessonRequestAvailabilityWindow.start_time",
    )

    @property
    def sessions_scheduled(self):
        """How many of this package's sessions are matched so far —
        meaningful only on the session_number==1 root row (None
        otherwise, since a child row isn't itself a package). Computed
        fresh via object_session(), same pattern as Instructor.average_rating."""
        if self.session_number != 1:
            return None
        session = object_session(self)
        if session is None:
            return None
        return (
            session.query(LessonRequest)
            .filter(
                or_(LessonRequest.id == self.id, LessonRequest.package_request_id == self.id),
                LessonRequest.status == "matched",
            )
            .count()
        )


class LessonRequestAvailabilityWindow(Base):
    """
    One day+window entry in the set of availability a customer submitted
    with a single LessonRequest — mirrors AvailabilityBlock's shape
    exactly (day_of_week 0=Monday..6=Sunday, start_time/end_time
    "HH:MM"), just scoped to one request instead of one instructor's
    whole week. A customer submits several of these per request (e.g.
    "Mon 9-11am, Wed 2-4pm, Fri 9am-noon"); matching.has_overlap_any()
    tries each one in order against a candidate instructor's own
    AvailabilityBlock list and returns the first that fits.
    """
    __tablename__ = "lesson_request_availability_windows"

    id = Column(Integer, primary_key=True, index=True)
    lesson_request_id = Column(Integer, ForeignKey("lesson_requests.id"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)

    lesson_request = relationship("LessonRequest", back_populates="availability_windows", foreign_keys=[lesson_request_id])


class RecurringSeries(Base):
    """
    A standing weekly booking, created from an already-matched LessonRequest
    via "Make this a standing weekly booking" (see routers/recurring_series.py).
    The series itself isn't a bookable slot — it's a template that
    ensure_upcoming_occurrences() lazily expands into real LessonRequest rows
    (see that function's docstring for why "lazy, on read" instead of a cron
    job). specialty/duration_minutes/day_of_week/start_time/end_time/
    price_per_lesson are all copied from the source LessonRequest at creation
    time — price_per_lesson is locked in then so a later DURATION_PRICING
    change doesn't retroactively reprice an existing series.
    """
    __tablename__ = "recurring_series"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=False)

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    duration_minutes = Column(Integer, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    start_time = Column(String, nullable=False)  # "HH:MM"
    end_time = Column(String, nullable=False)  # "HH:MM"
    price_per_lesson = Column(Float, nullable=False)

    status = Column(String, default="active")  # "active" | "paused" | "cancelled"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="recurring_series")
    instructor = relationship("Instructor")

    @property
    def customer_name(self):
        return self.customer.name if self.customer else None


class Review(Base):
    """
    A customer's rating of an instructor, tied to one specific matched
    Booking or LessonRequest — exactly one of `booking_id`/
    `lesson_request_id` is set per review, mirroring the same
    package-vs-schedule duality client_requests.py already handles.
    Reviewable as soon as that booking/request reaches "matched" — this
    app has no structured "the session actually happened on this date"
    signal to gate on instead (ClientLesson.date is free text, not a
    real date the backend could compare against now()), so "matched" is
    the simplification, documented rather than silently assumed.
    """
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("customer_id", "booking_id", name="uq_review_customer_booking"),
        UniqueConstraint("customer_id", "lesson_request_id", name="uq_review_customer_lesson_request"),
    )

    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    lesson_request_id = Column(Integer, ForeignKey("lesson_requests.id"), nullable=True)

    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    instructor = relationship("Instructor", back_populates="reviews_received")
    customer = relationship("Customer", back_populates="reviews_given")

    @property
    def customer_name(self):
        return self.customer.name if self.customer else None


class PasswordResetToken(Base):
    """
    A short-lived, single-use token for the forgot-password flow (see
    routers/auth.py and routers/customer_auth.py — Admin has no self-serve
    reset, matching its no-signup docstring below). Only `token_hash` is
    stored, never the raw token, same reasoning as hashed_password: a DB
    leak shouldn't hand out a working reset link. account_type/account_id
    play the same role as Report/Block's reporter_type/reporter_id below —
    this table serves both Instructor and Customer accounts, which live in
    different tables, so a single typed foreign key isn't possible.
    """
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    account_type = Column(String, nullable=False)  # "instructor" | "customer"
    account_id = Column(Integer, nullable=False)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Report(Base):
    """
    Either side of a match can report the other for a trust & safety
    concern — see routers/reports.py. Unlike ClientDeletionRequest, a
    report keeps a persistent history: `resolved` just marks whether an
    admin has looked at it, it never deletes the row, since a pattern
    across multiple past reports (same reporter, or the same person
    reported repeatedly) is exactly what an admin needs to be able to see.

    reporter_type/reported_type + *_id (not a typed foreign key) because
    either side of a report can be an Instructor or a Customer — the same
    "two possible tables, one column" shape as PasswordResetToken above.
    """
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    reporter_type = Column(String, nullable=False)  # "instructor" | "customer"
    reporter_id = Column(Integer, nullable=False)
    reported_type = Column(String, nullable=False)  # "instructor" | "customer"
    reported_id = Column(Integer, nullable=False)
    reason = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Block(Base):
    """
    `blocker` has blocked `blocked` — see routers/blocks.py. Stored
    one-directional, but treated as symmetric everywhere it matters: a
    block from either side is enough to stop a future match between the
    two (see client_requests.py's visibility checks), even though only
    one side actively chose to block.
    """
    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("blocker_type", "blocker_id", "blocked_type", "blocked_id", name="uq_block_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    blocker_type = Column(String, nullable=False)  # "instructor" | "customer"
    blocker_id = Column(Integer, nullable=False)
    blocked_type = Column(String, nullable=False)  # "instructor" | "customer"
    blocked_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Admin(Base):
    """
    A third account type, alongside Instructor and Customer — see
    security.py for the matching third JWT `type` claim. Deliberately
    has **no public signup route anywhere**: unlike the other two, an
    admin account is never created by hitting an API endpoint from the
    outside. It only ever comes from running create_admin.py locally
    against DATABASE_URL (same way seed.py already is), which closes off
    the obvious attack of someone hitting a hypothetical
    /api/admin/auth/signup and handing themselves admin access.
    """
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
