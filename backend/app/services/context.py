"""Context anomaly signal (C): amount ratio, new beneficiary, time window, velocity, process bypass."""
from app.models.schemas import SignalResult, TransactionContext


def analyze_context(ctx: TransactionContext | None, process_bypass_hits: int = 0, hour: int | None = None) -> SignalResult:
    raise NotImplementedError
