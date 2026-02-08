from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_engine = None
_SessionLocal = None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as session:
            # use session

    Commits on success, rolls back on error, always closes.
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database(database_path: Path) -> None:
    global _engine, _SessionLocal

    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{database_path}"

    _engine = create_engine(database_url)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)

    # Run pending migrations
    from .migrations import run_migrations

    with session_scope() as session:
        run_migrations(session)

    # Seed default projects and shopping lists
    from .queries import seed_default_projects, seed_default_shopping_lists

    with session_scope() as session:
        seed_default_projects(session)
        seed_default_shopping_lists(session)


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database first.")
    return _SessionLocal()
