import pytest

from app.services.redaction import redact


@pytest.mark.parametrize(
    "raw,must_not_contain,must_contain",
    [
        ("Call me on 9876543210 now", "9876543210", "[PHONE]"),
        ("Call +91 98765 43210 now", "98765 43210", "[PHONE]"),
        ("my number is 98765-43210", "43210", "[PHONE]"),
        ("mail rakesh.k@kaveritextiles.in please", "rakesh.k", "[EMAIL]"),
        ("pay to rakesh123@oksbi", "rakesh123", "ra"),
        ("PAN is ABCDE1234F ok", "ABCDE1234F", "[PAN]"),
        ("aadhaar 1234 5678 9012", "5678", "[AADHAAR]"),
        ("aadhaar 123456789012", "123456789012", "[AADHAAR]"),
        ("card 4111 1111 1111 1111", "4111", "[ACCOUNT/CARD]"),
        ("account number 123456789012345", "123456789012345", "[ACCOUNT/CARD]"),
        ("OTP is 482913 batao", "482913", "[CODE]"),
        ("code 4821", "4821", "[CODE]"),
        ("OTP hai ४८२९१३", "४८२९१३", "[CODE]"),
        ("मेरा नंबर 9876543210 है", "9876543210", "[PHONE]"),
    ],
)
def test_pii_patterns_redacted(raw, must_not_contain, must_contain):
    out = redact(raw)
    assert must_not_contain not in out
    assert must_contain in out


def test_upi_is_partially_masked_keeps_handle():
    out = redact("send to rakesh123@oksbi")
    assert out.endswith("@oksbi") and out.startswith("send to ra") and "*" in out


def test_amounts_are_preserved():
    assert "₹4,80,000" in redact("transfer ₹4,80,000 now")
    assert "50000" in redact("bhejo Rs 50000 abhi")
    assert "50000" in redact("50000 rupaye bhejo")
    assert "480000" in redact("480000 rupees")


def test_hindi_text_untouched():
    s = "आपका अकाउंट आज बंद हो जाएगा"
    assert redact(s) == s


def test_plain_text_untouched_and_empty_safe():
    assert redact("") == ""
    assert redact("Namaste, card dispatch ho gaya") == "Namaste, card dispatch ho gaya"


def test_multiple_pii_in_one_string():
    out = redact("call 9876543210, otp 123456, mail a@b.com")
    assert "9876543210" not in out and "123456" not in out and "a@b.com" not in out
