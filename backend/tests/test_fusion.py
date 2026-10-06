import pytest

from app.models.schemas import Evidence, SignalResult
from app.services.fusion import CREDENTIAL_EVIDENCE_KIND, fuse, tier_for


def sig(name, score, conf=1.0, evidence=None, source="rules"):
    return SignalResult(name=name, score=score, confidence=conf, source=source, evidence=evidence or [])


def full(v=0, s=0, u=0, f=0, c=0, i=0, **conf):
    vals = dict(voice=v, scam=s, urgency=u, financial=f, context=c, identity=i)
    return [sig(n, x, conf.get(n, 1.0)) for n, x in vals.items()]


@pytest.mark.parametrize(
    "score,tier",
    [(0, "LOW"), (29, "LOW"), (30, "MEDIUM"), (59, "MEDIUM"), (60, "HIGH"), (79, "HIGH"), (80, "CRITICAL"), (100, "CRITICAL")],
)
def test_tier_boundaries(score, tier):
    assert tier_for(score) == tier


def test_weighted_average_all_available():
    r = fuse(full(v=50, s=50, u=50, f=50, c=50, i=50))
    assert r.score == 50 and r.coverage == 1.0


def test_unavailable_signal_drops_out_and_lowers_coverage():
    r = fuse(full(v=100, s=0, u=0, f=0, c=0, i=0, voice=0.0))
    assert r.score == 0  # voice has confidence 0, so its 100 is ignored
    assert r.coverage == 0.8


def test_missing_signal_equals_zero_confidence():
    sigs = [sig(n, 40) for n in ("scam", "urgency", "financial", "context", "identity")]
    assert fuse(sigs).score == 40
    assert fuse(sigs).coverage == 0.8


def test_confidence_scales_weight():
    # voice 100 at confidence 0.5 vs others 0
    r = fuse(full(v=100, voice=0.5))
    assert r.score == round(100 * 0.2 * 0.5 / (0.2 * 0.5 + 0.8))
    assert r.coverage == pytest.approx(0.9)


def test_no_signals_returns_low_with_flag():
    r = fuse([])
    assert r.score == 0 and r.tier == "LOW" and r.coverage == 0 and r.flags


def test_r1_credential_request_floors_at_85():
    f = sig("financial", 40, evidence=[Evidence(kind=CREDENTIAL_EVIDENCE_KIND, text="asked for OTP", weight=1)])
    r = fuse([f] + [sig(n, 10) for n in ("voice", "scam", "urgency", "context")])
    assert r.score >= 85 and r.tier == "CRITICAL"
    assert [t.id for t in r.rules_triggered][0] == "R1"


def test_r1_not_defeated_by_single_signal_cap():
    f = sig("financial", 90, evidence=[Evidence(kind=CREDENTIAL_EVIDENCE_KIND, text="asked for OTP", weight=1)])
    others = [sig(n, 0) for n in ("voice", "scam", "urgency", "context", "identity")]
    r = fuse([f] + others)
    assert r.tier == "CRITICAL"
    assert not any(t.id == "R4" for t in r.rules_triggered)


def test_r2_context_led_is_detector_independent():
    # voice looks genuine and low-confidence; context + finance + identity are bad
    sigs = [sig("voice", 38, 0.3), sig("scam", 20), sig("urgency", 20), sig("financial", 80), sig("context", 85), sig("identity", 75)]
    r = fuse(sigs)
    assert any(t.id == "R2" for t in r.rules_triggered)
    assert r.score >= 70 and r.tier in ("HIGH", "CRITICAL")


def test_r2_via_urgency_branch():
    sigs = [sig("financial", 60), sig("context", 70), sig("urgency", 50), sig("identity", 0)]
    assert any(t.id == "R2" for t in fuse(sigs).rules_triggered)


def test_r2_not_triggered_below_thresholds():
    sigs = [sig("financial", 59), sig("context", 90), sig("urgency", 90), sig("identity", 90)]
    assert not any(t.id == "R2" for t in fuse(sigs).rules_triggered)


def test_r3_voice_plus_money_adds_8():
    base = fuse(full(v=60, f=60, c=0)).score
    r = fuse(full(v=70, f=60, c=0))
    assert any(t.id == "R3" for t in r.rules_triggered)
    no_rule = fuse(full(v=70, f=60, c=0, voice=0.4))  # confidence too low -> no R3
    assert not any(t.id == "R3" for t in no_rule.rules_triggered)
    assert r.score > base


def test_r3_requires_financial():
    assert not any(t.id == "R3" for t in fuse(full(v=90, f=59)).rules_triggered)


def test_r4_voice_alone_capped_below_high():
    r = fuse(full(v=100, s=5, u=5, f=5, c=5, i=5))
    assert r.score <= 59
    # and the invariant: a voice score alone never pushes above MEDIUM
    r = fuse([sig("voice", 100)] + [sig(n, 0) for n in ("scam", "urgency", "financial", "context")])
    assert r.tier in ("LOW", "MEDIUM")


def test_r4_cap_applies_and_is_recorded():
    # a lone high signal with nothing else available: base is 100, cap pulls it to 59
    r = fuse([sig("voice", 100)])
    assert r.score == 59
    assert any(t.id == "R4" for t in r.rules_triggered)


def test_r4_not_applied_when_two_signals_high():
    r = fuse([sig("voice", 90), sig("scam", 90)])
    assert r.score == 90 and not any(t.id == "R4" for t in r.rules_triggered)


def test_r4_not_applied_when_other_signal_is_mid():
    r = fuse([sig("voice", 100), sig("scam", 40)])
    assert not any(t.id == "R4" for t in r.rules_triggered)


def test_r5_low_coverage_flag_and_min_tier():
    # only context (0.20 of total weight) is available -> coverage 0.2
    r = fuse([sig("context", 45)])
    assert r.coverage == pytest.approx(0.2)
    assert any(t.id == "R5" for t in r.rules_triggered)
    assert r.tier in ("MEDIUM", "HIGH", "CRITICAL")
    assert "Insufficient evidence" in r.flags[0]


def test_r5_not_triggered_with_full_coverage_or_low_score():
    assert not any(t.id == "R5" for t in fuse(full(c=45, s=45)).rules_triggered)
    assert not any(t.id == "R5" for t in fuse([sig("context", 39)]).rules_triggered)


def test_clamping_with_r1_and_r3():
    f = sig("financial", 100, evidence=[Evidence(kind=CREDENTIAL_EVIDENCE_KIND, text="otp", weight=1)])
    r = fuse([sig("voice", 100), f, sig("scam", 100), sig("urgency", 100), sig("context", 100), sig("identity", 100)])
    assert r.score == 100


def test_contributions_sum_to_100_and_follow_weights():
    r = fuse(full(v=50, s=50, u=50, f=50, c=50, i=50))
    assert sum(r.contributions.values()) == pytest.approx(100, abs=0.5)
    assert r.contributions["voice"] == pytest.approx(20, abs=0.1)
    assert r.contributions["urgency"] == pytest.approx(10, abs=0.1)


def test_reasons_include_specific_evidence():
    ev = [Evidence(kind="amount", text="₹2,50,000 is 6.2× this account's typical transfer", weight=1.0)]
    sigs = full(f=70, u=40, i=40)
    sigs[4] = sig("context", 80, evidence=ev)
    r = fuse(sigs)
    assert any("6.2×" in x for x in r.reasons)
    assert len(r.reasons) <= 4
