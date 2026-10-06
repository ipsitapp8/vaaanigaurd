"""PII redaction before persistence: phone, account/card, OTP-like codes, Aadhaar, PAN, UPI IDs, emails."""


def redact(text: str) -> str:
    raise NotImplementedError
