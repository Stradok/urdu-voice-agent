import difflib
import unicodedata
from uuid import UUID

from sqlalchemy import select

from .db import get_session
from .models import Booking, MenuItem, ServiceItem, StockItem, TableSlot

# Cross-language name matching: a business may catalog its products/services in English
# (e.g. "Teeth Cleaning") while a customer asks in native Urdu ("دانتوں کی صفائی") - no
# shared characters, so difflib/substring matching (below) never bridges that gap. Loaded
# lazily since not every tool call needs it (loanword/transliterated queries like
# "ایئربڈز" for "earbuds" already match lexically).
_embedder = None
_NAME_MATCH_SIMILARITY_THRESHOLD = 0.75


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


def _best_match(query: str, candidates: list[str]) -> str | None:
    """Fuzzy-match a spoken/typed name against known item names (handles STT noise, partial
    names, and Arabic/Urdu letterform variants the LLM may generate)."""
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

    # lexical matching failed - likely a genuine cross-language query (a native-Urdu
    # phrase against an English-language catalog entry), not just STT noise. Fall back to
    # multilingual embedding similarity.
    embedder = _get_embedder()
    query_emb = embedder.encode(["query: " + query], normalize_embeddings=True)[0]
    candidate_embs = embedder.encode(["passage: " + c for c in candidates], normalize_embeddings=True)
    scores = candidate_embs @ query_emb
    best_idx = int(scores.argmax())
    if scores[best_idx] < _NAME_MATCH_SIMILARITY_THRESHOLD:
        return None
    return candidates[best_idx]


def check_stock(business_id: UUID, product_name: str | None = None) -> str:
    with get_session() as session:
        products = session.scalars(select(StockItem).where(StockItem.business_id == business_id)).all()

        if not product_name:
            lines = [
                f"{p.name} ({p.price} روپے" + (f"، {p.quantity} عدد دستیاب)" if p.quantity > 0 else "، اسٹاک ختم)")
                for p in products
            ]
            return "ہمارے پاس یہ پروڈکٹس دستیاب ہیں: " + "، ".join(lines)

        match_name = _best_match(product_name, [p.name for p in products])
        if match_name is None:
            return f"'{product_name}' نامی کوئی پروڈکٹ ہمارے پاس نہیں ملا۔"

        product = next(p for p in products if p.name == match_name)
        if product.quantity <= 0:
            return f"{product.name} فی الحال اسٹاک میں نہیں ہے۔ قیمت: {product.price} روپے۔"
        return f"{product.name} دستیاب ہے۔ قیمت: {product.price} روپے، اسٹاک میں {product.quantity} عدد باقی ہیں۔"


def check_appointment_slots(business_id: UUID, service_name: str) -> str:
    with get_session() as session:
        services = session.scalars(select(ServiceItem).where(ServiceItem.business_id == business_id)).all()
        match_name = _best_match(service_name, [s.name for s in services])
        if match_name is None:
            return f"'{service_name}' نامی کوئی سروس ہمارے پاس نہیں ملی۔"

        service = next(s for s in services if s.name == match_name)
        if not service.available_slots:
            return f"{service.name} کے لیے فی الحال کوئی خالی وقت دستیاب نہیں ہے۔"
        slots = "، ".join(service.available_slots)
        return f"{service.name} ({service.duration_minutes} منٹ) کے لیے دستیاب اوقات: {slots}"


def get_menu(business_id: UUID, item_name: str | None = None) -> str:
    with get_session() as session:
        items = session.scalars(select(MenuItem).where(MenuItem.business_id == business_id)).all()

        if item_name:
            match_name = _best_match(item_name, [i.name for i in items])
            if match_name is None:
                return f"'{item_name}' نامی کوئی ڈش مینو میں نہیں ملی۔"
            item = next(i for i in items if i.name == match_name)
            return f"{item.name} - {item.price} روپے۔ {item.description}۔"

        today_special = next((i.name for i in items if i.is_today_special), None)
        lines = [f"{i.name} ({i.price} روپے)" for i in items]
        prefix = f"آج کی اسپیشل ڈش: {today_special}۔ " if today_special else ""
        return f"{prefix}مکمل مینو: " + "، ".join(lines)


