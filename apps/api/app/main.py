"""FastAPI entrypoint.

Router registration is intentionally left as a single, easy-to-extend block
below — Track A (db/routers) and Track B (ai/pipeline) both land routers
here; keep additions to that one block so parallel branches don't collide
on unrelated parts of this file.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="CampusPluse API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "llm_provider": settings.llm_provider}


# --- Routers -----------------------------------------------------------
from app.routers import admin, categories, complaints, departments  # noqa: E402

app.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
app.include_router(departments.router, prefix="/departments", tags=["departments"])
app.include_router(categories.router, prefix="/categories", tags=["categories"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
