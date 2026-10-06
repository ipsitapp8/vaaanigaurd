# PLAN

Spec: docs/SPEC.md · Decisions: DECISIONS.md. Work one phase at a time.

## Phases
- [x] **Phase 1: Foundation** — env inspection, backend/frontend scaffold, models (H) + TS mirror, `config/risk.yaml` (F), service stubs (K), `/api/health`, Makefile + run.ps1
- [ ] Phase 2: pure logic (fusion, verification, redaction, audit chain) with tests; audio_io, ASR, language/context/identity engines; pipeline + `/scenarios/{id}/run` in fallback mode
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
- [ ] Analysis pipeline: ASR, voice authenticity, lexicon engine, urgency, financial, identity, context, fusion, tiering
- [ ] Adaptive verification engine + simulated execution + re-scoring
- [ ] Explainability (per-signal scores, confidence, contributions, rules, reasons, highlights)
- [ ] Six demo scenarios with audio, context and tier tests
- [ ] Live Call Monitor, Analysis Detail, Verification panel, Review Queue, Audit Log, Privacy Center
- [ ] PII redaction, ephemeral audio deletion, SHA-256 hashes, hash-chained audit, purge
- [ ] Graceful fallbacks (section R)
- [ ] pytest suite (fusion, rules, verification, redaction, lexicon, API)
- [ ] README

### SHOULD
- [ ] Speaker consistency · [ ] zero-shot intent · [ ] Customer view · [ ] Evidence report export · [ ] Mic recording · [ ] Docker

### STRETCH
- [ ] WebSocket streaming · [ ] what-if panel · [ ] red-team mode
