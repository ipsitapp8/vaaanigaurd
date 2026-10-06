"""Orchestrates the analysis: runs engines concurrently with per-engine timeouts, builds per-segment
cumulative scores, fuses, selects verification. Returns AnalysisResponse."""
from app.models.schemas import AnalysisResponse, CallMetadata, TransactionContext


def run_pipeline(
    audio: bytes,
    context: TransactionContext | None,
    metadata: CallMetadata,
    scenario_id: str | None = None,
) -> AnalysisResponse:
    raise NotImplementedError
