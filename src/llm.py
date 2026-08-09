import json
import logging
import os
from uuid import UUID

import numpy as np
from groq import APIStatusError as GroqAPIStatusError, Groq, GroqError
from openai import APIStatusError as OpenAIAPIStatusError, OpenAI, OpenAIError

from . import persona, session_log, settings as app_settings
from .tools import TOOLS_BY_NAME, tool_schemas_for

TOP_K_EXAMPLES = 2
FALLBACK_REPLY = "معذرت، ابھی مجھے تھوڑی دقت ہو رہی ہے۔ براہ کرم ایک لمحے بعد دوبارہ کوشش کریں۔"

# Every entry keyed by the exact string stored in AppSettings.llm_model (see src/models.py).
# Ordering and notes are from our OWN eval (scripts/eval_llm_models.py, 2026-08-08) against
# this project's real dental-clinic persona/guardrails/tools/FAQ - not just the UrduMMLU
# benchmark accuracy numbers (arXiv:2606.07167) that motivated trying these models in the
# first place. The two disagree in an important way: Gemini 3.5 Flash has the best published
# Urdu accuracy (90%) but got cut off mid-sentence on 2 of 4 real test cases under this
# project's max_tokens=300 - the benchmark leader is not the practical winner. See plan.md's
# "Open issue" section for the full writeup.
LLM_CATALOG = {
    "openrouter:google/gemma-4-31b-it": {
        "provider": "openrouter", "model": "google/gemma-4-31b-it",
        "label": "Gemma 4 31B", "note": "Recommended: correct + empathetic in our own tests, cheapest, fast",
    },
    "openrouter:google/gemini-3.5-flash-lite": {
        "provider": "openrouter", "model": "google/gemini-3.5-flash-lite",
        "label": "Gemini 3.5 Flash Lite", "note": "Correct in our tests, fastest, slightly pricier than Gemma",
    },
    "openrouter:anthropic/claude-haiku-4.5": {
        "provider": "openrouter", "model": "anthropic/claude-haiku-4.5",
        "label": "Claude Haiku 4.5", "note": "Correct in our tests; once added unprompted medical advice against a guardrail",
    },
    "openrouter:deepseek/deepseek-v4-flash": {
        "provider": "openrouter", "model": "deepseek/deepseek-v4-flash",
        "label": "DeepSeek V4 Flash", "note": "Correct in our tests but noticeably slower (3-15s) on tool calls",
    },
    "groq:llama-3.3-70b-versatile": {
        "provider": "groq", "model": "llama-3.3-70b-versatile",
        "label": "Groq Llama 3.3 70B (original default)", "note": "Fastest inference, known Urdu script-corruption defect",
    },
    "openrouter:google/gemini-3.5-flash": {
        "provider": "openrouter", "model": "google/gemini-3.5-flash",
        "label": "Gemini 3.5 Flash", "note": "Not recommended as configured: best published Urdu accuracy, but got cut off mid-reply in our own tests (too verbose for max_tokens=300), also slowest and priciest",
    },
}
DEFAULT_LLM_MODEL = "openrouter:google/gemma-4-31b-it"

_provider_clients: dict[str, object] = {}


def _get_client(provider: str):
    """Provider HTTP clients are cheap to share across businesses/requests - cached at
    module level rather than one per ChatEngine, since only the API key differs."""
    if provider not in _provider_clients:
        if provider == "groq":
            _provider_clients[provider] = Groq(api_key=os.environ["GROQ_API_KEY"])
        elif provider == "openrouter":
            _provider_clients[provider] = OpenAI(
                api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1"
            )
        else:
            raise ValueError(f"unknown LLM provider: {provider}")
    return _provider_clients[provider]

