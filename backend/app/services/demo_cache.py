"""Demo-safe mode (SPEC section R, last resort): replay a scenario result that a previous REAL run produced.

Only runs where ASR and the voice model were both real are cached, keyed by scenario and audio hash, so
changing the audio invalidates the cache. A replay is always labelled CACHED (signal and component sources
become "cached", with the original run time). Nothing is ever fabricated: with no cache entry the real
pipeline runs instead.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from app.config import get_settings
from app.models.schemas import AnalysisResponse, ComponentInfo

log = logging.getLogger("vaaniguard.cache")
_enabled: bool | None = None


def enabled() -> bool:
    return get_settings().demo_safe if _enabled is None else _enabled


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = value


def _path(scenario_id: str):
    d = get_settings().data_dir / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scenario_id}.json"


def is_real_run(res: AnalysisResponse) -> bool:
    return res.components["asr"].source == "model" and res.components["voice"].source == "model"


def save(scenario_id: str, audio_sha256: str, res: AnalysisResponse) -> None:
    if not is_real_run(res):
        return
    try:
        payload = {"audio_sha256": audio_sha256, "cached_at": datetime.now(timezone.utc).isoformat(), "response": res.model_dump(mode="json")}
        _path(scenario_id).write_text(json.dumps(payload), encoding="utf-8")
    except Exception as exc:
        log.warning("cache_write_failed", extra={"fields": {"type": type(exc).__name__}})


def replay(scenario_id: str, audio_sha256: str) -> AnalysisResponse | None:
    """Return a labelled copy of the last real run for this scenario and audio, or None."""
    try:
        data = json.loads(_path(scenario_id).read_text(encoding="utf-8"))
        if data["audio_sha256"] != audio_sha256:
            return None
        res = AnalysisResponse.model_validate(data["response"])
    except Exception:
        return None
    when = data["cached_at"]
    res.id = uuid.uuid4().hex[:12]
    for s in res.signals:
        s.source = "cached"
    note = f"CACHED RESULT from a real run at {when}"
    res.components = {k: ComponentInfo(source="cached", note=f"{note} (original source: {v.source})") for k, v in res.components.items()}
    res.components["cache"] = ComponentInfo(source="cached", note=note)
    return res
