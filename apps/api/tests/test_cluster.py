"""Tests for `app.pipeline.cluster`.

Uses small, hand-constructed 2D vectors rather than real 768-dim
embeddings — cosine similarity doesn't care about dimensionality, and
2D lets every test case state its expected similarity in closed form
(`cos(theta)` between two unit vectors at angle `theta`), which is what
makes the threshold-boundary tests below exact rather than approximate.
"""

from __future__ import annotations

import math

import pytest

from app.pipeline.cluster import (
    DUPLICATE_THRESHOLD,
    SUGGESTED_MERGE_THRESHOLD,
    classify_similarity,
    cluster_embeddings,
    cosine_similarity,
    find_best_match,
)


def _unit_vector_at_cosine(similarity: float) -> tuple[float, float]:
    """A 2D unit vector whose cosine similarity with (1, 0) is exactly `similarity`."""
    return (similarity, math.sqrt(1 - similarity**2))


# --- cosine_similarity ----------------------------------------------------


def test_cosine_similarity_identical_vectors_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors_is_negative_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_similarity_scale_invariant():
    # Cosine similarity ignores magnitude — scaling one vector shouldn't
    # change the result.
    a = [1.0, 2.0, 3.0]
    b = [2.0, 4.0, 6.0]  # same direction as a, 2x magnitude
    assert cosine_similarity(a, b) == pytest.approx(1.0)


def test_cosine_similarity_mismatched_length_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosine_similarity_zero_vector_raises():
    with pytest.raises(ValueError):
        cosine_similarity([0.0, 0.0], [1.0, 0.0])


# --- classify_similarity thresholds ---------------------------------------


def test_classify_similarity_duplicate_boundary_is_inclusive():
    assert classify_similarity(DUPLICATE_THRESHOLD) == "duplicate"
    assert classify_similarity(0.999) == "duplicate"
    assert classify_similarity(1.0) == "duplicate"


def test_classify_similarity_just_below_duplicate_is_suggested_merge():
    assert classify_similarity(DUPLICATE_THRESHOLD - 0.001) == "suggested_merge"


def test_classify_similarity_suggested_merge_boundary_is_inclusive():
    assert classify_similarity(SUGGESTED_MERGE_THRESHOLD) == "suggested_merge"
    assert classify_similarity(0.80) == "suggested_merge"


def test_classify_similarity_just_below_suggested_merge_is_new():
    assert classify_similarity(SUGGESTED_MERGE_THRESHOLD - 0.001) == "new"


def test_classify_similarity_low_score_is_new():
    assert classify_similarity(0.0) == "new"
    assert classify_similarity(-0.5) == "new"


def test_classify_similarity_via_constructed_vectors_at_exact_thresholds():
    origin = (1.0, 0.0)

    at_duplicate = _unit_vector_at_cosine(DUPLICATE_THRESHOLD)
    score = cosine_similarity(origin, at_duplicate)
    assert score == pytest.approx(DUPLICATE_THRESHOLD)
    assert classify_similarity(score) == "duplicate"

    at_suggested = _unit_vector_at_cosine(SUGGESTED_MERGE_THRESHOLD)
    score = cosine_similarity(origin, at_suggested)
    assert score == pytest.approx(SUGGESTED_MERGE_THRESHOLD)
    assert classify_similarity(score) == "suggested_merge"

    slightly_below_duplicate = _unit_vector_at_cosine(DUPLICATE_THRESHOLD - 0.01)
    score = cosine_similarity(origin, slightly_below_duplicate)
    assert classify_similarity(score) == "suggested_merge"

    slightly_below_suggested = _unit_vector_at_cosine(SUGGESTED_MERGE_THRESHOLD - 0.01)
    score = cosine_similarity(origin, slightly_below_suggested)
    assert classify_similarity(score) == "new"


# --- find_best_match --------------------------------------------------------


