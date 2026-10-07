import json

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, func, select

from app.config import get_settings
from app.db import get_session
from app.models.schemas import AuditEntryOut, AuditVerifyResult
from app.models.tables import AuditEntry
from app.services import audit, workflow

router = APIRouter()


@router.get("/audit", response_model=list[AuditEntryOut])
def list_audit(analysis_id: str | None = None, limit: int = Query(200, ge=1, le=1000), session: Session = Depends(get_session)):
    q = select(AuditEntry)
    if analysis_id:
        q = q.where(AuditEntry.analysis_id == analysis_id)
    rows = session.exec(q.order_by(AuditEntry.seq.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [
        AuditEntryOut(
            seq=e.seq or 0, ts=e.ts, actor=e.actor, action=e.action, analysis_id=e.analysis_id,
            detail=json.loads(e.detail_json), payload_hash=e.payload_hash, prev_hash=e.prev_hash, entry_hash=e.entry_hash,
        )
        for e in rows
    ]


@router.get("/audit/verify", response_model=AuditVerifyResult)
def verify_audit(session: Session = Depends(get_session)):
    valid, broken_at = audit.verify_chain(session)
    count = session.exec(select(func.count()).select_from(AuditEntry)).one()
    return AuditVerifyResult(valid=valid, broken_at=broken_at, entries=count)


@router.get("/stats")
def console_stats(session: Session = Depends(get_session)):
    return workflow.stats(session)


@router.delete("/analyses")
def purge_all_demo_data(session: Session = Depends(get_session)):
    """Privacy Center: purge every analysis (hash-only tombstones remain, each purge is audited)."""
    return {"purged": workflow.purge_all(session)}


@router.get("/privacy/manifest")
def privacy_manifest():
    hours = get_settings().audio_retention_hours
    return {
        "synthetic_data_notice": "All data in this prototype is synthetic. Do not upload real customer calls.",
        "collected": [
            {"item": "Call audio", "why": "Analysed in memory for voice authenticity and transcription", "retention": f"Deleted after analysis. Optional opt-in retention: encrypted, {hours} h, then swept."},
            {"item": "Redacted transcript", "why": "Scam-language analysis and explanation", "retention": "Stored until purged. Phone/account/card numbers, OTP-like codes, Aadhaar, PAN, UPI IDs and emails are redacted before storage."},
            {"item": "Signal scores, rules and reasons", "why": "Explainability and review", "retention": "Stored until purged"},
            {"item": "SHA-256 hashes of audio and analysis", "why": "Tamper-evident evidence", "retention": "Kept, including in the tombstone after a purge"},
            {"item": "Audit log entries (actor, action, ids, outcomes)", "why": "Hash-chained accountability", "retention": "Kept; contains no transcripts or personal data"},
            {"item": "Verification and review records", "why": "Decision trail", "retention": "Kept; analyst notes stay with the review item"},
        ],
        "never_collected": [
            "Voiceprints or speaker embeddings of callers",
            "Raw (unredacted) transcripts on disk",
            "Real phone numbers, account numbers or card numbers",
            "Anything sent to an external service at runtime (only optional first-time model downloads)",
        ],
        "purge": "DELETE /api/analyses/{id} removes audio, transcript, segments and signals, keeps a hash-only tombstone and writes an audit entry.",
        "disclaimers": [
            "Prototype with synthetic data; not production-grade banking security.",
            "Scores are risk indicators, not proof. The system never labels a person a fraudster.",
            "The voice model is not validated on Indian telephony audio.",
        ],
    }
