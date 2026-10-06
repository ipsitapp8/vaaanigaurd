"""Generate PLACEHOLDER demo audio for the six scenarios using Windows SAPI TTS.

These are NOT voice clones. They exist so the pipeline has real audio files to run on until the
consented genuine/cloned recordings are produced (SPEC section M). Each scenario's `segments`
get start/end timestamps written back to the scenario JSON.

Run from repo root:  cd backend && uv run python ../scripts/make_placeholder_audio.py
"""
import json
import subprocess
import tempfile
from math import gcd
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "backend" / "app" / "data" / "scenarios"
OUT_DIR = ROOT / "demo_audio"
SR = 16000
PAUSE_S = 0.35


def synth(segments: list[dict], voice: str, workdir: Path) -> list[np.ndarray]:
    items = [{"text": s.get("tts", s["text"]), "out": str(workdir / f"seg{i}.wav")} for i, s in enumerate(segments)]
    jp = workdir / "items.json"
    jp.write_text(json.dumps(items), encoding="utf-8")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "sapi_tts.ps1"), "-JsonPath", str(jp), "-Voice", voice],
        check=True,
    )
    out = []
    for it in items:
        x, sr = sf.read(it["out"], dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        g = gcd(SR, sr)
        out.append(resample_poly(x, SR // g, sr // g).astype(np.float32))
    return out


def telephony(x: np.ndarray, band_limit_hz: float, noise_db: float, seed: int) -> np.ndarray:
    nyq = SR / 2
    if band_limit_hz < nyq:
        x = sosfilt(butter(6, band_limit_hz / nyq, output="sos"), x)
    rng = np.random.default_rng(seed)
    x = x + rng.normal(0, 10 ** (noise_db / 20), size=x.shape).astype(np.float32)
    return np.clip(x, -1, 1).astype(np.float32)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for path in sorted(SCENARIOS.glob("s*.json")):
        sc = json.loads(path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            clips = synth(sc["segments"], sc["tts_voice"], Path(td))
        pause = np.zeros(int(PAUSE_S * SR), dtype=np.float32)
        parts, t = [], 0.0
        for seg, clip in zip(sc["segments"], clips):
            clip = clip / max(1e-6, float(np.abs(clip).max())) * 0.7
            seg["start"] = round(t, 2)
            seg["end"] = round(t + len(clip) / SR, 2)
            parts += [clip, pause]
            t += len(clip) / SR + PAUSE_S
        audio = np.concatenate(parts)
        tel = sc["telephony"]
        audio = telephony(audio, tel["band_limit_hz"], tel["noise_db"], seed=hash(sc["id"]) % 2**32)
        sf.write(OUT_DIR / sc["audio"], audio, SR, subtype="PCM_16")
        path.write_text(json.dumps(sc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{sc['id']}: {len(audio) / SR:.1f}s")


if __name__ == "__main__":
    main()
