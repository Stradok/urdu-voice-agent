import math
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import AppointmentSlot, AppSettings, BusinessHours

# All functions here take an already-open `session` and participate in the caller's
# transaction (same style as src/tools.py's own DB access) - they don't open their own
# get_session() block, since e.g. book_appointment needs slot-locking and reference-code
# creation to commit or roll back together as one unit.


def now_local(tz: str) -> datetime:
    """Current wall-clock time in `tz`, as a naive datetime - AppointmentSlot.starts_at and
    every other scheduling timestamp in this module are naive business-local wall clock,
    not UTC, so this is the one place "now" gets resolved. Never call datetime.now() bare
    elsewhere in scheduling code - a server running in UTC (Render, per plan.md) would
    silently reintroduce the exact "booked tomorrow without knowing it's Sunday" bug this
    module exists to fix."""
    return datetime.now(ZoneInfo(tz)).replace(tzinfo=None)


def set_business_hours(session: Session, business_id: UUID, hours: list[dict]) -> None:
    """Replace a business's weekly hours. `hours` is a list of dicts with keys weekday (0=Mon
    ..6=Sun), is_closed, open_time, close_time - callers should pass all 7 weekdays.

    Purges future *unbooked* slots and resets the generation watermark, so the next
    ensure_slots_generated() call regenerates under the new rules instead of leaving stale
    slots from the old hours sitting in the grid. Never touches status="booked" rows - an
    hours change must not silently cancel an existing appointment."""
    session.execute(delete(BusinessHours).where(BusinessHours.business_id == business_id))
    for h in hours:
        session.add(BusinessHours(business_id=business_id, **h))

    settings = session.get(AppSettings, business_id)
    cutoff = now_local(settings.timezone)
    session.execute(
        delete(AppointmentSlot).where(
            AppointmentSlot.business_id == business_id,
            AppointmentSlot.status == "open",
            AppointmentSlot.starts_at >= cutoff,
        )
    )
    settings.slots_generated_until = None


def ensure_slots_generated(session: Session, business_id: UUID, horizon_days: int = 14) -> None:
    """Tops up appointment_slots so open slots exist through today+horizon_days, in the
    business's own timezone. Cheap no-op on repeat calls the same day, via the
    AppSettings.slots_generated_until watermark - no cron/worker needed (none exists in this
    project, and the Render free-tier deploy target doesn't cleanly support one)."""
    settings = session.get(AppSettings, business_id)
    today = now_local(settings.timezone).date()
    target = today + timedelta(days=horizon_days)

    if settings.slots_generated_until is not None and settings.slots_generated_until >= target:
        return

    start_date = max(today, (settings.slots_generated_until or today))
    hours_by_weekday = {
        h.weekday: h
        for h in session.scalars(select(BusinessHours).where(BusinessHours.business_id == business_id))
    }

    new_starts: list[datetime] = []
    step = timedelta(minutes=settings.slot_duration_minutes)
    d = start_date
    while d <= target:
        hours = hours_by_weekday.get(d.weekday())
        if hours and not hours.is_closed and hours.open_time and hours.close_time:
            slot_time = datetime.combine(d, hours.open_time)
            close_dt = datetime.combine(d, hours.close_time)
            while slot_time + step <= close_dt:
                new_starts.append(slot_time)
                slot_time += step
        d += timedelta(days=1)

    if new_starts:
        stmt = pg_insert(AppointmentSlot).values(
            [{"business_id": business_id, "starts_at": s, "status": "open"} for s in new_starts]
        )
        # ON CONFLICT DO NOTHING on (business_id, starts_at) - the watermark should already
        # prevent regenerating a date twice, but this makes it safe rather than assumed.
        session.execute(stmt.on_conflict_do_nothing(index_elements=["business_id", "starts_at"]))

    settings.slots_generated_until = target


def find_available_starts(
    session: Session,
    business_id: UUID,
    duration_minutes: int,
    slot_duration_minutes: int,
    after: datetime,
    limit: int | None = None,
) -> list[datetime]:
    """Start times of runs of ceil(duration_minutes/slot_duration_minutes) contiguous open
    AppointmentSlot rows at/after `after`. Powers both check_appointment_slots (enumerate up
    to `limit` real options) and book_appointment (validate one exact chosen start with
    limit=1, after=that exact start)."""
    needed = max(1, math.ceil(duration_minutes / slot_duration_minutes))
    rows = session.scalars(
        select(AppointmentSlot.starts_at)
        .where(
            AppointmentSlot.business_id == business_id,
            AppointmentSlot.status == "open",
            AppointmentSlot.starts_at >= after,
        )
        .order_by(AppointmentSlot.starts_at)
    ).all()

    step = timedelta(minutes=slot_duration_minutes)
    results: list[datetime] = []
    for i in range(len(rows) - needed + 1):
        window = rows[i : i + needed]
        if all(window[j + 1] - window[j] == step for j in range(needed - 1)):
            results.append(window[0])
            if limit and len(results) >= limit:
                break
    return results
