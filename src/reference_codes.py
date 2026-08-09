import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# Digits only, no letters - these get read aloud over voice in Urdu/Roman Urdu, so avoid
# anything ambiguous when spoken (no O/0, I/1/l confusion). 5 digits gives 100k codes per
# prefix per business - comfortable headroom, still short enough to read back like a PIN.
_PREFIX = {"appointment": "AP", "escalation": "ES"}
_CODE_LENGTH = 5


def _generate_code(kind: str) -> str:
    digits = "".join(secrets.choice("0123456789") for _ in range(_CODE_LENGTH))
    return f"{_PREFIX[kind]}-{digits}"


def create_with_reference_code(session: Session, model_cls, kind: str, max_attempts: int = 5, **fields):
    """Insert a row of model_cls with a fresh reference_code, retrying on a
    (business_id, reference_code) collision. Catches the real IntegrityError from flush()
    rather than a racy check-then-insert SELECT, so this is safe under concurrent bookings/
    escalations for the same business.

    Each attempt runs in its own SAVEPOINT (session.begin_nested()), not a plain
    session.rollback() - a caller like book_appointment does other work (e.g. marking
    AppointmentSlot rows "booked" via SELECT ... FOR UPDATE) earlier in the same outer
    transaction, and a full rollback on a collision would silently discard that too."""
    last_error: IntegrityError | None = None
    for _ in range(max_attempts):
        row = model_cls(reference_code=_generate_code(kind), **fields)
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
            return row
        except IntegrityError as e:
            last_error = e
    raise RuntimeError(f"exhausted reference-code attempts for {model_cls.__name__}") from last_error
