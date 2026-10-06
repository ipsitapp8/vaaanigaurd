"""Lexicon (EN/HI/Hinglish) + optional zero-shot engine; amount and claimed-identity extraction.
Produces the scam (S), urgency (U) and financial (F) signals plus transcript highlights."""
from app.models.schemas import Highlight, SignalResult


def analyze_language(text: str, segments=None) -> tuple[SignalResult, SignalResult, SignalResult, list[Highlight]]:
    """Return (scam, urgency, financial, highlights)."""
    raise NotImplementedError


def extract_amount_inr(text: str) -> int | None:
    raise NotImplementedError


def extract_claimed_identity(text: str) -> str | None:
    raise NotImplementedError
