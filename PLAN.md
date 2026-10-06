# PLAN

Spec: docs/SPEC.md · Decisions: DECISIONS.md. Work one phase at a time.

## Phases
- [x] **Phase 1: Foundation** — env inspection, backend/frontend scaffold, models (H) + TS mirror, `config/risk.yaml` (F), service stubs (K), `/api/health`, Makefile + run.ps1
- [x] **Phase 2: Core logic and pipeline** — fusion (R1-R5), verification selector + state machine, redaction, audit chain, audio_io, ASR (+sidecar fallback), lexicon/context/identity engines, pipeline, `/scenarios`, `/scenarios/{id}/run`, `/analyses` upload; 190 tests
- [ ] Phase 3: deepfake model + acoustic heuristics, model registry timeouts, evidence, purge, segment scoring, DB persistence
- [ ] Phase 4: frontend pages (Live Monitor, Analysis Detail, Verification Panel)
- [ ] Phase 5: Review Queue, Audit, Privacy, Console; demo audio; `make demo-check`; SHOULD items
- [ ] Phase 6: polish, README, rehearsal

## Section D checklist

### MUST
- [x] FastAPI app, config (pydantic-settings), SQLModel + SQLite (DB file created at startup)
- [x] `/api/health` per-component status (reports `not_loaded` for now)
- [x] Data models (H) in Pydantic/SQLModel + `frontend/src/types.ts`
- [x] `config/risk.yaml` weights, rules, tiers
- [x] Dark UI shell with header, model pills, SYNTHETIC DEMO DATA badge
- [x] One-command startup (`make setup`, `make dev`, `run.ps1`)
- [ ] Analysis pipeline: ASR [x], voice authenticity [ ] (Phase 3), lexicon engine [x], urgency [x], financial [x], identity [x], context [x], fusion [x], tiering [x]
- [ ] Adaptive verification engine: selector + state machine [x]; endpoints, simulated execution + persisted re-scoring [ ] (Phase 3)
- [x] Explainability (per-signal scores, confidence, contributions, rules, reasons, highlights) in `AnalysisResponse`
- [ ] Six demo scenarios: JSON + context + tier tests [x]; audio is PLACEHOLDER TTS [ ] (replace with consented recordings, Phase 5)
- [ ] Live Call Monitor, Analysis Detail, Verification panel, Review Queue, Audit Log, Privacy Center
- [ ] PII redaction [x], in-memory audio (no temp files) [x], hash-chained audit module [x]; SHA-256 evidence, persistence, purge endpoint [ ] (Phase 3)
- [ ] Graceful fallbacks (section R): ASR/sidecar/partial analysis/timeouts/malformed audio [x]; detector-unavailable, DB fail, demo-safe mode [ ]
- [x] pytest suite (fusion, rules, verification, redaction, lexicon, audit, engines, API): 190 tests, run under `VG_FORCE_FALLBACK=1`
- [ ] README

### SHOULD
- [ ] Speaker consistency · [ ] zero-shot intent · [ ] Customer view · [ ] Evidence report export · [ ] Mic recording · [ ] Docker

### STRETCH
- [ ] WebSocket streaming · [ ] what-if panel · [ ] red-team mode
