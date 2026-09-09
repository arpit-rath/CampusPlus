"""`GeminiProvider` — the real `AIProvider` implementation, backed by the
`google-genai` SDK (`requirements.txt` pins `google-genai==0.7.0`).

**This file could not be run against a live install or a real API key in
the environment it was written in** (no PyPI/network access — see the
repo-level constraint in the task this was built under). It's written
carefully against the SDK's documented public interface, but the exact
call signature should be double-checked against the installed
`google-genai==0.7.0` the first time this runs for real. Notable
assumptions, spelled out so the integration pass can verify them fast:

- `from google import genai` exposes `genai.Client(api_key=...)`.
- Async calls live under `client.aio.models.*` (mirroring the sync
  `client.models.*` surface) — `generate_content` and `embed_content`.
- Structured JSON output: `genai.types.GenerateContentConfig(
  response_mime_type="application/json", response_schema=<dict>)`, where
  `response_schema` accepts a plain JSON-schema-shaped dict (uppercase
  `type` values like `"OBJECT"`/`"STRING"` — see `schemas.py`) as well as
  a `genai.types.Schema`. If 0.7.0 requires a `Schema` object instead of a
  raw dict, the fix is localized to `_build_generation_config()` below.
- An image is attached as `genai.types.Part.from_bytes(data=..., mime_type=...)`
  alongside a text `Part` in the same `contents` list.
- Embeddings: `client.aio.models.embed_content(model=..., contents=text,
  config=genai.types.EmbedContentConfig(task_type="CLUSTERING",
  output_dimensionality=768))`, and the result exposes `.embeddings[0].values`
  (a list of floats).
- The response's parsed JSON is available as `response.text` (a JSON
  string, since we asked for `application/json`) — parsed here with
  `json.loads` rather than relying on an SDK-specific `.parsed` accessor,
  since that accessor's exact shape is the part most likely to have
  shifted between SDK versions.

If any of these turn out wrong against the real SDK, `MockProvider` still
makes the rest of the app fully runnable — this file failing to import or
call correctly should only ever matter when `LLM_PROVIDER=gemini`.
"""

from __future__ import annotations

import json
import mimetypes

from app.ai.provider import AIProvider
from app.ai.schemas import GEMINI_RESPONSE_SCHEMA, ComplaintUnderstanding
from app.config import get_settings

EMBEDDING_DIM = 768


def _guess_image_mime_type(image_bytes: bytes) -> str:
    """Best-effort mime type sniff from magic bytes; defaults to jpeg.

    Avoids depending on the caller (a router we don't own) to pass a mime
    type alongside the raw bytes.
    """
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    guess, _ = mimetypes.guess_type("upload.jpg")
    return guess or "image/jpeg"


class GeminiProvider(AIProvider):
    """`AIProvider` implementation backed by Gemini via `google-genai`."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.gemini_model
        self._embedding_model = settings.gemini_embedding_model

        # Imported lazily (not at module import time) so `MockProvider`
        # keeps working in an environment that never installed
        # `google-genai` — `get_provider()` only imports this module at
        # all when `LLM_PROVIDER=gemini`.
        from google import genai  # type: ignore[import-not-found]

        self._genai = genai
        self._client = genai.Client(api_key=settings.llm_api_key)

    def _build_generation_config(self):
        types = self._genai.types
        return types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GEMINI_RESPONSE_SCHEMA,
        )

    async def understand_complaint(
        self, description: str, image_bytes: bytes | None
    ) -> ComplaintUnderstanding:
        types = self._genai.types

        parts = [
            types.Part.from_text(
                text=(
                    "You are the intake classifier for a campus facilities "
                    "complaint system. Read the student's report below "
                    "(and the attached photo, if present) and return the "
                    "structured fields defined by the response schema. "
                    "Be conservative with severity=5 and safety_flag=true — "
                    "reserve them for genuine urgent/safety issues.\n\n"
                    f"Student report:\n{description}"
                )
            )
        ]
        if image_bytes:
            mime_type = _guess_image_mime_type(image_bytes)
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=parts,
            config=self._build_generation_config(),
        )

        payload = json.loads(response.text)
        return ComplaintUnderstanding(
            category=payload.get("category", "other"),
            severity=int(payload.get("severity", 3)),
            safety_flag=bool(payload.get("safety_flag", False)),
            photo_matches_text=bool(payload.get("photo_matches_text", False)),
            summary=payload.get("summary", description[:180]),
            extracted_location_hint=payload.get("extracted_location_hint", "") or "",
            raw=payload,
        )

    async def embed(self, text: str) -> list[float]:
        types = self._genai.types

        response = await self._client.aio.models.embed_content(
            model=self._embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="CLUSTERING",
                output_dimensionality=EMBEDDING_DIM,
            ),
        )

        values = list(response.embeddings[0].values)
        if len(values) != EMBEDDING_DIM:
            # Defensive guard: the rest of the system (the pgvector column,
            # cluster.py's cosine similarity) hard-assumes 768 dims.
            raise ValueError(
                f"gemini embedding returned {len(values)} dims, expected "
                f"{EMBEDDING_DIM} — check `output_dimensionality` support "
                f"for model '{self._embedding_model}'."
            )
        return values
