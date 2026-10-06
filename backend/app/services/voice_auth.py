"""Voice authenticity: 0.7*model_prob + 0.3*acoustic_heuristic; confidence scaled by audio quality.
Alone it can never push risk above MEDIUM. Phase 3."""
from app.models.schemas import SignalResult


def analyze_voice(samples, sample_rate: int, quality) -> SignalResult:
    raise NotImplementedError
