"""SHA-256 hashing for evidence records. The full evidence report is built in a later phase."""
import hashlib
import json


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> str:
    """Stable serialization so the same content always hashes the same."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def hash_json(obj) -> str:
    return sha256_hex(canonical_json(obj).encode("utf-8"))


def build_report(analysis_id: str) -> dict:
    raise NotImplementedError("evidence report arrives with persistence (Phase 3)")
