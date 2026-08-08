"""Onboard one business: create its Supabase Auth login + its `businesses` row +
a default `app_settings` row. Manual per-business provisioning, matching the pilot-stage
approach in plan.md Phase 0 §2 (no self-serve signup yet).

Usage:
  .venv/bin/python scripts/create_business_account.py \\
      --email dental@sara-test.local --password "Sara-Dental-2026!" \\
      --name "Bright Smile Dental Clinic" --slug dental-clinic --business-type dentist_clinic

Safe to re-run: skips the Supabase Auth user if that email is already registered, skips
the businesses row if that slug already exists.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import select

from src.db import get_session
from src.models import AppSettings, Business
from src.tools import BUSINESS_TYPE_TOOLS

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
        print(f"created Supabase Auth user for {email}")
    elif response.status_code == 422 or "already been registered" in response.text.lower():
        print(f"Supabase Auth user for {email} already exists - skipping")
    else:
        response.raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True, help="business display name")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--business-type", required=True, choices=sorted(BUSINESS_TYPE_TOOLS))
    args = parser.parse_args()

    create_auth_user(args.email, args.password)

    with get_session() as session:
        existing = session.scalar(select(Business).where(Business.slug == args.slug))
        if existing is not None:
            print(f"business '{args.slug}' already exists ({existing.id}) - nothing to do")
            return

        business = Business(name=args.name, slug=args.slug, business_type=args.business_type, owner_email=args.email)
        session.add(business)
        session.flush()
        session.add(AppSettings(business_id=business.id))
        print(f"created business '{args.slug}' ({args.business_type}) -> {business.id}")


if __name__ == "__main__":
    main()
