"""Voice authenticity (V): 0.7*model_prob + 0.3*acoustic_heuristic, confidence scaled by audio quality.

PHASE 3. Until the deepfake model and acoustic heuristics exist this engine reports itself
unavailable (confidence 0), so V drops out of fusion and coverage falls accordingly. Nothing is faked.
A voice score alone can never push risk above MEDIUM (rule R4).
"""
from app.models.schemas import SignalResult


def analyze_voice(samples, sample_rate: int, quality) -> SignalResult:
    return SignalResult.unavailable("voice", source="fallback")
