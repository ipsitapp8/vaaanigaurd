import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VG_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    import app.db as db

    db._engine = None
    from app.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    get_settings.cache_clear()


def test_health_reports_components_and_creates_db(client, tmp_path):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["components"]["db"] == "loaded"
    assert body["components"]["asr"] == "not_loaded"
    assert (tmp_path / "vaaniguard.db").exists()


def test_force_fallback_reported(client, monkeypatch):
    monkeypatch.setenv("VG_FORCE_FALLBACK", "1")
    get_settings.cache_clear()
    body = client.get("/api/health").json()
    assert body["components"]["deepfake_model"] == "fallback"
    assert body["force_fallback"] is True


def test_risk_config_loads():
    from app.config import load_risk_config

    cfg = load_risk_config()
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert cfg["tiers"] == {"LOW": 0, "MEDIUM": 30, "HIGH": 60, "CRITICAL": 80}