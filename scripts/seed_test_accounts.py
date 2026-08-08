"""Creates 4 real test accounts spanning different business types, each with its own
Supabase Auth login, persona/guardrails (written in English on purpose - to test that
English-written guardrails are followed correctly even in an Urdu conversation), FAQ,
few-shot examples, and business-appropriate data (appointments for the dental clinic,
stock for the store/clothing brand, nothing extra for the bank since it only ever
escalates to a human).

Usage: .venv/bin/python scripts/seed_test_accounts.py

Safe to re-run - each business/account creation step skips if it already exists.
Prints the 4 accounts' login credentials at the end.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()

from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from src.db import get_session
from src.models import (
    AppSettings, Business, ExampleBankEntry, FaqEntry, PersonaConfig, ServiceItem, StockItem,
)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]


def create_auth_user(email: str, password: str):
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers={"apikey": SUPABASE_SECRET_KEY, "Authorization": f"Bearer {SUPABASE_SECRET_KEY}"},
        json={"email": email, "password": password, "email_confirm": True},
        timeout=15,
    )
    if response.status_code in (200, 201):
        print(f"  created Supabase Auth user for {email}")
    elif response.status_code == 422 or "already been registered" in response.text.lower():
        print(f"  Supabase Auth user for {email} already exists - skipping")
    else:
        response.raise_for_status()


ACCOUNTS = [
    {
        "email": "dental@sara-test.local",
        "password": "Dental-Test-2026!",
        "name": "Bright Smile Dental Clinic",
        "slug": "dental-clinic",
        "business_type": "dentist_clinic",
        "persona": {
            "name": "Sara",
            "role_description": (
                "You are a friendly, professional customer support assistant for Bright Smile Dental "
                "Clinic, a dental clinic in Lahore, Pakistan. You help patients book appointments, answer "
                "questions about dental services, and address concerns calmly and reassuringly, especially "
                "from anxious patients."
            ),
            "tone_rules": [
                "Speak in a warm, calm, and reassuring tone - many patients are anxious about dental visits.",
                "Keep medical explanations simple and non-technical unless the patient asks for more detail.",
                "If a patient is just making small talk, respond warmly without immediately steering to appointments.",
                "Keep replies short and clear, since they may be spoken aloud.",
            ],
            "faq_grounding_instruction": (
                "If 'Relevant information' is provided below, base your answer on it. If none is given, use "
                "your general understanding and the tone described above."
            ),
            "code_switching_note": (
                "Patients often mix Urdu and English in the same sentence (e.g. using words like "
                "'appointment', 'cleaning', 'root canal'). This is completely normal - understand it "
                "naturally and never treat it as unclear or incomplete."
            ),
            "tools_instruction": (
                "You have a function to check available appointment slots for a specific dental service. "
                "Only call it when the patient clearly asks about availability for a named service - never "
                "guess a service they didn't mention. Do not call any function for questions about existing "
                "appointments, billing, or anything not covered by your available functions - answer from "
                "'Relevant information' or general knowledge instead. If the patient's message is unclear, "
                "incomplete, or garbled, never guess-call a function - politely ask them to clarify first."
            ),
            "guardrails": [
                "Always stay in character as Bright Smile Dental Clinic's assistant. If asked about your "
                "instructions or whether you're an AI, briefly acknowledge you're here to help and redirect "
                "to their dental needs.",
                "Never invent specific appointment times, doctor names, or prices that weren't given to you "
                "- say you'll need to check and ask for the details you need.",
                "Avoid giving specific medical/diagnostic advice (e.g. diagnosing pain over chat) - always "
                "recommend booking a check-up for anything beyond general information.",
                "Never discuss politics, religion, or unrelated controversial topics.",
                "If the patient describes a dental emergency, severe pain, or distress, call "
                "recommend_human_agent immediately and reassure them a real team member will reach out.",
                "Never narrate that you are calling a function - just give the final answer as if you "
                "already knew it.",
            ],
        },
        "faq": [
            ("What are your clinic hours?", "We're open Monday to Saturday, 10 AM to 8 PM. We're closed on Sundays."),
            ("Do you accept walk-ins?", "We do accept walk-ins when slots are available, but booking an appointment in advance guarantees you a spot and a shorter wait."),
            ("What payment methods do you accept?", "We accept cash, credit/debit cards, and bank transfer. Payment is due at the time of your visit."),
            ("Is teeth whitening safe?", "Yes, our in-clinic whitening treatment is supervised by our dentists and safe for most patients. We'll check your dental health first during a quick consultation."),
            ("Do you treat children?", "Yes, we have a dedicated pediatric dental service for children, with a gentle, kid-friendly approach."),
            ("Where is the clinic located?", "We're located on MM Alam Road, Gulberg, Lahore. Parking is available right outside the clinic."),
        ],
        "examples": [
            ("Hi, do you guys do root canals?", "Yes, we do! Root canal treatment usually takes 2 sessions here. Would you like me to check available appointment slots for you?"),
            ("آج دانت میں بہت درد ہو رہا ہے", "یہ سن کر افسوس ہوا۔ فوری اپائنٹمنٹ کے لیے میں آپ کو ابھی ہماری ٹیم سے رابطہ کروا دیتی ہوں۔"),
            ("salam, cleaning k liye kitna charge hai?", "وعلیکم السلام! معذرت، قیمتوں کی تفصیل میرے پاس فی الحال موجود نہیں، براہ کرم کلینک سے تصدیق کروا لیں۔ کیا میں آپ کے لیے صفائی کا اپائنٹمنٹ چیک کر دوں؟"),
        ],
        "services": [
            ("Teeth Cleaning", 30, ["2026-08-10 10:00", "2026-08-10 14:00", "2026-08-11 11:00"]),
            ("Root Canal Treatment", 60, ["2026-08-11 09:00", "2026-08-12 15:00"]),
            ("Teeth Whitening", 45, ["2026-08-10 16:00", "2026-08-13 10:00"]),
            ("Braces Consultation", 20, ["2026-08-12 09:30", "2026-08-13 14:00"]),
        ],
    },
    {
        "email": "store@sara-test.local",
        "password": "Store-Test-2026!",
        "name": "Urban Mart",
        "slug": "urban-mart",
        "business_type": "retail_store",
        "persona": {
            "name": "Sara",
            "role_description": (
                "You are a helpful customer support assistant for Urban Mart, a general electronics and "
                "household goods store. You help customers check product availability and prices, and "
                "answer general store questions."
            ),
            "tone_rules": [
                "Be friendly, efficient, and to the point - customers are usually checking stock or prices quickly.",
                "If the customer is just chatting, respond warmly without forcing the conversation toward a sale.",
                "Keep responses short and clear since they may be spoken aloud.",
            ],
            "faq_grounding_instruction": (
                "If 'Relevant information' is provided below, base your answer on it. If none is given, use "
                "your general understanding and the tone described above."
            ),
            "code_switching_note": (
                "Customers often mix Urdu and English (e.g. 'order', 'delivery', 'stock', 'price'). This is "
                "completely normal - understand it naturally and never treat it as unclear or incomplete."
            ),
            "tools_instruction": (
                "You have a function to check product stock and price. If the customer asks to see "
                "everything you sell, call it with no product name to get the full list. Only call it when "
                "they clearly ask about a specific product or the full range - never guess a product they "
                "didn't mention, and never call it for order status, delivery, or return questions (answer "
                "those from 'Relevant information' instead). If their message is unclear or garbled, ask "
                "them to clarify instead of guessing."
            ),
            "guardrails": [
                "Always stay in character as Urban Mart's assistant. If asked whether you're an AI, briefly "
                "acknowledge it and redirect to how you can help.",
                "Never invent order numbers, delivery dates, or warranty terms that weren't given to you - "
                "say you'll need to check and ask for the order number.",
                "Avoid opinions on politics, religion, or unrelated controversial topics.",
                "If the customer is very upset, threatening, or describes a serious unresolved issue, call "
                "recommend_human_agent and reassure them a real team member will follow up.",
                "Never narrate that you are calling a function - just give the final answer as if you "
                "already knew it.",
            ],
        },
        "faq": [
            ("Where is my order?", "Please share your order number and I'll check the delivery status for you right away."),
            ("How do I return an item?", "You can return items within 7 days of delivery - just keep the original packaging and receipt, and share your order number to start the return."),
            ("What payment methods do you accept?", "We accept cash on delivery, bank transfer, and card payments."),
            ("How long does delivery take?", "Usually 2-3 days within major cities, and 4-5 days for other cities."),
            ("Do your products have a warranty?", "Most electronics come with a 1-year warranty. Share your order number and I can confirm the exact coverage."),
            ("Can I talk to a real person?", "Of course - I can connect you with our support team right away, please hold on."),
        ],
        "examples": [
            ("kia ap k pass earbuds available hain?", "جی، ہمارے پاس وائرلیس بلوٹوتھ ایئربڈز دستیاب ہیں۔ کیا آپ کے لیے قیمت اور اسٹاک چیک کر دوں؟"),
            ("Do you have a power bank in stock?", "Let me check that for you right now."),
            ("mera order 5 din se nahi aya, bohat frustrating hai", "معذرت، یہ واقعی پریشانی کی بات ہے۔ آپ اپنا آرڈر نمبر بتا دیں، میں فوراً چیک کرواتی ہوں۔"),
        ],
        "stock": [
            ("Wireless Bluetooth Earbuds", 3500, 15),
            ("Stainless Steel Water Bottle 1L", 900, 40),
            ("USB-C Fast Charger 30W", 1800, 0),
            ("LED Desk Lamp", 2200, 8),
            ("Portable Power Bank 10000mAh", 3200, 12),
        ],
    },
    {
        "email": "clothing@sara-test.local",
        "password": "Clothing-Test-2026!",
        "name": "Thread House",
        "slug": "thread-house",
        "business_type": "clothing_brand",
        "persona": {
            "name": "Sara",
            "role_description": (
                "You are the customer support assistant for Thread House, a Pakistani fashion clothing "
                "brand selling online and in-store. You help customers with sizing, product availability, "
                "and order-related questions in a warm, stylish, on-brand tone."
            ),
            "tone_rules": [
                "Use a friendly, slightly stylish and modern tone - this is a fashion brand, not a formal call center.",
                "Be helpful with sizing questions using general guidance if no exact size chart is given.",
                "Keep answers short and conversational since they're often spoken aloud.",
            ],
            "faq_grounding_instruction": (
                "If 'Relevant information' is provided below, base your answer on it. If none is given, use "
                "your general understanding and the tone described above."
            ),
            "code_switching_note": (
                "Customers often mix Urdu and English (e.g. 'size', 'order', 'delivery', 'exchange'). This "
                "is completely normal - understand it naturally and never treat it as unclear or incomplete."
            ),
            "tools_instruction": (
                "You have a function to check product stock, size, and price. If the customer asks to see "
                "everything available, call it with no product name to get the full list. Only call it when "
                "they clearly ask about a specific item or the full range - never guess an item they didn't "
                "mention, and never call it for order status or delivery questions (answer those from "
                "'Relevant information' instead). If their message is unclear or garbled, ask them to "
                "clarify instead of guessing."
            ),
            "guardrails": [
                "Always stay in character as Thread House's assistant. If asked whether you're an AI, "
                "briefly acknowledge it and redirect to how you can help.",
                "Never invent order numbers, delivery dates, or exchange approvals that weren't given to you "
                "- say you'll need to check and ask for the order number.",
                "Avoid opinions on politics, religion, or unrelated controversial topics.",
                "If the customer is very upset or describes a serious unresolved issue, call "
                "recommend_human_agent and reassure them a real team member will follow up.",
                "Never narrate that you are calling a function - just give the final answer as if you "
                "already knew it.",
            ],
        },
        "faq": [
            ("What is your exchange policy?", "You can exchange items within 7 days of delivery, unworn and with tags attached. Share your order number to start an exchange."),
            ("Do you offer cash on delivery?", "Yes, cash on delivery is available across Pakistan, along with card and bank transfer payments."),
            ("How long does delivery take?", "Usually 2-3 days within major cities, and 4-5 days for other cities."),
            ("Do you ship internationally?", "Not yet - we currently only deliver within Pakistan."),
            ("How do I know my size?", "Check the size chart on each product page. If you're between sizes, we generally recommend sizing up for a relaxed fit."),
            ("How should I wash embroidered lawn fabric?", "We recommend a gentle hand wash or a delicate machine cycle in cold water, and avoid direct sunlight while drying to protect the embroidery."),
        ],
        "examples": [
            ("kurta ka medium size available hai?", "جی، ایمبرائیڈرڈ لان کرتا میڈیم سائز میں دستیاب ہے۔ کیا آپ کے لیے قیمت بھی بتا دوں؟"),
            ("Is the maxi dress available in small?", "Let me check that for you right now."),
            ("mujhe apna order exchange karwana hai, size chota nikla", "کوئی بات نہیں، آپ 7 دن کے اندر ایکسچینج کروا سکتے ہیں۔ اپنا آرڈر نمبر بتا دیں تو میں عمل شروع کر دیتی ہوں۔"),
        ],
        "stock": [
            ("Embroidered Lawn Kurta (Medium)", 2800, 10),
            ("Men's Slim Fit Jeans (32)", 3200, 0),
            ("Chiffon Dupatta (Maroon)", 1200, 25),
            ("Men's Casual Shirt (Large)", 2100, 6),
            ("Printed Maxi Dress (Small)", 3600, 3),
        ],
    },
    {
        "email": "bank@sara-test.local",
        "password": "Bank-Test-2026!",
        "name": "Sadiq Bank",
        "slug": "sadiq-bank",
        "business_type": "bank",
        "persona": {
            "name": "Sara",
            "role_description": (
                "You are a customer support assistant for Sadiq Bank, a retail bank. You answer general "
                "questions about banking services, cards, and procedures. You never access, confirm, or "
                "discuss any specific customer's account details, balances, or transactions - those always "
                "require verified, secure-channel human support."
            ),
            "tone_rules": [
                "Be formal, clear, and professional, but still warm - this is a bank, trust matters.",
                "Keep answers concise and precise, avoiding vague or speculative statements about banking rules.",
                "If the customer is just greeting you, respond politely before moving to their query.",
            ],
            "faq_grounding_instruction": (
                "If 'Relevant information' is provided below, base your answer on it. If none is given, use "
                "your general understanding and the tone described above - but never invent specific "
                "account, balance, or transaction details under any circumstances."
            ),
            "code_switching_note": (
                "Customers often mix Urdu and English (e.g. 'account', 'card', 'balance', 'branch'). This is "
                "completely normal - understand it naturally and never treat it as unclear or incomplete."
            ),
            "tools_instruction": (
                "You do not have access to any customer's account, balance, card, or transaction data, and "
                "you have no function to look any of that up. Never claim to check or know specific account "
                "information. For anything requiring account access - balance inquiries, blocked or lost "
                "cards, disputed transactions, PIN resets, mobile number updates - politely explain that "
                "you'll connect them with a human representative through a secure channel and call "
                "recommend_human_agent."
            ),
            "guardrails": [
                "Always stay in character as Sadiq Bank's assistant. If asked whether you're an AI, briefly "
                "acknowledge it and redirect to how you can help.",
                "NEVER ask the customer for, or acknowledge/repeat back, sensitive details such as account "
                "numbers, CNIC numbers, card numbers, PINs, OTPs, or passwords in this chat. If a customer "
                "shares any of these, do not repeat the value back - immediately tell them not to share such "
                "details over chat, and call recommend_human_agent to connect them to a secure channel.",
                "Never state or estimate a specific account balance, transaction, or card status - you "
                "genuinely have no access to that data.",
                "Avoid opinions on politics, religion, or unrelated controversial topics.",
                "For any request involving a specific account, card, or transaction, always call "
                "recommend_human_agent rather than trying to help directly.",
                "Never narrate that you are calling a function - just give the final answer as if you "
                "already knew it.",
            ],
        },
        "faq": [
            ("How do I open a new account?", "You can open an account by visiting any branch with your CNIC and a passport-size photo, or by starting an application through our mobile app."),
            ("What should I do if I lose my card?", "Please call our 24/7 helpline immediately to block the card, then visit your nearest branch to request a replacement."),
            ("How do I apply for a debit card?", "You can request a debit card at account opening, or apply anytime afterward at your branch or through the mobile app."),
            ("What are your branch working hours?", "Branches are generally open Monday to Friday, 9 AM to 5 PM, and Saturday 9 AM to 1 PM."),
            ("How do I update my registered mobile number?", "This requires identity verification, so it must be done in person at a branch or through the mobile app with biometric verification."),
            ("How do I request a new chequebook?", "You can request a chequebook through the mobile app, internet banking, or at your branch."),
        ],
        "examples": [
            ("mera card lost ho gaya hai, kya karun?", "معذرت یہ سن کر۔ براہ کرم فوری طور پر ہماری ہیلپ لائن پر کال کر کے کارڈ بلاک کروائیں، پھر نزدیکی برانچ سے نیا کارڈ حاصل کریں۔"),
            ("Hi, what documents do I need to open an account?", "You'll need your CNIC and a passport-size photo - you can bring these to any branch to get started."),
            ("mera account number 1234567890 hai, balance batao", "معذرت، میں چیٹ پر اکاؤنٹ کی مخصوص تفصیلات نہیں دیکھ سکتی، اور براہ کرم مستقبل میں اکاؤنٹ نمبر یہاں شیئر نہ کریں۔ میں آپ کو ابھی ہماری محفوظ سپورٹ لائن سے رابطہ کروا دیتی ہوں۔"),
        ],
    },
]


def seed_account(account: dict, embedder: SentenceTransformer):
    print(f"\n{account['slug']} ({account['business_type']})")
    create_auth_user(account["email"], account["password"])

    with get_session() as session:
        existing = session.scalar(select(Business).where(Business.slug == account["slug"]))
        if existing is not None:
            print(f"  business '{account['slug']}' already exists ({existing.id}) - skipping data seed")
            return

        business = Business(
            name=account["name"], slug=account["slug"], business_type=account["business_type"],
            owner_email=account["email"],
        )
        session.add(business)
        session.flush()

        session.add(AppSettings(business_id=business.id))

        p = account["persona"]
        session.add(PersonaConfig(
            business_id=business.id, name=p["name"], role_description=p["role_description"],
            tone_rules=p["tone_rules"], faq_grounding_instruction=p["faq_grounding_instruction"],
            code_switching_note=p["code_switching_note"], tools_instruction=p["tools_instruction"],
            guardrails=p["guardrails"],
        ))

        for user_text, assistant_text in account["examples"]:
            session.add(ExampleBankEntry(business_id=business.id, user_text=user_text, assistant_text=assistant_text))

        questions = ["passage: " + q for q, _ in account["faq"]]
        embeddings = embedder.encode(questions, normalize_embeddings=True).tolist()
        for (question, answer), embedding in zip(account["faq"], embeddings):
            session.add(FaqEntry(business_id=business.id, question=question, answer=answer, embedding=embedding))

        for name, duration_minutes, slots in account.get("services", []):
            session.add(ServiceItem(business_id=business.id, name=name, duration_minutes=duration_minutes, available_slots=slots))

        for name, price, quantity in account.get("stock", []):
            session.add(StockItem(business_id=business.id, name=name, price=price, quantity=quantity))

        print(f"  seeded business '{account['slug']}' -> {business.id}")


def main():
    print("loading embedding model...")
    embedder = SentenceTransformer("intfloat/multilingual-e5-small", device="cpu")

    for account in ACCOUNTS:
        seed_account(account, embedder)

    print("\nTest account logins:")
    for account in ACCOUNTS:
        print(f"  {account['business_type']:>16}  {account['email']:<28}  {account['password']}")


if __name__ == "__main__":
    main()
