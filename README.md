# Sara — Urdu Customer Support Voice Agent

A voice/chat customer support agent named **"سارہ" (Sara)**. Customers talk to her in Urdu (voice or text, with English code-switching understood), she looks up relevant answers from a business's FAQ knowledge base and live stock/appointment/menu data, generates a natural, casual-Urdu reply with an LLM, and (in voice mode) speaks the reply back out loud.

The project has two parts today:
- A **FastAPI backend** (`src/`) — the actual agent: STT → FAQ retrieval → LLM (with tool-calling) → TTS, plus persona/guardrail config, and per-business "knowledge base" data (stock, services, menu, bookings).
- An **Electron + React desktop app** (`frontend/`) — a chat UI to talk to Sara, plus admin pages to edit her persona/guardrails, manage the store's data, edit the FAQ, and review past sessions/escalations.

A standalone CLI (`main.py`) also still works if you just want to talk to the agent from a terminal without the frontend.

> **Where this is headed**: this is currently a single-tenant local app (one business's data, running on one machine). The plan to turn it into a multi-tenant hosted product for many client businesses — phone + WhatsApp + web widget channels, a real database, per-business logins — lives in **[`plan.md`](./plan.md)**. This README covers what exists and runs *today*.

## Architecture

### Pipeline overview

```
🎤 Mic input (voice mode) / 💬 typed text (chat mode)
        │
        ▼
  ① Audio capture   records via `arecord` (auto-picks a USB mic over an
        │           unplugged analog jack — see src/audio_devices.py)
        ▼
  ② VAD             webrtcvad detects when the speaker stops talking, so
        │           recording ends on silence instead of a fixed duration
        ▼
  ③ STT             faster-whisper ("small" model, language="ur", GPU)
        │           transcribes the .wav to Urdu text
        ▼
  ④ Retrieval       embeds the question (multilingual-e5-small) and searches
        │  (FAQ)     a Chroma vector DB (data/faq/faq.json) for the closest
        │           FAQ. Close enough (cosine distance ≤ 0.22) → passed to
        │           the LLM as grounding context.
        ▼
  ⑤ LLM             sends system prompt (src/persona.py, editable from the
        │           Guardrails page) + tone-matched few-shot examples (picked
        │           by embedding similarity) + FAQ context + recent history +
        │           the message to Groq's llama-3.3-70b-versatile, with
        │           tool-calling enabled for stock/appointment/menu/booking
        │           lookups and human-escalation (⑥). Any Groq error (rate
        │           limit, malformed tool call) degrades to a graceful Urdu
        │           fallback message instead of crashing.
        ▼
  ⑥ Tools           if the LLM calls a tool, src/tools.py looks up (or
        │  (live data) updates) real stock/appointment/menu/booking data and
        │           the result is fed back for a final natural-language reply
        ▼
  ⑦ TTS             (voice mode only) sends the reply as SSML to Azure Speech
        │           (voice: ur-PK-UzmaNeural), retries once on transient
        │           synthesis failures
        ▼
  ⑧ Playback        plays the synthesized audio via `aplay` through the
        │           selected output device
        ▼
🔊 Spoken reply (voice mode) / printed or on-screen reply (text/chat mode)
```

### Pipeline stage reference — what's used where, and what it costs

| # | Stage | Purpose | Technology | Cost | Code |
|---|---|---|---|---|---|
| ① | Audio capture | Record the caller's voice | `arecord` (ALSA), auto USB-device detection | Free, local | `src/mic.py`, `src/audio_devices.py` |
| ② | VAD (endpointing) | Detect when the speaker stops talking, so recording doesn't wait for a fixed duration | `webrtcvad` (Google's WebRTC VAD engine, via `webrtcvad-wheels`) | Free, open source | `src/mic.py` |
| ③ | STT (transcription) | Convert recorded Urdu speech to text | `faster-whisper` ("small" model, `language="ur"`, self-hosted) | Free, self-hosted — needs a local GPU | `src/stt.py` |
| ④ | Retrieval (FAQ grounding) | Find the closest matching FAQ answer to ground the reply in real facts | `sentence-transformers` (`intfloat/multilingual-e5-small`) + ChromaDB vector search | Free, open source, self-hosted | `src/faq_store.py` |
| ⑤ | LLM (reasoning + reply) | Generate the natural-language Urdu reply; decide when a tool call is needed | Groq, `llama-3.3-70b-versatile` | Free tier: 100k tokens/day. Pay-as-you-go beyond that: $0.59 / $0.79 per million input/output tokens | `src/llm.py` |
| ⑥ | Tools (live data) | Look up/update real stock, appointments, menu, bookings; escalate sensitive cases to a human | Custom Python functions + Groq function-calling | Free, self-hosted | `src/tools.py` |
| ⑦ | TTS (speech synthesis) | Convert the reply back into natural-sounding spoken Urdu | Azure Speech, `ur-PK-UzmaNeural` neural voice, SSML | **Free tier (F0): 500,000 characters/month (~10 hours of audio), renews monthly, never expires.** Beyond that: throttled on F0, or ~$16/million characters on the paid S0 tier | `src/tts.py` |
| ⑧ | Audio playback | Play the synthesized reply out loud | `aplay` (ALSA) | Free, local | `src/tts.py` |

Every stage that costs money (STT is self-hosted/free today, but see `plan.md` for a planned move to Groq's hosted Whisper API — also inexpensive) runs on a provider with a genuine free tier, which is why this project can be developed and even piloted with real customers at close to zero infrastructure cost. See `plan.md` for how this evolves for a hosted, multi-tenant deployment (the local-hardware-bound stages — mic capture and playback — specifically don't carry over to a hosted product and are replaced there).

