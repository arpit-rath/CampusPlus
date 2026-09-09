"""Thin orchestration for "a new complaint just came in".

`process_new_complaint` is the function Track A's `# TODO(integration)`
comment in `complaints.py` should eventually call from the complaint-create
route. It does not touch the database — it takes the raw inputs a router
already has in hand plus a candidate pool of existing embeddings, and
returns everything the router needs to persist a new `complaints` row (and
decide whether to attach it to an existing `complaint_clusters` row or
start a new one).

**Integration note for whoever wires this into `complaints.py`** (spelled
out here since Track B doesn't own that router file):

- `existing_embeddings` must already be scoped by the caller per
  CLAUDE.md's similarity-search rule: same `location_building` + rolling
  14-day window. Category scoping is the one wrinkle — the AI-derived
  `category` isn't known until *inside* this call, so the cleanest
  options for the caller are (a) scope candidates by building + window
  only and accept that cross-category near-duplicates are rare in
  practice for a hackathon demo, or (b) call this function, then re-query
  the DB filtered by the now-known `result["understanding"]["category"]`
  and re-run just `cluster.classify_similarity` if a tighter pass is
  wanted before persisting. Either is a few lines in the router; nothing
  here needs to change for either choice.
- `result["cluster_size_hint"]` is computed only from the candidates you
  passed in (self + however many of them are >= the duplicate threshold
  away from the new embedding) — it is **not** read from
  `complaint_clusters.member_count`. If the new complaint is joining an
  existing DB cluster, prefer using that cluster's real, up-to-date
  `member_count` (+1) when calling `priority.compute_priority` for
  persistence; `cluster_size_hint` is a reasonable default when there's no
  existing cluster row yet, and is what this function's own
  `result["priority"]` is computed from.
- `age_hours` defaults to `0.0` (a brand-new complaint). This function
  doesn't recompute priority for *existing* complaints as their SLA clock
  ticks — that's a separate scheduled/recompute concern, not part of the
  create-time pipeline.
"""

from __future__ import annotations

from typing import Sequence

from app.ai.provider import AIProvider, get_provider
from app.pipeline import cluster, priority


async def process_new_complaint(
    description: str,
    image_bytes: bytes | None,
    existing_embeddings: Sequence[tuple[str, Sequence[float]]],
    *,
    age_hours: float = 0.0,
    provider: AIProvider | None = None,
) -> dict:
    """Run the full intake pipeline for one new complaint.

    Args:
        description: raw student-submitted text.
        image_bytes: raw photo bytes, or `None` if no photo was attached.
        existing_embeddings: candidate `(complaint_id, embedding)` pairs to
            compare against, already scoped by the caller (see module
            docstring for the category/building/window caveat).
        age_hours: hours since this complaint was first reported; `0.0`
            for a complaint being created right now (the expected case).
        provider: override for `get_provider()` — used by tests to inject
            a specific `AIProvider` without touching `Settings`. Callers
            in the real app should omit this and let it read
            `settings.llm_provider` as normal.

    Returns:
        A dict shaped for easy unpacking into a persistence call:

        {
            "understanding": {  # ComplaintUnderstanding.as_dict()
                "category": str, "severity": int, "safety_flag": bool,
                "photo_matches_text": bool, "summary": str,
                "extracted_location_hint": str,
            },
            "embedding": list[float],            # 768 floats
            "similarity": {
                "best_match_id": str | None,
                "best_match_score": float | None,
                "label": "duplicate" | "suggested_merge" | "new",
            },
            "cluster_size_hint": int,             # see integration note above
            "priority": {
                "priority_score": float,
                "priority_breakdown": {
                    "severity": float, "frequency": float,
                    "safety": float, "sla_age": float,
                },
            },
        }
    """
    ai = provider or get_provider()

    understanding = await ai.understand_complaint(description, image_bytes)
    # Embed the AI's normalized summary, not the raw student text, per
    # build-plan.md §4.2.
    embedding = await ai.embed(understanding.summary)

    candidates = list(existing_embeddings)
    match = cluster.find_best_match(embedding, candidates)

    if match is None:
        similarity = {"best_match_id": None, "best_match_score": None, "label": "new"}
        duplicate_count = 0
    else:
        best_id, best_score, label = match
        similarity = {
            "best_match_id": best_id,
            "best_match_score": best_score,
            "label": label,
        }
        duplicate_count = sum(
            1
            for candidate_id, candidate_embedding in candidates
            if cluster.classify_similarity(
                cluster.cosine_similarity(embedding, candidate_embedding)
            )
            == "duplicate"
        )

    # +1 to count the new complaint itself. A brand-new, non-duplicate
    # complaint has cluster_size_hint=1 (matches priority.py's
    # "unclustered complaint has cluster_size=1" convention).
    cluster_size_hint = duplicate_count + 1

    priority_result = priority.compute_priority(
        severity=understanding.severity,
        cluster_size=cluster_size_hint,
        safety_flag=understanding.safety_flag,
        age_hours=age_hours,
    )

    return {
        "understanding": understanding.as_dict(),
        "embedding": embedding,
        "similarity": similarity,
        "cluster_size_hint": cluster_size_hint,
        "priority": {
            "priority_score": priority_result.priority_score,
            "priority_breakdown": priority_result.breakdown.as_dict(),
        },
    }
