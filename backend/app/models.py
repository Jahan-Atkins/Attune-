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

from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import relationship, object_session
from .database import Base
from . import geo


class Instructor(Base):
    __tablename__ = "instructors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=False, server_default="")
    hashed_password = Column(String, nullable=False)

    bio = Column(Text, default="")
    address = Column(String, default="")
    certifications = Column(String, default="")  # comma-separated for simplicity
    specialty = Column(String, default="yoga")  # comma-separated: "yoga", "sound_bath", or both
    active = Column(Boolean, default=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    max_travel_distance_km = Column(Float, nullable=True)  # null = no limit

    clients = relationship("Client", back_populates="instructor", cascade="all, delete-orphan")
    requested_sessions = relationship("SessionListing", back_populates="requested_by")
    matched_bookings = relationship("Booking", back_populates="instructor")
    availability_blocks = relationship("AvailabilityBlock", back_populates="instructor", cascade="all, delete-orphan")
    matched_lesson_requests = relationship("LessonRequest", back_populates="instructor")
    reviews_received = relationship("Review", back_populates="instructor", cascade="all, delete-orphan")

    @property
    def city(self):
        """Display name for latitude/longitude, e.g. for the profile form's
        dropdown to show the currently-selected city. See geo.py — coords
        always come from the fixed demo city list, never free-text."""
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
    hashed_password = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    bookings = relationship("Booking", back_populates="customer", cascade="all, delete-orphan")
    lesson_requests = relationship("LessonRequest", back_populates="customer", cascade="all, delete-orphan")
    reviews_given = relationship("Review", back_populates="customer", cascade="all, delete-orphan")

    @property
    def city(self):
        """Display name for latitude/longitude — shown to instructors
        reviewing a pending request. See geo.py."""
        return geo.city_name_for_coords(self.latitude, self.longitude)


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

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    package = Column(String, nullable=False)  # "single" | "pack4" | "pack8"
    sessions_total = Column(Integer, nullable=False)
    amount_paid = Column(Float, nullable=False)  # the price the customer will owe, not necessarily charged yet — see `paid`
    paid = Column(Boolean, default=False)  # flips True only when an instructor confirms
    notes = Column(Text, nullable=True)  # anything extra the customer wants the instructor to see
    status = Column(String, default="pending")  # "pending" | "matched" | "unmatched"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="bookings")
    instructor = relationship("Instructor", back_populates="matched_bookings")


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
    A customer's request for one scheduled lesson (30/45/60/75/90
    minutes, in 15-minute steps) at a specific day/time. Same
    pending -> broadcast -> instructor-confirms lifecycle as Booking
    (see that model's docstring) — the only difference here is the
    broadcast/visibility query also requires a time-overlap match
    (has_overlap in matching.py), not just specialty + distance.

    This stays a separate model from Booking rather than an extension of
    it: Booking is "pick a package, get matched whenever" with no time
    component, while a LessonRequest is "I want a lesson in this specific
    window" — different enough shapes that bolting time/location fields
    onto Booking would leave most of them null for the package flow.
    """
    __tablename__ = "lesson_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    duration_minutes = Column(Integer, default=30, nullable=False)  # 30-90, 15-minute steps
    amount_paid = Column(Float, nullable=False)  # the price the customer will owe, not necessarily charged yet — see `paid`
    paid = Column(Boolean, default=False)  # flips True only when an instructor confirms
    notes = Column(Text, nullable=True)  # anything extra the customer wants the instructor to see

    # The window the customer proposed.
    requested_day = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    requested_start_time = Column(String, nullable=False)  # "HH:MM"
    requested_end_time = Column(String, nullable=False)  # "HH:MM"

    # The actual confirmed slot, set only once matched.
    matched_start_time = Column(String, nullable=True)
    matched_end_time = Column(String, nullable=True)
    distance_km = Column(Float, nullable=True)

    status = Column(String, default="pending")  # "pending" | "matched" | "unmatched"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="lesson_requests")
    instructor = relationship("Instructor", back_populates="matched_lesson_requests")


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