def recommend_human_agent(business_id: UUID, session_id: UUID, reason: str) -> str:
    from . import session_log

    session_log.log_escalation(business_id, session_id, reason)
    # Deliberately not a ready-made customer-facing sentence: an earlier version returned
    # one, and the model just echoed it verbatim instead of composing a reply from its own
    # persona/tone rules - dropping any empathy the persona's guardrails call for (e.g. a
    # patient in pain). This is status/meta content for the model to react to, not a script.
    return (
        "Escalation logged; a human team member has been notified and will follow up soon. "
        "Now write the reply to the customer yourself, in their language and your usual tone - "
        "acknowledge what they told you with genuine empathy before mentioning that a team "
        "member will follow up."
    )


def book_table(business_id: UUID, date_time: str, party_size: int | str) -> str:
    party_size = int(party_size)  # Groq's tool-calling sometimes emits numbers as strings
    with get_session() as session:
        slot = session.scalar(
            select(TableSlot).where(TableSlot.business_id == business_id, TableSlot.date_time == date_time)
        )
        if slot is None:
            remaining = session.scalars(select(TableSlot.date_time).where(TableSlot.business_id == business_id)).all()
            available = "، ".join(remaining) or "کوئی وقت دستیاب نہیں"
            return f"معذرت، {date_time} پر کوئی میز خالی نہیں۔ دستیاب اوقات: {available}"

        session.delete(slot)
        session.add(Booking(business_id=business_id, date_time=date_time, party_size=party_size))

    return f"آپ کی میز {date_time} کے لیے {party_size} افراد کے لیے بک ہو گئی ہے۔"


# Tool functions all take business_id (and recommend_human_agent additionally takes
# session_id) as their first argument(s) - bound by ChatEngine at the call site, never
# exposed to the LLM or listed in TOOL_SCHEMAS below.
TOOLS_BY_NAME = {
    "check_stock": check_stock,
    "check_appointment_slots": check_appointment_slots,
    "get_menu": get_menu,
    "book_table": book_table,
    "recommend_human_agent": recommend_human_agent,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "کسی پروڈکٹ کی اسٹاک دستیابی اور قیمت چیک کریں (نئی خریداری سے پہلے)۔ اگر صارف پورا سامان/تمام پروڈکٹس کی فہرست مانگے (مثلاً \"آپ کے پاس کیا کیا ہے\"، \"سب کچھ دکھائیں\") تو product_name خالی چھوڑ دیں — پوری فہرست واپس آئے گی۔ یہ کسی موجودہ آرڈر کی صورتحال یا ڈیلیوری کی معلومات کے لیے نہیں ہے۔",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "پروڈکٹ کا نام جیسا صارف نے بتایا (پوری فہرست کے لیے خالی چھوڑ دیں)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_appointment_slots",
            "description": "کسی سروس (مثلاً دانتوں کی صفائی) کے لیے دستیاب اپائنٹمنٹ اوقات چیک کریں۔",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "سروس کا نام جیسا صارف نے بتایا"},
                },
                "required": ["service_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_menu",
            "description": "ریسٹورنٹ کا مینو، آج کی اسپیشل ڈش، یا کسی مخصوص ڈش کی قیمت/تفصیل معلوم کریں۔",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "مخصوص ڈش کا نام (اختیاری - نہ دیا جائے تو پورا مینو واپس ہوگا)",
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
            "description": "ریسٹورنٹ میں میز بک کریں۔",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_time": {
                        "type": "string",
                        "description": "بکنگ کی تاریخ اور وقت، بالکل اسی فارمیٹ میں جیسا دستیاب اوقات کی فہرست میں دیا گیا ہو (مثلاً '2026-08-05 19:00')",
                    },
                    "party_size": {"type": "string", "description": "کتنے افراد کے لیے میز چاہیے (عدد کی صورت میں)"},
                },
                "required": ["date_time", "party_size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_human_agent",
            "description": "جب معاملہ حساس ہو (شدید غصہ، دھمکی، صحت/قانونی/مالی خطرہ) یا آپ خود حل نہ کر سکیں تو یہ فنکشن کال کریں تاکہ ایک حقیقی نمائندہ رابطہ کرے۔",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "مختصر وجہ کہ کیوں انسانی نمائندے کی ضرورت ہے"},
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
    "dentist_clinic": ["check_appointment_slots", "recommend_human_agent"],
    "retail_store": ["check_stock", "recommend_human_agent"],
    "clothing_brand": ["check_stock", "recommend_human_agent"],
    "restaurant": ["get_menu", "book_table", "recommend_human_agent"],
    "bank": ["recommend_human_agent"],
}


def tool_schemas_for(business_type: str) -> list[dict]:
    allowed = set(BUSINESS_TYPE_TOOLS.get(business_type, ["recommend_human_agent"]))
    return [schema for schema in TOOL_SCHEMAS if schema["function"]["name"] in allowed]
