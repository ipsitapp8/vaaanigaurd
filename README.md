# VaaniGuard

**Risk-adaptive verification for high-risk financial voice interactions.** A hackathon prototype for the Amazon x IIT Delhi RAKSHAM AI Cybersecurity Hackathon, Track 01: Voice Cloning Fraud Detection.

> **Prototype. All data is synthetic.** Nothing here is production-grade banking security, and no accuracy has been validated. Scores are risk indicators, not proof. The system never labels a person a fraudster: it labels an *interaction* as needing verification, and a human decides on high-impact actions.

## The problem

Voice clones are now good enough to impersonate a bank officer, a managing director or a family member on a phone call. Deepfake detectors are fallible, especially on compressed Indian telephony audio, and a clone is built to *match* the real voice, so "the voice sounds right" is not evidence of identity.

VaaniGuard sits beside a high-risk call (one that leads to a payment, an OTP disclosure or a beneficiary change) and answers one question: **how much independent verification does this interaction need before money moves?**

Core beliefs, enforced in code and tests:

- **A voice score alone can never push risk above MEDIUM** (rule R4).
- **A matching voice is not proof of identity.** Speaker similarity may raise risk when the voice does not match, but lowers it by at most 10 points when it does.
- **Friction scales with risk.** A legitimate call should pass with zero or minimal friction.
- **Detector-independent rules (R1, R2)** catch the clone that fools the detector (scenario 5).

## Architecture

```
            AUDIO (upload / scenario / microphone)
                          | validate (size, duration, decodable), resample 16 kHz mono, quality metrics
          +---------------+------------------------+
     voice authenticity   ASR (faster-whisper)     call metadata (simulated)
     wav2vec2 model +     segments + language      number, directory, channel
     acoustic heuristics        |                         |
     (telephony-aware           v                         |
      confidence)        LANGUAGE ENGINE (lexicon: EN/HI/Hinglish)
          |              scam S, urgency U, financial F, claimed identity
          |                     |                         |
          |              IDENTITY ENGINE <----------------+
          |              CONTEXT ENGINE (synthetic account profile + pending transaction)
          +---------+-----------+
                    v
        RISK FUSION  confidence-weighted sum + rules R1-R5 + tiers   (pure, config/risk.yaml)
                    v
        TIER LOW / MEDIUM / HIGH / CRITICAL + explanation
                    v
        ADAPTIVE VERIFICATION  least-disruptive sufficient method(s)
                    v
        OUTCOME (pass / fail / no response) -> re-score -> release / hold / block / human review
                    v
        EVIDENCE: redacted transcript, scores, SHA-256 hashes, hash-chained audit log
```

Modular monolith: FastAPI + SQLModel + SQLite backend, Vite + React + TypeScript + Tailwind + Recharts frontend. CPU only (int8 inference). No cloud services at runtime.

### Component labels

| Component | Label | Notes |
|---|---|---|
| ASR | **Real ML** | `faster-whisper` `small`, int8, auto language detect, VAD |
| Voice authenticity | **Real ML + Heuristic** | `MelodyMachine/Deepfake-audio-detection-V2` (wav2vec2, Apache-2.0) on 4 s windows, blended 0.7/0.3 with numpy/scipy acoustic heuristics (uncalibrated) |
| Scam / urgency / financial language | **Heuristic / Rules** | Weighted regex lexicon in English, Devanagari and romanized Hinglish; amount parser (lakh, hazaar, digits, Hindi number words) |
| Identity / channel, context | **Heuristic / Rules** | Claimed identity vs directory and channel; amount vs typical, new beneficiary, activity window, velocity, process-bypass phrases |
| Fusion, tiers, verification selector | **Heuristic / Rules** | Pure and deterministic; weights and thresholds in `config/risk.yaml` |
| Call metadata, bank/account data, directory | **Simulated** | Synthetic fixtures |
| Callback, device confirmation, second approver | **Simulated** | The demo user chooses the outcome |
| Speaker similarity, zero-shot intent | **Not built** | Hooks exist (`services/speaker.py`; identity engine accepts a similarity) |
| Production replacement | **Replace in production** | Bank CBS / UPI switch for the payment hold, telephony CPaaS for audio, HSM-managed keys, SIEM export |

## Scoring

Signals and default weights: voice V 0.20, scam S 0.15, urgency U 0.10, financial F 0.20, context C 0.20, identity I 0.15.

