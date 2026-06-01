from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

LLMInvocationStatus = Literal["ok", "error", "timeout", "unsupported"]


@dataclass(frozen=True)
class LLMInvocationRecord:
    llm_invocation_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    trace_id: UUID | None
    span_id: UUID | None
    purpose: str
    profile_key: str
    model_profile_id: UUID | None
    route_kind: str
    provider: str
    model: str
    requested_thinking_level: str | None
    effective_thinking_level: str | None
    thinking_fallback_policy: str
    thinking_downgraded: bool
    prompt_token_estimate: int
    output_token_estimate: int
    status: str
    error: str | None
    audit: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> LLMInvocationRecord:
        return cls(
            llm_invocation_id=row["llm_invocation_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            trace_id=_row_get(row, "trace_id"),
            span_id=_row_get(row, "span_id"),
            purpose=row["purpose"],
            profile_key=row["profile_key"],
            model_profile_id=_row_get(row, "model_profile_id"),
            route_kind=row["route_kind"],
            provider=row["provider"],
            model=row["model"],
            requested_thinking_level=_row_get(row, "requested_thinking_level"),
            effective_thinking_level=_row_get(row, "effective_thinking_level"),
            thinking_fallback_policy=row["thinking_fallback_policy"],
            thinking_downgraded=bool(row["thinking_downgraded"]),
            prompt_token_estimate=int(row["prompt_token_estimate"]),
            output_token_estimate=int(row["output_token_estimate"]),
            status=row["status"],
            error=_row_get(row, "error"),
            audit=_json_dict(row["audit"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "llm_invocation_id": str(self.llm_invocation_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "trace_id": str(self.trace_id) if self.trace_id else None,
            "span_id": str(self.span_id) if self.span_id else None,
            "purpose": self.purpose,
            "profile_key": self.profile_key,
            "model_profile_id": str(self.model_profile_id) if self.model_profile_id else None,
            "route_kind": self.route_kind,
            "provider": self.provider,
            "model": self.model,
            "requested_thinking_level": self.requested_thinking_level,
            "effective_thinking_level": self.effective_thinking_level,
            "thinking_fallback_policy": self.thinking_fallback_policy,
            "thinking_downgraded": self.thinking_downgraded,
            "prompt_token_estimate": self.prompt_token_estimate,
            "output_token_estimate": self.output_token_estimate,
            "status": self.status,
            "error": self.error,
            "audit": self.audit,
            "created_at": self.created_at.isoformat(),
        }


class LLMInvocationStore(Protocol):
    async def record_invocation(
        self,
        *,
        workspace_key: str,
        purpose: str,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        status: LLMInvocationStatus,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        model_profile_id: UUID | None = None,
        requested_thinking_level: str | None = None,
        effective_thinking_level: str | None = None,
        thinking_fallback_policy: str = "omit",
        thinking_downgraded: bool = False,
        prompt_token_estimate: int = 0,
        output_token_estimate: int = 0,
        error: str | None = None,
        audit: dict[str, Any] | None = None,
    ) -> LLMInvocationRecord:
        """Record one content-safe LLM invocation audit row."""


class NullLLMInvocationStore:
    async def record_invocation(
        self,
        *,
        workspace_key: str,
        purpose: str,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        status: LLMInvocationStatus,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        model_profile_id: UUID | None = None,
        requested_thinking_level: str | None = None,
        effective_thinking_level: str | None = None,
        thinking_fallback_policy: str = "omit",
        thinking_downgraded: bool = False,
        prompt_token_estimate: int = 0,
        output_token_estimate: int = 0,
        error: str | None = None,
        audit: dict[str, Any] | None = None,
    ) -> LLMInvocationRecord:
        return LLMInvocationRecord(
            llm_invocation_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            trace_id=trace_id,
            span_id=span_id,
            purpose=purpose,
            profile_key=profile_key,
            model_profile_id=model_profile_id,
            route_kind=route_kind,
            provider=provider,
            model=model,
            requested_thinking_level=requested_thinking_level,
            effective_thinking_level=effective_thinking_level,
            thinking_fallback_policy=thinking_fallback_policy,
            thinking_downgraded=thinking_downgraded,
            prompt_token_estimate=prompt_token_estimate,
            output_token_estimate=output_token_estimate,
            status=status,
            error=error,
            audit=audit or {},
            created_at=datetime.now(UTC),
        )


class AsyncpgLLMInvocationStore(AsyncpgPoolOwner):
    async def record_invocation(
        self,
        *,
        workspace_key: str,
        purpose: str,
        profile_key: str,
        route_kind: str,
        provider: str,
        model: str,
        status: LLMInvocationStatus,
        trace_id: UUID | None = None,
        span_id: UUID | None = None,
        model_profile_id: UUID | None = None,
        requested_thinking_level: str | None = None,
        effective_thinking_level: str | None = None,
        thinking_fallback_policy: str = "omit",
        thinking_downgraded: bool = False,
        prompt_token_estimate: int = 0,
        output_token_estimate: int = 0,
        error: str | None = None,
        audit: dict[str, Any] | None = None,
    ) -> LLMInvocationRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.llm_invocations (
                  llm_invocation_id,
                  workspace_id,
                  trace_id,
                  span_id,
                  purpose,
                  profile_key,
                  model_profile_id,
                  route_kind,
                  provider,
                  model,
                  requested_thinking_level,
                  effective_thinking_level,
                  thinking_fallback_policy,
                  thinking_downgraded,
                  prompt_token_estimate,
                  output_token_estimate,
                  status,
                  error,
                  audit
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9,
                  $10, $11, $12, $13, $14, $15, $16, $17, $18::jsonb
                )
                RETURNING *, $19::text AS workspace_key
                """,
                workspace_id,
                trace_id,
                span_id,
                purpose,
                profile_key,
                model_profile_id,
                route_kind,
                provider,
                model,
                requested_thinking_level,
                effective_thinking_level,
                thinking_fallback_policy,
                thinking_downgraded,
                prompt_token_estimate,
                output_token_estimate,
                status,
                error,
                _json(audit or {}),
                workspace_key,
            )
        return LLMInvocationRecord.from_row(row)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
