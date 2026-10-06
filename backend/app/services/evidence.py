"""SHA-256 hashing of audio and analysis JSON; evidence report (JSON, optional printable HTML)."""


def sha256_hex(data: bytes) -> str:
    raise NotImplementedError


def build_report(analysis_id: str) -> dict:
    raise NotImplementedError
