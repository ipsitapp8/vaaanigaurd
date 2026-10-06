"""Pure verification-method selector + outcome state machine (SPEC section G)."""
from dataclasses import dataclass
from itertools import combinations
from typing import Literal, get_args

from app.config import load_risk_config
from app.models.schemas import Tier, TransactionState, VerificationMethod, VerificationOutcome
from app.services.fusion import TIER_ORDER, tier_for, tier_min

ClaimedKind = Literal["bank_official", "authority", "executive", "family", "unknown"]

# method -> (friction cost 1-5, strength 1-5)
CATALOGUE: dict[str, tuple[int, int]] = {
    "in_app_warning": (1, 1),
    "codeword": (2, 2),
    "out_of_band_device_confirm": (2, 4),
    "independent_callback": (3, 4),
    "dynamic_challenge": (3, 3),
    "trusted_contact": (3, 3),
    "second_approver": (4, 5),
    "manual_security_review": (5, 5),
    "cooling_off_hold": (2, 3),
}

REQUIRED_STRENGTH: dict[str, int] = {"LOW": 0, "MEDIUM": 2, "HIGH": 4, "CRITICAL": 5}


@dataclass(frozen=True)
class Capabilities:
    """What verification channels exist for the claimed identity (from the synthetic directory)."""

    registered_device: bool = True
    callback_number: bool = True
    trusted_contact: bool = False
    second_approver: bool = True
    codeword: bool = True


@dataclass
class VerificationPlan:
    methods: list[VerificationMethod]
    reason: str
    transaction_state: TransactionState
    requires_review: bool = False
    special_route: str | None = None
    advice: list[str] | None = None


def _available(caps: Capabilities) -> list[str]:
    out = ["in_app_warning", "dynamic_challenge", "cooling_off_hold", "manual_security_review"]
    if caps.codeword:
        out.append("codeword")
    if caps.registered_device:
        out.append("out_of_band_device_confirm")
    if caps.callback_number:
        out.append("independent_callback")
    if caps.trusted_contact:
        out.append("trusted_contact")
    if caps.second_approver:
        out.append("second_approver")
    return out


def _cheapest_for_strength(required: int, caps: Capabilities) -> list[str]:
    """Lowest-friction single method (or pair) whose strength meets `required`.

    Codeword is never the sole method above MEDIUM (it can be stolen), so it is excluded
    from standalone selection when required > 2.
    """
    avail = [m for m in _available(caps) if m != "in_app_warning"]
    best: tuple[int, int, list[str]] | None = None
    for size in (1, 2):
        for combo in combinations(avail, size):
            strength = max(CATALOGUE[m][1] for m in combo)
            if size == 2:
                strength = min(5, strength + 1)  # two independent methods corroborate each other
            if strength < required:
                continue
            if required > 2 and set(combo) <= {"codeword"}:
                continue
            friction = sum(CATALOGUE[m][0] for m in combo)
            cand = (friction, size, list(combo))
            if best is None or cand[:2] < best[:2]:
                best = cand
        if best:
            break
    return best[2] if best else ["manual_security_review"]


def select_methods(
    tier: Tier,
    claimed_kind: ClaimedKind | None = None,
    amount_inr: int | None = None,
    credential_request: bool = False,
    caps: Capabilities | None = None,
    config: dict | None = None,
) -> VerificationPlan:
    cfg = config or load_risk_config()
    caps = caps or Capabilities()

    if tier == "LOW":
        return VerificationPlan([], "Low risk: no extra verification needed. The interaction is logged.", "released")

    # Special routes (SPEC G)
    if claimed_kind in ("bank_official", "authority") and (credential_request or tier in ("HIGH", "CRITICAL")):
        methods: list[VerificationMethod] = ["end_call_and_call_official_number"]
        if tier == "CRITICAL":
            methods.append("manual_security_review")
        return VerificationPlan(
            methods,
            "The caller claims to be from a bank or authority"
            + (" and asked for a credential" if credential_request else "")
            + ". Your bank will never ask for OTP/PIN. End this call and call the number on your card or the official app.",
            "held",
            requires_review=tier == "CRITICAL",
            special_route="end_call",
            advice=["Report to the National Cyber Crime Helpline 1930 or cybercrime.gov.in."],
        )

    if claimed_kind == "family" and tier in ("HIGH", "CRITICAL"):
        fam: list[VerificationMethod] = ["trusted_contact", "codeword"]
        if tier == "CRITICAL":
            fam.append("manual_security_review")
        return VerificationPlan(
            fam,
            "A family-emergency request needs a call to the person's saved number plus the family codeword, not the number that called you.",
            "held",
            requires_review=tier == "CRITICAL",
            special_route="family_emergency",
        )

    if tier == "MEDIUM":
        m: list[VerificationMethod] = ["in_app_warning"]
        m.append("codeword" if caps.codeword else "out_of_band_device_confirm" if caps.registered_device else "dynamic_challenge")
        return VerificationPlan(
            m,
            "Medium risk: show a warning and offer a one-tap confirmation. The user may proceed; the decision is logged.",
            "pending",
        )

    if tier == "HIGH":
        picked = _cheapest_for_strength(REQUIRED_STRENGTH["HIGH"], caps)
        return VerificationPlan(
            picked,  # type: ignore[arg-type]
            "High risk: the transaction is held until a strong, independent confirmation passes. "
            "Callbacks go to the number on file, never the incoming number.",
            "held",
        )

    # CRITICAL: independent callback AND second approver (or manual review when none exists)
    crit: list[str] = []
    if caps.registered_device:
        crit.append("out_of_band_device_confirm")
    crit.append("independent_callback" if caps.callback_number else "dynamic_challenge")
    crit.append("second_approver" if caps.second_approver else "manual_security_review")
    if amount_inr is not None and amount_inr >= cfg["verification"]["cooling_off_amount_inr"]:
        crit.append("cooling_off_hold")
    return VerificationPlan(
        crit,  # type: ignore[arg-type]
        "Critical risk: the transaction is held, confirmed out-of-band and by a second approver, and sent to the review queue."
        + (" A cooling-off period applies because the amount is large." if "cooling_off_hold" in crit else ""),
        "held",
        requires_review=True,
    )


def apply_outcome(
    score: int, tier: Tier, outcome: VerificationOutcome, config: dict | None = None
) -> tuple[int, Tier, TransactionState]:
    """pass: -35, floored at (tier minimum - 1), released. fail: CRITICAL + blocked.
    no_response/pending: stays held and escalates one tier."""
    cfg = config or load_risk_config()
    if outcome == "pass":
        floor = max(0, tier_min(tier, cfg) - 1)
        new = max(score + cfg["verification"]["pass_delta"], floor, 0)
        new = min(new, score)
        return new, tier_for(new, cfg), "released"
    if outcome == "fail":
        new = max(score, tier_min("CRITICAL", cfg))
        return new, "CRITICAL", "blocked"
    if outcome == "no_response":
        nxt = TIER_ORDER[min(TIER_ORDER.index(tier) + 1, len(TIER_ORDER) - 1)]
        new = max(score, tier_min(nxt, cfg))
        return new, tier_for(new, cfg), "held"
    return score, tier, "held"  # pending: nothing changes


assert set(CATALOGUE) <= set(get_args(VerificationMethod))
