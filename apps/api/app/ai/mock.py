"""`MockProvider` — deterministic, dependency-free stand-in for Gemini.

This is what the whole team develops against most of the time (per
CLAUDE.md, `LLM_PROVIDER=mock` is the dev default) and what a live demo
falls back to if a real Gemini call errors or times out. Both understanding
and embedding are cheap, pure-Python, and fully deterministic — same input
always produces the same output, no network, no API key.

`understand_complaint` keyword-sniffs the description to pick a plausible
category/severity/safety_flag instead of always returning the same fixed
values, so it's actually useful for exercising the clustering/priority
pipeline and for manual testing.

`embed` uses feature hashing (the "hashing trick"): each word in the text
is hashed to one of 768 dimensions with a deterministic +1/-1 sign and
accumulated with a per-word weight, and the resulting vector is
L2-normalized. Words that appear in `_CATEGORY_KEYWORDS` (the same list
`understand_complaint` uses to classify a category — "wifi", "spark",
"leak", etc.) are weighted much more heavily than ordinary words. This
isn't just a generic bag-of-words: it's deliberately biased toward the
domain vocabulary that actually identifies *what the problem is*, so that
two paraphrases of the same underlying issue ("wifi is completely down in
X, can't connect" vs "no wifi signal in X, network unreachable") land
close together in cosine similarity even though most of the surrounding
sentence differs — which is what makes `scripts/seed_demo.py`'s
near-duplicate WiFi/electrical clusters actually clear the >=0.92
duplicate threshold from CLAUDE.md under the mock provider, not just under
a real embedding model. Not a real semantic embedding — but a real
768-float unit vector with a deliberately useful notion of "closer" for
demo/test purposes.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.ai.provider import AIProvider
from app.ai.schemas import CATEGORY_SLUGS, ComplaintUnderstanding

EMBEDDING_DIM = 768

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to",
    "of", "and", "or", "with", "for", "this", "that", "it", "its", "has",
    "have", "had", "i", "we", "my", "our", "there", "been", "be", "as",
    "from", "by", "not", "so", "very", "also", "just", "please", "s",
}

# Category -> keywords that, if present, suggest that category. Order
# matters: checked in this order, first category with any keyword hit wins
# (so put more-specific categories before "other").
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "wifi",
        (
            "wifi", "wi-fi", "internet", "network", "router", "signal",
            "connectivity", "broadband", "ethernet", "hotspot", "lan",
            "disconnect", "disconnected", "wireless", "connect", "connected",
            "offline", "outage",
        ),
    ),
    (
        "electrical",
        (
            "electric", "electrical", "electricity", "power", "outlet",
            "socket", "wiring", "wire", "spark", "sparks", "sparking",
            "voltage", "short circuit", "circuit", "breaker", "switchboard",
            "mcb", "transformer", "fuse",
        ),
    ),
    (
        "sanitation",
        (
            "water", "leak", "leaking", "leakage", "toilet", "washroom",
            "bathroom", "restroom", "sewage", "drain", "drainage", "smell",
            "stink", "trash", "garbage", "clean", "unclean", "hygiene",
            "flush", "tap", "faucet", "mold", "mould", "overflow",
            "overflowing", "dirty",
        ),
    ),
    (
        "academics",
        (
            "class", "lecture", "professor", "exam", "syllabus", "course",
            "grade", "grading", "assignment", "attendance", "faculty",
            "timetable", "curriculum", "semester", "credit", "marks",
        ),
    ),
    (
        "infrastructure",
        (
            "door", "window", "wall", "ceiling", "floor", "furniture",
            "chair", "desk", "elevator", "lift", "crack", "cracked",
            "broken", "roof", "ac", "air conditioner", "fan", "hostel",
            "building", "gate", "lock", "staircase", "stairs", "bench",
            "projector", "bulb", "light",
        ),
    ),
]

_SAFETY_KEYWORDS = (
    "spark", "sparks", "sparking", "exposed wire", "exposed wiring",
    "exposed cable", "smoke", "smoking", "shock", "electrocut", "fire",
    "gas smell", "gas leak", "collapse", "collapsing", "collapsed",
    "burning", "burnt smell", "live wire", "current", "explode",
    "explosion", "hazard", "hazardous",
)

_INTENSITY_UP = (
    "completely", "totally", "entirely", "whole", "everyone", "always",
    "constantly", "urgent", "urgently", "severe", "severely", "again",
    "repeatedly", "still not", "worst", "unbearable", "flooding",
    "no water", "no power", "no internet", "not working at all",
)

_INTENSITY_DOWN = (
    "minor", "sometimes", "occasionally", "slightly", "small", "little",
    "once in a while",
)

_LOCATION_RE = re.compile(
    r"\b((?:block|building|hostel|wing|floor|room|lab|hall)\s*[-:]?\s*"
    r"[a-z0-9]+(?:\s*(?:floor|room))?)",
    re.IGNORECASE,
)

# Single-word category keywords, flattened into one set and used by embed()
# to weight domain-signal words much more heavily than ordinary words (see
# module docstring). Multi-word keywords (e.g. "short circuit", "gas leak")
# are skipped here — they're checked as substrings in _classify_category /
# _detect_safety_flag, but token-level weighting only ever sees one word at
# a time, so a multi-word entry would never match a single token anyway.
_SIGNAL_WORDS: frozenset[str] = frozenset(
    keyword
    for _slug, keywords in _CATEGORY_KEYWORDS
    for keyword in keywords
    if " " not in keyword
)

# How much more a recognized domain-signal word (e.g. "wifi", "sparking",
# "leak") counts toward the embedding than an ordinary word. High enough
# that a handful of shared signal words dominate the vector even when the
# surrounding sentence is phrased quite differently — see the module
# docstring for why that matters for the near-duplicate demo clusters.
_SIGNAL_WEIGHT = 6.0
_GENERIC_WEIGHT = 0.5


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


def _stable_hash(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)


def _classify_category(text_lower: str) -> str:
    for slug, keywords in _CATEGORY_KEYWORDS:
        if any(kw in text_lower for kw in keywords):
            return slug
    return "other"


def _detect_safety_flag(text_lower: str) -> bool:
    return any(kw in text_lower for kw in _SAFETY_KEYWORDS)


def _derive_severity(text_lower: str, safety_flag: bool) -> int:
    severity = 2  # baseline: "worth reporting" but not dramatic
    if safety_flag:
        severity += 2
    severity += sum(1 for kw in _INTENSITY_UP if kw in text_lower)
    severity -= sum(1 for kw in _INTENSITY_DOWN if kw in text_lower)
    return max(1, min(5, severity))


def _extract_location_hint(text: str) -> str:
    match = _LOCATION_RE.search(text)
    return match.group(1).strip() if match else ""


def _summarize(text: str, category: str) -> str:
    trimmed = " ".join(text.strip().split())
    if len(trimmed) > 180:
        trimmed = trimmed[:177].rsplit(" ", 1)[0] + "..."
    label = category.replace("_", " ")
    if not trimmed:
        return f"Student reported a {label} issue with no further detail."
    return f"{label.capitalize()} issue: {trimmed}"


def _mock_answer(question: str, records: list[dict]) -> str:
    """A genuinely informative, fully deterministic answer over `records`.

    The mock has no language model, so instead of pretending to write prose
    it reports the aggregates an admin actually asked about: how many
    complaints matched, how they split by category and building, how many
    are recurring or safety-flagged, and what the single highest-priority
    one is. That is a real answer grounded in real rows — just phrased by a
    template rather than by Gemini.
    """
    if not records:
        return "No complaints in the current data match that question."

    def _count(key: str) -> list[tuple[str, int]]:
        tally: dict[str, int] = {}
        for record in records:
            value = record.get(key) or "unspecified"
            tally[str(value)] = tally.get(str(value), 0) + 1
        return sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))

    categories = _count("category_slug")
    buildings = _count("location_building")
    recurring = sum(1 for r in records if r.get("is_recurring"))
    safety = sum(1 for r in records if r.get("safety_flag"))
    top = max(records, key=lambda r: r.get("priority_score") or 0.0)

    sentences = [
        f"{len(records)} complaint(s) match that question.",
        "By category: "
        + ", ".join(f"{slug} ({n})" for slug, n in categories[:4])
        + ".",
        "By location: "
        + ", ".join(f"{name} ({n})" for name, n in buildings[:4])
        + ".",
    ]
    if recurring:
        sentences.append(f"{recurring} are part of a recurring cluster.")
    if safety:
        sentences.append(f"{safety} are flagged as a safety risk.")

    top_summary = " ".join(
        str(top.get("ai_summary") or top.get("raw_description") or "").split()
    )[:140]
    if top_summary:
        sentences.append(
            f"Highest priority ({(top.get('priority_score') or 0.0):.2f}) at "
            f"{top.get('location_building') or 'an unspecified building'}: {top_summary}"
        )
    return " ".join(sentences)


class MockProvider(AIProvider):
    """Deterministic fake `AIProvider` — no network calls."""

    async def answer_question(
        self, question: str, records: list[dict], schema_hint: str = ""
    ) -> dict:
        return {
            "answer": _mock_answer(question, records),
            "cited_complaint_ids": [
                str(r["id"]) for r in records if r.get("id") is not None
            ],
        }

    async def understand_complaint(
        self, description: str, image_bytes: bytes | None
    ) -> ComplaintUnderstanding:
        text_lower = description.lower()
        category = _classify_category(text_lower)
        safety_flag = _detect_safety_flag(text_lower)
        severity = _derive_severity(text_lower, safety_flag)
        # Mock doesn't actually look at pixels; treat "a photo was attached"
        # as a weak positive signal so the field isn't always the same
        # value, while staying honest that this is a stub.
        photo_matches_text = bool(image_bytes)
        summary = _summarize(description, category)
        location_hint = _extract_location_hint(description)

        assert category in CATEGORY_SLUGS
        return ComplaintUnderstanding(
            category=category,
            severity=severity,
            safety_flag=safety_flag,
            photo_matches_text=photo_matches_text,
            summary=summary,
            extracted_location_hint=location_hint,
            raw={"provider": "mock"},
        )

    async def embed(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        tokens = _tokenize(text)

        if not tokens:
            # Degenerate input (empty string, all-stopword). Fall back to
            # hashing the raw text itself so we still return a stable,
            # non-zero unit vector instead of all zeros (which breaks
            # cosine similarity — 0/0).
            tokens = [text or "empty"]

        for token in tokens:
            h = _stable_hash(token)
            idx = h % EMBEDDING_DIM
            sign = 1.0 if (h // EMBEDDING_DIM) % 2 == 0 else -1.0
            weight = _SIGNAL_WEIGHT if token in _SIGNAL_WORDS else _GENERIC_WEIGHT
            vector[idx] += sign * weight

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            # All contributions cancelled out exactly (rare, but possible
            # with very short input) — perturb deterministically from a
            # hash of the whole string so we never divide by zero.
            seed = _stable_hash(text or "empty")
            idx = seed % EMBEDDING_DIM
            vector[idx] = 1.0
            norm = 1.0

        return [v / norm for v in vector]
