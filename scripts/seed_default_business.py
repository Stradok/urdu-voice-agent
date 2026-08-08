"""One-off migration: create the 'default' business and copy today's local JSON data
(persona, example bank, settings, FAQ, stock, services, menu, table slots) into Postgres.

Run once: .venv/bin/python scripts/seed_default_business.py

Safe to re-run - skips creation if a business with this slug already exists, so it won't
duplicate rows. It does NOT delete the local JSON files; they're left in place as a
pre-migration snapshot but are no longer read by the running app after this refactor.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from src.db import get_session
from src.models import (
    AppSettings,
    Business,
    ExampleBankEntry,
    FaqEntry,
    MenuItem,
    PersonaConfig,
    ServiceItem,
    StockItem,
    TableSlot,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SLUG = os.environ.get("DEFAULT_BUSINESS_SLUG", "default")


def _read_json(relpath: str):
    with open(DATA_DIR / relpath, encoding="utf-8") as f:
        return json.load(f)


def main():
    with get_session() as session:
        existing = session.scalar(select(Business).where(Business.slug == SLUG))
        if existing is not None:
            print(f"business '{SLUG}' already exists ({existing.id}) - nothing to do")
            return

        persona = _read_json("config/persona.json")
        examples = _read_json("config/example_bank.json")
        settings = _read_json("config/settings.json")
        faq = _read_json("faq/faq.json")
        stock = _read_json("store/stock.json")
        services = _read_json("store/services.json")
        menu = _read_json("store/menu.json")

        # spans stock + appointments + menu, so it's not a single business_type -
        # deliberately left generic; a real onboarded business gets a specific type
        # (see plan.md Phase 0 §2) once the login flow assigns one.
        business = Business(name=persona["name"], slug=SLUG, business_type="demo", owner_email="dev@local")
        session.add(business)
        session.flush()

        session.add(PersonaConfig(
            business_id=business.id,
            name=persona["name"],
            role_description=persona["role_description"],
            tone_rules=persona["tone_rules"],
            faq_grounding_instruction=persona["faq_grounding_instruction"],
            code_switching_note=persona["code_switching_note"],
            tools_instruction=persona["tools_instruction"],
            guardrails=persona["guardrails"],
        ))

        for ex in examples:
            session.add(ExampleBankEntry(business_id=business.id, user_text=ex["user"], assistant_text=ex["assistant"]))

        session.add(AppSettings(
            business_id=business.id,
            llm_temperature=settings.get("llm_temperature", 0.5),
            tts_rate_percent=settings.get("tts_rate_percent", 15),
            vad_silence_ms=settings.get("vad_silence_ms", 700),
            reply_language=settings.get("reply_language", "auto"),
        ))

        print("embedding FAQ entries...")
        embedder = SentenceTransformer("intfloat/multilingual-e5-small", device="cpu")
        questions = ["passage: " + e["question"] for e in faq]
        embeddings = embedder.encode(questions, normalize_embeddings=True).tolist() if questions else []
        for entry, embedding in zip(faq, embeddings):
            session.add(FaqEntry(business_id=business.id, question=entry["question"], answer=entry["answer"], embedding=embedding))

        for p in stock:
            session.add(StockItem(business_id=business.id, name=p["name"], price=p["price"], quantity=p["quantity"]))

        for s in services:
            session.add(ServiceItem(
                business_id=business.id, name=s["name"], duration_minutes=s["duration_minutes"],
                available_slots=s["available_slots"],
            ))

        for item in menu["items"]:
            session.add(MenuItem(
                business_id=business.id, name=item["name"], price=item["price"],
                description=item["description"], is_today_special=(item["name"] == menu["today_special"]),
            ))

        for slot in menu["table_slots"]:
            session.add(TableSlot(business_id=business.id, date_time=slot))

        print(f"seeded business '{SLUG}' -> {business.id}")


if __name__ == "__main__":
    main()
