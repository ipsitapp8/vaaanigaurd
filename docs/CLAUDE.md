# VaaniGuard — RAKSHAM Hackathon (Track 01: Voice Cloning Fraud Detection)

Full spec: docs/SPEC.md. Read the relevant sections before each phase.
Progress: PLAN.md. Decisions: DECISIONS.md.

## Stack
- Backend: FastAPI + SQLModel + SQLite, Python 3.11 via uv (NOT 3.14)
- Frontend: Vite + React + TypeScript + Tailwind + Recharts + lucide-react
- CPU only (no GPU), int8 inference. ffmpeg installed via winget.
- Windows: run.ps1 is the primary start command; Makefile for Git Bash.

## Rules
- Modular monolith. No microservices, Docker-first, auth systems or cloud infra.
- Every ML engine has a deterministic fallback and reports its source
  (model / heuristic / rules / simulated / fallback / cached).
- A voice score alone never pushes risk above MEDIUM.
- No placeholder buttons, no fake AI results. Cached results must be labelled.
- Never log transcripts, audio, phone numbers or account numbers.
- Store only redacted transcripts. Raw audio is deleted after analysis.
- All data is synthetic. Keep the "SYNTHETIC DEMO DATA" label visible.

## Workflow
- Work one phase at a time. Don't start the next phase unless asked.
- Run pytest before saying a phase is done.
- Update PLAN.md and commit at the end of each phase.
- Make ambiguous decisions yourself and log them in DECISIONS.md.