import json
import logging
import os
import time
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import numpy as np
from groq import APIStatusError as GroqAPIStatusError, Groq, GroqError
from openai import APIStatusError as OpenAIAPIStatusError, OpenAI, OpenAIError

from . import persona
from .livekit_inference_client import LiveKitInferenceClient
from .tools import TOOLS_BY_NAME, tool_schemas_for
from ..data import session_log, settings as app_settings

TOP_K_EXAMPLES = 2

# The one place customer-facing text has to stay per-language rather than English-authored:
# this is returned directly to the customer when the LLM call itself fails, so there's no
# model generation step left to render it in the right language - unlike everything else in
# this file, there's nothing here for the model to "just translate." Keyed by the same
# AppSettings.reply_language values as LANGUAGE_MODE_INSTRUCTIONS below. "auto" defaults to
# Urdu since we don't know the customer's language on this failure path and Urdu is this
# project's primary language.
FALLBACK_REPLIES = {
    "english": "Sorry, I'm having a little trouble right now. Please try again in a moment.",
    "urdu": "معذرت، ابھی مجھے تھوڑی دقت ہو رہی ہے۔ براہ کرم ایک لمحے بعد دوبارہ کوشش کریں۔",
    "roman_urdu": "Maazrat, abhi mujhe thori diqqat ho rahi hai. Baraah-e-karam aik lamhe baad dobara koshish karein.",
    "auto": "معذرت، ابھی مجھے تھوڑی دقت ہو رہی ہے۔ براہ کرم ایک لمحے بعد دوبارہ کوشش کریں۔",
}

_WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]  # date.weekday(): 0=Mon..6=Sun


def _current_date_statement(timezone: str) -> str:
    """Grounds the model on today's real date/day-of-week, in the business's own timezone -
    with no such statement anywhere in the prompt, "book me an appointment tomorrow" was
    being resolved with zero grounding (root cause of a live bug: agreeing to book on a day
    the clinic is actually closed). Must go through this, never a bare datetime.now() -
    a server running in UTC (Render, per plan.md) would silently reintroduce the same bug
    near midnight PKT. English text, like every other system message here - it's context for
    the model to reason over, not shown to the customer, so it doesn't need to be per-language."""
    now = datetime.now(ZoneInfo(timezone))
    return f"Today's date: {_WEEKDAY_EN[now.weekday()]}, {now.strftime('%Y-%m-%d')}, time {now.strftime('%H:%M')}."

