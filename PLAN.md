# PLAN

Spec: docs/SPEC.md · Decisions: DECISIONS.md. Work one phase at a time.

## Phases
- [x] **Phase 1: Foundation** — env inspection, backend/frontend scaffold, models (H) + TS mirror, `config/risk.yaml` (F), service stubs (K), `/api/health`, Makefile + run.ps1
- [x] **Phase 2: Core logic and pipeline** — fusion (R1-R5), verification selector + state machine, redaction, audit chain, audio_io, ASR (+sidecar fallback), lexicon/context/identity engines, pipeline, `/scenarios`, `/scenarios/{id}/run`, `/analyses` upload; 190 tests
- [x] **Phase 3: Voice, persistence and workflow** — deepfake model (wav2vec2) + acoustic heuristics, thread caps/timeouts, DB persistence, verification endpoints + re-scoring, review queue API, audit/verify endpoints, evidence report (JSON/HTML), purge + tombstone, encrypted opt-in audio retention, privacy manifest, `make demo-check`; 211 tests
- [x] **Phase 4: frontend pages** — Live Monitor (gauge, timeline, synced transcript, transaction bar, upload), Analysis Detail, Verification Panel wired to real endpoints; 213 tests
- [x] **Phase 5: Console, Review Queue, Audit, Privacy; customer view, mic recording, stats and purge-all** — consented demo audio and a green real-model `make demo-check` are NOT done (needs team recordings; see DECISIONS #33, #55)
- [x] **Phase 6: README (architecture, scoring, scenarios, privacy, limitations, disclosure, production path)** — live rehearsal on real recordings and a backup screen video remain with the team

## Section D checklist

### MUST
- [x] FastAPI app, config (pydantic-settings), SQLModel + SQLite (DB file created at startup)
- [x] `/api/health` per-component status (reports `not_loaded` for now)
- [x] Data models (H) in Pydantic/SQLModel + `frontend/src/types.ts`
- [x] `config/risk.yaml` weights, rules, tiers
- [x] Dark UI shell with header, model pills, SYNTHETIC DEMO DATA badge
- [x] One-command startup (`make setup`, `make dev`, `run.ps1`)
- [x] Analysis pipeline: ASR [x], voice authenticity [x], lexicon engine [x], urgency [x], financial [x], identity [x], context [x], fusion [x], tiering [x]
- [x] Adaptive verification engine: selector + state machine, endpoints, simulated execution + persisted re-scoring
- [x] Explainability (per-signal scores, confidence, contributions, rules, reasons, highlights) in `AnalysisResponse`
- [ ] Six demo scenarios: JSON + context + tier tests [x]; audio is PLACEHOLDER TTS [ ] (replace with consented recordings, Phase 5)
- [x] Live Call Monitor, Analysis Detail, Verification panel, Review Queue, Audit Log, Privacy Center, Console
- [ ] PII redaction [x], in-memory audio (no temp files) [x], hash-chained audit module [x]; SHA-256 evidence, persistence, purge endpoint [x]
- [ ] Graceful fallbacks (section R): ASR/sidecar/partial analysis/timeouts/malformed audio [x]; detector-unavailable [x], DB fail [x], demo-safe cached mode [ ]
- [x] pytest suite (fusion, rules, verification, redaction, lexicon, audit, engines, API): 211 tests, run under `VG_FORCE_FALLBACK=1`
- [x] README

### SHOULD
- [ ] Speaker consistency · [ ] zero-shot intent · [x] Customer view · [x] Evidence report export · [x] Mic recording · [ ] Docker

### STRETCH
- [ ] WebSocket streaming · [ ] what-if panel · [ ] red-team mode
