import logging
from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings
from app.models import tables  # noqa: F401  (registers tables on SQLModel.metadata)

log = logging.getLogger("vaaniguard.db")
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    return _engine


def init_db() -> None:
    """Create the SQLite file and all tables. Idempotent."""
    SQLModel.metadata.create_all(get_engine())


def db_ok() -> bool:
    try:
        with Session(get_engine()) as s:
            s.exec(text("SELECT 1"))
        return True
    except Exception:
        log.error("db_check_failed")
        return False


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
