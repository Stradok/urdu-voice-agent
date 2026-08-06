import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "sessions"
ESCALATIONS_PATH = SESSIONS_DIR / "escalations.json"

_current_session_id = None
_current_session_path = None


def start_session() -> str:
    global _current_session_id, _current_session_path
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _current_session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    _current_session_path = SESSIONS_DIR / f"{_current_session_id}.json"
    with open(_current_session_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "session_id": _current_session_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "exchanges": [],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    return _current_session_id


def log_exchange(user_text: str, reply_text: str):
    if _current_session_path is None:
        start_session()
    with open(_current_session_path, encoding="utf-8") as f:
        data = json.load(f)
    data["exchanges"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user_text,
        "assistant": reply_text,
    })
    with open(_current_session_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_escalation(reason: str):
    escalations = list_escalations()
    escalations.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": _current_session_id,
        "reason": reason,
    })
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ESCALATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(escalations, f, ensure_ascii=False, indent=2)


def list_sessions() -> list[dict]:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for path in sorted(SESSIONS_DIR.glob("*.json")):
        if path.name == "escalations.json":
            continue
        with open(path, encoding="utf-8") as f:
            sessions.append(json.load(f))
    return sessions


def list_escalations() -> list[dict]:
    if not ESCALATIONS_PATH.exists():
        return []
    with open(ESCALATIONS_PATH, encoding="utf-8") as f:
        return json.load(f)
