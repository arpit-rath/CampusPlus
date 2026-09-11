"""Ask CampusPlus — natural-language querying over admin complaint data.

Implementation-plan phase 11 is emphatic that the model must never execute
arbitrary SQL, and that answers must be grounded in real rows. The design
here takes that literally and splits the job in two:

1. **`extract_filters` (no model involved).** The question is parsed into a
   small, closed set of typed filters — category slug, building, status,
   recurring-only, safety-only, a day window, and a "most urgent" ordering
   hint. Anything it does not recognise is simply not filtered on. This is
   a vocabulary match against values that exist in our own schema, so there
   is no injection surface: the question text never reaches SQL, only the
   enum values it matched do.

2. **`answer_admin_question` (model summarizes, nothing more).** The
   filters run as an ordinary parameterized SQLAlchemy query. The rows that
   come back are handed to the provider as data, with an instruction to
   answer only from them. Whatever ids the model names are then intersected
   with the ids we actually supplied, so a hallucinated id cannot survive
   into the response even if the model invents one.

The result is that the worst a bad model answer can do is be unhelpful. It
cannot read a row the caller was not entitled to, and it cannot cite a
complaint that does not exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.provider import AIProvider, get_provider
from app.ai.schemas import CATEGORY_SLUGS
from app.db.models import Category, Complaint, ComplaintCluster

# Words in the question that map onto a category slug. Kept next to
# CATEGORY_SLUGS so an added category is one edit away from being askable.
_CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "wifi": ("wifi", "wi-fi", "internet", "network", "connectivity", "broadband"),
    "electrical": ("electrical", "electricity", "power", "wiring", "socket", "outlet", "light"),
    "sanitation": ("sanitation", "water", "toilet", "washroom", "bathroom", "hygiene", "garbage", "drain", "leak"),
    # "building" is deliberately absent. It is overwhelmingly a question word
    # ("which building has the most...?") rather than a category signal, and
    # including it silently narrowed general questions down to infrastructure.
    "infrastructure": ("infrastructure", "ceiling", "door", "window", "lift", "elevator", "furniture", "structural"),
    "academics": ("academics", "academic", "class", "lecture", "exam", "faculty", "timetable"),
    "other": ("other",),
}

_STATUS_SYNONYMS: dict[str, tuple[str, ...]] = {
    "open": ("open", "unresolved", "outstanding", "pending"),
    "in_progress": ("in progress", "in-progress", "being fixed", "underway", "ongoing"),
    "resolved": ("resolved", "closed", "fixed", "done"),
}

_RECURRING_WORDS = ("recurring", "repeated", "repeat", "again and again", "keeps happening", "chronic")
# Only words that actually mean *physical danger*. "urgent" and "risk" used to
# be here and were wrong: "the most urgent problems" is a question about
# priority ordering, not a request to see only safety-flagged rows, and
# treating it as a filter quietly hid every non-safety complaint.
_SAFETY_WORDS = ("safety", "unsafe", "dangerous", "danger", "hazard", "hazardous")

# "this week" / "last 3 days" / "past month" -> a day window.
_NAMED_WINDOWS: list[tuple[tuple[str, ...], int]] = [
    (("today", "past 24 hours", "last 24 hours"), 1),
    (("this week", "past week", "last week", "last 7 days", "past 7 days"), 7),
    (("this month", "past month", "last month", "last 30 days", "past 30 days"), 30),
    (("this term", "this semester"), 120),
]
_NUMERIC_WINDOW_RE = re.compile(r"\b(?:last|past)\s+(\d{1,3})\s*(day|week|month)s?\b")

_MAX_RECORDS_TO_MODEL = 25
_MAX_RECORDS_TO_FETCH = 200

# --- scope gate ---------------------------------------------------------
#
# Words that make a question unambiguously about *this* corpus. A question
# that matches none of them, and that also produced no typed filter, is not
# a question about campus complaints and is refused before any rows are
# fetched or any model is called.
#
# "problem" and "issue" are deliberately absent. They are ordinary English
# nouns, and treating them as domain evidence is exactly how "can you solve
# python problems for me" came back with a summary of the complaint queue.
# They still reach the corpus in a real question, because a real one carries
# something else with it — a category, a building, a status, a time window,
# or one of the nouns below.
_DOMAIN_WORDS: tuple[str, ...] = (
    "complaint", "complaints", "complain", "complained", "grievance", "grievances",
    "report", "reports", "reported", "ticket", "tickets", "queue", "backlog",
    "cluster", "clusters", "recurring", "duplicate", "duplicates", "merge", "merged",
    "priority", "priorities", "severity", "urgency", "escalate", "escalated", "sla",
    "campus", "building", "buildings", "hostel", "dorm", "block", "room", "rooms",
    "floor", "basement", "corridor", "classroom", "lab", "laboratory", "library",
    "cafeteria", "canteen", "mess", "washroom", "toilet", "hall",
    "facilities", "maintenance", "janitor", "plumbing", "repair", "repairs",
    "department", "departments", "student", "students", "reporter", "reporters",
    "resolved", "unresolved", "outstanding", "triage",
)

_OUT_OF_SCOPE_ANSWER = (
    "I can't answer that — I only answer questions about the campus "
    "complaints recorded in this system, using those records and nothing "
    "else. Please retype your question so it asks about complaints, a "
    "building, a category (wifi, electrical, sanitation, infrastructure, "
    "academics), a status, or a time window. For example: "
    '"any safety issues this week?" or '
    '"what wifi complaints are still open in Innovation Hall?"'
)

_OUT_OF_SCOPE_FILTERS = "out of scope — not a question about campus complaints"


def _mentions(text: str, phrase: str) -> bool:
    """Whole-word/phrase containment.

    Plain substring matching is wrong here in a way that silently corrupts
    results: "unresolved" contains "resolved", so "show unresolved issues"
    was being read as asking for open AND resolved complaints at once. Word
    boundaries also stop a category keyword matching inside an unrelated
    longer word.
    """
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


@dataclass
class QueryFilters:
    """The closed set of things a natural-language question can influence."""

    category_slugs: list[str] = field(default_factory=list)
    buildings: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    recurring_only: bool = False
    safety_only: bool = False
    window_days: int | None = None

    def describe(self) -> str:
        """Human-readable rendering, shown to the admin so the filtering is
        never a black box — they can see exactly what the question was read
        as before trusting the answer."""
        parts: list[str] = []
        if self.category_slugs:
            parts.append("category " + "/".join(self.category_slugs))
        if self.buildings:
            parts.append("in " + "/".join(self.buildings))
        if self.statuses:
            parts.append("status " + "/".join(self.statuses))
        if self.recurring_only:
            parts.append("recurring only")
        if self.safety_only:
            parts.append("safety-flagged only")
        if self.window_days:
            parts.append(f"last {self.window_days} day(s)")
        return ", ".join(parts) if parts else "no filters (all complaints)"


def extract_filters(question: str, known_buildings: list[str]) -> QueryFilters:
    """Map a free-text question onto typed filters. Never touches SQL.

    `known_buildings` comes from the database, so a building name only
    becomes a filter if it is a real building we already store.
    """
    text = question.lower()
    filters = QueryFilters()

    for slug, words in _CATEGORY_SYNONYMS.items():
        if slug in CATEGORY_SLUGS and any(_mentions(text, word) for word in words):
            filters.category_slugs.append(slug)

    for building in known_buildings:
        if building and building.lower() in text:
            filters.buildings.append(building)

    for status_value, words in _STATUS_SYNONYMS.items():
        if any(_mentions(text, word) for word in words):
            filters.statuses.append(status_value)

    filters.recurring_only = any(_mentions(text, word) for word in _RECURRING_WORDS)
    filters.safety_only = any(_mentions(text, word) for word in _SAFETY_WORDS)

    for words, days in _NAMED_WINDOWS:
        if any(_mentions(text, word) for word in words):
            filters.window_days = days
            break
    match = _NUMERIC_WINDOW_RE.search(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        filters.window_days = amount * {"day": 1, "week": 7, "month": 30}[unit]

    return filters


def is_in_scope(question: str, filters: QueryFilters) -> bool:
    """Whether a question is about the complaint corpus at all.

    Evidence is either a typed filter the question already produced — a real
    category, a real building, a status, a window — or one of the domain
    nouns above. Both are conservative on purpose: a legitimate question that
    is turned away costs a rephrase, while an off-topic one that gets through
    produces a confident answer to a question nobody asked, which is the more
    expensive failure for a tool whose whole claim is that it only speaks
    from records.
    """
    if filters != QueryFilters():
        return True
    text = question.lower()
    return any(_mentions(text, word) for word in _DOMAIN_WORDS)


async def fetch_records(
    db: AsyncSession, filters: QueryFilters, *, limit: int = _MAX_RECORDS_TO_FETCH
) -> list[dict[str, Any]]:
    """Run `filters` as one parameterized query and flatten the rows.

    Ordered by priority so that, when the result set is truncated, what
    survives is what an administrator would most want to hear about.
    """
    stmt = (
        select(Complaint)
        .options(
            selectinload(Complaint.category),
            selectinload(Complaint.department),
            selectinload(Complaint.cluster),
        )
        .order_by(Complaint.priority_score.desc(), Complaint.created_at.desc())
        .limit(limit)
    )

    if filters.category_slugs:
        stmt = stmt.join(Category, Complaint.category_id == Category.id).where(
            Category.slug.in_(filters.category_slugs)
        )
    if filters.buildings:
        stmt = stmt.where(Complaint.location_building.in_(filters.buildings))
    if filters.statuses:
        stmt = stmt.where(Complaint.status.in_(filters.statuses))
    if filters.safety_only:
        stmt = stmt.where(Complaint.safety_flag.is_(True))
    if filters.recurring_only:
        stmt = stmt.join(
            ComplaintCluster, Complaint.cluster_id == ComplaintCluster.id
        ).where(ComplaintCluster.is_recurring.is_(True))
    if filters.window_days:
        since = datetime.now(timezone.utc) - timedelta(days=filters.window_days)
        stmt = stmt.where(Complaint.created_at >= since)

    complaints = (await db.execute(stmt)).scalars().all()
    return [_record(c) for c in complaints]


def _record(complaint: Complaint) -> dict[str, Any]:
    """The compact projection handed to the model — no raw photo, no internals."""
    return {
        "id": str(complaint.id),
        "ai_summary": complaint.ai_summary,
        "raw_description": complaint.raw_description[:400],
        "category_slug": complaint.category.slug if complaint.category else None,
        "department_name": complaint.department.name if complaint.department else None,
        "location_building": complaint.location_building,
        "location_room": complaint.location_room,
        "severity": complaint.severity,
        "safety_flag": complaint.safety_flag,
        "status": complaint.status,
        "priority_score": round(complaint.priority_score or 0.0, 3),
        "is_recurring": bool(complaint.cluster and complaint.cluster.is_recurring),
        "independent_student_count": (
            complaint.cluster.independent_student_count if complaint.cluster else 1
        ),
        "created_at": complaint.created_at.isoformat() if complaint.created_at else None,
    }


async def known_buildings(db: AsyncSession) -> list[str]:
    rows = (
        await db.execute(
            select(Complaint.location_building)
            .where(Complaint.location_building.isnot(None))
            .distinct()
        )
    ).scalars().all()
    return [r for r in rows if r]


# Order in which filters are given up when a question matches nothing, most
# speculative first. Inferring a category from a loose synonym is the guess
# most likely to be wrong; a building name the admin typed verbatim is the
# one least likely to be, so it is never dropped.
_RELAXATION_ORDER: tuple[tuple[str, str], ...] = (
    ("safety_only", "the safety-only filter"),
    ("category_slugs", "the category filter"),
    ("window_days", "the time window"),
    ("statuses", "the status filter"),
    ("recurring_only", "the recurring-only filter"),
)


async def _fetch_with_relaxation(
    db: AsyncSession, filters: QueryFilters
) -> tuple[list[dict[str, Any]], QueryFilters, list[str]]:
    """Fetch rows, progressively dropping the most speculative filters.

    A question like "which building has the most urgent recurring problems?"
    can parse into several filters at once and AND itself down to nothing,
    which is a useless answer to a reasonable question. Rather than give up,
    widen one filter at a time and tell the caller what was given up, so the
    admin sees "no recurring wifi issues; here are the recurring issues
    across all categories" instead of a dead end. Honest, and far more useful
    than a bare zero.
    """
    records = await fetch_records(db, filters)
    if records:
        return records, filters, []

    relaxed = replace(filters)
    dropped: list[str] = []
    empty = QueryFilters()

    for attribute, description in _RELAXATION_ORDER:
        if getattr(relaxed, attribute) == getattr(empty, attribute):
            continue  # not set, nothing to drop
        setattr(relaxed, attribute, getattr(empty, attribute))
        dropped.append(description)

        records = await fetch_records(db, relaxed)
        if records:
            return records, relaxed, dropped

    return [], relaxed, dropped


async def answer_admin_question(
    db: AsyncSession, question: str, *, provider: AIProvider | None = None
) -> dict:
    """Answer one admin question, grounded in real rows.

    Returns `{"answer", "cited_complaint_ids", "filters", "matched_count"}`.
    Every id in `cited_complaint_ids` is guaranteed to belong to a complaint
    that was actually in the filtered result set.
    """
    requested = extract_filters(question, await known_buildings(db))

    # Refused before any query runs and before the model is called: an
    # off-topic question has no rows to be grounded in, so anything said
    # about it would be the one thing this endpoint promises never to do.
    if not is_in_scope(question, requested):
        return {
            "answer": _OUT_OF_SCOPE_ANSWER,
            "cited_complaint_ids": [],
            "filters": _OUT_OF_SCOPE_FILTERS,
            "matched_count": 0,
            "in_scope": False,
        }

    records, filters, dropped = await _fetch_with_relaxation(db, requested)

    if not records:
        return {
            "answer": (
                "No complaints match that question "
                f"({requested.describe()}). Try a different category "
                f"({', '.join(CATEGORY_SLUGS)}), another building, or a "
                "longer time window."
            ),
            "cited_complaint_ids": [],
            "filters": requested.describe(),
            "matched_count": 0,
            "in_scope": True,
        }

    shown = records[:_MAX_RECORDS_TO_MODEL]
    allowed_ids = {r["id"] for r in shown}

    ai = provider or get_provider()
    result = await ai.answer_question(
        question,
        shown,
        schema_hint=(
            f"These are the {len(shown)} highest-priority of {len(records)} "
            f"complaints matching: {filters.describe()}."
        ),
    )

    answer = (result.get("answer") or "").strip()
    if not answer:
        answer = f"Found {len(records)} matching complaint(s) ({filters.describe()})."

    if dropped:
        # Never let a widened search pass as an exact one.
        answer = (
            f"Nothing matched exactly, so I relaxed {', '.join(dropped)}. "
            f"{answer}"
        )

    # The grounding guarantee: intersect, preserving the model's ordering,
    # and fall back to the rows we showed it if it cited nothing usable.
    cited = [str(c) for c in result.get("cited_complaint_ids", [])]
    cited = [c for c in dict.fromkeys(cited) if c in allowed_ids]
    if not cited:
        cited = [r["id"] for r in shown[:5]]

    description = filters.describe()
    if dropped:
        description += f" (relaxed: {', '.join(dropped)})"

    return {
        "answer": answer,
        "cited_complaint_ids": cited,
        "filters": description,
        "matched_count": len(records),
        "in_scope": True,
    }
