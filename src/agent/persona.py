from uuid import UUID

from sqlalchemy import select

from ..data.db import get_session
from ..data.models import ExampleBankEntry, PersonaConfig


def load_persona_config(business_id: UUID) -> dict:
    with get_session() as session:
        cfg = session.scalar(select(PersonaConfig).where(PersonaConfig.business_id == business_id))
        return {
            "name": cfg.name,
            "role_description": cfg.role_description,
            "tone_rules": cfg.tone_rules,
            "faq_grounding_instruction": cfg.faq_grounding_instruction,
            "code_switching_note": cfg.code_switching_note,
            "tools_instruction": cfg.tools_instruction,
            "guardrails": cfg.guardrails,
        }


def save_persona_config(business_id: UUID, config: dict):
    with get_session() as session:
        cfg = session.scalar(select(PersonaConfig).where(PersonaConfig.business_id == business_id))
        cfg.name = config["name"]
        cfg.role_description = config["role_description"]
        cfg.tone_rules = config["tone_rules"]
        cfg.faq_grounding_instruction = config["faq_grounding_instruction"]
        cfg.code_switching_note = config["code_switching_note"]
        cfg.tools_instruction = config["tools_instruction"]
        cfg.guardrails = config["guardrails"]


# Keyed by business_id, holds the same list object across repeated load_example_bank() calls
# until a write invalidates it - agent/llm.py's ChatEngine._pick_examples() relies on this to
# know whether its own cached embeddings of the bank are still valid (compares by identity,
# `is`, against whatever this function returns), without persona.py needing to know anything
# about embeddings itself. Previously load_example_bank() queried Postgres and re-embedded the
# full bank on every single conversational turn, live-uninvestigated overhead independent of
# any LLM/STT/TTS provider choice - see plan.md's pipeline-overhaul section, 2026-08-10.
_example_bank_cache: dict[UUID, list[dict]] = {}


def load_example_bank(business_id: UUID) -> list[dict]:
    if business_id not in _example_bank_cache:
        with get_session() as session:
            entries = session.scalars(select(ExampleBankEntry).where(ExampleBankEntry.business_id == business_id)).all()
            _example_bank_cache[business_id] = [{"user": e.user_text, "assistant": e.assistant_text} for e in entries]
    return _example_bank_cache[business_id]


def save_example_bank(business_id: UUID, examples: list[dict]):
    with get_session() as session:
        session.query(ExampleBankEntry).filter(ExampleBankEntry.business_id == business_id).delete()
        for ex in examples:
            session.add(ExampleBankEntry(business_id=business_id, user_text=ex["user"], assistant_text=ex["assistant"]))
    _example_bank_cache.pop(business_id, None)


def add_example(business_id: UUID, example: dict):
    with get_session() as session:
        session.add(ExampleBankEntry(business_id=business_id, user_text=example["user"], assistant_text=example["assistant"]))
    _example_bank_cache.pop(business_id, None)


def build_system_prompt(business_id: UUID) -> str:
    """Assembled fresh from Postgres on every call, so edits made through the settings UI
    take effect on the very next message without restarting the app."""
    cfg = load_persona_config(business_id)

    sections = [cfg["role_description"], ""]

    sections.append("How you speak:")
    sections.extend(f"- {rule}" for rule in cfg["tone_rules"])
    sections.append("")

    sections.append(cfg["faq_grounding_instruction"])
    sections.append("")
    sections.append(cfg["code_switching_note"])
    sections.append("")
    sections.append(cfg["tools_instruction"])
    sections.append("")

    sections.append("Boundaries and guardrails:")
    sections.extend(f"- {rule}" for rule in cfg["guardrails"])

    return "\n".join(sections)
