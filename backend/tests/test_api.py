import io
import json
import time

import numpy as np
import pytest
import soundfile as sf

from app.config import get_settings
from app.services import model_registry, scenarios
from app.services.audio_io import compute_quality, load_audio

SCENARIO_IDS = list(scenarios.load_scenarios())


def wav_bytes(seconds=3.0, sr=16000, freq=220.0, channels=1) -> bytes:
    t = np.arange(int(seconds * sr)) / sr
    x = 0.3 * np.sin(2 * np.pi * freq * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    if channels == 2:
        x = np.stack([x, x], axis=1)
    buf = io.BytesIO()
    sf.write(buf, x.astype("float32"), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def test_six_scenarios_are_bundled():
    assert len(SCENARIO_IDS) == 6
    for sc in scenarios.load_scenarios().values():
        assert sc.audio_path.exists(), sc.audio
        assert sc.segments and all(s.end > s.start for s in sc.segments)


def test_scenarios_endpoint(client):
    body = client.get("/api/scenarios").json()
    assert len(body) == 6
    assert {"id", "title", "persona", "description", "expected_tier"} <= body[0].keys()


@pytest.mark.parametrize("sid", SCENARIO_IDS)
def test_scenario_hits_expected_tier_in_fallback_mode(client, sid):
    expected = scenarios.get_scenario(sid).expected_tiers
    r = client.post(f"/api/scenarios/{sid}/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tier"] in expected, (sid, body["score"], body["tier"], expected)
    assert body["is_synthetic"] is True
    assert [s["name"] for s in body["signals"]] == ["voice", "scam", "urgency", "financial", "identity", "context"]
    assert body["components"]["asr"]["source"] == "fallback"
    assert body["components"]["asr"]["note"]
    assert len(body["segments"]) == len(scenarios.get_scenario(sid).segments)
    assert abs(sum(body["contributions"].values()) - 100) < 1.0 or body["score"] == 0 or sum(body["contributions"].values()) == 0


def test_voice_falls_back_to_low_confidence_heuristics(client):
    body = client.post("/api/scenarios/s3_cloned_md_vendor_transfer/run").json()
    voice = body["signals"][0]
    assert voice["source"] == "heuristic" and 0 < voice["confidence"] <= 0.4
    assert any(e["kind"] == "voice_model_unavailable" for e in voice["evidence"])
    assert "heuristics only" in body["components"]["voice"]["note"]


def test_s2_triggers_r1_and_special_route(client):
    body = client.post("/api/scenarios/s2_cloned_bank_kyc/run").json()
    assert [r["id"] for r in body["rules_triggered"]][0] == "R1"
    assert body["recommended_action"]["methods"][0] == "end_call_and_call_official_number"
    assert "1930" in body["recommended_action"]["why"]
    assert body["recommended_action"]["transaction_state"] == "held"


def test_s3_hero_flow(client):
    body = client.post("/api/scenarios/s3_cloned_md_vendor_transfer/run").json()
    assert body["tier"] == "CRITICAL"
    m = body["recommended_action"]["methods"]
    assert "independent_callback" in m and "second_approver" in m and "cooling_off_hold" in m  # ₹4.8L >= 1L
    assert body["claimed_identity"].startswith("Rakesh")
    assert any("8.0×" in r for r in body["reasons"])  # context reason cites the amount ratio
    scores = [s["cumulative_score"] for s in body["segments"]]
    assert scores[0] < 30 and scores[-1] == body["score"]
    assert scores == sorted(scores)  # risk only climbs as the call unfolds


def test_s5_detector_independent_r2(client):
    body = client.post("/api/scenarios/s5_detector_evading_clone/run").json()
    assert body["tier"] == "HIGH"
    assert "R2" in [r["id"] for r in body["rules_triggered"]]
    assert body["signals"][0]["confidence"] <= 0.4  # the detector contributes little; R2 decides


def test_s6_low_friction(client):
    body = client.post("/api/scenarios/s6_false_positive_guard/run").json()
    assert body["tier"] in ("LOW", "MEDIUM")
    assert body["recommended_action"]["transaction_state"] in ("released", "pending")
    assert len(body["recommended_action"]["methods"]) <= 2


def test_s1_zero_friction(client):
    body = client.post("/api/scenarios/s1_legit_bank_call/run").json()
    assert body["tier"] == "LOW" and body["recommended_action"]["methods"] == []


def test_highlights_line_up_with_redacted_transcript(client):
    body = client.post("/api/scenarios/s3_cloned_md_vendor_transfer/run").json()
    t = body["transcript_redacted"]
    assert body["highlights"]
    for h in body["highlights"]:
        assert 0 <= h["start_char"] < h["end_char"] <= len(t)
    cats = {h["category"] for h in body["highlights"]}
    assert {"urgency", "process_bypass"} <= cats


def test_unknown_scenario_error_shape(client):
    r = client.post("/api/scenarios/nope/run")
    assert r.status_code == 404
    e = r.json()["error"]
    assert e["code"] == "scenario_not_found" and e["hint"]


# ---- uploads ----
def test_upload_without_transcript_is_a_partial_analysis(client):
    r = client.post("/api/analyses", files={"audio": ("clip.wav", wav_bytes(), "audio/wav")})
    assert r.status_code == 200
    body = r.json()
    assert body["components"]["asr"]["source"] == "fallback"
    assert "partial analysis" in body["components"]["asr"]["note"]
    assert body["coverage"] < 0.5
    assert body["transcript_redacted"] == ""


def test_upload_with_pasted_transcript_scores_and_redacts(client):
    r = client.post(
        "/api/analyses",
        files={"audio": ("clip.wav", wav_bytes(), "audio/wav")},
        data={"transcript": "Abhi turant apna OTP batao, call me on 9876543210"},
    )
    body = r.json()
    assert r.status_code == 200
    assert body["tier"] == "CRITICAL" and body["rules_triggered"][0]["id"] == "R1"
    assert "9876543210" not in body["transcript_redacted"] and "[PHONE]" in body["transcript_redacted"]


def test_upload_with_context_and_metadata(client):
    ctx = {"account_id": "KTX-0001", "amount_inr": 500000, "beneficiary_is_new": True, "beneficiary_age_days": 1, "typical_amount_inr": 50000, "activity_window": [9, 19], "recent_txn_count_1h": 0, "payment_rail": "RTGS"}
    meta = {"caller_number_masked": "+91 9XXXX XX111", "in_directory": False, "directory_name": None, "channel": "whatsapp", "started_at": "2026-10-06T15:00:00"}
    r = client.post(
        "/api/analyses",
        files={"audio": ("clip.wav", wav_bytes(), "audio/wav")},
        data={"context": json.dumps(ctx), "metadata": json.dumps(meta), "transcript": "Priya main Rakesh bol raha hoon, abhi transfer karo, accounts ko mat batana"},
    )
    assert r.status_code == 200
    assert r.json()["transaction"]["amount_inr"] == 500000


@pytest.mark.parametrize("channels,sr", [(2, 16000), (1, 8000), (1, 44100)])
def test_upload_accepts_stereo_and_other_sample_rates(client, channels, sr):
    r = client.post("/api/analyses", files={"audio": ("c.wav", wav_bytes(2.0, sr=sr, channels=channels), "audio/wav")})
    assert r.status_code == 200


def test_upload_rejects_non_audio(client):
    r = client.post("/api/analyses", files={"audio": ("evil.wav", b"this is not audio at all" * 50, "audio/wav")})
    assert r.status_code == 422
    e = r.json()["error"]
    assert e["code"] == "undecodable_audio" and "WAV/MP3/M4A" in e["hint"]


def test_upload_rejects_empty(client):
    r = client.post("/api/analyses", files={"audio": ("e.wav", b"", "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_file"


def test_upload_rejects_too_large(client, monkeypatch):
    monkeypatch.setenv("VG_MAX_AUDIO_BYTES", "1000")
    get_settings.cache_clear()
    r = client.post("/api/analyses", files={"audio": ("big.wav", wav_bytes(3.0), "audio/wav")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_upload_rejects_too_long(client, monkeypatch):
    monkeypatch.setenv("VG_MAX_AUDIO_SECONDS", "2")
    get_settings.cache_clear()
    r = client.post("/api/analyses", files={"audio": ("long.wav", wav_bytes(5.0), "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_too_long"


def test_upload_rejects_too_short(client):
    r = client.post("/api/analyses", files={"audio": ("s.wav", wav_bytes(0.2), "audio/wav")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "audio_too_short"


def test_upload_rejects_bad_context_json(client):
    r = client.post("/api/analyses", files={"audio": ("c.wav", wav_bytes(), "audio/wav")}, data={"context": "{not json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_json"


def test_upload_missing_file_is_validation_error(client):
    r = client.post("/api/analyses")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_m4a_decodes_via_pyav(client):
    av = pytest.importorskip("av")
    buf = io.BytesIO()
    try:
        with av.open(buf, "w", format="mp4") as out:
            stream = out.add_stream("aac", rate=16000)
            stream.layout = "mono"
            samples = (0.3 * np.sin(2 * np.pi * 220 * np.arange(16000 * 2) / 16000)).astype("float32")
            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="flt", layout="mono")
            frame.sample_rate = 16000
            for pkt in stream.encode(frame):
                out.mux(pkt)
            for pkt in stream.encode(None):
                out.mux(pkt)
    except Exception:
        pytest.skip("AAC encoder not available in this PyAV build")
    r = client.post("/api/analyses", files={"audio": ("clip.m4a", buf.getvalue(), "audio/mp4")})
    assert r.status_code == 200


# ---- audio quality / engine robustness ----
def test_quality_detects_telephony_bandwidth():
    s1 = scenarios.get_scenario("s1_legit_bank_call")
    _, _, q1 = load_audio(s1.audio_path.read_bytes())
    assert q1.is_telephony and q1.duration_s > 15
    wide = np.random.default_rng(0).normal(0, 0.1, 16000 * 3).astype("float32")
    assert not compute_quality(wide).is_telephony


def test_quality_snr_orders_clean_above_noisy():
    rng = np.random.default_rng(1)
    t = np.arange(16000 * 4) / 16000
    speechlike = np.sin(2 * np.pi * 200 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
    clean = (0.4 * speechlike + rng.normal(0, 0.001, t.size)).astype("float32")
    noisy = (0.4 * speechlike + rng.normal(0, 0.1, t.size)).astype("float32")
    assert compute_quality(clean).snr_db > compute_quality(noisy).snr_db + 10


def test_engine_timeout_returns_fallback():
    def slow():
        time.sleep(1.0)
        return "late"

    result, ok = model_registry.run_with_timeout(slow, 0.05, fallback=lambda: "fallback")
    assert (result, ok) == ("fallback", False)


def test_engine_error_returns_fallback():
    def boom():
        raise RuntimeError("model exploded")

    assert model_registry.run_with_timeout(boom, 1.0, fallback=lambda: 42) == (42, False)


def test_failed_asr_load_marks_unavailable_and_never_raises(monkeypatch):
    monkeypatch.setenv("VG_FORCE_FALLBACK", "0")
    get_settings.cache_clear()
    monkeypatch.setattr(model_registry, "_models", {})
    monkeypatch.setattr(model_registry, "_status", {})

    def fail():
        raise OSError("no network and no cache")

    monkeypatch.setitem(model_registry._LOADERS, "asr", fail)
    assert model_registry.get_model("asr") is None
    assert model_registry.component_status("asr") == "unavailable"
    assert model_registry.get_model("asr") is None  # does not retry-storm
    get_settings.cache_clear()


def test_request_id_header_and_cors_origin(client):
    r = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["x-request-id"]
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    r2 = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r2.headers


def test_scenario_audio_is_served(client):
    r = client.get("/api/scenarios/s1_legit_bank_call/audio")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert client.get("/api/scenarios/nope/audio").status_code == 404
