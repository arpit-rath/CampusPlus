"""Central settings — read once, imported everywhere.

Nothing in this codebase should call os.environ directly outside this file;
route every config value through `Settings` so there's one place that knows
what env vars exist (CLAUDE.md's contract for the AI provider depends on
LLM_PROVIDER being read from here, not scattered os.getenv() calls).

The similarity thresholds, the priority formula's constants and the
recurring threshold all live here too, rather than as magic numbers spread
across `app/pipeline/*` — the pipeline modules keep them as *default
argument values* so they stay pure and unit-testable, and callers that
actually run in the app pass the configured values in.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/ — used to anchor relative paths (uploads dir) regardless of
# what directory uvicorn was launched from.
API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://campusplus:campusplus@localhost:5432/campusplus"

    # --- AI provider ---------------------------------------------------
    llm_provider: str = "mock"  # "mock" | "gemini" (openai/claude stubbed)
    llm_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    # Hard ceiling on any single provider call. A demo that hangs is worse
    # than a demo that quietly falls back to the mock provider.
    llm_timeout_seconds: float = 20.0
    # When true (the default), a `gemini` provider that errors or times out
    # transparently falls back to MockProvider instead of 500-ing the
    # request — CLAUDE.md's "automatic fallback, not just a dev toggle".
    llm_fallback_to_mock: bool = True

    # --- Similarity / clustering (CLAUDE.md thresholds) -----------------
    duplicate_threshold: float = 0.92
    suggested_merge_threshold: float = 0.75
    similarity_window_days: int = 14
    # How many nearest neighbours to pull back from pgvector per lookup.
    similarity_candidate_limit: int = 20
    # Independent students in one cluster before it is flagged recurring.
    recurring_threshold: int = 3

    # --- Priority formula ----------------------------------------------
    cluster_cap: int = 20
    sla_saturation_hours: float = 72.0

    # --- Uploads ---------------------------------------------------------
    upload_dir: Path = API_ROOT / "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 MB
    # Absolute base URL the API is reachable at, used to build photo URLs.
    public_base_url: str = "http://localhost:8000"

    # --- Access control ---------------------------------------------------
    # When set, every /admin route and every mutating admin action on
    # /complaints requires `X-Admin-Token: <this value>`. Left empty the
    # API runs wide open, which is fine for a laptop demo but is reported
    # as `admin_auth: "disabled"` on /health so it's never a silent gap.
    admin_token: str = ""

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
