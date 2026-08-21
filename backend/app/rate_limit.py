"""
In-memory rate limiting — the app's only brute-force protection on
login and forgot-password today. Deliberately in-process (a plain
dict), not Redis-backed: this app runs as a single process (see
LAUNCH-ROADMAP.md's note on Render's free tier), so a shared, persistent
store would be solving a scaling problem this deployment doesn't have
yet. If a future deploy runs multiple workers/instances, swap the dict
below for Redis — the call sites (check_rate_limit/record_failed_attempt/
reset_attempts) wouldn't need to change.

Keyed by (scope, client IP, identifier) so a login lockout and a
forgot-password lockout for the same email never bleed into each other,
and one identifier's attempts never count against a different one.
"""
import time
from collections import defaultdict
from threading import Lock

from fastapi import HTTPException, Request, status

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60  # 15 minutes

_attempts = defaultdict(list)  # key -> [timestamp, ...], oldest first
_lock = Lock()


def _key(scope: str, request: Request, identifier: str) -> str:
    client_ip = request.client.host if request.client else "unknown"
    return f"{scope}:{client_ip}:{identifier.lower()}"


def check_rate_limit(scope: str, request: Request, identifier: str) -> None:
    """Call before doing any real work. Raises 429 if this
    (scope, IP, identifier) has hit MAX_ATTEMPTS within WINDOW_SECONDS."""
    key = _key(scope, request, identifier)
    now = time.time()
    with _lock:
        recent = [t for t in _attempts[key] if now - t < WINDOW_SECONDS]
        _attempts[key] = recent
        if len(recent) >= MAX_ATTEMPTS:
            retry_after = max(1, int(WINDOW_SECONDS - (now - recent[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )


def record_failed_attempt(scope: str, request: Request, identifier: str) -> None:
    _attempts[_key(scope, request, identifier)].append(time.time())


def reset_attempts(scope: str, request: Request, identifier: str) -> None:
    """Called on a successful login so a legitimate user who mistyped
    their password a few times isn't left with a lingering count."""
    _attempts.pop(_key(scope, request, identifier), None)


def reset_all() -> None:
    """Test-only: clears all state between tests (see conftest.py) so
    one test's failed attempts can never lock out another."""
    _attempts.clear()
