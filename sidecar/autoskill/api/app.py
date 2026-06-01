from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from autoskill import __version__
from autoskill.core.config import get_settings
from autoskill.core.events import IngestRequest, IngestResult
from autoskill.services.broker import (
    ContextHintRequest,
    ContextHintResponse,
    bootstrap_context_hint,
)


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class StatusResponse(BaseModel):
    mode: str
    database_configured: bool
    runtime_context_broker: dict[str, object]


def create_app() -> FastAPI:
    app = FastAPI(title="SkillKernel AutoSkill Sidecar", version=__version__)

    @app.get("/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, service="autoskill-sidecar", version=__version__)

    @app.get("/v1/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        settings = get_settings()
        return StatusResponse(
            mode=settings.mode.value,
            database_configured=bool(settings.database_url),
            runtime_context_broker={
                "timeout_ms": settings.runtime_context_timeout_ms,
                "max_tokens": settings.max_context_hint_tokens,
            },
        )

    @app.post("/v1/ingest/events", response_model=IngestResult)
    async def ingest_events(request: IngestRequest) -> IngestResult:
        # Phase 1 skeleton: validate, redact, and acknowledge. Durable DB writes land with the
        # repository/migration-backed data layer in the next pass.
        redacted = [event.redacted() for event in request.events]
        return IngestResult(accepted=len(redacted))

    @app.post("/v1/runtime/context-hint", response_model=ContextHintResponse)
    async def context_hint(request: ContextHintRequest) -> ContextHintResponse:
        return bootstrap_context_hint(request)

    @app.get("/v1/skills")
    async def list_skills() -> dict[str, list[object]]:
        return {"skills": []}

    @app.get("/v1/jobs")
    async def list_jobs() -> dict[str, list[object]]:
        return {"jobs": []}

    @app.get("/v1/audit/recent")
    async def recent_audit() -> dict[str, list[object]]:
        return {"audit": []}

    return app

