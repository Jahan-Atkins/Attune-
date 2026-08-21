"""
Pydantic schemas — these describe the *shape of JSON* going in and out
of the API, separate from models.py (which describes the database).
"""
from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime
from typing import List, Optional


class ClientLessonBase(BaseModel):
    lesson_number: int
    date: Optional[str] = None
    paid: bool = False


class ClientLessonCreate(ClientLessonBase):
    pass


class ClientLessonOut(ClientLessonBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ClientBase(BaseModel):
    name: str
    initials: str
    avatar_variant: str = "c1"
    status: str = "current"
    next_session: Optional[str] = None
    sessions_completed: int = 0
    sessions_total: int = 0
    amount_paid: float = 0
    amount_total: float = 0
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    location_type: Optional[str] = None
    start_date: Optional[str] = None
    lessons_per_week: Optional[int] = None
    available_days: Optional[str] = None  # comma-separated day-of-week ints, "0,2,3,5"
    weekday_start: Optional[str] = None
    weekday_end: Optional[str] = None
    weekend_start: Optional[str] = None
    weekend_end: Optional[str] = None


class ClientCreate(ClientBase):
    pass


class ClientOut(ClientBase):
    id: int
    lessons: List[ClientLessonOut] = []
    model_config = ConfigDict(from_attributes=True)


class SessionListingBase(BaseModel):
    title: str
    status: str = "open"
    date: Optional[str] = None
    location: Optional[str] = None
    pay_rate: Optional[str] = None
    notes: Optional[str] = None
    day_of_week: Optional[int] = None  # 0=Monday ... 6=Sunday
    lessons_per_week: Optional[int] = None
    city: Optional[str] = None  # one of geo.DEMO_CITIES' names — write-only, resolved to lat/lng server-side


class SessionListingCreate(SessionListingBase):
    pass


class SessionListingOut(SessionListingBase):
    id: int
    requested_by_id: Optional[int] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class Summary(BaseModel):
    greeting_name: str
    earned_this_week: float
    current_client_name: Optional[str] = None
    current_client_initials: Optional[str] = None


# ---- Auth ----

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Profile ----

class ProfileOut(BaseModel):
    name: str
    email: EmailStr
    phone: str
    bio: str
    address: str
    certifications: str
    specialty: str
    active: bool
    city: Optional[str] = None
    max_travel_distance_km: Optional[float] = None
    average_rating: Optional[float] = None
    review_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    certifications: Optional[str] = None
    specialty: Optional[str] = None
    active: Optional[bool] = None
    city: Optional[str] = None  # one of geo.DEMO_CITIES' names; resolved to lat/lng server-side
    max_travel_distance_km: Optional[float] = None  # null = no limit


# ---- FAQ ----

class FAQOut(BaseModel):
    id: int
    question: str
    category: str
    model_config = ConfigDict(from_attributes=True)


# ---- Customer signup/login ----

class CustomerSignupRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str


class CustomerOut(BaseModel):
    name: str
    email: EmailStr
    phone: str
    model_config = ConfigDict(from_attributes=True)


# ---- Public instructor view (what a matched customer sees) ----
# email/phone are included here on purpose — this schema is only ever
# populated once `instructor_id` is actually set on a Booking/LessonRequest,
# i.e. only after a match is confirmed. See client_requests.py's confirm
# routes for the symmetric case (the instructor learning the customer's
# contact info).

class InstructorPublicOut(BaseModel):
    name: str
    email: EmailStr
    phone: str
    bio: str
    certifications: str
    specialty: str
    average_rating: Optional[float] = None
    review_count: int = 0
    model_config = ConfigDict(from_attributes=True)


# ---- Bookings (signup + mock payment + matching) ----

class BookingCreate(BaseModel):
    specialty: str  # "yoga" | "sound_bath"
    package: str    # "single" | "pack4" | "pack8"
    city: str       # one of geo.DEMO_CITIES' names
    notes: Optional[str] = None  # anything extra for the instructor to see
    card_name: str
    card_number: str
    card_expiry: str
    card_cvc: str


class BookingOut(BaseModel):
    id: int
    specialty: str
    package: str
    sessions_total: int
    amount_paid: float
    paid: bool
    notes: Optional[str] = None
    status: str
    instructor: Optional[InstructorPublicOut] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ---- Availability blocks (instructor weekly schedule) ----

class AvailabilityBlockBase(BaseModel):
    day_of_week: int  # 0=Monday ... 6=Sunday
    start_time: str  # "HH:MM", 24-hour
    end_time: str  # "HH:MM", 24-hour


class AvailabilityBlockCreate(AvailabilityBlockBase):
    pass


class AvailabilityBlockOut(AvailabilityBlockBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ---- Lesson requests (schedule + nearest-instructor matching) ----

class LessonRequestCreate(BaseModel):
    specialty: str  # "yoga" | "sound_bath"
    city: str  # one of geo.DEMO_CITIES' names
    duration_minutes: int  # 30-90, 15-minute steps — see DURATION_PRICING
    requested_day: int  # 0=Monday ... 6=Sunday
    requested_start_time: str  # "HH:MM"
    requested_end_time: str  # "HH:MM"
    notes: Optional[str] = None  # anything extra for the instructor to see
    card_name: str
    card_number: str
    card_expiry: str
    card_cvc: str


class LessonRequestOut(BaseModel):
    id: int
    specialty: str
    duration_minutes: int
    amount_paid: float
    paid: bool
    notes: Optional[str] = None
    requested_day: int
    requested_start_time: str
    requested_end_time: str
    matched_start_time: Optional[str] = None
    matched_end_time: Optional[str] = None
    distance_km: Optional[float] = None
    status: str
    instructor: Optional[InstructorPublicOut] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ---- Client requests (instructor-facing pending-request queue) ----
# Unifies a pending Booking and a pending LessonRequest into one shape so
# the instructor's "Client Requests" screen can render both with a single
# template. `request_type` tells the frontend (and the confirm endpoint)
# which one it's looking at. Distance is computed fresh per instructor —
# it's not a stored value, since it depends on *who's* looking.

class ClientRequestOut(BaseModel):
    id: int
    request_type: str  # "package" | "schedule"
    specialty: str
    package: Optional[str] = None  # package requests only
    sessions_total: int
    duration_minutes: Optional[int] = None  # schedule requests only
    amount_due: float
    customer_name: str
    customer_city: Optional[str] = None
    customer_lat: Optional[float] = None
    customer_lng: Optional[float] = None
    distance_km: Optional[float] = None
    requested_day: Optional[int] = None  # schedule requests only
    requested_start_time: Optional[str] = None
    requested_end_time: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


class ClientRequestConfirmedOut(ClientRequestOut):
    """
    Returned only by the confirm routes, never by the list/browse
    endpoint — a customer's contact info shouldn't be visible to every
    instructor whose queue a pending request passes through, only to the
    one who actually confirms it. See client_requests.py.
    """
    customer_email: str
    customer_phone: str


# ---- Reviews ----

class ReviewCreate(BaseModel):
    booking_id: Optional[int] = None
    lesson_request_id: Optional[int] = None
    rating: int  # 1-5
    comment: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    instructor_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime
    customer_name: Optional[str] = None  # populated by the router, not a real Review column
    model_config = ConfigDict(from_attributes=True)
