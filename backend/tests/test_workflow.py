"""Persistence, verification re-scoring, review queue, purge, retention, audit and report (Phase 3)."""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

S1 = "s1_legit_bank_call"
S3 = "s3_cloned_md_vendor_transfer"
S5 = "s5_detector_evading_clone"


def run(client, sid):
    r = client.post(f"/api/scenarios/{sid}/run")
    assert r.status_code == 200
    return r.json()


def test_analysis_is_persisted_and_fetchable(client):
    a = run(client, S3)
    assert a["status"] == "in_review" and a["review_id"] and a["scenario_id"] == S3
    assert len(a["audio_sha256"]) == 64 and len(a["analysis_sha256"]) == 64
    got = client.get(f"/api/analyses/{a['id']}").json()
    assert got["score"] == a["score"] and got["transcript_redacted"] == a["transcript_redacted"]
    listing = client.get("/api/analyses?limit=5").json()
    assert listing[0]["id"] == a["id"] and listing[0]["tier"] == "CRITICAL"


def test_unknown_analysis_is_404(client):
    r = client.get("/api/analyses/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_low_risk_needs_no_verification(client):
    a = run(client, S1)
    assert a["status"] == "analyzed" and a["review_id"] is None
    r = client.post(f"/api/analyses/{a['id']}/verification")
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_verification_needed"


def test_verification_fail_blocks_and_is_audited(client):
    a = run(client, S3)
    v = client.post(f"/api/analyses/{a['id']}/verification").json()
    assert "independent_callback" in v["methods"] and set(v["methods"]) == set(v["instructions"])
    again = client.post(f"/api/analyses/{a['id']}/verification").json()
    assert again["verification_id"] == v["verification_id"]  # idempotent while pending
    r = client.post(f"/api/verifications/{v['verification_id']}/complete", json={"outcome": "fail", "actor": "rakesh"})
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "blocked" and b["tier"] == "CRITICAL"
    assert b["recommended_action"]["transaction_state"] == "blocked"
    assert any(x["id"] == "VERIFY_FAIL" for x in b["rules_triggered"])
    # cannot complete twice
    r2 = client.post(f"/api/verifications/{v['verification_id']}/complete", json={"outcome": "pass", "actor": "x"})
    assert r2.status_code == 409
    audit = client.get(f"/api/audit?analysis_id={a['id']}").json()
    assert [e["action"] for e in reversed(audit)] == ["analysis_created", "verification_started", "verification_completed"]
    assert client.get("/api/audit/verify").json()["valid"] is True


def test_verification_pass_lowers_score_and_releases(client):
    a = run(client, S5)  # HIGH, held
    assert a["status"] == "held"
    v = client.post(f"/api/analyses/{a['id']}/verification").json()
    b = client.post(f"/api/verifications/{v['verification_id']}/complete", json={"outcome": "pass", "actor": "user"}).json()
    assert b["status"] == "released" and b["score"] < a["score"]
    assert b["score"] == min(a["score"], max(a["score"] - 35, 59))  # -35, floored at HIGH minimum - 1
    assert any(x["id"] == "VERIFY_PASS" for x in b["rules_triggered"])
    assert b["recommended_action"]["transaction_state"] == "released"


def test_no_response_escalates_one_tier(client):
    a = run(client, S5)
    assert a["tier"] == "HIGH"
    v = client.post(f"/api/analyses/{a['id']}/verification").json()
    b = client.post(f"/api/verifications/{v['verification_id']}/complete", json={"outcome": "no_response", "actor": "user"}).json()
    assert b["tier"] == "CRITICAL" and b["recommended_action"]["transaction_state"] == "held"
    assert b["review_id"]  # now needs review
    queue = client.get("/api/review-queue").json()
    assert any(i["analysis_id"] == a["id"] for i in queue)


def test_review_queue_requires_note_and_is_final(client):
    a = run(client, S3)
    queue = client.get("/api/review-queue").json()
    item = next(i for i in queue if i["analysis_id"] == a["id"])
    assert item["tier"] == "CRITICAL" and item["amount_inr"]
    assert client.post(f"/api/review/{item['id']}/decision", json={"decision": "reject", "note": ""}).status_code == 422
    assert client.post(f"/api/review/{item['id']}/decision", json={"decision": "reject", "note": "   "}).status_code == 422
    ok = client.post(f"/api/review/{item['id']}/decision", json={"decision": "reject", "note": "MD confirmed he did not call"})
    assert ok.status_code == 200 and ok.json()["recommended_action"]["transaction_state"] == "blocked"
    assert all(i["id"] != item["id"] for i in client.get("/api/review-queue").json())
    assert client.post(f"/api/review/{item['id']}/decision", json={"decision": "approve", "note": "changed my mind"}).status_code == 409
    audit = client.get(f"/api/audit?analysis_id={a['id']}").json()
    assert "review_reject" in [e["action"] for e in audit]
    assert "MD confirmed" not in str(audit)  # notes are not copied into the audit log


def test_purge_keeps_tombstone_and_audits(client):
    a = run(client, S3)
    assert client.delete(f"/api/analyses/{a['id']}").status_code == 204
    r = client.get(f"/api/analyses/{a['id']}")
    assert r.status_code == 410
    assert client.get(f"/api/analyses/{a['id']}/audio").status_code == 410
    summary = next(s for s in client.get("/api/analyses").json() if s["id"] == a["id"])
    assert summary["purged"] is True
    actions = [e["action"] for e in client.get(f"/api/audit?analysis_id={a['id']}").json()]
    assert "analysis_purged" in actions
    assert client.delete(f"/api/analyses/{a['id']}").status_code == 204  # idempotent
    assert client.get("/api/audit/verify").json()["valid"] is True
    assert client.delete("/api/analyses/doesnotexist").status_code == 404
    # purged items leave the review queue
    assert all(i["analysis_id"] != a["id"] for i in client.get("/api/review-queue").json())


def test_report_json_and_html(client):
    a = run(client, S3)
    rep = client.get(f"/api/analyses/{a['id']}/report").json()
    assert rep["hashes"]["audio_sha256"] == a["audio_sha256"]
    assert rep["audit_chain"]["valid"] is True and rep["audit_trail"][0]["action"] == "analysis_created"
    html = client.get(f"/api/analyses/{a['id']}/report?format=html")
    assert html.status_code == 200 and "SYNTHETIC DEMO DATA" in html.text
    assert client.get(f"/api/analyses/{a['id']}/report?format=xml").status_code == 422


def test_audit_tamper_detected_via_api(client):
    import app.db as db
    from app.models.tables import AuditEntry

    run(client, S3)
    run(client, S1)
    with Session(db.get_engine()) as s:
        e = s.get(AuditEntry, 1)
        e.actor = "mallory"
        s.add(e)
        s.commit()
    r = client.get("/api/audit/verify").json()
    assert r["valid"] is False and r["broken_at"] == 1


def test_audio_not_retained_by_default_and_no_files_left(client):
    import app.db as db  # noqa: F401
    from app.config import get_settings

    a = run(client, S1)
    assert a["audio_retained"] is False
    assert client.get(f"/api/analyses/{a['id']}/audio").status_code == 410
    audio_dir = get_settings().data_dir / "audio"
    assert not audio_dir.exists() or not list(audio_dir.iterdir())


def _upload(client, retain):
    from app.services.scenarios import get_scenario

    data = get_scenario(S1).audio_path.read_bytes()
    return client.post("/api/analyses", files={"audio": ("a.wav", data, "audio/wav")}, data={"retain_audio": "true" if retain else "false"})


def test_retained_audio_is_encrypted_expires_and_is_swept(client):
    import app.db as db
    from app.config import get_settings
    from app.models.tables import Analysis
    from app.services import retention

    r = _upload(client, retain=True)
    assert r.status_code == 200
    a = r.json()
    assert a["audio_retained"] is True and a["audio_expires_at"]
    enc = get_settings().data_dir / "audio" / f"{a['id']}.enc"
    assert enc.exists() and enc.read_bytes()[:4] != b"RIFF"  # ciphertext, not WAV
    got = client.get(f"/api/analyses/{a['id']}/audio")
    assert got.status_code == 200 and got.content[:4] == b"RIFF"

    with Session(db.get_engine()) as s:  # force expiry
        row = s.get(Analysis, a["id"])
        row.audio_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        s.add(row)
        s.commit()
        assert retention.sweep_expired(s) == 1
    assert not enc.exists()
    assert client.get(f"/api/analyses/{a['id']}/audio").status_code == 410


def test_purge_deletes_retained_audio(client):
    from app.config import get_settings

    a = _upload(client, retain=True).json()
    enc = get_settings().data_dir / "audio" / f"{a['id']}.enc"
    assert enc.exists()
    client.delete(f"/api/analyses/{a['id']}")
    assert not enc.exists()


def test_privacy_manifest(client):
    m = client.get("/api/privacy/manifest").json()
    assert m["collected"] and m["never_collected"] and "tombstone" in m["purge"]


def test_analysis_survives_database_failure(client, monkeypatch):
    from app.services import audit

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(audit, "append_entry", boom)
    a = run(client, S1)
    assert a["components"]["store"]["source"] == "fallback"
    assert client.get(f"/api/analyses/{a['id']}").status_code == 200  # served from the in-memory fallback


def test_init_db_adds_columns_missing_from_an_older_database(tmp_path, monkeypatch):
    import sqlite3

    from app.config import get_settings

    monkeypatch.setenv("VG_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    import app.db as db

    db._engine = None
    con = sqlite3.connect(tmp_path / "vaaniguard.db")  # Phase 1 audit table: no detail_json
    con.execute("CREATE TABLE auditentry (seq INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT, analysis_id TEXT, payload_hash TEXT, prev_hash TEXT, entry_hash TEXT)")
    con.commit()
    con.close()
    db.init_db()
    cols = {r[1] for r in sqlite3.connect(tmp_path / "vaaniguard.db").execute("pragma table_info(auditentry)")}
    assert "detail_json" in cols
    db._engine = None
    get_settings.cache_clear()
