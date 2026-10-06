"""SHOULD: speaker consistency vs consented enrolled demo voices (Resemblyzer).
Caller embeddings are never persisted."""


def speaker_similarity(samples, sample_rate: int, enrolled_voice_id: str) -> float | None:
    """Cosine similarity in [-1, 1], or None when unavailable."""
    raise NotImplementedError
