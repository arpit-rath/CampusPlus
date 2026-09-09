"""FastAPI entrypoint: middleware, static uploads, routers, realtime socket."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.deps import admin_auth_enabled
from app.realtime import broadcaster
from app.routers import admin, categories, clusters, complaints, departments

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="CampusPluse API",
    version="1.0.0",
    description=(
        "AI-powered campus problem intelligence. Every database write and "
        "every model call happens here; the web app never talks to Postgres "
        "or a model provider directly."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    # Explicit rather than "*": the admin token travels in a custom header,
    # and listing it is what makes the browser send it cross-origin.
    allow_headers=["Content-Type", "X-Admin-Token"],
)

# Complaint photos. Created eagerly so mounting never fails on a fresh clone.
settings.upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Liveness plus an honest account of how the system is configured.

    `llm_effective` is the one worth reading before a demo: it says whether
    complaints are actually going to Gemini or quietly to the mock provider,
    which is not something anyone should have to infer from the output.
    """
    from app.ai.provider import describe_provider

    provider = describe_provider()
    return {
        "status": "ok",
        "llm_provider": provider["llm_provider"],
        "llm_effective": provider["effective"],
        "llm_fallback_to_mock": provider["fallback_to_mock"],
        "admin_auth": "enabled" if admin_auth_enabled() else "disabled",
        "realtime_subscribers": broadcaster.subscriber_count,
        "thresholds": {
            "duplicate": settings.duplicate_threshold,
            "suggested_merge": settings.suggested_merge_threshold,
            "recurring_students": settings.recurring_threshold,
            "window_days": settings.similarity_window_days,
        },
    }


@app.websocket("/ws/complaints")
async def complaints_socket(websocket: WebSocket) -> None:
    """Live feed of complaint and cluster changes.

    The dashboard subscribes here instead of polling, so the "third student
    reports it and the card goes recurring" moment is genuinely live rather
    than up-to-four-seconds-late. Messages are
    `{"type": "<event>", "data": {...}}`; see `app/realtime.py` for the
    event vocabulary.
    """
    await websocket.accept()
    queue = broadcaster.subscribe()
    try:
        await websocket.send_json({"type": "connected", "data": {"ok": True}})
        while True:
            message = await queue.get()
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — a broken socket must not
        # propagate into the server's task group and take other clients down.
        logger.info("realtime socket closed: %s", exc)
    finally:
        broadcaster.unsubscribe(queue)


# --- Routers -----------------------------------------------------------
app.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
app.include_router(clusters.router, prefix="/clusters", tags=["clusters"])
app.include_router(departments.router, prefix="/departments", tags=["departments"])
app.include_router(categories.router, prefix="/categories", tags=["categories"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
