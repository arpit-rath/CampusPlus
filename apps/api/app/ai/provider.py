"""The `AIProvider` protocol and the factory that picks a concrete one.

Per CLAUDE.md: **never import a provider SDK (google-genai, openai, ...)
from a router or pipeline module.** Always go through `get_provider()`
here. This keeps the system provider-agnostic and demo-safe.

The "MockProvider is the automatic fallback on error/timeout" promise is
implemented, not just documented: when `LLM_PROVIDER=gemini` and
`LLM_FALLBACK_TO_MOCK` is on (the default), `get_provider()` hands back a
`FallbackProvider` that wraps the live provider, applies
`LLM_TIMEOUT_SECONDS` to every call, and degrades to `MockProvider` on
timeout, rate-limit or API error. Callers therefore never need their own
try/except around a provider call.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.ai.schemas import ComplaintUnderstanding
from app.config import get_settings


@runtime_checkable
class AIProvider(Protocol):
    """Everything the rest of the backend is allowed to know about "the AI"."""

    async def understand_complaint(
        self, description: str, image_bytes: bytes | None
    ) -> ComplaintUnderstanding:
        """Run multimodal understanding on one complaint.

        `image_bytes` is the raw bytes of an optional photo (jpeg/png).
        Pass `None` when no photo was attached — implementations must not
        require a photo.

        Implementations raise on hard failure (bad API key, network error,
        model output that can't be repaired by
        `schemas.parse_understanding`) rather than silently returning a
        low-confidence guess. `FallbackProvider` is what turns those raises
        into a graceful MockProvider degrade.
        """
        ...

    async def embed(self, text: str) -> list[float]:
        """Return a 768-dim embedding vector for `text`.

        Embed the AI's normalized `summary`, not the raw student text, per
        build-plan.md section 4.2. Must always return exactly 768 floats —
        that is the width of the `complaint_embeddings.embedding
        vector(768)` column, so a provider returning a different
        dimensionality is a bug, not a valid variant.
        """
        ...

    async def answer_question(
        self, question: str, records: list[dict], schema_hint: str = ""
    ) -> dict:
        """Answer an admin question *strictly* from `records`.

        `records` are real complaint rows that `app/pipeline/ask.py` has
        already fetched and filtered with ordinary SQLAlchemy — the model
        never writes or influences a query. Returns
        ``{"answer": str, "cited_complaint_ids": list[str]}``; the caller
        intersects the returned ids with the ids it supplied, so a
        hallucinated id can never reach the client.
        """
        ...


def get_provider() -> AIProvider:
    """Read `settings.llm_provider` and return the matching concrete provider.

    - `"gemini"` -> `GeminiProvider` (imports `google-genai` lazily, inside
      this branch, so a `mock`-only dev environment never needs the SDK
      installed), wrapped in `FallbackProvider` unless
      `LLM_FALLBACK_TO_MOCK=false`.
    - `"mock"` (default) -> `MockProvider`.
    - anything else (e.g. the `openai`/`claude` stubs mentioned in
      CLAUDE.md) -> falls back to `MockProvider`; there is nothing to route
      to yet.
    """
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    from app.ai.mock import MockProvider

    if provider == "gemini":
        from app.ai.fallback import FallbackProvider
        from app.ai.gemini import GeminiProvider

        live: AIProvider = GeminiProvider()
        if not settings.llm_fallback_to_mock:
            return live
        return FallbackProvider(
            primary=live,
            fallback=MockProvider(),
            timeout_seconds=settings.llm_timeout_seconds,
        )

    # "mock" and any not-yet-implemented provider name both land here.
    return MockProvider()


def describe_provider() -> dict:
    """Small status blob for `/health`, so a demo can see what is actually live."""
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()
    configured = provider == "gemini" and bool(settings.llm_api_key)
    return {
        "llm_provider": provider,
        "api_key_configured": configured,
        "fallback_to_mock": settings.llm_fallback_to_mock,
        "effective": "gemini" if configured else "mock",
    }
