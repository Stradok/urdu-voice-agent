"""Pre-auth seam: resolves the one business this process serves.

Multi-tenant login (plan.md Phase 0 §2) doesn't exist yet - every request in the
FastAPI app and the CLI is served by a single business, chosen by DEFAULT_BUSINESS_SLUG
in .env. Once dashboard/widget auth lands, callers stop using this module and resolve
business_id from the request (JWT or widget_key) instead - everything downstream
(persona, settings, faq_store, tools, session_log) already takes business_id as a
parameter for exactly that reason.
"""
import os
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

from sqlalchemy import select

from .data.db import get_session
from .data.models import Business

DEFAULT_BUSINESS_SLUG = os.environ.get("DEFAULT_BUSINESS_SLUG", "default")


@dataclass(frozen=True)
class BusinessContext:
    id: UUID
    slug: str
    business_type: str


@lru_cache
def get_default_business() -> BusinessContext:
    with get_session() as session:
        business = session.scalar(select(Business).where(Business.slug == DEFAULT_BUSINESS_SLUG))
        if business is None:
            raise RuntimeError(
                f"no business with slug '{DEFAULT_BUSINESS_SLUG}' - run "
                f"`.venv/bin/python scripts/seed_default_business.py` first"
            )
        return BusinessContext(id=business.id, slug=business.slug, business_type=business.business_type)
