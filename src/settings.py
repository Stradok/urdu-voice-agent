import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "config" / "settings.json"

DEFAULTS = {
    "llm_temperature": 0.5,
    "tts_rate_percent": 15,
    "vad_silence_ms": 700,
}


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        return {**DEFAULTS, **json.load(f)}


def save_settings(settings: dict):
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
