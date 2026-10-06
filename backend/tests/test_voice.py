"""Voice engine: acoustic heuristics, telephony-aware confidence, model-absent fallback."""
import numpy as np

from app.config import load_risk_config
from app.services import audio_io, voice_auth

SR = 16000


def _speechlike(seconds=8.0, pitch_wobble=4.0, noise=0.01, pauses=True, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    f0 = 120 * 2 ** ((pitch_wobble * np.sin(2 * np.pi * 0.7 * t) + rng.normal(0, pitch_wobble / 6, len(t)).cumsum() * 0.0005) / 12)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    x = sum(np.sin(k * phase) / k for k in range(1, 8)) * 0.2
    x = x * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
    if pauses:
        x = x * (np.sin(2 * np.pi * 0.35 * t) > -0.6)  # silent gaps
    return (x + rng.normal(0, noise, len(t))).astype(np.float32)


def test_scale_is_linear_clamped_and_direction_agnostic():
    assert voice_auth._scale(0, ok=3, bad=1) == 100  # clamped (below "bad")
    assert voice_auth._scale(2, ok=3, bad=1) == 50
    assert voice_auth._scale(50, ok=35, bad=65) == 50
    assert voice_auth._scale(10, ok=35, bad=65) == 0


def test_quality_factor_lowers_confidence_for_telephony_short_and_noisy():
    cfg = load_risk_config()

    class Q:
        duration_s, snr_db, bandwidth_hz = 20.0, 25.0, 8000.0

    assert voice_auth.quality_factor(Q, cfg)[0] == 1.0
    Q.bandwidth_hz = 3400.0
    f1, notes = voice_auth.quality_factor(Q, cfg)
    assert f1 == cfg["voice"]["quality"]["telephony_factor"] and "narrowband telephony audio" in notes
    Q.duration_s, Q.snr_db = 2.0, 5.0
    assert voice_auth.quality_factor(Q, cfg)[0] < f1


def test_too_short_audio_yields_no_heuristic():
    score, ev = voice_auth.acoustic_heuristics(np.zeros(1000, dtype=np.float32), SR, 8000, load_risk_config())
    assert score is None and ev == []


def test_unnaturally_clean_flat_signal_scores_higher_than_natural():
    cfg = load_risk_config()
    natural = _speechlike(noise=0.02, pitch_wobble=4.0)
    clean_flat = _speechlike(noise=1e-5, pitch_wobble=0.1, pauses=False)
    s_nat, _ = voice_auth.acoustic_heuristics(natural, SR, 8000, cfg)
    s_syn, ev = voice_auth.acoustic_heuristics(clean_flat, SR, 8000, cfg)
    assert s_nat is not None and s_syn is not None
    assert s_syn > s_nat
    assert any(e.kind == "voice_noise_floor" for e in ev)


def test_analyze_voice_without_model_is_heuristic_only_and_capped():
    x = _speechlike(10.0)
    q = audio_io.compute_quality(x, SR)
    res = voice_auth.analyze_voice(x, SR, q)  # tests run with VG_FORCE_FALLBACK=1: no model
    assert res.source == "heuristic" and 0 < res.confidence <= 0.4
    assert res.evidence[0].kind == "voice_model_unavailable"


def test_silence_or_tiny_clip_reports_unavailable():
    x = np.zeros(2000, dtype=np.float32)
    res = voice_auth.analyze_voice(x, SR, audio_io.compute_quality(x, SR))
    assert res.confidence == 0 and res.source == "fallback"
