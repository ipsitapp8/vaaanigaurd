"""Pure verification-method selector + outcome state machine (SPEC section G)."""
from dataclasses import dataclass

from app.models.schemas import Tier, TransactionState, VerificationMethod, VerificationOutcome


@dataclass
class VerificationPlan:
    methods: list[VerificationMethod]
    reason: str
    transaction_state: TransactionState


def select_methods(tier: Tier, claimed_identity_kind: str | None = None, amount_inr: int | None = None) -> VerificationPlan:
    raise NotImplementedError


def apply_outcome(score: int, tier: Tier, outcome: VerificationOutcome) -> tuple[int, Tier, TransactionState]:
    """pass: -35 floored at tier minimum - 1; fail: CRITICAL + blocked; no_response: held + escalate one tier."""
    raise NotImplementedError
