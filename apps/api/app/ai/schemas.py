"""Structured-output schema for the AI "understand a complaint" call.

This is the source of truth for what `category`, `severity`, and
`safety_flag` mean everywhere else in the codebase (per CLAUDE.md) — don't
redefine these ad hoc in a router or another pipeline module.

Two things live here, kept in lockstep:

1. ``CATEGORY_SLUGS`` / ``GEMINI_RESPONSE_SCHEMA`` — the JSON schema dict
   handed to Gemini's ``response_schema`` for structured output.
2. ``ComplaintUnderstanding`` — a plain Python dataclass with the same
   fields, used everywhere else in the backend (pipeline, tests, the mock
   provider) so nothing downstream has to know it's talking to Gemini.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Category slugs Track A seeds into the `categories` table. Keep this list
# in sync with the seed data — it's the enum both the Gemini schema and the
# mock provider are allowed to return.
CATEGORY_SLUGS: tuple[str, ...] = (
    "wifi",
    "electrical",
    "sanitation",
    "infrastructure",
    "academics",
    "other",
)

# JSON schema dict for `google.genai.types.GenerateContentConfig(
#     response_mime_type="application/json", response_schema=GEMINI_RESPONSE_SCHEMA
# )`. Deliberately plain JSON-schema-shaped (OpenAPI 3.0 subset, which is
# what the Gemini structured-output feature expects) rather than a
# `genai.types.Schema` object, so this module has zero SDK import — it can
# be imported from anywhere (routers, tests) without pulling in
# `google-genai`.
GEMINI_RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "category": {
            "type": "STRING",
            "enum": list(CATEGORY_SLUGS),
            "description": (
                "Best-fit category slug for this complaint. Use 'other' "
                "only when nothing else plausibly fits."
            ),
        },
        "severity": {
            "type": "INTEGER",
            "description": (
                "How bad this issue is on a 1-5 scale: 1 = cosmetic/minor "
                "inconvenience, 3 = clearly disrupts normal use, 5 = urgent "
                "safety or total-outage level issue."
            ),
        },
        "safety_flag": {
            "type": "BOOLEAN",
            "description": (
                "True if the description suggests an immediate physical "
                "safety risk (exposed wiring, sparks, gas smell, structural "
                "collapse risk, etc.), false otherwise."
            ),
        },
        "photo_matches_text": {
            "type": "BOOLEAN",
            "description": (
                "True if a photo was provided and it visibly corroborates "
                "the text description. True when no photo was provided is "
                "not meaningful — callers should treat 'no photo' as N/A, "
                "not as a match; the model should still return a boolean "
                "here and default it to false when there is no photo."
            ),
        },
        "summary": {
            "type": "STRING",
            "description": (
                "A short (<= 2 sentence), normalized, third-person summary "
                "of the complaint suitable for display to an admin and for "
                "generating an embedding from — strip filler words, keep "
                "concrete nouns (what/where)."
            ),
        },
        "extracted_location_hint": {
            "type": "STRING",
            "description": (
                "A building/room/landmark hint pulled out of the free text, "
                "if any is present (e.g. 'Block C, 2nd floor washroom'). "
                "Empty string if nothing location-specific is mentioned."
            ),
        },
    },
    "required": [
        "category",
        "severity",
        "safety_flag",
        "photo_matches_text",
        "summary",
    ],
    "property_ordering": [
        "category",
        "severity",
        "safety_flag",
        "photo_matches_text",
        "summary",
        "extracted_location_hint",
    ],
}


@dataclass
class ComplaintUnderstanding:
    """Provider-agnostic result of understanding one complaint.

    Same fields as ``GEMINI_RESPONSE_SCHEMA`` above — this is what
    ``AIProvider.understand_complaint`` returns, regardless of which
    concrete provider produced it (Gemini or mock).
    """

    category: str
    severity: int
    safety_flag: bool
    photo_matches_text: bool
    summary: str
    extracted_location_hint: str = ""
    raw: dict = field(default_factory=dict, repr=False, compare=False)
    """Original provider payload, kept around for debugging/logging only.
    Never rely on this field's shape in downstream code."""

    def __post_init__(self) -> None:
        if self.category not in CATEGORY_SLUGS:
            self.category = "other"
        # Clamp defensively — a model can misbehave even with a schema.
        self.severity = max(1, min(5, int(self.severity)))

    def as_dict(self) -> dict:
        """JSON-serializable view, excluding the raw provider payload."""
        return {
            "category": self.category,
            "severity": self.severity,
            "safety_flag": self.safety_flag,
            "photo_matches_text": self.photo_matches_text,
            "summary": self.summary,
            "extracted_location_hint": self.extracted_location_hint,
        }
