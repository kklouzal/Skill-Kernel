from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class SkillRecord:
    skill_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    slug: str
    name: str
    source: str
    lifecycle_state: str
    active_version_id: UUID | None
    active_version: int | None
    scanner_status: str | None
    evaluator_status: str | None
    compiled_sha256: str | None
    manifest: dict[str, Any]
    last_canary_status: str | None
    freeze_reason: str | None
    created_at: datetime
    updated_at: datetime
    frozen_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> SkillRecord:
        return cls(
            skill_id=row["skill_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            slug=row["slug"],
            name=row["name"],
            source=row["source"],
            lifecycle_state=row["lifecycle_state"],
            active_version_id=_row_get(row, "active_version_id"),
            active_version=_row_get(row, "active_version"),
            scanner_status=_row_get(row, "scanner_status"),
            evaluator_status=_row_get(row, "evaluator_status"),
            compiled_sha256=_row_get(row, "compiled_sha256"),
            manifest=_json_dict(_row_get(row, "manifest")),
            last_canary_status=_row_get(row, "last_canary_status"),
            freeze_reason=_row_get(row, "freeze_reason"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            frozen_at=_row_get(row, "frozen_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_id": str(self.skill_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "slug": self.slug,
            "name": self.name,
            "source": self.source,
            "lifecycle_state": self.lifecycle_state,
            "active_version_id": str(self.active_version_id) if self.active_version_id else None,
            "active_version": self.active_version,
            "scanner_status": self.scanner_status,
            "evaluator_status": self.evaluator_status,
            "compiled_sha256": self.compiled_sha256,
            "manifest": self.manifest,
            "last_canary_status": self.last_canary_status,
            "freeze_reason": self.freeze_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
        }


class SkillStore(Protocol):
    async def list_skills(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
    ) -> list[SkillRecord]:
        """List skills with their active version metadata."""


class NullSkillStore:
    async def list_skills(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
    ) -> list[SkillRecord]:
        return []


class AsyncpgSkillStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def list_skills(
        self,
        *,
        workspace_key: str | None = None,
        lifecycle_state: str | None = None,
        limit: int = 100,
    ) -> list[SkillRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if workspace_key is not None:
                await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT
                  s.*,
                  w.external_key AS workspace_key,
                  sv.version AS active_version,
                  sv.scanner_status,
                  sv.evaluator_status,
                  sv.compiled_sha256,
                  sv.manifest
                FROM autoskill.skills s
                JOIN autoskill.workspaces w USING (workspace_id)
                LEFT JOIN autoskill.skill_versions sv
                  ON sv.skill_version_id = s.active_version_id
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::text IS NULL OR s.lifecycle_state = $2)
                ORDER BY s.updated_at DESC, s.slug ASC
                LIMIT $3
                """,
                workspace_key,
                lifecycle_state,
                max(1, min(limit, 500)),
            )
            return [SkillRecord.from_row(row) for row in rows]


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
