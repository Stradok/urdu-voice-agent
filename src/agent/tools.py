import difflib
import math
import unicodedata
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from . import scheduling
from ..data.db import get_session
from ..data.models import Appointment, AppointmentSlot, AppSettings, Booking, MenuItem, ServiceItem, StockItem, TableSlot
from ..data.reference_codes import create_with_reference_code

# Weekday names for slot display - date.weekday() convention (0=Monday..6=Sunday), matching
# BusinessHours. Digits for day/month rather than Urdu month names, to stay unambiguous
# when read aloud and easy for the model to copy back verbatim in book_appointment.
_WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_SLOT_FORMAT = "%Y-%m-%d %H:%M"


def _format_slot(dt: datetime) -> str:
    label = f"{_WEEKDAY_EN[dt.weekday()]} {dt.day:02d}/{dt.month:02d} {dt.hour:02d}:{dt.minute:02d}"
    return f"{label} ({dt.strftime(_SLOT_FORMAT)})"

# Cross-language name matching: a business may catalog its products/services in English
# (e.g. "Teeth Cleaning") while a customer asks in native Urdu ("دانتوں کی صفائی") - no
# shared characters, so difflib/substring matching (below) never bridges that gap. Loaded
# lazily since not every tool call needs it (loanword/transliterated queries like
# "ایئربڈز" for "earbuds" already match lexically).
_embedder = None
_NAME_MATCH_SIMILARITY_THRESHOLD = 0.75
# How far the top embedding score must clear the runner-up to count as a confident single
# match rather than an ambiguous one - see _rank_by_embedding for why this exists.
_CONFIDENT_MARGIN = 0.03


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer("intfloat/multilingual-e5-small", device="cpu")
    return _embedder

# LLMs frequently generate Urdu text using Arabic-script letterform variants that look
# near-identical but are different codepoints (e.g. Arabic Yeh vs. Urdu Yeh) - normalize
# both sides before comparing so lookups don't silently fail to match.
_CHAR_NORMALIZE = str.maketrans({
    "ي": "ی",  # Arabic Yeh -> Urdu Yeh (ي -> ی)
    "ى": "ی",  # Alef Maksura -> Urdu Yeh (ى -> ی)
    "ك": "ک",  # Arabic Kaf -> Urdu Keheh (ك -> ک)
    "ة": "ہ",  # Teh Marbuta -> Heh (ة -> ہ)
})


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_CHAR_NORMALIZE)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _rank_by_embedding(query: str, candidates: list[str]) -> list[tuple[str, float]]:
    embedder = _get_embedder()
    query_emb = embedder.encode(["query: " + query], normalize_embeddings=True)[0]
    candidate_embs = embedder.encode(["passage: " + c for c in candidates], normalize_embeddings=True)
    scores = candidate_embs @ query_emb
    return sorted(zip(candidates, scores), key=lambda pair: -pair[1])


def _best_match(query: str, candidates: list[str]) -> str | None:
    """Single confident match only - via exact/lexical matching, or an embedding match that
    clearly stands out from the rest. Returns None when nothing is confident (either no
    lexical overlap and no clear embedding winner) - see _closest_matches for that case."""
    if not candidates:
        return None

    norm_query = _normalize(query.strip().lower())
    normalized = {c: _normalize(c.lower()) for c in candidates}

    for name, norm_name in normalized.items():
        if norm_query in norm_name or norm_name in norm_query:
            return name

    close = difflib.get_close_matches(norm_query, list(normalized.values()), n=1, cutoff=0.5)
    if close:
        return next(name for name, norm_name in normalized.items() if norm_name == close[0])

    # Lexical matching failed - likely a genuine cross-language query (a native-Urdu phrase
    # against an English catalog entry) or a near-miss mishearing ("kirta" for "Kurta").
    # Only accept the embedding top pick if it's a clear standout, not just the argmax of a
    # noisy comparison - see _closest_matches's docstring for why that distinction matters.
    ranked = _rank_by_embedding(query, candidates)
    top_name, top_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else -1.0
    if top_score >= _NAME_MATCH_SIMILARITY_THRESHOLD and top_score - runner_up_score >= _CONFIDENT_MARGIN:
        return top_name
    return None


