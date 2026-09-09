"""Tests for `app.pipeline.understand.process_new_complaint`.

Uses `MockProvider` explicitly (via the `provider=` override) rather than
`get_provider()`/Settings, so these tests don't depend on env vars and
never make a network call.

Uses `asyncio.run()` directly instead of `@pytest.mark.asyncio` so these
tests don't depend on `pytest-asyncio` being configured (asyncio_mode) in
a pytest.ini/pyproject.toml that may not exist yet at this point in the
build — safe either way since `asyncio.run()` just needs an event loop.
"""

from __future__ import annotations

import asyncio

from app.ai.mock import MockProvider
from app.pipeline.understand import process_new_complaint


def run(coro):
    return asyncio.run(coro)


def test_process_new_complaint_no_existing_embeddings_is_new():
    result = run(
        process_new_complaint(
            "The wifi in Block C has been down all day, nobody can connect.",
            None,
            [],
        )
    )
    assert result["similarity"]["label"] == "new"
    assert result["similarity"]["best_match_id"] is None
    assert result["cluster_size_hint"] == 1
    assert len(result["embedding"]) == 768
    assert result["understanding"]["category"] == "wifi"
    assert 0.0 <= result["priority"]["priority_score"] <= 1.0
    breakdown = result["priority"]["priority_breakdown"]
    assert set(breakdown.keys()) == {"severity", "frequency", "safety", "sla_age"}


def test_process_new_complaint_detects_near_duplicate():
    provider = MockProvider()

    # Seed one existing embedding from essentially the same complaint text
    # so the mock's hashing-trick embedding lands very close to the new
    # one's.
    existing_summary = run(
        provider.understand_complaint(
            "Wifi is completely down in Block C, no internet at all.", None
        )
    ).summary
    existing_embedding = run(provider.embed(existing_summary))

    result = run(
        process_new_complaint(
            "Wifi is completely down in Block C, no internet at all.",
            None,
            [("existing-1", existing_embedding)],
            provider=provider,
        )
    )

    assert result["similarity"]["best_match_id"] == "existing-1"
    assert result["similarity"]["label"] == "duplicate"
    assert result["similarity"]["best_match_score"] >= 0.92
    # duplicate_count (1) + self (1)
    assert result["cluster_size_hint"] == 2


def test_process_new_complaint_unrelated_existing_embedding_is_new():
    provider = MockProvider()
    unrelated_embedding = run(
        provider.embed("Sanitation issue: overflowing trash bins near the library.")
    )

    result = run(
        process_new_complaint(
            "Exposed wiring sparking near the electrical panel in the gym.",
            None,
            [("unrelated-1", unrelated_embedding)],
            provider=provider,
        )
    )

    assert result["similarity"]["label"] == "new"
    assert result["cluster_size_hint"] == 1
    assert result["understanding"]["category"] == "electrical"
    assert result["understanding"]["safety_flag"] is True
    # Safety flag should be visible in the priority breakdown too.
    assert result["priority"]["priority_breakdown"]["safety"] > 0.0


def test_process_new_complaint_age_hours_affects_sla_term():
    fresh = run(
        process_new_complaint("Broken chair in the library.", None, [], age_hours=0)
    )
    stale = run(
        process_new_complaint(
            "Broken chair in the library.", None, [], age_hours=100
        )
    )
    assert (
        stale["priority"]["priority_breakdown"]["sla_age"]
        > fresh["priority"]["priority_breakdown"]["sla_age"]
    )
