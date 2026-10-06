"""Lazy model loading, timeouts and status reporting (SPEC sections K, R).

Registered: ASR (faster-whisper, int8 CPU) and the deepfake model (wav2vec2, registered by voice_auth).
Speaker and zero-shot report `not_loaded` (or `fallback` under VG_FORCE_FALLBACK=1) until built. A failed load marks the component
`unavailable` and never raises into the request path.
"""
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, TypeVar

from app.config import get_settings
from app.db import db_ok
from app.models.schemas import ComponentStatus, HealthComponents

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows without developer mode
log = logging.getLogger("vaaniguard.models")

ML_COMPONENTS = ("asr", "deepfake_model", "speaker", "zero_shot")

_lock = threading.Lock()
_models: dict[str, Any] = {}
_status: dict[str, ComponentStatus] = {}
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="engine")

T = TypeVar("T")


def component_status(name: str) -> ComponentStatus:
    if get_settings().force_fallback:
        return "fallback"
    return _status.get(name, "not_loaded")


def get_device() -> str:
    return "cpu"  # CPU-only target; CUDA detection arrives with torch


def health_components() -> HealthComponents:
    return HealthComponents(
        **{n: component_status(n) for n in ML_COMPONENTS},
        db="loaded" if db_ok() else "unavailable",
    )


def _load_asr():
    from faster_whisper import WhisperModel  # noqa: PLC0415

    s = get_settings()
    return WhisperModel(s.whisper_model, device="cpu", compute_type="int8", cpu_threads=s.asr_threads)


_LOADERS: dict[str, Callable[[], Any]] = {"asr": _load_asr}


def register_loader(name: str, loader: Callable[[], Any]) -> None:
    """Engines register their lazy model loader at import time (e.g. deepfake_model)."""
    _LOADERS[name] = loader


def peek_model(name: str) -> Any | None:
    """Return the model only if it is already loaded; never loads or waits (used on the request path)."""
    if get_settings().force_fallback:
        return None
    return _models.get(name)


def get_model(name: str) -> Any | None:
    """Return the loaded model, loading it on first use. None when forced to fallback or unavailable."""
    if get_settings().force_fallback:
        return None
    with _lock:
        if name in _models:
            return _models[name]
        if _status.get(name) == "unavailable" or name not in _LOADERS:
            return None
        try:
            _models[name] = _LOADERS[name]()
            _status[name] = "loaded"
            log.info("model_loaded", extra={"fields": {"model": name}})
        except Exception as exc:  # download failure, missing cache, etc.
            _status[name] = "unavailable"
            log.error("model_load_failed", extra={"fields": {"model": name, "type": type(exc).__name__}})
            return None
        return _models[name]


def warmup() -> None:
    """Load models in the background at startup so the first request is fast."""
    for name in _LOADERS:
        get_model(name)


def start_warmup() -> threading.Thread:
    t = threading.Thread(target=warmup, name="warmup", daemon=True)
    t.start()
    return t


def run_with_timeout(fn: Callable[[], T], timeout_s: float, fallback: Callable[[], T]) -> tuple[T, bool]:
    """Run fn in the engine pool. On timeout or error return (fallback(), False); else (result, True)."""
    fut = _pool.submit(fn)
    try:
        return fut.result(timeout=timeout_s), True
    except (FutureTimeout, Exception) as exc:
        log.warning("engine_fallback", extra={"fields": {"type": type(exc).__name__}})
        return fallback(), False
