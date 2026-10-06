from datetime import datetime

import pytest

from app.models.schemas import CallMetadata, TransactionContext
from app.services.context import analyze_context
from app.services.identity import analyze_identity
from app.services.language import ClaimedIdentity


def meta(in_dir=False, name=None, channel="pstn"):
    return CallMetadata(caller_number_masked="+91 9XXXX XX123", in_directory=in_dir, directory_name=name, channel=channel, started_at=datetime(2026, 10, 6, 15, 0))


def ctx(**kw):
    base = dict(account_id="KTX-0001", typical_amount_inr=60000, activity_window=(9, 19))
    base.update(kw)
    return TransactionContext(**base)


rakesh = ClaimedIdentity(name="Rakesh", role="MD", kind="executive", directory_id="rakesh_md", directory_name="Rakesh Menon (MD, Kaveri Textiles)")
bank = ClaimedIdentity(name="Sunita", role=None, kind="bank_official", directory_id="bnb_customer_care", directory_name="Bharat National Bank – Customer Care")


# ---- context ----
def test_context_unavailable_without_transaction():
    r = analyze_context(None)
    assert r.confidence == 0


def test_context_benign_routine_payment():
    r = analyze_context(ctx(amount_inr=62000), hour=14)
    assert r.score < 5 and r.confidence == 0.9


def test_context_amount_ratio_is_log_scaled_and_cited():
    r = analyze_context(ctx(amount_inr=372000, typical_amount_inr=60000))
    assert any("6.2×" in e.text for e in r.evidence)
    assert 40 < r.score < 55
    assert analyze_context(ctx(amount_inr=600000)).score > r.score


def test_context_new_young_beneficiary_off_hours_bypass_stack():
    r = analyze_context(ctx(amount_inr=480000, beneficiary_is_new=True, beneficiary_age_days=1, recent_txn_count_1h=3), process_bypass_hits=2, hour=23)
    assert r.score == 100
    kinds = {e.kind for e in r.evidence}
    assert {"amount", "beneficiary", "beneficiary_age", "time", "velocity", "process_bypass"} <= kinds


def test_context_without_amount_has_lower_confidence():
    assert analyze_context(ctx(), hour=12).confidence == 0.5


# ---- identity ----
def test_identity_matching_directory_number_is_low():
    r = analyze_identity(bank, meta(True, bank.directory_name), payment_request=False)
    assert r.score <= 5


def test_identity_bank_over_voip_asking_credential_is_very_high():
    r = analyze_identity(bank, meta(False, None, "voip"), credential_request=True)
    assert r.score >= 85


def test_identity_executive_unknown_number_whatsapp_payment():
    r = analyze_identity(rakesh, meta(False, None, "whatsapp"), payment_request=True)
    assert 65 <= r.score <= 85


def test_identity_unclaimed_unknown_number_is_mild_and_low_confidence():
    r = analyze_identity(None, meta(False))
    assert 0 < r.score < 40 and r.confidence <= 0.5


def test_identity_number_belongs_to_someone_else():
    r = analyze_identity(rakesh, meta(True, "Anil Verma (CFO, Kaveri Textiles)"), payment_request=True)
    assert r.score >= 35


def test_speaker_match_discount_is_capped_at_10():
    base = analyze_identity(rakesh, meta(False, None, "whatsapp"), payment_request=True).score
    matched = analyze_identity(rakesh, meta(False, None, "whatsapp"), payment_request=True, speaker_similarity=0.97).score
    assert base - matched == pytest.approx(10, abs=0.1)


def test_speaker_mismatch_raises_score():
    base = analyze_identity(rakesh, meta(False, None, "whatsapp")).score
    assert analyze_identity(rakesh, meta(False, None, "whatsapp"), speaker_similarity=0.4).score > base
