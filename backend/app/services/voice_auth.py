"""Voice authenticity (V): 0.7*model_prob + 0.3*acoustic_heuristic, confidence scaled by audio quality.

Real ML: a pretrained wav2vec2 anti-spoofing classifier (MelodyMachine/Deepfake-audio-detection-V2,
Apache-2.0, labels fake=0 / real=1) scored on 4 s windows with 50% overlap, aggregated by trimmed mean.
Heuristic: numpy/scipy acoustic features with config-driven thresholds (uncalibrated).

If the model is not loaded the engine returns heuristics only with confidence <= 0.4, and says so.
Not validated on Indian telephony audio. A voice score alone can never push risk above MEDIUM (R4).
"""
import logging
import time

import numpy as np
from scipy.signal import stft

from app.config import get_settings, load_risk_config
from app.models.schemas import Evidence, SignalResult
from app.services import model_registry

log = logging.getLogger("vaaniguard.voice")

DISCLAIMER = "Not validated on Indian telephony audio."
FRAME = 400  # 25 ms at 16 kHz
HOP = 160  # 10 ms


def _scale(value: float, ok: float, bad: float) -> float:
    """Linear map: `ok` -> 0, `bad` -> 100 (works for both directions), clamped."""
    return float(np.clip((value - ok) / (bad - ok), 0, 1) * 100)


def _frames(x: np.ndarray) -> np.ndarray:
    n = 1 + (len(x) - FRAME) // HOP
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    return x[idx]


def _f0_semitones(frames: np.ndarray, voiced: np.ndarray, sr: int) -> np.ndarray:
    """Autocorrelation pitch for voiced frames (50-400 Hz). Returns semitone values of confident frames."""
    lo, hi = sr // 400, sr // 50
    out = []
    for fr in frames[voiced]:
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, mode="full")[FRAME - 1 :]
        if ac[0] <= 1e-9:
            continue
        ac = ac / ac[0]
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.5:
            out.append(12 * np.log2(sr / lag / 100.0))
    return np.asarray(out)


def acoustic_heuristics(x: np.ndarray, sr: int, bandwidth_hz: float, cfg: dict) -> tuple[float | None, list[Evidence]]:
    """Return (score 0-100 or None when too little signal, evidence). Each feature is scored independently."""
    h = cfg["voice"]["heuristics"]
    if len(x) < FRAME * 8:
        return None, []
    fr = _frames(x.astype(np.float64))
    rms = np.sqrt((fr**2).mean(axis=1)) + 1e-9
    db = 20 * np.log10(rms)
    floor, peak = float(np.percentile(db, 5)), float(np.percentile(db, 95))
    speech = db > floor + 12
    feats: list[tuple[str, float, Evidence]] = []

    dyn = peak - floor
    s = _scale(dyn, **h["dynamic_range_db"])
    feats.append(("dyn", s, Evidence(kind="voice_noise_floor", text=f"Noise floor between words is {'unnaturally clean' if s >= 50 else 'natural'} (dynamic range {dyn:.0f} dB).", weight=s / 100)))

    if speech.sum() >= 15:
        st = _f0_semitones(fr, speech, sr)
        if len(st) >= 10:
            sd = float(np.std(st))
            s = _scale(sd, **h["pitch_std_semitones"])
            feats.append(("pitch", s, Evidence(kind="voice_pitch", text=f"Pitch {'varies very little' if s >= 50 else 'varies naturally'} ({sd:.1f} semitones).", weight=s / 100)))

        f, _, z = stft(x, fs=sr, nperseg=512, noverlap=256)
        mag = np.abs(z) + 1e-10
        energy = mag.sum(axis=0)
        loud = energy > np.percentile(energy, 50)
        flat = np.exp(np.log(mag).mean(axis=0)) / mag.mean(axis=0)
        flat = flat[loud]
        if len(flat) >= 10:
            var = float(np.var(flat))
            s = _scale(var, **h["flatness_variance"])
            feats.append(("flat", s, Evidence(kind="voice_flatness", text=f"Spectral texture is {'unusually uniform' if s >= 50 else 'varied'} (flatness variance {var:.4f}).", weight=s / 100)))

        if bandwidth_hz > 6000:
            p = mag**2
            ratio = float(p[f >= 4000][:, loud].sum() / (p[:, loud].sum() + 1e-12))
            s = _scale(ratio, **h["hf_energy_ratio"])
            feats.append(("hf", s, Evidence(kind="voice_rolloff", text=f"High-frequency energy is {'abnormally low' if s >= 50 else 'normal'} for wideband audio ({ratio * 100:.2f}% above 4 kHz).", weight=s / 100)))

    dur = len(x) / sr
    if dur >= 5:
        quiet = ~(db > floor + 6)
        runs, run = 0, 0
        for q in quiet:
            run = run + 1 if q else 0
            if run == 20:  # 200 ms of silence
                runs += 1
        pauses = runs / dur * 10
        s = _scale(pauses, **h["pauses_per_10s"])
        feats.append(("pause", s, Evidence(kind="voice_pauses", text=f"{'Almost no' if s >= 50 else 'Normal'} breath/pause gaps ({pauses:.1f} per 10 s).", weight=s / 100)))

    if len(feats) < 2:
        return None, []
    return float(np.mean([f[1] for f in feats])), [f[2] for f in feats]


