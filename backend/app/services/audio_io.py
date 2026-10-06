"""Validate (size, duration, decodable), decode, resample to 16 kHz mono, compute quality metrics.

Decoding is done fully in memory (no temp files): soundfile first (wav/flac/ogg/mp3), then PyAV
(bundled with faster-whisper, handles m4a/aac/mp3/opus without a system ffmpeg).
"""
import io
from dataclasses import dataclass
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, welch

from app.config import get_settings

TARGET_SR = 16000
MIN_SECONDS = 0.5
HINT = "Upload WAV/MP3/M4A under 2 minutes."


class AudioError(Exception):
    def __init__(self, code: str, message: str, hint: str = HINT, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.hint, self.status = code, message, hint, status


@dataclass
class AudioQuality:
    duration_s: float
    snr_db: float
    bandwidth_hz: float
    clipping_ratio: float

    @property
    def is_telephony(self) -> bool:
        return self.bandwidth_hz <= 4000


def _decode_soundfile(data: bytes) -> tuple[np.ndarray, int]:
    x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return x.mean(axis=1), sr


def _decode_av(data: bytes) -> tuple[np.ndarray, int]:
    import av  # noqa: PLC0415  (installed with faster-whisper)

    with av.open(io.BytesIO(data)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("no audio stream")
        resampler = av.AudioResampler(format="flt", layout="mono", rate=TARGET_SR)
        chunks: list[np.ndarray] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None) or []:
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError("empty audio")
    return np.concatenate(chunks).astype(np.float32), TARGET_SR


def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == TARGET_SR:
        return x
    g = gcd(TARGET_SR, sr)
    return resample_poly(x, TARGET_SR // g, sr // g).astype(np.float32)


def compute_quality(x: np.ndarray, sr: int = TARGET_SR) -> AudioQuality:
    duration = len(x) / sr
    frame = int(0.025 * sr)
    n = len(x) // frame
    if n < 4:
        return AudioQuality(duration, 0.0, sr / 2, 0.0)
    rms = np.sqrt((x[: n * frame].reshape(n, frame) ** 2).mean(axis=1)) + 1e-8
    noise = np.percentile(rms, 10)
    speech = np.percentile(rms, 90)
    snr = float(20 * np.log10(speech / noise))

    # Bandwidth: highest frequency whose smoothed PSD is clearly above the noise floor measured
    # in the top of the band. 8 kHz telephony (resampled up) or band-limited audio gives ~3.4-4 kHz
    # even with broadband noise added.
    freqs, psd = welch(x, fs=sr, nperseg=min(1024, len(x)))
    db = 10 * np.log10(np.convolve(psd, np.ones(5) / 5, mode="same") + 1e-20)
    floor = float(np.median(db[(freqs >= 7500) & (freqs <= 7950)])) if sr >= 16000 else float(db[-1])
    above = np.nonzero(db > floor + 8.0)[0]
    bandwidth = float(freqs[above[-1]]) if above.size else sr / 2  # flat spectrum: no cutoff
    clipping =float((np.abs(x) >= 0.99).mean())
    return AudioQuality(duration_s=duration, snr_db=snr, bandwidth_hz=bandwidth, clipping_ratio=clipping)


def load_audio(data: bytes, filename: str | None = None) -> tuple[np.ndarray, int, AudioQuality]:
    """Return (mono float32 samples at 16 kHz, 16000, AudioQuality). Raises AudioError on bad input."""
    s = get_settings()
    if not data:
        raise AudioError("empty_file", "The uploaded file is empty.")
    if len(data) > s.max_audio_bytes:
        raise AudioError("file_too_large", f"The file is larger than {s.max_audio_bytes // (1024 * 1024)} MB.", status=413)

    try:
        x, sr = _decode_soundfile(data)
    except Exception:
        try:
            x, sr = _decode_av(data)
        except Exception:
            raise AudioError("undecodable_audio", "This file could not be decoded as audio.") from None

    if not np.isfinite(x).all():
        raise AudioError("invalid_audio", "The audio contains invalid samples.")
    x = _resample(x, sr)
    duration = len(x) / TARGET_SR
    if duration < MIN_SECONDS:
        raise AudioError("audio_too_short", "The audio is shorter than half a second.")
    if duration > s.max_audio_seconds:
        raise AudioError("audio_too_long", f"The audio is longer than {s.max_audio_seconds} seconds.")
    return x, TARGET_SR, compute_quality(x, TARGET_SR)