### Key design points
- **Two API keys, two jobs**: Groq (`GROQ_API_KEY`) powers the conversation (the LLM). Azure Speech (`AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`) only powers voice *output* (text-to-speech) — text/chat mode never needs Azure.
- **FAQ grounding, not a hard rule engine**: the FAQ store gives the LLM relevant facts when a question is close enough to something in the knowledge base; off-topic chat skips it and the LLM answers freely, guided by the persona.
- **Tool-calling for live data**: stock levels, appointment slots, menu items, and table bookings are looked up (and, for bookings, updated) live via `src/tools.py` — the LLM decides when to call these and grounds its reply in the actual result instead of guessing. A `recommend_human_agent` tool lets Sara hand off sensitive cases to a real person, logged for the Continuous Learning page.
- **Persona & guardrails are runtime config, not code**: `data/config/persona.json` (role, tone rules, guardrails) and `data/config/example_bank.json` (few-shot examples) are edited live from the Guardrails page — no restart needed, `build_system_prompt()` rebuilds fresh from the current file on every reply.
- **Tunable at runtime**: LLM temperature, TTS speaking rate, and mic silence-cutoff are all editable sliders in the Guardrails page (`data/config/settings.json`), same story — no restart needed.
- **Conversation memory**: `ChatEngine` keeps the last few turns of history so replies stay contextual within a session.

## Setup

1. Create/activate a virtualenv and install dependencies (already done if `.venv/` exists):
   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your keys (see comments inside the file for how to get each one):
   ```bash
   cp .env.example .env
   ```
   - `GROQ_API_KEY` — free, from console.groq.com (100k tokens/day free tier; resets daily — heavy testing can hit this)
   - `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` — free tier (F0) from portal.azure.com; region must be the short code (e.g. `eastus`), not the display name
3. If you'll use the desktop app, install frontend dependencies:
   ```bash
   cd frontend && npm install
   ```

## Running it

**Desktop app** (chat UI + admin dashboard, recommended way to use/configure Sara):
```bash
cd frontend
npm run app:dev
```
This starts the Vite dev server, waits for it, then launches Electron — which itself spawns the Python backend (`uvicorn src.api:app`) as a child process. One command, everything comes up together.

- **Chat page**: text or push-to-talk voice messages with Sara.
- **Guardrails page**: edit persona/role/tone/guardrails, tune temperature/TTS rate/mic cutoff, pick input/output audio devices.
- **Store Data page**: edit stock, bookable services + slots, and menu/today's-special + table slots — Sara's live "knowledge base."
- **FAQ page**: add/edit/delete FAQ question-answer pairs.
- **Continuous Learning page**: review past session transcripts (promote a good exchange into the few-shot example bank) and escalation logs (sensitive cases handed to a human).

**Standalone CLI** (no frontend, useful for quick testing):
```bash
# Text mode — no mic/speaker/Azure key needed
.venv/bin/python main.py --text

# Voice mode — needs a working mic + speaker + all 3 keys set
.venv/bin/python main.py
```

**Backend only** (if you want to hit the API directly, e.g. with curl):
```bash
.venv/bin/python -m uvicorn src.api:app --host 127.0.0.1 --port 8420
```

## Project layout

| Path | Responsibility |
|---|---|
| `main.py` | Standalone CLI entry point (text or voice loop), independent of the FastAPI/Electron app |
| `src/api.py` | FastAPI app — chat/voice endpoints, and CRUD endpoints backing every admin page |
| `src/mic.py` | Records audio from the mic, auto-picks a USB device over an unplugged analog jack, VAD-based stop |
| `src/audio_devices.py` | Lists/resolves ALSA capture & playback devices |
| `src/stt.py` | Speech-to-text (faster-whisper, Urdu, GPU) |
| `src/llm.py` | `ChatEngine` — talks to Groq, picks relevant few-shot examples, handles tool-calling, manages history, degrades gracefully on Groq errors |
| `src/persona.py` | Loads/saves persona config + example bank from `data/config/`, builds the system prompt |
| `src/settings.py` | Loads/saves tunable runtime settings from `data/config/settings.json` |
| `src/faq_store.py` | Vector search over `data/faq/faq.json` (Chroma + sentence-transformers) |
| `src/tools.py` | Stock/appointment/menu/booking/escalation functions + their Groq tool schemas |
| `src/tts.py` | Text-to-speech via Azure Speech (SSML + rate tuning, retries once on failure), plays audio |
| `src/session_log.py` | Session transcript + escalation logging, read by the Continuous Learning page |
| `data/config/` | `persona.json`, `example_bank.json`, `settings.json` — editable from the Guardrails page |
| `data/faq/faq.json` | FAQ knowledge base, editable from the FAQ page |
| `data/chroma/` | Persisted vector index built from `faq.json` (auto-synced on every edit) |
| `data/store/*.json` | Stock/services/menu/bookings data, editable from the Store Data page |
| `data/sessions/` | Per-session transcript logs + `escalations.json` |
| `frontend/` | Electron + React + Vite + TypeScript desktop app (chat + admin dashboard) |
| `plan.md` | The roadmap: turning this into a multi-tenant hosted SaaS product |

To add or edit FAQ/persona/store data by hand instead of through the UI, just edit the corresponding JSON file directly — everything re-syncs or reloads on the next call, no restart needed.
