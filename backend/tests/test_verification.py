import pytest

from app.services.verification import CATALOGUE, Capabilities, apply_outcome, select_methods


def test_low_has_no_friction():
    p = select_methods("LOW")
    assert p.methods == [] and p.transaction_state == "released"


def test_medium_warns_and_lets_user_proceed():
    p = select_methods("MEDIUM")
    assert p.methods[0] == "in_app_warning"
    assert p.transaction_state == "pending"


def test_high_picks_lowest_friction_meeting_strength_4():
    p = select_methods("HIGH", claimed_kind="executive")
    assert p.methods == ["out_of_band_device_confirm"]
    assert p.transaction_state == "held"
    assert max(CATALOGUE[m][1] for m in p.methods) >= 4


def test_high_without_device_falls_back_to_callback():
    p = select_methods("HIGH", caps=Capabilities(registered_device=False))
    assert p.methods == ["independent_callback"]


def test_codeword_never_sole_method_above_medium():
    p = select_methods("HIGH", caps=Capabilities(registered_device=False, callback_number=False, second_approver=False))
    assert p.methods != ["codeword"]
    assert "codeword" not in p.methods or len(p.methods) > 1


def test_critical_callback_plus_second_approver_and_review():
    p = select_methods("CRITICAL", claimed_kind="executive", amount_inr=50_000)
    assert "independent_callback" in p.methods and "second_approver" in p.methods
    assert "cooling_off_hold" not in p.methods
    assert p.requires_review and p.transaction_state == "held"


def test_critical_cooling_off_for_large_amounts():
    p = select_methods("CRITICAL", claimed_kind="executive", amount_inr=480_000)
    assert "cooling_off_hold" in p.methods


def test_critical_without_second_approver_uses_manual_review():
    p = select_methods("CRITICAL", caps=Capabilities(second_approver=False))
    assert "manual_security_review" in p.methods


def test_bank_claim_with_credential_request_special_route():
    p = select_methods("CRITICAL", claimed_kind="bank_official", credential_request=True)
    assert p.methods[0] == "end_call_and_call_official_number"
    assert p.special_route == "end_call"
    assert "OTP" in p.reason
    assert any("1930" in a for a in p.advice or [])


def test_family_emergency_route():
    p = select_methods("HIGH", claimed_kind="family")
    assert p.methods == ["trusted_contact", "codeword"]
    assert p.transaction_state == "held"


def test_callback_methods_never_use_incoming_number_wording():
    assert "number on file" in select_methods("HIGH", claimed_kind="executive").reason


def test_pass_reduces_by_35_but_floors_one_below_tier_min():
    # HIGH (min 60): 72 - 35 = 37 but floor is 59
    assert apply_outcome(72, "HIGH", "pass") == (59, "MEDIUM", "released")
    # CRITICAL 95: 60, floor 79 -> 79
    assert apply_outcome(95, "CRITICAL", "pass")[0] == 79
    # MEDIUM 45: floor 29
    assert apply_outcome(45, "MEDIUM", "pass")[0:2] == (29, "LOW")
    # LOW never goes negative
    assert apply_outcome(10, "LOW", "pass")[0] == 0


def test_pass_never_increases_score():
    assert apply_outcome(60, "HIGH", "pass")[0] <= 60


def test_fail_is_critical_and_blocked():
    s, t, state = apply_outcome(65, "HIGH", "fail")
    assert (s, t, state) == (80, "CRITICAL", "blocked")


def test_no_response_stays_held_and_escalates_one_tier():
    assert apply_outcome(65, "HIGH", "no_response") == (80, "CRITICAL", "held")
    assert apply_outcome(35, "MEDIUM", "no_response") == (60, "HIGH", "held")
    assert apply_outcome(90, "CRITICAL", "no_response") == (90, "CRITICAL", "held")


@pytest.mark.parametrize("tier", ["MEDIUM", "HIGH", "CRITICAL"])
def test_methods_are_catalogued(tier):
    for m in select_methods(tier, claimed_kind="executive", amount_inr=200_000).methods:
        assert m in CATALOGUE
