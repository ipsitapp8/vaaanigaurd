"""PII redaction before persistence (SPEC section N).

Covers: emails, UPI IDs (partially masked), PAN, Aadhaar (12 digits), card/account numbers,
phone numbers and 4-8 digit OTP-like codes. Devanagari digits are treated as digits.
Amounts are preserved: numbers next to a currency marker are not treated as OTP codes.
"""
import re

_D = r"[0-9०-९]"  # ASCII + Devanagari digits

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_UPI = re.compile(r"\b([\w.\-]{2,})@([A-Za-z][A-Za-z0-9]{1,})\b")
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR = re.compile(rf"(?<!{_D})({_D}{{4}}[ -]?{_D}{{4}}[ -]?{_D}{{4}})(?!{_D})")
_CARD_ACCT = re.compile(rf"(?<!{_D})(?:{_D}[ -]?){{12,17}}{_D}(?!{_D})")
_PHONE = re.compile(rf"(?<![\w₹])(?:(?:\+|00)?91[ -]?)?[6-9६-९](?:{_D}[ -]?){{8}}{_D}(?!{_D})")
_CURRENCY_BEFORE = re.compile(r"(?:₹|rs\.?|inr|rupees?)\s*$", re.IGNORECASE)
_CURRENCY_AFTER = re.compile(r"^\s*(?:rupees?|rupaye|rupay|rs\b|inr|/-|hazaar|hajar|lakh|lac|crore|thousand|हज़ार|हजार|लाख|रुपये|रुपए)", re.IGNORECASE)
_CODE = re.compile(rf"(?<![\w.,₹]){_D}{{4,8}}(?![\w]|[.,]{_D})")


def _mask_upi(m: re.Match) -> str:
    user, handle = m.group(1), m.group(2)
    return f"{user[:2]}{'*' * max(2, len(user) - 2)}@{handle}"


def _code_sub(text: str):
    def repl(m: re.Match) -> str:
        before, after = text[: m.start()], text[m.end() :]
        if _CURRENCY_BEFORE.search(before) or _CURRENCY_AFTER.match(after):
            return m.group(0)  # an amount, not a code
        return "[CODE]"

    return repl


def redact(text: str) -> str:
    if not text:
        return text
    out = _EMAIL.sub("[EMAIL]", text)
    out = _UPI.sub(_mask_upi, out)
    out = _PAN.sub("[PAN]", out)
    out = _CARD_ACCT.sub("[ACCOUNT/CARD]", out)  # 13+ digits first, so a 16-digit card is not read as Aadhaar
    out = _AADHAAR.sub("[AADHAAR]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _CODE.sub(_code_sub(out), out)
    return out
