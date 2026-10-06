"""faster-whisper ASR (int8 CPU) with sidecar-transcript fallback. Phase 2."""
from dataclasses import dataclass


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


def transcribe(samples, sample_rate: int = 16000) -> AsrResult:
    raise NotImplementedError
