import time
from uuid import UUID

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select

from . import persona, session_log
from . import settings as app_settings
from .audio_devices import list_capture_devices, list_playback_devices
from .auth import get_current_business
from .business_context import BusinessContext
from .db import get_session
from .faq_store import FaqStore
from .llm import LLM_CATALOG, ChatEngine
from .models import MenuItem, ServiceItem, StockItem, TableSlot
from .models import FaqEntry as FaqEntryRow

app = FastAPI(title="Urdu Voice Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local-only desktop app, never exposed beyond localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

# loaded once at startup - the embedding model is expensive to (re)build, and its FAQ
# search methods already take business_id per call, so one instance serves every business
faq_store = FaqStore()

# one ChatEngine per logged-in business, created lazily and reused for the life of the
# process - each keeps its own conversation history/session, same as the single pre-auth
# global did, just keyed by business now instead of pinned to one at startup
_chat_engines: dict[UUID, ChatEngine] = {}


def _get_chat_engine(business: BusinessContext) -> ChatEngine:
    engine = _chat_engines.get(business.id)
    if engine is None:
        engine = ChatEngine(faq_store=faq_store, business_id=business.id, business_type=business.business_type)
        _chat_engines[business.id] = engine
    return engine


# voice pipeline loaded lazily on first use - needs mic hardware + Azure keys, which
# aren't required for text-only chat or the admin pages
_transcriber = None
_speaker = None


def _get_transcriber():
    global _transcriber
    if _transcriber is None:
        from .stt import Transcriber

        _transcriber = Transcriber()
    return _transcriber


def _get_speaker():
    global _speaker
    if _speaker is None:
        from .tts import Speaker

        _speaker = Speaker()
    return _speaker


class ChatMessage(BaseModel):
    message: str


class FaqEntryIn(BaseModel):
    question: str
    answer: str


class ExampleEntry(BaseModel):
    user: str
    assistant: str


@app.post("/chat")
def chat(payload: ChatMessage, business: BusinessContext = Depends(get_current_business)):
    reply = _get_chat_engine(business).reply(payload.message)
    return {"reply": reply}


@app.post("/voice_turn")
def voice_turn(business: BusinessContext = Depends(get_current_business)):
    """Record from the local mic until the user stops talking, transcribe, reply, and
    speak the reply out loud through the local speakers - same pipeline as CLI voice mode,
    triggered here by the mic button in the chat page."""
    from .mic import record

    t0 = time.monotonic()
    wav_path = record()
    t1 = time.monotonic()
    reply_language = app_settings.load_settings(business.id)["reply_language"]
    user_text = _get_transcriber().transcribe(wav_path, reply_language)
    t2 = time.monotonic()
    if not user_text:
        return {"user_text": "", "reply": ""}

    reply = _get_chat_engine(business).reply(user_text)
    t3 = time.monotonic()
    try:
        _get_speaker().say(reply, business.id)
    except Exception as e:
        # the text reply already succeeded - a flaky/slow TTS render (e.g. Azure's
        # real-time-factor watchdog under system load) shouldn't lose the whole turn
        print(f"TTS playback failed, continuing with text-only reply: {e}")
    t4 = time.monotonic()
    print(
        f"[timing] record={t1 - t0:.2f}s stt={t2 - t1:.2f}s llm={t3 - t2:.2f}s tts={t4 - t3:.2f}s "
        f"total={t4 - t0:.2f}s"
    )
    return {"user_text": user_text, "reply": reply}


@app.get("/config/persona")
def get_persona_config(business: BusinessContext = Depends(get_current_business)):
    return persona.load_persona_config(business.id)


@app.put("/config/persona")
def put_persona_config(config: dict, business: BusinessContext = Depends(get_current_business)):
    persona.save_persona_config(business.id, config)
    return config


@app.get("/config/example_bank")
def get_example_bank(business: BusinessContext = Depends(get_current_business)):
    return persona.load_example_bank(business.id)


@app.put("/config/example_bank")
def put_example_bank(examples: list[dict], business: BusinessContext = Depends(get_current_business)):
    persona.save_example_bank(business.id, examples)
    return examples


@app.post("/config/example_bank")
def add_example(entry: ExampleEntry, business: BusinessContext = Depends(get_current_business)):
    persona.add_example(business.id, entry.model_dump())
    return persona.load_example_bank(business.id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/whoami")
def whoami(business: BusinessContext = Depends(get_current_business)):
    return {"business_id": str(business.id), "slug": business.slug, "business_type": business.business_type}


@app.get("/audio/devices")
def get_audio_devices():
    return {"mic_devices": list_capture_devices(), "speaker_devices": list_playback_devices()}


@app.get("/config/llm_models")
def list_llm_models():
    # dict insertion order in LLM_CATALOG is already best-to-worst by real Urdu accuracy
    # (see src/llm.py's comment) - preserved here for the dropdown's option order.
    return [{"value": key, "label": entry["label"], "note": entry["note"]} for key, entry in LLM_CATALOG.items()]


@app.get("/config/settings")
def get_settings(business: BusinessContext = Depends(get_current_business)):
    return app_settings.load_settings(business.id)


@app.put("/config/settings")
def put_settings(settings: dict, business: BusinessContext = Depends(get_current_business)):
    app_settings.save_settings(business.id, settings)
    return settings


def _faq_list(business_id: UUID):
    with get_session() as session:
        rows = session.scalars(select(FaqEntryRow).where(FaqEntryRow.business_id == business_id)).all()
        return [{"id": str(r.id), "question": r.question, "answer": r.answer} for r in rows]


@app.get("/faq")
def get_faq(business: BusinessContext = Depends(get_current_business)):
    return _faq_list(business.id)


@app.put("/faq")
def put_faq(entries: list[FaqEntryIn], business: BusinessContext = Depends(get_current_business)):
    # ids are client-side React keys only (see frontend/src/pages/FaqPage.tsx) - the
    # server always assigns its own on write, so this is a full replace, not a merge.
    with get_session() as session:
        session.query(FaqEntryRow).filter(FaqEntryRow.business_id == business.id).delete()
        for entry in entries:
            session.add(FaqEntryRow(business_id=business.id, question=entry.question, answer=entry.answer))
    faq_store.sync_embeddings(business.id)
    return _faq_list(business.id)


@app.post("/faq")
def add_faq(entry: FaqEntryIn, business: BusinessContext = Depends(get_current_business)):
    with get_session() as session:
        session.add(FaqEntryRow(business_id=business.id, question=entry.question, answer=entry.answer))
    faq_store.sync_embeddings(business.id)
    return _faq_list(business.id)


@app.delete("/faq/{entry_id}")
def delete_faq(entry_id: str, business: BusinessContext = Depends(get_current_business)):
    try:
        entry_uuid = UUID(entry_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="no FAQ entry with this id")

    with get_session() as session:
        row = session.scalar(
            select(FaqEntryRow).where(FaqEntryRow.id == entry_uuid, FaqEntryRow.business_id == business.id)
        )
        if row is None:
            raise HTTPException(status_code=404, detail="no FAQ entry with this id")
        session.delete(row)
    return _faq_list(business.id)


def _stock_list(business_id: UUID):
    with get_session() as session:
        rows = session.scalars(select(StockItem).where(StockItem.business_id == business_id)).all()
        return [{"id": str(r.id), "name": r.name, "price": float(r.price), "quantity": r.quantity} for r in rows]


@app.get("/store/stock")
def get_stock(business: BusinessContext = Depends(get_current_business)):
    return _stock_list(business.id)


@app.put("/store/stock")
async def put_stock(request: Request, business: BusinessContext = Depends(get_current_business)):
    items = await request.json()
    with get_session() as session:
        session.query(StockItem).filter(StockItem.business_id == business.id).delete()
        for item in items:
            session.add(StockItem(business_id=business.id, name=item["name"], price=item["price"], quantity=item["quantity"]))
    return _stock_list(business.id)


def _services_list(business_id: UUID):
    with get_session() as session:
        rows = session.scalars(select(ServiceItem).where(ServiceItem.business_id == business_id)).all()
        return [
            {"id": str(r.id), "name": r.name, "duration_minutes": r.duration_minutes, "available_slots": r.available_slots}
            for r in rows
        ]


@app.get("/store/services")
def get_services(business: BusinessContext = Depends(get_current_business)):
    return _services_list(business.id)


@app.put("/store/services")
async def put_services(request: Request, business: BusinessContext = Depends(get_current_business)):
    items = await request.json()
    with get_session() as session:
        session.query(ServiceItem).filter(ServiceItem.business_id == business.id).delete()
        for item in items:
            session.add(ServiceItem(
                business_id=business.id, name=item["name"], duration_minutes=item["duration_minutes"],
                available_slots=item["available_slots"],
            ))
    return _services_list(business.id)


def _menu_data(business_id: UUID):
    with get_session() as session:
        items = session.scalars(select(MenuItem).where(MenuItem.business_id == business_id)).all()
        slots = session.scalars(select(TableSlot.date_time).where(TableSlot.business_id == business_id)).all()
        today_special = next((i.name for i in items if i.is_today_special), "")
        return {
            "today_special": today_special,
            "items": [{"name": i.name, "price": float(i.price), "description": i.description} for i in items],
            "table_slots": list(slots),
        }


@app.get("/store/menu")
def get_menu_data(business: BusinessContext = Depends(get_current_business)):
    return _menu_data(business.id)


@app.put("/store/menu")
async def put_menu_data(request: Request, business: BusinessContext = Depends(get_current_business)):
    menu = await request.json()
    with get_session() as session:
        session.query(MenuItem).filter(MenuItem.business_id == business.id).delete()
        session.query(TableSlot).filter(TableSlot.business_id == business.id).delete()
        for item in menu["items"]:
            session.add(MenuItem(
                business_id=business.id, name=item["name"], price=item["price"], description=item.get("description", ""),
                is_today_special=(item["name"] == menu.get("today_special")),
            ))
        for slot in menu["table_slots"]:
            session.add(TableSlot(business_id=business.id, date_time=slot))
    return _menu_data(business.id)


@app.get("/sessions")
def get_sessions(business: BusinessContext = Depends(get_current_business)):
    return session_log.list_sessions(business.id)


@app.get("/escalations")
def get_escalations(business: BusinessContext = Depends(get_current_business)):
    return session_log.list_escalations(business.id)
