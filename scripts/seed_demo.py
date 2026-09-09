#!/usr/bin/env python3
"""Generate realistic demo/test complaint data for CampusPluse.

Standalone script — writes a JSON fixture file, does not hit a running API
(per the task's own guidance: JSON output is fine and safer than a live
POST loop in an environment with no guaranteed running backend). Doubles
as:

- the seed data behind the "live merge" demo moment (a cluster of
  near-duplicate WiFi reports and a cluster of near-duplicate electrical
  reports, both in a single building within a short time window, so
  they're guaranteed to trip the >=0.92 duplicate threshold together), and
- a manual test fixture for `app/pipeline/cluster.py` — this script runs
  the *actual* clustering and priority pipeline (via `MockProvider`, no
  network) over its own generated data and prints a cluster summary, so
  running it is itself a smoke test of `understand.py`/`cluster.py`/
  `priority.py` working together end to end.

Usage:
    python3 scripts/seed_demo.py                # writes scripts/demo_data.json
    python3 scripts/seed_demo.py --out path.json
    python3 scripts/seed_demo.py --pretty        # (default) indented JSON
    python3 scripts/seed_demo.py --compact       # single-line JSON

Every field in the output is deterministic (same run -> same file), since
`MockProvider` is deterministic and every timestamp is computed from a
fixed `DEMO_START` rather than `datetime.now()`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- make `app.*` importable when run as `python3 scripts/seed_demo.py` ---
REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.ai.mock import MockProvider  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.pipeline import cluster, priority  # noqa: E402

# Fixed "now" for the whole demo dataset so output is fully deterministic
# and so the live-merge cluster's timestamps read as "just now, live on
# stage" relative to it. Timezone-aware UTC throughout.
DEMO_START = datetime(2026, 9, 9, 13, 0, 0, tzinfo=timezone.utc)
# "Now" for age_hours purposes — a bit after the latest report, so every
# complaint has a small, plausible, non-zero age.
DEMO_NOW = DEMO_START + timedelta(hours=6)


@dataclass
class RawComplaint:
    student_id: str
    description: str
    location_building: str
    location_room: str | None
    minutes_after_start: int
    has_photo: bool = False


# --- The dataset -----------------------------------------------------------
#
# Two "live merge" clusters (near-duplicate reports, same building, tight
# time window) plus a spread of genuinely distinct issues across other
# buildings/categories, ~28 complaints total.

RAW_COMPLAINTS: list[RawComplaint] = [
    # --- Cluster A: WiFi outage in Innovation Hall (4 reports, ~9 min) ----
    #
    # Deliberately near-identical phrasing across these four — that's
    # realistic (many students describing the exact same live outage
    # naturally converge on very similar wording: "wifi is down", "can't
    # connect", "the network") and, under MockProvider's keyword-weighted
    # embedding, is what reliably pushes pairwise cosine similarity past
    # CLAUDE.md's 0.92 duplicate threshold so this cluster actually forms
    # when this script is run against the mock provider. See the
    # `_SIGNAL_WEIGHT` note in `app/ai/mock.py` for why word choice this
    # deliberate is required to trip the threshold under a hashing-trick
    # embedding rather than a real one.
    RawComplaint(
        "student_014",
        "Wifi is completely down in Innovation Hall right now, nobody on "
        "my floor can connect to the network.",
        "Innovation Hall",
        "204",
        120,
    ),
    RawComplaint(
        "student_057",
        "Wifi is completely down in Innovation Hall again, nobody near me "
        "can connect to the network at all.",
        "Innovation Hall",
        "310",
        123,
    ),
    RawComplaint(
        "student_089",
        "Wifi is completely down in Innovation Hall this afternoon, "
        "nobody in my class can connect to the network.",
        "Innovation Hall",
        "lobby",
        126,
    ),
    RawComplaint(
        "student_132",
        "Wifi is completely down in Innovation Hall still, nobody in the "
        "lobby can connect to the network either.",
        "Innovation Hall",
        "112",
        129,
    ),
    # --- Cluster B: exposed/sparking wiring in Hostel Block B (3, ~40 min) -
    # Same near-identical-phrasing rationale as Cluster A above.
    RawComplaint(
        "student_021",
        "There is exposed sparking wiring near the electrical panel in "
        "the Hostel Block B basement, it looks dangerous.",
        "Hostel Block B",
        "basement",
        180,
    ),
    RawComplaint(
        "student_045",
        "The electrical panel in Hostel Block B basement has exposed "
        "sparking wiring, it still looks very dangerous.",
        "Hostel Block B",
        "basement",
        205,
        has_photo=True,
    ),
    RawComplaint(
        "student_078",
        "Exposed sparking wiring by the electrical panel in Hostel Block "
        "B basement again, it really looks dangerous.",
        "Hostel Block B",
        "basement",
        220,
    ),
    # --- Distinct issues spread across other buildings/categories ---------
    RawComplaint(
        "student_003",
        "The water fountain outside the main library is leaking constantly "
        "and there's a small puddle forming on the floor.",
        "Main Library",
        "ground floor",
        15,
    ),
    RawComplaint(
        "student_009",
        "Toilets on the second floor of the Science Block are clogged and "
        "smell really bad, hasn't been cleaned in days.",
        "Science Block",
        "2nd floor washroom",
        40,
    ),
    RawComplaint(
        "student_012",
        "One of the ceiling fans in lecture hall LH-3 is wobbling badly and "
        "making a loud grinding noise every time it's turned on.",
        "Academic Block A",
        "LH-3",
        55,
    ),
    RawComplaint(
        "student_018",
        "The projector in room 118 hasn't worked for two weeks, professors "
        "keep having to reschedule presentations because of it.",
        "Academic Block A",
        "118",
        70,
    ),
    RawComplaint(
        "student_025",
        "Course registration portal keeps showing the wrong seat count for "
        "my elective, I can't tell if I actually got a spot.",
        "Academic Block A",
        None,
        85,
    ),
    RawComplaint(
        "student_031",
        "Garbage bins outside the cafeteria have been overflowing for three "
        "days straight, trash is spilling onto the walkway.",
        "Cafeteria",
        None,
        95,
    ),
    RawComplaint(
        "student_038",
        "The main gate's automatic barrier is stuck half-open and won't "
        "respond to student ID cards anymore.",
        "Main Gate",
        None,
        100,
    ),
    RawComplaint(
        "student_042",
        "There's a large crack running across the wall in the second floor "
        "corridor of Hostel Block A, it looks like it's getting worse.",
        "Hostel Block A",
        "2nd floor corridor",
        110,
        has_photo=True,
    ),
    RawComplaint(
        "student_050",
        "The elevator in Hostel Block A has been out of service for a week, "
        "everyone with heavy luggage has to use the stairs.",
        "Hostel Block A",
        None,
        140,
    ),
    RawComplaint(
        "student_061",
        "Attendance wasn't recorded correctly for my 9am class even though "
        "I signed in, and now it's affecting my eligibility.",
        "Academic Block B",
        None,
        150,
    ),
    RawComplaint(
        "student_066",
        "A window pane is cracked and loose in the reading room, it rattles "
        "whenever it's windy and feels like it could fall.",
        "Main Library",
        "reading room",
        160,
    ),
    RawComplaint(
        "student_072",
        "The badminton court lights in the sports complex flicker on and "
        "off randomly during evening practice.",
        "Sports Complex",
        None,
        170,
    ),
    RawComplaint(
        "student_080",
        "Hot water hasn't worked in the Hostel Block C showers for four "
        "days now, it's freezing every morning.",
        "Hostel Block C",
        "3rd floor showers",
        190,
    ),
    RawComplaint(
        "student_091",
        "Printer in the computer lab is out of toner and nobody has "
        "refilled it despite multiple requests to the front desk.",
        "Computer Center",
        "lab 2",
        200,
    ),
    RawComplaint(
        "student_099",
        "There's a strong gas smell near the chemistry lab entrance, it's "
        "been there since this morning and nobody has checked it.",
        "Science Block",
        "chemistry lab entrance",
        210,
    ),
    RawComplaint(
        "student_104",
        "Bike racks outside Academic Block B are damaged and half of them "
        "can't actually lock a bike anymore.",
        "Academic Block B",
        None,
        215,
    ),
    RawComplaint(
        "student_110",
        "The AC in the reading room of the main library hasn't been cooling "
        "properly for a week, it's uncomfortably warm during exams.",
        "Main Library",
        "reading room",
        225,
    ),
    RawComplaint(
        "student_118",
        "Streetlights along the path from Hostel Block C to the main gate "
        "are out, it's completely dark walking back at night.",
        "Hostel Block C",
        "outside path",
        235,
    ),
    RawComplaint(
        "student_125",
        "A stray dog has been sleeping in the stairwell of Academic Block A "
        "and some students are scared to use the stairs.",
        "Academic Block A",
        "stairwell",
        245,
    ),
    RawComplaint(
        "student_131",
        "The mess hall ran out of vegetarian options again halfway through "
        "dinner, this is the third time this month.",
        "Cafeteria",
        None,
        250,
    ),
]


def _complaint_id(index: int) -> str:
    return f"demo-{index:03d}"


async def _build_complaint(index: int, raw: RawComplaint, provider: MockProvider) -> dict:
    understanding = await provider.understand_complaint(raw.description, None)
    embedding = await provider.embed(understanding.summary)
    created_at = DEMO_START + timedelta(minutes=raw.minutes_after_start)

    return {
        "id": _complaint_id(index),
        "student_id": raw.student_id,
        "raw_description": raw.description,
        "photo_url": (
            f"https://picsum.photos/seed/{raw.student_id}/640/480"
            if raw.has_photo
            else None
        ),
        "location_building": raw.location_building,
        "location_room": raw.location_room,
        "category_slug": understanding.category,
        "severity": understanding.severity,
        "safety_flag": understanding.safety_flag,
        "photo_matches_text": understanding.photo_matches_text,
        "ai_summary": understanding.summary,
        "extracted_location_hint": understanding.extracted_location_hint,
        "embedding": [round(v, 6) for v in embedding],
        "status": "open",
        "created_at": created_at.isoformat(),
    }


def _scope_key(complaint: dict) -> tuple[str, str]:
    """CLAUDE.md's clustering scope: same category + same building.

    (The rolling 14-day window is irrelevant here — every demo complaint is
    within hours of DEMO_START.)
    """
    return (complaint["category_slug"], complaint["location_building"] or "")


def _attach_clusters_and_priority(complaints: list[dict], recurring_threshold: int) -> None:
    """Mutates `complaints` in place: adds cluster_id/is_recurring/cluster_
    member_count/priority_score/priority_breakdown, using the real
    `cluster.py`/`priority.py` pipeline scoped per CLAUDE.md's rules.
    """
    by_scope: dict[tuple[str, str], list[dict]] = {}
    for c in complaints:
        by_scope.setdefault(_scope_key(c), []).append(c)

    next_cluster_num = 1
    for scope_complaints in by_scope.values():
        items = [(c["id"], c["embedding"]) for c in scope_complaints]
        groups = cluster.cluster_embeddings(items)
        by_id = {c["id"]: c for c in scope_complaints}

        for group_ids in groups:
            member_count = len(group_ids)
            is_recurring = member_count >= recurring_threshold
            cluster_id = f"cluster-{next_cluster_num:03d}" if member_count > 1 else None
            if member_count > 1:
                next_cluster_num += 1

            for complaint_id in group_ids:
                c = by_id[complaint_id]
                created_at = datetime.fromisoformat(c["created_at"])
                age_hours = (DEMO_NOW - created_at).total_seconds() / 3600.0

                result = priority.compute_priority(
                    severity=c["severity"],
                    cluster_size=member_count,
                    safety_flag=c["safety_flag"],
                    age_hours=age_hours,
                )
                c["cluster_id"] = cluster_id
                c["cluster_member_count"] = member_count
                c["is_recurring"] = is_recurring
                c["priority_score"] = round(result.priority_score, 6)
                c["priority_breakdown"] = {
                    k: round(v, 6) for k, v in result.breakdown.as_dict().items()
                }


def _print_summary(complaints: list[dict]) -> None:
    clusters: dict[str, list[str]] = {}
    for c in complaints:
        if c["cluster_id"]:
            clusters.setdefault(c["cluster_id"], []).append(c["id"])

    print(f"Generated {len(complaints)} demo complaints.")
    print(f"Clusters with 2+ members ({len(clusters)}):")
    for cluster_id, ids in sorted(clusters.items()):
        sample = next(c for c in complaints if c["id"] == ids[0])
        print(
            f"  {cluster_id}: {len(ids)} members "
            f"[{sample['category_slug']} @ {sample['location_building']}] "
            f"recurring={sample['is_recurring']} -> {ids}"
        )

    top5 = sorted(complaints, key=lambda c: c["priority_score"], reverse=True)[:5]
    print("Top 5 by priority_score:")
    for c in top5:
        print(
            f"  {c['id']}  priority={c['priority_score']:.3f}  "
            f"severity={c['severity']} safety={c['safety_flag']} "
            f"category={c['category_slug']} building={c['location_building']}"
        )


async def _generate() -> list[dict]:
    provider = MockProvider()
    complaints = [
        await _build_complaint(i, raw, provider)
        for i, raw in enumerate(RAW_COMPLAINTS, start=1)
    ]
    settings = get_settings()
    _attach_clusters_and_priority(complaints, settings.recurring_threshold)
    return complaints


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "scripts" / "demo_data.json",
        help="Output JSON file path (default: scripts/demo_data.json)",
    )
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument(
        "--pretty", action="store_true", default=True, help="Indented JSON (default)"
    )
    format_group.add_argument(
        "--compact", action="store_true", help="Single-line JSON instead of indented"
    )
    args = parser.parse_args()

    complaints = asyncio.run(_generate())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        if args.compact:
            json.dump(complaints, f, separators=(",", ":"))
        else:
            json.dump(complaints, f, indent=2)
        f.write("\n")

    _print_summary(complaints)
    print(f"\nWrote {len(complaints)} complaints to {args.out}")


if __name__ == "__main__":
    main()
