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

## Phase 3 decisions (2026-10-07)

27. **Deepfake model: `MelodyMachine/Deepfake-audio-detection-V2`.** Verified on the Hub: Apache-2.0, `Wav2Vec2ForSequenceClassification`, `id2label {0: fake, 1: real}` (the loader finds the "fake" index from the config rather than hard-coding it), 378 MB, downloads and loads (about 4 min first time, about 25 s warm). CPU torch (`+cpu` wheel via a uv explicit index) and `transformers` were added to `pyproject.toml`.
28. **Result on our audio: the model calls every placeholder clip 0% synthetic** (including the SAPI "cloned" ones after telephony band-limiting). That is a real finding, not a bug, and it supports the product thesis: a detector alone misses these. It is also why scenarios depend on R1/R2. Not validated on Indian telephony audio; the UI must keep that disclaimer.
29. **No librosa.** Acoustic heuristics (noise-floor dynamic range, pitch variability via autocorrelation, spectral-flatness variance, pause rate, HF energy for wideband audio) use numpy/scipy only: librosa pulls numba and was not worth the install risk. Thresholds live in `config/risk.yaml` under `voice:` and are **uncalibrated** starting points.
30. **Voice confidence.** Model path: base 0.75 x quality factor (short clip 0.5, SNR < 10 dB 0.6, bandwidth <= 4 kHz 0.6). Heuristic-only path: 0.4 x the same factor (so <= 0.4). Under `VG_FORCE_FALLBACK=1` heuristics still run (they are deterministic), so V is `source: heuristic`, not absent. This replaced the Phase 2 "voice unavailable" tests.
31. **Request path never waits for a model load.** `model_registry.peek_model` returns the model only if already loaded; otherwise voice uses heuristics. Inference stops starting new 4 s windows after `model_budget_s` (6 s) and uses the windows finished so far (at least one).
32. **Thread caps.** ASR (8) and torch (6) run concurrently; uncapped they oversubscribed the 18 logical CPUs and a 25 s clip took 10-18 s. With caps it takes about 6-8 s.
33. **Real-model `demo-check` currently fails scenarios 3 and 4** (s3 HIGH vs CRITICAL, s4 MEDIUM vs HIGH/CRITICAL). Cause: Whisper garbles the SAPI placeholder audio (e.g. "Durant for lock 80,000" for "turant ... 4,80,000"), so urgency and the amount are lost, and a low-score detector now dilutes the average (as the formula intends). I did **not** tune weights or add lexicon misspellings to chase this; consented real recordings (Phase 5) are the fix. `VG_FORCE_FALLBACK=1 make demo-check` and pytest match all six.
34. **Persistence.** The full `AnalysisResponse` (redacted) is stored in `explanation_json`; the spec columns (signals, rules, segments, transcript) are filled too. Initial status: LOW/MEDIUM `analyzed`, HIGH `held`, CRITICAL `in_review` (a `ReviewItem` is created, priority = score). `analysis_sha256` hashes the analysis as first produced; re-scoring is recorded in the audit chain and the report shows both hashes.
35. **Verification re-scoring** reuses `apply_outcome`. The "verification signal" is recorded as a `VERIFY_PASS/FAIL/NO_RESPONSE` entry in `rules_triggered` (the `SignalName` type has no `verification`). Pass releases the transaction but a CRITICAL review item stays pending; fail blocks; no_response escalates one tier and creates a review item if it reaches CRITICAL. Starting a verification twice returns the pending one; completing twice is 409.
36. **Review decisions are final** (approve -> released, reject -> blocked, both close the analysis; escalate keeps it in the queue). The note is mandatory (422) and is never copied into the audit log (only its length).
37. **Purge tombstone** keeps id, timestamps, audio and analysis hashes, score/tier/status (numbers only, no content) and clears transcript, segments, signals and explanation. Purged analyses return 410, leave the review queue, and the purge is audited with the hashes. Idempotent.
38. **Audio retention** (opt-in `retain_audio`): Fernet, key auto-generated in `data/retention.key` (git-ignored; the spec said `.env`, but a key file next to the data is simpler to auto-create), 24 h TTL, swept at startup and every 10 min, and on an expired fetch. No plaintext is ever written to disk.
39. **DB failure:** if persistence throws, the analysis is still returned, kept in an in-memory dict, and `components.store` says so. Workflow endpoints (verification, review, audit) need the database and return an error then.
40. **Circular import guard:** `evidence.build_report` imports `audit` lazily (audit imports evidence for hashing).
41. **Not done yet (later phases):** demo-safe cached-results mode, hardened-mode jitter, speaker similarity, zero-shot, `make demo-check` green with real recordings.


