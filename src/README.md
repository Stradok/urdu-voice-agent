# `src/` — architecture map

This is the backend. It's organized into four subpackages by concern — **voice** (async audio in/out), **agent** (the conversational brain), **data** (persistence), **realtime** (live calls) — plus a handful of top-level files that wire the app together. Nothing changed behavior when `voice`/`agent`/`data` were reorganized (2026-08-09); every file just moved to a clearer home.

## The three entry points

| Entry point | What it is | Who runs it |
|---|---|---|
| `main.py` (project root) | Standalone CLI — text or voice loop, one hardcoded business (`business_context.py`), no login | You, directly: `.venv/bin/python main.py` or `--text` |
| `src/api.py` | The FastAPI app — every endpoint the dashboard (Electron/React frontend) and the Continuous Learning/Guardrails/Store pages talk to, plus the hold-to-talk async voice-message flow | `uvicorn src.api:app`, spawned by `frontend/electron/main.cjs` when you run `npm run app:dev` |
| `src/realtime/worker.py` | The LiveKit Agents worker — live, real-time voice calls (VAD, turn-taking, barge-in), a separate long-running process from the FastAPI app | `.venv/bin/python -m src.realtime.worker dev` (connects out to LiveKit Cloud, no inbound ports) |

All three entry points import from `agent`/`data` — there's exactly one implementation of "how Sara replies" (`agent/llm.py`'s `ChatEngine`), used by the CLI, the dashboard, and live calls alike.

## Directory tree

```
src/
├── api.py                 FastAPI app - every HTTP endpoint. The dashboard's only way in.
├── auth.py                Dashboard login - verifies a bearer token against Supabase Auth
├── business_context.py    Pre-auth seam, only used by main.py (CLI has no login)
│
├── voice/                 Audio I/O - capturing, synthesizing, hardware
│   ├── mic.py                 Hold-to-talk recording (start_recording/stop_recording)
│   ├── stt.py                 Speech-to-text (Groq hosted whisper-large-v3-turbo)
│   ├── tts.py                 Text-to-speech (Azure Speech, SSML)
│   └── audio_devices.py       Resolves/lists ALSA capture & playback devices
│
├── agent/                 The conversational brain - everything ChatEngine needs to reason and act
│   ├── llm.py                  ChatEngine - talks to the LLM, dispatches tool calls, manages history
│   ├── persona.py              Builds the system prompt from a business's persona/guardrails config
│   ├── faq_store.py            FAQ vector search (pgvector, top-3 within a distance threshold)
│   ├── tools.py                Tool-calling functions the LLM can invoke (stock, appointments, escalation...)
│   └── scheduling.py           Business-hours-aware appointment slot generation (used only by tools.py)
│
├── data/                  Persistence - the only layer that talks to Postgres directly
│   ├── models.py               SQLAlchemy models - the whole schema
│   ├── db.py                   Engine/session (get_session() context manager)
│   ├── settings.py             Per-business tunable settings (LLM temp, TTS rate, reply language...)
│   ├── session_log.py          Session/exchange/escalation logging
│   └── reference_codes.py      Short voice-friendly ticket/reference codes (AP-#####, ES-#####)
│
└── realtime/              Live voice calls via LiveKit Agents - VAD/turn-taking/barge-in
    ├── worker.py               The agent entrypoint - SaraAgent wraps ChatEngine via llm_node
    ├── tenant.py                Resolves BusinessContext from room metadata (no HTTP request to auth from)
    └── providers.py            Per-reply_language STT/TTS plugin selection (Groq+Azure for Urdu)
```

## How a request actually flows

Text chat (`POST /chat`) and voice (`POST /voice_turn/start` + `/stop`) both end up in the same place - `agent/llm.py`'s `ChatEngine.reply()`:

1. **`api.py`** resolves `business_id` from the request's auth token (`auth.py`), and for voice, records audio first (`voice/mic.py`) and transcribes it (`voice/stt.py`).
2. **`ChatEngine.reply()`** (`agent/llm.py`) builds the system prompt (`agent/persona.py`), looks up relevant FAQ context (`agent/faq_store.py`), and picks tone-matched few-shot examples.
3. It calls the LLM. If the LLM wants to call a tool, `agent/tools.py`'s functions run against real data (`data/models.py`, via `data/db.py`) - `check_stock`, `check_appointment_slots`/`book_appointment` (using `agent/scheduling.py` for the actual slot math), or `recommend_human_agent` (which logs to `data/session_log.py` and gets back a reference code from `data/reference_codes.py`).
4. The reply text returns immediately. For voice, `api.py` speaks it out loud afterward in a background thread (`voice/tts.py`) - it never blocks the text response.

Every function in `agent/` and `data/` takes `business_id` as an explicit parameter and scopes every query to it - there's no global/ambient "current business" anywhere except `business_context.py`'s CLI-only pre-auth seam.

**Live calls** (`realtime/worker.py`) reach the same `ChatEngine.reply()` a different way: no HTTP request, so `realtime/tenant.py` resolves `business_id` from LiveKit room metadata instead of a bearer token; `realtime/providers.py` picks the STT/TTS plugins per the business's `reply_language`; `SaraAgent.llm_node()` calls `ChatEngine.reply()` directly (as a blocking call wrapped in `asyncio.to_thread`, not rewritten to stream). Steps 2-3 above are identical either way - same persona, same FAQ retrieval, same tools.

## "Where do I touch this?" quick reference

| I want to change... | File |
|---|---|
| How Sara decides what to say | `agent/llm.py` (`ChatEngine.reply`, `_complete`, `_run_tool_calls`) |
| The system prompt / persona structure | `agent/persona.py` |
| What tools exist, or add a new one | `agent/tools.py` (function + `TOOL_SCHEMAS` + `BUSINESS_TYPE_TOOLS`) |
| Appointment slot generation / business hours | `agent/scheduling.py` |
| FAQ matching behavior/threshold | `agent/faq_store.py` |
| STT/TTS provider or voice (async voice messages) | `voice/stt.py` / `voice/tts.py` |
| Mic recording behavior | `voice/mic.py` |
| Live call behavior (VAD, barge-in, the call entrypoint) | `realtime/worker.py` |
| STT/TTS provider for live calls | `realtime/providers.py` |
| The DB schema | `data/models.py` (+ a new Alembic migration in `alembic/versions/`) |
| Per-business tunables (temperature, TTS rate...) | `data/settings.py` |
| A new HTTP endpoint | `api.py` |
| Login/auth behavior | `auth.py` |

See the project-root `README.md` for the full pipeline diagram, provider costs, and setup instructions - this file is scoped to "how the backend code is organized," not the whole product.
