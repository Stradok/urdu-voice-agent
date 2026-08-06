# Urdu Voice Agent

A voice-based Urdu customer support agent named **"سارہ" (Sara)**. You talk to it in Urdu (by voice or text), it looks up relevant answers from a small FAQ knowledge base, generates a natural, casual-Urdu reply with an LLM, and (in voice mode) speaks the reply back out loud.

## How it works — the full pipeline

```
🎤 Mic input (voice mode only)
        │
        ▼
  src/mic.py        streams audio via `arecord`, using webrtcvad to detect when
        │           you stop talking (~700ms of silence) instead of a fixed
        │           duration → 16kHz mono .wav
        ▼
  src/stt.py        faster-whisper ("small" model, language="ur", GPU) transcribes
        │           the .wav to Urdu text, then deletes the temp file
        ▼
  src/faq_store.py  embeds your question (multilingual-e5-small) and searches
        │           a Chroma vector DB (data/faq/faq.json) for the closest FAQ.
        │           If the match is close enough (cosine distance ≤ 0.22),
        │           its answer is passed to the LLM as grounding context.
        ▼
  src/llm.py        sends system prompt (src/persona.py) + the most tone-relevant
        │           few-shot examples (picked by embedding similarity, not fixed)
        │           + FAQ context + recent chat history + your message to Groq's
        │           llama-3.3-70b-versatile model, with tool-calling enabled
        │           (src/tools.py) for stock/appointment/menu/booking lookups.
        │           If the model calls a tool, the result is fed back for a
        │           final natural-language reply in Urdu.
        ▼
  src/tts.py        (voice mode only) sends the reply as SSML (with a faster
        │           prosody rate) to Azure Speech (voice: ur-PK-UzmaNeural)
        │           → synthesizes a .wav → plays it via `aplay`.
        ▼
🔊 Spoken reply (voice mode) / printed reply (text mode)
```

The loop repeats until you exit.

### Key design points
- **Two API keys, two jobs**: Groq (`GROQ_API_KEY`) powers the actual conversation (the LLM). Azure Speech (`AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`) only powers the voice *output* (text-to-speech) in voice mode — text mode never needs Azure.
- **FAQ grounding, not a hard rule engine**: the FAQ store doesn't dictate the reply verbatim — it just gives the LLM relevant facts (e.g. return policy, delivery times) when your question is close enough to something in `data/faq/faq.json`. Off-topic chat (small talk, greetings) skips the FAQ and the LLM answers freely, guided by the persona.
- **Tool-calling for live data**: unlike the FAQ (static text), stock levels, appointment slots, menu items, and table bookings are looked up (and in the booking case, updated) live via `src/tools.py` against `data/store/*.json` — the LLM decides when to call these and grounds its reply in the actual result instead of guessing numbers.
- **Persona**: `src/persona.py` defines Sara's tone — casual spoken Pakistani Urdu, short answers (it's meant to be heard, not read), light friendliness without turning every reply into a sales pitch — plus guardrails (stay in character, don't fabricate order/account details, avoid politics/religion, Urdu-script-only output, understand English-Urdu code-switching).
- **Conversation memory**: `ChatEngine` keeps the last 6 turns (`history_turns=6`) so replies stay contextual within a session; memory resets each time you restart the script.

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
   - `GROQ_API_KEY` — free, from console.groq.com
   - `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` — free tier (F0) from portal.azure.com; region must be the short code (e.g. `uaenorth`), not the display name

## Running it

**Text mode** (no mic/speaker, no Azure key needed — good for quick testing):
```bash
.venv/bin/python main.py --text
```
Type in Urdu, get replies printed back. Type `exit` or `quit` to stop.

**Voice mode** (default, needs a working mic + speaker + all 3 keys set):
```bash
.venv/bin/python main.py
```
Speak after it says it's ready; it stops recording shortly after you stop talking, then transcribes, replies, and speaks the answer out loud. `Ctrl+C` to stop.

## Project layout

| File | Responsibility |
|---|---|
| `main.py` | Entry point; wires everything together, checks required `.env` keys, runs the text or voice loop |
| `src/mic.py` | Records audio from the default microphone, VAD-based stop (webrtcvad) |
| `src/stt.py` | Speech-to-text (faster-whisper, Urdu, GPU via CUDA-12 libs) |
| `src/llm.py` | Talks to Groq's LLM, picks relevant few-shot examples, handles tool-calling, manages chat history |
| `src/persona.py` | System prompt (persona + guardrails) + the few-shot example bank |
| `src/faq_store.py` | Vector search over `data/faq/faq.json` (Chroma + sentence-transformers) |
| `src/tools.py` | Stock/appointment/menu/booking lookup functions + their Groq tool schemas |
| `src/tts.py` | Text-to-speech via Azure Speech (SSML + rate tuning), plays audio |
| `data/faq/faq.json` | Editable FAQ knowledge base (question/answer pairs in Urdu) |
| `data/chroma/` | Persisted vector index built from `faq.json` (auto-synced on startup) |
| `data/store/*.json` | Mock stock/services/menu/bookings data queried by `src/tools.py` |

To add or edit FAQ answers, just edit `data/faq/faq.json` — `FaqStore._sync_from_json()` automatically adds new entries and removes deleted ones from the vector index on the next run.

To change the mock business data (products, appointment services, menu items), edit the corresponding file under `data/store/` directly — no re-sync step needed, `src/tools.py` reads them fresh on each call.
