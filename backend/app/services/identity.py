"""Identity/channel mismatch signal (I): claimed identity vs directory and channel (+speaker sim)."""
from app.models.schemas import CallMetadata, SignalResult


def analyze_identity(
    claimed_identity: str | None,
    metadata: CallMetadata,
    request_kind: str | None = None,
    speaker_similarity: float | None = None,
) -> SignalResult:
    raise NotImplementedError
