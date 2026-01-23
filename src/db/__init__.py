from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_engine = None
_SessionLocal = None


def init_database(database_path: Path) -> None:
    global _engine, _SessionLocal

    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_url = f"sqlite:///{database_path}"

    _engine = create_engine(database_url)
    Base.metadata.create_all(_engine)
    _SessionLocal = sessionmaker(bind=_engine)
    
    # Seed default projects
    from .queries import seed_default_projects
    session = _SessionLocal()
    seed_default_projects(session)
    session.close()


def get_session() -> Session:
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database first.")
    return _SessionLocal()
