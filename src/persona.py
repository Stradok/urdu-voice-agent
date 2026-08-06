import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "data" / "config"
PERSONA_PATH = CONFIG_DIR / "persona.json"
EXAMPLE_BANK_PATH = CONFIG_DIR / "example_bank.json"


def load_persona_config() -> dict:
    with open(PERSONA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_persona_config(config: dict):
    with open(PERSONA_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_example_bank() -> list[dict]:
    with open(EXAMPLE_BANK_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_example_bank(examples: list[dict]):
    with open(EXAMPLE_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)


def build_system_prompt() -> str:
    """Assembled fresh from data/config/persona.json on every call, so edits made through
    the settings UI take effect on the very next message without restarting the app."""
    cfg = load_persona_config()

    sections = [cfg["role_description"], ""]

    sections.append("آپ کے بولنے کا انداز:")
    sections.extend(f"- {rule}" for rule in cfg["tone_rules"])
    sections.append("")

    sections.append(cfg["faq_grounding_instruction"])
    sections.append("")
    sections.append(cfg["code_switching_note"])
    sections.append("")
    sections.append(cfg["tools_instruction"])
    sections.append("")

    sections.append("حدود اور احتیاطیں:")
    sections.extend(f"- {rule}" for rule in cfg["guardrails"])

    return "\n".join(sections)
