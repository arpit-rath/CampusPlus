"""Tests for the "Ask CampusPluse" query layer.

The security-relevant half of this feature is `extract_filters`: it is what
guarantees the model never influences a query. These tests are all about
that boundary — that a question is reduced to typed values drawn from our
own schema, and that text which matches nothing simply filters nothing
rather than leaking through.

The grounding guarantee (cited ids are always real) is exercised against a
live database in `test_pipeline_db.py`, since it depends on the actual
fetch.
"""

from __future__ import annotations

from app.pipeline.ask import QueryFilters, extract_filters

BUILDINGS = ["Innovation Hall", "Hostel Block B", "Main Library"]


def test_extracts_category_from_a_synonym_not_just_the_slug():
    filters = extract_filters("why is the internet so bad", BUILDINGS)
    assert filters.category_slugs == ["wifi"]


def test_extracts_building_only_when_it_actually_exists():
    filters = extract_filters("what is happening in Innovation Hall", BUILDINGS)
    assert filters.buildings == ["Innovation Hall"]

    unknown = extract_filters("what is happening in Atlantis", BUILDINGS)
    assert unknown.buildings == []


def test_building_match_is_case_insensitive():
    filters = extract_filters("anything in innovation hall?", BUILDINGS)
    assert filters.buildings == ["Innovation Hall"]


def test_extracts_status():
    assert extract_filters("show unresolved issues", BUILDINGS).statuses == ["open"]
    assert extract_filters("what got fixed", BUILDINGS).statuses == ["resolved"]


def test_extracts_recurring_and_safety_flags():
    filters = extract_filters("which recurring problems are dangerous", BUILDINGS)
    assert filters.recurring_only is True
    assert filters.safety_only is True


def test_named_time_windows():
    assert extract_filters("what happened this week", BUILDINGS).window_days == 7
    assert extract_filters("anything today", BUILDINGS).window_days == 1
    assert extract_filters("past month summary", BUILDINGS).window_days == 30


def test_numeric_time_window_overrides_named_one():
    assert extract_filters("in the last 3 days", BUILDINGS).window_days == 3
    assert extract_filters("over the past 2 weeks", BUILDINGS).window_days == 14


def test_question_with_no_recognizable_terms_filters_nothing():
    """The important negative case: unrecognized text must not become a filter.

    This is what keeps the question out of SQL entirely — there is no
    free-text term that can survive into a query.
    """
    filters = extract_filters("hello there, how are things", BUILDINGS)
    assert filters == QueryFilters()
    assert filters.describe() == "no filters (all complaints)"


def test_injection_attempt_is_inert():
    """A question containing SQL is just words that match no vocabulary."""
    filters = extract_filters("'; DROP TABLE complaints; --", BUILDINGS)
    assert filters.category_slugs == []
    assert filters.buildings == []
    assert filters.statuses == []
    assert filters.window_days is None


def test_describe_is_readable_for_a_compound_question():
    filters = extract_filters(
        "recurring wifi problems in Innovation Hall this week", BUILDINGS
    )
    description = filters.describe()
    assert "wifi" in description
    assert "Innovation Hall" in description
    assert "recurring" in description
    assert "7 day" in description


# --- regressions from driving the real UI --------------------------------
#
# Both of these were found by asking the running dashboard a perfectly
# reasonable question and getting zero results back.


def test_which_building_is_not_read_as_the_infrastructure_category():
    """"Which building has..." is a question phrasing, not a category.

    "building" used to be an infrastructure synonym, so every general
    question that started this way was silently narrowed to one category.
    """
    filters = extract_filters(
        "Which building has the most recurring problems?", BUILDINGS
    )
    assert filters.category_slugs == []
    assert filters.recurring_only is True


def test_urgent_is_about_priority_not_a_safety_filter():
    """"Most urgent" asks for ordering, not for safety-flagged rows only.

    Treating it as a filter hid every complaint that was serious but not a
    physical hazard.
    """
    assert extract_filters("what are the most urgent issues", BUILDINGS).safety_only is False
    assert extract_filters("what is at risk of getting worse", BUILDINGS).safety_only is False
    # Genuinely safety-shaped wording still filters.
    assert extract_filters("any dangerous problems", BUILDINGS).safety_only is True
    assert extract_filters("show me safety issues", BUILDINGS).safety_only is True