```
base     = sum(w_i * c_i * s_i) / sum(w_i * c_i)      c_i = confidence; unavailable signal -> c_i = 0 (drops out)
coverage = sum(w_i * c_i) / sum(w_i)
```

Rules, applied in order, each recorded in the explanation:

- **R1 Credential request** (OTP, UPI PIN, CVV, password, remote-access app): score at least 85. "Legitimate banks never ask for OTP/PIN over a call."
- **R2 Context-led, detector-independent:** F >= 60 and C >= 70 and (U >= 50 or I >= 60): score at least 70.
- **R3 Voice + money:** V >= 70 with confidence >= 0.5, and F >= 60: +8.
- **R4 Single-signal cap:** exactly one signal >= 60 and every other available signal < 30: cap at 59. (Skipped when R1 or R2 fired; see DECISIONS #12.)
- **R5 Low coverage:** coverage < 0.5 and score >= 40: at least MEDIUM plus "Insufficient evidence, verification recommended."

Tiers: LOW 0-29, MEDIUM 30-59, HIGH 60-79, CRITICAL 80-100.

### Adaptive verification

| Tier | Strength required | Default action | Transaction |
|---|---|---|---|
| LOW | 0 | None, minimal audit entry | Continue |
| MEDIUM | 2 | In-app warning plus optional codeword/device confirm | User may proceed (logged) |
| HIGH | 4 | Registered-device confirm or independent callback | Held until pass |
| CRITICAL | 5 | Callback and second approver (manual review if none); cooling-off from INR 1,00,000 | Held, in review queue |

Special routes: a claimed bank/RBI/police caller with a credential request gets "End this call, call the number on your card, report to 1930 / cybercrime.gov.in". A family emergency gets a trusted-contact callback plus a family codeword. Callbacks always use the directory number, never the incoming one; a codeword is never the sole method above MEDIUM. Outcomes: **pass** lowers the score by 35 (floored below the tier minimum) and releases; **fail** makes it CRITICAL and blocks; **no response** keeps it held and escalates one tier.

## Run it

Requirements: Windows or any OS with Python 3.11 via [uv](https://docs.astral.sh/uv/), and Node 18+.

```bash
make setup        # uv sync (Python 3.11) + npm install
make dev          # backend :8000 and frontend :5173 (Windows: .\run.ps1)
make test         # pytest, ML engines forced into their fallbacks (VG_FORCE_FALLBACK=1)
make demo-check   # all six scenarios through the real models; fails if a tier differs
```

Open http://localhost:5173. The first start downloads the ASR (about 480 MB) and deepfake (about 380 MB) models; the header pills show "not loaded" until warm-up finishes. With no network and no cache, each engine falls back and its pill turns amber.

Settings use the `VG_` prefix (`VG_FORCE_FALLBACK=1`, `VG_DATA_DIR`, `VG_WHISPER_MODEL`, `VG_ASR_THREADS`, `VG_TORCH_THREADS`, ...).

**Demo-safe mode (header toggle, `PUT /api/demo-safe`).** A last resort if a model misbehaves on stage: scenario runs replay the most recent *real* result for that scenario and audio hash, with every signal and component labelled `cached` and a banner "CACHED RESULT from a real run at ...". Only runs where ASR and the voice model were both real are cached, and with nothing cached the real pipeline runs. Nothing is fabricated.

## Demo scenarios

Fictional entities only (Bharat National Bank, Kaveri Textiles Pvt Ltd). Run from **Live Monitor**.

| # | Scenario | Expected | What to show |
|---|---|---|---|
| 1 | Legit BNB call about card delivery | LOW | Zero friction |
| 2 | Cloned "BNB officer" KYC threat, asks for OTP | CRITICAL | R1, end-call route, 1930, **Customer view** |
| 3 | Cloned MD "Rakesh sir" asks Priya for INR 4,80,000 to a new account | CRITICAL | Risk climbs as phrases appear; verification panel; "denies" blocks; evidence and audit |
| 4 | Family emergency (Hinglish), new UPI ID, 11:40 pm | HIGH / CRITICAL | Trusted-contact callback plus codeword |
| 5 | Calm, polite clone from an unknown CFO number, 6x typical amount, "skip the usual approval" | HIGH | Voice score low and faded, yet **R2 fires**: a detector alone would miss it |
| 6 | Real manager on a noisy 8 kHz line, routine payment | LOW / MEDIUM | R4 cap keeps friction minimal |

**Known gap:** the bundled clips are placeholder TTS (Windows SAPI), not consented recordings or clones (`demo_audio/consent.md`). With real models, Whisper garbles them and scenarios 3 and 4 do not reach their expected tiers; with `VG_FORCE_FALLBACK=1` (sidecar transcripts) all six match. Replace the clips with consented recordings and re-run `make demo-check`.

## Privacy and security

- Audio is decoded **in memory**; no temp files. Opt-in retention (`retain_audio`) stores it Fernet-encrypted for 24 h and sweeps it automatically.
- Only **redacted** transcripts are stored (phone, account/card, OTP-like codes, Aadhaar, PAN, UPI IDs, emails). Transcripts, audio and numbers are never logged.
- No voiceprints of callers. SHA-256 of audio and analysis in every evidence record; **hash-chained audit log** with a verify endpoint (tampering is detected; deleting only the newest entries is not, without an external anchor).
- `DELETE /api/analyses/{id}` purges audio, transcript, segments and signals, keeps a hash-only tombstone and audits the purge. The Privacy Center shows the full manifest.
- CORS limited to localhost; no runtime network calls other than first-time model downloads.
- The role switch is **demo only**; production would use bank IAM/SSO and RBAC.

### Adversarial notes

| Attack | Mitigation |
|---|---|
| Better clone defeats the detector | R1/R2 do not depend on V (scenario 5) |
| Noise or compression to blind the detector | Telephony-aware confidence lowers V's weight; low coverage pushes toward verification (R5) |
| Hinglish scripts | Trilingual lexicon; multilingual Whisper |
| Codeword theft | Verified only out-of-band; never the sole method above MEDIUM |
| Legit voice, malicious context | Speaker match barely lowers risk; context and process-bypass rules |
| Spoofed caller ID | Callback always to the directory number |
| Evidence tampering | Hash chain, redaction, purge |
| Replay of real recordings | Out-of-band confirm and callback (a liveness prompt is documented, not built) |
| Threshold probing | Set `VG_HARDENED_MODE=1`: tier boundaries shift by a random +-3 points, fixed per server session (off by default so demos and tests are deterministic); a score is never shown to the caller side |

## Limitations

- The voice model is **not validated on Indian telephony audio**. On our placeholder clips it rates everything as real, which is exactly why the system does not trust it alone.
- Acoustic-heuristic thresholds are uncalibrated; the lexicon is hand-written; no accuracy claims are made.
- Directory, accounts, call metadata and verification channels are simulated.
- Speaker similarity, zero-shot intent, Docker, true streaming, the what-if panel and red-team mode are not built. Analysis is one server-side pass; the UI replays it in sync with playback.
- Single-process SQLite; no authentication by design.

## Model, dataset and AI-content disclosure

- ASR: `Systran/faster-whisper-small` (CTranslate2 conversion of OpenAI Whisper small, MIT).
- Deepfake detection: `MelodyMachine/Deepfake-audio-detection-V2` (Apache-2.0), fine-tuned from `motheecreator/Deepfake-audio-detection` on an "audiofolder" dataset not documented in the model card. Reported accuracy there is the author's own and was not reproduced here.
- Libraries: FastAPI, SQLModel, PyTorch (CPU), Transformers, faster-whisper, SciPy, NumPy, React, Recharts, Tailwind, lucide-react.
- Demo audio: placeholder speech from Windows SAPI text-to-speech; no real person's voice and no cloning.
- All synthetic data and scenario scripts, and much of this code and documentation, were written with an AI assistant (Claude) and reviewed by the team.

## Production path (documentation only)

Deploy as a sidecar to the bank's telephony/CPaaS stream and its payment-hold API (UPI switch / CBS), owned by bank fraud-ops. Roll out in shadow mode first, then MEDIUM warnings only, then holds for HIGH/CRITICAL. Also needed: retraining on consented telephony data, HSM-managed keys, SIEM export of the audit chain with an external anchor, on-device ASR for retail apps, and a latency budget under 2 s per 3 s chunk.

## Repository map

`backend/app` (api, services, models, data) · `frontend/src` (pages, components) · `config/risk.yaml` · `docs/SPEC.md` · `PLAN.md` · `DECISIONS.md` (every judgement call, including findings) · `scripts/` (`demo_check.py`, placeholder audio).
