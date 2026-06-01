from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

EXTERNAL_SKILL_STATUSES = {"visible", "missing", "changed", "ignored", "quarantined"}


@dataclass(frozen=True)
class ExternalSkillInput:
    source: str
    root_path_hash: str
    slug: str
    file_hash: str
    name: str | None = None
    description: str | None = None
    frontmatter: dict[str, Any] | None = None
    status: str = "visible"
    risk_summary: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExternalSkillRecord:
    external_skill_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source: str
    root_path_hash: str
    slug: str
    name: str | None
    description: str | None
    frontmatter: dict[str, Any]
    file_hash: str
    status: str
    risk_summary: dict[str, Any]
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ExternalSkillRecord:
        return cls(
            external_skill_id=row["external_skill_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source=row["source"],
            root_path_hash=row["root_path_hash"],
            slug=row["slug"],
            name=_row_get(row, "name"),
            description=_row_get(row, "description"),
            frontmatter=_json_dict(_row_get(row, "frontmatter")),
            file_hash=row["file_hash"],
            status=row["status"],
            risk_summary=_json_dict(_row_get(row, "risk_summary")),
            last_seen_at=row["last_seen_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "external_skill_id": str(self.external_skill_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source": self.source,
            "root_path_hash": self.root_path_hash,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "frontmatter": self.frontmatter,
            "file_hash": self.file_hash,
            "status": self.status,
            "risk_summary": self.risk_summary,
            "last_seen_at": self.last_seen_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class ExternalSkillUpsertResult:
    created: int
    updated: int
    skills: list[ExternalSkillRecord]

    def to_json(self) -> dict[str, object]:
        return {
            "created": self.created,
            "updated": self.updated,
            "skills": [skill.to_json() for skill in self.skills],
        }


class ExternalSkillStore(Protocol):
    async def upsert_external_skills(
        self,
        *,
        workspace_key: str,
        skills: list[ExternalSkillInput],
    ) -> ExternalSkillUpsertResult:
        """Record read-only external skill inventory for collision analysis."""

    async def list_external_skills(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillRecord]:
        """List external skill inventory records."""


class NullExternalSkillStore:
    async def upsert_external_skills(
        self,
        *,
        workspace_key: str,
        skills: list[ExternalSkillInput],
    ) -> ExternalSkillUpsertResult:
        return ExternalSkillUpsertResult(created=0, updated=0, skills=[])

    async def list_external_skills(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillRecord]:
        return []


class AsyncpgExternalSkillStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def upsert_external_skills(
        self,
        *,
        workspace_key: str,
        skills: list[ExternalSkillInput],
    ) -> ExternalSkillUpsertResult:
        _validate_inputs(skills)
        pool = await self._get_pool()
        records: list[ExternalSkillRecord] = []
        created = 0
        updated = 0
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            for skill in skills:
                row = await conn.fetchrow(
                    """
                    WITH upserted AS (
                      INSERT INTO autoskill.external_skill_inventory (
                        external_skill_id,
                        workspace_id,
                        source,
                        root_path_hash,
                        slug,
                        name,
                        description,
                        frontmatter,
                        file_hash,
                        status,
                        risk_summary,
                        last_seen_at
                      )
                      VALUES (
                        gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9,
                        $10::jsonb, now()
                      )
                      ON CONFLICT (workspace_id, source, root_path_hash, slug) DO UPDATE
                      SET name = EXCLUDED.name,
                          description = EXCLUDED.description,
                          frontmatter = EXCLUDED.frontmatter,
                          file_hash = EXCLUDED.file_hash,
                          status = EXCLUDED.status,
                          risk_summary = EXCLUDED.risk_summary,
                          last_seen_at = now(),
                          updated_at = now()
                      RETURNING *, (xmax = 0) AS inserted
                    )
                    SELECT upserted.*, w.external_key AS workspace_key
                    FROM upserted
                    JOIN autoskill.workspaces w USING (workspace_id)
                    """,
                    workspace_id,
                    skill.source,
                    skill.root_path_hash,
                    skill.slug,
                    skill.name,
                    skill.description,
                    _json(skill.frontmatter or {}),
                    skill.file_hash,
                    skill.status,
                    _json(skill.risk_summary or {}),
                )
                if row["inserted"]:
                    created += 1
                else:
                    updated += 1
                records.append(ExternalSkillRecord.from_row(row))

        return ExternalSkillUpsertResult(created=created, updated=updated, skills=records)

    async def list_external_skills(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillRecord]:
        if status is not None and status not in EXTERNAL_SKILL_STATUSES:
            raise ValueError(f"status must be one of {sorted(EXTERNAL_SKILL_STATUSES)}")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if workspace_key is not None:
                await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT e.*, w.external_key AS workspace_key
                FROM autoskill.external_skill_inventory e
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::text IS NULL OR e.status = $2)
                ORDER BY e.last_seen_at DESC, e.slug ASC
                LIMIT $3
                """,
                workspace_key,
                status,
                max(1, min(limit, 500)),
            )
        return [ExternalSkillRecord.from_row(row) for row in rows]


def _validate_inputs(skills: list[ExternalSkillInput]) -> None:
    for skill in skills:
        if skill.status not in EXTERNAL_SKILL_STATUSES:
            raise ValueError(f"status must be one of {sorted(EXTERNAL_SKILL_STATUSES)}")
        if not skill.source.strip():
            raise ValueError("source is required")
        if not skill.root_path_hash.strip():
            raise ValueError("root_path_hash is required")
        if not skill.slug.strip():
            raise ValueError("slug is required")
        if not skill.file_hash.strip():
            raise ValueError("file_hash is required")


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
