"""Dashboard login: Supabase Auth, email + password (plan.md Phase 0 §2).

Verification is delegated to Supabase itself rather than reimplementing JWT signature
checking here - we forward the caller's bearer token to Supabase's own /auth/v1/user
endpoint, which validates it and returns the authenticated user (or 401s) . One extra
network hop per request, acceptable at pilot scale and avoids tracking Supabase's signing
key rotation ourselves. `business_id` is resolved by matching the verified email against
`businesses.owner_email` - for the pilot stage there's exactly one login per business,
provisioned manually at onboarding (scripts/create_business_account.py), no self-serve
signup.
"""
import os

import httpx
from fastapi import Header, HTTPException
from sqlalchemy import select

from .business_context import BusinessContext
from .db import get_session
from .models import Business

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_PUBLISHABLE_KEY = os.environ["SUPABASE_PUBLISHABLE_KEY"]


def _verify_token(token: str) -> str:
    """Returns the verified user's email, or raises HTTPException(401)."""
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


def get_current_business(authorization: str = Header(...)) -> BusinessContext:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    email = _verify_token(token)

    with get_session() as session:
        business = session.scalar(select(Business).where(Business.owner_email == email))
        if business is None:
            raise HTTPException(status_code=403, detail="no business is registered to this account")
        return BusinessContext(id=business.id, slug=business.slug, business_type=business.business_type)
