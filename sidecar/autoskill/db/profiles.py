from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ExecutorProfileRecord:
    executor_profile_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    profile_key: str
    model_family: str | None
    agent_backend: str | None
    sandbox: str | None
    os_name: str | None
    available_tools: list[str]
    available_binaries: list[str]
    permissions: dict[str, Any]
    api_contracts: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ExecutorProfileRecord:
        return cls(
            executor_profile_id=row["executor_profile_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            profile_key=row["profile_key"],
            model_family=_row_get(row, "model_family"),
            agent_backend=_row_get(row, "agent_backend"),
            sandbox=_row_get(row, "sandbox"),
            os_name=_row_get(row, "os_name"),
            available_tools=list(row["available_tools"]),
            available_binaries=list(row["available_binaries"]),
            permissions=_json_dict(row["permissions"]),
            api_contracts=_json_dict(row["api_contracts"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "executor_profile_id": str(self.executor_profile_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "profile_key": self.profile_key,
            "model_family": self.model_family,
            "agent_backend": self.agent_backend,
            "sandbox": self.sandbox,
            "os_name": self.os_name,
            "available_tools": self.available_tools,
            "available_binaries": self.available_binaries,
            "permissions": self.permissions,
            "api_contracts": self.api_contracts,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class ModelProfileRecord:
    profile_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    profile_key: str
    provider: str
    model: str
    route_kind: str
    endpoint_ref: str | None
    timeout_seconds: float
    thinking_level: str
    thinking_fallback_policy: str
    status: str
    qualification: dict[str, Any]
    kind: Literal["model", "embedding"]
    embedding_dim: int | None
    created_at: datetime
    updated_at: datetime

    def to_json(self) -> dict[str, Any]:
        return {
            "profile_id": str(self.profile_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "profile_key": self.profile_key,
            "provider": self.provider,
            "model": self.model,
            "route_kind": self.route_kind,
            "endpoint_ref": self.endpoint_ref,
            "timeout_seconds": self.timeout_seconds,
            "thinking_level": self.thinking_level,
            "thinking_fallback_policy": self.thinking_fallback_policy,
            "status": self.status,
            "qualification": self.qualification,
            "kind": self.kind,
            "embedding_dim": self.embedding_dim,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_model_row(cls, row: asyncpg.Record | dict[str, Any]) -> ModelProfileRecord:
        return cls(
            profile_id=row["model_profile_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            profile_key=row["profile_key"],
            provider=row["provider"],
            model=row["model"],
            route_kind=row["route_kind"],
            endpoint_ref=_row_get(row, "endpoint_ref"),
            timeout_seconds=float(row["timeout_seconds"]),
            thinking_level=_row_get(row, "thinking_level") or "off",
            thinking_fallback_policy=_row_get(row, "thinking_fallback_policy") or "omit",
            status=row["status"],
            qualification=_json_dict(row["qualification"]),
            kind="model",
            embedding_dim=None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def from_embedding_row(cls, row: asyncpg.Record | dict[str, Any]) -> ModelProfileRecord:
        return cls(
            profile_id=row["embedding_profile_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            profile_key=row["profile_key"],
            provider=row["provider"],
            model=row["model"],
            route_kind=row["route_kind"],
            endpoint_ref=_row_get(row, "endpoint_ref"),
            timeout_seconds=float(row["timeout_seconds"]),
            thinking_level="off",
            thinking_fallback_policy="omit",
            status=row["status"],
            qualification=_json_dict(row["qualification"]),
            kind="embedding",
            embedding_dim=int(row["embedding_dim"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class ProfileStore(Protocol):
    async def upsert_executor_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        model_family: str | None = None,
        agent_backend: str | None = None,
        sandbox: str | None = None,
        os_name: str | None = None,
        available_tools: list[str] | None = None,
        available_binaries: list[str] | None = None,
        permissions: dict[str, Any] | None = None,
        api_contracts: dict[str, Any] | None = None,
        status: str = "active",
    ) -> ExecutorProfileRecord:
        """Create or update an executor compatibility profile."""

    async def list_executor_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExecutorProfileRecord]:
        """List executor profiles."""

    async def upsert_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        provider: str,
        model: str,
        route_kind: str,
        endpoint_ref: str | None = None,
        timeout_seconds: float = 60.0,
        status: str = "candidate",
        qualification: dict[str, Any] | None = None,
        thinking_level: str = "off",
        thinking_fallback_policy: str = "omit",
    ) -> ModelProfileRecord:
        """Create or update the configured text model access profile."""

    async def get_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        """Fetch one text model profile for provider-qualified runtime use."""

    async def list_model_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        """List text model profiles for operator readiness checks."""

    async def upsert_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        provider: str,
        model: str,
        route_kind: str,
        embedding_dim: int,
        endpoint_ref: str | None = None,
        timeout_seconds: float = 30.0,
        status: str = "candidate",
        qualification: dict[str, Any] | None = None,
    ) -> ModelProfileRecord:
        """Create or update the configured embedding access profile."""

    async def get_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        """Fetch one embedding profile for provider-qualified runtime use."""

    async def list_embedding_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        """List embedding profiles for operator readiness checks."""

    async def get_active_embedding_profile(
        self,
        *,
        workspace_key: str,
    ) -> ModelProfileRecord | None:
        """Fetch the active qualified embedding profile for a workspace, if any."""


class NullProfileStore:
    async def upsert_executor_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        model_family: str | None = None,
        agent_backend: str | None = None,
        sandbox: str | None = None,
        os_name: str | None = None,
        available_tools: list[str] | None = None,
        available_binaries: list[str] | None = None,
        permissions: dict[str, Any] | None = None,
        api_contracts: dict[str, Any] | None = None,
        status: str = "active",
    ) -> ExecutorProfileRecord:
        from uuid import uuid4

        now = datetime.now()
        return ExecutorProfileRecord(
            executor_profile_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            profile_key=profile_key,
            model_family=model_family,
            agent_backend=agent_backend,
            sandbox=sandbox,
            os_name=os_name,
            available_tools=available_tools or [],
            available_binaries=available_binaries or [],
            permissions=permissions or {},
            api_contracts=api_contracts or {},
            status=status,
            created_at=now,
            updated_at=now,
        )

    async def list_executor_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExecutorProfileRecord]:
        return []

    async def upsert_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        provider: str,
        model: str,
        route_kind: str,
        endpoint_ref: str | None = None,
        timeout_seconds: float = 60.0,
        status: str = "candidate",
        qualification: dict[str, Any] | None = None,
        thinking_level: str = "off",
        thinking_fallback_policy: str = "omit",
    ) -> ModelProfileRecord:
        from uuid import uuid4

        now = datetime.now()
        return ModelProfileRecord(
            profile_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            profile_key=profile_key,
            provider=provider,
            model=model,
            route_kind=route_kind,
            endpoint_ref=endpoint_ref,
            timeout_seconds=timeout_seconds,
            thinking_level=thinking_level,
            thinking_fallback_policy=thinking_fallback_policy,
            status=status,
            qualification=qualification or {},
            kind="model",
            embedding_dim=None,
            created_at=now,
            updated_at=now,
        )

    async def get_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        return None

    async def list_model_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        return []

    async def upsert_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        provider: str,
        model: str,
        route_kind: str,
        embedding_dim: int,
        endpoint_ref: str | None = None,
        timeout_seconds: float = 30.0,
        status: str = "candidate",
        qualification: dict[str, Any] | None = None,
    ) -> ModelProfileRecord:
        from uuid import uuid4

        now = datetime.now()
        return ModelProfileRecord(
            profile_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            profile_key=profile_key,
            provider=provider,
            model=model,
            route_kind=route_kind,
            endpoint_ref=endpoint_ref,
            timeout_seconds=timeout_seconds,
            thinking_level="off",
            thinking_fallback_policy="omit",
            status=status,
            qualification=qualification or {},
            kind="embedding",
            embedding_dim=embedding_dim,
            created_at=now,
            updated_at=now,
        )

    async def get_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        return None

    async def list_embedding_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        return []

    async def get_active_embedding_profile(
        self,
        *,
        workspace_key: str,
    ) -> ModelProfileRecord | None:
        return None


class AsyncpgProfileStore(AsyncpgPoolOwner):
    async def upsert_executor_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        model_family: str | None = None,
        agent_backend: str | None = None,
        sandbox: str | None = None,
        os_name: str | None = None,
        available_tools: list[str] | None = None,
        available_binaries: list[str] | None = None,
        permissions: dict[str, Any] | None = None,
        api_contracts: dict[str, Any] | None = None,
        status: str = "active",
    ) -> ExecutorProfileRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.executor_profiles (
                  executor_profile_id,
                  workspace_id,
                  profile_key,
                  model_family,
                  agent_backend,
                  sandbox,
                  os_name,
                  available_tools,
                  available_binaries,
                  permissions,
                  api_contracts,
                  status
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11
                )
                ON CONFLICT (workspace_id, profile_key) DO UPDATE
                SET model_family = EXCLUDED.model_family,
                    agent_backend = EXCLUDED.agent_backend,
                    sandbox = EXCLUDED.sandbox,
                    os_name = EXCLUDED.os_name,
                    available_tools = EXCLUDED.available_tools,
                    available_binaries = EXCLUDED.available_binaries,
                    permissions = EXCLUDED.permissions,
                    api_contracts = EXCLUDED.api_contracts,
                    status = EXCLUDED.status,
                    updated_at = now()
                RETURNING *, $12::text AS workspace_key
                """,
                workspace_id,
                profile_key,
                model_family,
                agent_backend,
                sandbox,
                os_name,
                available_tools or [],
                available_binaries or [],
                _json(permissions or {}),
                _json(api_contracts or {}),
                status,
                workspace_key,
            )
        return ExecutorProfileRecord.from_row(row)

    async def list_executor_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExecutorProfileRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT *, $3::text AS workspace_key
                FROM autoskill.executor_profiles
                WHERE workspace_id = $1
                  AND ($2::text IS NULL OR status = $2)
                ORDER BY updated_at DESC
                LIMIT $4
                """,
                workspace_id,
                status,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [ExecutorProfileRecord.from_row(row) for row in rows]

    async def upsert_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        provider: str,
        model: str,
        route_kind: str,
        endpoint_ref: str | None = None,
        timeout_seconds: float = 60.0,
        status: str = "candidate",
        qualification: dict[str, Any] | None = None,
        thinking_level: str = "off",
        thinking_fallback_policy: str = "omit",
    ) -> ModelProfileRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.model_profiles (
                  model_profile_id,
                  workspace_id,
                  profile_key,
                  provider,
                  model,
                  route_kind,
                  endpoint_ref,
                  timeout_seconds,
                  thinking_level,
                  thinking_fallback_policy,
                  status,
                  qualification
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb
                )
                ON CONFLICT (workspace_id, profile_key) DO UPDATE
                SET provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    route_kind = EXCLUDED.route_kind,
                    endpoint_ref = EXCLUDED.endpoint_ref,
                    timeout_seconds = EXCLUDED.timeout_seconds,
                    thinking_level = EXCLUDED.thinking_level,
                    thinking_fallback_policy = EXCLUDED.thinking_fallback_policy,
                    status = EXCLUDED.status,
                    qualification = EXCLUDED.qualification,
                    updated_at = now()
                RETURNING *, $12::text AS workspace_key
                """,
                workspace_id,
                profile_key,
                provider,
                model,
                route_kind,
                endpoint_ref,
                timeout_seconds,
                thinking_level,
                thinking_fallback_policy,
                status,
                _json(qualification or {}),
                workspace_key,
            )
        return ModelProfileRecord.from_model_row(row)

    async def get_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                SELECT *, $3::text AS workspace_key
                FROM autoskill.model_profiles
                WHERE workspace_id = $1
                  AND profile_key = $2
                """,
                workspace_id,
                profile_key,
                workspace_key,
            )
        return ModelProfileRecord.from_model_row(row) if row else None

    async def list_model_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT *, $3::text AS workspace_key
                FROM autoskill.model_profiles
                WHERE workspace_id = $1
                  AND ($2::text IS NULL OR status = $2)
                ORDER BY updated_at DESC
                LIMIT $4
                """,
                workspace_id,
                status,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [ModelProfileRecord.from_model_row(row) for row in rows]

    async def upsert_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
        provider: str,
        model: str,
        route_kind: str,
        embedding_dim: int,
        endpoint_ref: str | None = None,
        timeout_seconds: float = 30.0,
        status: str = "candidate",
        qualification: dict[str, Any] | None = None,
    ) -> ModelProfileRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            if status == "active":
                await conn.execute(
                    """
                    UPDATE autoskill.embedding_profiles
                    SET status = 'qualified',
                        updated_at = now()
                    WHERE workspace_id = $1
                      AND status = 'active'
                    """,
                    workspace_id,
                )
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.embedding_profiles (
                  embedding_profile_id,
                  workspace_id,
                  profile_key,
                  provider,
                  model,
                  route_kind,
                  embedding_dim,
                  endpoint_ref,
                  timeout_seconds,
                  status,
                  qualification
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                ON CONFLICT (workspace_id, profile_key) DO UPDATE
                SET provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    route_kind = EXCLUDED.route_kind,
                    embedding_dim = EXCLUDED.embedding_dim,
                    endpoint_ref = EXCLUDED.endpoint_ref,
                    timeout_seconds = EXCLUDED.timeout_seconds,
                    status = EXCLUDED.status,
                    qualification = EXCLUDED.qualification,
                    updated_at = now()
                RETURNING *, $11::text AS workspace_key
                """,
                workspace_id,
                profile_key,
                provider,
                model,
                route_kind,
                embedding_dim,
                endpoint_ref,
                timeout_seconds,
                status,
                _json(qualification or {}),
                workspace_key,
            )
        return ModelProfileRecord.from_embedding_row(row)

    async def get_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                SELECT *, $3::text AS workspace_key
                FROM autoskill.embedding_profiles
                WHERE workspace_id = $1
                  AND profile_key = $2
                """,
                workspace_id,
                profile_key,
                workspace_key,
            )
        return ModelProfileRecord.from_embedding_row(row) if row else None

    async def list_embedding_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT *, $3::text AS workspace_key
                FROM autoskill.embedding_profiles
                WHERE workspace_id = $1
                  AND ($2::text IS NULL OR status = $2)
                ORDER BY updated_at DESC
                LIMIT $4
                """,
                workspace_id,
                status,
                workspace_key,
                max(1, min(limit, 1000)),
            )
        return [ModelProfileRecord.from_embedding_row(row) for row in rows]

    async def get_active_embedding_profile(
        self,
        *,
        workspace_key: str,
    ) -> ModelProfileRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                SELECT *, $2::text AS workspace_key
                FROM autoskill.embedding_profiles
                WHERE workspace_id = $1
                  AND status = 'active'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                workspace_id,
                workspace_key,
            )
        return ModelProfileRecord.from_embedding_row(row) if row else None


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
