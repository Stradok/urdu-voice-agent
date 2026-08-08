import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, ForeignKey, Numeric, String, Text
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
    llm_model: Mapped[str] = mapped_column(String, nullable=False, default="groq:llama-3.3-70b-versatile")


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
    available_slots: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)


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
