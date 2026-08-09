# Sara — Urdu Customer Support Voice Agent

A voice/chat customer support agent named **"سارہ" (Sara)**, now a real (if early) multi-tenant product: each business logs in and only ever sees its own persona, FAQ, data, and tools. Customers talk to her in Urdu (voice or text, with English code-switching understood), she looks up relevant answers from that business's FAQ knowledge base and live stock/appointment/menu data, generates a natural reply with an LLM (matching the customer's language even when the business's own persona/guardrails were written in English), and (in voice mode) speaks the reply back out loud.

The project has two parts today:
- A **FastAPI backend** (`src/`) — the agent: STT → FAQ retrieval → LLM (with tool-calling, scoped to what that business type actually offers) → TTS, plus persona/guardrail config and per-business "knowledge base" data (stock, services, menu, bookings), all behind login.
- An **Electron + React desktop app** (`frontend/`) — a login-gated chat UI to talk to Sara, plus admin pages to edit her persona/guardrails, manage the business's data, edit the FAQ, and review past sessions/escalations.

A standalone CLI (`main.py`) also still works if you just want to talk to the agent from a terminal without the frontend — it has no login and always talks to one hardcoded business (`DEFAULT_BUSINESS_SLUG`, see `src/business_context.py`).

> **Current market focus (2026-08-08): dental clinics and banks, not retail.** Live testing found every real correctness bug in the retail stock-matching path (fuzzy-matching a spoken product name against an open-ended catalog is genuinely harder than a clinic's one bounded action or a bank's deliberately narrow "always escalate to a human" scope). The dental-clinic and bank test accounts are the actively pitched/demoed reference customers; the retail accounts below still work and stay in the codebase, just deprioritized until a later focused push. See `plan.md`'s Executive Summary for the full reasoning.
>
> **Where this is headed**: the database (Supabase Postgres, `business_id`-scoped throughout) and dashboard login (Supabase Auth) are both live — see **[`plan.md`](./plan.md)** Phase 0 §1/§2/§4 for exactly what shipped and when. Four real test accounts across different verticals (dental clinic, retail store, clothing brand, bank) exist to exercise this: each only sees its own data and its own subset of tools, and each was seeded with persona/guardrails/FAQ written in English on purpose, to prove the agent still replies in whichever language the *customer* uses. Still ahead: per-business Groq/Azure credentials (today all businesses share one backend API key — plan.md §3), and the customer-facing web widget/anonymous auth (§5), which is what a real non-technical customer would actually talk to instead of this desktop app.

## Architecture

### Pipeline overview

```
🎤 Mic input (voice mode, hold-to-talk) / 💬 typed text (chat mode)
        │
        ▼
  ① Audio capture   records via `arecord` (auto-picks a USB mic over an
        │           unplugged analog jack — see src/audio_devices.py) for
        │           as long as the mic button is held; button release is
        │           the stop signal, not a silence timeout
        ▼
  ② STT             Groq's hosted whisper-large-v3-turbo transcribes the
        │           .wav to text — handles Urdu/English code-switching
        │           ("kya apka paas class 10 hai") far better than the
        │           small local model this replaced, and needs no GPU
        ▼
  ③ Retrieval       embeds the question (multilingual-e5-small) and searches
        │  (FAQ)     pgvector-indexed FAQ entries in Postgres for the closest
        │           matches (top 3, not just the single closest - two FAQs can
        │           sit within noise distance of each other). Close enough
        │           (cosine distance ≤ 0.22) → passed to the LLM as grounding
        │           context, each labeled with its own question so the model
        │           can judge which one actually answers what was asked.
        ▼
  ④ LLM             sends system prompt (src/persona.py, editable from the
        │           Guardrails page) + tone-matched few-shot examples (picked
        │           by embedding similarity) + FAQ context + recent history +
        │           the message to that business's chosen model (per-business
        │           AppSettings.llm_model, src/llm.py's LLM_CATALOG - Groq or
        │           OpenRouter), with tool-calling enabled for stock/
        │           appointment/menu/booking lookups and human-escalation (⑤).
        │           Any provider error (rate limit, malformed tool call)
        │           degrades to a graceful Urdu fallback message instead of
        │           crashing.
        ▼
  ⑤ Tools           if the LLM calls a tool, src/tools.py looks up (or
        │  (live data) updates) real stock/appointment/menu/booking data and
        │           the result is fed back for a final natural-language reply
        ▼
  ⑥ Response        (both modes) the text reply returns to the caller
        │           immediately - voice mode does not wait for ⑦/⑧ below
        ▼
  ⑦ TTS             (voice mode only, background thread) sends the reply as
        │           SSML to Azure Speech (voice: ur-PK-UzmaNeural), retries
        │           once on transient synthesis failures
        ▼
  ⑧ Playback        plays the synthesized audio via `aplay` through the
        │           selected output device, after the text reply already
        │           returned (so a long spoken reply no longer delays the
        │           on-screen text)
        ▼
🔊 Spoken reply (voice mode) / printed or on-screen reply (text/chat mode)
```

