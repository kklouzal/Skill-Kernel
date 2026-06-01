from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Annotated

from autoskill import __version__
from autoskill.core.config import get_settings
from autoskill.core.events import IngestRequest, IngestResult
from autoskill.db.events import AsyncpgEventStore, EventStore, NullEventStore
from autoskill.services.broker import (
    ContextHintRequest,
    ContextHintResponse,
    bootstrap_context_hint,
)
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    service: str
    version: str


class StatusResponse(BaseModel):
    mode: str
    database_configured: bool
    ingest_auth_configured: bool
    runtime_context_broker: dict[str, object]


def _build_event_store() -> EventStore:
    settings = get_settings()
    if settings.database_url:
        return AsyncpgEventStore(
            settings.database_url,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    return NullEventStore()


def _require_ingest_auth(authorization: str | None) -> None:
    settings = get_settings()
    if not settings.ingest_token:
        return

    expected = f"Bearer {settings.ingest_token}"
    if authorization is None or not compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid ingest authorization",
        )


def create_app(event_store: EventStore | None = None) -> FastAPI:
    store = event_store or _build_event_store()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            close = getattr(store, "close", None)
            if close is not None:
                await close()

    app = FastAPI(
        title="SkillKernel AutoSkill Sidecar",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/v1/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(ok=True, service="autoskill-sidecar", version=__version__)

    @app.get("/v1/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        settings = get_settings()
        return StatusResponse(
            mode=settings.mode.value,
            database_configured=bool(settings.database_url),
            ingest_auth_configured=bool(settings.ingest_token),
            runtime_context_broker={
                "timeout_ms": settings.runtime_context_timeout_ms,
                "max_tokens": settings.max_context_hint_tokens,
            },
        )

    @app.post("/v1/ingest/events", response_model=IngestResult)
    async def ingest_events(
        request: IngestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> IngestResult:
        _require_ingest_auth(authorization)
        redacted = [event.redacted() for event in request.events]
        summary = await store.ingest_events(redacted)
        return IngestResult(
            accepted=summary.accepted,
            duplicate=summary.duplicate,
            rejected=summary.rejected,
        )

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