def quality_factor(quality, cfg: dict) -> tuple[float, list[str]]:
    q = cfg["voice"]["quality"]
    factor, notes = 1.0, []
    if quality.duration_s < q["short_duration_s"]:
        factor *= q["short_duration_factor"]
        notes.append("short clip")
    if quality.snr_db < q["low_snr_db"]:
        factor *= q["low_snr_factor"]
        notes.append("low signal-to-noise ratio")
    if quality.bandwidth_hz <= q["telephony_bandwidth_hz"]:
        factor *= q["telephony_factor"]
        notes.append("narrowband telephony audio")
    return factor, notes


def _load_model():
    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification  # noqa: PLC0415

    model_id = load_risk_config()["voice"]["model_id"]
    extractor = AutoFeatureExtractor.from_pretrained(model_id)
    model = AutoModelForAudioClassification.from_pretrained(model_id).eval()
    labels = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
    fake = [i for i, v in labels.items() if "fake" in v or "spoof" in v]
    if len(fake) != 1:
        raise RuntimeError("cannot determine the synthetic-speech label")
    return extractor, model, fake[0]


model_registry.register_loader("deepfake_model", _load_model)


def model_probability(x: np.ndarray, sr: int, bundle, cfg: dict, deadline: float) -> tuple[float, int] | None:
    """Trimmed mean of P(synthetic) over 4 s windows (50% overlap). None if no window finished in time."""
    import torch  # noqa: PLC0415

    torch.set_num_threads(get_settings().torch_threads)

    extractor, model, fake_idx = bundle
    v = cfg["voice"]
    win = int(v["window_s"] * sr)
    step = win // 2
    starts = list(range(0, max(1, len(x) - win + 1), step)) or [0]
    if len(starts) > v["max_windows"]:  # spread evenly instead of truncating the end
        starts = [starts[i] for i in np.linspace(0, len(starts) - 1, v["max_windows"]).astype(int)]
    probs: list[float] = []
    with torch.inference_mode():
        for s in starts:
            if probs and time.perf_counter() > deadline:
                break
            chunk = x[s : s + win]
            if len(chunk) < sr:  # under 1 s of audio
                continue
            inputs = extractor(chunk, sampling_rate=sr, return_tensors="pt")
            logits = model(**inputs).logits
            probs.append(float(torch.softmax(logits, dim=-1)[0, fake_idx]))
    if not probs:
        return None
    p = np.sort(probs)
    k = int(len(p) * 0.2) if len(p) >= 5 else 0
    return float(p[k : len(p) - k].mean()), len(probs)


def analyze_voice(samples, sample_rate: int, quality) -> SignalResult:
    t0 = time.perf_counter()
    cfg = load_risk_config()
    v = cfg["voice"]
    evidence: list[Evidence] = []
    try:
        heur, h_ev = acoustic_heuristics(samples, sample_rate, quality.bandwidth_hz, cfg)
    except Exception as exc:
        log.warning("heuristics_failed", extra={"fields": {"type": type(exc).__name__}})
        heur, h_ev = None, []

    prob = None
    bundle = model_registry.peek_model("deepfake_model")  # never blocks on a model that is still loading
    if bundle is not None:
        try:
            prob = model_probability(samples, sample_rate, bundle, cfg, t0 + v["model_budget_s"])
        except Exception as exc:
            log.warning("deepfake_model_failed", extra={"fields": {"type": type(exc).__name__}})

    def ms() -> int:
        return int((time.perf_counter() - t0) * 1000)

    if prob is None and heur is None:
        res = SignalResult.unavailable("voice", source="fallback")
        res.latency_ms = ms()
        return res

    factor, notes = quality_factor(quality, cfg)
    if prob is not None:
        p, n = prob
        score = p * 100 if heur is None else v["model_weight"] * p * 100 + v["heuristic_weight"] * heur
        conf = v["model_base_confidence"] * factor
        source = "model"
        evidence.append(Evidence(kind="voice_model", text=f"Anti-spoofing model: {p * 100:.0f}% probability of synthetic speech over {n} window(s). {DISCLAIMER}", weight=p))
    else:
        score = heur  # type: ignore[assignment]
        conf = v["heuristic_max_confidence"] * factor
        source = "heuristic"
        evidence.append(Evidence(kind="voice_model_unavailable", text="Deepfake model not available: acoustic heuristics only, low confidence.", weight=0.0))
    if notes:
        evidence.append(Evidence(kind="voice_quality", text=f"Confidence reduced: {', '.join(notes)}.", weight=0.0))
    evidence.extend(h_ev)
    return SignalResult(name="voice", score=round(float(score), 1), confidence=round(float(conf), 3), source=source, evidence=evidence, latency_ms=ms())  # type: ignore[arg-type]
