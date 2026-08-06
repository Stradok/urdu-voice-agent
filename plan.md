# Sara — Production Roadmap

## Executive Summary

Sara is an Urdu-language customer support agent — voice and text, with English code-switching support — currently implemented as a single-tenant desktop application. This document defines the path from that prototype to a hosted, multi-tenant product serving multiple client businesses across web, WhatsApp, and phone channels.

The strategic position is deliberate: this project assembles existing, proven infrastructure (LLM inference, speech services, telephony) into a vertical product for a specific market — Urdu-speaking customer support for Pakistani SMBs — rather than building competing infrastructure from scratch. Given the constraints (minimal capital, available time, no existing client base), this is the correct posture: capital-light, revenue-first, building on suppliers rather than competing with them.

## Current State

A single-tenant Electron desktop application:
- One business's persona, FAQ index, inventory/menu/booking data, and session log, stored as flat JSON files on one machine.
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
| LLM (conversation logic) | **Groq**, `llama-3.3-70b-versatile` | Already integrated; among the cheapest and fastest inference available ($0.59 / $0.79 per M input/output tokens); free tier sufficient for pilot development. |
| Speech-to-text | **Groq hosted Whisper** (`whisper-large-v3`) | $0.04/hour, Urdu-capable, removes the self-hosted GPU/CUDA dependency the project currently carries (`faster-whisper` + a machine-specific CUDA-12 library workaround). One less piece of infrastructure to operate. |
| Text-to-speech | **Azure Speech** (`ur-PK-UzmaNeural`), already integrated | Proven, free-tier friendly (500k characters/month), production-grade Urdu voice. Groq's own TTS does not yet support Urdu in production (English/Arabic only as of this writing) and is not a substitute. |
| TTS — evaluate as fast-follow | **Uplift AI** | Pakistan-specific Urdu voice model, free tier then ~$5/month, claims better Urdu quality than Azure/OpenAI at lower cost. Worth a direct listening comparison once Phase 0 is live; not a blocker. |
| Database | **Supabase** (managed Postgres + Auth + Storage) | Free tier bundles the three things this project needs most at zero cost; pgvector extension covers FAQ embeddings in the same database instead of a separate, file-based Chroma index. |
| Phone channel orchestration | **LiveKit Agents** (self-hosted, open source), with Groq + Azure/Uplift plugged in, over a SIP trunk | See "Phone Channel" below. |
| Backend hosting | **Render** (free tier) | See Phase 0, Hosting. |
| Frontend hosting | **Vercel** (free tier) | Static hosting, no cold-start concern. |

### Why not a managed voice-agent platform (Retell, Vapi, Bland)?

These platforms were seriously evaluated. Retell AI in particular is a strong product — it added Urdu ASR support in 2026, supports bring-your-own-LLM, and has a documented real-world Urdu+English deployment. It remains a legitimate fallback. It was not selected as the primary path for one reason: **recurring per-minute platform fees compound against margin at every scale**, from the first pilot call through any future high-volume client, and the constraint that matters most for this project — abundant time, scarce capital — favors trading engineering time for a lower permanent cost over paying an ongoing platform fee for convenience.

LiveKit Agents is open source, has native Groq integration, and includes SIP telephony support — the same real-time engineering (barge-in, streaming, turn-taking) a managed platform provides, self-hosted, with no per-minute markup beyond the underlying Groq/Azure/telephony usage already being paid for regardless. The cost is engineering time to build and operate it, which is the one resource this project has in surplus.

**Fallback position**: if the self-hosted phone pipeline is not ready in time for a real client commitment, Vapi's bring-your-own-LLM tier (~$0.05/min platform fee, no LLM markup) is the cheapest managed alternative — materially cheaper than Retell's stacked $0.13–0.31/min for this use case. Retell remains a secondary fallback behind Vapi if Vapi doesn't fit for some reason encountered during Phase 1.

---

## Phase 0 — Detailed Plan

### 1. Data Layer

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

Tenant isolation is enforced at the application layer (`WHERE business_id = ...` on every query) and proven with an integration test that seeds two distinct fake businesses and asserts neither can see the other's data or resources — not assumed correct by construction.

### 2. Authentication

Two distinct trust models:
- **Dashboard login** (business owner): Supabase Auth, email + password. The backend verifies the issued JWT and resolves `business_id` from it.
- **Widget** (anonymous end customers on a client's website): a public per-business `widget_key`, the same trust model used by Intercom/Crisp-style embeds — an identifier, not a secret.

For the pilot stage (1–3 businesses), no self-serve signup flow is required; each business's login is provisioned manually at onboarding.

### 3. Per-Business Provider Credentials & Usage

Each business gets its **own** Groq account and Azure Speech resource, provisioned by us during onboarding — not a shared key across all clients. This matters for a reason beyond isolation: rate limits on Groq (and effectively every LLM/API provider) are enforced at the **account** level, not per-key, so multiple keys under one shared account would still draw from one pooled quota. A dedicated account per business gives each client their own free tier (100k Groq tokens/day, 500k Azure characters/month) — at realistic small-business volume, most clients likely never leave it, meaning near-zero marginal LLM/TTS cost per client rather than one shared pool being split across everyone.

Onboarding a business: create its Groq account and Azure Speech resource, store the resulting credentials encrypted (Supabase Vault, already a natural fit given the DB choice) against that business's row. `ChatEngine`, the STT call, and the TTS call are constructed per-business using its own decrypted credentials — a direct extension of the singleton-removal work already required in the backend refactor below, not separate work.

**Usage display** (the "usage bar" requirement, modeled on Claude Code's): two different mechanisms, since the providers expose this differently —
- **Groq**: genuinely live — every API response carries real rate-limit headers (`x-ratelimit-remaining-tokens`, `x-ratelimit-limit-tokens`, and the requests-per-day equivalents). Read directly off the business's own account, refreshed on every real conversation turn.
- **Azure**: no equivalent header, so this is self-tracked — sum characters sent to synthesis per business in a usage log, compared against the known 500k/month ceiling (or a higher figure if that business later upgrades their own Azure plan directly).

When a business's own quota is exhausted, the existing graceful-fallback behavior in `llm.py` (catch the provider error, return a fallback message) now applies per-business instead of platform-wide — and the usage bar simply reads 100%, self-explanatory without extra UI work.

### 4. Backend Refactor

The most significant correctness issue to resolve in this pass: `ChatEngine.history` currently holds one shared, in-memory conversation history for the entire server process — every caller, indefinitely. This becomes per-conversation history loaded from the `exchanges` table. `session_log.py`'s module-level "current session" pointer is replaced the same way — real rows scoped by business and session, not a global pointer.

Every function in `src/tools.py` (`check_stock`, `book_table`, etc.) gains a `business_id` parameter, bound at the call site — the LLM itself never sees or supplies it.

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

1. **[User]** Create a free [Supabase](https://supabase.com) project — provides the Postgres connection string and JWT secret needed to begin the backend refactor. This is the only account currently blocking code; everything else (LiveKit, Uplift AI, WhatsApp, etc.) belongs to Phase 1.
2. **[Agent]** Enable the `pgvector` extension; write the SQLAlchemy models and Alembic migration for the schema above.
3. **[Agent]** Seed two deliberately distinct fake businesses (e.g., retail and restaurant) so tenant isolation is provable from the first test, not assumed.
4. **[Agent]** Build `src/db.py` and `src/auth.py` (JWT verification, `business_id` resolution), proven with a throwaway `/whoami` endpoint before any further work proceeds.