def test_find_best_match_picks_highest_scoring_candidate():
    query = (1.0, 0.0)
    candidates = [
        ("far", (0.0, 1.0)),  # similarity 0.0
        ("close", (0.99, math.sqrt(1 - 0.99**2))),  # similarity 0.99
        ("mid", (0.8, math.sqrt(1 - 0.8**2))),  # similarity 0.8
    ]
    result = find_best_match(query, candidates)
    assert result is not None
    best_id, score, label = result
    assert best_id == "close"
    assert score == pytest.approx(0.99)
    assert label == "duplicate"


def test_find_best_match_empty_candidates_returns_none():
    assert find_best_match((1.0, 0.0), []) is None


def test_find_best_match_classifies_new_when_nothing_close():
    query = (1.0, 0.0)
    candidates = [("orthogonal", (0.0, 1.0))]
    best_id, score, label = find_best_match(query, candidates)
    assert best_id == "orthogonal"
    assert label == "new"


# --- cluster_embeddings -----------------------------------------------------


def test_cluster_embeddings_groups_near_identical_vectors():
    # Three near-identical "wifi down in block C" style embeddings should
    # land in one cluster; a fourth, orthogonal, unrelated complaint stays
    # separate.
    items = [
        ("c1", (1.0, 0.0)),
        ("c2", (0.999, math.sqrt(1 - 0.999**2))),  # similarity ~0.999 to c1
        ("c3", (0.995, math.sqrt(1 - 0.995**2))),  # similarity ~0.995 to c1
        ("other", (0.0, 1.0)),  # orthogonal - unrelated issue
    ]
    clusters = cluster_embeddings(items)

    cluster_by_id = {item_id: idx for idx, group in enumerate(clusters) for item_id in group}
    assert cluster_by_id["c1"] == cluster_by_id["c2"] == cluster_by_id["c3"]
    assert cluster_by_id["other"] != cluster_by_id["c1"]

    sizes = sorted(len(group) for group in clusters)
    assert sizes == [1, 3]


def test_cluster_embeddings_transitive_chain_merges_into_one_group():
    # a<->b duplicate, b<->c duplicate, but a<->c alone might be just under
    # threshold — connected components should still merge all three via b.
    a = (1.0, 0.0)
    # b is 0.93 similar to a (comfortably >= 0.92 threshold)
    b = _unit_vector_at_cosine(0.93)
    # c is constructed to be 0.93 similar to b but further from a directly.
    # Rotate by the same angular step again from b.
    theta_step = math.acos(0.93)
    theta_c = 2 * theta_step
    c = (math.cos(theta_c), math.sin(theta_c))

    items = [("a", a), ("b", b), ("c", c)]
    clusters = cluster_embeddings(items)

    assert len(clusters) == 1
    assert sorted(clusters[0]) == ["a", "b", "c"]


def test_cluster_embeddings_all_singletons_when_nothing_similar():
    items = [
        ("wifi", (1.0, 0.0)),
        ("sanitation", (0.0, 1.0)),
        ("electrical", (-1.0, 0.0)),
    ]
    clusters = cluster_embeddings(items)
    assert len(clusters) == 3
    assert all(len(group) == 1 for group in clusters)


def test_cluster_embeddings_empty_input():
    assert cluster_embeddings([]) == []


def test_cluster_embeddings_single_item():
    clusters = cluster_embeddings([("only", (1.0, 0.0))])
    assert clusters == [["only"]]


def test_cluster_embeddings_every_id_appears_exactly_once():
    items = [
        ("a", (1.0, 0.0)),
        ("b", (0.999, math.sqrt(1 - 0.999**2))),
        ("c", (0.0, 1.0)),
        ("d", (-1.0, 0.0)),
        ("e", (0.998, math.sqrt(1 - 0.998**2))),
    ]
    clusters = cluster_embeddings(items)
    all_ids = [item_id for group in clusters for item_id in group]
    assert sorted(all_ids) == ["a", "b", "c", "d", "e"]
    assert len(all_ids) == len(set(all_ids))
