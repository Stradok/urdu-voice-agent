# Sara — Production Roadmap

## Executive Summary

Sara is an Urdu-language customer support agent — voice and text, with English code-switching support — currently implemented as a single-tenant desktop application. This document defines the path from that prototype to a hosted, multi-tenant product serving multiple client businesses across web, WhatsApp, and phone channels.

The strategic position is deliberate: this project assembles existing, proven infrastructure (LLM inference, speech services, telephony) into a vertical product for a specific market — Urdu-speaking customer support for Pakistani SMBs — rather than building competing infrastructure from scratch. Given the constraints (minimal capital, available time, no existing client base), this is the correct posture: capital-light, revenue-first, building on suppliers rather than competing with them.

**Current market focus (decided 2026-08-08): clinics and banks, not retail.** Live testing across all 4 seeded verticals showed every real correctness bug traced back to the retail stock-matching path (Urban Mart, Thread House - see Phase 0 §2's bug list) - fuzzy-matching a spoken product name against an open-ended catalog is a fundamentally harder problem than a clinic's one bounded action (check appointment slots for a named service) or a bank's deliberately narrow scope (no account access at all, always escalate to a human). Clinics and banks are where the product is genuinely strong today. **Decision: pitch and demo only the dental-clinic (FAQ + appointment-slot-checking) and bank (FAQ + escalation) verticals for now.** Retail (`retail_store`, `clothing_brand`) is not removed - the code, test accounts, and `check_stock` tool all stay in the repo and keep working - it's deliberately deprioritized, to be revisited as its own focused effort later rather than being a third, under-baked vertical today.

## Current State

A single-tenant Electron desktop application:
- One business's persona, FAQ index, inventory/menu/booking data, and session log — now stored in Postgres (Supabase), `business_id`-scoped throughout the backend, though only one business is ever resolved today (see Phase 0 §4's pre-auth seam).
- No authentication, no multi-user support, no hosted deployment.
- Voice I/O bound to the local machine's own microphone and speakers — this does not generalize to a hosted, multi-customer product.

Full technical detail of what exists today is in `README.md`.

## Target State

A hosted, multi-tenant SaaS: one backend serving many client businesses, each with isolated persona, knowledge base, and customer data behind a login. End customers reach the agent through three channels — a website widget, WhatsApp, and phone — all backed by the same core agent logic.

---

## Phased Roadmap

| Phase | Scope | Status |
|---|---|---|
| **Phase 0** | Multi-tenant data foundation, authentication, one channel (web widget, text + voice) working end-to-end, existing admin pages made per-tenant | Next |
| **Phase 1** | Phone and WhatsApp channels, media/invoice-delivery tools | Planned |
| **Phase 2** | Paid-tier infrastructure once revenue justifies it; broader scale hardening | Future |

Each phase builds on the last — nothing in Phase 0 is discarded later; later phases add channels and scale on top of the same foundation.

---

## Technology Stack

| Component | Choice | Rationale |
|---|---|---|
| LLM (conversation logic) | **Groq**, `llama-3.3-70b-versatile` — **quality issue open, see note below** | Cheapest/fastest inference available ($0.59 / $0.79 per M input/output tokens), free tier sufficient for pilot volume. But: live testing surfaced Urdu script errors (letter substitutions, e.g. "سامان" garbled) — a known weak point of Llama-family models on Arabic-script languages. Given this product's explicit bar ("indistinguishable from a real person"), this is disqualifying if it can't be fixed by prompting alone. |
| Speech-to-text | **Groq hosted Whisper** (`whisper-large-v3`) | $0.04/hour, Urdu-capable, removes the self-hosted GPU/CUDA dependency the project currently carries (`faster-whisper` + a machine-specific CUDA-12 library workaround). One less piece of infrastructure to operate. |
| Text-to-speech | **Azure Speech** (`ur-PK-UzmaNeural`), already integrated | Proven, free-tier friendly (500k characters/month), production-grade Urdu voice. Groq's own TTS does not yet support Urdu in production (English/Arabic only as of this writing) and is not a substitute. |
| TTS — evaluate as fast-follow | **Uplift AI** | Pakistan-specific Urdu voice model, free tier then ~$5/month, claims better Urdu quality than Azure/OpenAI at lower cost. Worth a direct listening comparison once Phase 0 is live; not a blocker. |
| Database | **Supabase** (managed Postgres + Auth + Storage) | Free tier bundles the three things this project needs most at zero cost; pgvector extension covers FAQ embeddings in the same database instead of a separate, file-based Chroma index. |
| Phone channel orchestration | **LiveKit Agents** (self-hosted, open source), with Groq + Azure/Uplift plugged in, over a SIP trunk | See "Phone Channel" below. |
| Backend hosting | **Render** (free tier) | See Phase 0, Hosting. |
| Frontend hosting | **Vercel** (free tier) | Static hosting, no cold-start concern. |

### Open issue: Groq's Urdu script quality — corrected LLM options research (2026-08-08)

Live testing (2026-08-07) reproduced a real defect: the LLM occasionally substitutes visually-similar Urdu letters (e.g. Noon/Laam confusion, "سامان" mangled) in generated replies. This isn't a prompting bug — it's a known characteristic of Llama-family models, which are trained on comparatively little high-quality Arabic-script data. Since the whole premise of this product is that Sara has to be indistinguishable from a real Urdu speaker, this is worth fixing at the model layer.

**The earlier recommendation to switch to Claude Haiku 4.5 was wrong — corrected after actually finding real benchmark data.** It had been a "strong prior" based on Claude's general multilingual reputation, explicitly never verified. Real data since found (UrduMMLU, arXiv:2606.07167, June 2026 — an academic Urdu-understanding benchmark, not vendor marketing):

| Model | Urdu accuracy | Input / Output $ per M tokens |
|---|---|---|
| Gemini-3.5-Flash | **90.34%** (best of all tested) | $1.50 / $9.00 |
| Gemini-3.1-Flash-Lite | 84.68% | cheaper tier, not yet priced here |
| GPT-5.4 | 84.53% | — |
| Claude-Sonnet-4.6 | 82.94% | — |
| DeepSeek-V4-Flash | 81.42% (best open-weight) | — |
| **Gemma-4-31B-IT** (LiveKit Inference) | 76.39% | $1.20 / M **output** only, extremely voice-latency-optimized (381ms time-to-first-sentence, ~100ms warm token) |
| Claude-Haiku-4.5 | **72.45%** — weaker than open-weight Gemma 4 | $1.00 / $5.00 |
| Groq `llama-3.3-70b-versatile` (current) | not in this benchmark, but live-observed letter-substitution defects | $0.59 / $0.79, 100k tokens/day free |

