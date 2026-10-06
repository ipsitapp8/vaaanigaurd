import pytest

from app.services.fusion import CREDENTIAL_EVIDENCE_KIND
from app.services.language import analyze_language, extract_amount_inr, extract_claimed_identity, find_highlights, format_inr


@pytest.mark.parametrize(
    "text,expected",
    [
        ("transfer ₹2,50,000 now", 250000),
        ("Rs. 4,80,000 vendor ko", 480000),
        ("send 2.5 lakh today", 250000),
        ("pachaas hazaar bhejo", 50000),
        ("4 lakh 80 hazaar", 480000),
        ("chaar lakh assi hazaar rupaye", 480000),
        ("one lakh twenty thousand", 120000),
        ("50000 rupees", 50000),
        ("Rs 500 only", 500),
        ("₹6,20,000 to a new vendor", 620000),
        ("ek sau pachaas rupaye", 150),
        ("paanch sau rupaye", 500),
        ("2 crore", 20_000_000),
    ],
)
def test_amount_parser(text, expected):
    assert extract_amount_inr(text) == expected


@pytest.mark.parametrize("text", ["OTP bata do", "call me at 9876543210", "main teen din mein aata hoon", "do minute ruko", ""])
def test_amount_parser_no_false_positives(text):
    assert extract_amount_inr(text) is None


def test_amount_picks_largest():
    assert extract_amount_inr("pehle ₹5,000 phir 2 lakh bhejo") == 200000


def test_format_inr_grouping():
    assert format_inr(250000) == "2,50,000" and format_inr(480000) == "4,80,000" and format_inr(999) == "999" and format_inr(10_000_000) == "1,00,00,000"


def has_cat(a, cat):
    return any(h.category == cat for h in a.hits)


@pytest.mark.parametrize(
    "text,cat",
    [
        ("Please tell me the OTP you received", "credential"),
        ("aap apna OTP batao jo phone par aaya", "credential"),
        ("ओटीपी बताइए अभी", "credential"),
        ("share your UPI PIN with me", "credential"),
        ("aapka account aaj band ho jayega", "account_threat"),
        ("your KYC will expire today", "account_threat"),
        ("this is a digital arrest", "account_threat"),
        ("abhi turant karo", "urgency"),
        ("do it immediately", "urgency"),
        ("जल्दी करो", "urgency"),
        ("RBI officer speaking", "authority"),
        ("kisi ko mat batana", "secrecy"),
        ("don't tell anyone about this", "secrecy"),
        ("GPay karo is number pe", "payment"),
        ("please transfer the amount", "payment"),
        ("install AnyDesk on your phone", "remote_access"),
        ("skip the usual approval", "process_bypass"),
        ("accounts ko mat batana", "process_bypass"),
        ("naya account hai", "process_bypass"),
        ("papa accident ho gaya hai", "emotional_lever"),
    ],
)
def test_lexicon_hits_en_hi_hinglish(text, cat):
    assert has_cat(analyze_language(text), cat), (text, [(h.category, h.text) for h in analyze_language(text).hits])


@pytest.mark.parametrize(
    "text",
    [
        "Never share your OTP with anyone, including bank staff.",
        "do not share your PIN or OTP with anybody",
        "OTP kisi ko mat batana, bank kabhi nahi poochta",
    ],
)
def test_warnings_about_otp_are_not_credential_requests(text):
    a = analyze_language(text)
    assert not a.credential_request
    assert not has_cat(a, "credential")


def test_credential_request_sets_evidence_kind_for_r1():
    a = analyze_language("Abhi turant apna OTP batao")
    assert a.credential_request
    assert any(e.kind == CREDENTIAL_EVIDENCE_KIND for e in a.financial.evidence)
    assert a.financial.score >= 85


def test_remote_access_counts_as_credential_request():
    assert analyze_language("please install AnyDesk now").credential_request


def test_benign_call_scores_low():
    a = analyze_language("Namaste, aapka naya debit card dispatch ho gaya hai aur teen din mein ghar pahunch jayega. Dhanyavaad.")
    assert a.scam.score < 15 and a.urgency.score < 15 and a.financial.score < 15


def test_diminishing_returns_per_category():
    one = analyze_language("abhi karo please do it for me now").urgency.score
    many = analyze_language("abhi turant jaldi immediately urgent asap right now").urgency.score
    assert many > one and many < 100


def test_confidence_scales_with_transcript_length():
    assert analyze_language("").financial.confidence == 0
    assert analyze_language("OTP batao").financial.confidence == pytest.approx(0.3)
    assert analyze_language("abhi OTP batao aapka account band ho jayega warna problem hogi bahut badi aur phir hum kuch nahi kar sakte").scam.confidence == pytest.approx(0.9)


def test_speech_rate_bonus_raises_urgency():
    text = "abhi karo " + "word " * 40
    slow = analyze_language(text, duration_s=40).urgency.score
    fast = analyze_language(text, duration_s=8).urgency.score
    assert fast > slow


def test_amount_adds_to_financial_with_inr_grouping_in_evidence():
    a = analyze_language("please send ₹2,50,000 to the vendor today")
    assert a.amount_inr == 250000
    assert any("2,50,000" in e.text for e in a.financial.evidence)


def test_highlights_cover_matches_on_given_text():
    t = "abhi OTP batao aur kisi ko mat batana"
    hl = find_highlights(t)
    cats = {h.category for h in hl}
    assert {"urgency", "credential", "secrecy"} <= cats
    assert all(0 <= h.start_char < h.end_char <= len(t) for h in hl)


def test_claimed_identity_bank():
    c = extract_claimed_identity("Hello, main Bharat National Bank ke security department se bol raha hoon")
    assert c and c.kind == "bank_official" and c.directory_id == "bnb_customer_care"


def test_claimed_identity_executive_by_name():
    c = extract_claimed_identity("Priya, main Rakesh bol raha hoon, board meeting mein hoon")
    assert c and c.kind == "executive" and c.directory_id == "rakesh_md"


def test_claimed_identity_cfo_english():
    c = extract_claimed_identity("Good afternoon, this is Anil from the finance office, the CFO.")
    assert c and c.kind == "executive" and c.directory_id == "anil_cfo"


def test_claimed_identity_family():
    c = extract_claimed_identity("Papa, main Aarav bol raha hoon, accident ho gaya")
    assert c and c.kind == "family" and c.directory_id == "aarav_son"


def test_claimed_identity_authority_unknown_directory():
    c = extract_claimed_identity("I am calling from the Mumbai police cyber cell")
    assert c and c.kind == "authority" and c.directory_id is None


def test_no_claim_returns_none():
    assert extract_claimed_identity("Please process the invoice") is None


@pytest.mark.parametrize("text", ["Apka naya card dispatch ho gaya", "APK", "Hello APK sir, aapka account", "Isbhaare main Apka koi action lean ki zaroorat nahi hai"])
def test_asr_noise_like_apk_is_not_a_remote_access_request(text):
    # Whisper renders "aapka" as "APK"; a bare token must never trigger R1.
    assert not analyze_language(text).credential_request


def test_explicit_install_apk_is_remote_access():
    assert analyze_language("please install this APK on your phone").credential_request