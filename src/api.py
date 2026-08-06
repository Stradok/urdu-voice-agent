import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import persona, session_log
from . import settings as app_settings
from .faq_store import FaqStore
from .llm import ChatEngine

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FAQ_PATH = DATA_DIR / "faq" / "faq.json"
STORE_FILES = {
    "stock": DATA_DIR / "store" / "stock.json",
    "services": DATA_DIR / "store" / "services.json",
    "menu": DATA_DIR / "store" / "menu.json",
}

app = FastAPI(title="Urdu Voice Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local-only desktop app, never exposed beyond localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

# loaded once at startup - the embedding model and FAQ index are expensive to (re)build
faq_store = FaqStore()
chat_engine = ChatEngine(faq_store=faq_store)

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


class FaqEntry(BaseModel):
    id: str
    question: str
    answer: str


class ExampleEntry(BaseModel):
    user: str
    assistant: str


def _read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.post("/chat")
def chat(payload: ChatMessage):
    reply = chat_engine.reply(payload.message)
    return {"reply": reply}


@app.post("/voice_turn")
def voice_turn():
    """Record from the local mic until the user stops talking, transcribe, reply, and
    speak the reply out loud through the local speakers - same pipeline as CLI voice mode,
    triggered here by the mic button in the chat page."""
    from .mic import record

    wav_path = record()
    user_text = _get_transcriber().transcribe(wav_path)
    if not user_text:
        return {"user_text": "", "reply": ""}

    reply = chat_engine.reply(user_text)
    try:
        _get_speaker().say(reply)
    except Exception as e:
        # the text reply already succeeded - a flaky/slow TTS render (e.g. Azure's
        # real-time-factor watchdog under system load) shouldn't lose the whole turn
        print(f"TTS playback failed, continuing with text-only reply: {e}")
    return {"user_text": user_text, "reply": reply}


@app.get("/config/persona")
def get_persona_config():
    return persona.load_persona_config()


@app.put("/config/persona")
def put_persona_config(config: dict):
    persona.save_persona_config(config)
    return config


@app.get("/config/example_bank")
def get_example_bank():
    return persona.load_example_bank()


@app.put("/config/example_bank")
def put_example_bank(examples: list[dict]):
    persona.save_example_bank(examples)
    return examples


@app.post("/config/example_bank")
def add_example(entry: ExampleEntry):
    examples = persona.load_example_bank()
    examples.append(entry.model_dump())
    persona.save_example_bank(examples)
    return examples


@app.get("/config/settings")
def get_settings():
    return app_settings.load_settings()


@app.put("/config/settings")
def put_settings(settings: dict):
    app_settings.save_settings(settings)
    return settings


@app.get("/faq")
def get_faq():
    return _read_json(FAQ_PATH)


@app.put("/faq")
def put_faq(entries: list[FaqEntry]):
    _write_json(FAQ_PATH, [e.model_dump() for e in entries])
    faq_store._sync_from_json()
    return entries


@app.post("/faq")
def add_faq(entry: FaqEntry):
    entries = _read_json(FAQ_PATH)
    if any(e["id"] == entry.id for e in entries):
        raise HTTPException(status_code=409, detail="an FAQ entry with this id already exists")
    entries.append(entry.model_dump())
    _write_json(FAQ_PATH, entries)
    faq_store._sync_from_json()
    return entries


@app.delete("/faq/{entry_id}")
def delete_faq(entry_id: str):
    entries = _read_json(FAQ_PATH)
    remaining = [e for e in entries if e["id"] != entry_id]
    if len(remaining) == len(entries):
        raise HTTPException(status_code=404, detail="no FAQ entry with this id")
    _write_json(FAQ_PATH, remaining)
    faq_store._sync_from_json()
    return remaining


@app.get("/store/{name}")
def get_store(name: str):
    if name not in STORE_FILES:
        raise HTTPException(status_code=404, detail=f"unknown store dataset '{name}'")
    return _read_json(STORE_FILES[name])


@app.put("/store/{name}")
async def put_store(name: str, request: Request):
    if name not in STORE_FILES:
        raise HTTPException(status_code=404, detail=f"unknown store dataset '{name}'")
    data = await request.json()
    _write_json(STORE_FILES[name], data)
    return data


@app.get("/sessions")
def get_sessions():
    return session_log.list_sessions()


@app.get("/escalations")
def get_escalations():
    return session_log.list_escalations()