def _closest_matches(query: str, candidates: list[str], top_k: int = 5) -> list[str]:
    """Cross-language/uncertain fallback for when _best_match finds nothing confident -
    likely a generic category word ("pants") not literally in, or clearly close to, any
    catalog name. Returns several candidates for the caller to present as options, not a
    single silent pick.

    Live testing (2026-08-08) showed why a single top-1 pick is unsafe here: for the query
    "pants" against a 5-item clothing catalog, multilingual-e5-small scored every single
    item within 0.006 of each other (0.800-0.808) regardless of actual relevance - the
    correct answer ("Men's Slim Fit Jeans") scored *lower* than an unrelated dress, so
    picking the argmax silently returned the wrong product with total confidence. Same
    failure class as the FAQ retrieval top-1 bug (src/faq_store.py) - hand the ambiguity to
    the LLM instead of resolving it with one noisy float comparison."""
    if not candidates:
        return []

    ranked = _rank_by_embedding(query, candidates)
    return [name for name, score in ranked[:top_k] if score >= _NAME_MATCH_SIMILARITY_THRESHOLD]


def check_stock(business_id: UUID, product_name: str | None = None) -> str:
    with get_session() as session:
        products = session.scalars(select(StockItem).where(StockItem.business_id == business_id)).all()

        if not product_name:
            lines = [
                f"{p.name} ({p.price} PKR" + (f", {p.quantity} in stock)" if p.quantity > 0 else ", out of stock)")
                for p in products
            ]
            return "We have these products available: " + ", ".join(lines)

        all_names = [p.name for p in products]
        match_name = _best_match(product_name, all_names)
        if match_name is None:
            closest = _closest_matches(product_name, all_names)
            if not closest:
                return f"No product named '{product_name}' was found."
            options = ", ".join(
                f"{p.name} ({p.price} PKR" + (f", {p.quantity} in stock)" if p.quantity > 0 else ", out of stock)")
                for p in products if p.name in closest
            )
            return f"No product exactly named '{product_name}' was found, but here are similar options: {options}."

        product = next(p for p in products if p.name == match_name)
        if product.quantity <= 0:
            return f"{product.name} is currently out of stock. Price: {product.price} PKR."
        return f"{product.name} is available. Price: {product.price} PKR, {product.quantity} left in stock."


def _resolve_service(session, business_id: UUID, service_name: str) -> tuple[ServiceItem | None, str | None]:
    """Shared by check_appointment_slots and book_appointment - resolve a spoken/typed
    service name, or return an error string (already includes closest-match suggestions)."""
    services = session.scalars(select(ServiceItem).where(ServiceItem.business_id == business_id)).all()
    all_names = [s.name for s in services]
    match_name = _best_match(service_name, all_names)
    if match_name is not None:
        return next(s for s in services if s.name == match_name), None

    closest = _closest_matches(service_name, all_names)
    if not closest:
        return None, f"No service named '{service_name}' was found."
    return None, f"No service exactly named '{service_name}' was found, but here are similar services available: {', '.join(closest)}."


def check_appointment_slots(business_id: UUID, service_name: str) -> str:
    with get_session() as session:
        service, error = _resolve_service(session, business_id, service_name)
        if error:
            return error

        settings = session.get(AppSettings, business_id)
        scheduling.ensure_slots_generated(session, business_id)
        starts = scheduling.find_available_starts(
            session, business_id, service.duration_minutes, settings.slot_duration_minutes,
            after=scheduling.now_local(settings.timezone), limit=6,
        )
        if not starts:
            return f"There are currently no open slots available for {service.name}."
        options = ", ".join(_format_slot(dt) for dt in starts)
        return (
            f"Available times for {service.name} ({service.duration_minutes} min): {options} - "
            "when booking, use the part inside the parentheses () exactly as given."
        )


