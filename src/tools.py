import difflib
import json
import unicodedata
from pathlib import Path

STORE_DIR = Path(__file__).resolve().parent.parent / "data" / "store"

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


def _load(name: str):
    with open(STORE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _save(name: str, data):
    with open(STORE_DIR / name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _best_match(query: str, candidates: list[str]) -> str | None:
    """Fuzzy-match a spoken/typed name against known item names (handles STT noise, partial
    names, and Arabic/Urdu letterform variants the LLM may generate)."""
    query = _normalize(query.strip().lower())
    normalized = {c: _normalize(c.lower()) for c in candidates}

    for name, norm_name in normalized.items():
        if query in norm_name or norm_name in query:
            return name

    close = difflib.get_close_matches(query, list(normalized.values()), n=1, cutoff=0.5)
    if not close:
        return None
    return next(name for name, norm_name in normalized.items() if norm_name == close[0])


def check_stock(product_name: str) -> str:
    products = _load("stock.json")
    match_name = _best_match(product_name, [p["name"] for p in products])
    if match_name is None:
        return f"'{product_name}' نامی کوئی پروڈکٹ ہمارے پاس نہیں ملا۔"

    product = next(p for p in products if p["name"] == match_name)
    if product["quantity"] <= 0:
        return f"{product['name']} فی الحال اسٹاک میں نہیں ہے۔ قیمت: {product['price']} روپے۔"
    return f"{product['name']} دستیاب ہے۔ قیمت: {product['price']} روپے، اسٹاک میں {product['quantity']} عدد باقی ہیں۔"


def check_appointment_slots(service_name: str) -> str:
    services = _load("services.json")
    match_name = _best_match(service_name, [s["name"] for s in services])
    if match_name is None:
        return f"'{service_name}' نامی کوئی سروس ہمارے پاس نہیں ملی۔"

    service = next(s for s in services if s["name"] == match_name)
    if not service["available_slots"]:
        return f"{service['name']} کے لیے فی الحال کوئی خالی وقت دستیاب نہیں ہے۔"
    slots = "، ".join(service["available_slots"])
    return f"{service['name']} ({service['duration_minutes']} منٹ) کے لیے دستیاب اوقات: {slots}"


def get_menu(item_name: str | None = None) -> str:
    menu = _load("menu.json")
    if item_name:
        match_name = _best_match(item_name, [i["name"] for i in menu["items"]])
        if match_name is None:
            return f"'{item_name}' نامی کوئی ڈش مینو میں نہیں ملی۔"
        item = next(i for i in menu["items"] if i["name"] == match_name)
        return f"{item['name']} - {item['price']} روپے۔ {item['description']}۔"

    lines = [f"{i['name']} ({i['price']} روپے)" for i in menu["items"]]
    return f"آج کی اسپیشل ڈش: {menu['today_special']}۔ مکمل مینو: " + "، ".join(lines)


def recommend_human_agent(reason: str) -> str:
    from . import session_log

    session_log.log_escalation(reason)
    return "میں اس معاملے کے لیے ایک حقیقی نمائندے سے رابطہ کروانے کی سفارش کرتی ہوں۔ وہ جلد آپ سے رابطہ کریں گے۔"


def book_table(date_time: str, party_size: int | str) -> str:
    party_size = int(party_size)  # Groq's tool-calling sometimes emits numbers as strings
    menu = _load("menu.json")
    if date_time not in menu["table_slots"]:
        available = "، ".join(menu["table_slots"]) or "کوئی وقت دستیاب نہیں"
        return f"معذرت، {date_time} پر کوئی میز خالی نہیں۔ دستیاب اوقات: {available}"

    menu["table_slots"].remove(date_time)
    _save("menu.json", menu)

    bookings = _load("bookings.json")
    bookings.append({"date_time": date_time, "party_size": party_size})
    _save("bookings.json", bookings)

    return f"آپ کی میز {date_time} کے لیے {party_size} افراد کے لیے بک ہو گئی ہے۔"


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
            "description": "کسی پروڈکٹ کی اسٹاک دستیابی اور قیمت چیک کریں (نئی خریداری سے پہلے)۔ یہ کسی موجودہ آرڈر کی صورتحال یا ڈیلیوری کی معلومات کے لیے نہیں ہے۔",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string", "description": "پروڈکٹ کا نام جیسا صارف نے بتایا"},
                },
                "required": ["product_name"],
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
