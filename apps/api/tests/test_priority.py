"""Tests for `app.pipeline.priority` — the explainable priority formula.

Every case here is hand-computed against AGENTS.md's formula:

    priority = 0.40*severity_score + 0.30*log1p(cluster_size)/log1p(CLUSTER_CAP)
             + 0.20*safety_flag + 0.10*sla_age_factor

so a regression here means the *number*, not just the code, changed.
"""

from __future__ import annotations

import math

import pytest

from app.pipeline.priority import (
    CLUSTER_CAP,
    SLA_AGE_SATURATION_HOURS,
    compute_priority,
    frequency_score,
    sla_age_factor,
    severity_to_unit,
)


def test_severity_to_unit_endpoints_and_midpoint():
    assert severity_to_unit(1) == 0.0
    assert severity_to_unit(5) == 1.0
    assert severity_to_unit(3) == pytest.approx(0.5)


def test_severity_to_unit_clamps_out_of_range():
    assert severity_to_unit(0) == 0.0
    assert severity_to_unit(99) == 1.0


def test_frequency_score_single_complaint_is_not_zero():
    # A brand-new, unclustered complaint (cluster_size=1) should still
    # register some frequency signal, not exactly 0 — log1p(1) > 0.
    score = frequency_score(1)
    assert 0.0 < score < 0.3


def test_frequency_score_saturates_at_cluster_cap():
    assert frequency_score(CLUSTER_CAP) == pytest.approx(1.0)
    # Exceeding the cap must not exceed 1.0 (formula would overshoot
    # without clamping since log1p(x>cap)/log1p(cap) > 1).
    assert frequency_score(CLUSTER_CAP * 3) == pytest.approx(1.0)


def test_frequency_score_matches_hand_computation():
    # log1p(3) / log1p(20)
    expected = math.log1p(3) / math.log1p(20)
    assert frequency_score(3, cluster_cap=20) == pytest.approx(expected)


def test_frequency_score_clamps_below_one():
    assert frequency_score(0) == frequency_score(1)


def test_sla_age_factor_zero_at_or_before_report_time():
    assert sla_age_factor(0) == 0.0
    assert sla_age_factor(-5) == 0.0


def test_sla_age_factor_saturates_at_threshold():
    assert sla_age_factor(SLA_AGE_SATURATION_HOURS) == pytest.approx(1.0)
    assert sla_age_factor(SLA_AGE_SATURATION_HOURS * 2) == pytest.approx(1.0)


def test_sla_age_factor_linear_midpoint():
    assert sla_age_factor(36, saturation_hours=72) == pytest.approx(0.5)


def test_compute_priority_minimum_case():
    # Lowest severity, unclustered, no safety flag, brand new.
    result = compute_priority(
        severity=1, cluster_size=1, safety_flag=False, age_hours=0
    )
    assert result.breakdown.severity == pytest.approx(0.0)
    assert result.breakdown.safety == pytest.approx(0.0)
    assert result.breakdown.sla_age == pytest.approx(0.0)
    # Only the frequency term contributes anything.
    expected_frequency = 0.30 * (math.log1p(1) / math.log1p(20))
    assert result.breakdown.frequency == pytest.approx(expected_frequency)
    assert result.priority_score == pytest.approx(expected_frequency)


def test_compute_priority_maximum_case_saturates_at_one():
    result = compute_priority(
        severity=5,
        cluster_size=CLUSTER_CAP,
        safety_flag=True,
        age_hours=SLA_AGE_SATURATION_HOURS,
    )
    assert result.breakdown.severity == pytest.approx(0.40)
    assert result.breakdown.frequency == pytest.approx(0.30)
    assert result.breakdown.safety == pytest.approx(0.20)
    assert result.breakdown.sla_age == pytest.approx(0.10)
    assert result.priority_score == pytest.approx(1.0)


def test_compute_priority_mid_case_matches_hand_computation():
    # severity=3 -> unit 0.5 -> term 0.20
    # cluster_size=3 (the recurring threshold) -> term 0.30*log1p(3)/log1p(20)
    # safety_flag=False -> term 0
    # age_hours=36 (half of 72h saturation) -> term 0.05
    result = compute_priority(
        severity=3, cluster_size=3, safety_flag=False, age_hours=36
    )

    expected_severity = 0.40 * 0.5
    expected_frequency = 0.30 * (math.log1p(3) / math.log1p(20))
    expected_safety = 0.0
    expected_sla = 0.10 * 0.5
    expected_total = (
        expected_severity + expected_frequency + expected_safety + expected_sla
    )

    assert result.breakdown.severity == pytest.approx(expected_severity)
    assert result.breakdown.frequency == pytest.approx(expected_frequency)
    assert result.breakdown.safety == pytest.approx(expected_safety)
    assert result.breakdown.sla_age == pytest.approx(expected_sla)
    assert result.priority_score == pytest.approx(expected_total)
    assert result.priority_score == pytest.approx(0.3866, abs=1e-3)


def test_breakdown_terms_always_sum_to_priority_score():
    cases = [
        (1, 1, False, 0),
        (5, 1, True, 10),
        (2, 7, False, 200),
        (4, 20, True, 72),
    ]
    for severity, cluster_size, safety_flag, age_hours in cases:
        result = compute_priority(
            severity=severity,
            cluster_size=cluster_size,
            safety_flag=safety_flag,
            age_hours=age_hours,
        )
        b = result.breakdown
        assert (b.severity + b.frequency + b.safety + b.sla_age) == pytest.approx(
            result.priority_score
        )


def test_priority_score_always_in_unit_interval():
    for severity in (1, 2, 3, 4, 5):
        for cluster_size in (1, 3, 20, 500):
            for safety_flag in (True, False):
                for age_hours in (-10, 0, 36, 72, 1000):
                    result = compute_priority(
                        severity=severity,
                        cluster_size=cluster_size,
                        safety_flag=safety_flag,
                        age_hours=age_hours,
                    )
                    assert 0.0 <= result.priority_score <= 1.0 + 1e-9


def test_breakdown_as_dict_matches_frontend_field_names():
    result = compute_priority(
        severity=4, cluster_size=5, safety_flag=True, age_hours=48
    )
    d = result.breakdown.as_dict()
    assert set(d.keys()) == {"severity", "frequency", "safety", "sla_age"}
