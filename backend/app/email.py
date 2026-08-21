"""
Mock email notifications — same "mock now, real gateway later" pattern
already used for payments (see bookings.py's _mock_charge). The default/
only backend right now just prints to the console — plain print(),
deliberately not the logging module, since Python's logging defaults to
WARNING with no handler configured anywhere in this app, which would
silently swallow every notification without anyone noticing. print()
guarantees it actually shows up under `uvicorn --reload`, and is just as
easy to assert on in tests via pytest's built-in capsys fixture (see
tests/test_email.py). EMAIL_BACKEND is read the same way DATABASE_URL
already switches between SQLite and Postgres — swap in a real provider
(SendGrid/Postmark/SES) later by adding a branch here, not by touching
any of the trigger points that call send_email().
"""
import os

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console")


def send_email(to: str, subject: str, body: str) -> None:
    if EMAIL_BACKEND == "console":
        print(f"EMAIL to={to} subject={subject!r} body={body!r}")
    else:
        raise NotImplementedError(f"Unknown EMAIL_BACKEND: {EMAIL_BACKEND!r}")