# Every entry keyed by the exact string stored in AppSettings.llm_model (see src/models.py).
# Ordering and notes are from our OWN eval (scripts/eval_llm_models.py, 2026-08-08, re-run
# 2026-08-10 after the max_tokens fix below) against this project's real dental-clinic
# persona/guardrails/tools/FAQ - not just the UrduMMLU benchmark accuracy numbers
# (arXiv:2606.07167) that motivated trying these models in the first place, though those
# numbers are worth recording here since they're the best available signal for a model this
# project hasn't been able to eval as thoroughly yet: Gemini 3.5 Flash 91.72%, Gemma 4 31B
# 80.95%, Llama 3.1 8B 45.7% (ruled out for the live-call speed experiment for exactly this
# reason - see plan.md's pipeline-overhaul section, 2026-08-10).
#
# max_tokens is per-model, not a single global 300 - Gemini 3.5 Flash was previously marked
# "not recommended" for getting cut off mid-reply on 2 of 4 real test cases, but that was a
# config bug (budget too tight for a more verbose model), not a quality problem - fixed by
# giving it more headroom instead of discarding the model with the best measured Urdu accuracy.
LLM_CATALOG = {
    "openrouter:google/gemma-4-31b-it": {
        "provider": "openrouter", "model": "google/gemma-4-31b-it", "max_tokens": 300,
        "label": "Gemma 4 31B", "note": "correct + empathetic in our own tests, cheapest, fast; 80.95% UrduMMLU",
    },
    "openrouter:google/gemini-3.5-flash-lite": {
        "provider": "openrouter", "model": "google/gemini-3.5-flash-lite", "max_tokens": 300,
        "label": "Gemini 3.5 Flash Lite", "note": "Correct in our tests, fastest, slightly pricier than Gemma",
    },
    "openrouter:anthropic/claude-haiku-4.5": {
        "provider": "openrouter", "model": "anthropic/claude-haiku-4.5", "max_tokens": 300,
        "label": "Claude Haiku 4.5", "note": "Correct in our tests; once added unprompted medical advice against a guardrail",
    },
    "openrouter:deepseek/deepseek-v4-flash": {
        "provider": "openrouter", "model": "deepseek/deepseek-v4-flash", "max_tokens": 300,
        "label": "DeepSeek V4 Flash", "note": "Correct in our tests but noticeably slower (3-15s) on tool calls",
    },
    "groq:llama-3.3-70b-versatile": {
        "provider": "groq", "model": "llama-3.3-70b-versatile", "max_tokens": 300,
        "label": "Groq Llama 3.3 70B (original default)", "note": "Fastest inference, known Urdu script-corruption defect",
    },
    "openrouter:google/gemini-3.5-flash": {
        "provider": "openrouter", "model": "google/gemini-3.5-flash", "max_tokens": 600,
        "label": "Gemini 3.5 Flash", "note": "Recommended: best measured Urdu accuracy (91.72% UrduMMLU) - previously marked not-recommended for truncating under max_tokens=300, fixed by raising this model's budget to 600",
    },
    "livekit:google/gemma-4-31b-it": {
        "provider": "livekit", "model": "google/gemma-4-31b-it", "max_tokens": 300,
        "label": "Gemma 4 31B (LiveKit Inference)", "note": (
            "English-path recommended: same model as the OpenRouter Gemma 4 entry above, but "
            "served with speculative decoding + reserved GPU capacity - 192ms TTFT, 354ms "
            "time-to-first-sentence at production-scale prompt sizes per LiveKit's own "
            "published benchmarks (2026-08-10). Schema validation at the serving layer catches "
            "malformed tool calls before they reach us - directly relevant after the compulsive/"
            "malformed tool-calling found with Llama 3.3 70B this session. Bills against "
            "LiveKit Cloud's own inference credits, not Groq/OpenRouter - sidesteps both "
            "quota blocks hit this session. Not proven for Urdu conversations - English path "
            "only until that's separately verified."
        ),
    },
}
DEFAULT_LLM_MODEL = "openrouter:google/gemini-3.5-flash"

_provider_clients: dict[str, object] = {}

# business_id -> (example_bank list persona.py returned, its embeddings) - shared across every
# ChatEngine instance in the process, not just within one conversation, since the example bank
# is the same for every call/conversation a given business has. See _pick_examples.
_example_embeddings_cache: dict[UUID, tuple] = {}


# Both SDKs default to a much more patient timeout than a live voice call can tolerate
# (openai-python: 600s, groq: 60s) - and both already retry automatically on timeout up to
# max_retries before raising (confirmed by reading openai._base_client.SyncAPIClient.request -
# `except timeout_exceptions(): ... self._sleep_for_retry(...)` runs before the final
# APITimeoutError, which reply()'s existing except (GroqError, OpenAIError) already catches).
# So the fix here is just a sane per-attempt ceiling, not new retry logic - a single call
# hanging past this retries automatically, then falls back gracefully instead of the caller
# (a live call, mid-conversation) waiting an unbounded amount of time. 10s is generous enough
# to not break DeepSeek V4 Flash's documented legitimate 3-15s tool-call latency (LLM_CATALOG
# note above), tight enough to catch the kind of 11.6s single-call anomaly found 2026-08-10
# (six identical calls at 1.5-2.5s, one outlier at 11.6s) well before it compounds into a
# multi-second wait across retries.
_LLM_REQUEST_TIMEOUT_SECONDS = 10.0


