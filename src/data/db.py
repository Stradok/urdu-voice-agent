import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# DATABASE_URL is the transaction-mode pooler (port 6543) - used for all normal app queries.
# Alembic migrations use DIRECT_URL instead (see alembic/env.py) since transaction-mode
# pooling doesn't reliably support the session-level locks migrations need.
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
