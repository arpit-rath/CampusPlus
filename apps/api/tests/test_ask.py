"""Tests for `app.pipeline.ask.answer_admin_question`.

Uses `MockProvider` explicitly and `asyncio.run()` — see the note at the
top of `test_understand.py` for why.
"""

from __future__ import annotations

import asyncio

from app.ai.mock import MockProvider
from app.pipeline.ask import answer_admin_question


def run(coro):
    return asyncio.run(coro)


SAMPLE_COMPLAINTS = [
    {
        "id": "c1",
        "raw_description": "Wifi has been down in Sunrise Hostel for two days.",
        "ai_summary": "Wifi issue: Wifi has been down in Sunrise Hostel for two days.",
        "category_slug": "wifi",
        "location_building": "Sunrise Hostel",
        "location_room": "204",
        "department_name": "IT Services",
        "status": "open",
        "safety_flag": False,
        "priority_score": 0.55,
    },
    {
        "id": "c2",
        "raw_description": "No internet connection in the Sunrise Hostel common room.",
        "ai_summary": "Wifi issue: no internet connection in the Sunrise Hostel common room.",
        "category_slug": "wifi",
        "location_building": "Sunrise Hostel",
        "location_room": "common room",
        "department_name": "IT Services",
        "status": "open",
        "safety_flag": False,
        "priority_score": 0.50,
    },
    {
        "id": "c3",
        "raw_description": "Exposed sparking wire near the Twin Towers electrical panel.",
        "ai_summary": "Electrical issue: exposed sparking wire near panel.",
        "category_slug": "electrical",
        "location_building": "Twin Towers",
        "location_room": "basement",
        "department_name": "Facilities",
        "status": "open",
        "safety_flag": True,
        "priority_score": 0.92,
    },
    {
        "id": "c4",
        "raw_description": "Overflowing trash bins outside the cafeteria.",
        "ai_summary": "Sanitation issue: overflowing trash bins outside cafeteria.",
        "category_slug": "sanitation",
        "location_building": "Cafeteria",
        "location_room": None,
        "department_name": "Facilities",
        "status": "resolved",
        "safety_flag": False,
        "priority_score": 0.20,
    },
]


def test_answer_admin_question_filters_by_keyword():
    result = run(
        answer_admin_question(
            "What's going on with wifi in Sunrise Hostel?",
            SAMPLE_COMPLAINTS,
            provider=MockProvider(),
        )
    )
    assert "c1" in result["cited_complaint_ids"]
    assert "c2" in result["cited_complaint_ids"]
    # Electrical/sanitation complaints shouldn't be cited for a wifi/Sunrise
    # Hostel question — c3 is Twin Towers, c4 doesn't mention wifi or the
    # hostel at all, and neither shares a keyword with the question.
    assert "c3" not in result["cited_complaint_ids"]
    assert "c4" not in result["cited_complaint_ids"]
    assert isinstance(result["answer"], str) and result["answer"]


def test_answer_admin_question_filters_by_category_word():
    result = run(
        answer_admin_question(
            "Any electrical complaints?", SAMPLE_COMPLAINTS, provider=MockProvider()
        )
    )
    assert result["cited_complaint_ids"] == ["c3"]


def test_answer_admin_question_cited_ids_are_always_real():
    result = run(
        answer_admin_question(
            "wifi block c", SAMPLE_COMPLAINTS, provider=MockProvider()
        )
    )
    valid_ids = {c["id"] for c in SAMPLE_COMPLAINTS}
    assert set(result["cited_complaint_ids"]) <= valid_ids


def test_answer_admin_question_no_complaints_at_all():
    result = run(answer_admin_question("anything?", [], provider=MockProvider()))
    assert result["cited_complaint_ids"] == []
    assert "answer" in result


def test_answer_admin_question_generic_question_falls_back_to_top_priority():
    # A question with no matching keywords should fall back to considering
    # everything, sorted by priority — the electrical safety issue (0.92)
    # should be surfaced.
    result = run(
        answer_admin_question(
            "give me the current situation", SAMPLE_COMPLAINTS, provider=MockProvider()
        )
    )
    assert "c3" in result["cited_complaint_ids"]


def test_answer_admin_question_returns_expected_shape():
    result = run(
        answer_admin_question("wifi", SAMPLE_COMPLAINTS, provider=MockProvider())
    )
    assert set(result.keys()) == {"answer", "cited_complaint_ids"}
    assert isinstance(result["cited_complaint_ids"], list)
