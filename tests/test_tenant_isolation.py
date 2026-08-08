"""Proves per-business data isolation by test, not by assumption (plan.md, Phase 0 §1):
seeds two distinct fake businesses with their own data, then asserts business-scoped
queries for one never return the other's rows. Talks to the real Supabase database
configured in .env - run against a throwaway/dev project, not production data."""

import uuid

import pytest
from sqlalchemy import select

from src.db import get_session
from src.models import Business, Escalation, Exchange, FaqEntry, Session, StockItem


@pytest.fixture
def two_businesses():
    with get_session() as db:
        shoe_store = Business(
            name="Test Shoe Store",
            slug=f"test-shoe-store-{uuid.uuid4().hex[:8]}",
            business_type="retail_store",
            owner_email="shoe-store@example.com",
        )
        dentist = Business(
            name="Test Dental Clinic",
            slug=f"test-dental-clinic-{uuid.uuid4().hex[:8]}",
            business_type="dentist_clinic",
            owner_email="dentist@example.com",
        )
        db.add_all([shoe_store, dentist])
        db.flush()  # assign IDs without committing yet

        db.add_all([
            StockItem(business_id=shoe_store.id, name="Running Shoes", price=5200, quantity=10),
            FaqEntry(business_id=shoe_store.id, question="Return policy?", answer="7 days."),
        ])
        db.add_all([
            StockItem(business_id=dentist.id, name="Toothbrush", price=150, quantity=50),
            FaqEntry(business_id=dentist.id, question="Opening hours?", answer="9am-5pm."),
        ])

        shoe_session = Session(business_id=shoe_store.id, channel="dashboard")
        dentist_session = Session(business_id=dentist.id, channel="dashboard")
        db.add_all([shoe_session, dentist_session])
        db.flush()

        db.add_all([
            Exchange(session_id=shoe_session.id, user_text="Do you have size 42?", assistant_text="Yes."),
            Exchange(session_id=dentist_session.id, user_text="Book a cleaning", assistant_text="Sure."),
        ])
        db.add_all([
            Escalation(business_id=shoe_store.id, session_id=shoe_session.id, reason="angry customer"),
            Escalation(business_id=dentist.id, session_id=dentist_session.id, reason="medical concern"),
        ])

        shoe_store_id, dentist_id = shoe_store.id, dentist.id

    yield shoe_store_id, dentist_id

    with get_session() as db:
        db.execute(Business.__table__.delete().where(Business.id.in_([shoe_store_id, dentist_id])))


def test_stock_items_are_isolated(two_businesses):
    shoe_store_id, dentist_id = two_businesses
    with get_session() as db:
        shoe_stock = db.scalars(select(StockItem).where(StockItem.business_id == shoe_store_id)).all()
        dentist_stock = db.scalars(select(StockItem).where(StockItem.business_id == dentist_id)).all()

    assert {i.name for i in shoe_stock} == {"Running Shoes"}
    assert {i.name for i in dentist_stock} == {"Toothbrush"}


def test_faq_entries_are_isolated(two_businesses):
    shoe_store_id, dentist_id = two_businesses
    with get_session() as db:
        shoe_faq = db.scalars(select(FaqEntry).where(FaqEntry.business_id == shoe_store_id)).all()
        dentist_faq = db.scalars(select(FaqEntry).where(FaqEntry.business_id == dentist_id)).all()

    assert {f.question for f in shoe_faq} == {"Return policy?"}
    assert {f.question for f in dentist_faq} == {"Opening hours?"}


def test_sessions_and_exchanges_are_isolated(two_businesses):
    shoe_store_id, dentist_id = two_businesses
    with get_session() as db:
        shoe_sessions = db.scalars(select(Session).where(Session.business_id == shoe_store_id)).all()
        dentist_sessions = db.scalars(select(Session).where(Session.business_id == dentist_id)).all()

        assert len(shoe_sessions) == 1 and len(dentist_sessions) == 1

        shoe_exchanges = db.scalars(
            select(Exchange).where(Exchange.session_id == shoe_sessions[0].id)
        ).all()
        dentist_exchanges = db.scalars(
            select(Exchange).where(Exchange.session_id == dentist_sessions[0].id)
        ).all()

    assert {e.user_text for e in shoe_exchanges} == {"Do you have size 42?"}
    assert {e.user_text for e in dentist_exchanges} == {"Book a cleaning"}


def test_escalations_are_isolated(two_businesses):
    shoe_store_id, dentist_id = two_businesses
    with get_session() as db:
        shoe_escalations = db.scalars(select(Escalation).where(Escalation.business_id == shoe_store_id)).all()
        dentist_escalations = db.scalars(select(Escalation).where(Escalation.business_id == dentist_id)).all()

    assert {e.reason for e in shoe_escalations} == {"angry customer"}
    assert {e.reason for e in dentist_escalations} == {"medical concern"}


def test_cascade_delete_removes_all_business_data(two_businesses):
    """Deleting a business must not leave orphaned rows in any related table -
    proves the ondelete='CASCADE' foreign keys actually work, not just that they're declared."""
    shoe_store_id, _ = two_businesses
    with get_session() as db:
        db.execute(Business.__table__.delete().where(Business.id == shoe_store_id))

    with get_session() as db:
        remaining_stock = db.scalars(select(StockItem).where(StockItem.business_id == shoe_store_id)).all()
        remaining_sessions = db.scalars(select(Session).where(Session.business_id == shoe_store_id)).all()

    assert remaining_stock == []
    assert remaining_sessions == []
