"""Explainable priority scoring — AGENTS.md's 4-term weighted formula.

    priority = 0.40 * severity_score
             + 0.30 * log1p(cluster_size) / log1p(CLUSTER_CAP)
             + 0.20 * safety_flag
             + 0.10 * sla_age_factor

All four terms are returned individually (not just the total) so the API
can expose `priority_breakdown` matching `apps/web/src/lib/api.ts`'s
`PriorityBreakdown` type field-for-field:

    { severity, frequency, safety, sla_age }

Every term here is normalized to [0, 1] *before* the formula's own weight
is applied, so `priority_score` itself always lands in [0, 1] and each
breakdown segment is directly comparable/stackable in a segmented bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p

# Weights from AGENTS.md — keep these named constants in sync with the doc
# if the formula ever changes; nothing else in this file should hardcode
# 0.40/0.30/0.20/0.10.
SEVERITY_WEIGHT = 0.40
FREQUENCY_WEIGHT = 0.30
SAFETY_WEIGHT = 0.20
SLA_AGE_WEIGHT = 0.10

# Cluster size (independent-student count on one complaint cluster) at
# which the frequency term saturates near 1.0. 20 is a deliberately high
# ceiling for a single-campus hackathon demo — a cluster this big is
# already very obviously a big deal, and log1p keeps the curve concave so
# the jump from 1->3 students (the recurring-threshold in AGENTS.md)
# already moves the needle a lot.
CLUSTER_CAP = 20

# Hours after which the SLA-age term is considered "maxed out" (an open
# complaint older than this is as urgent, time-wise, as this term gets).
# 72h (3 days) matches a typical campus-facilities SLA expectation: fresh
# reports shouldn't dominate priority purely by being loud, but a report
# that's been sitting open for 3 days should be pushed up regardless of
# anything else.
SLA_AGE_SATURATION_HOURS = 72.0

# Severity from the AI schema is an int 1-5 (schemas.py). Map it onto
# [0, 1] linearly with severity=1 -> 0.0 and severity=5 -> 1.0, so a
# minimum-severity report contributes nothing to this term and a
# maximum-severity report contributes the full weight.
_SEVERITY_MIN = 1
_SEVERITY_MAX = 5


@dataclass(frozen=True)
class PriorityBreakdown:
    """Mirrors `PriorityBreakdown` in `apps/web/src/lib/api.ts` exactly.

    Field names (`severity`, `frequency`, `safety`, `sla_age`) are the
    already-weighted contribution of each term — i.e. they sum to
    `priority_score`, and each is directly usable as one segment's width
    in a 4-segment breakdown bar without any further scaling.
    """

    severity: float
    frequency: float
    safety: float
    sla_age: float

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "frequency": self.frequency,
            "safety": self.safety,
            "sla_age": self.sla_age,
        }


@dataclass(frozen=True)
class PriorityResult:
    priority_score: float
    breakdown: PriorityBreakdown


def severity_to_unit(severity: int) -> float:
    """Map the AI's 1-5 severity int onto [0, 1]."""
    clamped = max(_SEVERITY_MIN, min(_SEVERITY_MAX, severity))
    return (clamped - _SEVERITY_MIN) / (_SEVERITY_MAX - _SEVERITY_MIN)


def frequency_score(cluster_size: int, cluster_cap: int = CLUSTER_CAP) -> float:
    """log1p-scaled cluster size, normalized to [0, 1] by `cluster_cap`.

    `cluster_size` is the number of complaints (independent students)
    merged into this complaint's cluster, including itself — a brand new,
    unclustered complaint has `cluster_size=1`.
    """
    if cluster_size < 1:
        cluster_size = 1
    if cluster_cap < 1:
        raise ValueError("cluster_cap must be >= 1")
    score = log1p(cluster_size) / log1p(cluster_cap)
    return min(1.0, score)


def sla_age_factor(
    age_hours: float, saturation_hours: float = SLA_AGE_SATURATION_HOURS
) -> float:
    """How close an open complaint is to "unacceptably old", in [0, 1].

    Linear ramp from 0 at age_hours<=0 to 1.0 at age_hours>=saturation_hours.
    A linear ramp (rather than another log curve) is deliberate here: unlike
    cluster size, there's no reason early hours should matter more than
    later ones — an SLA clock ticks at a constant rate.
    """
    if age_hours <= 0:
        return 0.0
    if age_hours >= saturation_hours:
        return 1.0
    return age_hours / saturation_hours


def compute_priority(
    *,
    severity: int,
    cluster_size: int,
    safety_flag: bool,
    age_hours: float,
    cluster_cap: int = CLUSTER_CAP,
    sla_saturation_hours: float = SLA_AGE_SATURATION_HOURS,
) -> PriorityResult:
    """Compute the full priority score and its four weighted terms.

    Args:
        severity: AI-assigned severity, 1-5 (schemas.py's `severity` field).
        cluster_size: number of complaints in this complaint's cluster,
            including itself (1 for a brand-new, unclustered complaint).
        safety_flag: AI-assigned safety flag (schemas.py's `safety_flag`).
        age_hours: hours since the complaint (or, for a cluster, its
            earliest member) was first reported and still open.
        cluster_cap: override for `CLUSTER_CAP`, mainly for tests.
        sla_saturation_hours: override for `SLA_AGE_SATURATION_HOURS`,
            mainly for tests.

    Returns:
        `PriorityResult(priority_score, breakdown)` where `breakdown`'s
        four fields already sum to `priority_score` (up to floating-point
        rounding) and match `PriorityBreakdown` in `apps/web/src/lib/api.ts`.
    """
    severity_term = SEVERITY_WEIGHT * severity_to_unit(severity)
    frequency_term = FREQUENCY_WEIGHT * frequency_score(cluster_size, cluster_cap)
    safety_term = SAFETY_WEIGHT * (1.0 if safety_flag else 0.0)
    sla_term = SLA_AGE_WEIGHT * sla_age_factor(age_hours, sla_saturation_hours)

    breakdown = PriorityBreakdown(
        severity=severity_term,
        frequency=frequency_term,
        safety=safety_term,
        sla_age=sla_term,
    )
    total = severity_term + frequency_term + safety_term + sla_term
    return PriorityResult(priority_score=total, breakdown=breakdown)