# Overrides the persona's default "Urdu script only" guardrail when the business configures
# a different reply-language mode. Placed as the last system message (closest to the user's
# message) so it takes priority over the earlier, more general persona guardrails.
LANGUAGE_MODE_INSTRUCTIONS = {
    "auto": (
        "زبان کا اصول: صارف کے پیغام کی زبان کی تین ممکنہ صورتیں ہیں - براہِ کرم انہیں الگ الگ پہچانیں: "
        "(1) اگر صارف اردو رسم الخط میں لکھے (جیسے 'کیا حال ہے')، تو اردو رسم الخط میں جواب دیں۔ "
        "(2) اگر صارف رومن اردو میں لکھے، یعنی اردو زبان مگر انگریزی حروف میں (جیسے 'kya hal hai', 'mujha kapre kharedna hn')، "
        "تو جواب بھی رومن اردو ہی میں دیں - اسے انگریزی سمجھ کر انگریزی میں جواب نہ دیں، اور نہ ہی اردو رسم الخط میں بدلیں۔ "
        "(3) اگر صارف حقیقتاً انگریزی زبان میں لکھے (جیسے 'do you have earbuds?')، تو مکمل رواں انگریزی میں جواب دیں۔ "
        "یہ ہدایت اوپر دی گئی 'ہمیشہ صرف اردو میں لکھیں' کی پابندی پر فوقیت رکھتی ہے۔"
    ),
    "english": (
        "زبان کا اصول: صارف چاہے کسی بھی زبان میں بات کرے، آپ نے ہمیشہ صرف رواں انگریزی میں جواب دینا ہے۔ "
        "یہ ہدایت اوپر دی گئی 'ہمیشہ صرف اردو میں لکھیں' کی پابندی پر فوقیت رکھتی ہے۔"
    ),
    "roman_urdu": (
        "زبان کا اصول: صارف چاہے اردو رسم الخط میں لکھے، رومن اردو میں لکھے، یا انگریزی میں لکھے، آپ نے ہمیشہ "
        "رومن اردو میں جواب دینا ہے - یعنی اردو زبان، مگر انگریزی حروف میں (جیسے 'ji bilkul, kya madad kar sakti hun'). "
        "کبھی بھی اردو رسم الخط استعمال نہ کریں اور نہ ہی مکمل انگریزی میں جواب دیں۔ "
        "یہ ہدایت اوپر دی گئی 'ہمیشہ صرف اردو میں لکھیں' کی پابندی پر فوقیت رکھتی ہے۔"
    ),
    "urdu": None,  # matches the persona's existing default guardrail — no override needed
}


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
        history_turns: int = 6,
    ):
        self.faq_store = faq_store
        self.business_id = business_id
        self.tool_schemas = tool_schemas_for(business_type)
        self.history: list[dict] = []
        self.history_turns = history_turns

        # reuse the FAQ store's embedder instead of loading a second model onto the GPU
        self.embedder = faq_store.embedder
        self.session_id = session_log.start_session(business_id)

    def _pick_examples(self, user_text: str, k: int = TOP_K_EXAMPLES) -> list[dict]:
        """Return the k example exchanges whose user-side is most similar to what was just said,
        so the LLM sees tone-matched few-shot context (small talk vs. complaint vs. thanks, etc.)
        instead of always the same fixed pair. Reads the bank fresh each call since the
        Continuous Learning UI can append new examples to it while the app is running."""
        example_bank = persona.load_example_bank(self.business_id)
        example_texts = ["query: " + ex["user"] for ex in example_bank]
        example_embeddings = self.embedder.encode(example_texts, normalize_embeddings=True)

        query_emb = self.embedder.encode(["query: " + user_text], normalize_embeddings=True)[0]
        scores = example_embeddings @ query_emb
        top_indices = np.argsort(scores)[::-1][:k]

        messages = []
        for i in top_indices:
            example = example_bank[i]
            messages.append({"role": "user", "content": example["user"]})
            messages.append({"role": "assistant", "content": example["assistant"]})
        return messages

    def reply(self, user_text: str) -> str:
        faq_context = self.faq_store.get_context(self.business_id, user_text)

        system_prompt = persona.build_system_prompt(self.business_id)
        messages = [{"role": "system", "content": system_prompt}] + self._pick_examples(user_text)

        if faq_context:
            messages.append({
                "role": "system",
                "content": f"متعلقہ معلومات: {faq_context}",
            })

        settings = app_settings.load_settings(self.business_id)
        language_instruction = LANGUAGE_MODE_INSTRUCTIONS.get(settings["reply_language"])
        if language_instruction:
            messages.append({"role": "system", "content": language_instruction})

        messages += self.history[-self.history_turns * 2:]
        messages.append({"role": "user", "content": user_text})

        # re-read per turn (not cached at __init__) so a business switching models on the
        # Guardrails page takes effect on the next message, without needing to recreate or
        # invalidate the cached ChatEngine (see api.py's _chat_engines).
        catalog_entry = LLM_CATALOG.get(settings["llm_model"], LLM_CATALOG[DEFAULT_LLM_MODEL])
        client = _get_client(catalog_entry["provider"])
        model = catalog_entry["model"]

        try:
            reply_text = self._complete(client, model, messages, settings["llm_temperature"], language_instruction)
        except (GroqError, OpenAIError):
            # rate limits, malformed tool-call generations, network hiccups, etc. -
            # degrade gracefully instead of crashing the whole conversation loop, but log
            # it: silently swallowing every failure mode here means a real production
            # failure rate would otherwise be invisible.
            logging.exception("ChatEngine.reply() failed, returning fallback")
            return FALLBACK_REPLY

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply_text})
        session_log.log_exchange(self.session_id, user_text, reply_text)

        return reply_text

    def _complete(
        self, client, model: str, messages: list[dict], temperature: float,
        language_instruction: str | None = None,
    ) -> str:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=300,
                tools=self.tool_schemas,
                tool_choice="auto",
            )
            response_message = completion.choices[0].message
        except (GroqAPIStatusError, OpenAIAPIStatusError):
            # occasionally the model generates a malformed tool call that the provider
            # rejects outright (400) before we ever see a tool_calls response - fall back to
            # a plain reply instead of failing this turn entirely.
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=300,
            )
            return completion.choices[0].message.content

        if response_message.tool_calls:
            return self._run_tool_calls(client, model, messages, response_message, temperature, language_instruction)

        if not _looks_like_leaked_tool_call(response_message.content):
            return response_message.content

        # the model tried to call a tool but leaked it as text - retry once (usually enough
        # to get a properly structured tool_calls response), and if it happens again, escalate
        # to a human instead of ever showing the customer raw function-call syntax
        retry = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=300,
            tools=self.tool_schemas,
            tool_choice="auto",
        )
        retry_message = retry.choices[0].message
        if retry_message.tool_calls:
            return self._run_tool_calls(client, model, messages, retry_message, temperature, language_instruction)
        if not _looks_like_leaked_tool_call(retry_message.content):
            return retry_message.content
        return TOOLS_BY_NAME["recommend_human_agent"](
            self.business_id, self.session_id, "صارف کی درخواست کو صحیح طور پر پروسیس نہیں کیا جا سکا (فنکشن کال ناکام)"
        )

    def _run_tool_calls(
        self, client, model: str, messages: list[dict], response_message, temperature: float,
        language_instruction: str | None = None,
    ) -> str:
        messages.append(response_message)
        for tool_call in response_message.tool_calls:
            function = TOOLS_BY_NAME[tool_call.function.name]
            arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            arguments = arguments or {}
            # business_id (and, for recommend_human_agent, session_id) are bound here, not
            # supplied by the model - they're never part of TOOL_SCHEMAS.
            if tool_call.function.name == "recommend_human_agent":
                result = function(self.business_id, self.session_id, **arguments)
            else:
                result = function(self.business_id, **arguments)
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

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=300,
        )
        return completion.choices[0].message.content