def _get_client(provider: str, model: str | None = None):
    """Provider HTTP clients are cheap to share across businesses/requests - cached at
    module level rather than one per ChatEngine, since only the API key differs. "livekit" is
    keyed by provider+model (unlike groq/openrouter, whose clients are model-agnostic and take
    model= per-call) because LiveKitInferenceClient fixes its model at construction time - see
    livekit_inference_client.py."""
    cache_key = f"{provider}:{model}" if provider == "livekit" else provider
    if cache_key not in _provider_clients:
        if provider == "groq":
            _provider_clients[cache_key] = Groq(
                api_key=os.environ["GROQ_API_KEY"], timeout=_LLM_REQUEST_TIMEOUT_SECONDS, max_retries=2,
            )
        elif provider == "openrouter":
            _provider_clients[cache_key] = OpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1",
                timeout=_LLM_REQUEST_TIMEOUT_SECONDS, max_retries=2,
            )
        elif provider == "livekit":
            _provider_clients[cache_key] = LiveKitInferenceClient(
                model=model, api_key=os.environ["LIVEKIT_API_KEY"], api_secret=os.environ["LIVEKIT_API_SECRET"],
            )
        else:
            raise ValueError(f"unknown LLM provider: {provider}")
    return _provider_clients[cache_key]

# Overrides the persona's default "Urdu script only" guardrail when the business configures
# a different reply-language mode. Placed as the last system message (closest to the user's
# message) so it takes priority over the earlier, more general persona guardrails.
LANGUAGE_MODE_INSTRUCTIONS = {
    "auto": (
        "Language rule: there are three possible cases for the language of the customer's message - "
        "recognize them separately, don't conflate them: "
        "(1) If the customer writes in Urdu script (e.g. 'کیا حال ہے'), reply in Urdu script. "
        "(2) If the customer writes in Roman Urdu - meaning the Urdu language, but spelled in English "
        "letters (e.g. 'kya hal hai', 'mujha kapre kharedna hn') - reply in Roman Urdu too. Do not treat "
        "this as English and reply in English, and do not convert it into Urdu script either. "
        "(3) If the customer genuinely writes in English (e.g. 'do you have earbuds?'), reply fully in "
        "fluent English. "
        "This instruction overrides the 'always write only in Urdu' restriction given above."
    ),
    "english": (
        "Language rule: no matter what language the customer writes in, you must always reply only in "
        "fluent English. This instruction overrides the 'always write only in Urdu' restriction given above."
    ),
    "roman_urdu": (
        "Language rule: whether the customer writes in Urdu script, Roman Urdu, or English, you must "
        "always reply in Roman Urdu - meaning the Urdu language, spelled in English letters (e.g. 'ji "
        "bilkul, kya madad kar sakti hun'). Never use Urdu script, and never reply fully in English either. "
        "This instruction overrides the 'always write only in Urdu' restriction given above."
    ),
    "urdu": None,  # matches the persona's existing default guardrail — no override needed
}


def _is_usable_reply(content: str | None) -> bool:
    """False for None/empty content (a provider can return finish_reason="stop" with zero
    usable text - observed live: the model wanted to make a second tool call after an
    ambiguous first tool result, wasn't offered one, and produced only an internal "thought"
    fragment that consumed the whole token budget with nothing left to surface) or leaked
    tool-call syntax. Never treat either as a valid final reply - both must escalate instead
    of being logged/spoken as the customer's answer."""
    return bool(content) and not _looks_like_leaked_tool_call(content)


def _looks_like_leaked_tool_call(content: str | None) -> bool:
    """Occasionally the model tries to call a tool but emits it as plain text (XML-ish
    <function> tags, or raw JSON) instead of populating the structured tool_calls field -
    catch that so the customer never sees broken function-call syntax as a reply.

    Checks anywhere in the message, not just a prefix: live testing (2026-08-08) caught a
    real case where the model wrote a normal Urdu greeting/prose reply and *then* appended
    a leaked `<function=...>` tag - a startswith-only check missed it entirely since the
    message didn't begin with the tag."""
    if not content:
        return False
    stripped = content.strip()
    if not ("<function" in content or stripped.startswith("{")):
        return False
    return any(name in content for name in TOOLS_BY_NAME)