## Phase 4 decisions (2026-10-07)

42. **Router and pages.** `react-router-dom` added with the first real pages: `/live` (Live Call Monitor) and `/analyses/:id` (Analysis Detail); `/` redirects to `/live`. The nav only lists pages that exist (Review, Audit, Privacy, Console arrive in Phase 5).
43. **Scenario audio endpoint** `GET /api/scenarios/{id}/audio` serves the bundled synthetic clip so the monitor can play it; uploads are played from a browser object URL (never sent back).
44. **Live sync model.** The whole analysis is computed server-side; the UI reveals segments by `audio.currentTime` (a segment appears when it starts). The Verification Panel mounts once the displayed tier reaches the analysis tier (or on end / "Skip to end", which exists because autoplay can be blocked and for rehearsal). A toast fires on each tier increase.
45. **Verification panel outcomes are labelled simulated** and use the claimed identity ("Simulate: Rakesh Menon confirms / denies / no response"). The re-scored result shows old -> new score, tier and transaction state, and links to the evidence page.
46. **Bug found in browser testing:** CSS grid columns defaulted to `min-width: auto`, so the Recharts `ResponsiveContainer` fed its own width back into the column and the tab froze. Fixed with `grid-cols-[repeat(3,minmax(0,1fr))]` and `min-w-0`.
47. **Bug found in browser testing:** a `data/vaaniguard.db` created in Phase 1 lacked `auditentry.detail_json` (`create_all` never alters tables), so persistence silently fell back to memory. `init_db` now adds missing columns (test added). The in-memory fallback itself behaved as designed and was labelled in `components.store`.
48. **Automation caveat:** the Chrome screenshot tool timed out while CSS animations were running (JS still responded); with animations disabled the same page screenshots fine. Not reproduced as a user-facing hang.
49. **Not in this phase:** the Customer view, what-if panel and Console/KPI page; the audio element showed 0:00 in the automated browser, so real-time playback sync was verified only through "Skip to end" and the first segment, not by listening. Re-check on a normal browser before the demo.


## Phase 5 decisions (2026-10-07)

50. **Pages added:** Console (`/`, KPIs from `GET /api/stats`), Review Queue (`/review`), Audit Log (`/audit`, "Verify chain integrity" button recomputes server-side), Privacy Center (`/privacy`, manifest table, purge-all via `DELETE /api/analyses`, each purge audited). All have skeleton, empty (with CTA) and error-with-retry states.
51. **Demo role switch** (User / Analyst, header, labelled "demo only: production would use bank IAM/SSO + RBAC"). It is a UI gate only: the Review page disables decisions unless Analyst. The backend has no auth, by design (spec: no auth systems).
52. **Console KPIs** use only persisted, non-purged analyses: "protected" is the sum of the amounts of blocked transactions (synthetic); "held" counts held, verifying and in_review. The review count excludes purged items.
53. **SHOULD items done:** Customer view (English + Hindi alert card, 1930 line, bank-never-asks-OTP text for the special route), microphone recording (MediaRecorder -> normal upload path; button hidden if unsupported, message if denied), evidence report export (JSON + printable HTML, from Phase 3).
54. **Double verification bug:** React StrictMode ran the panel's start effect twice and created two pending verifications for one analysis; the panel now starts once per analysis id.
55. **Demo audio is still placeholder TTS.** I cannot record or clone consenting people's voices from here, so the consented-recording step is NOT done and `make demo-check` with real models still fails scenarios 3 and 4 (#33). Needed from the team: record genuine clips and generate clones with consent, write them to `demo_audio/` and `consent.md`, and re-run `make demo-check`. Not done: Dockerfile, README (Phase 6), demo-safe cached mode, hardened-mode jitter, speaker similarity, zero-shot.
