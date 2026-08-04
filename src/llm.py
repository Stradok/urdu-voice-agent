import os

from groq import Groq

from .persona import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES

MODEL = "llama-3.3-70b-versatile"  # stable production model on Groq; strong Urdu support


class ChatEngine:
    def __init__(self, faq_store, api_key: str | None = None, history_turns: int = 6):
        self.client = Groq(api_key=api_key or os.environ["GROQ_API_KEY"])
        self.faq_store = faq_store
        self.history: list[dict] = []
        self.history_turns = history_turns

    def reply(self, user_text: str) -> str:
        faq_context = self.faq_store.get_context(user_text)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + FEW_SHOT_EXAMPLES

        if faq_context:
            messages.append({
                "role": "system",
                "content": f"متعلقہ معلومات: {faq_context}",
            })

        messages += self.history[-self.history_turns * 2:]
        messages.append({"role": "user", "content": user_text})

        completion = self.client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=300,
        )
        reply_text = completion.choices[0].message.content

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply_text})

        return reply_text