Two real candidates worth actually testing, not just theorizing about:
1. **Gemini-3.5-Flash** — best raw Urdu accuracy by a wide margin, has a genuinely recurring free tier (unlike Anthropic's one-time credit) for cheap ongoing testing.
2. **Gemma-4-31B-IT via LiveKit Inference** — beats Haiku on Urdu at a fraction of the cost and with dramatically lower latency, purpose-built for voice, and architecturally elegant since LiveKit Agents is already the planned Phase 1 phone-channel stack (§ Phone Channel below) — using Gemma 4 there means one vendor covers LLM + real-time orchestration + eventually telephony, instead of Groq+Azure+custom FastAPI glue. **Real unverified risk**: UrduMMLU is a multiple-choice accuracy benchmark — it says nothing about tool-calling reliability, which is what this codebase's actual bugs have been about (leaked tool-call text, wrong tool selection). A 31B open-weight model's function-calling reliability under our exact `TOOL_SCHEMAS` pattern is untested, and it hasn't been checked for the same script-corruption failure mode caught on Groq specifically.

**OpenRouter as a testing shortcut, not a production base**: one API key gives access to Gemini/Gemma/DeepSeek/Claude/GPT through a single integration, with genuinely free rate-limited models (20 req/min, 200/day, no card) — the fastest way to benchmark several candidates today. Not recommended as the permanent architecture: pure passthrough pricing (no savings over going direct), an added network hop hurting latency for a voice product, and free-tier listings are volatile.

**Per-business LLM model selection — ✅ live (2026-08-08).** Rather than pick one model globally, each business now chooses its own LLM from a dropdown on the Guardrails page (`AppSettings.llm_model`, e.g. `"openrouter:google/gemini-3.5-flash"` or `"groq:llama-3.3-70b-versatile"`). `src/llm.py`'s `LLM_CATALOG` is the single source of truth (provider, model slug, label, quality note), listed best-to-worst by the UrduMMLU accuracy numbers above; `GET /config/llm_models` exposes it to the frontend so the dropdown never hardcodes the list. `ChatEngine` re-reads the business's `llm_model` setting on every `reply()` call (not cached at construction), so switching models takes effect on the next message without needing to recreate the cached `ChatEngine` in `api.py`'s `_chat_engines`. Provider HTTP clients (`Groq`, and `OpenAI` pointed at OpenRouter's base URL for every non-Groq model) are cached per-provider at module level. Requires `OPENROUTER_API_KEY` in `.env` only if a business actually selects a non-Groq model — Groq remains the zero-setup default.

**Real bug found and fixed along the way, unrelated to the provider work itself**: live testing during this refactor (2026-08-08) caught `_looks_like_leaked_tool_call()` missing a real case — the model wrote a normal Urdu greeting/prose reply and then appended a leaked `<function=check_appointment_slots>{...}</function>` tag *after* the prose, which the old `.startswith("<function")` check didn't catch (it only checked the message prefix). Customers were seeing raw function-call syntax mixed into otherwise normal replies. Fixed by checking for `"<function"` anywhere in the content, not just at the start; verified fixed live via the exact reproduction case.

**Eval results — ✅ done (2026-08-08), `scripts/eval_llm_models.py`.** Ran all 6 `LLM_CATALOG` candidates against the real dental-clinic persona/guardrails/tools/FAQ on 4 cases (pain/empathy, cross-lingual tool-calling, a Roman-Urdu greeting, an English query). Two findings, one expected and one not:

1. **The benchmark leader isn't the practical winner.** Gemini 3.5 Flash has the best published Urdu accuracy (90%), but got cut off mid-sentence on 2 of 4 real test cases under this project's `max_tokens=300` (e.g. `"وعلیکم السلام! ہمارا کلینک پیر سے"` — cut off after "Monday from") — it appears to consume tokens differently than the other candidates and needs a larger budget to finish a normal reply. It was also the slowest (up to 15.8s) and most expensive of the six. **Not recommended as configured.**
2. **Gemma 4 31B, Gemini 3.5 Flash Lite, DeepSeek V4 Flash, and Claude Haiku 4.5 all answered every test case correctly** once the FAQ retrieval bug below was fixed — correct clinic hours, correct appointment slots, genuine empathy on the pain case, correct language switching. **Gemma 4 31B is the recommended default**: cheapest (has a literal `$0/$0` free-tier variant on OpenRouter too), fast (1.6-4.4s), and matched or beat the pricier options — a good fit for [[user-mission-pakistan-affordability]]. Gemini 3.5 Flash Lite is the runner-up if slightly more headroom is wanted. Claude Haiku 4.5 is viable but on one run added unprompted medical advice ("you can take a pain medication...") directly against the persona's explicit "avoid giving medical/diagnostic advice" guardrail — not reproduced on a second run (temperature=0.5 randomness), flagged as a mild reliability concern, not disqualifying.

**A bigger bug found along the way, independent of model choice**: `FaqStore.get_context()` only fetched the single closest FAQ match (`.limit(1)`). Live testing surfaced a real failure — for a Roman-Urdu "clinic timings" query, "Where is the clinic located?" (cosine distance 0.1385) narrowly beat "What are your clinic hours?" (0.1399), a gap of 0.0014 that's pure embedding noise. Every model was then working from the wrong grounding fact; some (correctly, per their guardrails) admitted they didn't have the hours, one (Gemini 3.5 Flash Lite, before the fix) hallucinated plausible-but-wrong hours instead. **Fixed**: `get_context()` now returns the top 3 matches within threshold (each labeled with its own question) instead of just the top 1, letting the model pick the actually-relevant fact itself. This affects every business and every model, not just this eval — a real RAG-quality fix, not a model-selection one. Verified fixed live (re-ran the eval, all four viable models then answered hours/slots correctly).

`LLM_CATALOG` in `src/llm.py` is now ordered and annotated by these real results, not the raw benchmark numbers. **All 5 seeded businesses (4 test accounts + the demo account) were switched to `openrouter:google/gemma-4-31b-it` on 2026-08-08**, and it's now the default (`DEFAULT_LLM_MODEL` in `src/llm.py`, `AppSettings.llm_model`'s column default) for any new business too.

### Voice pipeline — three real bugs found via live dashboard use (2026-08-08)

Live use of the dashboard's mic button (not the eval harness - this was normal conversational testing) surfaced three separate problems, all fixed the same day:

1. **STT was badly garbling real Pakistani speech.** A pulled session transcript (Urban Mart, `sessions` table) showed nonsense Urdu transcriptions ("امشانہ ہوں آپ کے پاس کیا کہ یہ پروڈکٹ ہے...") and one outright hallucinated Portuguese sentence on noisy audio - classic local Whisper failure modes. Root cause: `src/stt.py` was running `faster-whisper`'s **"small"** model locally, which is both weak at Urdu generally and specifically bad at Urdu/English code-switching ("kya apka paas class 10 hai"-style sentences, common in real Pakistani speech). **Fixed**: swapped to Groq's hosted `whisper-large-v3-turbo` (`GET https://api.groq.com`, same `GROQ_API_KEY` already used for the LLM) - dramatically more accurate, and removes a local-GPU dependency that would have blocked hosting this in production anyway. `faster-whisper` and `webrtcvad-wheels` dropped from `requirements.txt` (no longer used anywhere). **Not yet re-run against a live conversation** - the fix is smoke-tested (a synthetic tone round-tripped through the real Groq API successfully) but should be judged on real speech once the app is run again.
2. **`/voice_turn` blocked the HTTP response until the TTS audio finished playing out loud.** This is what made a multi-item list reply "take 20 seconds to return" - most of that time wasn't LLM generation, it was `Speaker.say()`'s `aplay` call blocking in real time for however long the full reply took to speak. **Fixed**: the text reply now returns as soon as the LLM finishes; audio plays in a background thread (`threading.Thread(daemon=True)` in `src/api.py`). The dashboard's text bubble now appears as fast as the LLM answers, independent of how long Sara takes to finish saying it out loud.
3. **Mic button changed from click-to-record (VAD-guessed stop) to hold-to-talk**, per direct request - a held button is a more reliable stop signal than guessing from a silence tail, and removes the silence-tail wait itself from the latency budget. `src/mic.py` rewritten around explicit `start_recording()`/`stop_recording()` (a single shared mic slot with a 30s watchdog timeout, since this is one physical mic on one desktop machine) instead of `record()`'s old VAD loop; `POST /voice_turn` split into `POST /voice_turn/start` and `POST /voice_turn/stop`; the dashboard's mic button uses `onMouseDown`/`onMouseUp` (+ touch equivalents) instead of `onClick`. CLI voice mode (`main.py`) adapted to press-Enter-to-start/press-Enter-to-stop, since a terminal can't detect a truly held key without raw-mode input.

