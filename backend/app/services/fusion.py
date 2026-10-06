"""Pure, deterministic risk fusion (SPEC section F): confidence-weighted sum, rules R1-R5, tiers.

Weights and thresholds come from config/risk.yaml. No I/O, no models.
"""
from dataclasses import dataclass, field

from app.config import load_risk_config
from app.models.schemas import RuleTriggered, SignalResult, Tier

TIER_ORDER: list[Tier] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Evidence kind emitted by the language engine for OTP/PIN/CVV/password/remote-access requests (R1).
CREDENTIAL_EVIDENCE_KIND = "credential_request"

SIGNAL_LABELS = {
    "voice": "Voice authenticity",
    "scam": "Scam language",
    "urgency": "Urgency/coercion",
    "financial": "Financial/credential request",
    "context": "Transaction context",
    "identity": "Identity/channel",
}


@dataclass
class FusionResult:
    score: int
    tier: Tier
    coverage: float
    base_score: float = 0.0
    contributions: dict[str, float] = field(default_factory=dict)  # signal name -> pct of weighted sum
    rules_triggered: list[RuleTriggered] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def tier_for(score: int, config: dict | None = None) -> Tier:
    bounds = (config or load_risk_config())["tiers"]
    tier: Tier = "LOW"
    for t in TIER_ORDER:
        if score >= bounds[t]:
            tier = t
    return tier


def tier_min(tier: Tier, config: dict | None = None) -> int:
    return (config or load_risk_config())["tiers"][tier]


def max_tier(a: Tier, b: Tier) -> Tier:
    return a if TIER_ORDER.index(a) >= TIER_ORDER.index(b) else b


def _has_credential_request(sig: SignalResult | None) -> bool:
    return bool(sig and sig.confidence > 0 and any(e.kind == CREDENTIAL_EVIDENCE_KIND for e in sig.evidence))


def fuse(signals: list[SignalResult], config: dict | None = None) -> FusionResult:
    cfg = config or load_risk_config()
    weights: dict[str, float] = cfg["weights"]
    rules = cfg["rules"]
    by_name = {s.name: s for s in signals}

    wc = {n: weights[n] * by_name[n].confidence if n in by_name else 0.0 for n in weights}
    denom = sum(wc.values())
    coverage = denom / sum(weights.values())
    available = {n: s for n, s in by_name.items() if s.confidence > 0}

    if denom == 0:
        return FusionResult(
            score=0,
            tier="LOW",
            coverage=0.0,
            flags=[rules["R5_low_coverage"]["flag"]],
            reasons=["No signal was available to assess this interaction."],
        )

    weighted = {n: wc[n] * by_name[n].score for n in available}
    base = sum(weighted.values()) / denom
    score = base
    triggered: list[RuleTriggered] = []
    flags: list[str] = []

    def s(name: str) -> float:
        return by_name[name].score if name in available else 0.0

    # R1: credential request
    r1 = rules["R1_credential_request"]
    if _has_credential_request(by_name.get("financial")):
        triggered.append(
            RuleTriggered(
                id="R1",
                effect=f"score raised to at least {r1['min_score']}",
                reason="Legitimate banks never ask for OTP/PIN over a call.",
            )
        )
        score = max(score, r1["min_score"])

    # R2: context-led, detector-independent
    r2 = rules["R2_context_led"]
    if (
        "financial" in available
        and "context" in available
        and s("financial") >= r2["financial_min"]
        and s("context") >= r2["context_min"]
        and (s("urgency") >= r2["urgency_min"] or s("identity") >= r2["identity_min"])
    ):
        triggered.append(
            RuleTriggered(
                id="R2",
                effect=f"score raised to at least {r2['min_score']}",
                reason="A payment request that is unusual for this account, combined with pressure or an identity/channel mismatch, needs verification regardless of how the voice sounds.",
            )
        )
        score = max(score, r2["min_score"])

    # R3: voice + money
    r3 = rules["R3_voice_plus_money"]
    v = by_name.get("voice")
    if v and v.score >= r3["voice_min"] and v.confidence >= r3["voice_confidence_min"] and s("financial") >= r3["financial_min"]:
        triggered.append(
            RuleTriggered(
                id="R3",
                effect=f"+{r3['bonus']} points",
                reason="A likely synthetic voice is making a money request.",
            )
        )
        score += r3["bonus"]

    # R4: single-signal cap (skipped when R1/R2 fired: those are strong, detector-independent rules)
    r4 = rules["R4_single_signal_cap"]
    high = [n for n, sig in available.items() if sig.score >= r4["high_signal_min"]]
    others_low = all(sig.score < r4["others_below"] for n, sig in available.items() if n not in high)
    if len(high) == 1 and others_low and not any(t.id in ("R1", "R2") for t in triggered):
        if score > r4["cap"]:
            score = r4["cap"]
            triggered.append(
                RuleTriggered(
                    id="R4",
                    effect=f"score capped at {r4['cap']}",
                    reason=f"Only one signal ({SIGNAL_LABELS[high[0]].lower()}) is elevated; a single weak signal is not enough to accuse an interaction.",
                )
            )

    score_int = max(0, min(100, round(score)))
    tier = tier_for(score_int, cfg)

    # R5: low coverage
    r5 = rules["R5_low_coverage"]
    if coverage < r5["coverage_below"] and score_int >= r5["score_min"]:
        flags.append(r5["flag"])
        triggered.append(
            RuleTriggered(id="R5", effect=f"tier at least {r5['min_tier']}", reason=r5["flag"])
        )
        tier = max_tier(tier, r5["min_tier"])

    total_w = sum(weighted.values())
    contributions = {
        n: round(100 * weighted[n] / total_w, 1) if total_w > 0 and n in weighted else 0.0 for n in weights
    }

    return FusionResult(
        score=score_int,
        tier=tier,
        coverage=round(coverage, 3),
        base_score=round(base, 1),
        contributions=contributions,
        rules_triggered=triggered,
        reasons=build_reasons(by_name, weighted, triggered),
        flags=flags,
    )


def build_reasons(by_name: dict[str, SignalResult], weighted: dict[str, float], triggered: list[RuleTriggered]) -> list[str]:
    """Top 3-4 plain-English reasons: triggered rules first, then the highest-contributing signals."""
    reasons: list[str] = [t.reason for t in triggered if t.id in ("R1", "R2", "R3")]
    for name in sorted(weighted, key=lambda n: weighted[n], reverse=True):
        sig = by_name[name]
        if sig.score < 30 or not sig.evidence:
            continue
        top = max(sig.evidence, key=lambda e: e.weight)
        reasons.append(f"{SIGNAL_LABELS[name]} ({round(sig.score)}/100): {top.text}")
        if len(reasons) >= 4:
            break
    return reasons[:4]
