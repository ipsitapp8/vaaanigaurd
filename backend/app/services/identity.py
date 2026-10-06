"""Identity/channel mismatch signal (I): claimed identity vs directory and channel (+speaker sim).

Heuristic/Rules. A matching voice barely lowers risk (at most 10 points): clones are built to match.
"""
import time

from app.models.schemas import CallMetadata, Evidence, SignalResult
from app.services.language import ClaimedIdentity

UNOFFICIAL_CHANNELS = ("voip", "whatsapp", "unknown")
SPEAKER_MISMATCH_BELOW = 0.75
SPEAKER_MATCH_ABOVE = 0.85
MAX_SPEAKER_DISCOUNT = 10


def analyze_identity(
    claimed: ClaimedIdentity | None,
    metadata: CallMetadata,
    payment_request: bool = False,
    credential_request: bool = False,
    speaker_similarity: float | None = None,
) -> SignalResult:
    t0 = time.perf_counter()
    score = 0.0
    ev: list[Evidence] = []

    def add(points: float, kind: str, text: str):
        nonlocal score
        score += points
        ev.append(Evidence(kind=kind, text=text, span=None, weight=points / 100))

    risky_request = payment_request or credential_request

    if claimed is None:
        if metadata.in_directory:
            score = 5
            ev.append(Evidence(kind="identity", text="The caller's number is in the directory and no conflicting identity claim was made.", weight=0.05))
        else:
            add(20, "number", "The caller's number is not in the directory and they did not clearly identify themselves.")
            if metadata.channel in UNOFFICIAL_CHANNELS:
                add(10, "channel", f"The call came over {metadata.channel.upper()}.")
        confidence = 0.5
    else:
        who = claimed.directory_name or claimed.name or "the claimed person"
        number_matches = metadata.in_directory and (
            claimed.directory_name is None or metadata.directory_name == claimed.directory_name
        )
        if number_matches:
            ev.append(Evidence(kind="identity", text=f"The caller's number matches the directory entry for {who}.", weight=0.0))
        elif metadata.in_directory:
            add(35, "number", f"The number belongs to {metadata.directory_name}, not {who}.")
        elif claimed.directory_id:
            add(40, "number", f"The caller claims to be {who} but is calling from a number that is not in the directory.")
        else:
            add(35, "number", "The caller claims an identity that is not in the directory and is calling from an unknown number.")

        if claimed.kind in ("bank_official", "authority") and metadata.channel in UNOFFICIAL_CHANNELS and not number_matches:
            add(30, "channel", f"Banks and officials do not call from {metadata.channel.upper()} numbers.")
        elif claimed.kind in ("executive", "family") and metadata.channel in UNOFFICIAL_CHANNELS and not number_matches:
            add(10, "channel", f"The call came over {metadata.channel.upper()}, not the registered number.")

        if claimed.kind == "bank_official" and risky_request and not number_matches:
            add(25, "role", "A bank official asked for a payment or credential over a call, which banks do not do.")
        elif claimed.kind == "authority" and risky_request:
            add(25, "role", "Police, tax and customs officers do not collect money or credentials over the phone.")
        elif claimed.kind == "executive" and payment_request and not number_matches:
            add(25, "role", f"A payment request from an unregistered number claiming to be {who}.")
        elif claimed.kind == "family" and payment_request and not number_matches:
            add(20, "role", "An urgent payment request from an unrecognised number claiming to be a family member.")
        confidence = 0.85

    if speaker_similarity is not None:
        if speaker_similarity < SPEAKER_MISMATCH_BELOW:
            add(25, "speaker", f"The voice does not match the enrolled speaker (similarity {speaker_similarity:.2f}).")
        elif speaker_similarity >= SPEAKER_MATCH_ABOVE and score > 0:
            discount = min(MAX_SPEAKER_DISCOUNT, score)
            score -= discount
            ev.append(Evidence(kind="speaker", text="The voice matches the enrolled speaker, which lowers risk only slightly because clones are built to match.", weight=0.0))

    return SignalResult(
        name="identity",
        score=round(max(0.0, min(100.0, score)), 1),
        confidence=confidence,
        source="rules",
        evidence=ev,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )
