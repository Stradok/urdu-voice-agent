# Voice-Enabled Support Agent, Pakistan Solo Builder — Model & Stack Recommendation (Aug 2026)

*Council member: Claude Opus 5. Angle taken: the binding constraints here are **not** model intelligence. They are (1) the Urdu **output** path, (2) telephony economics in Pakistan, and (3) the fact that vision + browsing must be pulled *out* of the voice loop. I go deep on those and treat "which LLM" as a downstream, swappable decision.*

---

## 0. The one-paragraph answer

Use a **modular STT → LLM → TTS pipeline**, not a native speech-to-speech model, and orchestrate it with **Pipecat or LiveKit Agents** (both free, Apache-2.0/BSD). Brain: **Gemini 3.1 Flash / 3.5 Flash** as the in-call conversational + tool-calling model, with **Claude Opus-class or GPT-5.x** reserved for a slower "async task agent" that runs after the call. Ears: **ElevenLabs Scribe v2 Realtime**. Mouth: **ElevenLabs Eleven v3** (the only ElevenLabs model that supports Urdu) or **Sarvam Bulbul V3** as the cheap Hinglish-native alternative. Retrieval: **two separate indexes** — text via Gemini Embedding 2 or Cohere Embed v4, images via a *fine-tuned* SigLIP-2/CLIP — joined by a reranker (**voyage-rerank-2.5-lite** or self-hosted BGE-v2-m3). Vision product matching runs **asynchronously** via a VLM verifier, never inside the 600 ms voice turn. **No computer-use model at v1.** And the single biggest line on the bill is not any of the above: it is the phone call.

---

## 1. The cost inversion nobody budgets for: PSTN in Pakistan costs more than the AI

Twilio's published Programmable Voice rate card for Pakistan is **$0.1550/min for local numbers and $0.1800/min to Pakistani mobile**, versus **$0.0040/min for browser/app (WebRTC)** legs ([Twilio Pakistan pricing](https://www.twilio.com/en-us/voice/pricing/pk)). A well-tuned OpenAI Realtime session runs ~$0.04–$0.10 per conversational minute ([Fora Soft](https://www.forasoft.com/blog/article/openai-realtime-api-voice-agent-production-guide-2026), [aireiter](https://aireiter.com/blog/openai-realtime-api-pricing)), and a Gemini Live session about $0.005/min in + $0.018/min out ([Google pricing](https://ai.google.dev/gemini-api/docs/pricing)). **Telephony is 2–10× the model cost.** Any optimization effort spent shaving the LLM bill before fixing the channel is misallocated.

