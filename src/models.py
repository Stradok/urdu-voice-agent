import uuid
from datetime import date, datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Date, ForeignKey, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

# multilingual-e5-small (src/faq_store.py) produces 384-dim embeddings.
FAQ_EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _business_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # scopes which tools the agent is allowed to call - see plan.md, Phase 0 §2
    business_type: Mapped[str] = mapped_column(String, nullable=False, default="other")
    widget_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, default=lambda: uuid.uuid4().hex)
    owner_email: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PersonaConfig(Base):
    __tablename__ = "persona_configs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    role_description: Mapped[str] = mapped_column(Text, nullable=False)
    tone_rules: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    faq_grounding_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    code_switching_note: Mapped[str] = mapped_column(Text, nullable=False)
    tools_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    guardrails: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)


class ExampleBankEntry(Base):
    __tablename__ = "example_bank_entries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_text: Mapped[str] = mapped_column(Text, nullable=False)


class AppSettings(Base):
    __tablename__ = "app_settings"

    # one row per business - mic_device/speaker_device deliberately excluded: those are
    # local-hardware settings for the Electron/CLI app, meaningless for a hosted business
    # (see plan.md's Pipeline stage reference note on this).
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    llm_temperature: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.5)
    tts_rate_percent: Mapped[int] = mapped_column(nullable=False, default=15)
    vad_silence_ms: Mapped[int] = mapped_column(nullable=False, default=700)
    reply_language: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    # key into src/llm.py's LLM_CATALOG - which provider+model this business's ChatEngine
    # uses, selectable per-business (see the LLM model dropdown on the Guardrails page).
    llm_model: Mapped[str] = mapped_column(String, nullable=False, default="openrouter:google/gemma-4-31b-it")
    # appointment-scheduling settings (src/scheduling.py) - the grid granularity slots are
    # generated at, the IANA timezone all "today"/"tomorrow" reasoning is anchored to (never
    # bare server-local time - see the Sunday-booking bug this was added to fix), and a
    # rolling-window watermark so ensure_slots_generated() is a cheap no-op after the first
    # call each day instead of re-scanning for gaps.
    slot_duration_minutes: Mapped[int] = mapped_column(nullable=False, default=30)
    timezone: Mapped[str] = mapped_column(String, nullable=False, default="Asia/Karachi")
    slots_generated_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class FaqEntry(Base):
    __tablename__ = "faq_entries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(FAQ_EMBEDDING_DIM), nullable=True)


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Numeric, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)


class ServiceItem(Base):
    __tablename__ = "service_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    # Superseded by AppointmentSlot (generated from BusinessHours) - kept as an unused
    # column for now rather than dropped immediately, so the migration that removes it is
    # a separate, cleanly revertible step once the new system is verified live.
    available_slots: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)


class BusinessHours(Base):
    """Always exactly 7 rows per business (one per weekday) - a missing row is a distinct,
    detectable 'hours never configured' state, not silently misread as closed. Weekday
    follows Python's date.weekday() convention: 0=Monday...6=Sunday (NOT isoweekday())."""

    __tablename__ = "business_hours"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    weekday: Mapped[int] = mapped_column(nullable=False)
    is_closed: Mapped[bool] = mapped_column(nullable=False, default=False)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    __table_args__ = (UniqueConstraint("business_id", "weekday"),)


class Appointment(Base):
    """A real, persisted booking - src/tools.py's book_appointment is the only writer.
    service_name/duration_minutes are snapshotted at booking time so a later service
    rename/delete doesn't retroactively change historical appointment records."""

    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("service_items.id", ondelete="SET NULL"), nullable=True
    )
    service_name: Mapped[str] = mapped_column(String, nullable=False)
    customer_name: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(nullable=False)
    duration_minutes: Mapped[int] = mapped_column(nullable=False)
    reference_code: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (UniqueConstraint("business_id", "reference_code"),)


class AppointmentSlot(Base):
    """The generated, bookable grid - src/scheduling.py's ensure_slots_generated() is the
    only writer of new rows (from BusinessHours + AppSettings.slot_duration_minutes), and
    book_appointment is the only writer of status="booked". starts_at is a naive wall-clock
    datetime in the business's own AppSettings.timezone, not UTC - always resolve "now"
    through scheduling.now_local(), never bare datetime.now()."""

    __tablename__ = "appointment_slots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    starts_at: Mapped[datetime] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")  # "open" | "booked"
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (UniqueConstraint("business_id", "starts_at"),)


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Numeric, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_today_special: Mapped[bool] = mapped_column(nullable=False, default=False)


class TableSlot(Base):
    __tablename__ = "table_slots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    date_time: Mapped[str] = mapped_column(String, nullable=False)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    date_time: Mapped[str] = mapped_column(String, nullable=False)
    party_size: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    channel: Mapped[str] = mapped_column(String, nullable=False, default="dashboard")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())

    exchanges: Mapped[list["Exchange"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Exchange(Base):
    __tablename__ = "exchanges"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_text: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())

    session: Mapped["Session"] = relationship(back_populates="exchanges")


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = _business_fk()
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())
    reference_code: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint("business_id", "reference_code"),)
