"""Tests for the synthetic complaint generator behind the chaos button.

A chaos button that produced unrelated noise would demonstrate nothing — the
whole point is that the burst visibly merges and escalates. These pin the two
properties that make that true: the text actually clusters, and the reporters
are distinct.
"""

from __future__ import annotations

import pytest

from app.ai.mock import MockProvider
from app.pipeline import cluster
from app.pipeline.chaos import SCENARIOS, generate


def test_generates_exactly_the_requested_count():
    for count in (1, 6, 25):
        assert len(generate(count)) == count


def test_every_complaint_has_a_distinct_reporter():
    """A burst must be able to push a cluster past the recurring threshold.

    Reusing one student id would (correctly) refuse to mark anything
    recurring, and the demo would fall flat for the right reason.
    """
    complaints = generate(20, seed=1)
    assert len({c.student_id for c in complaints}) == 20


def test_uses_only_real_campus_buildings():
    """Similarity is scoped by building, so an invented name would never merge."""
    known = {scenario.building for scenario in SCENARIOS}
    assert {c.location_building for c in generate(20)} <= known


# Marked async on the *session* loop rather than calling `asyncio.run()`.
# `asyncio.run()` in a module that sorts alphabetically before
# `test_pipeline_db.py` tears down the session event loop those tests share,
# and every one of them then fails with "coroutine was never awaited" — a
# genuinely confusing failure a long way from its cause. See conftest.py.
@pytest.mark.asyncio(loop_scope="session")
async def test_every_scenarios_variants_collapse_into_one_cluster():
    """Each scenario's paraphrases must all merge with each other.

    Asserted per scenario rather than in aggregate, because "something
    merged" is too weak a bar: an early version had a scenario whose two
    phrasings scored just under 0.92 and quietly produced *two* clusters for
    one problem, which on stage looks exactly like the duplicate detection
    failing. This catches that.
    """
    provider = MockProvider()

    for scenario in SCENARIOS:
        pairs = []
        for index, description in enumerate(scenario.variants):
            understanding = await provider.understand_complaint(description, None)
            pairs.append((str(index), await provider.embed(understanding.summary)))

        groups = cluster.cluster_embeddings(pairs)
        assert len(groups) == 1, (
            f"{scenario.building}: {len(scenario.variants)} paraphrases of one "
            f"problem split into {len(groups)} clusters — they need to share "
            f"more signal words to clear the duplicate threshold"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_a_burst_actually_produces_clusters():
    """A whole burst merges rather than staying as singletons."""
    complaints = generate(len(SCENARIOS) * 2, seed=7)

    provider = MockProvider()
    pairs = []
    for index, complaint in enumerate(complaints):
        understanding = await provider.understand_complaint(complaint.description, None)
        pairs.append((str(index), await provider.embed(understanding.summary)))

    groups = cluster.cluster_embeddings(pairs)
    assert len(groups) < len(complaints), "nothing merged — the burst is just noise"
    assert any(len(g) >= 2 for g in groups)


def test_generation_is_reproducible_for_a_fixed_seed():
    a = generate(8, seed=42)
    b = generate(8, seed=42)
    assert [c.student_id for c in a] == [c.student_id for c in b]
    assert [c.description for c in a] == [c.description for c in b]
