"""Lazy model loading, timeouts and status reporting (SPEC sections K, R).

Phase 1: no models exist yet, so every ML component reports `not_loaded`
(or `fallback` when VG_FORCE_FALLBACK=1). Later phases register loaders here.
"""
from app.config import get_settings
from app.db import db_ok
from app.models.schemas import ComponentStatus, HealthComponents

ML_COMPONENTS = ("asr", "deepfake_model", "speaker", "zero_shot")


def component_status(name: str) -> ComponentStatus:
    if get_settings().force_fallback:
        return "fallback"
    return "not_loaded"


def get_device() -> str:
    return "cpu"  # CPU-only target; CUDA detection arrives with torch


def health_components() -> HealthComponents:
    return HealthComponents(
        **{n: component_status(n) for n in ML_COMPONENTS},
        db="loaded" if db_ok() else "unavailable",
    )
