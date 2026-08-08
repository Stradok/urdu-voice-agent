from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .db import get_session
from .models import Escalation, Exchange, Session


def start_session(business_id: UUID, channel: str = "dashboard") -> UUID:
    with get_session() as session:
        row = Session(business_id=business_id, channel=channel)
        session.add(row)
        session.flush()
        return row.id


def log_exchange(session_id: UUID, user_text: str, reply_text: str):
    with get_session() as session:
        session.add(Exchange(session_id=session_id, user_text=user_text, assistant_text=reply_text))


def log_escalation(business_id: UUID, session_id: UUID | None, reason: str):
    with get_session() as session:
        session.add(Escalation(business_id=business_id, session_id=session_id, reason=reason))


def list_sessions(business_id: UUID) -> list[dict]:
    with get_session() as session:
        rows = session.scalars(
            select(Session)
            .where(Session.business_id == business_id)
            .options(selectinload(Session.exchanges))
            .order_by(Session.started_at)
        ).all()
        return [
            {
                "session_id": str(row.id),
                "started_at": row.started_at.isoformat(),
                "exchanges": [
                    {
                        "timestamp": ex.timestamp.isoformat(),
                        "user": ex.user_text,
                        "assistant": ex.assistant_text,
                    }
                    for ex in sorted(row.exchanges, key=lambda e: e.timestamp)
                ],
            }
            for row in rows
        ]


def list_escalations(business_id: UUID) -> list[dict]:
    with get_session() as session:
        rows = session.scalars(
            select(Escalation).where(Escalation.business_id == business_id).order_by(Escalation.timestamp)
        ).all()
        return [
            {
                "timestamp": row.timestamp.isoformat(),
                "session_id": str(row.session_id) if row.session_id else None,
                "reason": row.reason,
            }
            for row in rows
        ]
