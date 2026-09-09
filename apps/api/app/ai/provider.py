"""The `AIProvider` protocol and the factory that picks a concrete one.

Per CLAUDE.md: **never import a provider SDK (google-genai, openai, ...)
from a router or pipeline module.** Always go through `get_provider()`
here. This keeps the system provider-agnostic and demo-safe — if
`LLM_PROVIDER=gemini` and a live call errors or times out, callers are
expected to fall back to `MockProvider` (see `understand_complaint`'s
docstring below) rather than let the request 500.
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

        Implementations should raise on hard failure (bad API key, network
        error, malformed model output that can't be repaired) rather than
        silently returning a low-confidence guess — `understand.py` (or
        whatever calls this) is responsible for deciding whether to retry,
        fall back to `MockProvider`, or propagate the error, per the
        "MockProvider is the automatic fallback on error/timeout" note in
        CLAUDE.md.
        """
        ...

    async def embed(self, text: str) -> list[float]:
        """Return a 768-dim embedding vector for `text`.

        Embed the AI's normalized `summary`, not the raw student text, per
        build-plan.md §4.2. Must always return exactly 768 floats — that's
        the width of the `complaint_embeddings.embedding vector(768)`
        column (CLAUDE.md's data model), so a provider returning a
        different dimensionality is a bug, not a valid variant.
        """
        ...


def get_provider() -> AIProvider:
    """Read `settings.llm_provider` and return the matching concrete provider.

    - `"gemini"` -> `GeminiProvider` (imports `google-genai` lazily, inside
      this branch, so a `mock`-only dev environment never needs the SDK
      installed).
    - `"mock"` (default) -> `MockProvider`.
    - anything else (e.g. the `openai`/`claude` stubs mentioned in
      CLAUDE.md) -> falls back to `MockProvider` for now; there's nothing
      to route to yet.
    """
    settings = get_settings()
    provider = settings.llm_provider.strip().lower()

    if provider == "gemini":
        from app.ai.gemini import GeminiProvider

        return GeminiProvider()

    # "mock" and any not-yet-implemented provider name both land here.
    from app.ai.mock import MockProvider

    return MockProvider()
