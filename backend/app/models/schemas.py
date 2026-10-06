"""Pydantic models (SPEC sections E, H, I). Mirrored in frontend/src/types.ts."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SignalName = Literal["voice", "scam", "urgency", "financial", "identity", "context"]
SignalSource = Literal["model", "heuristic", "rules", "simulated", "fallback", "cached"]
Tier = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Channel = Literal["pstn", "voip", "whatsapp", "unknown"]
PaymentRail = Literal["UPI", "IMPS", "NEFT", "RTGS", "wallet"]
AnalysisStatus = Literal["analyzed", "verifying", "released", "held", "blocked", "in_review", "closed"]
VerificationOutcome = Literal["pending", "pass", "fail", "no_response"]
ReviewDecisionValue = Literal["pending", "approve", "reject", "escalate"]
TransactionState = Literal["pending", "held", "released", "blocked"]
VerificationMethod = Literal[
    "in_app_warning",
    "codeword",
    "out_of_band_device_confirm",
    "independent_callback",
    "dynamic_challenge",
    "trusted_contact",
    "second_approver",
    "manual_security_review",
    "cooling_off_hold",
    "end_call_and_call_official_number",  # special route: claimed bank/RBI/police
]
ComponentStatus = Literal["loaded", "fallback", "unavailable", "not_loaded"]


class Evidence(BaseModel):
    kind: str
    text: str
    span: tuple[float, float] | None = None
    weight: float = 0.0


class SignalResult(BaseModel):
    """Common interface implemented by every detection engine (SPEC section E)."""

    name: SignalName
    score: float = Field(ge=0, le=100)  # higher = riskier
    confidence: float = Field(ge=0, le=1)  # 0 = unavailable
    source: SignalSource
    evidence: list[Evidence] = []
    latency_ms: int = 0

    @classmethod
    def unavailable(cls, name: SignalName, source: SignalSource = "fallback") -> "SignalResult":
        return cls(name=name, score=0, confidence=0, source=source)


class CallMetadata(BaseModel):
    caller_number_masked: str
    in_directory: bool
    directory_name: str | None = None
    channel: Channel
    started_at: datetime


class TransactionContext(BaseModel):
    account_id: str
    amount_inr: int | None = None
    beneficiary_id: str | None = None
    beneficiary_is_new: bool = False
    beneficiary_age_days: int | None = None
    typical_amount_inr: int
    activity_window: tuple[int, int]  # hours, e.g. (9, 19)
    recent_txn_count_1h: int = 0
    payment_rail: PaymentRail | None = None


class SegmentScore(BaseModel):
    t_start: float
    t_end: float
    text_redacted: str
    cumulative_score: int
    tier: Tier


# --- API response shapes (SPEC section I) ---


class RuleTriggered(BaseModel):
    id: str
    effect: str
    reason: str


class Highlight(BaseModel):
    start_char: int
    end_char: int
    category: str


class RecommendedAction(BaseModel):
    tier: Tier
    methods: list[VerificationMethod]
    why: str
    transaction_state: TransactionState


class ComponentInfo(BaseModel):
    source: SignalSource
    note: str | None = None


class AnalysisResponse(BaseModel):
    id: str
    score: int
    tier: Tier
    coverage: float
    signals: list[SignalResult]
    contributions: dict[str, float]
    rules_triggered: list[RuleTriggered]
    reasons: list[str]
    recommended_action: RecommendedAction
    segments: list[SegmentScore]
    transcript_redacted: str
    highlights: list[Highlight]
    language: str | None = None
    latency_ms: dict[str, int]
    components: dict[str, ComponentInfo]
    is_synthetic: bool = True


class HealthComponents(BaseModel):
    asr: ComponentStatus
    deepfake_model: ComponentStatus
    speaker: ComponentStatus
    zero_shot: ComponentStatus
    db: ComponentStatus


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    device: Literal["cpu", "cuda"]
    components: HealthComponents
    force_fallback: bool


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: str


class ApiError(BaseModel):
    error: ErrorBody
