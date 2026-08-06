import json
import os

import numpy as np
from groq import APIStatusError, Groq, GroqError

from . import persona, session_log, settings as app_settings
from .tools import TOOL_SCHEMAS, TOOLS_BY_NAME

MODEL = "llama-3.3-70b-versatile"  # stable production model on Groq; strong Urdu support
TOP_K_EXAMPLES = 2
FALLBACK_REPLY = "معذرت، ابھی مجھے تھوڑی دقت ہو رہی ہے۔ براہ کرم ایک لمحے بعد دوبارہ کوشش کریں۔"


class ChatEngine:
    def __init__(self, faq_store, api_key: str | None = None, history_turns: int = 6):
        self.client = Groq(api_key=api_key or os.environ["GROQ_API_KEY"])
        self.faq_store = faq_store
        self.history: list[dict] = []
        self.history_turns = history_turns

        # reuse the FAQ store's embedder instead of loading a second model onto the GPU
        self.embedder = faq_store.embedder
        session_log.start_session()

    def _pick_examples(self, user_text: str, k: int = TOP_K_EXAMPLES) -> list[dict]:
        """Return the k example exchanges whose user-side is most similar to what was just said,
        so the LLM sees tone-matched few-shot context (small talk vs. complaint vs. thanks, etc.)
        instead of always the same fixed pair. Reads the bank fresh each call since the
        Continuous Learning UI can append new examples to it while the app is running."""
        example_bank = persona.load_example_bank()
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
        faq_context = self.faq_store.get_context(user_text)

        system_prompt = persona.build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}] + self._pick_examples(user_text)

        if faq_context:
            messages.append({
                "role": "system",
                "content": f"متعلقہ معلومات: {faq_context}",
            })

        messages += self.history[-self.history_turns * 2:]
        messages.append({"role": "user", "content": user_text})

        try:
            reply_text = self._complete(messages)
        except GroqError:
            # rate limits, malformed tool-call generations, network hiccups, etc. -
            # degrade gracefully instead of crashing the whole conversation loop.
            return FALLBACK_REPLY

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply_text})
        session_log.log_exchange(user_text, reply_text)

        return reply_text

    def _complete(self, messages: list[dict]) -> str:
        temperature = app_settings.load_settings()["llm_temperature"]
        try:
            completion = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=300,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
            response_message = completion.choices[0].message
        except APIStatusError:
            # occasionally the model generates a malformed tool call that Groq rejects
            # outright (400) before we ever see a tool_calls response - fall back to a
            # plain reply instead of failing this turn entirely.
            completion = self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=300,
            )
            return completion.choices[0].message.content

        if not response_message.tool_calls:
            return response_message.content

        messages.append(response_message)
        for tool_call in response_message.tool_calls:
            function = TOOLS_BY_NAME[tool_call.function.name]
            arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            arguments = arguments or {}
            result = function(**arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        completion = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=300,
        )
        return completion.choices[0].message.content
