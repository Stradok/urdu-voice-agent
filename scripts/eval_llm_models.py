"""One-off head-to-head comparison of candidate LLMs (src/llm.py's LLM_CATALOG) against
this project's own dental-clinic persona, guardrails, tools, and few-shot examples - not
just published benchmark numbers, which don't measure tool-calling reliability, script
corruption, or empathetic tone. Re-run whenever LLM_CATALOG changes or a new model is
worth evaluating. See plan.md's "Open issue" section for the benchmark data this follows up on.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dotenv

dotenv.load_dotenv()

from sqlalchemy import select

from src import persona
from src import settings as app_settings
from src.db import get_session
from src.faq_store import FaqStore
from src.llm import LANGUAGE_MODE_INSTRUCTIONS, LLM_CATALOG, ChatEngine, _get_client
from src.models import Business

TEST_CASES = [
    ("pain_empathy", "مجھے دانت میں بہت شدید درد ہو رہا ہے، رات بھر سو نہیں سکا"),
    ("tool_call_cross_lingual", "دانتوں کی صفائی کے لیے اپائنٹمنٹ چاہیے"),
    ("greeting_roman_urdu", "salam, clinic k timings kya hain?"),
    ("english_input", "Hi, do you guys do root canals?"),
]


def get_dental_business_id():
    with get_session() as s:
        biz = s.scalar(select(Business).where(Business.slug == "dental-clinic"))
        return biz.id


def build_messages(engine: ChatEngine, user_text: str):
    faq_context = engine.faq_store.get_context(engine.business_id, user_text)
    system_prompt = persona.build_system_prompt(engine.business_id)
    messages = [{"role": "system", "content": system_prompt}] + engine._pick_examples(user_text)
    if faq_context:
        messages.append({"role": "system", "content": f"متعلقہ معلومات: {faq_context}"})
    settings = app_settings.load_settings(engine.business_id)
    language_instruction = LANGUAGE_MODE_INSTRUCTIONS.get(settings["reply_language"])
    if language_instruction:
        messages.append({"role": "system", "content": language_instruction})
    messages.append({"role": "user", "content": user_text})
    return messages, language_instruction, settings["llm_temperature"]


def looks_broken(reply: str | None) -> str | None:
    if reply is None:
        return None
    if "<function" in reply or reply.strip().startswith("{"):
        return "leaked tool-call syntax"
    return None


def main():
    business_id = get_dental_business_id()
    faq_store = FaqStore()
    results = []

    for model_key, entry in LLM_CATALOG.items():
        client = _get_client(entry["provider"])
        for case_name, user_text in TEST_CASES:
            engine = ChatEngine(faq_store=faq_store, business_id=business_id, business_type="dentist_clinic")
            messages, language_instruction, temperature = build_messages(engine, user_text)

            t0 = time.monotonic()
            reply, error = None, None
            try:
                reply = engine._complete(client, entry["model"], messages, temperature, language_instruction)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
            elapsed = time.monotonic() - t0

            flag = looks_broken(reply)
            results.append({
                "model": model_key, "case": case_name, "latency_s": round(elapsed, 2),
                "reply": reply, "error": error, "flag": flag,
            })
            status = f"ERROR: {error}" if error else (f"[{flag}] {reply}" if flag else reply)
            print(f"[{model_key:45s}] {case_name:25s} {elapsed:5.2f}s  {status}")
        print()

    return results


if __name__ == "__main__":
    main()
