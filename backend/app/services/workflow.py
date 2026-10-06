"""Persistence and workflow for analyses: save, load, verification, review, purge (SPEC sections G, H, N).

Every state change writes an audit entry. Only redacted content is stored. If the database is
unavailable at save time the analysis is still returned and held in memory for the session
(SPEC section R); workflow endpoints that need the database then return an error.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.schemas import AnalysisResponse, AnalysisSummary, ComponentInfo, RuleTriggered
from app.models.tables import Analysis, ReviewItem, Verification
from app.services import audit, retention
from app.services.evidence import hash_json, sha256_hex
from app.services.verification import apply_outcome

log = logging.getLogger("vaaniguard.workflow")

# In-memory fallback when the database cannot be written (session only; never retains audio).
_mem: dict[str, AnalysisResponse] = {}

INSTRUCTIONS: dict[str, str] = {
    "in_app_warning": "Show the user an in-app warning that this call may be unsafe. They may proceed; the choice is logged.",
    "codeword": "Ask for the pre-agreed codeword through a separate, trusted channel. Never ask over the suspect call.",
    "out_of_band_device_confirm": "Send a confirmation prompt to the claimed person's registered device (not the incoming call).",
    "independent_callback": "Call the number on file in the directory. Never use the number that called you.",
    "dynamic_challenge": "Ask a question about recent shared context, via an out-of-band channel, that only the real person would know.",
    "trusted_contact": "Call the trusted contact on their saved number and confirm the person is safe.",
    "second_approver": "A second authorised approver must independently review and approve this transaction.",
    "manual_security_review": "Send to the security analyst review queue for a human decision.",
    "cooling_off_hold": "Hold the transaction for a timed cooling-off period (e.g. 30 minutes) before it can proceed.",
    "end_call_and_call_official_number": "End this call. Your bank will never ask for OTP/PIN. Call the number on your card or the official app, and report to 1930 / cybercrime.gov.in.",
}


class NotFound(Exception):
    pass


class Purged(Exception):
    pass


class Conflict(Exception):
    def __init__(self, code: str, message: str, hint: str):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


def _initial_status(res: AnalysisResponse) -> str:
    return {"LOW": "analyzed", "MEDIUM": "analyzed", "HIGH": "held", "CRITICAL": "in_review"}[res.tier]


def _row_from(res: AnalysisResponse) -> Analysis:
    return Analysis(
        id=res.id,
        created_at=res.created_at or datetime.now(timezone.utc),
        scenario_id=res.scenario_id,
        is_synthetic=res.is_synthetic,
        audio_sha256=res.audio_sha256 or "",
        audio_retained=res.audio_retained,
        audio_expires_at=res.audio_expires_at,
        language=res.language,
        transcript_redacted=res.transcript_redacted,
        signals_json=json.dumps([s.model_dump(mode="json") for s in res.signals]),
        rules_triggered_json=json.dumps([r.model_dump() for r in res.rules_triggered]),
        segments_json=json.dumps([s.model_dump() for s in res.segments]),
        score=res.score,
        tier=res.tier,
        coverage=res.coverage,
        explanation_json=res.model_dump_json(),
        status=res.status,
    )


def save_new(session: Session | None, res: AnalysisResponse, audio: bytes, scenario_id: str | None, retain: bool) -> AnalysisResponse:
    """Stamp evidence fields, persist, write the audit entry, and create a review item for CRITICAL."""
    res.created_at = datetime.now(timezone.utc)
    res.scenario_id = scenario_id
    res.audio_sha256 = sha256_hex(audio)
    res.status = _initial_status(res)  # type: ignore[assignment]
    res.analysis_sha256 = hash_json(res.model_dump(mode="json", exclude={"analysis_sha256", "audio_expires_at"}))
    try:
        if retain:
            res.audio_expires_at = retention.store_audio(res.id, audio)
            res.audio_retained = True
        if session is None:
            raise RuntimeError("no session")
        session.add(_row_from(res))
        session.commit()
        if res.tier == "CRITICAL":
            item = ReviewItem(id=uuid.uuid4().hex[:12], analysis_id=res.id, priority=res.score)
            session.add(item)
            session.commit()
            res.review_id = item.id
            _save(session, res)
        audit.append_entry(session, "system", "analysis_created", res.id, {"tier": res.tier, "score": res.score, "scenario": scenario_id, "audio_retained": res.audio_retained})
    except Exception as exc:
        log.error("persist_failed", extra={"fields": {"analysis_id": res.id, "type": type(exc).__name__}})
        _mem[res.id] = res
        res.components["store"] = ComponentInfo(source="fallback", note="Database unavailable: this result is held in memory for the session only.")
    return res


def _save(session: Session, res: AnalysisResponse) -> None:
    row = session.get(Analysis, res.id)
    if row is None:
        raise NotFound(res.id)
    row.score, row.tier, row.status, row.coverage = res.score, res.tier, res.status, res.coverage
    row.audio_retained, row.audio_expires_at = res.audio_retained, res.audio_expires_at
    row.rules_triggered_json = json.dumps([r.model_dump() for r in res.rules_triggered])
    row.explanation_json = res.model_dump_json()
    session.add(row)
    session.commit()


def get_analysis(session: Session, analysis_id: str) -> AnalysisResponse:
    row = session.get(Analysis, analysis_id)
    if row is None:
        if analysis_id in _mem:
            return _mem[analysis_id]
        raise NotFound(analysis_id)
    expl = json.loads(row.explanation_json or "{}")
    if expl.get("purged"):
        raise Purged(analysis_id)
    return AnalysisResponse.model_validate(expl)


def list_analyses(session: Session, limit: int = 50) -> list[AnalysisSummary]:
    rows = session.exec(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return [
        AnalysisSummary(
            id=r.id, created_at=r.created_at, scenario_id=r.scenario_id, score=r.score, tier=r.tier,  # type: ignore[arg-type]
            status=r.status, coverage=r.coverage, purged=bool(json.loads(r.explanation_json or "{}").get("purged")),  # type: ignore[arg-type]
        )
        for r in rows
    ]


def purge(session: Session, analysis_id: str, actor: str = "user") -> None:
    """Delete audio, transcript, segments and signals; keep a hash-only tombstone and audit the purge."""
    row = session.get(Analysis, analysis_id)
    if row is None:
        if _mem.pop(analysis_id, None) is None:
            raise NotFound(analysis_id)
        return
    prior = json.loads(row.explanation_json or "{}")
    retention.delete_audio(analysis_id)
    if prior.get("purged"):
        return  # idempotent
    row.transcript_redacted, row.signals_json, row.segments_json, row.rules_triggered_json = "", "[]", "[]", "[]"
    row.explanation_json = json.dumps({"purged": True, "purged_at": datetime.now(timezone.utc).isoformat(), "analysis_sha256": prior.get("analysis_sha256")})
    row.audio_retained, row.audio_expires_at, row.status = False, None, "closed"
    session.add(row)
    session.commit()
    audit.append_entry(session, actor, "analysis_purged", analysis_id, {"audio_sha256": row.audio_sha256, "analysis_sha256": prior.get("analysis_sha256")})


# --- verification ---


def start_verification(session: Session, analysis_id: str, actor: str = "user") -> tuple[Verification, AnalysisResponse]:
    res = get_analysis(session, analysis_id)
    if res.status in ("released", "blocked", "closed"):
        raise Conflict("analysis_finalised", f"This analysis is already {res.status}.", "Run a new analysis to verify another interaction.")
    if res.tier == "LOW" or not res.recommended_action.methods:
        raise Conflict("no_verification_needed", "Low-risk interactions need no verification.", "Nothing to do; the interaction is logged.")
    if res.verification_id:
        existing = session.get(Verification, res.verification_id)
        if existing and existing.outcome == "pending":
            return existing, res
    v = Verification(
        id=uuid.uuid4().hex[:12],
        analysis_id=analysis_id,
        methods_json=json.dumps(res.recommended_action.methods),
        reason=res.recommended_action.why,
        actor=actor,
    )
    session.add(v)
    session.commit()
    res.verification_id = v.id
    if res.status != "in_review":
        res.status = "verifying"
    _save(session, res)
    audit.append_entry(session, actor, "verification_started", analysis_id, {"verification_id": v.id, "methods": res.recommended_action.methods, "tier": res.tier})
    return v, res


def _ensure_review(session: Session, res: AnalysisResponse) -> None:
    if res.review_id:
        return
    item = ReviewItem(id=uuid.uuid4().hex[:12], analysis_id=res.id, priority=res.score)
    session.add(item)
    session.commit()
    res.review_id = item.id


def complete_verification(session: Session, verification_id: str, outcome: str, actor: str) -> AnalysisResponse:
    v = session.get(Verification, verification_id)
    if v is None:
        raise NotFound(verification_id)
    if v.outcome != "pending":
        raise Conflict("verification_completed", f"This verification is already '{v.outcome}'.", "Start a new verification from the analysis if needed.")
    res = get_analysis(session, v.analysis_id)
    old_score, old_tier = res.score, res.tier
    new_score, new_tier, txn = apply_outcome(res.score, res.tier, outcome)  # type: ignore[arg-type]

    effect = {"pass": f"{new_score - old_score:+d}", "fail": "CRITICAL", "no_response": "escalated one tier"}[outcome]
    reason = {
        "pass": "Independent verification passed; the score is reduced but the record is retained.",
        "fail": "Verification failed: the person did not confirm. The transaction is blocked and the evidence package is available.",
        "no_response": "No response to verification: the transaction stays held and risk escalates one tier.",
    }[outcome]
    res.rules_triggered.append(RuleTriggered(id=f"VERIFY_{outcome.upper()}", effect=effect, reason=reason))
    res.reasons.insert(0, reason)
    res.score, res.tier = new_score, new_tier
    res.recommended_action.tier, res.recommended_action.transaction_state = new_tier, txn
    res.status = {"pass": "released", "fail": "blocked", "no_response": "in_review" if new_tier == "CRITICAL" else "held"}[outcome]  # type: ignore[assignment]
    if new_tier == "CRITICAL" and outcome != "pass":
        _ensure_review(session, res)

    v.outcome, v.actor, v.completed_at = outcome, actor, datetime.now(timezone.utc)
    session.add(v)
    session.commit()
    _save(session, res)
    audit.append_entry(session, actor, "verification_completed", res.id, {"verification_id": v.id, "outcome": outcome, "score": f"{old_score}->{new_score}", "tier": f"{old_tier}->{new_tier}", "transaction": txn})
    return res


# --- review ---


def review_queue(session: Session, include_decided: bool = False) -> list[dict]:
    q = select(ReviewItem)
    if not include_decided:
        q = q.where(ReviewItem.decision.in_(["pending", "escalate"]))  # type: ignore[attr-defined]
    items = session.exec(q.order_by(ReviewItem.priority.desc(), ReviewItem.id)).all()  # type: ignore[attr-defined]
    out = []
    for it in items:
        row = session.get(Analysis, it.analysis_id)
        expl = json.loads(row.explanation_json or "{}") if row else {}
        if expl.get("purged"):
            continue
        txn = expl.get("transaction") or {}
        out.append({
            **it.model_dump(),
            "score": row.score if row else None,
            "tier": row.tier if row else None,
            "status": row.status if row else None,
            "claimed_identity": expl.get("claimed_identity"),
            "amount_inr": txn.get("amount_inr"),
            "scenario_id": row.scenario_id if row else None,
        })
    return out


def decide_review(session: Session, review_id: str, decision: str, note: str, actor: str = "analyst") -> tuple[ReviewItem, AnalysisResponse]:
    item = session.get(ReviewItem, review_id)
    if item is None:
        raise NotFound(review_id)
    if item.decision in ("approve", "reject"):
        raise Conflict("review_decided", f"This item was already decided: {item.decision}.", "Decisions are final; see the audit log.")
    if not note.strip():
        raise Conflict("note_required", "An analyst note is required.", "Explain the decision in the note field.")
    res = get_analysis(session, item.analysis_id)
    item.decision, item.analyst_note, item.decided_at = decision, note.strip(), datetime.now(timezone.utc)
    session.add(item)
    if decision == "approve":
        res.status, res.recommended_action.transaction_state = "closed", "released"
    elif decision == "reject":
        res.status, res.recommended_action.transaction_state = "closed", "blocked"
    else:
        res.status = "in_review"
    session.commit()
    _save(session, res)
    audit.append_entry(session, actor, f"review_{decision}", res.id, {"review_id": item.id, "note_length": len(note.strip())})
    return item, res
