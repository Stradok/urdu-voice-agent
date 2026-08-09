# Sara — Product & Pricing Strategy

**Status: draft v1, 2026-08-09.** Grounded in this project's own real infrastructure costs (established live in `plan.md`/`README.md`) plus market research below. Treat the specific PKR/USD figures as a starting point to validate against actual pilot customers, not a locked-in price — re-verify before committing to a rate card, same discipline used throughout `plan.md`.

## 1. Market position

Sara is scoped to **two verticals only: dental/medical clinics and banks** (`plan.md`'s Executive Summary, decided 2026-08-08) — not general retail. This wasn't an arbitrary narrowing: every real correctness bug found in live testing traced back to the retail stock-matching path (open-ended catalogs, sizes, variants). Clinics and banks are structurally easier to make *excellent* rather than *broad*:

- A **bank's** entire tool surface is deliberately narrow — no account access at all, everything sensitive routes to a human. Low complexity, low risk, matches where regulation is heading anyway (§3).
- A **clinic's** tool surface is one bounded action — check/book a real appointment slot against real business hours (`src/scheduling.py`, shipped 2026-08-09).

That narrowness is a genuine competitive advantage for a two-person team with no capital: it's the difference between being mediocre at four things and excellent at two.

## 2. Competitive & cost anchors (researched, not assumed)

| Reference point | Cost | Why it matters |
|---|---|---|
| A Pakistani text-only chatbot (local dev shops) | PKR 5,000–15,000/mo | The low end of what local businesses already pay for far less capability (no voice, no Urdu code-switching, no real tool-calling) |
| A Pakistani voice chatbot, ~100 calls/day | PKR 75,000–90,000/mo | The closest local comparable to what Sara does — this is the price to undercut, not match |
| A single Pakistani support staff member | PKR 25,000–45,000/mo | The real alternative a small clinic/bank branch is weighing Sara against — a human, not a SaaS category. Sara needs to comfortably beat this to be an easy yes, since a human also does things Sara can't (yet) |
| Western AI voice-agent SaaS (Aircall, Vapi-class) | $300–1,200/mo ($0.08–0.20/min) | Irrelevant as a direct comparable (wrong market, wrong currency) but useful as a ceiling — confirms Pakistani SMB pricing needs to be a small fraction of US norms, not a discount off them |

**Read:** the addressable price band for a real paying customer is roughly **PKR 10,000–35,000/month** — well above what a bare text chatbot charges (Sara does more), well below what a local voice-chatbot shop or a human salary costs (the actual competition), and nowhere near US SaaS pricing (irrelevant comparison for this market).

Sources: [House of Digital Solutions — chatbot cost Pakistan 2026](https://www.hods.io/chatbot-development-cost-in-pakistan), [Aircall — AI voice agent cost 2026](https://aircall.io/blog/best-practices/ai-voice-agent-cost/)

## 3. Regulatory context (why the current tool scope is the right one, not just the safe one)

The State Bank of Pakistan is in **advanced stages of finalizing AI guidelines for financial services**, oriented around transparency, accountability, and consumer protection. The direction of travel for 2026 banking AI generally: a banking chatbot must resolve real questions, **refuse to give regulated advice it isn't qualified to give, and produce an audit trail that survives a compliance review**.

Sara's current bank design — zero account access, mandatory human escalation for anything account-specific, and now a real reference-code audit trail (`Escalation.reference_code`, shipped 2026-08-09) — already satisfies the strictest plausible reading of where this is heading. **Do not build account-linked banking tools ahead of SBP's actual published guidelines** — the conservative posture is a compliance advantage, not just a caution.

Sources: [BPC — what SBP's new guidelines mean for banks](https://www.bpcbt.com/blog/what-the-state-bank-of-pakistans-new-guidelines-mean-for-banks), [Dawn — regulations for AI use in banks on the cards](https://www.dawn.com/news/1906849/regulations-for-ai-use-in-banks-on-the-cards)

## 4. Cost-to-serve model

Per-business monthly infrastructure cost, using this project's own established real numbers (`plan.md` §3, `README.md`'s pipeline-stage cost table):

| Line item | Free tier | Standard (dedicated) | Enterprise |
|---|---|---|---|
| Supabase (DB) | Shared free project (7-day pause risk) | Shared Pro ($25/mo split across all Standard customers) | Dedicated project or higher Supabase tier |
| Render (backend) | Shared free instance (cold-start risk) | Shared Starter ($7/mo split across customers) | Dedicated instance |
| Groq (STT + optional LLM) | Shared 100k tokens/day (this already broke once under test load) | **Own Groq account** (still-open item, `plan.md` §3) — free tier per business | Own account, paid tier if volume needs it |
| OpenRouter (LLM, Gemma 4 31B default) | Shared free-tier variant | Own key, likely still free-tier at this volume | Own key |
| Azure Speech (TTS) | Shared F0 (500k chars/mo) | Own F0 grant per business — plenty for one clinic/branch | Own grant, S0 paid tier if needed |

**Realistic marginal cost per Standard customer once shared hosting is amortized across ~10-20 customers: roughly $2–8/month (PKR 600–2,200).** The dominant fixed costs (Supabase Pro, Render Starter) are shared infrastructure, not per-customer — they don't scale linearly with customer count until real volume growth forces dedicated resources. This is the same "near-zero marginal cost per client" structure already identified in `plan.md` §3 for provider credentials specifically.

**The one item that must not be skipped before selling Standard/Enterprise seats**: per-business Groq/OpenRouter credentials (`plan.md` §3's still-open item). Multiple paying customers sharing one Groq key is the exact failure already reproduced live this session (100k-token/day quota exhausted mid-testing) — at real paying-customer volume this becomes an outage, not an inconvenience.

## 5. Tiers

| | **Free** | **Standard** | **Enterprise** |
|---|---|---|---|
| **Who it's for** | Trial / lead generation, one clinic or bank owner evaluating Sara | A single clinic or a single bank branch, real paying customer | Multi-branch bank, clinic chain, or a business needing data-residency/custom integration |
| **Conversations/month** | 100 (hard cap) | ~1,500 (soft cap — see below) | Custom / high volume |
| **Channels** | Dashboard only | Dashboard + (once built) web widget | All channels incl. phone/WhatsApp when live |
| **Voice + text** | Both | Both | Both |
| **Appointment booking / escalation ticketing** | Yes | Yes | Yes, plus priority routing |
| **LLM/STT credentials** | Shared | **Dedicated per business** (required — see §4) | Dedicated, higher-tier where needed |
| **Uptime** | Best-effort (Render free tier sleeps) | Always-warm | Always-warm + SLA |
| **Data residency** | Standard (Supabase default region) | Standard | Configurable, given Pakistan's data-localization trajectory (`plan.md`, Phase 1 note on the National Data Governance Policy) — relevant for health-adjacent and financial data specifically |
| **Support** | Community/email | Email + WhatsApp | Priority, named contact |
| **Suggested price** | **PKR 0** | **PKR 15,000/month** (~$55) | **PKR 45,000+/month** (~$160+), custom |

**Why PKR 15,000 for Standard**: roughly **5–6x cheaper than a comparable local voice chatbot** (PKR 75-90k/mo), **comfortably cheaper than one support staffer** (PKR 25-45k/mo) while working 24/7 in both Urdu and English, and still carries a **healthy multiple over the ~PKR 600-2,200 marginal cost to serve** once shared infra is amortized. This is a price a clinic owner or bank branch manager can approve without escalating to head office — that matters more here than maximizing per-customer revenue.

**Why the Free tier has a hard cap, not a soft one**: unlike Standard, Free tier runs on shared infrastructure with the exact quota-collision risk already reproduced live (Groq's 100k/day limit). A hard 100-conversation cap keeps Free tier from ever being the thing that breaks a paying Standard customer's shared quota.

## 6. Capacity — what breaks first, and when to upgrade

Working backward from real limits already hit or measured this session:

- **Groq's shared 100k-tokens/day** is the first thing to break under multi-business load — already reproduced live. This is why dedicated per-business keys are a Standard-tier requirement, not a nice-to-have.
- **Render free tier's cold-start** (30-60s wake-up after 15 min idle) is a real UX failure for any business with real customers depending on responsiveness — this alone justifies the jump from Free to Standard for anyone actually live.
- **A single clinic's realistic volume**: even a busy solo-dentist practice booking ~20-30 patients/day plus FAQ traffic lands well under 1,500 conversations/month — Standard's soft cap has real headroom, not a hidden squeeze.
- **A single bank branch**: likely lower real conversational volume than a clinic (most banking queries are FAQ-shaped or immediately escalated), so Standard's cap is generous here too.
- **Multi-branch banks or clinic chains** are the actual trigger for Enterprise — not raw volume from one location, but *multiple locations each needing their own isolated persona/data* (already the schema's design, `business_id`-scoped throughout) plus centralized billing/reporting, which doesn't exist yet and would be real Enterprise-tier build work.

## 7. Tool integration roadmap — banks and clinics specifically

The generic "voice agent tool integration" research from earlier in this project (the Perplexity model-council report) was scoped to a much bigger e-commerce/logistics product than what Sara actually is now. This section is scoped correctly: integrations that matter for *this* market.

### Clinics: integrate with what they already run, don't replace it

Pakistani clinics already have a real, mature local software market for practice management — **iTack Solutions, Instacare, e-Mareez, HCloud, DocEngage** all offer cloud-based EMR/appointment/billing systems already in use. This is a critical finding: **a clinic that already runs one of these will not want a second, disconnected appointment system.** The right integration posture is not "replace their EMR with Sara's booking system" — it's "Sara's voice/chat front door writes into whatever the clinic already uses."

Concretely, once there's real pilot demand:
- `src/tools.py`'s `book_appointment` (shipped 2026-08-09) is already the right internal shape — a thin sync layer to push a confirmed booking into the clinic's existing PMS (most of these vendors expose some form of API or at minimum a calendar export) is additive work, not a rewrite.
- This is a genuine differentiator to lead with in clinic sales conversations: "Sara doesn't replace your existing system, she's the voice/Urdu front door to it."

Sources: [SoftwareSuggest — clinic management software Pakistan 2026](https://www.softwaresuggest.com/clinic-management-software/pakistan), [Instacare EMR](https://instacare.com.pk/emr-software-in-pakistan/)

### Banks: stay read-only + human-handoff until SBP's guidelines are published

Per §3, the regulatory direction is toward audit trails and refusing unqualified regulated advice — exactly what Sara's current design already does. **Resist the temptation to build account-linked tools (balance checks, transaction lookups) even if a pilot bank asks for them**, until SBP's guidelines are actually published and reviewed. The tool integration that *does* make sense for banks now:
- Deeper FAQ/knowledge-base grounding (already the architecture, `src/faq_store.py`) — most real banking queries are policy/procedure questions ("how do I open an account," "what documents do I need"), not account-specific.
- The reference-code ticketing system (shipped 2026-08-09) *is* the audit trail SBP-style guidelines will likely expect — this is already ahead of the requirement, worth stating explicitly in any bank sales conversation.
- Branch/agent routing (which human a given escalation reaches) is a reasonable next tool-integration step that stays entirely on the safe side of the regulatory line — routing metadata, not account access.

### Both verticals: WhatsApp is the highest-leverage next integration, not a bank/clinic-specific one

Independent of vertical, `plan.md`'s already-planned WhatsApp channel (§5) is the single highest-leverage integration for this market — it's how Pakistani customers already expect to reach a business, and per the earlier research this session, WhatsApp Business Calling is free for user-initiated calls (vs. Twilio PSTN's $0.155-0.18/min). This isn't a bank or clinic-specific integration, but it's more valuable than any vertical-specific one until it exists.
