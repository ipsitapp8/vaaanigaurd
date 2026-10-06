import logging
from collections.abc import Iterator

from sqlalchemy import inspect, text
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


def _add_missing_columns(engine) -> None:
    """create_all never alters existing tables, so a database made by an older phase would lack newer
    columns. Add them (nullable or with the model default); no data is touched."""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'
                default = getattr(col.default, "arg", None)
                if isinstance(default, (str, int, float)):
                    ddl += f" DEFAULT {default!r}" if isinstance(default, str) else f" DEFAULT {default}"
                conn.execute(text(ddl))
                log.info("column_added", extra={"fields": {"table": table.name, "column": col.name}})


def init_db() -> None:
    """Create the SQLite file and all tables, adding columns introduced since it was created. Idempotent."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _add_missing_columns(engine)


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
