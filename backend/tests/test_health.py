from app.config import get_settings


def test_health_reports_db_and_creates_file(client, tmp_path):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["device"] == "cpu"
    assert body["components"]["db"] == "loaded"
    assert (tmp_path / "vaaniguard.db").exists()


def test_force_fallback_marks_ml_components_fallback(client):
    body = client.get("/api/health").json()
    assert body["force_fallback"] is True
    for k in ("asr", "deepfake_model", "speaker", "zero_shot"):
        assert body["components"][k] == "fallback"


def test_ml_components_not_loaded_without_force_fallback(client, monkeypatch):
    monkeypatch.setenv("VG_FORCE_FALLBACK", "0")
    get_settings.cache_clear()
    from app.services import model_registry

    monkeypatch.setattr(model_registry, "_status", {})
    body = client.get("/api/health").json()
    assert body["force_fallback"] is False
    assert body["components"]["asr"] == "not_loaded"


def test_unavailable_asr_is_reported(client, monkeypatch):
    monkeypatch.setenv("VG_FORCE_FALLBACK", "0")
    get_settings.cache_clear()
    from app.services import model_registry

    monkeypatch.setattr(model_registry, "_status", {"asr": "unavailable"})
    assert client.get("/api/health").json()["components"]["asr"] == "unavailable"


def test_risk_config_loads():
    from app.config import load_risk_config

    cfg = load_risk_config()
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert cfg["tiers"] == {"LOW": 0, "MEDIUM": 30, "HIGH": 60, "CRITICAL": 80}
