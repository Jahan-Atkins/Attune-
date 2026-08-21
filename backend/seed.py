"""
Populates the database with demo data so the app looks right the first
time you run it — including three instructors with different specialties,
so the customer app's matching logic actually has something to choose
between.

Run from the backend/ folder:

    python seed.py

Safe to re-run — it checks for existing rows first instead of
duplicating them.

    Instructor login:  demo@attune.app / password123   (yoga + sound bath)
    Instructor login:  kai@attune.app / password123     (sound bath only)
    Instructor login:  priya@attune.app / password123   (yoga only)
"""
from app.database import SessionLocal, engine, Base
from app import geo, models
from app.security import hash_password

Base.metadata.create_all(bind=engine)

db = SessionLocal()

NYC = geo.CITY_BY_NAME["New York, NY"]
CHICAGO = geo.CITY_BY_NAME["Chicago, IL"]
AUSTIN = geo.CITY_BY_NAME["Austin, TX"]

INSTRUCTORS = [
    dict(
        name="Maya Solis", email="demo@attune.app", password="password123",
        bio="Hi! I'm Maya, a certified 500-HR yoga teacher and sound healing "
            "practitioner devoted to helping people find stillness and balance.",
        certifications="RYT-500, Sound Healing Practitioner",
        specialty="yoga,sound_bath",
        city=NYC,
        # Weekday mornings and afternoons.
        availability=[(0, "09:00", "12:00"), (2, "09:00", "12:00"), (4, "13:00", "17:00")],
    ),
    dict(
        name="Kai Bennett", email="kai@attune.app", password="password123",
        bio="Kai leads immersive sound bath journeys using crystal bowls, "
            "gongs, and chimes to guide deep relaxation.",
        certifications="Certified Sound Healing Practitioner",
        specialty="sound_bath",
        city=CHICAGO,
        # Evenings, later in the week.
        availability=[(3, "17:00", "20:00"), (4, "17:00", "20:00"), (5, "10:00", "14:00")],
    ),
    dict(
        name="Priya Anand", email="priya@attune.app", password="password123",
        bio="Priya is a 200-HR vinyasa instructor focused on breath-led, "
            "accessible flows for every body.",
        certifications="RYT-200",
        specialty="yoga",
        city=AUSTIN,
        # Early mornings, most of the week.
        availability=[(0, "06:00", "09:00"), (1, "06:00", "09:00"), (2, "06:00", "09:00"), (3, "06:00", "09:00")],
        max_travel_distance_km=500,  # the other two leave this unset (no limit), on purpose — real variety to demo the filter
    ),
]

try:
    instructors_by_email = {}
    for data in INSTRUCTORS:
        existing = db.query(models.Instructor).filter(models.Instructor.email == data["email"]).first()
        if existing:
            instructors_by_email[data["email"]] = existing
            continue
        instructor = models.Instructor(
            name=data["name"],
            email=data["email"],
            hashed_password=hash_password(data["password"]),
            bio=data["bio"],
            address="",
            certifications=data["certifications"],
            specialty=data["specialty"],
            active=True,
            latitude=data["city"]["lat"],
            longitude=data["city"]["lng"],
            max_travel_distance_km=data.get("max_travel_distance_km"),
        )
        db.add(instructor)
        db.commit()
        db.refresh(instructor)
        instructors_by_email[data["email"]] = instructor
        print(f"Created instructor: {data['email']} / {data['password']}")

        if db.query(models.AvailabilityBlock).filter(models.AvailabilityBlock.instructor_id == instructor.id).count() == 0:
            db.add_all([
                models.AvailabilityBlock(instructor_id=instructor.id, day_of_week=day, start_time=start, end_time=end)
                for day, start, end in data["availability"]
            ])
            db.commit()
            print(f"Seeded availability for {data['name']}.")

    maya = instructors_by_email["demo@attune.app"]

    if db.query(models.Client).filter(models.Client.instructor_id == maya.id).count() == 0:
        db.add_all([
            models.Client(
                instructor_id=maya.id,
                name="Rosa Klein",
                initials="RK",
                avatar_variant="c1",
                status="current",
                next_session="Thu, 6:00 PM",
                sessions_completed=8,
                sessions_total=10,
                amount_paid=320,
                amount_total=400,
            ),
            models.Client(
                instructor_id=maya.id,
                name="Theo Nakamura",
                initials="TN",
                avatar_variant="c2",
                status="current",
                next_session=None,
                sessions_completed=12,
                sessions_total=12,
                amount_paid=480,
                amount_total=480,
            ),
        ])
        print("Seeded clients for Maya.")
    else:
        print("Clients already exist, skipping.")

    if db.query(models.FAQ).count() == 0:
        db.add_all([
            models.FAQ(
                question="Is there a cancellation policy? If a client cancels within 2 hours "
                          "of their session, do I still get paid for travel and setup time?",
                category="cancellations",
            ),
            models.FAQ(
                question="How soon after a session is payment released to my account?",
                category="payments",
            ),
            models.FAQ(
                question="Can I bring my own singing bowls, or does the studio provide equipment?",
                category="app use",
            ),
            models.FAQ(
                question="How do I mark myself unavailable for a week without deactivating my whole profile?",
                category="app use",
            ),
            models.FAQ(
                question="Do I need to submit a W-9 before my first payout?",
                category="payments",
            ),
        ])
        print("Seeded FAQs.")
    else:
        print("FAQs already exist, skipping.")

    db.commit()
finally:
    db.close()
