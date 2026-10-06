"""SHA-256 hashing and the evidence report (SPEC sections I, N)."""
import hashlib
import html
import json

from sqlmodel import Session, select

from app.models.tables import AuditEntry, ReviewItem, Verification


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> str:
    """Stable serialization so the same content always hashes the same."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def hash_json(obj) -> str:
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def build_report(session: Session, res) -> dict:
    """Evidence package: redacted analysis, hashes, verification/review records and its audit trail."""
    from app.services import audit  # noqa: PLC0415  (audit imports this module for hashing)

    analysis = res.model_dump(mode="json")
    valid, broken_at = audit.verify_chain(session)
    entries = session.exec(select(AuditEntry).where(AuditEntry.analysis_id == res.id).order_by(AuditEntry.seq)).all()  # type: ignore[arg-type]
    verifications = session.exec(select(Verification).where(Verification.analysis_id == res.id)).all()
    reviews = session.exec(select(ReviewItem).where(ReviewItem.analysis_id == res.id)).all()
    return {
        "report_version": 1,
        "disclaimer": "Prototype. All data is synthetic. Scores are risk indicators, not proof; a human decides on high-impact actions.",
        "analysis": analysis,
        "hashes": {
            "audio_sha256": res.audio_sha256,
            "analysis_sha256_at_creation": res.analysis_sha256,
            "analysis_sha256_now": hash_json({**analysis, "analysis_sha256": None, "audio_expires_at": None}),
        },
        "verifications": [{"id": v.id, "methods": json.loads(v.methods_json), "reason": v.reason, "outcome": v.outcome, "actor": v.actor, "completed_at": v.completed_at} for v in verifications],
        "reviews": [{"id": r.id, "priority": r.priority, "decision": r.decision, "analyst_note": r.analyst_note, "decided_at": r.decided_at} for r in reviews],
        "audit_trail": [{"seq": e.seq, "ts": e.ts, "actor": e.actor, "action": e.action, "detail": json.loads(e.detail_json), "entry_hash": e.entry_hash} for e in entries],
        "audit_chain": {"valid": valid, "broken_at": broken_at},
    }


def report_html(report: dict) -> str:
    """Printable HTML rendering of the report (all values escaped)."""
    a = report["analysis"]
    e = html.escape
    rows = "".join(f"<tr><td>{e(s['name'])}</td><td>{s['score']}</td><td>{s['confidence']}</td><td>{e(s['source'])}</td></tr>" for s in a["signals"])
    rules = "".join(f"<li><b>{e(r['id'])}</b> ({e(r['effect'])}): {e(r['reason'])}</li>" for r in a["rules_triggered"]) or "<li>None</li>"
    reasons = "".join(f"<li>{e(r)}</li>" for r in a["reasons"])
    trail = "".join(f"<tr><td>{t['seq']}</td><td>{e(str(t['ts']))}</td><td>{e(t['actor'])}</td><td>{e(t['action'])}</td></tr>" for t in report["audit_trail"])
    h = report["hashes"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>VaaniGuard evidence {e(a['id'])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #999;padding:4px 8px;text-align:left}}code{{font-size:.8rem;word-break:break-all}}</style></head><body>
<h1>Evidence report {e(a['id'])}</h1><p><b>SYNTHETIC DEMO DATA — prototype.</b> {e(report['disclaimer'])}</p>
<h2>Result</h2><p>Score <b>{a['score']}</b> — tier <b>{e(a['tier'])}</b> — status {e(a['status'])} — coverage {a['coverage']}</p>
<h2>Reasons</h2><ul>{reasons}</ul><h2>Rules triggered</h2><ul>{rules}</ul>
<h2>Signals</h2><table><tr><th>Signal</th><th>Score</th><th>Confidence</th><th>Source</th></tr>{rows}</table>
<h2>Redacted transcript</h2><p>{e(a['transcript_redacted'])}</p>
<h2>Hashes</h2><p>Audio SHA-256<br><code>{e(str(h['audio_sha256']))}</code></p><p>Analysis SHA-256 at creation<br><code>{e(str(h['analysis_sha256_at_creation']))}</code></p>
<h2>Audit trail</h2><table><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th></tr>{trail}</table>
<p>Audit chain valid: <b>{report['audit_chain']['valid']}</b></p></body></html>"""