def book_appointment(
    business_id: UUID, session_id: UUID | None, service_name: str, slot_start: str, customer_name: str
) -> str:
    with get_session() as session:
        service, error = _resolve_service(session, business_id, service_name)
        if error:
            return error

        try:
            requested_start = datetime.strptime(slot_start.strip(), _SLOT_FORMAT)
        except ValueError:
            return "The given time wasn't understood. Re-check available slots via check_appointment_slots first and use that exact format."

        settings = session.get(AppSettings, business_id)
        scheduling.ensure_slots_generated(session, business_id)

        needed = max(1, math.ceil(service.duration_minutes / settings.slot_duration_minutes))
        step = timedelta(minutes=settings.slot_duration_minutes)
        # Row-lock the exact candidate slots before validating, so a concurrent booking
        # attempt against the same time can't also claim them before this commits.
        candidate_rows = session.scalars(
            select(AppointmentSlot)
            .where(
                AppointmentSlot.business_id == business_id,
                AppointmentSlot.starts_at >= requested_start,
                AppointmentSlot.starts_at < requested_start + step * needed,
            )
            .order_by(AppointmentSlot.starts_at)
            .with_for_update()
        ).all()

        valid = (
            len(candidate_rows) == needed
            and candidate_rows[0].starts_at == requested_start
            and all(r.status == "open" for r in candidate_rows)
            and all(candidate_rows[i + 1].starts_at - candidate_rows[i].starts_at == step for i in range(needed - 1))
            and requested_start >= scheduling.now_local(settings.timezone)
        )
        if not valid:
            alternatives = scheduling.find_available_starts(
                session, business_id, service.duration_minutes, settings.slot_duration_minutes,
                after=scheduling.now_local(settings.timezone), limit=5,
            )
            options = ", ".join(_format_slot(dt) for dt in alternatives) or "no times available"
            return f"Sorry, that time is no longer available. Available times: {options}"

        appointment = create_with_reference_code(
            session, Appointment, "appointment",
            business_id=business_id, session_id=session_id, service_id=service.id,
            service_name=service.name, customer_name=customer_name,
            starts_at=requested_start, duration_minutes=service.duration_minutes,
        )
        for row in candidate_rows:
            row.status = "booked"
            row.appointment_id = appointment.id

    return (
        f"Appointment confirmed: {customer_name}, {service.name}, {_format_slot(requested_start)}. "
        f"Reference code: {appointment.reference_code} - read this code back to the customer one digit at a time, clearly."
    )


def get_menu(business_id: UUID, item_name: str | None = None) -> str:
    with get_session() as session:
        items = session.scalars(select(MenuItem).where(MenuItem.business_id == business_id)).all()

        if item_name:
            all_names = [i.name for i in items]
            match_name = _best_match(item_name, all_names)
            if match_name is None:
                closest = _closest_matches(item_name, all_names)
                if not closest:
                    return f"No dish named '{item_name}' was found on the menu."
                options = ", ".join(f"{i.name} ({i.price} PKR)" for i in items if i.name in closest)
                return f"No dish exactly named '{item_name}' was found, but here are similar dishes available: {options}."
            item = next(i for i in items if i.name == match_name)
            return f"{item.name} - {item.price} PKR. {item.description}."

        today_special = next((i.name for i in items if i.is_today_special), None)
        lines = [f"{i.name} ({i.price} PKR)" for i in items]
        prefix = f"Today's special: {today_special}. " if today_special else ""
        return f"{prefix}Full menu: " + ", ".join(lines)


def recommend_human_agent(business_id: UUID, session_id: UUID, reason: str) -> str:
    from ..data import session_log

    code = session_log.log_escalation(business_id, session_id, reason)
    # Deliberately not a ready-made customer-facing sentence: an earlier version returned
    # one, and the model just echoed it verbatim instead of composing a reply from its own
    # persona/tone rules - dropping any empathy the persona's guardrails call for (e.g. a
    # patient in pain). This is status/meta content for the model to react to, not a script.
    return (
        f"Escalation logged (ticket number: {code}); a human team member has been notified "
        "and will follow up soon. Now write the reply to the customer yourself, in their "
        "language and your usual tone - acknowledge what they told you with genuine empathy, "
        "clearly read back the ticket number one digit at a time so it's unambiguous, then "
        "mention that a team member will follow up."
    )