class ChatEngine:
    """One instance per conversation. business_id scopes every persona/settings/FAQ/tool/
    log lookup to the right business's data; session_id (a fresh row in the `sessions`
    table, created here) scopes conversation history the same way session_log.py's old
    module-level "current session" pointer never could for more than one caller at a time."""

    def __init__(
        self, faq_store, business_id: UUID, business_type: str = "demo",
        history_turns: int = 6, on_tool_call=None,
    ):
        self.faq_store = faq_store
        self.business_id = business_id
        self.tool_schemas = tool_schemas_for(business_type)
        self.history: list[dict] = []
        self.history_turns = history_turns
        # reply() overwrites this per-turn from LLM_CATALOG once it resolves which model the
        # business is using - this default only matters for a caller that invokes _complete()
        # directly without going through reply() first (scripts/eval_llm_models.py does
        # exactly that, to isolate LLM behavior from the rest of reply()'s turn bookkeeping).
        self.max_tokens = 300
        # Called as on_tool_call(user_text) -> str | None, returning the filler phrase to say
        # while a slow tool (e.g. check_appointment_slots hitting Postgres) runs - live calls
        # use this so a tool-calling turn isn't dead air. user_text (not tool names) is all the
        # caller needs since phrase selection only depends on matching the customer's language.
        #
        # Deliberately just returns text rather than speaking it itself (an earlier version
        # called session.say() directly from here as a side effect) - confirmed live
        # (2026-08-10) that a session.say() call made while an llm_node stream is already in
        # flight gets queued BEHIND that stream's eventual output instead of interrupting it:
        # the real reply would arrive, THEN the filler, backwards from "filler while the tool
        # runs." reply_stream() below calls this directly and yields the result as part of its
        # own stream instead, so there's no separate scheduling path left to lose that race.
        # None for every other caller (text chat, hold-to-talk, CLI) - they have no such gap.
        self._on_tool_call = on_tool_call

        # reuse the FAQ store's embedder instead of loading a second model onto the GPU
        self.embedder = faq_store.embedder
        self.session_id = session_log.start_session(business_id)

    def _pick_examples(self, user_text: str, k: int = TOP_K_EXAMPLES) -> list[dict]:
        """Return the k example exchanges whose user-side is most similar to what was just said,
        so the LLM sees tone-matched few-shot context (small talk vs. complaint vs. thanks, etc.)
        instead of always the same fixed pair. Reads the bank fresh each call since the
        Continuous Learning UI can append new examples to it while the app is running - but
        only re-embeds it when the bank actually changed (persona.load_example_bank returns
        the exact same list object on a cache hit, invalidated only on a write - see its
        docstring), instead of re-running the embedder over the whole bank on every single
        turn regardless of whether anything changed."""
        example_bank = persona.load_example_bank(self.business_id)
        cached = _example_embeddings_cache.get(self.business_id)
        if cached is not None and cached[0] is example_bank:
            example_embeddings = cached[1]
        else:
            example_texts = ["query: " + ex["user"] for ex in example_bank]
            example_embeddings = self.embedder.encode(example_texts, normalize_embeddings=True)
            _example_embeddings_cache[self.business_id] = (example_bank, example_embeddings)

        query_emb = self.embedder.encode(["query: " + user_text], normalize_embeddings=True)[0]
        scores = example_embeddings @ query_emb
        top_indices = np.argsort(scores)[::-1][:k]

        messages = []
        for i in top_indices:
            example = example_bank[i]
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})
        return messages

    def _prepare_turn(self, user_text: str):
        """Shared setup between reply() and reply_stream() - builds the same messages/
        settings/client/model every turn needs, so the two entry points can't silently drift
        apart on anything except how they get the final text out of the LLM."""
        settings = app_settings.load_settings(self.business_id)

        faq_context = self.faq_store.get_context(self.business_id, user_text)

        system_prompt = persona.build_system_prompt(self.business_id)
        messages = [{"role": "system", "content": system_prompt}] + self._pick_examples(user_text)
        messages.append({"role": "system", "content": _current_date_statement(settings["timezone"])})

        if faq_context:
            messages.append({
                "role": "system",
                "content": f"Relevant information: {faq_context}",
            })

        language_instruction = LANGUAGE_MODE_INSTRUCTIONS.get(settings["reply_language"])
        if language_instruction:
            messages.append({"role": "system", "content": language_instruction})

        messages += self.history[-self.history_turns * 2:]
        messages.append({"role": "user", "content": user_text})

        catalog_entry = LLM_CATALOG.get(settings["llm_model"], LLM_CATALOG[DEFAULT_LLM_MODEL])
        model = catalog_entry["model"]
        client = _get_client(catalog_entry["provider"], model)
        return messages, language_instruction, settings, client, model

    def _finish_turn(self, user_text: str, reply_text: str, reply_start: float) -> None:
        """Shared bookkeeping both reply() and reply_stream() do once a final answer exists -
        history, session logging, and the same total-turn timing log used to find which stage
        dominates a slow turn (see _timed_completion)."""
        logging.info(
            "ChatEngine.reply() finished",
            extra={"business_id": str(self.business_id), "total_ms": round((time.perf_counter() - reply_start) * 1000)},
        )
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply_text})
        session_log.log_exchange(self.session_id, user_text, reply_text)

    def reply(self, user_text: str) -> str:
        messages, language_instruction, settings, client, model = self._prepare_turn(user_text)
        # Per-model, not a single global budget - see LLM_CATALOG's docstring for why
        # (Gemini 3.5 Flash needs more headroom than the others to stop truncating).
        self.max_tokens = LLM_CATALOG.get(settings["llm_model"], LLM_CATALOG[DEFAULT_LLM_MODEL])["max_tokens"]

        reply_start = time.perf_counter()
        try:
            reply_text = self._complete(client, model, messages, settings["llm_temperature"], language_instruction)
        except (GroqError, OpenAIError):
            # rate limits, malformed tool-call generations, network hiccups, etc. -
            # degrade gracefully instead of crashing the whole conversation loop, but log
            # it: silently swallowing every failure mode here means a real production
            # failure rate would otherwise be invisible.
            logging.exception("ChatEngine.reply() failed, returning fallback")
            return FALLBACK_REPLIES.get(settings["reply_language"], FALLBACK_REPLIES["auto"])

        self._finish_turn(user_text, reply_text, reply_start)
        return reply_text

    def reply_stream(self, user_text: str):
        """Live-call-only entry point (src/realtime/worker.py's llm_node) - yields the reply
        text in chunks as they're generated instead of returning one final string, so TTS can
        start speaking the first words while the rest is still being generated.

        Deliberately narrow in scope: only the "no tool call needed" case actually streams.
        The moment the model starts producing a tool call instead of content, this abandons
        the stream and falls back to reply()'s exact existing _complete()/_run_tool_calls()
        path (multi-round tool-calling, retries, leaked-call detection, all untouched), yielding
        its result as a single final chunk. That logic earned real correctness fixes this
        project depends on - reimplementing it a second time in a streaming shape would double
        the surface area for the same bugs to reappear. Plain conversational replies - the
        common case, and previously the single biggest per-turn cost after STT/turn-detection -
        are exactly where streaming actually pays off; a tool-calling turn instead gets a filler
        phrase yielded as the first chunk (see on_tool_call, ChatEngine.__init__) so it isn't
        dead air either, just not token-streamed.
        """
        messages, language_instruction, settings, client, model = self._prepare_turn(user_text)
        self.max_tokens = LLM_CATALOG.get(settings["llm_model"], LLM_CATALOG[DEFAULT_LLM_MODEL])["max_tokens"]

        reply_start = time.perf_counter()
        try:
            stream = client.chat.completions.create(
                model=model, messages=messages, temperature=settings["llm_temperature"],
                max_tokens=self.max_tokens, tools=self.tool_schemas, tool_choice="auto", stream=True,
            )
            accumulated_content = ""
            tool_call_detected = False
            for chunk in stream:
                delta = chunk.choices[0].delta
                if getattr(delta, "tool_calls", None):
                    tool_call_detected = True
                    break
                if delta.content:
                    accumulated_content += delta.content
                    yield delta.content

            if tool_call_detected or not _is_usable_reply(accumulated_content):
                # Either a tool call started, or the stream produced nothing usable (mirrors
                # _complete()'s own "empty/leaked content" retry reasoning) - both cases need
                # the full non-streaming machinery, not a partial/wrong answer already sent to
                # TTS. Nothing has been spoken yet in either case: a tool call is caught before
                # its first content delta (content and tool_calls don't interleave within one
                # streamed choice - confirmed against the real Groq API, not assumed), and an
                # unusable stream never yielded anything to begin with.
                logging.info(
                    "reply_stream falling back to non-streaming path",
                    extra={"business_id": str(self.business_id), "reason": "tool_call" if tool_call_detected else "empty_stream"},
                )
                if tool_call_detected and self._on_tool_call:
                    # Yielded as part of THIS stream, not spoken out-of-band - see
                    # ChatEngine.__init__'s on_tool_call docstring for why that used to reorder
                    # audio (real reply, then the filler) once llm_node became a stream.
                    filler_text = self._on_tool_call(user_text)
                    if filler_text:
                        yield filler_text
                reply_text = self._complete(client, model, messages, settings["llm_temperature"], language_instruction)
                yield reply_text
            else:
                reply_text = accumulated_content
        except (GroqError, OpenAIError):
            logging.exception("ChatEngine.reply_stream() failed, returning fallback")
            reply_text = FALLBACK_REPLIES.get(settings["reply_language"], FALLBACK_REPLIES["auto"])
            yield reply_text

        self._finish_turn(user_text, reply_text, reply_start)

    def _timed_completion(self, client, model: str, stage: str, **kwargs) -> object:
        """Every LLM call goes through here instead of calling client.chat.completions.create
        directly, purely so a slow turn can be broken down by stage (initial call vs. each
        tool-calling round) instead of showing up as one unexplained multi-second gap - see
        the E2E latency investigation in plan.md (2026-08-10, LiveKit Console showed 13s total
        with only ~2.4s accounted for by STT+turn-detection)."""
        start = time.perf_counter()
        completion = client.chat.completions.create(model=model, **kwargs)
        logging.info(
            "LLM call finished",
            extra={
                "business_id": str(self.business_id), "stage": stage, "model": model,
                "ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return completion

    def _complete(
        self, client, model: str, messages: list[dict], temperature: float,
        language_instruction: str | None = None,
    ) -> str:
        try:
            completion = self._timed_completion(
                client, model, "initial",
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
                tools=self.tool_schemas,
                tool_choice="auto",
            )
            response_message = completion.choices[0].message
        except (GroqAPIStatusError, OpenAIAPIStatusError):
            # occasionally the model generates a malformed tool call that the provider
            # rejects outright (400) before we ever see a tool_calls response - fall back to
            # a plain reply instead of failing this turn entirely.
            completion = self._timed_completion(
                client, model, "initial_fallback_no_tools",
                messages=messages,
                temperature=temperature,
                max_tokens=self.max_tokens,
            )
            return completion.choices[0].message.content

        if response_message.tool_calls:
            return self._run_tool_calls(client, model, messages, response_message, temperature, language_instruction)

        if _is_usable_reply(response_message.content):
            return response_message.content

        # the model tried to call a tool but leaked it as text, or returned empty/no-content -
        # retry once (usually enough to get a properly structured tool_calls response or a
        # real reply), and if it happens again, escalate to a human instead of ever showing
        # the customer raw function-call syntax or a blank message
        retry = self._timed_completion(
            client, model, "retry",
            messages=messages,
            temperature=temperature,
            max_tokens=self.max_tokens,
            tools=self.tool_schemas,
            tool_choice="auto",
        )
        retry_message = retry.choices[0].message
        if retry_message.tool_calls:
            return self._run_tool_calls(client, model, messages, retry_message, temperature, language_instruction)
        if _is_usable_reply(retry_message.content):
            return retry_message.content
        return TOOLS_BY_NAME["recommend_human_agent"](
            self.business_id, self.session_id, "Could not correctly process the user's request (function call failed)"
        )

    # Safety cap on chained tool-call rounds - real conversations here need at most 2 (e.g.
    # an ambiguous lookup, then a disambiguated re-query), this just bounds a runaway loop.
    _MAX_TOOL_ROUNDS = 3

    def _run_tool_calls(
        self, client, model: str, messages: list[dict], response_message, temperature: float,
        language_instruction: str | None = None, _round: int = 1,
    ) -> str:
        # No on_tool_call firing here anymore - reply_stream() (the only live caller that ever
        # sets on_tool_call) now calls it directly and yields the result before delegating to
        # _complete()/_run_tool_calls, so this method doesn't need to know about fillers at
        # all. See ChatEngine.__init__'s on_tool_call docstring for why.
        messages.append(response_message)
        for tool_call in response_message.tool_calls:
            function = TOOLS_BY_NAME[tool_call.function.name]
            arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            arguments = arguments or {}
            tool_start = time.perf_counter()
            # business_id (and, for recommend_human_agent/book_appointment, session_id, for
            # traceability back to the conversation) are bound here, not supplied by the
            # model - they're never part of TOOL_SCHEMAS.
            if tool_call.function.name in ("recommend_human_agent", "book_appointment"):
                result = function(self.business_id, self.session_id, **arguments)
            else:
                result = function(self.business_id, **arguments)
            logging.info(
                "tool call finished",
                extra={
                    "business_id": str(self.business_id), "tool": tool_call.function.name,
                    "round": _round, "ms": round((time.perf_counter() - tool_start) * 1000),
                },
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        if language_instruction:
            # re-assert as the very last message - by now the tool call/result round trip
            # has pushed the original language instruction several messages back, and a
            # long English-authored persona/guardrail block can otherwise dominate by sheer
            # recency and outweigh it (observed: an English-configured business replying in
            # English to an Urdu message even with "auto" reply_language set).
            messages.append({"role": "system", "content": language_instruction})

        # Offer tools again on the follow-up completion, not just a plain text request - a
        # tool result can be ambiguous or incomplete (e.g. check_appointment_slots's "no
        # exact match, here are similar options"), and the model's genuinely correct next
        # step is often a second tool call (re-querying with the disambiguated name), not a
        # final reply yet. Live-observed failure without this: the model wasn't offered a
        # tool, so it either leaked malformed tool-call-shaped text, or spent its whole
        # max_tokens budget on an internal "thought" fragment and returned literally no
        # content - which used to crash the whole turn (None hitting a NOT NULL DB column).
        if _round < self._MAX_TOOL_ROUNDS:
            completion = self._timed_completion(
                client, model, f"tool_round_{_round}",
                messages=messages, temperature=temperature, max_tokens=self.max_tokens,
                tools=self.tool_schemas, tool_choice="auto",
            )
            next_message = completion.choices[0].message
            if next_message.tool_calls:
                return self._run_tool_calls(
                    client, model, messages, next_message, temperature, language_instruction, _round + 1
                )
            if _is_usable_reply(next_message.content):
                return next_message.content
        else:
            completion = self._timed_completion(
                client, model, "final_round_no_tools",
                messages=messages, temperature=temperature, max_tokens=self.max_tokens,
            )
            if _is_usable_reply(completion.choices[0].message.content):
                return completion.choices[0].message.content

        # exhausted rounds, or the model returned empty/leaked content instead of a real
        # reply - escalate rather than log/speak a None or garbled message to the customer
        return TOOLS_BY_NAME["recommend_human_agent"](
            self.business_id, self.session_id, "Could not compose a final reply after tool calls (empty or malformed model output)"
        )
