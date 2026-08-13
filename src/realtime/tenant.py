"""Resolves which business a live LiveKit room belongs to - the same BusinessContext shape
src/auth.py resolves per-HTTP-request (bearer token -> Supabase -> business), just from room
metadata instead, since there's no HTTP request/auth header inside a LiveKit room.
"""
import json
import logging
import os
from uuid import UUID

from livekit.agents import JobContext

from ..business_context import BusinessContext
from ..data.db import get_session
from ..data.models import Business

logger = logging.getLogger("livekit.agents")


def resolve_tenant(ctx: JobContext) -> BusinessContext:
    """Room metadata is set by the dashboard when it requests a LiveKit access token for a
    test call: '{"business_id": "..."}'. Only business_id travels in the token - business_type
    (and, at the call site, AppSettings.reply_language) are always read fresh from Postgres
    from there, the same "never cache settings, always re-read" discipline used everywhere
    else in this codebase (see src/agent/llm.py's ChatEngine.reply()), so a business's
    settings changes take effect on their very next call without the token needing to be
    re-minted.

    Real inbound phone calls will need a different resolver later (phone number ->
    business_id via a SIP dispatch rule, not room metadata) - not built yet, this is the seam
    for it; whatever resolves that should also return a BusinessContext so nothing downstream
    needs to care which path resolved it.
    """
    metadata = json.loads(ctx.room.metadata or "{}")
    if "business_id" not in metadata:
        # LiveKit Cloud's own hosted Console test tool (cloud.livekit.io -> Agents -> Launch
        # Console) creates its own room ("console-<hex>") and dispatches us into it with no
        # way to stamp our custom metadata onto it first - it's generic LiveKit tooling, it
        # has no idea our tenant resolution needs business_id. Without this fallback, every
        # Console test session crashes here (confirmed live 2026-08-10: room "console-c02a791a",
        # this exact ValueError). LIVEKIT_TEST_BUSINESS_ID is opt-in and unset in production -
        # a real inbound call arriving with broken/missing metadata must still fail loudly,
        # never silently serve some other business's persona/data.
        test_business_id = os.environ.get("LIVEKIT_TEST_BUSINESS_ID")
        if not test_business_id:
            raise ValueError(
                "room metadata is missing business_id - was the token minted correctly? "
                "(testing via LiveKit's hosted Console? set LIVEKIT_TEST_BUSINESS_ID in .env)"
            )
        logger.warning(
            "room metadata missing business_id - falling back to LIVEKIT_TEST_BUSINESS_ID "
            "(expected only from LiveKit's hosted Console, never in production)",
            extra={"room": ctx.room.name, "fallback_business_id": test_business_id},
        )
        business_id = UUID(test_business_id)
    else:
        business_id = UUID(metadata["business_id"])

    with get_session() as session:
        business = session.get(Business, business_id)
        if business is None:
            raise ValueError(f"room metadata referenced unknown business_id {business_id}")
        return BusinessContext(id=business.id, slug=business.slug, business_type=business.business_type)
