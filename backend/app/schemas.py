"""
Pydantic schemas — these describe the *shape of JSON* going in and out
of the API, separate from models.py (which describes the database).
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime
from typing import List, Optional


class ClientLessonBase(BaseModel):
    lesson_number: int
    date: Optional[str] = None
    paid: bool = False


class ClientLessonCreate(ClientLessonBase):
    pass


class ClientLessonPaidUpdate(BaseModel):
    paid: bool


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
    # Read-only — only ever set server-side at confirm time (see
    # client_requests.py), never accepted through ClientCreate/ClientBase,
    # so an instructor can't forge a link to an arbitrary customer account
    # via "+ Add Client"/"Edit Client". Lets the frontend look up whether
    # this client has an active RecurringSeries.
    customer_id: Optional[int] = None
    # Also read-only, also computed — see Client.deletion_pending. True
    # once the instructor has requested deletion, until an admin resolves it.
    deletion_pending: bool = False
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
    password: str = Field(min_length=8)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


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

class FAQCreate(BaseModel):
    question: str
    category: str = "app use"  # "app use" | "payments" | "cancellations"


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
    password: str = Field(min_length=8)


# ---- Public instructor view (what a matched customer sees) ----
# email/phone are included here on purpose — this schema is only ever
# populated once `instructor_id` is actually set on a Booking/LessonRequest,
# i.e. only after a match is confirmed. See client_requests.py's confirm
# routes for the symmetric case (the instructor learning the customer's
# contact info).

class InstructorPublicOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    bio: str
    certifications: str
    specialty: str
    average_rating: Optional[float] = None
    review_count: int = 0
    model_config = ConfigDict(from_attributes=True)


# ---- Bookings (legacy — read-only, see routers/bookings.py's module docstring) ----

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
    package: str  # "single" | "pack4" | "pack8" | "pack12" | "pack16"
    city: str  # one of geo.DEMO_CITIES' names
    duration_minutes: int  # 30-90, 15-minute steps — see PACKAGE_DISCOUNT/DURATION_PRICING
    availability_windows: List[AvailabilityBlockBase]  # at least one — the candidate windows to match against
    lessons_per_week: Optional[int] = None  # a stated preference, not enforced — see models.LessonRequest
    notes: Optional[str] = None  # anything extra for the instructor to see
    preferred_instructor_id: Optional[int] = None  # set by "Book Again"
    card_name: str
    card_number: str
    card_expiry: str
    card_cvc: str


class ScheduleNextSessionRequest(BaseModel):
    # Omit (or leave empty) to reuse the package root's originally-submitted
    # windows — see routers/lesson_requests.py's schedule_next_session.
    availability_windows: Optional[List[AvailabilityBlockBase]] = None


class LessonRequestOut(BaseModel):
    id: int
    specialty: str
    duration_minutes: int
    amount_paid: float
    paid: bool
    notes: Optional[str] = None
    package: Optional[str] = None
    sessions_total: int = 1
    session_number: int = 1
    package_request_id: Optional[int] = None
    sessions_scheduled: Optional[int] = None
    lessons_per_week: Optional[int] = None
    availability_windows: List[AvailabilityBlockOut] = []
    requested_day: Optional[int] = None
    requested_start_time: Optional[str] = None
    requested_end_time: Optional[str] = None
    matched_start_time: Optional[str] = None
    matched_end_time: Optional[str] = None
    distance_km: Optional[float] = None
    status: str
    instructor: Optional[InstructorPublicOut] = None
    created_at: Optional[datetime] = None
    # Set only on a row generated by a RecurringSeries — see that model.
    recurring_series_id: Optional[int] = None
    occurrence_date: Optional[str] = None
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
    source: str  # "booking" | "lesson_request" — which underlying model/confirm route this is
    specialty: str
    package: Optional[str] = None  # package requests only
    sessions_total: int
    duration_minutes: Optional[int] = None  # schedule requests only
    lessons_per_week: Optional[int] = None
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


# ---- Recurring bookings ----
# One schema serves both the customer-facing and instructor-facing list
# endpoints — customer_name/instructor are each just None on whichever
# side doesn't apply, same "reuse one shape" approach as ClientRequestOut.

class RecurringSeriesCreate(BaseModel):
    lesson_request_id: int  # must already be status == "matched"


class RecurringSeriesOut(BaseModel):
    id: int
    customer_id: int
    specialty: str
    duration_minutes: int
    day_of_week: int
    start_time: str
    end_time: str
    price_per_lesson: float
    status: str
    created_at: datetime
    customer_name: Optional[str] = None
    instructor: Optional[InstructorPublicOut] = None
    model_config = ConfigDict(from_attributes=True)


# ---- Admin ----
# A third role, alongside Instructor/Customer — see models.Admin and
# security.get_current_admin. No AdminSignupRequest anywhere on purpose.

class AdminLoginRequest(BaseModel):
    """Not used directly — admin login goes through the same
    OAuth2PasswordRequestForm as the other two account types (see
    routers/admin_auth.py). Kept only as documentation of the shape."""
    email: EmailStr
    password: str


class SuspendRequest(BaseModel):
    reason: Optional[str] = None


class InstructorAdminOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    specialty: str
    active: bool
    suspended: bool
    suspension_reason: Optional[str] = None
    city: Optional[str] = None
    average_rating: Optional[float] = None
    review_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class CustomerAdminOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    suspended: bool
    suspension_reason: Optional[str] = None
    city: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# Admin list views need to see both sides of a request at a glance
# (which customer, which instructor) — neither BookingOut nor
# LessonRequestOut carries the customer's name, and InstructorPublicOut
# is nested rather than flat, so these are separate, admin-specific
# shapes built by the router rather than reusing the customer-facing ones.

class BookingAdminOut(BaseModel):
    id: int
    customer_name: str
    instructor_name: Optional[str] = None
    specialty: str
    package: str
    amount_paid: float
    paid: bool
    status: str
    created_at: Optional[datetime] = None


class LessonRequestAdminOut(BaseModel):
    id: int
    customer_name: str
    instructor_name: Optional[str] = None
    specialty: str
    duration_minutes: int
    amount_paid: float
    paid: bool
    status: str
    package: Optional[str] = None
    sessions_total: int = 1
    session_number: int = 1
    requested_day: Optional[int] = None
    requested_start_time: Optional[str] = None
    requested_end_time: Optional[str] = None
    created_at: Optional[datetime] = None


class MetricsOut(BaseModel):
    total_instructors: int
    active_instructors: int
    total_customers: int
    active_customers: int
    bookings_by_status: dict
    lesson_requests_by_status: dict
    match_rate_30d: Optional[float] = None  # confirmed / (confirmed + unmatched) over the last 30 days; None if no data at all


class ClientDeletionRequestOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    instructor_name: str
    requested_at: datetime


# ---- Reports & blocks ----
# A customer reports/blocks an instructor by that instructor's id; an
# instructor reports/blocks a customer by the Client id on their own
# practice list (never a raw customer_id — same reasoning ClientOut's
# customer_id field already documents: an instructor shouldn't be able to
# name an arbitrary customer they have no relationship with). The router
# resolves Client -> customer_id server-side and rejects hand-added
# clients with no real customer account behind them.

class ReportInstructorRequest(BaseModel):
    instructor_id: int
    reason: str
    message: Optional[str] = None


class ReportClientRequest(BaseModel):
    client_id: int
    reason: str
    message: Optional[str] = None


class ReportOut(BaseModel):
    id: int
    reporter_type: str
    reporter_name: str
    reported_type: str
    reported_name: str
    reason: str
    message: Optional[str] = None
    resolved: bool
    created_at: datetime


class BlockInstructorRequest(BaseModel):
    instructor_id: int


class BlockClientRequest(BaseModel):
    client_id: int


class BlockedInstructorOut(BaseModel):
    instructor_id: int
    name: str
    created_at: datetime


class BlockedClientOut(BaseModel):
    client_id: int
    name: str
    created_at: datetime
