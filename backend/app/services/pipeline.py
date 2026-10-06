"""Orchestrates the analysis (SPEC section E): audio -> ASR || voice -> language -> identity -> context
-> fusion -> verification plan. Engines run with per-engine timeouts and deterministic fallbacks.

Per-segment scoring: after each ASR segment the cumulative transcript is re-scored so the live monitor
can animate risk over time. Everything is computed server-side in one pass.
"""
import time
import uuid

from app.config import get_settings
from app.models.schemas import (
    AnalysisResponse,
    CallMetadata,
    ComponentInfo,
    SegmentScore,
    SignalResult,
    TransactionContext,
)
from app.services import asr, audio_io, model_registry, voice_auth
from app.services.context import analyze_context
from app.services.directory import get_entry
from app.services.fusion import FusionResult, fuse
from app.services.identity import analyze_identity
from app.services.language import LanguageAnalysis, analyze_language, find_highlights
from app.services.redaction import redact
from app.services.scenarios import Scenario
from app.services.verification import Capabilities, select_methods

SIGNAL_ORDER = ["voice", "scam", "urgency", "financial", "identity", "context"]


def _payment_request(la: LanguageAnalysis) -> bool:
    return la.amount_inr is not None or any(h.category == "payment" and h.weight >= 0.3 for h in la.hits)


def _score_text(
    text: str,
    duration_s: float,
    voice: SignalResult,
    metadata: CallMetadata,
    ctx: TransactionContext | None,
):
    """Run language, identity and context engines on a transcript prefix and fuse."""
    la = analyze_language(text, duration_s)
    pay = _payment_request(la)
    ident = analyze_identity(la.claimed, metadata, pay, la.credential_request)

    ctx_eff = ctx
    if ctx is not None:
        if not pay:
            # The pending transaction only matters once the call actually asks for money.
            ctx_eff = ctx.model_copy(update={"amount_inr": None, "beneficiary_id": None, "beneficiary_is_new": False, "beneficiary_age_days": None})
        elif ctx.amount_inr is None and la.amount_inr:
            ctx_eff = ctx.model_copy(update={"amount_inr": la.amount_inr})
    c = analyze_context(ctx_eff, la.process_bypass_hits, metadata.started_at.hour)

    signals = {s.name: s for s in (voice, la.scam, la.urgency, la.financial, ident, c)}
    ordered = [signals[n] for n in SIGNAL_ORDER]
    return la, ordered, fuse(ordered)


def run_pipeline(
    audio: bytes,
    metadata: CallMetadata,
    context: TransactionContext | None,
    scenario: Scenario | None = None,
    manual_transcript: str | None = None,
) -> AnalysisResponse:
    """Raises audio_io.AudioError on invalid audio; every other failure degrades to a fallback."""
    t_start = time.perf_counter()
    settings = get_settings()
    lat: dict[str, int] = {}

    samples, sr, quality = audio_io.load_audio(audio)

    # Voice and ASR run concurrently, each with its own timeout and fallback.
    t = time.perf_counter()
    voice_fut = model_registry._pool.submit(voice_auth.analyze_voice, samples, sr, quality)
    asr_res, asr_ok = model_registry.run_with_timeout(
        lambda: asr.transcribe(samples, sr), settings.asr_timeout_s, fallback=lambda: None
    )
    lat["asr"] = int((time.perf_counter() - t) * 1000)
    try:
        voice = voice_fut.result(timeout=settings.engine_timeout_s)
    except Exception:
        voice = SignalResult.unavailable("voice")
    lat["voice"] = voice.latency_ms

    asr_note: str | None = None
    if asr_res is not None:
        segs = [(s.start, s.end, s.text) for s in asr_res.segments]
        language, asr_source = asr_res.language, "model"
    elif manual_transcript:
        segs = [(0.0, quality.duration_s, manual_transcript)]
        language, asr_source, asr_note = None, "fallback", "Transcript pasted manually (ASR unavailable)."
    elif scenario is not None:
        segs = [(s.start, s.end, s.text) for s in scenario.segments]
        language, asr_source, asr_note = scenario.language, "fallback", "Fallback transcript (sidecar) used because ASR was unavailable."
    else:
        segs, language, asr_source = [], None, "fallback"
        asr_note = "ASR unavailable: partial analysis from voice and context only."

    # Per-segment cumulative scoring
    t = time.perf_counter()
    segment_scores: list[SegmentScore] = []
    texts: list[str] = []
    final: tuple[LanguageAnalysis, list[SignalResult], FusionResult] | None = None
    for start, end, text in segs:
        texts.append(text)
        final = _score_text(" ".join(texts), end, voice, metadata, context)
        segment_scores.append(SegmentScore(t_start=round(start, 2), t_end=round(end, 2), text_redacted=redact(text), cumulative_score=final[2].score, tier=final[2].tier))
    if final is None:
        final = _score_text("", quality.duration_s, voice, metadata, context)
    la, signals, fusion = final
    lat["scoring"] = int((time.perf_counter() - t) * 1000)

    # Verification plan
    entry = get_entry(la.claimed.directory_id) if la.claimed else None
    if entry:
        caps = entry.capabilities()
    elif la.claimed:  # claimed an identity we have no directory contact for
        caps = Capabilities(registered_device=False, callback_number=False, trusted_contact=False, second_approver=True, codeword=False)
    else:
        caps = Capabilities()
    amount = (context.amount_inr if context and context.amount_inr else None) or la.amount_inr
    plan = select_methods(fusion.tier, la.claimed.kind if la.claimed else None, amount, la.credential_request, caps)  # type: ignore[arg-type]
    why = plan.reason + ("".join(" " + a for a in (plan.advice or [])))

    transcript_redacted = " ".join(s.text_redacted for s in segment_scores)
    lat["total"] = int((time.perf_counter() - t_start) * 1000)

    if voice.confidence == 0:
        voice_note = "Voice analysis unavailable; voice is excluded from scoring."
    elif voice.source == "heuristic":
        voice_note = "Deepfake model not loaded: acoustic heuristics only, low confidence."
    else:
        voice_note = "Deepfake model + acoustic heuristics. Not validated on Indian telephony audio."
    components = {
        "asr": ComponentInfo(source=asr_source, note=asr_note),  # type: ignore[arg-type]
        "voice": ComponentInfo(source=voice.source, note=voice_note),
        "language": ComponentInfo(source="rules", note="Lexicon (English/Hindi/Hinglish)"),
        "identity": ComponentInfo(source="rules", note="Directory and channel checks (simulated directory)"),
        "context": ComponentInfo(source="simulated", note="Synthetic account profile"),
        "fusion": ComponentInfo(source="rules", note="Confidence-weighted sum + rules R1-R5"),
    }

    return AnalysisResponse(
        id=uuid.uuid4().hex[:12],
        score=fusion.score,
        tier=fusion.tier,
        coverage=fusion.coverage,
        signals=signals,
        contributions=fusion.contributions,
        rules_triggered=fusion.rules_triggered,
        reasons=fusion.reasons + fusion.flags,
        recommended_action={"tier": fusion.tier, "methods": plan.methods, "why": why, "transaction_state": plan.transaction_state},  # type: ignore[arg-type]
        segments=segment_scores,
        transcript_redacted=transcript_redacted,
        highlights=find_highlights(transcript_redacted),
        language=language,
        latency_ms=lat,
        components=components,
        is_synthetic=True,
        claimed_identity=(la.claimed.directory_name or la.claimed.name) if la.claimed else None,
        call_metadata=metadata,
        transaction=context,
    )
