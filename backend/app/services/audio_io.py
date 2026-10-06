"""Validate (size <=10MB, <=120s, decodable), decode via soundfile/ffmpeg, resample to 16 kHz mono,
compute quality metrics (SNR, bandwidth, clipping, duration). Phase 2."""
from dataclasses import dataclass


@dataclass
class AudioQuality:
    duration_s: float
    snr_db: float
    bandwidth_hz: float
    clipping_ratio: float


def load_audio(data: bytes, filename: str | None = None):
    """Return (mono float32 samples at 16 kHz, sample_rate, AudioQuality). Raise ValueError on bad input."""
    raise NotImplementedError
