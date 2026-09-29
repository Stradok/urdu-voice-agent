"""Dashboard login.

Two modes, chosen by what's configured in the environment:

**Supabase mode** (the real one, plan.md Phase 0 §2): email + password, verification delegated
to Supabase itself rather than reimplementing JWT signature checking here - we forward the
caller's bearer token to Supabase's own /auth/v1/user endpoint, which validates it and returns
the authenticated user (or 401s). One extra network hop per request, acceptable at pilot scale
and avoids tracking Supabase's signing key rotation ourselves. `business_id` is resolved by
matching the verified email against `businesses.owner_email` - for the pilot stage there's
exactly one login per business, provisioned manually at onboarding
(scripts/create_business_account.py), no self-serve signup.

**Local mode** (LOCAL_AUTH_EMAIL set, Supabase absent): added 2026-08 when the Supabase project
became unreachable and the database moved to local Docker Postgres. With Supabase gone there is
no token issuer or verifier left, so this mode **skips token verification entirely** and treats
every request as coming from the business that owns LOCAL_AUTH_EMAIL. That is a genuine
authentication bypass, appropriate only for a single developer on localhost.

Two guards keep it from becoming a production hole: it activates only when Supabase is *not*
configured (so an environment that can still do real auth always does), and it logs a warning
on every startup that it's active.
"""
import logging
import os

import httpx
from fastapi import Header, HTTPException
from sqlalchemy import select

from .business_context import BusinessContext
from .data.db import get_session
from .data.models import Business

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
LOCAL_AUTH_EMAIL = os.environ.get("LOCAL_AUTH_EMAIL")

# Supabase wins whenever it's actually configured - LOCAL_AUTH_EMAIL left set in an environment
# that can still do real auth must never silently downgrade it to no auth at all.
LOCAL_AUTH_MODE = bool(LOCAL_AUTH_EMAIL) and not SUPABASE_URL

if LOCAL_AUTH_MODE:
    logging.warning(
        "AUTH BYPASS ACTIVE: LOCAL_AUTH_EMAIL=%s is set and Supabase is not configured, so "
        "every request is treated as this business's owner without any token verification. "
        "Local development only - never deploy with this set.",
        LOCAL_AUTH_EMAIL,
    )
elif not SUPABASE_URL:
    logging.warning(
        "No auth configured: set SUPABASE_URL/SUPABASE_PUBLISHABLE_KEY for real auth, or "
        "LOCAL_AUTH_EMAIL for local development. Authenticated endpoints will return 500."
    )


def _verify_token(token: str) -> str:
    """Returns the verified user's email, or raises HTTPException(401)."""
    if not SUPABASE_URL:
        raise HTTPException(status_code=500, detail="auth is not configured on this server")
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_PUBLISHABLE_KEY, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="could not reach the auth service")

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid or expired session")

    email = response.json().get("email")
    if not email:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return email


def _business_for_email(email: str) -> BusinessContext:
    with get_session() as session:
        business = session.scalar(select(Business).where(Business.owner_email == email))
        if business is None:
            raise HTTPException(status_code=403, detail="no business is registered to this account")
        return BusinessContext(id=business.id, slug=business.slug, business_type=business.business_type)


def get_current_business(authorization: str = Header(default="")) -> BusinessContext:
    # authorization defaults to "" rather than being required, so local mode doesn't reject a
    # request just for omitting a header it no longer has any way to produce a token for.
    if LOCAL_AUTH_MODE:
        return _business_for_email(LOCAL_AUTH_EMAIL)

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    return _business_for_email(_verify_token(token))
