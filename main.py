import argparse
import os
import sys

from dotenv import load_dotenv

from src.business_context import get_default_business
from src.faq_store import FaqStore
from src.llm import ChatEngine
from src.settings import load_settings

load_dotenv()

REQUIRED_KEYS = {
    "GROQ_API_KEY": "console.groq.com -> API Keys",
    "AZURE_SPEECH_KEY": "portal.azure.com -> your Speech resource -> Keys and Endpoint",
    "AZURE_SPEECH_REGION": "portal.azure.com -> your Speech resource -> Keys and Endpoint (short code, e.g. eastus, not 'East US')",
}


def check_required_keys(keys):
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        print("\n.env میں یہ ویلیوز خالی ہیں / Missing required .env values:")
        for k in missing:
            print(f"  - {k}  ({REQUIRED_KEYS[k]})")
        print("\nEdit the .env file at the project root and fill these in, then run again.\n")
        sys.exit(1)


def build_engine():
    business = get_default_business()
    faq_store = FaqStore()
    return ChatEngine(faq_store=faq_store, business_id=business.id, business_type=business.business_type)


def run_text_mode():
    check_required_keys(["GROQ_API_KEY"])
    engine = build_engine()
    print("اردو کسٹمر سپورٹ ایجنٹ تیار ہے۔ (لکھ کر بات کریں، 'exit' لکھ کر بند کریں)")
    while True:
        try:
            user_text = input("آپ: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_text or user_text.lower() in {"exit", "quit"}:
            break
        reply = engine.reply(user_text)
        print(f"سارہ: {reply}")


def run_voice_mode():
    from src.mic import record
    from src.stt import Transcriber
    from src.tts import Speaker

    check_required_keys(["GROQ_API_KEY", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"])
    business = get_default_business()
    engine = ChatEngine(faq_store=FaqStore(), business_id=business.id, business_type=business.business_type)
    transcriber = Transcriber()
    speaker = Speaker()

    print("اردو وائس ایجنٹ تیار ہے۔ بولنا شروع کریں (Ctrl+C سے بند کریں)")
    while True:
        try:
            wav_path = record()
            user_text = transcriber.transcribe(wav_path, load_settings(business.id)["reply_language"])
            if not user_text:
                continue
            print(f"آپ: {user_text}")
            reply = engine.reply(user_text)
            print(f"سارہ: {reply}")
            speaker.say(reply, business.id)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="store_true", help="Run in text mode instead of voice mode")
    args = parser.parse_args()

    if args.text:
        run_text_mode()
    else:
        run_voice_mode()
