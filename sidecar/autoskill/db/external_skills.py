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
EXTERNAL_SKILL_REVIEW_ACTIONS = {"reuse", "import", "ignore", "quarantine"}
EXTERNAL_SKILL_REVIEW_STATUSES = {"requested", "approved", "rejected", "completed"}


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


@dataclass(frozen=True)
class ExternalSkillReviewActionRecord:
    external_skill_review_action_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    external_skill_id: UUID
    action: str
    status: str
    operator_id: str | None
    rationale: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> ExternalSkillReviewActionRecord:
        return cls(
            external_skill_review_action_id=row["external_skill_review_action_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            external_skill_id=row["external_skill_id"],
            action=row["action"],
            status=row["status"],
            operator_id=_row_get(row, "operator_id"),
            rationale=_row_get(row, "rationale"),
            metadata=_json_dict(_row_get(row, "metadata")),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, object]:
        return {
            "external_skill_review_action_id": str(self.external_skill_review_action_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "external_skill_id": str(self.external_skill_id),
            "action": self.action,
            "status": self.status,
            "operator_id": self.operator_id,
            "rationale": self.rationale,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
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

    async def record_review_action(
        self,
        *,
        workspace_key: str,
        external_skill_id: UUID,
        action: str,
        status: str = "requested",
        operator_id: str | None = None,
        rationale: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalSkillReviewActionRecord:
        """Record an explicit operator decision for external skill reuse/import review."""

    async def list_review_actions(
        self,
        *,
        workspace_key: str,
        external_skill_id: UUID | None = None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillReviewActionRecord]:
        """List operator decisions for guarded external-skill workflows."""


class NullExternalSkillStore:
    def __init__(self) -> None:
        self.review_actions: list[ExternalSkillReviewActionRecord] = []

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

    async def record_review_action(
        self,
        *,
        workspace_key: str,
        external_skill_id: UUID,
        action: str,
        status: str = "requested",
        operator_id: str | None = None,
        rationale: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalSkillReviewActionRecord:
        _validate_review(action=action, status=status)
        from datetime import UTC
        from uuid import uuid4

        now = datetime.now(UTC)
        record = ExternalSkillReviewActionRecord(
            external_skill_review_action_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            external_skill_id=external_skill_id,
            action=action,
            status=status,
            operator_id=operator_id,
            rationale=rationale,
            metadata=metadata or {},
            created_at=now,
        )
        self.review_actions.append(record)
        return record

    async def list_review_actions(
        self,
        *,
        workspace_key: str,
        external_skill_id: UUID | None = None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillReviewActionRecord]:
        return [
            record
            for record in self.review_actions[:limit]
            if record.workspace_key == workspace_key
            and (external_skill_id is None or record.external_skill_id == external_skill_id)
            and (action is None or record.action == action)
            and (status is None or record.status == status)
        ]


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

    async def list_review_actions(
        self,
        *,
        workspace_key: str,
        external_skill_id: UUID | None = None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillReviewActionRecord]:
        if action is not None and action not in EXTERNAL_SKILL_REVIEW_ACTIONS:
            raise ValueError(f"action must be one of {sorted(EXTERNAL_SKILL_REVIEW_ACTIONS)}")
        if status is not None and status not in EXTERNAL_SKILL_REVIEW_STATUSES:
            raise ValueError(f"status must be one of {sorted(EXTERNAL_SKILL_REVIEW_STATUSES)}")
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await ensure_workspace(conn, workspace_key)
            rows = await conn.fetch(
                """
                SELECT a.*, w.external_key AS workspace_key
                FROM autoskill.external_skill_review_actions a
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE w.external_key = $1
                  AND ($2::uuid IS NULL OR a.external_skill_id = $2)
                  AND ($3::text IS NULL OR a.action = $3)
                  AND ($4::text IS NULL OR a.status = $4)
                ORDER BY a.created_at DESC, a.external_skill_review_action_id DESC
                LIMIT $5
                """,
                workspace_key,
                external_skill_id,
                action,
                status,
                max(1, min(limit, 500)),
            )
        return [ExternalSkillReviewActionRecord.from_row(row) for row in rows]

    async def record_review_action(
        self,
        *,
        workspace_key: str,
        external_skill_id: UUID,
        action: str,
        status: str = "requested",
        operator_id: str | None = None,
        rationale: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExternalSkillReviewActionRecord:
        _validate_review(action=action, status=status)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.external_skill_review_actions (
                  external_skill_review_action_id,
                  workspace_id,
                  external_skill_id,
                  action,
                  status,
                  operator_id,
                  rationale,
                  metadata
                )
                SELECT gen_random_uuid(), $1, e.external_skill_id, $3, $4, $5, $6, $7::jsonb
                FROM autoskill.external_skill_inventory e
                WHERE e.workspace_id = $1
                  AND e.external_skill_id = $2
                RETURNING *, $8::text AS workspace_key
                """,
                workspace_id,
                external_skill_id,
                action,
                status,
                operator_id,
                rationale,
                _json(metadata or {}),
                workspace_key,
            )
            if row is None:
                raise ValueError("external skill not found in workspace")
            if status in {"approved", "completed"} and action in {"ignore", "quarantine"}:
                await conn.execute(
                    """
                    UPDATE autoskill.external_skill_inventory
                    SET status = $3,
                        updated_at = now()
                    WHERE workspace_id = $1
                      AND external_skill_id = $2
                    """,
                    workspace_id,
                    external_skill_id,
                    "ignored" if action == "ignore" else "quarantined",
                )
        return ExternalSkillReviewActionRecord.from_row(row)


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


def _validate_review(*, action: str, status: str) -> None:
    if action not in EXTERNAL_SKILL_REVIEW_ACTIONS:
        raise ValueError(f"action must be one of {sorted(EXTERNAL_SKILL_REVIEW_ACTIONS)}")
    if status not in EXTERNAL_SKILL_REVIEW_STATUSES:
        raise ValueError(f"status must be one of {sorted(EXTERNAL_SKILL_REVIEW_STATUSES)}")


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
