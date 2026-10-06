# MASTER IMPLEMENTATION PROMPT — "VaaniGuard": Risk-Adaptive Verification for High-Risk Financial Voice Interactions

You are building a hackathon-finale prototype (48 hours, team of 2–4) for the Amazon x IIT Delhi RAKSHAM AI Cybersecurity Hackathon, Track 01: Voice Cloning Fraud Detection.

Philosophy: **Build the smallest impressive system that actually works.** Use a modular monolith with clean interfaces. Every ML component must be replaceable and must have a deterministic fallback. No Kubernetes, microservices, cloud infra, auth systems, training from scratch, placeholder buttons, or fake AI. If an ambiguous decision comes up, choose whatever maximizes demo reliability, then technical differentiation, then feasibility. Record each such decision in `DECISIONS.md` instead of asking me.

## 0. First actions (do these before writing code)
1. Inspect the repository (`ls -la`, read any README/existing code). Do not delete existing work. Adapt to it or build alongside it.
2. Check the environment: Python ≥3.10, Node ≥18, ffmpeg present, GPU availability (`torch.cuda.is_available()`), free disk space.
3. Write `PLAN.md` with the MUST/SHOULD/STRETCH checklist from Section D, and tick items off as you go.
4. Build MUST items end-to-end first: a thin vertical slice (upload → score → UI) before polishing anything.

---

## A. Product definition
VaaniGuard sits beside a high-risk voice interaction, such as a call that leads to a payment, OTP disclosure or beneficiary change. It answers one question: **"How much independent verification does this interaction need before money moves?"**

Pipeline:
Audio → ASR → (voice authenticity ‖ scam-language ‖ urgency ‖ financial-request ‖ identity/channel ‖ transaction context) → confidence-weighted fusion → risk tier → adaptive verification → human review / transaction hold → tamper-evident evidence record.

Core beliefs, which must appear in the UI and README:
- Voice deepfake detectors are fallible, especially on compressed Indian telephony audio. **A voice score alone can never push risk above MEDIUM.**
- **A matching voice is not proof of identity**, because clones are built to match. Speaker similarity can raise risk when the voice doesn't match, but it barely lowers risk when it does.
- Friction scales with risk. Legitimate calls should pass with zero or minimal friction.
- The system never labels a person a fraudster. It labels an interaction as needing verification. The verification outcome decides.

Explicit labels: this is a **prototype**. All financial data is **SYNTHETIC**. Never claim production-grade banking security or validated accuracy.

## B. Personas
1. **Priya, finance executive at a Bengaluru SME.** She receives a call from her "MD" asking for an urgent vendor transfer. Primary user of the transaction-protection flow.
2. **Ramesh, 62, retail bank customer.** He receives a "bank officer" KYC call or a "son in an accident" call. He sees a simple customer-facing alert card.
3. **Anjali, fraud analyst at a bank or the SME's finance-controls owner.** She works the human review queue, inspects evidence and makes the final decision on CRITICAL cases.

