# Model council report: LLM stack for a Pakistan-based voice support agent

**As of 8 August 2026**

## Recommendation in one line

Use **GPT-Realtime-2.1 for the spoken conversation**, but put consequential actions behind a separate **GPT-5.6 Terra “action governor” using strict tool schemas**; use **GPT-5.6 Sol only as an escalation model**. For product search, use **Voyage Multimodal 3.5 embeddings → metadata/BM25 fusion → a vision-model verification pass**, not a VLM searching the whole catalog.

This two-plane design is the important choice. GPT-Realtime-2.1 has native speech-to-speech, image input, function calling, interruption handling and a 128K context, but it does **not** support Structured Outputs; GPT-5.6 models support image input, function calling and schema-constrained output ([GPT-Realtime-2.1 model card](https://developers.openai.com/api/docs/models/gpt-realtime-2.1), [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)). That makes Realtime the natural, low-latency “mouth and ears,” while Terra validates a booking/shipment payload before application code commits it.

## Default stack

| Layer | Default | Why / implementation note |
|---|---|---|
| Voice transport | WebRTC in app; SIP/telephony adapter for phone calls | Keep media streaming and barge-in handling outside the business-logic agent. |
| Spoken conversation | **`gpt-realtime-2.1`**, low reasoning | OpenAI positions it for low-latency voice agents that converse, call tools and manage state; it accepts text/audio/image and returns text/audio ([Realtime guide](https://developers.openai.com/api/docs/guides/realtime), [model card](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)). |
| Reliable action/tool layer | **`gpt-5.6-terra` Responses API**, `strict:true`, low/medium reasoning | Terra is the cost-balanced GPT-5.6 tier at **$2/M input, $12/M output**, versus Sol at **$5/$30**; GPT-5.6 supports functions, web search, file search and computer use ([OpenAI model list](https://developers.openai.com/api/docs/models), [pricing](https://developers.openai.com/api/docs/pricing)). |
| Escalation | **`gpt-5.6-sol`** | Invoke only for ambiguous multi-step planning, difficult photo adjudication, or failed browser recovery—not every voice turn. |
| Product image retrieval | **Voyage `voyage-multimodal-3.5`**, 1024-d vectors | One aligned space for catalog title/description/images and customer photos; it supports interleaved text and visuals with 32K context ([Voyage docs](https://docs.voyageai.com/docs/multimodal-embeddings)). |
| Text RAG | Same multimodal model for product records; optionally `voyage-3.5` for long support documents; PostgreSQL FTS + pgvector | Keep lexical SKU/model-number recall alongside semantics. Voyage charges $0.12/M text tokens and $0.60/B pixels for Multimodal 3.5, with 200M text tokens and 150B pixels free; a 1 MP image is about $0.0006 after the allowance ([Voyage pricing](https://docs.voyageai.com/docs/pricing)). |
| Text reranker | **`rerank-2.5-lite`** | Multilingual, instruction-following, 32K context and tuned for latency; list price is $0.02/M processed tokens, with an estimated $0.001 for a 100-document request and 200M free tokens ([Voyage reranker docs](https://docs.voyageai.com/docs/reranker), [pricing](https://docs.voyageai.com/docs/pricing)). |
| Final photo/SKU adjudication | **GPT-5.6 Terra vision**, Sol on low confidence | Give it the query photo plus only the top 3–8 catalog candidates and demand `{sku, match|no_match, attributes_seen, conflicts, confidence}`. |
| Browser | **Playwright/API-first; no dedicated computer-use model by default** | Playwright MCP exposes structured accessibility snapshots of roughly 200–400 tokens and does not require vision ([Playwright MCP](https://playwright.dev/mcp/introduction)). Use GPT-5.6 Sol computer use only when a permitted site has no API/feed and ordinary selectors fail. |

### Voice architecture

Start with native speech-to-speech because it removes two network/model boundaries and preserves timing, emotion, interruption and code-switch context. Realtime 2.1 explicitly improves silence/noise handling, alphanumeric recognition and interruption behavior, all unusually important for phone support ([OpenAI model card](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)). It also supports live function calls, but use those directly only for **read-only** operations such as `check_stock`; send writes such as `create_booking`, `dispatch_driver` and `create_shipment` through Terra and deterministic validation.

Do not assume “multilingual” means Pakistani Urdu/Hinglish is solved. Deepgram added production Urdu (`ur`) to Nova-3 in 2026, but its published multilingual code-switch model lists English/Hindi and eight other languages—not Urdu—so a monolingual Urdu model may still lose embedded English SKU names ([Deepgram Urdu release](https://developers.deepgram.com/changelog/2026/2/3), [language matrix](https://developers.deepgram.com/docs/models-languages-overview)). Google Chirp 3 explicitly supports streaming `ur-PK`, and Google has Urdu voices under `ur-IN` ([Google STT language table](https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages), [Google TTS voices](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types)). Before launch, run a 300–500-utterance local bake-off containing Pakistani accents, Roman Urdu, English nouns, addresses, phone numbers, drug names and SKUs; optimize **slot error rate**, not generic WER.

Target about **300–600 ms first audible response** for native Realtime and **500–900 ms** for a cascade. Keep retrieval/tool work off the audio loop: acknowledge immediately (“Let me check that”), run the operation asynchronously, then speak the result.

### Tool execution pattern

Expose narrow business verbs, not a generic database or shell: `search_inventory`, `hold_stock`, `get_slots`, `propose_booking`, `confirm_booking`, `request_doctor_confirmation`, `get_shipment_quote`, `create_shipment`. OpenAI recommends strict function mode; strict schemas require all properties to be required and `additionalProperties:false` ([function-calling guide](https://developers.openai.com/api/docs/guides/function-calling)).

Every write should be a two-phase state machine:

1. Resolve and read back canonical entities (customer, date/time/time zone, SKU, quantity, address).
2. Produce a proposal with a server-generated idempotency key.
3. Obtain explicit user confirmation for price/date/address-sensitive actions.
4. Commit in application code; never let the model claim success until the external API returns success.
5. Persist the tool request/result and announce a reference number.

“Confirm with a doctor” is asynchronous workflow state, not conversational memory: `pending_doctor → accepted/rejected/expired`, with a later callback/message to the customer.

## Vision and retrieval design

“Find me this mouse” and “is this return the same item?” are different tasks. For discovery, normalize catalog images, titles, brand, model, color and key attributes; embed 2–4 views per SKU; retrieve top 30–50 with multimodal vectors; fuse with BM25/exact SKU and stock/location filters; then let Terra compare the customer image with the top few candidates. For return verification, require barcode/OCR/serial when available and compare multiple views—semantic image similarity alone cannot reliably distinguish visually identical variants.

Do not use the text reranker directly on raw photos. Use `rerank-2.5-lite` for textual support/catalog passages; use the VLM adjudication pass for visual candidates. Calibrate separate thresholds for **exact match**, **similar product**, and **no match**, and always permit abstention.

For lower lock-in, the open-weight **Jina CLIP v2** is a credible replacement candidate: it is a 0.9B model supporting 89 languages, 512×512 images and truncatable 64–1024-dimensional vectors ([Jina CLIP v2](https://jina.ai/news/jina-clip-v2-multilingual-multimodal-embeddings-for-text-and-images/)). Retain raw text/images and version every embedding index so a provider/model swap is a rebuild, not a data migration.

## Is browser/computer use needed?

Not for inventory, appointments, shipping or ordinary product search: use first-party APIs, merchant feeds, search APIs and deterministic Playwright flows. A visual computer-use loop is slower, costlier and less auditable than selectors/accessibility snapshots. GPT-5.6 Sol does expose computer use and scored strongly on BrowseComp/OSWorld in OpenAI’s own evaluations, but that is a fallback capability, not a reason to place GUI automation in the critical transaction path ([OpenAI GPT-5.6 announcement](https://openai.com/index/gpt-5-6/)).

Restrict browser automation to allow-listed domains, a sandboxed browser and read-only exploration by default. Require human/user confirmation before login, purchase, message sending or irreversible submission; retain screenshots and network/tool logs. Expect CAPTCHAs, UI changes and site terms to force handoff.

## Budget alternative

**Cascade:** Deepgram Nova-3 streaming STT → **GPT-5.6 Luna** (or hosted **Mistral Small 4**) → Google Chirp 3 HD TTS; use `gpt-realtime-2.1-mini` if natural barge-in is more important than maximum savings.

* Deepgram Nova-3 multilingual is **$0.0058/min PAYG** and its Urdu monolingual model is available for streaming ([Deepgram pricing](https://deepgram.com/pricing), [Urdu announcement](https://deepgram.com/learn/speech-to-text-for-hebrew-persian-urdu-on-nova-3)).
* GPT-5.6 Luna is **$0.20/M input, $1.20/M output**; Realtime 2.1 mini audio is **$10/M input and $20/M output** ([OpenAI pricing](https://developers.openai.com/api/docs/pricing)).
* Google Chirp 3 HD includes 1M characters/month, then costs **$30/M characters**, and offers Urdu voices ([Google TTS pricing](https://cloud.google.com/text-to-speech/pricing), [voice list](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types)).
* Mistral Small 4 is Apache-2.0, multilingual and multimodal; Mistral’s hosted rate is **$0.15/M input, $0.60/M output**, making it a useful vendor-neutral text/tool fallback ([Mistral Small 4](https://mistral.ai/news/mistral-small-4/)).

For full self-hosting, combine Mistral Small 4, Jina CLIP v2, `bge-reranker-v2-m3`, Whisper Large v3 and Indic Parler-TTS. Whisper Large v3 is multilingual and trained on 5M hours, while Indic Parler-TTS explicitly includes Urdu and is Apache-2.0 ([Whisper model card](https://huggingface.co/openai/whisper-large-v3), [Indic Parler-TTS](https://huggingface.co/ai4bharat/indic-parler-tts)). This reduces vendor dependence but is **not** the economic default for a solo builder: idle GPU capacity, streaming/VAD engineering, observability and voice-quality tuning usually cost more than API usage at small scale.

## Rough five-minute conversation cost

Assumption: 2.25 minutes of customer speech, 1.75 minutes of agent speech, 1 minute silence; about 10K cumulative LLM input tokens and 1K output tokens; excludes taxes and application hosting.

| Option | Approx. AI cost / 5-min call | Notes |
|---|---:|---|
| Realtime 2.1 + Terra action check | **$0.21–0.30** | OpenAI bills user audio at 1 token/100 ms and assistant audio at 1 token/50 ms; at $32/$64 per M audio tokens, the speech portion is about **$0.18** under this talk-time mix, before text/tool calls ([Realtime cost guide](https://developers.openai.com/api/docs/guides/realtime-costs), [pricing](https://developers.openai.com/api/docs/pricing)). |
| Realtime 2.1 mini + Terra/Luna governor | **$0.06–0.12** | Same talk-time calculation at mini’s $10/$20 audio rates. |
| Deepgram → Terra/Luna → Google TTS | **$0.08–0.15** after free TTS allowance | Approximately $0.029 STT for five streamed minutes, roughly $0.003–0.032 LLM, plus synthesized characters. |

Telephony can dominate the AI bill in Pakistan. Twilio lists **$0.155/min to Pakistan landlines and $0.18/min to mobile**, adding about **$0.78–0.90** to a five-minute outbound call; browser/app VoIP is listed at $0.004/min ([Twilio Pakistan pricing](https://www.twilio.com/en-us/voice/pricing/pk)). Prefer in-app WebRTC or negotiate a local SIP carrier/BYOC before optimizing a few cents of model usage.

## Top three architectural risks

1. **Silent speech corruption in code-switching.** Names, dates, medicine names, addresses and SKU digits can be wrong while the transcript sounds plausible. Maintain a transcript mirror, inject catalog keywords, repeat critical slots, offer keypad/text fallback and route low-confidence turns to a human.
2. **Duplicate or unauthorized side effects.** Retries, barge-ins and model loops can create two bookings or shipments. Enforce idempotency keys, two-phase confirmation, least-privilege tools, server-side invariants and immutable audit logs.
3. **Open-set visual false matches.** Embeddings nearly always return a “nearest” SKU even when the correct answer is absent. Use an explicit no-match class, calibrated thresholds, barcode/OCR and multi-view checks; require human review for refunds/high-value returns.

Finally, keep provider adapters at every boundary (`SpeechIn`, `ConversationModel`, `ActionPlanner`, `Embedder`, `Reranker`, `SpeechOut`), canonical JSON tool contracts, and raw source assets. This preserves the ability to swap speech, LLM or embedding vendors without rewriting business workflows.
