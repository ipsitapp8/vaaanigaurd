"""Hash-chained audit log (SPEC section N).

payload_hash = sha256(canonical({actor, action, analysis_id, ts, detail}))
entry_hash   = sha256(prev_hash + payload_hash)

Editing any field of any entry, deleting an entry, or reordering entries breaks the chain.
Never put transcripts, audio, phone or account numbers in `detail`.
"""
import threading
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.tables import AuditEntry
from app.services.evidence import canonical_json, hash_json, sha256_hex

GENESIS_HASH = "0" * 64
_lock = threading.Lock()


def _ts_key(ts: datetime) -> str:
    return ts.replace(tzinfo=None).isoformat()  # tz-independent: UTC is implied


def compute_payload_hash(actor: str, action: str, analysis_id: str | None, ts: datetime, detail_json: str) -> str:
    return hash_json({"actor": actor, "action": action, "analysis_id": analysis_id, "ts": _ts_key(ts), "detail": detail_json})


def compute_entry_hash(prev_hash: str, payload_hash: str) -> str:
    return sha256_hex((prev_hash + payload_hash).encode("ascii"))


def append_entry(session: Session, actor: str, action: str, analysis_id: str | None = None, detail: dict | None = None) -> AuditEntry:
    with _lock:
        last = session.exec(select(AuditEntry).order_by(AuditEntry.seq.desc())).first()  # type: ignore[union-attr]
        prev = last.entry_hash if last else GENESIS_HASH
        ts = datetime.now(timezone.utc)
        detail_json = canonical_json(detail or {})
        payload_hash = compute_payload_hash(actor, action, analysis_id, ts, detail_json)
        entry = AuditEntry(
            ts=ts,
            actor=actor,
            action=action,
            analysis_id=analysis_id,
            detail_json=detail_json,
            payload_hash=payload_hash,
            prev_hash=prev,
            entry_hash=compute_entry_hash(prev, payload_hash),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def verify_chain(session: Session) -> tuple[bool, int | None]:
    """Return (valid, broken_at_seq). Deleting the first entries is detected via the genesis link;
    deleting trailing entries is not detectable without an external anchor (documented limitation)."""
    prev = GENESIS_HASH
    for e in session.exec(select(AuditEntry).order_by(AuditEntry.seq)):  # type: ignore[arg-type]
        expected_payload = compute_payload_hash(e.actor, e.action, e.analysis_id, e.ts, e.detail_json)
        if (
            e.prev_hash != prev
            or e.payload_hash != expected_payload
            or e.entry_hash != compute_entry_hash(prev, e.payload_hash)
        ):
            return False, e.seq
        prev = e.entry_hash
    return True, None
