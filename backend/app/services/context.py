"""Context anomaly signal (C): amount vs typical, new beneficiary, time window, velocity, process bypass.

Heuristic/Rules over the synthetic account profile. Amount is log-scaled.
"""
import math
import time

from app.models.schemas import Evidence, SignalResult, TransactionContext
from app.services.language import format_inr


def analyze_context(ctx: TransactionContext | None, process_bypass_hits: int = 0, hour: int | None = None) -> SignalResult:
    t0 = time.perf_counter()
    if ctx is None:
        return SignalResult(name="context", score=0, confidence=0, source="simulated", evidence=[], latency_ms=0)

    score = 0.0
    ev: list[Evidence] = []

    def add(points: float, kind: str, text: str):
        nonlocal score
        score += points
        ev.append(Evidence(kind=kind, text=text, span=None, weight=points / 100))

    if ctx.amount_inr and ctx.typical_amount_inr > 0:
        ratio = ctx.amount_inr / ctx.typical_amount_inr
        pts = max(0.0, min(60.0, 60 * math.log10(ratio))) if ratio > 1 else 0.0
        if pts >= 5:
            add(pts, "amount", f"₹{format_inr(ctx.amount_inr)} is {ratio:.1f}× this account's typical transfer.")
    if ctx.beneficiary_is_new:
        add(15, "beneficiary", "The beneficiary is new to this account.")
        if ctx.beneficiary_age_days is not None and ctx.beneficiary_age_days < 7:
            add(20, "beneficiary_age", f"The beneficiary account is only {ctx.beneficiary_age_days} day(s) old.")
    if hour is not None:
        lo, hi = ctx.activity_window
        if not (lo <= hour < hi):
            add(15, "time", f"{hour:02d}:00 is outside this account's usual activity window ({lo:02d}:00–{hi:02d}:00).")
    if ctx.recent_txn_count_1h >= 3:
        add(15, "velocity", f"{ctx.recent_txn_count_1h} transfers in the last hour.")
    elif ctx.recent_txn_count_1h == 2:
        add(8, "velocity", "Two transfers in the last hour.")
    if process_bypass_hits:
        add(min(40, 25 + 10 * (process_bypass_hits - 1)), "process_bypass", "The caller asked to skip normal approval or avoid involving accounts/finance.")

    has_txn = ctx.amount_inr is not None or ctx.beneficiary_id is not None
    return SignalResult(
        name="context",
        score=round(min(100.0, score), 1),
        confidence=0.9 if has_txn else 0.5,
        source="simulated",
        evidence=ev,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
