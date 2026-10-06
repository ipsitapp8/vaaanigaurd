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
8. **Rule thresholds in `risk.yaml`.** Rules R1-R5 thresholds, tier lower bounds, `pass_delta: -35`, cooling-off amount and hardened jitter are all config, not code.
9. **Env prefix `VG_`** for all settings (`VG_FORCE_FALLBACK`, `VG_DATA_DIR`, ...), matching the spec's `VG_FORCE_FALLBACK=1`.
10. **Phase 1 deliberately has no numpy/librosa/torch dependency.** ML dependencies are added in the phase that uses them to keep `make setup` fast.
11. **`docs/CLAUDE.md` says ffmpeg was installed via winget; it is not present in this shell.** Flagged above rather than assumed.

## Phase 2 decisions (2026-10-06)

12. **R4 is skipped when R1 or R2 fired.** Applied literally, "single signal >= 60 and all others < 30 -> cap 59" would cap an OTP request (R1) to MEDIUM when the language engine is the only high signal. R1/R2 are the detector-independent rules, so they win. The invariant "a voice score alone never pushes above MEDIUM" still holds (R4 caps it, and R1/R2 need F).
13. **Removed `voice_only_cap` from `risk.yaml`.** It duplicated R4 and was never in section F.
14. **R1 evidence contract.** The language engine marks credential/remote-access requests with `Evidence.kind == "credential_request"`; fusion reads only that. Bare "OTP/PIN" mentions and negated phrasings ("never share your OTP") do not count. A bare `apk` token was removed from the lexicon because Whisper renders "aapka" as "APK" and that produced a false R1 on a legitimate call (regression test added).
15. **Voice engine is honestly unavailable in Phase 2.** `voice_auth` returns confidence 0 (source `fallback`), so V drops out of fusion and coverage is about 0.63-0.71. Nothing is simulated. All six scenarios still reach their expected tiers on language/identity/context alone; Phase 3 adds V (and R3).
16. **Pending-transaction gating.** The synthetic pending transaction (amount, new beneficiary) only enters the context score once the transcript contains a payment request. Without this the live timeline would show a high score from the first second, before the caller asks for anything.
17. **No temp files for audio.** Uploads are decoded in memory (soundfile, then PyAV, which ships with faster-whisper), so there is no ffmpeg dependency and nothing to delete in a `finally`. Retained-audio encryption (Fernet) arrives with persistence. `retain_audio` is not accepted yet.
18. **ffmpeg is still not installed** and is not needed so far; PyAV decodes mp3/m4a/aac. It would only be needed to post-process demo audio with real AMR/opus (the placeholder script uses scipy instead).
19. **Placeholder demo audio** (Windows SAPI English voices reading romanized Hinglish, band-limited + noise). Not clones. See `demo_audio/consent.md`. Consequence: with the real Whisper model, scenario 3 transcribes badly ("lock 80,000", "Durant") and scores 70 HIGH instead of the expected CRITICAL. In forced-fallback mode (sidecar transcript) it scores 88. Real recordings in Phase 5 fix this; I did not add lexicon misspellings to chase SAPI artefacts.
20. **ASR timing (CPU, int8).** Whisper `small`: model load ~55 s on first use (includes the download), then ~5 s per ~20 s clip (about 0.25x real time), well under the 1.5x threshold, so `small` stays.
21. **Added `detail_json` to `AuditEntry`.** The audit hash must cover actor, action, analysis_id, timestamp and details so editing any field is detectable; the original table had no place for details. Documented limitation: deleting the newest entries is not detectable without an external anchor.
22. **`AnalysisResponse` extras:** `claimed_identity`, `call_metadata`, `transaction` (additive; the call card and transaction bar need them).
23. **Verification model.** `Capabilities` (device / callback / trusted contact / second approver / codeword) come from the synthetic directory entry of the claimed identity. CRITICAL = [device confirm if available] + callback + second approver (manual review if none) + cooling-off if amount >= INR 1,00,000, and always requires review. HIGH picks the lowest-friction method with strength >= 4; a codeword is never the sole method above MEDIUM. Pass applies -35 floored at (tier min - 1).
24. **Hardened-mode jitter is configured but not implemented yet** (off by default, per spec).
25. **Zero-shot intent and speaker similarity are not built** (SHOULD items); `analyze_identity` already accepts a speaker similarity and caps the "matching voice" discount at 10 points.
26. **Local environment gotcha:** a stale dev server from an earlier `make dev` can keep port 8000 after the terminal closes; find the PID with `netstat -ano` and stop it.