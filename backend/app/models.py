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

from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from .database import Base
from . import geo


class Instructor(Base):
    __tablename__ = "instructors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    bio = Column(Text, default="")
    address = Column(String, default="")
    certifications = Column(String, default="")  # comma-separated for simplicity
    specialty = Column(String, default="yoga")  # comma-separated: "yoga", "sound_bath", or both
    active = Column(Boolean, default=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    clients = relationship("Client", back_populates="instructor", cascade="all, delete-orphan")
    requested_sessions = relationship("SessionListing", back_populates="requested_by")
    matched_bookings = relationship("Booking", back_populates="instructor")
    availability_blocks = relationship("AvailabilityBlock", back_populates="instructor", cascade="all, delete-orphan")
    matched_lesson_requests = relationship("LessonRequest", back_populates="instructor")

    @property
    def city(self):
        """Display name for latitude/longitude, e.g. for the profile form's
        dropdown to show the currently-selected city. See geo.py — coords
        always come from the fixed demo city list, never free-text."""
        return geo.city_name_for_coords(self.latitude, self.longitude)


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

    instructor = relationship("Instructor", back_populates="clients")


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

    requested_by_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)
    requested_by = relationship("Instructor", back_populates="requested_sessions")


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
    hashed_password = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    bookings = relationship("Booking", back_populates="customer", cascade="all, delete-orphan")
    lesson_requests = relationship("LessonRequest", back_populates="customer", cascade="all, delete-orphan")


class Booking(Base):
    """
    One signup+payment+match event. `instructor_id` is null only in the
    rare case no active instructor offers the requested specialty at
    all — everything else results in an immediate match.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    package = Column(String, nullable=False)  # "single" | "pack4" | "pack8"
    sessions_total = Column(Integer, nullable=False)
    amount_paid = Column(Float, nullable=False)
    status = Column(String, default="matched")  # "matched" | "unmatched"
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
    A customer's request for one scheduled 30-minute lesson at a specific
    day/time, matched by specialty + time overlap + nearest distance.

    This is intentionally a separate model from Booking rather than an
    extension of it: Booking represents "pick a package (single/4/8) and
    get matched whenever" with no time component, while a LessonRequest
    is "I want a lesson in this specific window" — different enough
    shapes that bolting time/location fields onto Booking would leave
    most of them null for the package flow. Both flows charge through the
    same mock-payment helper and reuse the "single" package's $65/1-session
    pricing, since a scheduled request is always exactly one lesson.
    """
    __tablename__ = "lesson_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructors.id"), nullable=True)

    specialty = Column(String, nullable=False)  # "yoga" | "sound_bath"
    duration_minutes = Column(Integer, default=30, nullable=False)
    amount_paid = Column(Float, nullable=False)

    # The window the customer proposed.
    requested_day = Column(Integer, nullable=False)  # 0=Monday ... 6=Sunday
    requested_start_time = Column(String, nullable=False)  # "HH:MM"
    requested_end_time = Column(String, nullable=False)  # "HH:MM"

    # The actual confirmed slot, set only once matched.
    matched_start_time = Column(String, nullable=True)
    matched_end_time = Column(String, nullable=True)
    distance_km = Column(Float, nullable=True)

    status = Column(String, default="matched")  # "matched" | "unmatched"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    customer = relationship("Customer", back_populates="lesson_requests")
    instructor = relationship("Instructor", back_populates="matched_lesson_requests")
