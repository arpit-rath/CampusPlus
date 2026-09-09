"""Central settings — read once, imported everywhere.

Nothing in this codebase should call os.environ directly outside this file;
route every config value through `Settings` so there's one place that knows
what env vars exist (CLAUDE.md's contract for the AI provider depends on
LLM_PROVIDER being read from here, not scattered os.getenv() calls).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://campuspulse:campuspulse@localhost:5432/campuspulse"

    llm_provider: str = "mock"  # "mock" | "gemini" | "openai" (stub)
    llm_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "gemini-embedding-001"

    cors_origins: str = "http://localhost:3000"
    recurring_threshold: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
