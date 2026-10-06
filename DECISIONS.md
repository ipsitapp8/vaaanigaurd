# DECISIONS

## Environment findings (Phase 1, 2026-10-06)

| Item | Finding | Impact |
|---|---|---|
| OS | Windows 11 Home, 15.6 GB RAM, 18 logical CPUs | Plenty for CPU int8 Whisper `small` |
| Python | System has 3.14.2 (`py`) and 3.13.7; `uv` present | Backend pinned to **3.11 via uv** (ML wheels lag on 3.14) |
| Node / npm | 24.13.0 / 11.6.4 | OK (need 18 or newer) |
| ffmpeg | **Not on PATH**; no winget package found | Not needed in Phase 1. Needed in Phase 2 for m4a/mp3 decode and demo-audio telephony re-encode. Install with `winget install Gyan.FFmpeg` before Phase 2. |
| GPU | Intel Arc integrated only; no NVIDIA, no `nvidia-smi` | CPU-only, int8 everywhere. `/api/health` reports `device: cpu` |
| Disk | ~635 GB free | OK for model caches |
| make | GNU Make 4.4.1 (Git Bash) | `make` works; `run.ps1` is the PowerShell equivalent |
| git | 2.51.1; local repo with `master`; `origin` = github.com/ipsitapp8/vaaanigaurd (empty) | Not pushed |

## Decisions

1. **Python 3.11 via uv, not the system 3.14.** `backend/pyproject.toml` pins `requires-python = ">=3.11,<3.12"`; `make setup` runs `uv sync --python 3.11`. Per `docs/CLAUDE.md`.
2. **Config location.** `config/risk.yaml` lives at the repo root (spec F says `config/risk.yaml`); data (DB, retained audio) at repo-root `data/` (spec H says `data/vaaniguard.db`), while static seed data (lexicon, scenarios, directory, accounts) lives in `backend/app/data/` (spec K).
3. **Literal columns in SQLModel tables are `str`.** SQLAlchemy cannot map `Literal`. Allowed values are the `Literal` aliases in `models/schemas.py` and are validated at the API layer. Schema is otherwise exactly section H.
4. **Health status enum adds `not_loaded`.** Spec lists `loaded|fallback|unavailable`; Phase 1 has no models so components report `not_loaded` (or `fallback` under `VG_FORCE_FALLBACK=1`). The UI shows a grey pill for it.
5. **Added `end_call_and_call_official_number` to `VerificationMethod`.** Spec G uses it as a special route outside the 9-method catalogue; typed so the selector can return it.
6. **Tailwind v4 via `@tailwindcss/vite`** (no PostCSS config); no router yet (no pages exist, so no dead nav). `react-router-dom` arrives with the first real page.
7. **Vite dev proxy** forwards `/api` to `127.0.0.1:8000`, so the frontend has no CORS dependency in dev; backend CORS still allows only localhost origins.
8. **`voice_only_cap` and rule thresholds in `risk.yaml`.** Rules R1-R5 thresholds, tier lower bounds, `pass_delta: -35`, cooling-off amount and hardened jitter are all config, not code.
9. **Env prefix `VG_`** for all settings (`VG_FORCE_FALLBACK`, `VG_DATA_DIR`, ...), matching the spec's `VG_FORCE_FALLBACK=1`.
10. **Phase 1 deliberately has no numpy/librosa/torch dependency.** ML dependencies are added in the phase that uses them to keep `make setup` fast.
11. **`docs/CLAUDE.md` says ffmpeg was installed via winget; it is not present in this shell.** Flagged above rather than assumed.