def book_table(business_id: UUID, date_time: str, party_size: int | str) -> str:
    party_size = int(party_size)  # Groq's tool-calling sometimes emits numbers as strings
    with get_session() as session:
        slot = session.scalar(
            select(TableSlot).where(TableSlot.business_id == business_id, TableSlot.date_time == date_time)
        )
        if slot is None:
            remaining = session.scalars(select(TableSlot.date_time).where(TableSlot.business_id == business_id)).all()
            available = ", ".join(remaining) or "no times available"
            return f"Sorry, no table is free at {date_time}. Available times: {available}"

        session.delete(slot)
        session.add(Booking(business_id=business_id, date_time=date_time, party_size=party_size))

    return f"Your table for {party_size} people at {date_time} is booked."


# Tool functions all take business_id (and recommend_human_agent/book_appointment
# additionally take session_id, for escalation/appointment traceability back to the
# conversation) as their first argument(s) - bound by ChatEngine at the call site, never
# exposed to the LLM or listed in TOOL_SCHEMAS below.
TOOLS_BY_NAME = {
    "check_stock": check_stock,
    "check_appointment_slots": check_appointment_slots,
    "book_appointment": book_appointment,
    "get_menu": get_menu,
    "book_table": book_table,
    "recommend_human_agent": recommend_human_agent,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check a product's stock availability and price (before a new purchase). If the customer asks for the full inventory/all products (e.g. \"what do you have\", \"show me everything\"), leave product_name empty - the full list will be returned. This is not for existing order status or delivery information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "Product name as the customer said it (leave empty for the full list)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_appointment_slots",
            "description": "Check available appointment times for a service (e.g. teeth cleaning).",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Service name as the customer said it"},
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Confirm/book an appointment. Only book at a time that check_appointment_slots actually showed - never write a guessed time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Service name as the customer said it"},
                    "slot_start": {
                        "type": "string",
                        "description": "The time given inside the parentheses () from check_appointment_slots' result, in the exact same format (e.g. '2026-08-11 10:00')",
                    },
                    "customer_name": {"type": "string", "description": "Customer's name"},
                },
                "required": ["service_name", "slot_start", "customer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_menu",
            "description": "Look up the restaurant's menu, today's special dish, or a specific dish's price/details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Specific dish name (optional - if omitted, the full menu is returned)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_table",
            "description": "Book a table at the restaurant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_time": {
                        "type": "string",
                        "description": "Booking date and time, in exactly the same format as given in the available-times list (e.g. '2026-08-05 19:00')",
                    },
                    "party_size": {"type": "string", "description": "How many people the table is for (as a number)"},
                },
                "required": ["date_time", "party_size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_human_agent",
            "description": "Call this function when the matter is sensitive (severe anger, threats, health/legal/financial risk) or you can't resolve it yourself, so a real representative can reach out.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Brief reason why a human representative is needed"},
                },
                "required": ["reason"],
            },
        },
    },
]

# Which tools a business's agent is even offered, by business_type - not just which tools
# *execute* correctly (business_id-scoping above already handles that), but which ones the
# model can see at all. A dentist's agent never sees check_stock; a store's never sees
# check_appointment_slots. This directly shrinks the space of wrong-tool guesses the model
# can make (see plan.md, Phase 0 §2, the 2026-08-07 dental/book mix-up bug this addresses).
# "demo" is the original single seeded business, spanning every domain on purpose so it
# stays useful for regression testing - real businesses always get a narrower type.
BUSINESS_TYPE_TOOLS = {
    "demo": list(TOOLS_BY_NAME),
    "dentist_clinic": ["check_appointment_slots", "book_appointment", "recommend_human_agent"],
    "retail_store": ["check_stock", "recommend_human_agent"],
    "clothing_brand": ["check_stock", "recommend_human_agent"],
    "restaurant": ["get_menu", "book_table", "recommend_human_agent"],
    "bank": ["recommend_human_agent"],
}


def tool_schemas_for(business_type: str) -> list[dict]:
    allowed = set(BUSINESS_TYPE_TOOLS.get(business_type, ["recommend_human_agent"]))
    return [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] in allowed]
