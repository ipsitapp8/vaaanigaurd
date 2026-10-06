"""faster-whisper ASR (int8 CPU). Raises AsrUnavailable when the model cannot be used; the pipeline
then falls back to a scenario's sidecar transcript or returns a partial analysis (SPEC section R)."""
from dataclasses import dataclass

import numpy as np

from app.services import model_registry


class AsrUnavailable(Exception):
    pass


@dataclass
class AsrSegment:
    start: float
    end: float
    text: str


@dataclass
class AsrResult:
    segments: list[AsrSegment]
    language: str | None
    source: str  # "model" | "fallback"
    note: str | None = None


def transcribe(samples: np.ndarray, sample_rate: int = 16000) -> AsrResult:
    model = model_registry.get_model("asr")
    if model is None:
        raise AsrUnavailable("ASR model not available")
    segments, info = model.transcribe(samples, vad_filter=True, beam_size=1, condition_on_previous_text=False)
    out = [AsrSegment(s.start, s.end, s.text.strip()) for s in segments if s.text.strip()]
    return AsrResult(segments=out, language=info.language, source="model")
