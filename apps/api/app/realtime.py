"""In-process pub/sub behind the `/ws/complaints` websocket.

CLAUDE.md's realtime section allows two shapes: Supabase Realtime when the
database is hosted there, or "a plain `/ws/complaints` fallback so the
frontend isn't hard-coupled to one provider". This is that fallback, and on
a laptop-hosted Postgres it is the only one available — Supabase Realtime
needs Supabase.

The design is deliberately the smallest thing that removes polling: the
FastAPI process already owns every database write (that is the whole point
of the "API owns all writes" rule), so it can publish an event at the same
moment it commits, with no change-feed listener in between. Every connected
dashboard gets the event within a tick.

The one thing this cannot do is notice a write made by something other than
this process — a psql session, a second API replica. For a single-process
hackathon deployment that is not a real limitation, and the frontend still
refetches on reconnect, so a missed event self-heals rather than leaving the
dashboard permanently stale.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

logger = logging.getLogger(__name__)

EventType = Literal[
    "complaint.created",
    "complaint.updated",
    "cluster.updated",
    "cluster.recurring",
]

# Bounded so one wedged browser tab can never grow memory without limit;
# a subscriber that falls this far behind is dropped and reconnects.
_QUEUE_MAXSIZE = 100


class Broadcaster:
    """Fan-out of JSON events to every connected websocket."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Queue an event for every subscriber. Never blocks, never raises.

        Called from request handlers right after a commit, so it must not be
        able to fail the request that triggered it — a dashboard that missed
        an update is a far smaller problem than a complaint that failed to
        save because a websocket was slow.
        """
        if not self._subscribers:
            return

        message = json.dumps({"type": event_type, "data": payload}, default=str)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("dropping realtime subscriber: queue full")
                self._subscribers.discard(queue)


broadcaster = Broadcaster()
