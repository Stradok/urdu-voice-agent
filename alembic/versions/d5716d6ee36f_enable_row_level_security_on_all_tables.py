"""enable row level security on all tables

Revision ID: d5716d6ee36f
Revises: 3ff75540d6d1
Create Date: 2026-08-07 22:41:38.632770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5716d6ee36f'
down_revision: Union[str, Sequence[str], None] = '3ff75540d6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "businesses", "persona_configs", "example_bank_entries", "app_settings",
    "faq_entries", "stock_items", "service_items", "menu_items", "table_slots",
    "bookings", "sessions", "exchanges", "escalations",
]


def upgrade() -> None:
    """Enable RLS with no policies on every table - default-deny for any role except the
    table owner. Our backend connects as the owning role (via DATABASE_URL/DIRECT_URL), so
    this is a no-op for the app; it's defense-in-depth against Supabase's auto-generated
    PostgREST API ever being re-enabled and reachable with the publishable key (see plan.md,
    Phase 0 §1, "Security correction")."""
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
