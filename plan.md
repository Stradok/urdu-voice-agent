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

1. **[User]** Create a free [Supabase](https://supabase.com) project — provides the Postgres connection string and JWT secret needed to begin the backend refactor. This is the only account currently blocking code; everything else (LiveKit, Uplift AI, WhatsApp, etc.) belongs to Phase 1.
2. **[Agent]** Enable the `pgvector` extension; write the SQLAlchemy models and Alembic migration for the schema above.
3. **[Agent]** Seed two deliberately distinct fake businesses (e.g., retail and restaurant) so tenant isolation is provable from the first test, not assumed.
4. **[Agent]** Build `src/db.py` and `src/auth.py` (JWT verification, `business_id` resolution), proven with a throwaway `/whoami` endpoint before any further work proceeds.
