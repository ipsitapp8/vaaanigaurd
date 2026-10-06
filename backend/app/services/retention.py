"""Opt-in audio retention (SPEC section N): Fernet-encrypted, 24 h TTL, swept on startup and periodically.

By default audio is never written to disk. When `retain_audio=true` the bytes are encrypted with a key
that is generated on first run and kept in data/ (git-ignored); the plaintext never touches disk.
"""
import logging
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, select

from app.config import get_settings
from app.models.tables import Analysis

log = logging.getLogger("vaaniguard.retention")


def _audio_dir():
    d = get_settings().data_dir / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fernet() -> Fernet:
    key_path = get_settings().data_dir / "retention.key"
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(Fernet.generate_key())
    return Fernet(key_path.read_bytes())


def audio_path(analysis_id: str):
    return _audio_dir() / f"{analysis_id}.enc"


def store_audio(analysis_id: str, data: bytes) -> datetime:
    """Encrypt and write the audio; returns the expiry time."""
    audio_path(analysis_id).write_bytes(_fernet().encrypt(data))
    return datetime.now(timezone.utc) + timedelta(hours=get_settings().audio_retention_hours)


def load_audio(analysis_id: str) -> bytes | None:
    p = audio_path(analysis_id)
    if not p.exists():
        return None
    try:
        return _fernet().decrypt(p.read_bytes())
    except InvalidToken:
        log.error("retained_audio_undecryptable", extra={"fields": {"analysis_id": analysis_id}})
        return None


def delete_audio(analysis_id: str) -> bool:
    p = audio_path(analysis_id)
    if p.exists():
        p.unlink()
        return True
    return False


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite returns naive UTC


def sweep_expired(session: Session) -> int:
    """Delete retained audio past its expiry. Returns the number of files removed."""
    now = datetime.now(timezone.utc)
    removed = 0
    rows = session.exec(select(Analysis).where(Analysis.audio_retained == True)).all()  # noqa: E712
    for row in rows:
        if row.audio_expires_at is None or as_utc(row.audio_expires_at) <= now:
            delete_audio(row.id)
            row.audio_retained = False
            session.add(row)
            removed += 1
    if removed:
        session.commit()
    return removed
