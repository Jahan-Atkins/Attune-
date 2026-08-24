"""
Email notifications. Defaults to printing to the console — plain
print(), deliberately not the logging module, since Python's logging
defaults to WARNING with no handler configured anywhere in this app,
which would silently swallow every notification without anyone
noticing. print() guarantees it actually shows up under
`uvicorn --reload`, and is just as easy to assert on in tests via
pytest's built-in capsys fixture (see tests/test_email.py).

EMAIL_BACKEND is read the same way DATABASE_URL already switches between
SQLite and Postgres. Set it to "resend" (and RESEND_API_KEY) to send
real email via Resend's API — see README/CLAUDE.md for where those env
vars actually go (backend/.env locally, Render's Environment tab in
production; never committed, never pasted into chat). Leaving
EMAIL_BACKEND unset keeps every environment — including the test suite —
on the console backend by default, so nothing needs a real API key to
run.
"""
import os

import httpx

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "console")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
# A Resend account can send from this shared, unverified address with no
# setup; once a real domain is verified with Resend, point this at
# something like "Attune <notifications@yourdomain.com>" instead.
RESEND_FROM_ADDRESS = os.getenv("RESEND_FROM_ADDRESS", "Attune <onboarding@resend.dev>")


def send_email(to: str, subject: str, body: str) -> None:
    if EMAIL_BACKEND == "console":
        print(f"EMAIL to={to} subject={subject!r} body={body!r}")
    elif EMAIL_BACKEND == "resend":
        _send_via_resend(to, subject, body)
    else:
        raise NotImplementedError(f"Unknown EMAIL_BACKEND: {EMAIL_BACKEND!r}")


def _send_via_resend(to: str, subject: str, body: str) -> None:
    """A failed send prints instead of raising — every call site here
    treats send_email() as a fire-and-forget side effect of some other
    action (confirming a match, cancelling a series), and that primary
    action succeeding must never depend on a notification email actually
    going out. Same "don't let the side effect break the main thing"
    reasoning as _mock_charge never actually touching card data."""
    if not RESEND_API_KEY:
        print(f"EMAIL SEND SKIPPED (no RESEND_API_KEY configured) to={to} subject={subject!r}")
        return
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": RESEND_FROM_ADDRESS, "to": [to], "subject": subject, "text": body},
            timeout=8.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as err:
        print(f"EMAIL SEND FAILED to={to} subject={subject!r}: {err}")
