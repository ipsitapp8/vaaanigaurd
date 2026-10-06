"""Run all six scenarios through the real pipeline with real models (when available) and compare to the
expected tiers (SPEC section O). Exits non-zero if any tier differs.

    cd backend && uv run python ../scripts/demo_check.py          # real models
    cd backend && VG_FORCE_FALLBACK=1 uv run python ../scripts/demo_check.py   # fallbacks only

Uses a throwaway data directory, so it never touches data/vaaniguard.db.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ["VG_DATA_DIR"] = tempfile.mkdtemp(prefix="vg_demo_check_")


def main() -> int:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import model_registry, scenarios

    forced = os.environ.get("VG_FORCE_FALLBACK") == "1"
    if not forced:
        print("Loading models (first run downloads them)...")
        t = time.perf_counter()
        model_registry.warmup()
        print(f"  warm-up {time.perf_counter() - t:.0f}s")
    model_registry.start_warmup = lambda: None  # already warmed (or forced to fallback)

    failures = 0
    rows = []
    with TestClient(app) as client:
        health = client.get("/api/health").json()["components"]
        print("Health:", {k: v for k, v in health.items()})
        for sc in scenarios.load_scenarios().values():
            t = time.perf_counter()
            r = client.post(f"/api/scenarios/{sc.id}/run")
            wall = time.perf_counter() - t
            if r.status_code != 200:
                rows.append((sc.id, "ERROR", "-", "-", f"{wall:.1f}s", r.text[:60], "FAIL"))
                failures += 1
                continue
            b = r.json()
            ok = b["tier"] in sc.expected_tiers
            failures += 0 if ok else 1
            sources = " ".join(f"{k}:{v['source']}" for k, v in b["components"].items() if k in ("asr", "voice"))
            v = next(s for s in b["signals"] if s["name"] == "voice")
            rows.append((sc.id, b["tier"], "/".join(sc.expected_tiers), str(b["score"]), f"{wall:.1f}s", f"V={v['score']:.0f}@{v['confidence']:.2f} {sources}", "ok" if ok else "FAIL"))

    print(f"{'scenario':38} {'tier':9} {'expected':14} {'score':6} {'time':7} {'signals/sources':44} result")
    for r in rows:
        print(f"{r[0]:38} {r[1]:9} {r[2]:14} {r[3]:6} {r[4]:7} {r[5]:44} {r[6]}")
    print("ALL SCENARIOS MATCH" if not failures else f"{failures} SCENARIO(S) DIFFER FROM EXPECTED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
