"""
Pydantic schemas — these describe the *shape of JSON* going in and out
of the API, separate from models.py (which describes the database).
"""
from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional


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


class ClientCreate(ClientBase):
    pass


class ClientOut(ClientBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class SessionListingBase(BaseModel):
    title: str
    status: str = "open"
    date: Optional[str] = None
    location: Optional[str] = None
    pay_rate: Optional[str] = None
    notes: Optional[str] = None


class SessionListingCreate(SessionListingBase):
    pass


class SessionListingOut(SessionListingBase):
    id: int
    requested_by_id: Optional[int] = None
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
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Profile ----

class ProfileOut(BaseModel):
    name: str
    email: EmailStr
    bio: str
    address: str
    certifications: str
    specialty: str
    active: bool
    city: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    certifications: Optional[str] = None
    specialty: Optional[str] = None
    active: Optional[bool] = None
    city: Optional[str] = None  # one of geo.DEMO_CITIES' names; resolved to lat/lng server-side


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
    password: str


class CustomerOut(BaseModel):
    name: str
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)


# ---- Public instructor view (what a matched customer sees — no email, no address) ----

class InstructorPublicOut(BaseModel):
    name: str
    bio: str
    certifications: str
    specialty: str
    model_config = ConfigDict(from_attributes=True)


# ---- Bookings (signup + mock payment + matching) ----

class BookingCreate(BaseModel):
    specialty: str  # "yoga" | "sound_bath"
    package: str    # "single" | "pack4" | "pack8"
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
    status: str
    instructor: Optional[InstructorPublicOut] = None
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
    requested_day: int  # 0=Monday ... 6=Sunday
    requested_start_time: str  # "HH:MM"
    requested_end_time: str  # "HH:MM"
    card_name: str
    card_number: str
    card_expiry: str
    card_cvc: str


class LessonRequestOut(BaseModel):
    id: int
    specialty: str
    duration_minutes: int
    amount_paid: float
    requested_day: int
    requested_start_time: str
    requested_end_time: str
    matched_start_time: Optional[str] = None
    matched_end_time: Optional[str] = None
    distance_km: Optional[float] = None
    status: str
    instructor: Optional[InstructorPublicOut] = None
    model_config = ConfigDict(from_attributes=True)
