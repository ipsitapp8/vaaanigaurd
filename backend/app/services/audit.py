"""Hash-chained audit log: entry_hash = sha256(prev_hash + payload_hash). verify_chain() detects tampering."""


def append_entry(actor: str, action: str, analysis_id: str | None, payload: dict) -> None:
    raise NotImplementedError


def verify_chain() -> tuple[bool, int | None]:
    """Return (valid, broken_at_seq)."""
    raise NotImplementedError
