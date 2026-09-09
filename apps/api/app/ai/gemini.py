"""`GeminiProvider` — the real `AIProvider` implementation, backed by the
`google-genai` SDK.

Every SDK assumption below was verified by introspecting the installed
`google-genai==2.22.0` (the version `requirements.txt` now pins; the
scaffold's original 0.7.0 pin predates the Gemini 3.x models this targets):

- `from google import genai` exposes `genai.Client(api_key=...)`.
- Async calls live under `client.aio.models.*` — `generate_content` and
  `embed_content` are both present on `AsyncModels`.
- `types.Part.from_text(*, text)` and
  `types.Part.from_bytes(*, data, mime_type)` are keyword-only.
- `types.GenerateContentConfig` accepts `response_mime_type` and
  `response_schema`; a plain JSON-schema-shaped dict (uppercase `"OBJECT"`
  / `"STRING"` type values — see `schemas.py`) is accepted, which is why
  this module needs no SDK import to define its schemas.
- `types.EmbedContentConfig` accepts `task_type` and
  `output_dimensionality`.

Model choices, re-verified against the live docs (build-plan.md section 12
explicitly asks for this before building):

- `gemini-3.8-flash` is current and is the default generation model.
- `gemini-embedding-001` supports `task_type="CLUSTERING"` and
  `output_dimensionality` in 128..3072, so the plan's 768-dim Matryoshka
  truncation is real and supported. Truncated vectors from *this* model
  are **not** auto-normalized, so `_normalize` below does it explicitly.
- The newer `gemini-embedding-2` drops `task_type` entirely and
  auto-normalizes. `_embed_config` detects that family by name and simply
  omits `task_type`, so switching models is an env-var change rather than
  a code change.

If `LLM_PROVIDER=gemini` and anything here fails, `FallbackProvider`
degrades the call to `MockProvider` — this file breaking should never take
the app down.
"""

from __future__ import annotations

import json
import logging
import math

from app.ai.provider import AIProvider
from app.ai.schemas import (
    GEMINI_ANSWER_SCHEMA,
    GEMINI_RESPONSE_SCHEMA,
    ComplaintUnderstanding,
    MalformedUnderstandingError,
    parse_understanding,
)
from app.config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768

# Embedding models that do not accept `task_type` (they take task
# instructions in the prompt instead) and that normalize truncated
# dimensions themselves.
_NO_TASK_TYPE_PREFIXES = ("gemini-embedding-2",)

_UNDERSTAND_INSTRUCTIONS = (
    "You are the intake classifier for a campus facilities complaint "
    "system. Read the student's report below (and the attached photo, if "
    "present) and return the structured fields defined by the response "
    "schema.\n\n"
    "Rules:\n"
    "- Be conservative with severity=5 and safety_flag=true: reserve them "
    "for genuine urgent or physical-safety issues (exposed wiring, sparks, "
    "gas, structural collapse risk, flooding).\n"
    "- `summary` must be a normalized, third-person, at-most-two-sentence "
    "restatement that keeps the concrete what and where and drops filler. "
    "It is embedded for duplicate detection, so two students describing "
    "the same real-world problem should produce near-identical summaries.\n"
    "- `photo_matches_text` must be false when no photo was provided.\n\n"
    "Student report:\n"
)


