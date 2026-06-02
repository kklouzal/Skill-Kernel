import os
from functools import lru_cache
from pathlib import Path

from autoskill.core.enums import AutonomyMode
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Sidecar settings.

    Environment variables use the AUTOSKILL_ prefix. The defaults intentionally
    match the v9 handoff's local-first development posture.
    """

    model_config = SettingsConfigDict(env_prefix="AUTOSKILL_", env_file=".env", extra="ignore")

    mode: AutonomyMode = AutonomyMode.AUTONOMOUS_GUARDED
    host: str = "127.0.0.1"
    port: int = 8765
    database_url: str | None = Field(default=None, alias="AUTOSKILL_DATABASE_URL")
    schema_name: str = "autoskill"
    statement_timeout_ms: int = 30_000
    ingest_token: str | None = None
    control_token: str | None = None
    active_root: Path = Path("skills/autoskill")
    archive_root: Path = Path(".autoskill/archive")
    staging_root: Path = Path(".autoskill/staging")
    runtime_context_broker_enabled: bool = False
    runtime_context_timeout_ms: int = 150
    max_context_hint_tokens: int = 800
    llm_api_base_url: str | None = None
    llm_api_key: str | None = None
    embedding_provider: str = "hash"
    embedding_model: str = "autoskill-hash-embedding.v1"
    embedding_dim: int = 1536
    embedding_api_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_timeout_seconds: float = 30.0
    worker_scheduler_concurrency: int = 1
    worker_maintenance_concurrency: int = 2
    worker_mutation_concurrency: int = 1
    allow_support_scripts: bool = True
    allow_network_in_generated_skills: bool = False
    allow_shell_in_generated_skills: bool = False
    forbid_hidden_markdown: bool = True
    redact_before_store: bool = True
    redact_before_embed: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    if os.environ.get("AUTOSKILL_IGNORE_ENV_FILE"):
        return Settings(_env_file=None)
    return Settings()