Two levers, both large:
- **WhatsApp Business Calling API.** Meta bills **nothing for user-initiated calls** — a customer taps a call button inside the chat thread and connects over data, no PSTN leg; only business-*initiated* outbound calls are metered, in six-second pulses ([ChatMaxima](https://chatmaxima.com/blog/whatsapp-business-calling-pricing-2026/)). Independent BSP writeups put the practical all-in stack at ₹0.40–0.60/min including the agent-side SIP bridge versus ₹0.45–1.20/min for PSTN, with no DLT-equivalent registration ([RichAutomate](https://richautomate.in/blog/whatsapp-business-calling-api-india-2026-implementation-guide)). In a WhatsApp-first market this is the correct primary channel. Note the countervailing risk: Meta has announced that from **1 Oct 2026 service messages stop being free** and move to per-message pricing ([industry notice](https://www.linkedin.com/posts/manozthapa_whatsapp-update-oct-1-2026-activity-7482342007928102912-w1-u)) — that affects chat, not the free inbound-call path, but it shows Meta will reprice.
- **In-app / web WebRTC** for the storefront ("talk to us" button): $0.004/min-class transport, and Pipecat/LiveKit give it to you natively ([LiveKit vs Pipecat](https://www.evalgent.com/blog/pipecat-vs-livekit)).

Keep a PSTN number for legitimacy and inbound, but architect so that *most* minutes never touch it.

---

## 2. Speech-to-speech vs pipeline — decided by Urdu, not by latency

This is where I diverge most sharply from the default 2026 advice ("just use a native S2S model").

**The Urdu output path is the narrowest part of the whole stack.** Concretely:

| Component | Urdu support | Note |
|---|---|---|
| ElevenLabs **Flash v2.5** (~75 ms, $0.05/1k chars) | **No** — 32 languages, Urdu not among them | The cheapest, fastest TTS is unusable for you ([ElevenLabs model list](https://help.elevenlabs.io/hc/en-us/articles/17883183930129-What-models-do-you-offer-and-what-is-the-difference-between-them)) |
| ElevenLabs **Multilingual v2** ($0.10/1k) | **No** — 29 languages | Same trap |
| ElevenLabs **Eleven v3** | **Yes** — 74 languages incl. URD | Higher quality, ~250–300 ms class latency, $0.10/1k chars ([API pricing](https://elevenlabs.io/pricing/api)) |
| **Sarvam Bulbul V3** | Hinglish/code-switch at the model level, single-pass, sub-250 ms first byte, ₹30/10k chars (~$0.035) | 11 Indian languages; code-mixing is *trained in*, not glued together ([Sarvam TTS](https://www.sarvam.ai/text-to-speech)) |
| **Gemini Live** native audio | Live API docs list **97 languages including `ur`** ([Live API capabilities](https://ai.google.dev/gemini-api/docs/live-api/capabilities)) — but the Vertex native-audio voice/language table lists only ~25 locales and **Urdu is not in it** ([Vertex configure-language-voice](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api/configure-language-voice)) | Contradictory docs = unverified. Do not build your architecture on it before A/B testing with real Urdu speakers |
| **Qwen3-Omni** (Apache 2.0, self-host) | Speech **input** includes Urdu; speech **output** is 10 languages, Urdu **not** among them ([Qwen3-Omni overview](https://medium.com/data-and-beyond/qwen3-omni-alibabas-groundbreaking-multimodal-foundation-model-890a120069ed)) | Great open ASR/understanding, wrong for Urdu voice out |

The asymmetry is the point: **Urdu ASR is largely solved, Urdu TTS is not.** ElevenLabs reports Scribe at 3.1% WER on Urdu FLEURS while Deepgram Nova-2 scores **100% WER** on the same benchmark — i.e. total failure, not degradation ([ElevenLabs Urdu STT](https://elevenlabs.io/speech-to-text/urdu)). That single data point is the strongest argument in this whole report for a **modular pipeline**: vendor quality in Urdu is bimodal and unpredictable, and you must be able to swap one box without rebuilding the agent. A native S2S model welds STT, LLM, and TTS into one non-substitutable unit.

Secondary arguments for the pipeline: you get a text transcript for free (needed for tool arguments, audit, and dispute resolution); you can route the LLM per-turn (cheap model for chit-chat, stronger model when a tool call is imminent); and you avoid Gemini Live's **context re-billing**, where accumulated raw audio tokens from prior turns are re-charged at the audio input rate on *every* turn, so "a 10-second interaction at the end of a long session costs significantly more than a 10-second interaction at the start" ([Google AI dev forum](https://discuss.ai.google.dev/t/pricing-of-speech-to-speech-live-model/140340)).

**When S2S wins:** if English-only or Roman-Urdu-tolerant output is acceptable, `gemini-3.1-flash-live-preview` at $0.005/min in / $0.018/min out ([Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)) is genuinely the cost floor and has the best interruption/prosody feel. Ship the pipeline; keep an S2S branch behind a feature flag for the English-dominant segment.

### Latency budget, Pakistan-adjusted

There is **no hyperscaler region in Pakistan**. Nearest are Mumbai, Bahrain and UAE, with ~**40–70 ms** RTT to Karachi/Lahore for compute (CloudFront's Karachi edge helps static assets only, not inference) ([QloudSec](https://www.qloudsec.live/aws-cloud-pakistan)). For reference, in-country Indian metros see 3–30 ms to Mumbai and 72–92 ms to Singapore ([TechPlained](https://www.techplained.com/india-cloud-latency)) — so **never terminate your media in Singapore or the US**.

| Stage | Typical 2026 | Your realistic number |
|---|---|---|
| VAD | 20–60 ms | 40 ms |
| STT partial (Scribe v2 Realtime) | 0.13 s to first partial at 3.65% WER ([Artificial Analysis AA-WER Streaming](https://artificialanalysis.ai/articles/new-streaming-speech-to-text-benchmark-aa-wer-streaming)) | 150 ms |
| LLM first token (Flash-tier) | 150–400 ms | 250 ms |
| TTS first audio (Eleven v3) | 250–300 ms | 280 ms |
| Transport RTT (PK ↔ Mumbai, twice) | 30–80 ms | 100 ms |
| **Total** | 450–600 ms premium; 800–1200 ms common; >1500 ms "feels broken" ([AI Engineering Academy](https://ai-engineering.academy/learn/14-agent-engineering/22-voice-agents-pipecat-livekit/)) | **~820 ms** |

820 ms is acceptable, not premium. Buy it back by (a) terminating media in Mumbai/UAE, (b) using Sarvam Bulbul (sub-250 ms first byte) instead of Eleven v3 where its voice suits, and (c) **speaking a filler acknowledgement before any tool call** rather than trying to make tools fast.

---

## 3. The conversational / tool-calling model

Benchmarks are close enough that the deciding factors are latency, price, and Urdu instruction-following — not the leaderboard.

| Model | Relevant evidence | Verdict for this build |
|---|---|---|
| **Gemini 3.1 Pro / 3.5 Flash** | MCP-Atlas 69.2% (multi-server tool coordination, +9.7 pp over Opus 4.6), MMMLU multilingual 92.6%, tau2-bench retail 90.8% ([apiyi comparison](https://help.apiyi.com/en/gemini-3-1-pro-preview-vs-claude-opus-4-6-comparison-en.html)) | **Primary.** Best multilingual + tool-orchestration per dollar; Flash tier at $0.30–$1.50/M in keeps in-call cost trivial ([Google pricing](https://ai.google.dev/gemini-api/docs/pricing)) |
| **GPT-5.x** | 98.7% TAU2-Bench Telecom (multi-turn customer-support tool calling), fastest function calls ([fleeceai](https://fleeceai.app/blog/best-ai-model-for-tool-calling-2026)) | Strong alternative primary; keep as failover to avoid single-vendor risk |
| **Claude Opus 4.7/4.8-class** | Leads GDPval-AA expert-task Elo (1606 vs Gemini 1317) and long-horizon autonomy/OSWorld ([apiyi](https://help.apiyi.com/en/gemini-3-1-pro-preview-vs-claude-opus-4-6-comparison-en.html), [beri.net](https://www.beri.net/article/google-gemini-35-flash-computer-use-enterprise-ai-agents-rpa-disruption-2026)) | **Not in the voice loop** — too slow/expensive per turn. Use for the async task agent: reconciling a returned item, chasing a doctor's confirmation, resolving a messy shipment |
| **Sarvam-105B / 30B** | $0.80 per 1M blended tokens, ~5.5× cheaper than GPT-5.4-mini and ~11× cheaper than Gemini 3.5 Flash; India-hosted; tuned for code-mixed romanized Hindi/Urdu-script inputs ([India Today](https://www.indiatoday.in/amp/technology/news/story/sarvam-announces-1-trillion-parametre-ai-model-vision-and-speech-getting-new-updates-2959609-2026-07-30), [Sarvam pricing](https://www.sarvam.ai/api-pricing)) | **Budget primary.** ₹-denominated, geographically near, cheap. Weaker at complex multi-tool orchestration — pair it with strict schemas and few tools |

**Architectural rule that matters more than the model choice:** run **two agents**. A *conversation agent* (fast, cheap, ≤8 narrowly-scoped tools, one job: talk and enqueue work) and a *task agent* (strong model, minutes not milliseconds, does the actual booking/verification/shipment creation and reports back over WhatsApp). Solo builders who put 25 tools on the realtime model get both bad latency and bad reliability.

---

## 4. Vision: pull it out of the voice loop entirely

The two vision jobs are genuinely different and should not share a model or a code path.

**(a) "Does this returned item match SKU-1234?"** — This is *verification*, not retrieval. Send the photo plus the canonical catalog image and attribute text to a VLM and demand a structured verdict (`match: true|false|uncertain`, `confidence`, `discrepancies[]`, `evidence`). Gemini Flash-tier image input is ~$0.30–$0.50/M tokens ([Google pricing](https://ai.google.dev/gemini-api/docs/pricing)); Sarvam Vision is ₹0.50/page for the document/receipt side ([Sarvam pricing](https://www.sarvam.ai/api-pricing)). **Always allow `uncertain` and route it to a human** — a false "match" on a return is a direct cash loss.

**(b) "Find me this mouse"** — This is instance-level retrieval and it is the single most likely thing to under-deliver. The critical, non-obvious number: off-the-shelf CLIP matched the correct retail product **41%** of the time; the same architecture fine-tuned on domain images reached **89% top-1** on SKU matching and 92.44% top-1 against a 10M+ product database ([Width.ai](https://www.width.ai/post/image-embedding-models)). Academic work agrees that top-tuning frozen text-image embeddings is the efficient path for e-commerce retrieval ([Benchmarking Image Embeddings for E-Commerce, arXiv](https://arxiv.org/html/2504.07567v1)). **Plan for a fine-tune from day one** — a few thousand of your own product photos, top-tuning only (train a small head on frozen features), which is affordable on a single rented GPU.

Then never let the customer see a bare top-1: return top-3 candidates with images and let the VLM narrate *"I think it's one of these three — is it the black one with the side buttons?"* Voice + visual disambiguation beats a silent wrong answer.

---

## 5. Retrieval: two indexes, one reranker

**Do not force text and images into one vector space for SKU-level matching.** Cross-modal models carry a measurable "modality gap" — Qwen3-VL-2B 0.25, Voyage Multimodal 3.5 0.59, Gemini Embedding 2 0.73, Jina CLIP v2 0.87 ([Zenn benchmark, Apr 2026](https://zenn.dev/mohhh_ok/articles/image-text-embedding-models-2026?locale=en), corroborated by [Milvus](https://milvus.io/blog/choose-embedding-model-rag-2026.md)). A large gap means text queries and image queries land in different neighborhoods, so a single hybrid score is dominated by modality, not relevance. Run an image→image index and a text→text index, fuse the candidate lists, then rerank.

| Role | Default | Price | Budget / self-host |
|---|---|---|---|
| Text embeddings (catalog, policies, Urdu/Roman-Urdu queries) | **Gemini Embedding 2** — natively multimodal, 100+ languages, 8,192-token input, 128–3,072 MRL dims | $0.20/M text, $0.45/M image ($0.00012/image) ([Google pricing](https://ai.google.dev/gemini-api/docs/pricing)) | **Cohere Embed v4** $0.12/M text, $0.47/M image, 128K context, one image per call ([Puter](https://developer.puter.com/tutorials/cohere-api-pricing/)); or self-host multilingual E5/Qwen3 |
| Image embeddings (product photos) | **SigLIP-2 ViT-SO400M**, Apache 2.0, 1152-dim, 512×512, served via Infinity-Embedding — strongest open image-text model as of mid-2026 ([Spheron](https://www.spheron.network/blog/multimodal-embedding-models-gpu-cloud-siglip2-jinaclip-cohere/)) | GPU-hours only | JinaCLIP-v2 (1024-dim, Matryoshka 64–1024) if VRAM-bound |
| Lexical | BM25 in Postgres/OpenSearch | free | — |
| Reranker | **voyage-rerank-2.5-lite** $0.02/M tokens with **200M tokens/month free** ([Rabhi comparison](https://ianas.fr/en/blog/2026/06/07/reranker-comparatif-cohere-bge-jina-voyage/)) | effectively $0 at your scale | **BGE-reranker-v2-m3** (Apache/MIT, the default self-host baseline) or **jina-reranker-v3** (81.33% Hit@1 at 188 ms — the only top-tier model under 200 ms, [AIMultiple](https://aimultiple.com/rerankers)) |

Two traps. **Cohere rerank-3.5 was deprecated 1 Jul 2026 and requests now auto-serve rerank-4-fast** ([Pinecone](https://docs.pinecone.io/models/cohere-rerank-3.5)) — don't hardcode it; and at $2.00/1k searches Cohere is 40–100× the Voyage rate for you ([Rabhi](https://ianas.fr/en/blog/2026/06/07/reranker-comparatif-cohere-bge-jina-voyage/)). **jina-reranker weights are CC-BY-NC 4.0** — commercial self-hosting requires an agreement with Jina; use the hosted API or pick BGE/Qwen3/mxbai (Apache 2.0) instead ([Future AGI](https://futureagi.com/blog/best-rerankers-for-rag-2026/)).

The reranker is also the highest-ROI dollar in the retrieval stack: dense-only ≈ 0.55 nDCG@10, hybrid + rerank ≈ 0.70–0.75 ([reranking overview](https://elliot-digital.co.uk/rag/reranking)).

---

## 6. Browser/computer use: **not needed at v1**

"Browse sites to find products the customer describes" sounds like a computer-use task and almost never is. Cheaper, more reliable ordering: (1) your own catalog index, (2) supplier/merchant feeds and product APIs, (3) a grounded web-search call — Gemini gives 5,000 free grounded searches/month then $14/1k ([Google pricing](https://ai.google.dev/gemini-api/docs/pricing)) — and only then (4) a GUI agent.

If you eventually need one: **computer use is now a built-in tool inside Gemini 3.5 Flash** (announced 25 Jun 2026), scoring **78.4% OSWorld-Verified** at Flash-tier pricing, versus Claude Opus 4.8 at 83.4% and Claude Mythos/Fable 5 at 85.0% ([beri.net](https://www.beri.net/article/google-gemini-35-flash-computer-use-enterprise-ai-agents-rpa-disruption-2026)). Folding perception+reasoning+action into one Flash call roughly halves the calls per step versus the old perception+frontier chaining ([ai-cost-estimator](https://ai-cost-estimator.com/blog/gemini-3-5-flash-computer-use-builtin-agent-app-pricing-floor)). Realistic per-task cost is $0.01–$0.20 with 3–10× the token burn of a chat call ([Eden AI](https://www.edenai.co/post/ai-computer-use-apis-build-browser-agents)). The open path is **browser-use** (MIT, model-agnostic, 89.1% WebVoyager) ([kspl scorecard](https://academy.kspl.tech/blog/2026-05-14-gemini-intelligence-agent-browsing-stack)). Either way it runs in the async task agent, sandboxed, with a hard step cap — never in a live call.

---

## 7. Recommended default stack (and the budget alternative)

| Layer | **Default** | **Budget** |
|---|---|---|
| Channel | WhatsApp Business Calling (inbound free) + in-app WebRTC; PSTN via Twilio PK as fallback | Same; skip PSTN entirely at launch |
| Orchestration | **Pipecat** (BSD-2, Python, best provider swap, WhatsApp transport included) ([AI Eng. Academy](https://ai-engineering.academy/learn/14-agent-engineering/22-voice-agents-pipecat-livekit/)); LiveKit Agents if you want built-in SIP + numbers | Same — both free; managed clouds ≈$0.01/min ([Fora Soft](https://www.forasoft.com/blog/article/pipecat-vs-livekit-agents)) |
| STT | **ElevenLabs Scribe v2 Realtime** — 3.65% WER at 0.13 s first partial, best accuracy/latency frontier; batch Scribe v2 leads AA-WER at 2.2% and $6.67/1k min ([AA streaming](https://artificialanalysis.ai/articles/new-streaming-speech-to-text-benchmark-aa-wer-streaming), [AA STT](https://artificialanalysis.ai/speech-to-text/models/elevenlabs)) | **Sarvam Saaras v3** — ₹30/hr (~$0.36/hr = $0.006/min), explicitly tuned for 8 kHz telephony + code-mixed speech ([Sarvam models](https://explainx.ai/blog/sarvam-ai-capabilities-api-models-guide-2026)) |
| Conversation LLM | **Gemini 3.5 Flash** (fallback GPT-5.x) | **Sarvam-30B/105B** (~$0.80/M blended) |
| Task/async LLM | **Claude Opus-class** for messy multi-step work | Gemini 3.1 Pro |
| TTS | **ElevenLabs Eleven v3** (Urdu, $0.10/1k chars) for Urdu; Flash v2.5 ($0.05/1k, 75 ms) for English-only calls | **Sarvam Bulbul V3** — ₹30/10k chars (~$0.035), single-pass Hinglish, sub-250 ms, beat ElevenLabs and Cartesia in a 20k-vote blind study ([Sarvam TTS](https://www.sarvam.ai/text-to-speech)) |
| Text embeddings | Gemini Embedding 2 ($0.20/M) | Cohere Embed v4 ($0.12/M) or self-host |
| Image embeddings | SigLIP-2 SO400M, **top-tuned on your catalog** | JinaCLIP-v2 (Apache 2.0) |
| Reranker | voyage-rerank-2.5-lite (200M free/mo) | BGE-reranker-v2-m3 self-hosted |
| Vision verify/match | Gemini Flash-tier VLM with structured verdict + `uncertain` | Qwen3-VL (open weights) |
| Computer use | None. Add Gemini 3.5 Flash built-in computer use later | None |

### Rough cost per conversation (4-minute call, agent speaks ~90 s ≈ 1,400 chars)

| Line item | Default | Budget | Native S2S (Gemini Live) |
|---|---|---|---|
| STT | $0.027 | $0.024 | included |
| LLM | ~$0.01–0.03 | ~$0.005 | included |
| TTS | $0.14 (Eleven v3) | $0.049 (Bulbul V3) | included |
| Model subtotal | **~$0.18** (≈$0.045/min) | **~$0.08** (≈$0.02/min) | **~$0.05–0.12** ($0.005/min in + $0.018/min out, before context re-billing) |
| Retrieval + rerank | <$0.001 | <$0.001 | <$0.001 |
| Async vision (when triggered) | ~$0.002–0.01 | ~$0.002 | — |
| **Channel: WhatsApp inbound** | **$0** | **$0** | $0 |
| **Channel: Twilio PSTN instead** | **+$0.62** | +$0.62 | +$0.62 |

At 1,000 calls/month the default stack is roughly **$180 of model spend** — and **$800 if you route those same calls over Pakistani PSTN**. Cross-check on the S2S side: OpenAI's `gpt-realtime-2.1-mini` at $10/$20 per M audio tokens works out to ~$0.016–0.05/min ([layer3labs](https://www.layer3labs.io/guides/openai-realtime-api-pricing), [Fora Soft](https://www.forasoft.com/blog/article/openai-realtime-api-pricing)); the flagship at $32/$64 lands at $0.06–0.10/min with prompt caching and can hit $0.18–0.46/min uncached ([callsphere](https://callsphere.ai/blog/vw2c-openai-realtime-cost-per-minute-math-2026)). Note also that a 1,000-word system prompt roughly doubled measured per-minute cost on a mini realtime model ([eesel](https://www.eesel.ai/blog/gpt-realtime-mini-pricing)) — **prompt length is a latency and cost decision, not just a quality one.**

### On self-hosting and vendor lock-in
Self-hosting is the right *insurance policy*, wrong *v1 plan* — especially in Pakistan, where you'd rent GPUs in Mumbai/UAE anyway and grid reliability makes on-prem inference a liability. Break-even for a self-hosted reranker sits around ~200k rerank calls/month ([omeronal](https://omeronal.com/reranking-cohere-jina-bge-modeller-2026/)); you will be nowhere near that. Buy the insurance cheaply instead: keep the pipeline modular, keep Qwen3-Omni (Apache 2.0, 119 text / 19 speech-input languages incl. Urdu, ~211–234 ms first audio, function calling) as the documented escape hatch for ASR and understanding, and accept that Urdu **TTS** has no good open substitute today.

---

## 8. Top 3 architectural risks

**1. Urdu code-switched output degradation — and provider quality that is bimodal, not gradual.**
Every accuracy number you can find is English-centric. The published Urdu figures come from **FLEURS, which is clean read speech**, not 8 kHz code-mixed telephony; and the spread on that benchmark runs from Scribe at 3.1% to **Deepgram Nova-2 at 100% WER** ([ElevenLabs](https://elevenlabs.io/speech-to-text/urdu)) — a provider that is excellent in English failing completely. Meanwhile Sierra's multilingual μ-bench shows even the leader mangling **14% of utterances** with at least one meaning-changing error ([μ-bench](https://research.sierra.ai/mubench/)). *Mitigation:* build a 200-utterance Urdu/Roman-Urdu/Hinglish eval set from real calls before you choose a vendor; keep STT and TTS behind interfaces; A/B Eleven v3 against Bulbul V3 with actual customers; log every turn's transcript and confidence.

**2. Irreversible tool side effects executed on a misheard word.**
A voice agent that can book a doctor's appointment, dispatch a driver and create a shipment has three ways to cause real-world loss, and it acts on a transcript that is wrong a few percent of the time. Voice interfaces also lack the visual confirm/undo affordances that make text agents forgiving. *Mitigation:* split tools into read (free to call) and write (gated); require spoken read-back confirmation of every write with all extracted parameters; idempotency keys on every write so a retry can't double-dispatch; **the "confirm with a doctor" step must be human-in-the-loop by design**, not a model capability — the agent proposes a slot, a human or the clinic's own system confirms. Cap actions per call and hard-fail closed.

**3. Latency/cost blowup from the two things that compound silently: session context and geography.**
Gemini Live re-bills accumulated audio tokens **every turn**, so long conversations get superlinearly expensive ([Google AI dev forum](https://discuss.ai.google.dev/t/pricing-of-speech-to-speech-live-model/140340)), audio-only Live sessions are capped at 15 minutes ([laozhang](https://blog.laozhang.ai/en/posts/gemini-3-1-flash-live-api)), and there is **no cloud region in Pakistan** — 40–70 ms each way to Mumbai/Bahrain/UAE, doubled per turn ([QloudSec](https://www.qloudsec.live/aws-cloud-pakistan)). A single sloppy choice (media terminated in us-east-1, a 2,000-word prompt, uncached context) turns an 820 ms agent into a 2 s agent that costs 5× more. *Mitigation:* pin all inference and media to Mumbai/UAE; enforce prompt caching (cached audio input is $0.40 vs $32/M on OpenAI — an ~80× lever, [Fora Soft](https://www.forasoft.com/blog/article/openai-realtime-api-voice-agent-production-guide-2026)); summarize-and-truncate context every ~6 turns; alert on p95 turn latency and per-call cost, not monthly totals.

**Honourable-mention risk (legal, and it is coming):** Pakistan's draft Personal Data Protection Bill requires **critical personal data to be processed only on servers inside Pakistan**, with sensitive-data localisation left to a future commission and fines up to **USD 2 million** ([Chambers 2026](https://practiceguides.chambers.com/practice-guides/data-protection-privacy-2026/pakistan), [ITIF](https://itif.org/publications/2025/05/16/pakistan-cross-border-data-transfer-regulation/)), and the **National Data Governance Policy 2026** already requires sensitive government and personal data to be hosted and processed domestically with prior approval for offshore processing ([Connected Pakistan](https://blog.connectedpakistan.pk/pakistan-national-data-governance-policy-2026-localization)). Health-adjacent data (doctor appointments) is exactly the category most likely to be swept in. Practical hedge now: store PII and call recordings on infrastructure you can relocate, send only minimized/pseudonymized payloads to foreign model APIs, and keep the transcript store separate from the model vendor.

---

## 9. Two things I'd tell this builder that aren't in the question

- **Your differentiator is the code-switching voice, not the LLM.** Every competitor can call Gemini. Almost none will have collected 500 hours of Karachi/Lahore telephony audio with Roman-Urdu transcripts. That dataset is the moat, and the modular pipeline is what lets you exploit it later (fine-tuned ASR, fine-tuned TTS voice, fine-tuned CLIP head). A native S2S model gives you nowhere to put it.
- **Ship the *text* WhatsApp agent first, with the same tools.** Same brain, same RAG, same tool schemas, ~1/20th the cost, no latency budget, and it lets you debug tool reliability and Urdu handling in a medium where errors are visible and recoverable. Turn on voice once the write-path is boring.

---

*Prepared 8 Aug 2026. All prices are vendor list prices as published on the cited dates and change frequently — re-verify before committing budget.*