def _guess_image_mime_type(image_bytes: bytes) -> str:
    """Best-effort mime type sniff from magic bytes; defaults to jpeg."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _extract_json(text: str) -> object:
    """Parse a model response that should be JSON.

    We ask for `response_mime_type="application/json"`, so the happy path
    is a bare `json.loads`. The fallback strips a markdown fence and grabs
    the outermost braces, which is what a model occasionally emits when it
    decides to be helpful — cheap insurance versus a failed demo.
    """
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    if stripped.startswith("```"):
        stripped = stripped.split("```")[1]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        try:
            return json.loads(stripped.strip())
        except json.JSONDecodeError:
            pass

    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        return json.loads(stripped[start : end + 1])

    raise MalformedUnderstandingError(
        f"provider response was not JSON: {text[:200]!r}"
    )


def _normalize(values: list[float]) -> list[float]:
    """L2-normalize so cosine distance and dot product agree.

    `gemini-embedding-001` returns unit vectors only at its full 3072
    dimensions; a Matryoshka-truncated 768-dim vector is not unit length.
    Cosine similarity is scale-invariant so this does not change our
    thresholds, but it keeps the vectors we hand to pgvector consistent
    with the ones `MockProvider` produces and makes any future switch to a
    dot-product operator class safe.
    """
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0.0:
        raise ValueError("embedding provider returned a zero vector")
    return [v / norm for v in values]


class GeminiProvider(AIProvider):
    """`AIProvider` implementation backed by Gemini via `google-genai`."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.gemini_model
        self._embedding_model = settings.gemini_embedding_model

        if not settings.llm_api_key:
            raise ValueError(
                "LLM_PROVIDER=gemini but LLM_API_KEY is empty. Set it in "
                "apps/api/.env (never hardcode a key), or use "
                "LLM_PROVIDER=mock."
            )

        # Imported lazily (not at module import time) so `MockProvider`
        # keeps working in an environment that never installed
        # `google-genai` — `get_provider()` only imports this module at all
        # when `LLM_PROVIDER=gemini`.
        from google import genai  # type: ignore[import-not-found]

        self._genai = genai
        self._client = genai.Client(api_key=settings.llm_api_key)

    # --- config builders ------------------------------------------------

    def _generation_config(self, schema: dict):
        return self._genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )

    def _embed_config(self):
        types = self._genai.types
        kwargs: dict = {"output_dimensionality": EMBEDDING_DIM}
        if not self._embedding_model.startswith(_NO_TASK_TYPE_PREFIXES):
            # CLUSTERING is the documented task type for "group texts by
            # similarity", which is exactly what duplicate detection is.
            kwargs["task_type"] = "CLUSTERING"
        return types.EmbedContentConfig(**kwargs)

    # --- AIProvider -----------------------------------------------------

    async def understand_complaint(
        self, description: str, image_bytes: bytes | None
    ) -> ComplaintUnderstanding:
        types = self._genai.types

        parts = [types.Part.from_text(text=_UNDERSTAND_INSTRUCTIONS + description)]
        if image_bytes:
            parts.append(
                types.Part.from_bytes(
                    data=image_bytes, mime_type=_guess_image_mime_type(image_bytes)
                )
            )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=parts,
            config=self._generation_config(GEMINI_RESPONSE_SCHEMA),
        )

        payload = _extract_json(response.text or "")
        understanding = parse_understanding(
            payload, fallback_summary=description[:180]
        )
        # A photo the model never saw can't corroborate anything; enforce
        # the schema's own rule rather than trusting the model to.
        if image_bytes is None:
            understanding.photo_matches_text = False
        return understanding

    async def embed(self, text: str) -> list[float]:
        response = await self._client.aio.models.embed_content(
            model=self._embedding_model,
            contents=text,
            config=self._embed_config(),
        )

        embeddings = getattr(response, "embeddings", None)
        if not embeddings:
            raise ValueError("gemini embed_content returned no embeddings")

        values = list(embeddings[0].values or [])
        if len(values) != EMBEDDING_DIM:
            # The rest of the system (the pgvector column, cluster.py's
            # cosine similarity) hard-assumes 768 dims.
            raise ValueError(
                f"gemini embedding returned {len(values)} dims, expected "
                f"{EMBEDDING_DIM} — check `output_dimensionality` support "
                f"for model {self._embedding_model!r}."
            )
        return _normalize(values)

    async def answer_question(
        self, question: str, records: list[dict], schema_hint: str = ""
    ) -> dict:
        """Summarize pre-fetched complaint records in answer to `question`.

        The model is given data and a question, never a database handle and
        never the ability to shape a query — see `app/pipeline/ask.py` for
        where the filtering actually happens.
        """
        prompt = (
            "You are an analyst for a campus facilities team. Answer the "
            "administrator's question using ONLY the complaint records in "
            "the JSON below. Do not speculate beyond them and do not "
            "invent complaint ids.\n\n"
            + (f"Context: {schema_hint}\n\n" if schema_hint else "")
            + f"Question: {question}\n\n"
            + f"Complaint records (JSON):\n{json.dumps(records, default=str)}"
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[self._genai.types.Part.from_text(text=prompt)],
            config=self._generation_config(GEMINI_ANSWER_SCHEMA),
        )

        payload = _extract_json(response.text or "")
        if not isinstance(payload, dict):
            raise ValueError("gemini answer_question returned a non-object payload")

        answer = payload.get("answer")
        cited = payload.get("cited_complaint_ids")
        return {
            "answer": answer if isinstance(answer, str) and answer.strip() else "",
            "cited_complaint_ids": [str(c) for c in cited] if isinstance(cited, list) else [],
        }
