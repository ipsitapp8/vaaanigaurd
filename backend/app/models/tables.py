"""SQLModel tables (SPEC section H). SQLite at data/vaaniguard.db.

Enum-like columns are plain `str` here because SQLAlchemy cannot map `Literal`;
the allowed values are the Literal aliases in schemas.py and are validated at the API layer.
"""
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Analysis(SQLModel, table=True):
    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    scenario_id: str | None = None
    is_synthetic: bool = True
    audio_sha256: str
    audio_retained: bool = False
    audio_expires_at: datetime | None = None
    language: str | None = None
    transcript_redacted: str = ""
    signals_json: str = "[]"
    rules_triggered_json: str = "[]"
    segments_json: str = "[]"
    score: int = 0
    tier: str = "LOW"
    coverage: float = 0.0
    explanation_json: str = "{}"
    status: str = "analyzed"  # analyzed|verifying|released|held|blocked|in_review|closed


class Verification(SQLModel, table=True):
    id: str = Field(primary_key=True)
    analysis_id: str = Field(index=True)
    methods_json: str = "[]"
    reason: str = ""
    outcome: str = "pending"  # pending|pass|fail|no_response
    completed_at: datetime | None = None
    actor: str = ""


class ReviewItem(SQLModel, table=True):
    id: str = Field(primary_key=True)
    analysis_id: str = Field(index=True)
    priority: int = 0
    decision: str = "pending"  # pending|approve|reject|escalate
    analyst_note: str | None = None
    decided_at: datetime | None = None


class AuditEntry(SQLModel, table=True):
    seq: int | None = Field(default=None, primary_key=True)  # autoincrement
    ts: datetime = Field(default_factory=utcnow)
    actor: str
    action: str
    analysis_id: str | None = Field(default=None, index=True)
    detail_json: str = "{}"  # non-sensitive event details (ids, tiers, outcomes); hashed into payload_hash
    payload_hash: str
    prev_hash: str
    entry_hash: str  # sha256(prev_hash + payload)


class EnrolledVoice(SQLModel, table=True):
    """SHOULD item: consented demo personas only. Never callers."""

    id: str = Field(primary_key=True)
    display_name: str
    consent_ref: str
    embedding_encrypted: bytes
