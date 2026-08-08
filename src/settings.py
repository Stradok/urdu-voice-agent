import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from .db import get_session
from .models import AppSettings

# mic_device/speaker_device are local hardware settings for this machine's Electron/CLI
# app - meaningless for a hosted business, so (per plan.md's Data Layer notes) they were
# deliberately excluded from the app_settings table and stay in a small local file instead.
LOCAL_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "config" / "local_settings.json"
LOCAL_DEFAULTS = {
    "mic_device": "auto",
    "speaker_device": "auto",
}


def _load_local() -> dict:
    if not LOCAL_SETTINGS_PATH.exists():
        return dict(LOCAL_DEFAULTS)
    with open(LOCAL_SETTINGS_PATH, encoding="utf-8") as f:
        return {**LOCAL_DEFAULTS, **json.load(f)}


def _save_local(local: dict):
    LOCAL_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCAL_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(local, f, ensure_ascii=False, indent=2)


def load_settings(business_id: UUID) -> dict:
    with get_session() as session:
        row = session.scalar(select(AppSettings).where(AppSettings.business_id == business_id))
        settings = {
            "llm_temperature": float(row.llm_temperature),
            "tts_rate_percent": row.tts_rate_percent,
            "vad_silence_ms": row.vad_silence_ms,
            "reply_language": row.reply_language,
            "llm_model": row.llm_model,
        }
    settings.update(_load_local())
    return settings


def save_settings(business_id: UUID, settings: dict):
    with get_session() as session:
        row = session.scalar(select(AppSettings).where(AppSettings.business_id == business_id))
        row.llm_temperature = settings["llm_temperature"]
        row.tts_rate_percent = settings["tts_rate_percent"]
        row.vad_silence_ms = settings["vad_silence_ms"]
        row.reply_language = settings["reply_language"]
        row.llm_model = settings["llm_model"]

    _save_local({
        "mic_device": settings.get("mic_device", LOCAL_DEFAULTS["mic_device"]),
        "speaker_device": settings.get("speaker_device", LOCAL_DEFAULTS["speaker_device"]),
    })