## C. Core user journeys
1. **Live call monitor (hero demo):** pick a scenario → the audio plays → the transcript and risk meter update segment by segment, in sync with playback → the tier changes and the reasons appear → the verification panel opens automatically → complete the verification → final decision → evidence record.
2. **Upload analysis:** upload a .wav/.mp3/.m4a file and fill in or choose a transaction context → get the full breakdown.
3. **Verification:** the system proposes the least-disruptive sufficient method → the user or analyst completes it (pass / fail / no response) → risk is re-evaluated → the transaction is released or blocked.
4. **Human review:** CRITICAL items land in the queue → the analyst views evidence (redacted transcript, signal breakdown, hashes) → approves, rejects or escalates with a mandatory note.
5. **Privacy:** view the data manifest (what is collected, what isn't, retention) → purge any analysis → see the purge recorded in the audit log.

## D. Feature scope

### MUST BUILD
- FastAPI backend with the analysis pipeline: ASR, voice authenticity (model + acoustic fallback), scam-language lexicon engine (English/Hindi/Hinglish), urgency, financial-request, identity/channel mismatch, context engine, fusion engine, tiering.
- Adaptive verification engine with a method-selection matrix, simulated execution (callback, out-of-band device confirmation, challenge, second approver) and re-scoring after the outcome.
- Explainability: per-signal scores (0–100), confidence for each signal, contribution percentages, triggered escalation rules, top reasons in plain English, highlighted transcript spans.
- Six demo scenarios (Section M) with bundled audio, synthetic context and expected tiers enforced by tests.
- Live Call Monitor page with segment-synchronized risk timeline.
- Analysis Detail, Verification panel, Review Queue, Audit Log, Privacy Center pages.
- PII redaction before storage, ephemeral audio deletion, SHA-256 evidence hashes, hash-chained audit log, purge endpoint.
- `/api/health` reporting the real status of each model (loaded / fallback / unavailable), shown in the UI header.
- Graceful fallbacks for every failure in Section R.
- pytest suite for fusion, rules, verification selection, redaction, lexicon and API.
- One-command startup and a README.

### SHOULD BUILD
- Speaker-consistency signal (Resemblyzer, or SpeechBrain ECAPA if fast enough) against consented enrolled demo voices, kept in memory and encrypted at rest.
- Multilingual zero-shot intent classifier (`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`) blended with the lexicon.
- A "Customer view" toggle showing the mobile-style alert Ramesh would see.
- Exportable evidence report (JSON plus printable HTML).
- Microphone recording (record → analyze as upload).
- Dockerfile / docker-compose.

### STRETCH
- True streaming analysis over WebSocket from the microphone in 3-second chunks.
- A "what-if" panel: sliders for amount, beneficiary age and time to show tier changes live.
- A red-team mode that replays an attack with one signal suppressed to demonstrate robustness.

---

## E. Detection architecture

```
                 AUDIO (upload / scenario / mic)
                          │  validate (size ≤10MB, ≤120s, decodable), resample 16kHz mono
          ┌───────────────┼──────────────────────┐
     AUDIO QUALITY     ASR ENGINE            CALL METADATA (simulated)
     (SNR, bandwidth,  faster-whisper         caller no., in-directory?,
      clipping, dur.)  → segments+lang        channel: pstn/voip/whatsapp
          │               │                         │
   VOICE AUTHENTICITY     │                         │
   model prob ⊕ acoustic  │                         │
   heuristics; confidence │                         │
   scaled by quality ─────┤                         │
          │        LANGUAGE ENGINE                  │
          │   scam lexicon + (zero-shot) →          │
          │   S scam, U urgency, F financial req,   │
          │   claimed identity extraction           │
          │               │                         │
          │        IDENTITY ENGINE ◄────────────────┘
          │   claimed identity vs directory/channel (+speaker sim)
          │               │
          │        CONTEXT ENGINE  (synthetic account profile + pending txn)
          │   amount ratio, new beneficiary, time window, velocity, process bypass
          └───────┬───────┴─────────┘
                  ▼
        RISK FUSION ENGINE  (confidence-weighted sum + escalation rules + caps)
                  ▼
        TIER: LOW / MEDIUM / HIGH / CRITICAL  + explanation
                  ▼
        ADAPTIVE VERIFICATION ENGINE (least-disruptive sufficient method)
                  ▼
        VERIFICATION OUTCOME → re-score → RELEASE / HOLD / BLOCK / HUMAN REVIEW
                  ▼
        EVIDENCE RECORD (redacted transcript, scores, hashes, hash-chained audit)
```

Each engine implements a common interface:
```python
class SignalResult(BaseModel):
    name: Literal["voice","scam","urgency","financial","identity","context"]
    score: float          # 0–100, higher = riskier
    confidence: float     # 0–1; 0 = unavailable
    source: Literal["model","heuristic","rules","simulated","fallback","cached"]
    evidence: list[Evidence]   # human-readable reasons + transcript spans
    latency_ms: int
```
Per-segment: compute cumulative signal results after each ASR segment so the live monitor can show risk evolving over time. This is done server-side in one pass; the frontend animates it in sync with audio playback.

Label every component in the UI and README as one of: **Real ML** (ASR, deepfake model, speaker embeddings, zero-shot), **Heuristic/Rules** (acoustic features, lexicon, context, fusion), **Simulated** (call metadata, bank/account data, callback/device confirmation), **Production replacement** (bank CBS/UPI switch, telephony CPaaS, HSM, SIEM).

## F. Risk scoring formula (implement exactly, keep weights in `config/risk.yaml`)

Signals and initial weights: V voice 0.20, S scam language 0.15, U urgency/coercion 0.10, F financial/credential request 0.20, C context anomaly 0.20, I identity/channel mismatch 0.15.

```
base = Σ(w_i · c_i · s_i) / Σ(w_i · c_i)        # unavailable signal → c_i = 0 (drops out)
coverage = Σ(w_i · c_i) / Σ(w_i)
```

Escalation rules (apply in order, and record every triggered rule in the explanation):
- **R1 Credential request:** F detected a request for OTP/UPI PIN/CVV/password/remote-access app → `score = max(score, 85)`. Reason: "Legitimate banks never ask for OTP/PIN over a call."
- **R2 Context-led (detector-independent):** F ≥ 60 AND C ≥ 70 AND (U ≥ 50 OR I ≥ 60) → `score = max(score, 70)`.
- **R3 Voice + money:** V ≥ 70 (with c_V ≥ 0.5) AND F ≥ 60 → `score += 8`.
- **R4 Single-signal cap:** if exactly one signal has s ≥ 60 and every other available signal is < 30 → `score = min(score, 59)`. No accusation from a single weak signal.
- **R5 Low coverage:** if coverage < 0.5 and score ≥ 40 → tier at least MEDIUM, plus the flag "Insufficient evidence — verification recommended."
- Clamp to 0–100 and round.

Tiers: **LOW 0–29, MEDIUM 30–59, HIGH 60–79, CRITICAL 80–100.**
Contribution % per signal = `w_i·c_i·s_i / Σ(...)`, displayed alongside the rule contributions.
Explanation generator: top 3–4 reasons from the highest contributions plus triggered rules, as templated plain-English sentences that include specific values (e.g. "₹2,50,000 is 6.2× this account's typical transfer").

Sub-score definitions:
- **V (voice):** `0.7·model_prob + 0.3·acoustic_heuristic` (if the model is unavailable, heuristic only, with confidence ≤ 0.4). Acoustic heuristics come from librosa: unnaturally low pitch jitter/shimmer variance, low spectral flatness variance, near-silent noise floor between words (unnaturally clean), missing breath pauses, abnormal high-frequency rolloff. Confidence = base model confidence × quality factor. The quality factor drops for duration < 3s, SNR < 10dB, or bandwidth ≤ 4kHz (8kHz telephony). This is telephony-aware confidence.
- **S (scam language):** weighted lexicon category hits (diminishing returns per category) blended with zero-shot P("scam/fraud attempt") when available.
- **U (urgency/coercion):** urgency, threat, secrecy and authority categories plus speech rate (words/sec from ASR) above the speaker baseline.
- **F (financial request):** payment/transfer intent, amount extraction (₹, "lakh", "hazaar", digits, Hindi number words), credential request, remote-access request.
- **I (identity/channel):** claimed identity (regex/NER on "main X bank se bol raha hoon", "this is Rakesh", "CFO") vs directory. Score rises for: claimed number not in directory, unofficial channel (WhatsApp/VoIP for a "bank"), claimed role not authorized for this request, speaker similarity < threshold (SHOULD). High similarity lowers I by at most 10.
- **C (context):** amount ÷ 90-day median (log-scaled), new beneficiary (+), beneficiary account/UPI ID age < 7 days (+), outside the user's activity window (+), velocity (several transfers in 1h), process bypass phrases ("don't loop in accounts", "skip approval").

## G. Adaptive verification logic

Method catalogue, each with a friction cost (1–5) and strength (1–5):
`in_app_warning (1/1)`, `codeword (2/2)`, `out_of_band_device_confirm (2/4)` (push to the claimed person's registered device), `independent_callback (3/4)` (call the number on file, never the incoming number), `dynamic_challenge (3/3)` (question about recent shared context, issued via out-of-band channel), `trusted_contact (3/3)`, `second_approver (4/5)`, `manual_security_review (5/5)`, `cooling_off_hold (2/3)` (timed hold, e.g. 30 min).

Selection: required strength comes from the tier. Pick the lowest-friction combination that meets it, filtered by what is available for the claimed identity (e.g. a "bank" caller has no registered device, so use `end_call_and_call_official_number`).

| Tier | Required strength | Default action | Transaction |
|---|---|---|---|
| LOW | 0 | None; minimal audit entry | Continue |
| MEDIUM | 2 | In-app warning + one-tap optional codeword/device confirm | User may proceed (logged) |
| HIGH | 4 | Out-of-band device confirm OR independent callback | **Held** until pass |
| CRITICAL | 5+ | Independent callback **AND** second approver/manual review; cooling-off if amount ≥ ₹1,00,000 | **Held**, goes to review queue |

Special routes:
- Claimed bank/RBI/police + credential request → "End this call. Your bank will never ask for OTP/PIN. Call the number on your card / official app." Offer to report to 1930 / cybercrime.gov.in.
- Family emergency → trusted-contact callback on the saved number + family codeword.

Outcome handling:
- **pass** → re-score with `verification` signal (−35, floor at that tier's minimum − 1). The case is released but the record is retained.
- **fail** → CRITICAL, transaction blocked, evidence package generated.
- **no_response/timeout** → stays held and escalates one tier.

Every decision shows **"Why this verification?"** in plain English.

Anti-gaming rules:
- Codewords are never asked over the suspect channel and are verified only out-of-band.
- Callbacks always use the directory number, never the caller's number.
- Thresholds carry ±3 random jitter per session in a "hardened mode" flag so attackers can't probe exact cut-offs (off by default for deterministic demos/tests).

## H. Data models (Pydantic + SQLModel, SQLite at `data/vaaniguard.db`)

```python
class Evidence(BaseModel): kind: str; text: str; span: tuple[float,float]|None; weight: float
class CallMetadata(BaseModel):
    caller_number_masked: str; in_directory: bool; directory_name: str|None
    channel: Literal["pstn","voip","whatsapp","unknown"]; started_at: datetime
class TransactionContext(BaseModel):
    account_id: str; amount_inr: int|None; beneficiary_id: str|None
    beneficiary_is_new: bool; beneficiary_age_days: int|None
    typical_amount_inr: int; activity_window: tuple[int,int]  # hours
    recent_txn_count_1h: int; payment_rail: Literal["UPI","IMPS","NEFT","RTGS","wallet"]|None
class SegmentScore(BaseModel): t_start: float; t_end: float; text_redacted: str; cumulative_score: int; tier: str
class Analysis(SQLModel, table=True):
    id: str; created_at: datetime; scenario_id: str|None; is_synthetic: bool = True
    audio_sha256: str; audio_retained: bool = False; audio_expires_at: datetime|None
    language: str|None; transcript_redacted: str
    signals_json: str; rules_triggered_json: str; segments_json: str
    score: int; tier: str; coverage: float; explanation_json: str
    status: Literal["analyzed","verifying","released","held","blocked","in_review","closed"]
class Verification(SQLModel, table=True):
    id: str; analysis_id: str; methods_json: str; reason: str
    outcome: Literal["pending","pass","fail","no_response"]; completed_at: datetime|None; actor: str
class ReviewItem(SQLModel, table=True):
    id: str; analysis_id: str; priority: int; decision: Literal["pending","approve","reject","escalate"]
    analyst_note: str|None; decided_at: datetime|None
class AuditEntry(SQLModel, table=True):
    seq: int; ts: datetime; actor: str; action: str; analysis_id: str|None
    payload_hash: str; prev_hash: str; entry_hash: str   # sha256(prev_hash + payload)
class EnrolledVoice(SQLModel, table=True):   # SHOULD; consented demo personas only
    id: str; display_name: str; consent_ref: str; embedding_encrypted: bytes
```
Mirror these as TypeScript types in `frontend/src/types.ts`.

## I. API (FastAPI, prefix `/api`)
- `GET /health` → per-component status `{asr, deepfake_model, speaker, zero_shot, db}` each `loaded|fallback|unavailable` plus device (cpu/cuda).
- `GET /scenarios` → list with title, persona, description, expected tier.
- `POST /scenarios/{id}/run` → runs the **real pipeline** on the bundled audio + context → `AnalysisResponse`.
- `POST /analyses` (multipart: `audio`, `context` JSON, `metadata` JSON, `retain_audio: bool=false`) → `AnalysisResponse`.
- `GET /analyses/{id}`; `GET /analyses?limit=50`.
- `GET /analyses/{id}/audio` → only if retained and not expired; otherwise 410.
- `POST /analyses/{id}/verification` → creates a verification using the selected methods → `{verification_id, methods, reason, instructions}`.
- `POST /verifications/{id}/complete` `{outcome, actor}` → re-scored `AnalysisResponse`.
- `GET /review-queue`; `POST /review/{id}/decision` `{decision, note}` (note is required).
- `GET /audit?analysis_id=` plus `GET /audit/verify` → recomputes the hash chain and returns `{valid, broken_at}`.
- `DELETE /analyses/{id}` → purges audio, transcript and segments, keeps a hash-only tombstone, writes an audit entry.
- `GET /privacy/manifest` → what is collected, why, retention, what is never collected.
- `GET /analyses/{id}/report` → evidence report (JSON; `?format=html` SHOULD).

`AnalysisResponse` = `{id, score, tier, coverage, signals: SignalResult[], contributions: {name:pct}, rules_triggered: [{id, effect, reason}], reasons: string[], recommended_action: {tier, methods, why, transaction_state}, segments: SegmentScore[], transcript_redacted, highlights: [{start_char,end_char,category}], language, latency_ms: {...}, components: {...source/fallback per engine}, is_synthetic}`.

Errors use the shape `{error: {code, message, hint}}` with appropriate HTTP codes.

## J. Frontend (Vite + React + TypeScript + Tailwind + Recharts + lucide-react)
Vite was chosen over Next.js because it is faster to set up and has no SSR complexity; this is a local demo. Dark security-console aesthetic: slate/near-black base, a single accent per tier (LOW emerald, MEDIUM amber, HIGH orange, CRITICAL red). Monospace for IDs and hashes. A persistent **"SYNTHETIC DEMO DATA"** badge. A header shows model-status pills from `/health`.

Pages and components:
1. **Console (`/`)**: KPI tiles (analyses today, held transactions, ₹ protected (synthetic), median latency), recent analyses table with tier chips, review-queue count.
2. **Live Call Monitor (`/live`)**: scenario picker plus upload. Left: call card (caller masked, channel, claimed identity) and audio player. Center: **risk gauge 0–100** that animates per segment, plus a risk timeline chart. Right: streaming redacted transcript with colored highlights per category. On a tier change, a toast appears and the **Verification Panel** slides in. Simulated "Transaction pending: ₹X to NEW beneficiary" bar with state (Pending / Held / Released / Blocked).
3. **Analysis Detail (`/analyses/:id`)**: signal breakdown bars (score + confidence opacity + source tag), contribution donut, triggered rules list, "Why" reasons, component latency, evidence hashes, purge button, report export.
4. **Verification Panel** (component): chosen methods with "Why this verification?", simulation controls (e.g. "Simulate: Rakesh confirms on registered device / denies / no response"), and re-scored result.
5. **Review Queue (`/review`)**: priority-sorted CRITICAL items; side panel with evidence; approve/reject/escalate with required note.
6. **Audit Log (`/audit`)**: entries plus a "Verify chain integrity" button.
7. **Privacy Center (`/privacy`)**: manifest table (Collected / Why / Retention / Not collected), retention settings display, purge-all-demo-data.
8. **Customer View** (SHOULD, a toggle on Live): phone-frame alert card in simple English + Hindi, e.g. "रुकिए! Is call पर भरोसा करने से पहले verify करें."

Every async view needs loading skeletons, an empty state with a CTA ("Run a demo scenario") and an error state with a retry button. No dead buttons.

## K. Backend services (`backend/app/`)
`main.py` (app, CORS localhost only, routers) · `config.py` (pydantic-settings, env) · `services/audio_io.py` (validate, decode via soundfile/ffmpeg, resample, quality metrics) · `services/asr.py` · `services/voice_auth.py` · `services/speaker.py` · `services/language.py` (lexicon + zero-shot + amount/identity extraction) · `services/identity.py` · `services/context.py` · `services/fusion.py` (pure, deterministic) · `services/verification.py` (pure selector + state machine) · `services/redaction.py` · `services/evidence.py` (hashing, report) · `services/audit.py` (hash chain) · `services/model_registry.py` (lazy load, timeouts, status) · `services/pipeline.py` (orchestrates, runs engines concurrently with per-engine timeouts, builds segments) · `data/lexicon.yaml` · `data/scenarios/*.json` · `data/directory.json` (synthetic contacts/officials) · `data/accounts.json`.
Logging: structured JSON logs (`logging` + request id). **Never log transcripts, audio or numbers**; log only ids, timings and tiers.

## L. AI/ML pipeline
- **ASR:** `faster-whisper`, model `small` (Hindi/Hinglish quality) with CTranslate2 int8 on CPU, or `base` if `small` is too slow (> 1.5× real-time); auto-detect language; `vad_filter=True`; keep segment timestamps.
- **Deepfake model:** a pretrained wav2vec2-based audio anti-spoofing classifier from Hugging Face (candidate: `MelodyMachine/Deepfake-audio-detection-V2`). **Verify it exists, check its label mapping and license, and test it on one real and one TTS clip.** If unusable, pick another ASVspoof/In-the-Wild-trained checkpoint and log the choice in DECISIONS.md. Run on 4s windows with 50% overlap; aggregate with a trimmed mean. Show the disclaimer: "Not validated on Indian telephony audio."
- **Acoustic heuristics:** librosa features listed in Section F, mapped to 0–100 via fixed thresholds kept in config.
- **Speaker (SHOULD):** Resemblyzer embeddings; cosine similarity against the enrolled persona; embeddings for incoming audio are never persisted.
- **Zero-shot (SHOULD):** mDeBERTa XNLI with labels ["fraud or scam attempt", "urgent pressure", "request for money or OTP", "normal conversation"]; truncate to 512 tokens.
- **Lexicon** (`lexicon.yaml`, weighted, regex, with English + Devanagari + romanized Hinglish). Categories: `credential` (OTP, PIN, CVV, "OTP batao", "code bata do", "ओटीपी"), `account_threat` (account block, KYC expire, "band ho jayega", digital arrest, FIR), `urgency` (abhi, turant, jaldi, "10 minute mein", immediately), `authority` (RBI, CBI, customs, police, bank manager, CFO, MD), `secrecy` (kisi ko mat batana, confidential, don't tell), `payment` (UPI, GPay, PhonePe, Paytm, transfer, "paise bhejo", collect request, scan QR, IMPS/NEFT/RTGS), `remote_access` (AnyDesk, TeamViewer, screen share, "app install karo"), `process_bypass` (skip approval, "accounts ko mat batao", new account details), `emotional_lever` (accident, hospital, arrested, emergency).
- **Confidence handling:** every engine returns its confidence; fusion uses it; the UI shows low-confidence signals faded with a tooltip explaining why.
- **Latency target:** a 30s clip fully analyzed in ≤ 10s on CPU after warm-up. Warm models on startup in a background task; the UI shows "warming up".

## M. Demo data
Use fictional entities only: "Bharat National Bank (BNB)", "Kaveri Textiles Pvt Ltd". Audio sources:
- **Genuine clips** recorded by team members with written consent.
- **"Cloned" clips** generated before the event with an open TTS/voice-cloning tool. Preferred: XTTS-v2 cloning a consenting team member's voice; alternative: Piper TTS. These are stored in `demo_audio/` with `consent.md` listing who consented.
- **Telephony realism:** use ffmpeg to downsample to 8kHz, add mild noise, and apply AMR/opus re-encode.

If audio isn't ready yet, generate placeholder TTS clips with any locally available TTS and mark them in DECISIONS.md. Each scenario JSON contains the audio path, call metadata, transaction context, expected tier, and a sidecar transcript used **only** if ASR fails.

| # | Scenario | Key signals (approx.) | Expected | Verification → outcome |
|---|---|---|---|---|
| 1 | **Legit BNB call**: genuine officer from directory number about card delivery; no request | V~20 S~10 F~5 C~0 I~5 | LOW | None; continue |
| 2 | **Cloned "BNB officer" KYC threat**: "aapka account aaj band ho jayega, OTP batao" from VoIP number | V~80 S~90 U~85 F~95 (credential) I~85; R1 | CRITICAL | End call, call official number, report 1930; Ramesh sees the customer card |
| 3 | **Cloned MD "Rakesh sir" → Priya**: "board meeting mein hoon, ₹4,80,000 vendor ko abhi bhejo, naya account, accounts ko mat batana" over WhatsApp | V~75 F~90 C~85 U~80 I~70; R2, R3 | CRITICAL | Device confirm + callback + second approver → Rakesh denies → **blocked**, evidence package |
| 4 | **Family emergency (Hinglish)**: cloned "son": "Papa accident hua, ₹50,000 GPay karo is number pe", 11:40 pm, new UPI ID | V~75 U~85 F~85 C~75 | HIGH/CRITICAL | Trusted-contact callback on saved number + family codeword → son is safe at home → blocked |
| 5 | **Detector-evading clone**: high-quality clone, calm and polite; V~38 with low confidence; "CFO" from unknown number asks for ₹6,20,000 (6× typical) to a 2-day-old beneficiary, "skip the usual approval" | V low, F~80 C~85 I~75; **R2 fires** | HIGH | Callback to directory number → CFO unaware → blocked. **Point the judges here: the detector alone would miss it.** |
| 6 | **False-positive guard**: real manager on a noisy 8kHz line (V~65, confidence ~0.5) asks for a routine payment to a known vendor at a normal amount | Only V elevated; R4 cap | LOW–MEDIUM | At most a light confirm; proceeds. Shows low friction for legitimate users |

Synthetic account profiles: typical amount, activity window 9:00–19:00, known beneficiaries. Directory entries for BNB official numbers, Rakesh (MD, with registered device), CFO, and the son.

## N. Security and privacy (concrete)
- **Ephemeral audio:** written to a temp dir with a random name and deleted in a `finally` block after analysis. If `retain_audio=true`, the audio is AES-encrypted via Fernet (key from `.env`, auto-generated on first run, git-ignored) with a 24h TTL; a startup and periodic sweeper deletes expired files.
- **Redaction before persistence:** phone numbers, account/card numbers, 4–8 digit OTP-like codes, Aadhaar-pattern (12 digits), PAN pattern, UPI IDs (partially masked), emails. Raw transcript exists in memory only.
- **No voiceprints of callers.** Enrolled embeddings exist only for consented demo personas, encrypted at rest.
- **Integrity:** SHA-256 of audio and of the analysis JSON in the evidence record; hash-chained audit log with a verify endpoint.
- **Input hardening:** size/duration/MIME limits, decode in try/except, reject non-audio; Pydantic validation on all JSON; no shell interpolation of filenames (pass ffmpeg args as a list).
- CORS limited to localhost; no external network calls at runtime except optional first-time model downloads.
- **Demo role switch** (User / Analyst) is clearly labeled "demo only — production would use bank IAM/SSO + RBAC".
- Persistent UI disclaimers: synthetic data, prototype, scores are risk indicators and not proof, a human decides on high-impact actions.
- **Adversarial mitigations.** Implement these where marked; otherwise document them in README:

| Attack | Mitigation |
|---|---|
| Better clone defeats detector | Context, identity and credential rules are independent of V (R1/R2); Scenario 5 |
| Replay of real recordings | Out-of-band confirm/callback; dynamic challenge about recent context; (doc) liveness prompt |
| Noise/compression to blind detector | Telephony-aware confidence lowers V's weight instead of trusting it; low coverage pushes toward verification (R5) |
| Multilingual/Hinglish scripts | Trilingual lexicon + multilingual Whisper/zero-shot |
| Codeword theft | Codeword verified only out-of-band; rotate after use; never the sole method above MEDIUM |
| Legit voice, malicious context (insider/coerced) | Speaker match barely lowers risk; context + process-bypass rules |
| Semantically normal AI conversation | Context + identity/channel signals |
| Learning thresholds | Hardened-mode jitter, rule diversity, no score shown to the caller side |
| Spoofed caller ID | Callback always to the directory number |
| Evidence tampering/abuse | Hash chain, redaction, purge, analyst-only evidence view |

## O. Testing (pytest, `backend/tests/`)
- **Unit:** fusion formula (coverage drop-out, each rule R1–R5, clamping, tier boundaries 29/30/59/60/79/80); verification selector per tier and special routes; state machine (pass/fail/no_response); redaction (each PII pattern, Devanagari text); lexicon hits for English/Hindi/Hinglish phrases; amount parser ("2.5 lakh", "₹2,50,000", "pachaas hazaar"); audit chain tamper detection.
- **Integration:** `TestClient` runs all 6 scenarios with models **forced into fallback mode** (env `VG_FORCE_FALLBACK=1`) and asserts expected tiers; upload validation errors; purge → 410 on audio; health endpoint.
- **Demo check:** `make demo-check` runs all scenarios with real models when available and prints a table of score/tier/latency/sources; it fails if any tier differs from expected. Tune weights only within ±0.05 to pass, and log the changes.
- **Frontend:** TypeScript strict build passes. STRETCH: one Playwright smoke test of Scenario 3.

## P. Deployment
- **Local:** `make setup` (venv, pip install, npm install, optional model pre-download script `scripts/download_models.py`) then `make dev` (uvicorn :8000 + vite :5173 concurrently). Also provide `run.sh` / `run.ps1`. SHOULD: docker-compose with a model cache volume.
- **README** includes: problem, architecture diagram, component labels (Real ML / Heuristic / Simulated / Replaceable), scoring formula, scenarios, privacy manifest, limitations, model/dataset/third-party/AI-generated-content disclosure, and the production path.
- **Production path (document only):** deploy as a sidecar to the bank's telephony/CPaaS stream and the payment-hold API (UPI switch / CBS). Owner: bank fraud-ops. Rollout: shadow mode → MEDIUM warnings only → holds for HIGH/CRITICAL. Other items: model retraining on consented telephony data, HSM-managed keys, SIEM export, on-device ASR for retail apps, latency budget < 2s per 3s chunk.

## Q. 48-hour roadmap
- **0–4h:** repo inspection, scaffold backend/frontend, config, schemas, `/health`, scenario JSONs + directory/accounts, fusion.py + verification.py **with unit tests first** (pure logic, no models).
- **4–8h:** audio_io, ASR with sidecar fallback, lexicon language engine, context and identity engines, pipeline orchestration, `/scenarios/{id}/run` working end-to-end in fallback mode; integration tests pass.
- **8–16h:** deepfake model + acoustic heuristics + model registry with timeouts; redaction, evidence, audit chain, purge; segment-level scoring; DB persistence.
- **16–24h:** frontend: Live Call Monitor (gauge, timeline, transcript highlights, transaction bar), Analysis Detail, Verification Panel wired to the real endpoints.
- **24–36h:** Review Queue, Audit, Privacy Center, Console; loading/empty/error states; demo audio finalized; `make demo-check` green; SHOULD items (speaker, zero-shot, customer view, report export).
- **36–48h:** polish, latency tuning and warm-up, README + DECISIONS, rehearse the demo script 3×, record a backup screen video, feature freeze 6h before judging.

## R. Failure handling (the demo must never dead-end)
- **Model download fails / no internet:** use the cached model if present; otherwise mark it `unavailable`, fall back (heuristics for V, lexicon only for language), and show an amber pill in the header. Pre-download script + instructions in README.
- **No GPU:** CPU int8 by default; this is never an error.
- **Slow inference:** per-engine timeout (ASR 25s, others 8s); on timeout the engine returns confidence 0 with `source="fallback"`; downgrade the Whisper model size via config; cache scenario results by audio hash.
- **Audio detector unavailable:** heuristics only with confidence ≤ 0.4; the UI says so.
- **ASR fails:** for scenarios, use the sidecar transcript labeled "fallback transcript". For uploads, return a partial analysis (voice + context only) with an R5 low-coverage flag and an option to paste a transcript manually.
- **DB fails:** in-memory store for the session plus a banner; analysis still returns.
- **Microphone unavailable/denied:** hide record and show upload/scenarios with an explanation.
- **External API unavailable:** none are required at runtime. Verification channels are simulated locally.
- **Malformed audio:** 422 with a hint ("Upload WAV/MP3/M4A under 2 minutes").
- **Last resort "Demo-safe mode" toggle:** replays results previously produced by real runs (stored with timestamp and component sources), clearly labeled "CACHED RESULT from run at …". Never fabricate results.

## S. Demo script (≈6 minutes)
1. **(30s) Hook.** Console with the model-status pills green. Say: "Detectors are fallible; we decide how much verification a call needs before money moves."
2. **(60s) Scenario 1, legit call.** LOW, zero friction. Point out that nothing interrupts genuine customers.
3. **(90s) Scenario 3, cloned MD.** Play the live monitor: the gauge climbs as "abhi", "naya account", "accounts ko mat batana" are highlighted, the transaction is held, and the Verification Panel shows "Why". Simulate "Rakesh denies on registered device" → blocked → open the evidence and audit chain.
4. **(60s) Scenario 5, detector evasion.** The voice score is low and faded (low confidence), yet R2 fires → HIGH. "A pure deepfake classifier would have approved this."
5. **(40s) Scenario 6, false-positive guard.** Noisy real voice; the R4 cap keeps friction minimal.
6. **(30s) Scenario 2 customer view.** Ramesh's Hindi/English card and the 1930 reporting path.
7. **(40s) Privacy Center + purge + audit chain verify; close** with the architecture slide and production path.

## T. Acceptance criteria (DONE when all are true)
- `make setup && make dev` works on a fresh machine (CPU only) and the UI loads at localhost:5173.
- All 6 scenarios run through the **real pipeline** and hit their expected tiers; `make demo-check` and `pytest` pass, including with `VG_FORCE_FALLBACK=1`.
- Uploading an arbitrary audio file produces a full explained analysis in ≤ 15s on CPU (after warm-up).
- Each tier triggers the correct verification; pass/fail/no_response each change the transaction state and score; CRITICAL items appear in the Review Queue and need an analyst note.
- The explanation shows per-signal score, confidence, source, contribution %, triggered rules and plain-English reasons.
- No raw audio remains on disk after a non-retained analysis; stored transcripts are redacted; purge works; the audit chain verifies and detects tampering.
- `/health` accurately reflects model state and every failure in Section R degrades gracefully with a visible label.
- No placeholder buttons, no console errors in the demo path, and the synthetic-data/prototype disclaimers are visible.
- README and DECISIONS.md are complete, including the model/dataset/AI-content disclosure.