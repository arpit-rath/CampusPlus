"""Pure similarity/clustering functions — no DB access.

Everything here takes plain lists/tuples of floats (or of `(id, embedding)`
pairs) and returns similarity/grouping decisions. Callers (routers, the
`understand.py` orchestrator) are responsible for scoping candidates to
"same category + same building + rolling 14-day window" *before* calling
into this module (per AGENTS.md's similarity-search section) — this module
has no idea what a category or a building is, on purpose, so it stays
trivially unit-testable and reusable for the pgvector-backed path and for
`scripts/seed_demo.py`'s offline fixture generation alike.

Thresholds (AGENTS.md):
    >= 0.92        -> "duplicate" (auto-merge into the existing complaint)
    0.75 - 0.92    -> "suggested_merge" (surfaced to an admin, not auto-applied)
    < 0.75         -> "new" (independent complaint)
"""

from __future__ import annotations

import math
from typing import Literal, Sequence

SimilarityLabel = Literal["duplicate", "suggested_merge", "new"]

DUPLICATE_THRESHOLD = 0.92
SUGGESTED_MERGE_THRESHOLD = 0.75


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors, in [-1, 1].

    Pure Python (no numpy) by design — see the repo-level note about
    avoiding install-time dependency risk during the hackathon.

    Raises ValueError if the vectors differ in length or either is a
    zero vector (cosine similarity is undefined for a zero vector; a
    caller passing one has a bug upstream, so this fails loudly instead
    of silently returning 0.0).
    """
    if len(a) != len(b):
        raise ValueError(f"vector length mismatch: {len(a)} vs {len(b)}")

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("cosine_similarity is undefined for a zero vector")

    similarity = dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
    # Clamp for float rounding — dot-product-based cosine can drift a hair
    # outside [-1, 1] (e.g. 1.0000000000000002) for near-identical vectors.
    return max(-1.0, min(1.0, similarity))


def classify_similarity(
    score: float,
    *,
    duplicate_threshold: float = DUPLICATE_THRESHOLD,
    suggested_merge_threshold: float = SUGGESTED_MERGE_THRESHOLD,
) -> SimilarityLabel:
    """Bucket a cosine similarity score per AGENTS.md's thresholds.

    >= duplicate_threshold        -> "duplicate"
    >= suggested_merge_threshold  -> "suggested_merge"
    otherwise                     -> "new"
    """
    if score >= duplicate_threshold:
        return "duplicate"
    if score >= suggested_merge_threshold:
        return "suggested_merge"
    return "new"


def find_best_match(
    embedding: Sequence[float],
    candidates: Sequence[tuple[str, Sequence[float]]],
) -> tuple[str, float, SimilarityLabel] | None:
    """Compare `embedding` against each `(id, embedding)` candidate.

    Returns `(best_id, best_score, label)` for the highest-scoring
    candidate, or `None` if `candidates` is empty. Callers are expected to
    have already scoped `candidates` to the same category/building/time
    window (see module docstring) — this just picks the closest one and
    classifies it.
    """
    best: tuple[str, float] | None = None
    for candidate_id, candidate_embedding in candidates:
        score = cosine_similarity(embedding, candidate_embedding)
        if best is None or score > best[1]:
            best = (candidate_id, score)

    if best is None:
        return None
    best_id, best_score = best
    return best_id, best_score, classify_similarity(best_score)


def cluster_embeddings(
    items: Sequence[tuple[str, Sequence[float]]],
    *,
    duplicate_threshold: float = DUPLICATE_THRESHOLD,
) -> list[list[str]]:
    """Connected components over the pairwise-duplicate similarity graph.

    Two items are joined by an edge when their cosine similarity clears
    `duplicate_threshold` (i.e. `classify_similarity` would call them
    "duplicate" of each other) — this mirrors AGENTS.md's ">= 0.92 ->
    auto-merge" rule, generalized from "compare one new complaint against
    existing ones" to "group a whole batch at once" (used by
    `scripts/seed_demo.py` to sanity-check the generated fixture, and
    reusable for any future "recompute clusters from scratch" maintenance
    task).

    Returns a list of clusters, each a list of item ids, in first-seen
    order (both across clusters and within a cluster). Every id in `items`
    appears in exactly one cluster, including singletons.

    O(n^2) pairwise comparisons — perfectly fine for demo-fixture sizes
    (tens of items); a real DB-backed path would instead ask pgvector for
    nearest neighbors per item and wouldn't need this function at all.
    """
    n = len(items)
    ids = [item_id for item_id, _ in items]
    embeddings = [embedding for _, embedding in items]

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path halving
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_j] = root_i

    for i in range(n):
        for j in range(i + 1, n):
            try:
                score = cosine_similarity(embeddings[i], embeddings[j])
            except ValueError:
                # A zero vector shouldn't take down clustering for the
                # whole batch; treat it as similar to nothing.
                continue
            if score >= duplicate_threshold:
                union(i, j)

    groups: dict[int, list[str]] = {}
    for i in range(n):
        root = find(i)
        groups.setdefault(root, []).append(ids[i])

    # Preserve first-seen order of clusters by the smallest original index
    # in each group (dict insertion order from the loop above already
    # gives us this, since `i` is visited in order).
    return list(groups.values())


def count_independent_students(
    members: Sequence[tuple[str, str | None]],
) -> int:
    """Distinct reporters among `(complaint_id, student_id)` pairs.

    AGENTS.md's recurring rule is about *independent students*, not about
    submissions: a cluster is recurring once three different people have
    reported it. Counting rows instead would let one frustrated student
    reporting the same broken cooler five times manufacture a campus-wide
    "recurring issue", which is exactly the failure the rule exists to
    prevent.

    A `None` student_id is an anonymous report, and each one counts as its
    own reporter (keyed by complaint id). That direction is deliberate:
    treating every anonymous report as the same person would *under*-count
    a genuine recurring problem reported by three students who all chose not
    to identify themselves, and under-counting a real safety issue is the
    worse error.

    The database-backed equivalent is
    `app.pipeline.similarity.count_independent_students`, which computes the
    same number in SQL; this pure version is what the offline seed/test path
    uses.
    """
    return len({student_id or f"anon:{complaint_id}" for complaint_id, student_id in members})
