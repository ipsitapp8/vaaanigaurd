"""Language engine: lexicon (EN/HI/Hinglish), amount and claimed-identity extraction.

Produces the scam (S), urgency (U) and financial (F) signals plus highlights.
The zero-shot classifier (SHOULD) will be blended in later; the lexicon alone is the deterministic fallback.
"""
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.models.schemas import Evidence, Highlight, SignalResult
from app.services.directory import DirectoryEntry, find_by_text
from app.services.fusion import CREDENTIAL_EVIDENCE_KIND

LEXICON_PATH = Path(__file__).resolve().parents[1] / "data" / "lexicon.yaml"


# --------------------------------------------------------------------------------------
# Lexicon
# --------------------------------------------------------------------------------------
@dataclass
class Hit:
    category: str
    start: int
    end: int
    text: str
    weight: float


@lru_cache
def _lexicon() -> dict:
    with open(LEXICON_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    compiled: dict[str, list[tuple[re.Pattern, float]]] = {}
    for cat, spec in raw["categories"].items():
        default_w = spec["weight"]
        items = []
        for p in spec["patterns"]:
            pat, w = (p, default_w) if isinstance(p, str) else (p["p"], p.get("w", default_w))
            items.append((re.compile(pat, re.IGNORECASE), w))
        compiled[cat] = items
    return {
        "compiled": compiled,
        "negation": re.compile(raw["credential_negation"], re.IGNORECASE),
        "signals": raw["signals"],
        "speech_rate": raw["speech_rate"],
    }


def find_hits(text: str) -> list[Hit]:
    lex = _lexicon()
    hits: list[Hit] = []
    for cat, patterns in lex["compiled"].items():
        taken: list[tuple[int, int]] = []
        for rx, w in patterns:
            for m in rx.finditer(text):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue  # overlapping hit in the same category counts once
                if cat == "credential":
                    window = text[max(0, m.start() - 45) : min(len(text), m.end() + 10)]
                    if lex["negation"].search(window):
                        continue  # "never share your OTP" is a warning, not a request
                taken.append((m.start(), m.end()))
                hits.append(Hit(cat, m.start(), m.end(), m.group(0), w))
    return sorted(hits, key=lambda h: h.start)


def _category_values(hits: list[Hit]) -> dict[str, float]:
    """Diminishing returns: v = 1 - prod(1 - w_i) over a category's hits."""
    out: dict[str, float] = {}
    for h in hits:
        out[h.category] = 1 - (1 - out.get(h.category, 0.0)) * (1 - h.weight)
    return out


def _noisy_or(values: dict[str, float], multipliers: dict[str, float]) -> float:
    p = 1.0
    for cat, k in multipliers.items():
        p *= 1 - values.get(cat, 0.0) * k
    return 100 * (1 - p)


# --------------------------------------------------------------------------------------
# Amount extraction (rupees)
# --------------------------------------------------------------------------------------
_UNITS = {
    "ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "char": 4, "chaar": 4, "four": 4,
    "paanch": 5, "panch": 5, "five": 5, "chhe": 6, "chhah": 6, "che": 6, "six": 6, "saat": 7, "seven": 7,
    "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10, "ten": 10, "gyarah": 11, "eleven": 11,
    "barah": 12, "twelve": 12, "terah": 13, "thirteen": 13, "chaudah": 14, "fourteen": 14,
    "pandrah": 15, "fifteen": 15, "solah": 16, "sixteen": 16, "satrah": 17, "seventeen": 17,
    "atharah": 18, "eighteen": 18, "unees": 19, "nineteen": 19, "bees": 20, "twenty": 20,
    "tees": 30, "thirty": 30, "chalis": 40, "forty": 40, "pachaas": 50, "pachas": 50, "fifty": 50,
    "saath": 60, "sixty": 60, "sattar": 70, "seventy": 70, "assi": 80, "eighty": 80,
    "nabbe": 90, "ninety": 90,
}
_MULTS = {
    "sau": 100, "hundred": 100, "hazaar": 1_000, "hajar": 1_000, "thousand": 1_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
    "हज़ार": 1_000, "हजार": 1_000, "लाख": 100_000, "करोड़": 10_000_000,
}
_CURRENCY = {"₹", "rs", "rs.", "inr", "rupees", "rupee", "rupaye", "rupay", "rupaiye", "रुपये", "रुपए", "रुपया"}
_TOKEN = re.compile(r"₹|\d[\d,]*(?:\.\d+)?|[A-Za-zऀ-ॿ]+\.?")


def extract_amount_inr(text: str) -> int | None:
    """Largest rupee amount mentioned. Handles ₹2,50,000 / Rs 4,80,000 / 2.5 lakh / pachaas hazaar /
    4 lakh 80 hazaar. A run of numbers counts only if it has a multiplier or sits next to a currency marker."""
    tokens = [(m.group(0), m.start()) for m in _TOKEN.finditer(text)]
    kinds: list[str] = []
    for tok, _ in tokens:
        low = tok.lower()
        bare = low.rstrip(".")
        if low in _CURRENCY or bare in _CURRENCY:
            kinds.append("cur")
        elif low[0].isdigit():
            kinds.append("num")
        elif bare in _UNITS:
            kinds.append("unit")
        elif bare in _MULTS:
            kinds.append("mult")
        else:
            kinds.append("other")

    best: int | None = None
    i = 0
    while i < len(tokens):
        if kinds[i] not in ("num", "unit", "mult"):
            i += 1
            continue
        j = i
        while j < len(tokens) and kinds[j] in ("num", "unit", "mult"):
            j += 1
        run = range(i, j)
        has_mult = any(kinds[k] == "mult" for k in run)
        near_cur = (i > 0 and kinds[i - 1] == "cur") or (j < len(tokens) and kinds[j] == "cur")
        if has_mult or near_cur:
            total, current = 0.0, 0.0
            for k in run:
                low = tokens[k][0].lower().rstrip(".")
                if kinds[k] == "num":
                    current += float(low.replace(",", ""))
                elif kinds[k] == "unit":
                    current += _UNITS[low]
                elif low in ("sau", "hundred"):
                    current = (current or 1) * 100
                else:
                    total += (current or 1) * _MULTS[low]
                    current = 0.0
            value = int(round(total + current))
            if value > 0 and (best is None or value > best):
                best = value
        i = j
    return best


# --------------------------------------------------------------------------------------
# Claimed identity
# --------------------------------------------------------------------------------------
@dataclass
class ClaimedIdentity:
    name: str | None
    role: str | None
    kind: str  # bank_official | authority | executive | family | unknown
    directory_id: str | None = None
    directory_name: str | None = None
    raw: str = ""


_SELF_INTRO = [
    re.compile(r"\bmain\s+(?P<name>[A-Za-z]+)(?:\s+(?:sir|madam|ji))?(?:\s+(?P<org>[A-Za-z ]{3,40}?))?\s+(?:se\s+)?bol\s+(?:raha|rahi)\s+hoon", re.IGNORECASE),
    re.compile(r"\b(?P<name>[A-Za-z]+)\s+bol\s+(?:raha|rahi)\s+hoon", re.IGNORECASE),
    re.compile(r"\bthis\s+is\s+(?P<name>[A-Za-z]+)\b(?:\s+from\s+(?P<org>[A-Za-z ]{3,40}?))?(?:[,.]|$)", re.IGNORECASE),
    re.compile(r"\b(?:i\s+am|i'm)\s+(?P<name>[A-Za-z]+)\b(?:\s+from\s+(?P<org>[A-Za-z ]{3,40}?))?(?:[,.]|$)", re.IGNORECASE),
    re.compile(r"\b(?P<name>[A-Za-z]+)\s+(?:here|speaking)\b", re.IGNORECASE),
]
_STOP_NAMES = {"the", "a", "an", "calling", "your", "sir", "madam", "ji", "hello", "hi", "main", "from", "this", "that", "not", "just", "so", "very"}
_AUTHORITY = re.compile(r"\b(police|cbi|customs|income\s+tax|narcotics|cyber\s?(cell|crime)|enforcement)\b", re.IGNORECASE)
_BANKISH = re.compile(r"\b(bank|rbi|customer\s+care|security\s+department|fraud\s+department|kyc)\b", re.IGNORECASE)
_EXEC_ROLE = re.compile(r"\b(cfo|md|ceo|managing\s+director|director|chief\s+financial\s+officer|manager|boss)\b", re.IGNORECASE)
_FAMILY_ADDR = re.compile(r"\b(papa|mummy|mom|dad|maa|beta)\b|पापा|मम्मी", re.IGNORECASE)


def extract_claimed_identity(text: str) -> ClaimedIdentity | None:
    name = org = None
    for rx in _SELF_INTRO:
        m = rx.search(text)
        if m and m.group("name").lower() not in _STOP_NAMES:
            name = m.group("name")
            org = (m.groupdict().get("org") or "").strip() or None
            break

    entry: DirectoryEntry | None = find_by_text(name, org) or find_by_text(text)
    role_m = _EXEC_ROLE.search(text)
    role = role_m.group(0) if role_m else None

    if entry:
        kind = entry.kind
    elif _AUTHORITY.search(text):
        kind = "authority"
    elif _BANKISH.search(text):
        kind = "bank_official"
    elif _FAMILY_ADDR.search(text) and name:
        kind = "family"
    elif role:
        kind = "executive"
    elif name:
        kind = "unknown"
    else:
        return None

    return ClaimedIdentity(
        name=name or (entry.display_name if entry else None),
        role=role or (entry.role if entry else None),
        kind=kind,
        directory_id=entry.id if entry else None,
        directory_name=entry.display_name if entry else None,
        raw=(m.group(0) if name and m else role or ""),
    )


# --------------------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------------------
@dataclass
class LanguageAnalysis:
    scam: SignalResult
    urgency: SignalResult
    financial: SignalResult
    hits: list[Hit]
    amount_inr: int | None
    claimed: ClaimedIdentity | None
    credential_request: bool
    process_bypass_hits: int
    word_count: int = 0
    category_values: dict[str, float] = field(default_factory=dict)


def _confidence(word_count: int) -> float:
    return 0.0 if word_count == 0 else 0.3 if word_count < 5 else 0.6 if word_count < 15 else 0.9


def _evidence(hits: list[Hit], cats: list[str], kind_override: dict[str, str] | None = None) -> list[Evidence]:
    out = []
    for h in hits:
        if h.category in cats:
            kind = (kind_override or {}).get(h.category, h.category)
            out.append(Evidence(kind=kind, text=f"“{h.text.strip()}” ({h.category.replace('_', ' ')})", span=(float(h.start), float(h.end)), weight=h.weight))
    return out


def analyze_language(text: str, duration_s: float | None = None) -> LanguageAnalysis:
    """Score S, U, F on `text` (raw transcript, in memory only). `duration_s` enables the speech-rate bonus."""
    t0 = time.perf_counter()
    lex = _lexicon()
    sig_cfg = lex["signals"]
    words = re.findall(r"[\wऀ-ॿ₹]+", text)
    n_words = len(words)
    conf = _confidence(n_words)

    hits = find_hits(text)
    values = _category_values(hits)
    amount = extract_amount_inr(text)
    claimed = extract_claimed_identity(text) if text.strip() else None

    cred_hits = [h for h in hits if h.category in ("credential", "remote_access")]
    credential_request = bool(cred_hits)

    s_score = _noisy_or(values, sig_cfg["scam"])
    u_score = _noisy_or(values, sig_cfg["urgency"])
    if duration_s and duration_s > 0 and n_words >= 8:
        wps = n_words / duration_s
        sr = lex["speech_rate"]
        u_score = min(100.0, u_score + max(0.0, min(sr["max_bonus"], (wps - sr["baseline_words_per_sec"]) * sr["bonus_per_wps"])))

    f_vals = dict(values)
    if amount:
        f_vals["amount"] = sig_cfg["amount_found_value"]
    f_mult = dict(sig_cfg["financial"])
    f_mult["amount"] = 1.0
    f_score = _noisy_or(f_vals, f_mult)

    latency = int((time.perf_counter() - t0) * 1000)

    f_evidence = _evidence(hits, ["payment", "credential", "remote_access"], {"credential": CREDENTIAL_EVIDENCE_KIND, "remote_access": CREDENTIAL_EVIDENCE_KIND})
    if amount:
        f_evidence.append(Evidence(kind="amount", text=f"A payment amount of ₹{_fmt_inr(amount)} was mentioned.", span=None, weight=0.5))
    if credential_request:
        f_evidence.insert(0, Evidence(kind=CREDENTIAL_EVIDENCE_KIND, text="The caller asked for an OTP, PIN, password or remote access.", span=None, weight=1.0))

    def mk(name, score, evidence):
        return SignalResult(name=name, score=round(score, 1), confidence=conf, source="rules", evidence=evidence, latency_ms=latency)

    return LanguageAnalysis(
        scam=mk("scam", s_score, _evidence(hits, list(sig_cfg["scam"]))),
        urgency=mk("urgency", u_score, _evidence(hits, list(sig_cfg["urgency"]))),
        financial=mk("financial", f_score, f_evidence),
        hits=hits,
        amount_inr=amount,
        claimed=claimed,
        credential_request=credential_request,
        process_bypass_hits=sum(1 for h in hits if h.category == "process_bypass"),
        word_count=n_words,
        category_values=values,
    )


def find_highlights(text: str) -> list[Highlight]:
    """Highlight spans for the UI, computed on the *redacted* transcript so offsets line up."""
    return [Highlight(start_char=h.start, end_char=h.end, category=h.category) for h in find_hits(text) if h.category != "credential_mention"]


def _fmt_inr(n: int) -> str:
    """Indian digit grouping: 250000 -> 2,50,000."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def format_inr(n: int) -> str:
    return _fmt_inr(n)