**Not yet verified live in the running app** (needs the user's own machine, mic hardware, and speakers) - all three fixes are smoke-tested (unit tests, a synthetic STT round-trip, typecheck) but not confirmed against a real held-button conversation yet.

### Why not a managed voice-agent platform (Retell, Vapi, Bland)?

These platforms were seriously evaluated. Retell AI in particular is a strong product — it added Urdu ASR support in 2026, supports bring-your-own-LLM, and has a documented real-world Urdu+English deployment. It remains a legitimate fallback. It was not selected as the primary path for one reason: **recurring per-minute platform fees compound against margin at every scale**, from the first pilot call through any future high-volume client, and the constraint that matters most for this project — abundant time, scarce capital — favors trading engineering time for a lower permanent cost over paying an ongoing platform fee for convenience.

LiveKit Agents is open source, has native Groq integration, and includes SIP telephony support — the same real-time engineering (barge-in, streaming, turn-taking) a managed platform provides, self-hosted, with no per-minute markup beyond the underlying Groq/Azure/telephony usage already being paid for regardless. The cost is engineering time to build and operate it, which is the one resource this project has in surplus.

**Fallback position**: if the self-hosted phone pipeline is not ready in time for a real client commitment, Vapi's bring-your-own-LLM tier (~$0.05/min platform fee, no LLM markup) is the cheapest managed alternative — materially cheaper than Retell's stacked $0.13–0.31/min for this use case. Retell remains a secondary fallback behind Vapi if Vapi doesn't fit for some reason encountered during Phase 1.

---

## Phase 0 — Detailed Plan

### 1. Data Layer — ✅ live (2026-08-07)

Move off flat JSON files onto Postgres via Supabase. FAQ embeddings move from local ChromaDB onto pgvector in the same database — one durable store instead of two systems that can drift out of sync, and Chroma's on-disk index does not survive a redeploy on most free hosting tiers.

Every table gains a `business_id`. Core schema:

```
businesses           — one row per client business (name, slug, widget key, owner)
persona_configs      — per-business persona/guardrails (was persona.json)
example_bank_entries — per-business few-shot examples
app_settings         — per-business tuning (LLM temperature, TTS rate, VAD cutoff)
faq_entries          — per-business FAQ text + embedding column (was faq.json + Chroma)
stock_items / service_items / menu_items / table_slots / bookings
                     — per-business knowledge base (was store/*.json)
sessions / exchanges — per-business conversation history (was session_log's JSON files)
escalations          — per-business escalation log
```

Tenant isolation is enforced at the application layer (`WHERE business_id = ...` on every query) and proven with an integration test (`tests/test_tenant_isolation.py`) that seeds two distinct fake businesses (a shoe store and a dental clinic) and asserts neither can see the other's stock, FAQ, sessions/exchanges, or escalations — including a dedicated test that deleting a business cascades and leaves zero orphaned rows anywhere. Passing against the real Supabase project, not a mock.

**Security correction (2026-08-07):** the original plan said "application-layer isolation, not Postgres RLS, for Phase 0" — refined after actually setting up the project. Supabase auto-generates a public REST API (PostgREST) over every table by default, reachable with the publishable key — a key that will legitimately end up embedded in client-side widget JS once Phase 0's web widget ships (§5). If that API stays enabled with no RLS, anyone who opens their browser devtools on a client's website can read/write *every* business's data directly through Supabase, completely bypassing FastAPI and the app-layer `business_id` checks. Two independent mitigations, both applied: (1) **the Data API (PostgREST) is disabled entirely** in Project Settings — our backend talks to Postgres directly via a SQLAlchemy connection string, so the auto-REST surface is pure unneeded attack surface; (2) **RLS is enabled on every table with zero policies** (migration `d5716d6ee36f`) — default-deny for any role except the table owner, as defense-in-depth in case the Data API is ever re-enabled later. The backend's own connection is the owning role (via `DATABASE_URL`/`DIRECT_URL`), so this is a no-op for the app itself, confirmed by re-running the isolation tests with RLS on. (Note: this project uses Supabase's newer `publishable`/`secret` key pair, not the legacy `anon`/`service_role` names used in older Supabase docs and in earlier drafts of this plan — same roles, new names. The `secret` key is server-side only, never shipped to any frontend/widget bundle.)

**Implementation notes for whoever touches this next:** `src/models.py` (SQLAlchemy models), `src/db.py` (engine/session, uses `DATABASE_URL` — the transaction-mode pooler, port 6543), `alembic/` (migrations, configured to run against `DIRECT_URL` — the session-mode pooler, port 5432, since transaction-mode pooling doesn't reliably support the session-level locks migrations need). `mic_device`/`speaker_device` were deliberately left out of `app_settings` — those are local-hardware settings for the Electron/CLI app, meaningless for a hosted business.

### 2. Authentication — ✅ live for dashboard login (2026-08-08)

Two distinct trust models:
- **Dashboard login** (business owner): Supabase Auth, email + password. The backend verifies the issued JWT and resolves `business_id` from it.
- **Widget** (anonymous end customers on a client's website): a public per-business `widget_key`, the same trust model used by Intercom/Crisp-style embeds — an identifier, not a secret. Not built yet — lands with the Web Widget (§5).

For the pilot stage (1–3 businesses), no self-serve signup flow is required; each business's login is provisioned manually at onboarding (`scripts/create_business_account.py`).

**Explicit product requirement, not yet built (2026-08-08):** real business owners signing up should get OAuth (Google/GitHub sign-in), not email/password — no password to manage, faster onboarding, and Supabase Auth already supports it natively so this isn't a heavy lift when self-serve signup gets built. Email/password (current state) is fine for the 4 manually-provisioned pilot/test accounts, but should not be the primary path once real businesses are onboarding themselves.

**How dashboard login actually works:** `src/auth.py`'s `get_current_business()` FastAPI dependency takes the request's `Authorization: Bearer <token>` header and forwards it to Supabase's own `/auth/v1/user` endpoint to verify it (rather than reimplementing JWT signature checking or tracking Supabase's signing-key rotation ourselves — one extra network hop per request, acceptable at pilot scale). The verified email is matched against `businesses.owner_email` to resolve `business_id`. Every `src/api.py` endpoint now takes `business: BusinessContext = Depends(get_current_business)` instead of the single startup-pinned business from the pre-auth seam (`src/business_context.py`, which the CLI still uses since it has no login). `src/api.py` keeps one `ChatEngine` per logged-in business (a dict keyed by `business_id`, built lazily), the same singleton-per-conversation pattern as before, just no longer pinned to one business at process start. A throwaway `GET /whoami` (returns `business_id`/`slug`/`business_type`) and `GET /health` (unauthenticated liveness check, used for the frontend's readiness poll) were added alongside it.

Frontend: `frontend/src/lib/auth.ts` calls Supabase's password-grant token endpoint directly (`VITE_SUPABASE_URL`/`VITE_SUPABASE_PUBLISHABLE_KEY` in `frontend/.env`, the publishable key is safe client-side by design) and stores the JWT in `localStorage`; `api.ts`'s `request()` attaches it to every call and clears it on a 401/403. `App.tsx` gates the whole app behind a new `LoginPage.tsx` until `/whoami` succeeds.

**Business type scopes which tools the agent can even see — ✅ live.** Every business row has a `business_type` (`dentist_clinic`, `retail_store`, `clothing_brand`, `restaurant`, `bank`, or `demo` for the original all-tools test business), set at onboarding. `src/tools.py`'s `BUSINESS_TYPE_TOOLS` maps each type to its allowed tool names, and `tool_schemas_for(business_type)` filters `TOOL_SCHEMAS` before `ChatEngine` ever sends them to Groq — not just the tool's *execution* (already `business_id`-scoped since the Backend Refactor), but which tools the model is even offered. This directly addresses the real session log from 2026-08-07 (`20260807T152233-dafbe4.json`) that showed the model calling the *wrong* tool (dental appointment slots) mid-conversation about an unrelated product purchase — a dentist's agent literally cannot call `check_stock` anymore, regardless of what the model guesses.

**Four real test accounts** were created to verify all of this against live data spanning different verticals, each with persona/guardrails/FAQ written in English on purpose (to test that English-authored configuration is followed correctly in an Urdu conversation) — see `scripts/seed_test_accounts.py` for full content and login credentials. All four still work and stay in the repo, but per the current market focus above, only the dental clinic and bank rows are actively pitched/demoed - retail (Urban Mart, Thread House) is dormant, not deleted:

| Business | slug | business_type | Tools offered | Status |
|---|---|---|---|---|
| Bright Smile Dental Clinic | `dental-clinic` | `dentist_clinic` | `check_appointment_slots`, `recommend_human_agent` | **Active focus** |
| Urban Mart | `urban-mart` | `retail_store` | `check_stock`, `recommend_human_agent` | Dormant - deprioritized 2026-08-08, revisit later |
| Thread House | `thread-house` | `clothing_brand` | `check_stock`, `recommend_human_agent` | Dormant - deprioritized 2026-08-08, revisit later |
| Sadiq Bank | `sadiq-bank` | `bank` | `recommend_human_agent` only | **Active focus** |

Testing this surfaced two real bugs, both fixed the same day:
1. **Cross-language name matching failed.** `_best_match()` in `src/tools.py` only did lexical/difflib matching, so a native-Urdu query ("دانتوں کی صفائی") never matched an English catalog entry ("Teeth Cleaning") — no shared characters. It worked by accident for transliterated loanwords (`ایئربڈز` → "earbuds") but not genuine translation pairs. Fixed by adding a multilingual-embedding fallback (`intfloat/multilingual-e5-small`, same model used for FAQ retrieval) when lexical matching finds nothing, at a 0.75 cosine-similarity threshold. Verified live: the same Urdu query now correctly returns Bright Smile's real appointment slots.
2. **English-authored personas could make the agent reply in English to an Urdu message**, despite `reply_language: "auto"`. Root cause: the `LANGUAGE_MODE_INSTRUCTIONS` system message is appended once, early in the prompt — a tool-call round trip (assistant tool-call message + tool result message) pushes it several messages back by the time the final reply is generated, and a long English persona/guardrail block can dominate by sheer recency. Fixed in `ChatEngine._run_tool_calls()` by re-appending the language instruction as the very last message before the final completion call, whenever a tool was used. **Verified live (2026-08-08):** logged in as `bank@sara-test.local`, sent `"میرا اکاؤنٹ نمبر 1234567890 ہے، بیلنس بتائیں"` — reply came back fully in Urdu (`"براہ کرم اپنی اکاؤنٹ کی معلومات کے لیے ہمارے محفوظ چیٹ یا فون لائن کا استعمال کریں۔"`) and correctly never echoed the account number back.

**Two more real bugs found via live dashboard use, both fixed 2026-08-08:**

3. **`auto` reply-language mode had no concept of Roman Urdu.** `LANGUAGE_MODE_INSTRUCTIONS["auto"]` only distinguished Urdu-script vs. English, so the model was left guessing whether Roman Urdu input ("mujha kapre kharedna hn") counted as "English" - live testing showed the same input getting an English reply one turn and an Urdu-script reply the next, purely inconsistent. Fixed by teaching `auto` to recognize Roman Urdu as its own category and reply in kind; also added a dedicated `roman_urdu` reply-language mode (frontend dropdown + `LANGUAGE_MODE_INSTRUCTIONS` entry) for businesses that want it forced rather than auto-detected. Verified directly against the LLM with the exact reported messages.

4. **`tools_instruction` was too conservative, causing the model to ask clarifying questions instead of checking stock.** All 4 seeded businesses' `tools_instruction` (persona config, Postgres) said "never guess an item they didn't mention... if unclear, ask them to clarify" - live testing showed the model over-applying this to *any* generic-but-real item name ("I need shirt," "kirta hai kya") by asking about color/style before ever calling `check_stock`, even though `_best_match()`'s fuzzy matching already resolves these correctly (verified separately: `"kirta"` → `"Embroidered Lawn Kurta (Medium)"` via existing difflib/embedding fallback, no code change needed there). The actual bug was the model never calling the tool in the first place for a plain product name. Fixed by rewriting `tools_instruction` for all 4 businesses (Urban Mart, Thread House, Bright Smile Dental, demo) to call the lookup function immediately on any named item/service - even a broad one - and only ask for clarification when the customer named nothing at all or the message was genuinely garbled. Since `persona.build_system_prompt()` reads `tools_instruction` fresh from Postgres every turn (no caching), this fix went live in the running backend immediately, no restart needed. Verified live: `"I need shirt"`, `"mujhe shirt chahiye"`, and `"kirta hai kya"` against Thread House's real catalog all now correctly return the matched product, price, and stock count instead of a clarifying question.

5. **`_best_match()`'s embedding fallback could confidently return the wrong item for generic category words**, and the model then fabricated a plausible-sounding excuse around the wrong answer. Live case: asked (in Urdu) for "pants" against Thread House's catalog (which has "Men's Slim Fit Jeans," not an item literally named "pants") - Sara replied that pants weren't available and the store was "currently focusing on shirts and kurtas," a reason invented from nothing, not grounded in any tool result or persona config. Root cause, confirmed by dumping the actual embedding scores: `multilingual-e5-small` scored every one of the 5 catalog items within 0.006 of each other for the query "pants" (0.800-0.808) regardless of real relevance - the correct answer (jeans) scored *lower* than an unrelated dress, so taking the argmax as a silent single answer was actively worse than random. Same failure class as the FAQ retrieval top-1 bug above, just in the product/service-matching code path. **Fixed** by splitting `_best_match()` (in `src/tools.py`) into a confident-only matcher (exact/substring/difflib, or an embedding top pick that clears the runner-up by ≥0.03 - e.g. "kirta" vs "Kurta" scores 0.845 vs a 0.798 runner-up, a clear win) and a new `_closest_matches()` used only when nothing is confident, returning up to 5 candidates above the similarity threshold for the LLM to reason over and present honestly ("we don't have that exact item, but here's...") instead of a single silently-wrong pick. Applied to all three lookup tools (`check_stock`, `check_appointment_slots`, `get_menu`). Also caught and fixed a second bug in the fix itself during verification: the "closest matches" list in `check_stock` initially didn't include per-item stock status, so it said out-of-stock jeans were "available" - fixed to reuse the same in-stock/out-of-stock formatting as the full-catalog listing. Verified live end-to-end: `"میں پینٹس لینا چاہتا ہوں"` now gets `"ہمارے پاس اس وقت پینٹس میں صرف Men's Slim Fit Jeans تھیں لیکن وہ فی الحال ختم ہو چکی ہیں..."` - correctly names the actual relevant item and its real stock status instead of an invented excuse.

### 3. Per-Business Provider Credentials & Usage

Each business gets its **own** Groq account and Azure Speech resource, provisioned by us during onboarding — not a shared key across all clients. This matters for a reason beyond isolation: rate limits on Groq (and effectively every LLM/API provider) are enforced at the **account** level, not per-key, so multiple keys under one shared account would still draw from one pooled quota. A dedicated account per business gives each client their own free tier (100k Groq tokens/day, 500k Azure characters/month) — at realistic small-business volume, most clients likely never leave it, meaning near-zero marginal LLM/TTS cost per client rather than one shared pool being split across everyone. **Concretely demonstrated, not just theoretical:** testing all 4 pilot accounts against the one shared `GROQ_API_KEY` in `.env` exhausted its 100k-tokens/day free tier before test coverage was even complete (2026-08-08) — exactly the shared-pool problem this section describes, still open.

Onboarding a business: create its Groq account and Azure Speech resource, store the resulting credentials encrypted (Supabase Vault, already a natural fit given the DB choice) against that business's row. `ChatEngine`, the STT call, and the TTS call are constructed per-business using its own decrypted credentials — a direct extension of the singleton-removal work already required in the backend refactor below, not separate work.

**Usage display** (the "usage bar" requirement, modeled on Claude Code's): two different mechanisms, since the providers expose this differently —
- **Groq**: genuinely live — every API response carries real rate-limit headers (`x-ratelimit-remaining-tokens`, `x-ratelimit-limit-tokens`, and the requests-per-day equivalents). Read directly off the business's own account, refreshed on every real conversation turn.
- **Azure**: no equivalent header, so this is self-tracked — sum characters sent to synthesis per business in a usage log, compared against the known 500k/month ceiling (or a higher figure if that business later upgrades their own Azure plan directly).

When a business's own quota is exhausted, the existing graceful-fallback behavior in `llm.py` (catch the provider error, return a fallback message) now applies per-business instead of platform-wide — and the usage bar simply reads 100%, self-explanatory without extra UI work.

### 4. Backend Refactor — ✅ live (2026-08-08)

Every read/write in the running app moved off local JSON/Chroma onto the Postgres schema from §1: `src/persona.py`, `src/settings.py`, `src/faq_store.py` (Chroma replaced with pgvector `cosine_distance` queries), `src/tools.py`, and `src/session_log.py` are now all Postgres-backed, each function taking a `business_id` (and, where relevant, `session_id`) parameter instead of reading a fixed local file. `src/api.py` and `main.py` were updated to thread it through. A one-off migration script, `scripts/seed_default_business.py`, copied the existing local JSON/FAQ/store data into a real `businesses` row (slug `default`) plus its child rows — including computing and storing pgvector embeddings for all 7 FAQ entries. The local JSON files under `data/` are left in place as a pre-migration snapshot but are no longer read by the app.

`mic_device`/`speaker_device` stay in a small local file (`data/config/local_settings.json`) rather than the `app_settings` table, per the reasoning already recorded in §1 — they're this machine's hardware settings, meaningless for a hosted business.

Every function in `src/tools.py` (`check_stock`, `book_table`, etc.) now takes `business_id` as its first argument, bound by `ChatEngine._run_tool_calls()` at the call site — the LLM itself never sees or supplies it (not part of `TOOL_SCHEMAS`). `recommend_human_agent` additionally takes `session_id` the same way, so escalations land against a real `sessions` row instead of a guessed pointer.

**Pre-auth seam (`src/business_context.py`):** written the same day as this refactor, before dashboard login existed. `src/api.py` has since moved off it entirely onto real per-request `business_id` resolution (§2) — every endpoint now takes `business: BusinessContext = Depends(get_current_business)`, and `ChatEngine` is a dict keyed by `business_id` instead of one startup-pinned singleton. `business_context.py` itself lives on only because `main.py` (the standalone CLI) has no login and still needs a "which business" default. That said, the fix that mattered even before real auth existed still shipped as part of this refactor: `ChatEngine.history` combined with the old JSON `session_log` meant a corrupted or partially-written session file could silently lose a conversation's ground truth; history is now persisted to the `exchanges` table exchange-by-exchange as the conversation happens.

`TOOL_SCHEMAS` business-type filtering (only offer a dentist's agent `check_appointment_slots`, only offer a store's agent `check_stock`) landed in §2 once real `business_type` assignment existed, not in this pass — see §2 for how it works and the real bug it fixes.

Verified live against the real Supabase database (not mocked): stock listing and specific lookup, appointment-slot lookup, FAQ retrieval via pgvector (cosine-distance grounding on "return policy" correctly matched), table booking (confirmed the row actually leaves `table_slots` and lands in `bookings`), and human escalation (confirmed a real `escalations` row with the right `session_id`). `tests/test_tenant_isolation.py`'s 5 tests still pass unchanged.

**Guardrails must hold regardless of which language the customer uses.** A business owner may write their persona/guardrail config in English while customers speak Urdu (or vice versa) — this should already work by construction, since `build_system_prompt()` feeds the persona text to the LLM as-is and the model reads/enforces instructions in whichever language they're written, independent of the conversation's language (the `reply_language` setting added 2026-08-07 only controls *output* language, not instruction comprehension). Confirm this holds with a real test (English guardrails + Urdu conversation) before relying on it — not yet verified live.

### 5. Web Widget Channel

New endpoints (`/widget/session`, `/widget/chat`, `/widget/voice_turn`), authenticated by widget key.

Voice flow: browser records audio via `MediaRecorder` → uploads to the backend → **Groq's hosted Whisper API transcribes it** (replacing the self-hosted `faster-whisper` model — no GPU, no model loading, no CUDA library management on our own infrastructure) → `ChatEngine.reply()` generates the response → Azure synthesizes speech → audio is returned to the browser for playback, replacing today's `arecord`/`aplay`, which only makes sense on a single local machine.

This channel is turn-based (record → upload → reply → synthesize → play), not real-time streaming. This is the right fit for Phase 0: fastest to ship, least new infrastructure, and appropriate for a widget that also needs to do things a call-oriented real-time engine isn't built for anyway — sending photos, links, and guiding page navigation.

### 6. Frontend

Two separate deliverables:
- **Admin dashboard** — the existing React application, extended with a router and login page, and `api.ts` switched from a hardcoded local URL to an environment-configured API base with an attached auth token. Existing pages (Guardrails, Store Data, FAQ, Continuous Learning) carry over largely as-is once scoped to the authenticated business.
- **Embeddable widget** — a separate, minimal bundle (a `<script>` tag a client drops on their own site), isolated via Shadow DOM so its styles don't collide with the host page's.

Electron is dropped as the client-facing product — a browser-based dashboard is simpler to hand to a business than a desktop installer, and matches the stated requirement that not every client will have a suitable machine available.

### 7. Hosting

- Backend: Render, free tier. Flag: free-tier instances sleep after ~15 minutes idle, and cold start here is worse than typical since the process also needs to initialize — mitigated with a scheduled keep-alive ping from day one.
- Database: Supabase, free tier.
- Dashboard and widget bundle: Vercel, free tier — static hosting, no cold-start concern.

---

## Phase 1 — Phone, WhatsApp, and Media Tools

### Phone Channel

**Primary path**: LiveKit Agents (self-hosted), configured with Groq for STT + LLM and Azure/Uplift for TTS, connected to a SIP trunk for PSTN connectivity. This reuses the existing `ChatEngine`/tools/persona logic as the "brain" behind the call — LiveKit is purely the real-time audio/telephony adapter, the same channel-adapter pattern used for the web widget.

**Fallback path**: Vapi (bring-your-own-LLM tier, ~$0.05/min platform fee) if the self-hosted pipeline isn't production-ready in time for a specific client commitment. Retell AI remains available as a secondary fallback — genuinely Urdu-capable and well-documented, just not the primary path given the cost profile above.

A note on Pakistani phone number provisioning: a documented Urdu+English voice agent deployment used Twilio SIP trunks rather than a native Twilio-issued Pakistani number — this is the practical path to pursue rather than assuming a local number can be purchased directly through a global telephony provider.

### WhatsApp

Text and voice notes, in both directions. `/widget/chat` and `/widget/voice_turn` already generalize to "business_id + session_id + text-or-audio-in → text-or-audio-out" — a WhatsApp webhook becomes a third caller of the same underlying functions, with `sessions.channel` already able to hold `'whatsapp'`.

Provider decision not yet made: direct Meta Cloud API (cheaper, more setup, no reseller markup) versus a Business Solution Provider such as Gupshup or 360dialog (easier integration, ongoing cost). Direct Meta API is the leaning given the cost profile, to be confirmed once this phase starts.

One policy detail to design around: WhatsApp permits free-form business messages only within 24 hours of the customer's last message. An escalation that originates from a phone call, not WhatsApp, requires a pre-approved template message to reach the customer via WhatsApp afterward — not a free-form message.

### Media and Invoice Delivery

`src/tools.py`'s `TOOLS_BY_NAME`/`TOOL_SCHEMAS` pattern, and the business-scoped dispatch established in Phase 0, is the seam new tools slot into: `send_product_photo`, `send_invoice` (routed to WhatsApp, email, or SMS depending on what the customer has available), `send_help_video`. Media storage uses Supabase Storage, already provisioned alongside the database.

**Appointment booking via Google Calendar** — an alternative/addition to the existing custom `table_slots`/`bookings` system: `book_table`-style tools call the Google Calendar API (per-business OAuth, stored in Supabase Vault same as the Groq/Azure credentials) to create a real calendar event the business owner already sees in their own calendar app, instead of a booking record only visible inside our dashboard. Worth offering as a business-owner choice at onboarding (some will prefer staying inside our system; some will already run their scheduling off Google Calendar and want it to stay the source of truth).

**Known gap, found live (2026-08-08):** asked the dental-clinic account to book "tomorrow" and it agreed without checking that tomorrow was a Sunday. Root cause: `TableSlot` (`src/models.py`) is just a bare `date_time: str` — no concept of clinic operating days/hours, no recurring generation, and no per-doctor slot management. The seed script only wrote 2 days' worth of rows, so there's no real availability model at all right now, just whatever rows happen to exist. Needed before this is real:
- Business-level operating hours (open days, start/end time, e.g. 9am–6pm) and a slot duration (e.g. 30 min) stored per business, used both to generate the slot grid and to make the agent itself refuse/reschedule around closed days instead of just trusting whatever rows are in `table_slots`.
- A recurring slot-generation job (or generate-on-read for a rolling window) instead of one-off seeded rows, so availability doesn't silently run out.
- A way for the business owner (e.g. the dentist) to open/close individual slots — the WhatsApp channel above is one candidate interface for this once it exists ("check", "uncheck" a slot via message), same idea as the Google Calendar option but staying inside our own system.
This is a real product gap, not yet scheduled against a specific phase — deferred while Phase 0 focuses on core conversation quality (latency, contextual/emotional understanding, tool-scoping correctness) per direct instruction, but it needs to land before any pilot business goes live on real bookings.

**Delivery handoff — calling/messaging a real courier, not modeling logistics ourselves.** When a customer needs something delivered, the agent isn't meant to compute routes or run a courier fleet — it hands off to whichever delivery contact the *business* configures (a rider's WhatsApp/phone number, a local courier service like Leopards Courier, a ride-hailing delivery option like InDrive, or the business owner's own number for manual dispatch). Concretely: a `dispatch_delivery` tool takes the order details + customer address, and either places a WhatsApp/SMS message to the configured delivery contact (reusing the WhatsApp channel above) or — for a phone-only contact — this is exactly the phone channel's outbound-call capability once LiveKit Agents is live, placing a real call to relay the delivery details. Delivery *cost* itself (e.g. a flat per-km rate) is a simple business-configured rate table, not a live pricing API — most local delivery/courier arrangements in this market are informal enough that "call the guy" is genuinely the mechanism, so the tool should make that call/message happen rather than trying to replace it with computed logistics.

### Continuous Learning & RAG Architecture

Today's retrieval is intentionally simple: one embedding model (`multilingual-e5-small`), one flat vector index per business, top-1 match against a fixed distance threshold. That was the right starting point for Phase 0. This section defines the upgrade path once there's real call volume to learn from — both a better retrieval pipeline, and a safe mechanism for the knowledge base to actually grow from real conversations rather than staying static until someone edits it by hand.

**Embedding model.** Checked current options (Aug 2026) rather than assume the existing choice is still competitive:
- **Recommended upgrade: BGE-M3** (BAAI, open-weight, ~568M params, 100+ languages) — the most-downloaded open embedding model, and notable for producing dense, sparse, *and* multi-vector representations from a single model, which directly enables the hybrid search approach below without operating two separate systems. Free, self-hosted, same cost profile as today.
- **Fallback if BGE-M3 is too heavy for free-tier CPU hosting**: `multilingual-e5-large-instruct` — same model family already in use, a smaller incremental step, and specifically documented to outperform much larger LLM-based embeddings on low-resource languages. Both should be benchmarked on real Urdu FAQ data before committing, not chosen on paper alone.
- **Future, paid fast-follow once revenue justifies it**: Qwen3-Embedding-8B (currently the strongest open-weight model on MTEB v2, but too heavy to self-host on free-tier CPU) or a hosted embedding API (Cohere, Google Gemini Embedding) — evaluated later, same pattern as the Azure-vs-Uplift-AI TTS comparison.

**Retrieval technique — hybrid search + reranking**, the current production-standard approach:
1. **Hybrid search**: combine dense vector similarity (the embedding model above) with sparse keyword search (Postgres's native full-text search — already in the same database, no extra system needed), merged via Reciprocal Rank Fusion. Dense retrieval handles paraphrasing and synonyms; keyword search catches exact terms — product names, order numbers, code-switched words — that embeddings alone can miss, which matters more for Urdu than for a high-resource language given comparatively less embedding-model training data.
2. **Reranking**: retrieve a broader candidate set cheaply via hybrid search, then rerank with a cross-encoder (e.g., BGE-Reranker, same open-source family as the embedding model) before handing the top few results to the LLM. Consistently the highest-ROI single improvement to retrieval quality; adds a small latency cost, worth it once quality issues actually appear rather than defaulting to it before Phase 0 data exists to justify it.
3. **Multi-result synthesis, not single-match**: replace today's top-1-with-hard-cutoff with retrieving several candidates above a lower confidence bar and letting the LLM synthesize across them — handles the common case where a full answer spans more than one stored fact.

**Not the same bug as tool-call confusion.** A real session (2026-08-07, `20260807T152233-dafbe4.json`) showed the agent answering a garbled message with the wrong *tool call* (dental appointment slots mid-conversation about buying a book) — this is a tool-selection/grounding problem, fixed directly in `llm.py`/`persona.json` the same day (don't call a tool on unclear input; retry-then-escalate if a tool call leaks as raw text). It's unrelated to FAQ retrieval quality and isn't fixed by the hybrid-search work above — keep the two straight when prioritizing.

**Knowledge classification ("arrange the data for each client")**: every stored knowledge unit gets a `category` (free-form or a light per-vertical taxonomy — policy, pricing, hours, product, etc., since the agent needs to fit a retail shop, a clinic, or a restaurant equally well) and a `source` tag (`admin_entered` vs `call_derived`). This isn't just organizational — it's what lets the dashboard show a business owner which facts they entered themselves versus which the agent picked up from real customer conversations, and lets call-derived facts be weighted or surfaced differently until a human has reviewed them.

**How the knowledge base actually grows from calls** (ties directly to retrieval confidence, not a separate mechanism): when a customer's question scores below the retrieval confidence bar — i.e., nothing in the knowledge base actually answered it well — that low-confidence query is logged as a candidate gap. A periodic pass drafts a candidate FAQ entry from how the LLM ultimately handled it (or flags it as unanswered if it couldn't), surfaced on the Continuous Learning page for a human to approve, edit, or reject — the same page and review pattern already built for promoting few-shot examples. Nothing enters the trusted knowledge base without a human decision; the automation is in *finding and drafting* candidates, not in silently ingesting raw call transcripts. This is a deliberate safety boundary: an uncurated auto-learning loop is a real risk for a business-facing product (a confused customer's wrong statement, a hallucinated tool result, or a deliberately bad "correction" could otherwise corrupt what Sara tells the next customer).

Sources: [multilingual embedding model landscape 2026](https://presenc.ai/research/best-open-weight-embedding-models-2026), [MMTEB benchmark](https://arxiv.org/html/2502.13595v1), [hybrid search + reranking practices 2026](https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026)

### Per-Business Trend Detection ("Vigilance")

Distinct from both the per-conversation history fix (Phase 0, §4) and the FAQ-gap-filling above — this is about noticing *patterns across many separate calls* for one business, not improving any single answer. Concretely: if several different customers report a similar problem with the same product or brand, the agent should become aware of that pattern and start acknowledging it, not treat every caller's complaint as if it's the first anyone's ever raised it.

**Two guarantees that must not be conflated:**
- **Isolation is absolute, not tunable.** A shoe store's agent must never draw on a tyre store's data, under any circumstance. This is already structurally guaranteed by the `business_id` scoping established in Phase 0 and proven by the tenant-isolation test — trend detection is built strictly on top of that boundary, never across it.
- **"Global improvement" is infrastructure only, never data.** The base LLM itself isn't fine-tuned by this project — that's Groq's responsibility. What legitimately improves for everyone at once is the shared RAG pipeline and default persona/guardrail templates. Actual facts, complaints, and trend data belonging to one business are never visible to another's agent, regardless of how the underlying infrastructure improves.

**Mechanism:**
1. **Issue extraction.** After a call where a customer reports a problem, a lightweight classification step (reusing Groq, similar to how `recommend_human_agent` already captures a `reason`) extracts a structured record: `{business_id, product_or_brand, issue_category, description, session_id}`, stored in a new `issue_reports` table with an embedding of the description — so differently-worded complaints about the same underlying problem still cluster together, not just exact string matches.
2. **Trend detection.** A periodic pass (or a check triggered on each new report) clusters recent `issue_reports` for a business by embedding similarity within a rolling window (e.g., the last 30 days). Crossing a threshold (e.g., 3+ similar reports) marks it an active trend for that business.
3. **Surfaced to the business owner** as a panel on the Continuous Learning page — "3 customers in the last 2 weeks reported [issue] with [brand]" — visible and actionable, not buried in raw transcripts.
4. **Fed back into the live conversation.** An active trend is injected into that business's context the same way FAQ grounding already works — so a future caller asking about that brand gets a reply that acknowledges the known issue instead of the same generic response every time. This is a direct, concrete way to serve the original "feel less like a generic AI, more like an attentive person" goal from early in this project — Sara noticing a pattern and saying so is a meaningfully more human behavior than answering every call in isolation.

Same safety posture as the FAQ-learning mechanism above: detection and surfacing are automatic, but nothing changes what the agent says to customers without passing through the same trusted-context mechanism already governing FAQ grounding — this isn't a separate, less-controlled path into the conversation.

---

## Multi-Modal Input (Customer Photos & Screenshots)

A real scenario worth designing for: a customer sends a photo of a damaged product, or a screenshot of an error/receipt, and expects the agent to understand it — directly relevant to the trend-detection feature above (a photo of a defective product is exactly the kind of report that should feed `issue_reports`).

**Tested empirically before committing to anything** (Aug 2026), rather than trusting vendor claims — findings:
- The vision-capable models originally identified (Llama 4 Scout/Maverick on Groq) were **deprecated in Feb/March 2026**, moved to enterprise-committed-spend only. Not available on free/developer tier. The current Groq model list has no dedicated vision offering; `openai/gpt-oss-120b` (the current flagship free/dev-tier model) rejects image input outright. `qwen/qwen3.6-27b` does accept images, but isn't positioned by Groq as a supported vision model — a fragile dependency to build on, not a stable foundation.
- Ran a real test: a synthetic customer-complaint screenshot (Urdu text, Noto Nastaliq Urdu font, an order/product/complaint layout) through `qwen/qwen3.6-27b`. Result was a genuine, specific pattern, not a blanket pass or fail — it **reliably read the primary, clearly-labeled complaint field correctly** ("مسئلہ: جوتے کا سول ٹوٹا ہوا ہے" — problem: the shoe sole is broken, read and understood correctly), but **consistently mangled secondary details** — an ordinal number ("third time") and less common phrasing came back as near-nonsense in two separate runs.

**Design implication**: treat vision input as good enough for **triage** — understanding the gist of what a customer is showing — but never as ground truth for anything precise. Order numbers, dates, counts, or exact quotes extracted from an image must be confirmed verbally with the customer before being acted on or written into `issue_reports`/`stock`/`bookings`, not trusted directly from a single vision-model read. This also means the trend-detection design above is already correctly shaped for this limitation — it clusters *independent reports across separate customers and sessions* rather than depending on any single customer's self-reported claim of recurrence, which is exactly the kind of detail vision input proved unreliable on.

**Before relying on this in production**: re-run this same test against whichever vision model is actually available and current at implementation time (model availability and quality both shift fast — this section should be re-verified, not assumed still accurate, once Phase 1 implementation starts), and evaluate Azure AI Vision's OCR (Read API, which lists Urdu support) as a dedicated text-extraction pass for the precision-critical cases, rather than relying solely on a general vision-LLM's built-in reading ability.

---

## Business Strategy

### Positioning

Start with local Pakistani businesses, not enterprise clients. This is the correct sequencing for the stated constraints — faster sales cycles, no enterprise procurement or compliance overhead, and a path to real case studies and product refinement before any attempt at a larger deal.

### The Management Dashboard as a Second Product

The admin dashboard being built for Phase 0 regardless — stock, appointment slots, menu/pricing management — is, independent of the voice agent, a usable lightweight business management tool. This does not require separate development; it changes only the pitch: a client gets an AI support agent *and* a dashboard to manage their own inventory, bookings, and pricing from the same product.

### Cost Structure Per Client

With each business on its own Groq account and Azure resource (see Phase 0, §3), most small-business volume (10–100 customer interactions/day) likely stays within that business's own free tier entirely — near-zero marginal provider cost per client, rather than a shared pool. Even in the worst case of a client exceeding their free tier, the overage at this volume is on the order of a few dollars to roughly $15/month. Either way, this leaves substantial margin for a low, locally-appropriate flat-rate monthly price — usage-based billing is avoided deliberately, since a flat rate is far easier for a non-technical business owner to understand and budget for than a variable bill tied to infrastructure consumption they don't see.

### Payments

- **Paying upstream providers** (Groq, etc.): pure pay-as-you-go, no minimum commitment, no upfront charge — billed monthly or at spend thresholds, with spend limits available to cap risk. A standard Pakistani bank-issued Visa/Mastercard should work; confirm "international online transactions" is enabled with the issuing bank, the common practical obstacle.
- **Collecting from local clients**: plan around what's realistic for the target market rather than a card-based checkout flow — bank transfer, JazzCash/Easypaisa, or cash for the earliest pilot clients while a track record is being established. More structured billing can follow once there is a track record to build on.

---

## Enterprise / Hyperscale Considerations (Future Reference, Not Current Scope)

Preserved from an earlier analysis of a hypothetical large client (a national bank, ~100,000 calls/day), so the reasoning doesn't need to be redone if a comparable opportunity arises:

- At that volume (~9M minutes/month), a managed platform's bundled pricing ($0.13–0.31/min all-in) would cost **$1.17M–$2.79M/month** — untenable at that scale, and the clearest illustration of why the self-hosted orchestration path matters even at today's much smaller scale.
- Self-hosting the LLM specifically on generic cloud GPUs is not the fix: a single AWS `p4d.24xlarge` instance (needed for a 70B-parameter model) costs roughly $23,600/month running continuously — more than Groq's managed API already costs for equivalent load (~$15,000/month under the assumptions used). Groq's purpose-built inference hardware already beats generic GPU economics; there is no clear win in self-hosting the LLM layer itself.
- The actual cost driver in a managed platform at scale is the bundled platform and telephony markup, not the LLM — which is exactly why the self-hosted LiveKit + Groq architecture chosen above for Phase 1 is also the correct direction at any future larger scale, not a decision that needs revisiting later.
- A deal at this scale is a different business — compliance, data residency, uptime SLAs, and a real operating team, not solo engineering work. This should be modeled precisely once such an opportunity is real, not built speculatively in advance.

---

## Open Decisions

- WhatsApp provider: direct Meta Cloud API versus a Business Solution Provider (leaning direct Meta, not yet confirmed).
- Actual local price point — requires market feedback from real prospective clients, not an abstract estimate.
- Naming and branding for the dashboard and widget.

---

## Immediate Next Steps

1. ✅ **[User]** Create a free [Supabase](https://supabase.com) project (2026-08-07).
2. ✅ **[Agent]** Enable `pgvector`; write the SQLAlchemy models and Alembic migrations (2026-08-07).
3. ✅ **[Agent]** Seed two deliberately distinct fake businesses and prove tenant isolation (2026-08-07).
4. ✅ **[Agent]** Backend refactor — every read/write path moved onto Postgres, `business_id`-scoped throughout, verified live (2026-08-08). See Phase 0 §4.
5. ✅ **[Agent]** Dashboard login (`src/auth.py`, Supabase JWT verification via `/auth/v1/user`), `business_type`-based tool scoping, and a frontend login page — 4 real test accounts (dental clinic, retail store, clothing brand, bank) created and verified live, including cross-language name matching and English-guardrail-in-Urdu-conversation fixes (2026-08-08). See Phase 0 §2.
6. ✅ **[Agent]** Re-verified the English-guardrail language-reassertion fix live against the bank test account (2026-08-08) — Urdu in, Urdu out, account number correctly withheld. See Phase 0 §2.
7. **[Agent]** Per-business provider credentials (Groq/Azure per business, Supabase Vault) — the shared-key rate-limit collision from testing today (§3) is the concrete case for doing this next, before onboarding any real pilot client.
8. **[Agent]** Widget key / anonymous end-customer auth, and the web widget channel itself (§5) — dashboard login only covers the business owner side so far.
9. ✅ **[User decision]** Narrowed active market focus to dental clinics and banks; retail (`retail_store`/`clothing_brand`) deprioritized but kept in the codebase for a later push (2026-08-08). See Executive Summary.
