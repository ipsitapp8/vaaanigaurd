"""Pure, deterministic risk fusion (SPEC section F): confidence-weighted sum, rules R1-R5, tiers.
Weights and thresholds come from config/risk.yaml. Phase 2 (unit tests first)."""
from dataclasses import dataclass, field

from app.models.schemas import RuleTriggered, SignalResult, Tier


@dataclass
class FusionResult:
    score: int
    tier: Tier
    coverage: float
    contributions: dict[str, float] = field(default_factory=dict)  # signal name -> pct
    rules_triggered: list[RuleTriggered] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def tier_for(score: int) -> Tier:
    raise NotImplementedError


def fuse(signals: list[SignalResult], config: dict | None = None) -> FusionResult:
    raise NotImplementedError
