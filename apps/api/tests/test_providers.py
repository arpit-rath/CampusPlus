"""Provider-layer tests: schema repair, mock behaviour, and the fallback.

The fallback is the one piece of this system whose whole job is to behave
correctly when something else is broken, so it gets tested against the
specific failure modes a live demo actually hits: a hang, a rate-limit
error, and output that does not match the schema.
"""

from __future__ import annotations

import asyncio

import pytest

from app.ai.fallback import FallbackProvider
from app.ai.mock import MockProvider
from app.ai.schemas import (
    CATEGORY_SLUGS,
    MalformedUnderstandingError,
    parse_understanding,
)


def run(coro):
    return asyncio.run(coro)


# --- schema repair -------------------------------------------------------


def test_parse_understanding_accepts_a_well_formed_payload():
    result = parse_understanding(
        {
            "category": "wifi",
            "severity": 4,
            "safety_flag": False,
            "photo_matches_text": True,
            "summary": "WiFi is down in Block C.",
            "extracted_location_hint": "Block C",
        }
    )
    assert result.category == "wifi"
    assert result.severity == 4
    assert result.photo_matches_text is True


def test_parse_understanding_repairs_an_unknown_category():
    result = parse_understanding(
        {"category": "plumbing", "severity": 3, "summary": "A leak."}
    )
    assert result.category == "other"
    assert result.category in CATEGORY_SLUGS


def test_parse_understanding_coerces_and_clamps_severity():
    assert parse_understanding({"severity": "5", "summary": "x"}).severity == 5
    assert parse_understanding({"severity": 99, "summary": "x"}).severity == 5
    assert parse_understanding({"severity": -4, "summary": "x"}).severity == 1
    # A severity the model omitted entirely defaults to the middle of the
    # scale rather than to either extreme.
    assert parse_understanding({"summary": "x"}).severity == 3


def test_parse_understanding_coerces_string_booleans():
    result = parse_understanding(
        {"summary": "x", "safety_flag": "true", "photo_matches_text": "no"}
    )
    assert result.safety_flag is True
    assert result.photo_matches_text is False


def test_parse_understanding_falls_back_when_summary_is_missing():
    result = parse_understanding({"category": "wifi"}, fallback_summary="raw text here")
    assert result.summary == "raw text here"


def test_parse_understanding_rejects_a_non_object_payload():
    with pytest.raises(MalformedUnderstandingError):
        parse_understanding(["not", "an", "object"])


def test_parse_understanding_rejects_no_summary_and_no_fallback():
    with pytest.raises(MalformedUnderstandingError):
        parse_understanding({"category": "wifi"})


# --- mock provider -------------------------------------------------------


def test_mock_embed_is_deterministic_and_correct_width():
    a = run(MockProvider().embed("wifi is down in Block C"))
    b = run(MockProvider().embed("wifi is down in Block C"))
    assert a == b
    assert len(a) == 768


def test_mock_answer_question_is_grounded_in_the_records_it_is_given():
    records = [
        {"id": "c1", "category_slug": "wifi", "location_building": "Block A", "priority_score": 0.8, "ai_summary": "WiFi down"},
        {"id": "c2", "category_slug": "wifi", "location_building": "Block A", "priority_score": 0.4, "ai_summary": "No signal"},
    ]
    result = run(MockProvider().answer_question("what is wrong with wifi", records))
    assert set(result["cited_complaint_ids"]) == {"c1", "c2"}
    assert "2 complaint(s)" in result["answer"]
    assert "Block A" in result["answer"]


def test_mock_answer_question_with_no_records():
    result = run(MockProvider().answer_question("anything?", []))
    assert result["cited_complaint_ids"] == []
    assert "No complaints" in result["answer"]


# --- fallback ------------------------------------------------------------


class _HangingProvider:
    """Never returns — stands in for a provider that has stopped responding."""

    async def understand_complaint(self, description, image_bytes):
        await asyncio.sleep(30)
        raise AssertionError("should have timed out")

    async def embed(self, text):
        await asyncio.sleep(30)
        raise AssertionError("should have timed out")

    async def answer_question(self, question, records, schema_hint=""):
        await asyncio.sleep(30)
        raise AssertionError("should have timed out")


class _RateLimitedProvider:
    """Raises the way a quota-exhausted API client does."""

    async def understand_complaint(self, description, image_bytes):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    async def embed(self, text):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    async def answer_question(self, question, records, schema_hint=""):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")


class _WorkingProvider:
    async def understand_complaint(self, description, image_bytes):
        return parse_understanding(
            {"category": "wifi", "severity": 5, "summary": "from the live provider"}
        )

    async def embed(self, text):
        return [1.0] + [0.0] * 767

    async def answer_question(self, question, records, schema_hint=""):
        return {"answer": "live answer", "cited_complaint_ids": []}


def _fallback(primary, timeout=0.05):
    return FallbackProvider(
        primary=primary, fallback=MockProvider(), timeout_seconds=timeout
    )


def test_fallback_is_not_used_when_the_primary_works():
    provider = _fallback(_WorkingProvider(), timeout=5)
    result = run(provider.understand_complaint("wifi is down", None))
    assert result.summary == "from the live provider"
    assert provider.primary_calls == 1
    assert provider.fallback_calls == 0


def test_fallback_engages_on_timeout():
    provider = _fallback(_HangingProvider())
    result = run(provider.understand_complaint("the wifi is completely down", None))
    # The mock understood it rather than the request failing.
    assert result.category == "wifi"
    assert provider.fallback_calls == 1
    assert "timed out" in (provider.last_error or "")


def test_fallback_engages_on_a_rate_limit_error():
    provider = _fallback(_RateLimitedProvider(), timeout=5)
    embedding = run(provider.embed("sparking wires in the basement"))
    assert len(embedding) == 768
    assert provider.fallback_calls == 1
    assert "RESOURCE_EXHAUSTED" in (provider.last_error or "")


def test_fallback_covers_every_protocol_method():
    provider = _fallback(_RateLimitedProvider(), timeout=5)
    run(provider.understand_complaint("wifi down", None))
    run(provider.embed("wifi down"))
    run(provider.answer_question("what is down", [{"id": "c1"}]))
    assert provider.fallback_calls == 3
    assert provider.stats()["primary_calls"] == 0


def test_fallback_does_not_swallow_cancellation():
    """A client disconnecting must cancel the request, not silently produce
    a mock result as if the work had succeeded."""

    class _Cancelling:
        async def understand_complaint(self, description, image_bytes):
            raise asyncio.CancelledError()

        async def embed(self, text):  # pragma: no cover
            raise AssertionError

        async def answer_question(self, question, records, schema_hint=""):  # pragma: no cover
            raise AssertionError

    provider = _fallback(_Cancelling(), timeout=5)
    with pytest.raises(asyncio.CancelledError):
        run(provider.understand_complaint("anything", None))
    assert provider.fallback_calls == 0
