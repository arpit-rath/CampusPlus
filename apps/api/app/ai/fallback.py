"""`FallbackProvider` — keeps the demo alive when the live provider is not.

Wraps any `AIProvider` and, for every call:

1. applies a hard timeout (`LLM_TIMEOUT_SECONDS`), and
2. on timeout / rate limit / API error / malformed output, re-runs the
   same call against a fallback provider (`MockProvider`).

This is CLAUDE.md's "MockProvider is the automatic fallback when a live
call errors or times out, not just a dev convenience". Nothing downstream
— routers, the pipeline — needs its own try/except around a provider call,
which is exactly the point: there is one place that decides what "the AI
is unavailable" means.

Degradations are logged at WARNING and counted, so `/health` can report
whether the last few complaints were actually understood by Gemini or
quietly by the mock. That matters on stage: silently serving mock output
while claiming it is Gemini would be worse than a visible error.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

from app.ai.provider import AIProvider
from app.ai.schemas import ComplaintUnderstanding

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FallbackProvider(AIProvider):
    """Primary provider with an automatic degrade to `fallback`."""

    def __init__(
        self,
        *,
        primary: AIProvider,
        fallback: AIProvider,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._timeout = timeout_seconds
        # Counters surfaced on /health so "is Gemini actually working?" is
        # answerable without reading logs mid-demo.
        self.primary_calls = 0
        self.fallback_calls = 0
        self.last_error: str | None = None

    async def _call(
        self,
        name: str,
        primary_fn: Callable[[], Awaitable[T]],
        fallback_fn: Callable[[], Awaitable[T]],
    ) -> T:
        try:
            result = await asyncio.wait_for(primary_fn(), timeout=self._timeout)
        except asyncio.TimeoutError:
            self.last_error = f"{name}: timed out after {self._timeout}s"
            logger.warning(
                "AI %s timed out after %ss - falling back to mock", name, self._timeout
            )
        except asyncio.CancelledError:
            # A cancelled request is the client going away, not a provider
            # failure — never swallow it into a mock result.
            raise
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad: any provider-side failure (auth, quota,
            # 5xx, malformed output, SDK surface drift) should degrade
            # rather than 500 during a live demo.
            self.last_error = f"{name}: {type(exc).__name__}: {exc}"
            logger.warning("AI %s failed (%s) - falling back to mock", name, exc)
        else:
            self.primary_calls += 1
            return result

        self.fallback_calls += 1
        return await fallback_fn()

    async def understand_complaint(
        self, description: str, image_bytes: bytes | None
    ) -> ComplaintUnderstanding:
        return await self._call(
            "understand_complaint",
            lambda: self._primary.understand_complaint(description, image_bytes),
            lambda: self._fallback.understand_complaint(description, image_bytes),
        )

    async def embed(self, text: str) -> list[float]:
        return await self._call(
            "embed",
            lambda: self._primary.embed(text),
            lambda: self._fallback.embed(text),
        )

    async def answer_question(
        self, question: str, records: list[dict], schema_hint: str = ""
    ) -> dict:
        return await self._call(
            "answer_question",
            lambda: self._primary.answer_question(question, records, schema_hint),
            lambda: self._fallback.answer_question(question, records, schema_hint),
        )

    def stats(self) -> dict:
        return {
            "primary_calls": self.primary_calls,
            "fallback_calls": self.fallback_calls,
            "last_error": self.last_error,
        }
