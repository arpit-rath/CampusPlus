""""Ask CampusPluse" — a simple natural-language query over admin complaint
data (build-plan.md §6/§7). Backs `POST /admin/ask` (see `api.ts`'s
`askAdmin`, which expects `{answer, cited_complaint_ids}`).

Deliberately not real RAG: this is a keyword/category/building filter over
whatever complaint dicts the caller already has in memory (the router owns
fetching them from the DB), followed by one provider call that summarizes
the filtered set in a sentence or two and is told to only cite ids it was
actually given. Good enough for a hackathon demo box of a few dozen to a
few hundred complaints; not built to scale past that.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.provider import AIProvider, get_provider
from app.ai.schemas import CATEGORY_SLUGS

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "of", "and", "or", "with", "for", "this", "that", "it", "how", "many",
    "what", "which", "show", "me", "there", "have", "has", "had", "do",
    "does", "any", "all", "list", "give", "us", "please", "about",
}

_MAX_MATCHES_FOR_PROMPT = 25
_MAX_MATCHES_TO_CONSIDER = 200


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def _complaint_haystack(complaint: dict[str, Any]) -> set[str]:
    """Tokens pulled from every field a question might reasonably reference."""
    fields = [
        complaint.get("raw_description", ""),
        complaint.get("ai_summary", "") or "",
        complaint.get("category_slug", "") or "",
        complaint.get("location_building", "") or "",
        complaint.get("location_room", "") or "",
        complaint.get("department_name", "") or "",
        complaint.get("status", "") or "",
    ]
    tokens: set[str] = set()
    for field in fields:
        tokens |= _tokenize(str(field))
    return tokens


def _filter_complaints(
    question: str, complaints: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keyword/category/building overlap filter.

    A complaint matches if it shares at least one non-stopword token with
    the question. If that filter yields nothing (e.g. a very generic
    question like "what's most urgent?"), fall back to considering
    everything, up to `_MAX_MATCHES_TO_CONSIDER`, sorted by priority so the
    most relevant/urgent items are what actually get summarized.
    """
    question_tokens = _tokenize(question)

    if question_tokens:
        matches = [
            c for c in complaints if question_tokens & _complaint_haystack(c)
        ]
        if matches:
            matches.sort(key=lambda c: c.get("priority_score", 0), reverse=True)
            return matches[:_MAX_MATCHES_TO_CONSIDER]

    fallback = sorted(
        complaints, key=lambda c: c.get("priority_score", 0), reverse=True
    )
    return fallback[:_MAX_MATCHES_TO_CONSIDER]


def _no_match_answer(question: str) -> dict:
    return {
        "answer": (
            "I couldn't find any complaints matching that question in the "
            "current data. Try mentioning a category "
            f"({', '.join(CATEGORY_SLUGS)}), a building, or a keyword from "
            "the report text."
        ),
        "cited_complaint_ids": [],
    }


def _build_data_blurb(question: str, matches: list[dict[str, Any]]) -> str:
    """A short, data-dense, plain-English blurb built from `matches`.

    This — not the raw question or a long instruction block — is what gets
    handed to `AIProvider.understand_complaint` as the "description" to
    summarize. Two reasons to keep it data-first and compact:

    - `MockProvider.understand_complaint`'s summary is a naive prefix
      truncation of its input (it's a complaint summarizer, not a general
      chat model) — putting the actual facts (counts, categories,
      buildings, the top match) in the first ~180 characters means the
      mock path still produces a genuinely informative answer instead of
      echoing back instruction text.
    - For `GeminiProvider`, a compact, fact-dense input is also just a
      better summarization prompt than a long wall of instructions.
    """
    categories = sorted({c.get("category_slug", "other") for c in matches})
    buildings = sorted(
        {c.get("location_building") for c in matches if c.get("location_building")}
    )
    safety_count = sum(1 for c in matches if c.get("safety_flag"))
    top = matches[0]  # matches are pre-sorted by priority_score, descending
    top_summary = (top.get("ai_summary") or top.get("raw_description") or "").strip()
    top_summary = " ".join(top_summary.split())[:120]

    parts = [f'{len(matches)} complaint(s) match "{question}"']
    if categories:
        parts.append(f"across {', '.join(categories)}")
    if buildings:
        parts.append(f"in {', '.join(buildings)}")
    if safety_count:
        parts.append(f"({safety_count} flagged for safety)")
    blurb = ", ".join(parts) + "."
    if top_summary:
        blurb += f" Top match: {top_summary}"
    return blurb


async def answer_admin_question(
    question: str,
    complaints: list[dict[str, Any]],
    *,
    provider: AIProvider | None = None,
) -> dict:
    """Answer one admin natural-language question over `complaints`.

    Args:
        question: free-text admin question, e.g. "what's going on with
            wifi in Block C" or "any safety issues this week?".
        complaints: list of complaint dicts (already fetched by the
            caller — this function does not touch the DB). Expected to
            look like the API's `Complaint` shape (`apps/web/src/lib/
            api.ts`), but only reads fields defensively via `.get()`, so a
            partial dict (e.g. missing `ai_summary`) won't crash it.
        provider: override for `get_provider()`, for tests.

    Returns:
        `{"answer": str, "cited_complaint_ids": list[str]}` — every id in
        `cited_complaint_ids` is guaranteed to be an id of a complaint that
        was actually in the filtered match set (never hallucinated),
        regardless of what the model returns, because the ids are
        cross-checked against the match set after the call.
    """
    if not complaints:
        return _no_match_answer(question)

    matches = _filter_complaints(question, complaints)
    if not matches:
        return _no_match_answer(question)

    matched_ids = {str(c.get("id")) for c in matches if c.get("id") is not None}
    prompt_matches = matches[:_MAX_MATCHES_FOR_PROMPT]

    blurb = _build_data_blurb(question, prompt_matches)

    ai = provider or get_provider()
    understanding = await ai.understand_complaint(blurb, None)
    answer_text = understanding.summary or (
        f"Found {len(matches)} matching complaint(s)."
    )

    # Cite every matched id shown to the model, capped to what was in the
    # prompt — cheap and never hallucinates, since it's not parsed out of
    # free text the model wrote. A future pass could ask the provider for
    # an explicit `cited_ids` field the same way `understand_complaint`
    # asks for structured fields, and intersect that with `matched_ids`.
    cited_ids = [c.get("id") for c in prompt_matches if c.get("id") is not None]
    cited_ids = [cid for cid in cited_ids if str(cid) in matched_ids]

    return {"answer": answer_text, "cited_complaint_ids": cited_ids}
