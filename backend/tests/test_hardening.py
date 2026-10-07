"""Hardened-mode threshold jitter and demo-safe cached replay."""
import pytest

from app.config import get_settings
from app.models.schemas import AnalysisResponse
from app.services import demo_cache, fusion

S3 = "s3_cloned_md_vendor_transfer"


@pytest.fixture(autouse=True)
def _reset():
    demo_cache.set_enabled(False)
    fusion.reset_jitter()
    yield
    demo_cache.set_enabled(False)
    fusion.reset_jitter()
    get_settings.cache_clear()


def test_jitter_is_off_by_default():
    assert [fusion.tier_for(s) for s in (29, 30, 59, 60, 79, 80)] == ["LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "CRITICAL"]


def test_hardened_jitter_shifts_bounds_within_range_and_is_stable(monkeypatch):
    monkeypatch.setenv("VG_HARDENED_MODE", "1")
    get_settings.cache_clear()
    base = {"LOW": 0, "MEDIUM": 30, "HIGH": 60, "CRITICAL": 80}
    seen = set()
    for _ in range(40):
        fusion.reset_jitter()
        b = {t: fusion.tier_min(t) for t in base}
        assert b["LOW"] == 0
        assert all(abs(b[t] - base[t]) <= 3 for t in base)
        assert b["MEDIUM"] < b["HIGH"] < b["CRITICAL"]
        assert b == {t: fusion.tier_min(t) for t in base}  # fixed for the session
        assert fusion.tier_for(b["HIGH"]) == "HIGH" and fusion.tier_for(b["HIGH"] - 1) == "MEDIUM"
        seen.add(tuple(b.values()))
    assert len(seen) > 1  # actually random across sessions


def test_fallback_runs_are_never_cached(client, tmp_path):
    client.post(f"/api/scenarios/{S3}/run")
    assert not (get_settings().data_dir / "cache" / f"{S3}.json").exists()


def test_demo_safe_replays_a_labelled_real_run(client):
    first = AnalysisResponse.model_validate(client.post(f"/api/scenarios/{S3}/run").json())
    for k in ("asr", "voice"):  # pretend this was a real-model run so it is eligible for the cache
        first.components[k].source = "model"
    from app.services.evidence import sha256_hex
    from app.services.scenarios import get_scenario

    demo_cache.save(S3, sha256_hex(get_scenario(S3).audio_path.read_bytes()), first)

    assert client.put("/api/demo-safe", json={"enabled": True}).json() == {"enabled": True}
    assert client.get("/api/health").json()["demo_safe"] is True
    again = client.post(f"/api/scenarios/{S3}/run").json()
    assert again["id"] != first.id and again["score"] == first.score and again["tier"] == first.tier
    assert all(s["source"] == "cached" for s in again["signals"])
    assert "CACHED RESULT" in again["components"]["cache"]["note"]
    # still a normal persisted analysis: workflow endpoints work on it
    assert client.get(f"/api/analyses/{again['id']}").status_code == 200
    assert client.post(f"/api/analyses/{again['id']}/verification").status_code == 200


def test_demo_safe_without_cache_runs_the_real_pipeline(client):
    client.put("/api/demo-safe", json={"enabled": True})
    body = client.post("/api/scenarios/s1_legit_bank_call/run").json()
    assert "cache" not in body["components"] and all(s["source"] != "cached" for s in body["signals"])
