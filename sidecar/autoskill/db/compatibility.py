from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class SkillProfileCompatibilityRecord:
    skill_profile_compatibility_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_version_id: UUID
    executor_profile_id: UUID
    status: str
    evidence: dict[str, Any]
    last_checked_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> SkillProfileCompatibilityRecord:
        return cls(
            skill_profile_compatibility_id=row["skill_profile_compatibility_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_version_id=row["skill_version_id"],
            executor_profile_id=row["executor_profile_id"],
            status=row["status"],
            evidence=_json_dict(row["evidence"]),
            last_checked_at=row["last_checked_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_profile_compatibility_id": str(
                self.skill_profile_compatibility_id
            ),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_version_id": str(self.skill_version_id),
            "executor_profile_id": str(self.executor_profile_id),
            "status": self.status,
            "evidence": self.evidence,
            "last_checked_at": self.last_checked_at.isoformat(),
        }


class CompatibilityStore(Protocol):
    async def upsert_compatibility(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID,
        status: str,
        evidence: dict[str, Any] | None = None,
    ) -> SkillProfileCompatibilityRecord:
        """Record the latest skill-version compatibility for one executor profile."""

    async def list_statuses(
        self,
        *,
        workspace_key: str,
        executor_profile_id: UUID,
        skill_version_ids: list[UUID],
    ) -> dict[UUID, str]:
        """Return compatibility statuses keyed by skill version."""


class NullCompatibilityStore:
    def __init__(self) -> None:
        self.records: dict[tuple[UUID, UUID], SkillProfileCompatibilityRecord] = {}

    async def upsert_compatibility(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID,
        status: str,
        evidence: dict[str, Any] | None = None,
    ) -> SkillProfileCompatibilityRecord:
        record = SkillProfileCompatibilityRecord(
            skill_profile_compatibility_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            status=status,
            evidence=evidence or {},
            last_checked_at=datetime.now(),
        )
        self.records[(skill_version_id, executor_profile_id)] = record
        return record

    async def list_statuses(
        self,
        *,
        workspace_key: str,
        executor_profile_id: UUID,
        skill_version_ids: list[UUID],
    ) -> dict[UUID, str]:
        return {
            skill_version_id: record.status
            for skill_version_id in skill_version_ids
            if (
                record := self.records.get((skill_version_id, executor_profile_id))
            )
            is not None
        }


class AsyncpgCompatibilityStore(AsyncpgPoolOwner):
    async def upsert_compatibility(
        self,
        *,
        workspace_key: str,
        skill_version_id: UUID,
        executor_profile_id: UUID,
        status: str,
        evidence: dict[str, Any] | None = None,
    ) -> SkillProfileCompatibilityRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.skill_profile_compatibility (
                  skill_profile_compatibility_id,
                  workspace_id,
                  skill_version_id,
                  executor_profile_id,
                  status,
                  evidence
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (workspace_id, skill_version_id, executor_profile_id)
                DO UPDATE SET
                  status = EXCLUDED.status,
                  evidence = EXCLUDED.evidence,
                  last_checked_at = now()
                RETURNING *, $6::text AS workspace_key
                """,
                workspace_id,
                skill_version_id,
                executor_profile_id,
                status,
                _json(evidence or {}),
                workspace_key,
            )
        return SkillProfileCompatibilityRecord.from_row(row)

    async def list_statuses(
        self,
        *,
        workspace_key: str,
        executor_profile_id: UUID,
        skill_version_ids: list[UUID],
    ) -> dict[UUID, str]:
        if not skill_version_ids:
            return {}
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            workspace_id = await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT skill_version_id, status
                FROM autoskill.skill_profile_compatibility
                WHERE workspace_id = $1
                  AND executor_profile_id = $2
                  AND skill_version_id = ANY($3::uuid[])
                """,
                workspace_id,
                executor_profile_id,
                skill_version_ids,
            )
        return {row["skill_version_id"]: row["status"] for row in rows}


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
