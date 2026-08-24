"""
"Sign in with Google" — verifies the ID token a browser's Google
Identity Services button hands back. Uses Google's own google-auth
library rather than hand-rolled JWT verification: checking a token's
signature against Google's rotating public keys, and its audience/
issuer/expiry, is security-critical, and google-auth is the correct,
well-vetted way to do it, not something worth reimplementing.

GOOGLE_CLIENT_ID goes in backend/.env locally and Render's Environment
tab in production (same pattern as SECRET_KEY/RESEND_API_KEY — never
committed, never pasted into chat). It's not secret — Google client IDs
are public identifiers safe to expose to the browser — but the routes
that call verify_google_id_token() below need it configured to actually
verify anything, so GET /api/config also serves it to the frontend
(deciding whether to render a "Sign in with Google" button at all).

Deliberately NOT wired up for Admin accounts — see models.Admin's
docstring: there is no public signup path for that account type,
anywhere, on purpose, and a Google sign-in route that auto-creates an
admin account by email would defeat that entirely.
"""
import os

from dotenv import load_dotenv
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

# database.py also calls this, but this module's GOOGLE_CLIENT_ID is read
# at import time too, and main.py imports google_auth before models (and
# therefore before database.py's load_dotenv() has had a chance to run —
# see main.py's `from . import geo, google_auth, models, schemas`, where
# import order is left-to-right). Without this, a real GOOGLE_CLIENT_ID in
# backend/.env silently read as None locally: os.getenv() ran before the
# .env file was ever loaded into the process's environment. Calling it
# again here is a safe no-op once database.py also has, and does nothing
# at all in production, where Render sets real environment variables
# directly rather than through a .env file.
load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


def verify_google_id_token(token: str):
    """Returns {"email": str, "name": str} on success, or None if the
    token is invalid, expired, or wasn't issued for this app (wrong
    audience) — callers turn None into a 401, same "fail fast with a
    clear message" pattern as every other auth check in this app. Raises
    only if GOOGLE_CLIENT_ID itself isn't configured — that's a deploy-
    time problem, not something a bad token from a user should be
    confused with."""
    if not GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured.")
    try:
        payload = google_id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
    except ValueError:
        return None
    email = payload.get("email")
    if not email:
        return None
    return {"email": email, "name": payload.get("name") or email.split("@")[0]}
