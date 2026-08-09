"""add appointment booking and reference codes

Revision ID: 7a2c9f1e4b3d
Revises: 398258e41eaf
Create Date: 2026-08-09 00:00:00.000000

Additive only - does not touch or drop service_items.available_slots (superseded by the new
appointment_slots grid, but dropped in a later, separate migration once the new booking
system is verified live, so this migration stays cleanly revertible on its own).
"""
import secrets
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7a2c9f1e4b3d'
down_revision: Union[str, Sequence[str], None] = '398258e41eaf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_RLS_TABLES = ["business_hours", "appointments", "appointment_slots"]


def _generate_escalation_code() -> str:
    return "ES-" + "".join(secrets.choice("0123456789") for _ in range(5))


def upgrade() -> None:
    op.create_table(
        'business_hours',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), nullable=False),
        sa.Column('open_time', sa.Time(), nullable=True),
        sa.Column('close_time', sa.Time(), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'weekday'),
    )

    # server_default backfills the 5 already-seeded businesses; the model-level defaults in
    # src/models.py cover new rows going forward (same pattern as the llm_model migration).
    op.add_column('app_settings', sa.Column('slot_duration_minutes', sa.Integer(), nullable=False, server_default='30'))
    op.alter_column('app_settings', 'slot_duration_minutes', server_default=None)
    op.add_column('app_settings', sa.Column('timezone', sa.String(), nullable=False, server_default='Asia/Karachi'))
    op.alter_column('app_settings', 'timezone', server_default=None)
    op.add_column('app_settings', sa.Column('slots_generated_until', sa.Date(), nullable=True))

    op.create_table(
        'appointments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=True),
        sa.Column('service_id', sa.UUID(), nullable=True),
        sa.Column('service_name', sa.String(), nullable=False),
        sa.Column('customer_name', sa.String(), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('reference_code', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['service_id'], ['service_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'reference_code'),
    )

    op.create_table(
        'appointment_slots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('appointment_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id', 'starts_at'),
    )

    for table in NEW_RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # escalations.reference_code: nullable first so the column add doesn't fail on existing
    # rows, backfill a real code per row, then tighten to NOT NULL + unique - skipping the
    # backfill would break on any deploy with existing escalation data (there is some: the
    # tenant-isolation tests and the bank test account's history).
    op.add_column('escalations', sa.Column('reference_code', sa.String(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, business_id FROM escalations")).fetchall()
    for row in rows:
        for _ in range(5):
            code = _generate_escalation_code()
            existing = bind.execute(
                sa.text("SELECT 1 FROM escalations WHERE business_id = :b AND reference_code = :c"),
                {"b": row.business_id, "c": code},
            ).first()
            if existing is None:
                bind.execute(
                    sa.text("UPDATE escalations SET reference_code = :c WHERE id = :id"),
                    {"c": code, "id": row.id},
                )
                break
    op.alter_column('escalations', 'reference_code', nullable=False)
    op.create_unique_constraint('uq_escalations_business_id_reference_code', 'escalations', ['business_id', 'reference_code'])

    # Every existing business gets a safe default 7-row (all closed) business_hours set, so
    # no business is ever in the ambiguous "zero rows configured" state - scripts/
    # seed_test_accounts.py sets the dental clinic's real hours right after this migration.
    business_ids = [r.id for r in bind.execute(sa.text("SELECT id FROM businesses")).fetchall()]
    for business_id in business_ids:
        for weekday in range(7):
            bind.execute(
                sa.text(
                    "INSERT INTO business_hours (id, business_id, weekday, is_closed) "
                    "VALUES (:id, :b, :w, true)"
                ),
                {"id": uuid.uuid4(), "b": business_id, "w": weekday},
            )


def downgrade() -> None:
    op.drop_constraint('uq_escalations_business_id_reference_code', 'escalations', type_='unique')
    op.drop_column('escalations', 'reference_code')

    op.drop_table('appointment_slots')
    op.drop_table('appointments')

    op.drop_column('app_settings', 'slots_generated_until')
    op.drop_column('app_settings', 'timezone')
    op.drop_column('app_settings', 'slot_duration_minutes')

    op.drop_table('business_hours')
