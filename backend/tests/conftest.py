import os

# Integration tests run with every ML engine forced into its deterministic fallback (SPEC section O).
# Override with VG_FORCE_FALLBACK=0 to exercise the real models.
os.environ.setdefault("VG_FORCE_FALLBACK", "1")

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VG_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    import app.db as db
    from app.services import model_registry

    monkeypatch.setattr(model_registry, "start_warmup", lambda: None)  # never download models in tests
    db._engine = None
    from app.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    get_settings.cache_clear()