### Pipeline stage reference — what's used where, and what it costs

| # | Stage | Purpose | Technology | Cost | Code |
|---|---|---|---|---|---|
| ① | Audio capture | Record the caller's voice for as long as the mic button is held (hold-to-talk, not VAD-guessed) | `arecord` (ALSA), auto USB-device detection | Free, local | `src/mic.py`, `src/audio_devices.py` |
| ② | STT (transcription) | Convert recorded speech to text, including Urdu/English code-switching | Groq hosted `whisper-large-v3-turbo` | Groq free tier: 100k tokens/day (shared with the LLM stage's quota, see `plan.md` §3) | `src/stt.py` |
| ③ | Retrieval (FAQ grounding) | Find the closest matching FAQ answer to ground the reply in real facts | `sentence-transformers` (`intfloat/multilingual-e5-small`) + Postgres `pgvector` search | Free, open source (Supabase free tier for the DB) | `src/faq_store.py` |
| ④ | LLM (reasoning + reply) | Generate the natural-language Urdu reply; decide when a tool call is needed | Per-business choice via a dropdown (`src/llm.py`'s `LLM_CATALOG`) — Gemma 4 31B via OpenRouter by default (recommended after real eval testing, see `plan.md`), or Gemini 3.5 Flash / Gemini 3.5 Flash Lite / DeepSeek V4 Flash / Claude Haiku 4.5 via OpenRouter, or Groq `llama-3.3-70b-versatile` | OpenRouter models are pay-as-you-go, from ~$0/M (Gemma 4's free-tier variant) to ~$1.50-9/M (Gemini 3.5 Flash). Groq free tier: 100k tokens/day — see `plan.md`'s "Open issue" section for the full cost/quality comparison | `src/llm.py` |
| ⑤ | Tools (live data) | Look up/update real stock, appointments, menu, bookings; escalate sensitive cases to a human | Custom Python functions + function-calling | Free, self-hosted | `src/tools.py` |
| ⑥ | TTS (speech synthesis) | Convert the reply back into natural-sounding spoken Urdu, in a background thread so it doesn't delay the text reply | Azure Speech, `ur-PK-UzmaNeural` neural voice, SSML | **Free tier (F0): 500,000 characters/month (~10 hours of audio), renews monthly, never expires.** Beyond that: throttled on F0, or ~$16/million characters on the paid S0 tier | `src/tts.py` |
| ⑦ | Audio playback | Play the synthesized reply out loud | `aplay` (ALSA) | Free, local | `src/tts.py` |

Every stage runs on a provider with a genuine free tier, which is why this project can be developed and even piloted with real customers at close to zero infrastructure cost. See `plan.md` for how this evolves for a hosted, multi-tenant deployment (the local-hardware-bound stages — mic capture and playback — specifically don't carry over to a hosted product and are replaced there).

### Database schema (Postgres / Supabase)

Every table hangs off `businesses` by a `business_id` foreign key (`ON DELETE CASCADE`) — this is what makes the schema multi-tenant-ready even though only one business is served today (see `src/business_context.py`). `sessions` → `exchanges` is the conversation history; `escalations` optionally links back to the session it came from (`ON DELETE SET NULL`, so deleting a session doesn't delete the escalation record). Defined in `src/models.py`, created by `alembic/versions/`.

```mermaid
erDiagram
    BUSINESSES ||--o| APP_SETTINGS : configures
    BUSINESSES ||--o{ PERSONA_CONFIGS : has
    BUSINESSES ||--o{ EXAMPLE_BANK_ENTRIES : has
    BUSINESSES ||--o{ FAQ_ENTRIES : has
    BUSINESSES ||--o{ STOCK_ITEMS : has
    BUSINESSES ||--o{ SERVICE_ITEMS : has
    BUSINESSES ||--o{ MENU_ITEMS : has
    BUSINESSES ||--o{ TABLE_SLOTS : has
    BUSINESSES ||--o{ BOOKINGS : has
    BUSINESSES ||--o{ SESSIONS : has
    BUSINESSES ||--o{ ESCALATIONS : has
    SESSIONS ||--o{ EXCHANGES : contains
    SESSIONS |o--o{ ESCALATIONS : "optionally raised from"

    BUSINESSES {
        uuid id PK
        string name
        string slug UK
        string business_type "scopes tools, not enforced yet"
        string widget_key UK
        string owner_email
        datetime created_at
    }
    APP_SETTINGS {
        uuid business_id PK_FK
        numeric llm_temperature
        int tts_rate_percent
        int vad_silence_ms
        string reply_language "auto | urdu | english"
    }
    PERSONA_CONFIGS {
        uuid id PK
        uuid business_id FK
        string name
        text role_description
        text_array tone_rules
        text faq_grounding_instruction
        text code_switching_note
        text tools_instruction
        text_array guardrails
    }
    EXAMPLE_BANK_ENTRIES {
        uuid id PK
        uuid business_id FK
        text user_text
        text assistant_text
    }
    FAQ_ENTRIES {
        uuid id PK
        uuid business_id FK
        text question
        text answer
        vector384 embedding "pgvector, multilingual-e5-small"
    }
    STOCK_ITEMS {
        uuid id PK
        uuid business_id FK
        string name
        numeric price
        int quantity
    }
    SERVICE_ITEMS {
        uuid id PK
        uuid business_id FK
        string name
        int duration_minutes
        string_array available_slots
    }
    MENU_ITEMS {
        uuid id PK
        uuid business_id FK
        string name
        numeric price
        text description
        bool is_today_special
    }
    TABLE_SLOTS {
        uuid id PK
        uuid business_id FK
        string date_time
    }
    BOOKINGS {
        uuid id PK
        uuid business_id FK
        string date_time
        int party_size
        datetime created_at
    }
    SESSIONS {
        uuid id PK
        uuid business_id FK
        string channel "dashboard | widget | whatsapp | phone"
        datetime started_at
    }
    EXCHANGES {
        uuid id PK
        uuid session_id FK
        text user_text
        text assistant_text
        datetime timestamp
    }
    ESCALATIONS {
        uuid id PK
        uuid business_id FK
        uuid session_id FK "nullable"
        text reason
        datetime timestamp
    }
```

Tenant isolation is enforced at the application layer (every query filters on `business_id`, proven by `tests/test_tenant_isolation.py`) and backstopped by Postgres RLS enabled with zero policies on every table (default-deny for any role but the table owner) — see `plan.md` Phase 0 §1 for why both layers exist.

### Key design points
- **Two API keys, two jobs**: Groq (`GROQ_API_KEY`) powers the conversation (the LLM). Azure Speech (`AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`) only powers voice *output* (text-to-speech) — text/chat mode never needs Azure.
- **FAQ grounding, not a hard rule engine**: the FAQ store gives the LLM relevant facts when a question is close enough to something in the knowledge base; off-topic chat skips it and the LLM answers freely, guided by the persona.
- **Tool-calling for live data**: stock levels, appointment slots, menu items, and table bookings are looked up (and, for bookings, updated) live via `src/tools.py` — the LLM decides when to call these and grounds its reply in the actual result instead of guessing. A `recommend_human_agent` tool lets Sara hand off sensitive cases to a real person, logged for the Continuous Learning page.
- **Persona & guardrails are runtime config, not code**: persona (role, tone rules, guardrails) and the few-shot example bank live in Postgres (`persona_configs`/`example_bank_entries`) and are edited live from the Guardrails page — no restart needed, `build_system_prompt()` rebuilds fresh from the current row on every reply.
- **Tunable at runtime**: LLM temperature, TTS speaking rate, mic silence-cutoff, and reply language are all editable sliders/selects in the Guardrails page (the `app_settings` table; `mic_device`/`speaker_device` are the one exception — local hardware settings, kept in a small local file instead), same story — no restart needed.
- **Conversation memory**: `ChatEngine` keeps the last few turns of history in memory *and* persists every exchange to the `exchanges` table as it happens, scoped to `business_id` + `session_id`.

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
   - `OPENROUTER_API_KEY` — optional, only needed if a business selects a non-Groq model from the Guardrails page's AI Model dropdown (Gemini/DeepSeek/Gemma/Claude, all via OpenRouter); free from openrouter.ai, no card required for the free-tier models
   - `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` — free tier (F0) from portal.azure.com; region must be the short code (e.g. `eastus`), not the display name
   - `DATABASE_URL` / `DIRECT_URL` / `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_SECRET_KEY` — free Supabase project (see comments in `.env.example`). **Required** — the app reads/writes all persona/FAQ/stock/session data through Postgres now, not local JSON files.
3. Run migrations, then seed either the default CLI-only business, some real test accounts, or both (all one-off, safe to re-run):
   ```bash
   .venv/bin/alembic upgrade head
   .venv/bin/python scripts/seed_default_business.py   # for main.py --text / voice mode, no login
   .venv/bin/python scripts/seed_test_accounts.py       # 4 login-able test accounts, prints their credentials
   ```
   To onboard a new business by hand instead: `scripts/create_business_account.py --email ... --password ... --name ... --slug ... --business-type ...`.
4. If you'll use the desktop app: install frontend dependencies, then create `frontend/.env` (copy `frontend/.env.example`) with the same `SUPABASE_URL`/`SUPABASE_PUBLISHABLE_KEY` values as the backend's `.env`, under the `VITE_` prefix - the frontend logs in against Supabase directly.
   ```bash
   cd frontend && npm install
   ```

## Running it

**Desktop app** (chat UI + admin dashboard, recommended way to use/configure Sara):
```bash
cd frontend
npm run app:dev
```
This starts the Vite dev server, waits for it, then launches Electron — which itself spawns the Python backend (`uvicorn src.api:app`) as a child process. One command, everything comes up together. You'll land on a login screen first - sign in with one of the test accounts from `scripts/seed_test_accounts.py` (or your own, from `create_business_account.py`). Every page below is scoped to whichever business you logged in as.

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
Every endpoint except `/health` requires `Authorization: Bearer <token>`, a real Supabase Auth JWT for one of the login-able businesses. Get one via Supabase's password-grant endpoint:
```bash
curl -s -X POST "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H "Content-Type: application/json" \
  -d '{"email":"dental@sara-test.local","password":"Dental-Test-2026!"}'
# then: curl http://127.0.0.1:8420/whoami -H "Authorization: Bearer <access_token from above>"
```

## Project layout

| Path | Responsibility |
|---|---|
| `main.py` | Standalone CLI entry point (text or voice loop), independent of the FastAPI/Electron app |
| `src/api.py` | FastAPI app — chat/voice endpoints, and CRUD endpoints backing every admin page |
| `src/mic.py` | Records audio from the mic, auto-picks a USB device over an unplugged analog jack, explicit hold-to-talk `start_recording()`/`stop_recording()` |
| `src/audio_devices.py` | Lists/resolves ALSA capture & playback devices |
| `src/stt.py` | Speech-to-text (Groq hosted `whisper-large-v3-turbo`, no local GPU needed) |
| `src/llm.py` | `ChatEngine` — talks to whichever LLM the business selected (`LLM_CATALOG`: Groq or an OpenRouter model, re-read per turn from settings), picks relevant few-shot examples, handles tool-calling, manages history (in-memory + persisted to Postgres), degrades gracefully on provider errors |
| `src/persona.py` | Loads/saves persona config + example bank (Postgres, `business_id`-scoped), builds the system prompt |
| `src/settings.py` | Loads/saves tunable runtime settings (Postgres for LLM temp/TTS rate/VAD/reply language; `mic_device`/`speaker_device` stay in a local file) |
| `src/faq_store.py` | FAQ vector search — embeds with `sentence-transformers`, searches via Postgres `pgvector` (`cosine_distance`) |
| `src/tools.py` | Stock/appointment/menu/booking/escalation functions (Postgres, `business_id`-scoped), their Groq tool schemas, and `BUSINESS_TYPE_TOOLS`/`tool_schemas_for()` (which tools a given business type is even offered) |
| `src/tts.py` | Text-to-speech via Azure Speech (SSML + rate tuning, retries once on failure), plays audio |
| `src/session_log.py` | Session/exchange/escalation logging (Postgres), read by the Continuous Learning page |
| `src/auth.py` | Dashboard login — verifies a request's bearer token against Supabase Auth, resolves `business_id` from `businesses.owner_email`. Used as a FastAPI dependency on every `src/api.py` endpoint |
| `src/business_context.py` | Pre-auth seam, still used by `main.py` (the CLI has no login) — resolves one business by `DEFAULT_BUSINESS_SLUG`. `src/api.py` no longer uses this; it resolves `business_id` per-request via `src/auth.py` instead |
| `src/models.py` | SQLAlchemy models for the Postgres (Supabase) schema — `businesses`, `persona_configs`, `faq_entries`, etc. |
| `src/db.py` | Postgres engine/session setup (`DATABASE_URL`, the transaction-mode pooler) |
| `alembic/` | Database migrations (run against `DIRECT_URL`, the session-mode pooler) |
| `scripts/seed_default_business.py` | One-off migration script — copied the original local JSON/FAQ/store data into the `default` business's Postgres rows (used by the CLI, no login) |
| `scripts/create_business_account.py` | Onboard one business by hand — Supabase Auth user + `businesses` row + default `app_settings` |
| `scripts/seed_test_accounts.py` | Creates the 4 real test accounts (dental clinic, retail store, clothing brand, bank), each with full English persona/FAQ/example-bank/data content |
| `tests/test_tenant_isolation.py` | Integration test proving per-business data isolation against the real Supabase database |
| `data/config/`, `data/faq/`, `data/store/`, `data/sessions/` | Pre-migration JSON snapshot — no longer read by the running app; `data/config/local_settings.json` is the one file still live (mic/speaker device) |
| `frontend/src/lib/auth.ts` | Logs in against Supabase's password-grant endpoint directly, stores the JWT |
| `frontend/src/pages/LoginPage.tsx` | Email/password login screen; `App.tsx` gates the whole app behind it |
| `frontend/` | Electron + React + Vite + TypeScript desktop app (login + chat + admin dashboard) |
| `plan.md` | The roadmap: turning this into a multi-tenant hosted SaaS product |

FAQ/persona/store data is now edited through the admin UI (writes go straight to Postgres); there's no JSON file to hand-edit anymore.
