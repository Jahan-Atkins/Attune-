"""
Stripe Connect — lets an instructor connect a Stripe account so the
platform can eventually pay them out for completed sessions. This is
onboarding only: creating the connected account and sending the
instructor through Stripe's own hosted onboarding flow, then checking
whether they came back with transfers enabled. It deliberately does NOT
build the charge/transfer side of payouts — this app's customer payments
are still fully mocked (see routers/bookings.py's _mock_charge), so
there's no real money on the platform's balance to transfer yet. That's
a separate, later project once real customer charging exists.

Uses Stripe's classic v1 Accounts + Account Links API (`type="express"`,
Stripe-hosted onboarding via a redirect) rather than the newer v2
Accounts API / embedded Connect.js components — both are current,
supported paths as of this writing, but the v1 hosted-redirect flow
needs no new client-side JS library and no server-side "account
session"/client-secret handshake, which fits this app's no-build-step,
minimal-dependency frontends far better. ponytail: if this app ever
needs a fully embedded (no-redirect) onboarding UI, migrate to
Connect.js + AccountSessions then — not before it's actually needed.

Same "load and expose a few small functions" shape as google_auth.py —
see that file for why a defensive `load_dotenv()` call belongs here too
(import-order fragility with database.py's own load_dotenv()).
"""
import os

import stripe
from dotenv import load_dotenv

load_dotenv()
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
stripe.api_key = STRIPE_SECRET_KEY


def create_connect_account(email: str) -> str:
    """Creates a new Express connected account requesting only the
    `transfers` capability — this platform is the merchant of record and
    never asks a connected account to accept card payments directly, so
    `card_payments` is never requested. Returns the new account's id."""
    account = stripe.Account.create(
        type="express",
        email=email,
        capabilities={"transfers": {"requested": True}},
    )
    return account.id


def create_onboarding_link(account_id: str, return_url: str, refresh_url: str) -> str:
    """A fresh Account Link is needed every time an instructor starts or
    resumes onboarding — Stripe's own links expire after a few minutes
    and are single-use. `refresh_url` is where Stripe sends the
    instructor back if the link expired or they navigated away
    mid-flow; the caller should generate a new link and redirect them
    there again, exactly like this same function's own return value."""
    link = stripe.AccountLink.create(
        account=account_id,
        type="account_onboarding",
        return_url=return_url,
        refresh_url=refresh_url,
    )
    return link.url


def transfers_enabled(account_id: str) -> bool:
    """Re-checks the connected account's actual capability status with
    Stripe — the only source of truth for whether onboarding is really
    complete. Returning to `return_url` only means the instructor
    finished (or abandoned) the flow, not that Stripe approved them."""
    account = stripe.Account.retrieve(account_id)
    return account.capabilities.get("transfers") == "active"
