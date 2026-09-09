"""Synthetic complaint generator behind the demo "chaos button".

Spectacle feature (implementation plan phase 12.6), built the way the plan
asks for spectacle to be built: it **reuses the pipeline rather than bolting
onto it**. Every complaint it produces goes through the same
`ingest_complaint` as a real student submission — same understanding, same
embedding, same pgvector search, same clustering and priority. There is no
shortcut that writes rows directly, which is the whole point: if the chaos
button makes the dashboard light up, that is the real system working, not an
animation.

The generated text is deliberately templated from the same near-duplicate
phrasings the seed data uses, because random word salad would not cluster and
a chaos button that produces no merges demonstrates nothing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# (category-shaped phrasing, building, room) triples. Each scenario carries
# several paraphrases of *one* underlying problem, so firing a burst produces
# real clusters rather than unrelated noise.
@dataclass(frozen=True)
class Scenario:
    building: str
    room: str | None
    variants: tuple[str, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "Hostel Block C",
        "3rd floor",
        (
            "Water is leaking from the ceiling in the Hostel Block C third floor corridor.",
            "Water is leaking from the ceiling in the Hostel Block C third floor corridor again.",
            "Water is leaking from the ceiling in the Hostel Block C third floor corridor, it is getting worse.",
            "Water is still leaking from the ceiling in the Hostel Block C third floor corridor.",
        ),
    ),
    Scenario(
        "Main Library",
        "reading room",
        (
            "Wifi is completely down in the Main Library reading room, nobody can connect to the network.",
            "Wifi is completely down in the Main Library, nobody around me can connect to the network at all.",
            "Wifi is completely down in the Main Library reading room again, cannot connect to the network.",
        ),
    ),
    Scenario(
        "Academic Block B",
        "stairwell",
        (
            "There is exposed sparking wiring in the Academic Block B stairwell, it looks dangerous.",
            "Exposed sparking wiring in the Academic Block B stairwell again, it really looks dangerous.",
            "The wiring in the Academic Block B stairwell is exposed and sparking, very dangerous.",
        ),
    ),
    Scenario(
        "Cafeteria",
        None,
        (
            "Garbage bins outside the Cafeteria are overflowing and trash is spilling onto the walkway.",
            "Garbage bins outside the Cafeteria are overflowing again, trash is spilling onto the walkway.",
            "Garbage bins outside the Cafeteria are still overflowing, trash is spilling onto the walkway.",
        ),
    ),
    Scenario(
        "Sports Complex",
        "changing rooms",
        (
            "The lights in the Sports Complex changing rooms are completely out, nobody can see.",
            "The lights in the Sports Complex changing rooms are completely out again, nobody can see.",
            "The lights in the Sports Complex changing rooms are still completely out, nobody can see.",
        ),
    ),
)


@dataclass(frozen=True)
class SyntheticComplaint:
    description: str
    location_building: str
    location_room: str | None
    student_id: str


def generate(count: int, *, seed: int | None = None) -> list[SyntheticComplaint]:
    """Produce `count` synthetic complaints that will genuinely cluster.

    Each one gets a distinct `student_id`, so a burst can legitimately push a
    cluster past the recurring threshold — using one id would (correctly)
    refuse to mark anything recurring and the demo would fall flat for the
    right reason.
    """
    rng = random.Random(seed)
    out: list[SyntheticComplaint] = []
    scenarios = list(SCENARIOS)
    rng.shuffle(scenarios)

    index = 0
    while len(out) < count:
        scenario = scenarios[index % len(scenarios)]
        variant = scenario.variants[(index // len(scenarios)) % len(scenario.variants)]
        out.append(
            SyntheticComplaint(
                description=variant,
                location_building=scenario.building,
                location_room=scenario.room,
                # Random suffix so repeated presses never collide on an id and
                # accidentally look like one student spamming.
                student_id=f"chaos_{rng.randrange(16**6):06x}",
            )
        )
        index += 1
    return out
