from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.db.governance import GovernanceStore, RevocationRequestRecord
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class SkillLifecycleRecord:
    skill_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    slug: str
    lifecycle_state: str
    active_version_id: UUID | None
    last_canary_status: str | None
    freeze_reason: str | None
    frozen_at: datetime | None
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> SkillLifecycleRecord:
        return cls(
            skill_id=row["skill_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            slug=row["slug"],
            lifecycle_state=row["lifecycle_state"],
            active_version_id=_row_get(row, "active_version_id"),
            last_canary_status=_row_get(row, "last_canary_status"),
            freeze_reason=_row_get(row, "freeze_reason"),
            frozen_at=_row_get(row, "frozen_at"),
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_id": str(self.skill_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "slug": self.slug,
            "lifecycle_state": self.lifecycle_state,
            "active_version_id": str(self.active_version_id) if self.active_version_id else None,
            "last_canary_status": self.last_canary_status,
            "freeze_reason": self.freeze_reason,
            "frozen_at": _iso_or_none(self.frozen_at),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class CanaryResultRecord:
    canary_result_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_id: UUID
    skill_version_id: UUID | None
    evolution_transaction_id: UUID | None
    status: str
    critical: bool
    reason: str | None
    metrics: dict[str, Any]
    observed_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> CanaryResultRecord:
        return cls(
            canary_result_id=row["canary_result_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_id=row["skill_id"],
            skill_version_id=_row_get(row, "skill_version_id"),
            evolution_transaction_id=_row_get(row, "evolution_transaction_id"),
            status=row["status"],
            critical=row["critical"],
            reason=_row_get(row, "reason"),
            metrics=_json_dict(row["metrics"]),
            observed_at=row["observed_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "canary_result_id": str(self.canary_result_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id),
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "evolution_transaction_id": (
                str(self.evolution_transaction_id) if self.evolution_transaction_id else None
            ),
            "status": self.status,
            "critical": self.critical,
            "reason": self.reason,
            "metrics": self.metrics,
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True)
class CanaryRecordResult:
    canary: CanaryResultRecord
    skill: SkillLifecycleRecord | None
    revocation: RevocationRequestRecord | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "canary": self.canary.to_json(),
            "skill": self.skill.to_json() if self.skill else None,
            "revocation": self.revocation.to_json() if self.revocation else None,
        }


class LifecycleStore(Protocol):
    async def freeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        reason: str,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        """Freeze one skill and optionally record the freeze in an evolution transaction."""

    async def unfreeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        target_state: str = "candidate",
        reason: str | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        """Move one frozen skill back to an explicit non-frozen lifecycle state."""

    async def record_canary_result(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        status: str,
        critical: bool = False,
        reason: str | None = None,
        metrics: dict[str, Any] | None = None,
        skill_version_id: UUID | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> CanaryRecordResult:
        """Record a canary observation and freeze on critical failure."""

    async def get_canary_result(
        self,
        *,
        workspace_key: str | None = None,
        canary_result_id: UUID,
    ) -> CanaryResultRecord | None:
        """Fetch one canary result for content-safe operator drill-down."""

    async def list_canary_results(
        self,
        *,
        workspace_key: str | None = None,
        skill_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CanaryResultRecord]:
        """List recent canary results for Observatory lifecycle diagnostics."""


class NullLifecycleStore:
    async def freeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        reason: str,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        return _null_skill(
            workspace_key=workspace_key,
            skill_id=skill_id,
            lifecycle_state="frozen",
            last_canary_status="critical",
            freeze_reason=reason,
        )

    async def unfreeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        target_state: str = "candidate",
        reason: str | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        return _null_skill(
            workspace_key=workspace_key,
            skill_id=skill_id,
            lifecycle_state=target_state,
            last_canary_status=None,
            freeze_reason=None,
        )

    async def record_canary_result(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        status: str,
        critical: bool = False,
        reason: str | None = None,
        metrics: dict[str, Any] | None = None,
        skill_version_id: UUID | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> CanaryRecordResult:
        now = datetime.now(UTC)
        canary = CanaryResultRecord(
            canary_result_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            evolution_transaction_id=evolution_transaction_id,
            status=status,
            critical=critical,
            reason=reason,
            metrics=metrics or {},
            observed_at=now,
        )
        skill = None
        if critical:
            skill = _null_skill(
                workspace_key=workspace_key,
                skill_id=skill_id,
                lifecycle_state="frozen",
                last_canary_status=status,
                freeze_reason=reason,
            )
        return CanaryRecordResult(canary=canary, skill=skill)

    async def get_canary_result(
        self,
        *,
        workspace_key: str | None = None,
        canary_result_id: UUID,
    ) -> CanaryResultRecord | None:
        return None

    async def list_canary_results(
        self,
        *,
        workspace_key: str | None = None,
        skill_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CanaryResultRecord]:
        return []


class AsyncpgLifecycleStore(AsyncpgPoolOwner):
    def __init__(
        self,
        database_url: str,
        *,
        governance: GovernanceStore | None = None,
        statement_timeout_ms: int = 30_000,
    ) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)
        self._governance = governance

    async def freeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        reason: str,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await _set_skill_lifecycle(
                conn,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
                skill_id=skill_id,
                lifecycle_state="frozen",
                last_canary_status="critical",
                freeze_reason=reason,
            )
        if row is not None and evolution_transaction_id is not None and self._governance:
            await self._governance.record_transaction_item(
                evolution_transaction_id=evolution_transaction_id,
                item_kind="skill_lifecycle",
                item_id=skill_id,
                activation_state="frozen",
                rollback_action={
                    "kind": "restore_lifecycle",
                    "target_state": "candidate",
                },
            )
        return row

    async def unfreeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        target_state: str = "candidate",
        reason: str | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        if target_state == "frozen":
            raise ValueError("target_state must not be frozen")
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await _set_skill_lifecycle(
                conn,
                workspace_id=workspace_id,
                workspace_key=workspace_key,
                skill_id=skill_id,
                lifecycle_state=target_state,
                last_canary_status=None,
                freeze_reason=None,
            )
        if row is not None and evolution_transaction_id is not None and self._governance:
            await self._governance.record_transaction_item(
                evolution_transaction_id=evolution_transaction_id,
                item_kind="skill_lifecycle",
                item_id=skill_id,
                activation_state=target_state,
                rollback_action={
                    "kind": "restore_lifecycle",
                    "target_state": "frozen",
                    "reason": reason,
                },
            )
        return row

    async def record_canary_result(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        status: str,
        critical: bool = False,
        reason: str | None = None,
        metrics: dict[str, Any] | None = None,
        skill_version_id: UUID | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> CanaryRecordResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            canary_row = await conn.fetchrow(
                """
                INSERT INTO autoskill.canary_results (
                  canary_result_id,
                  workspace_id,
                  skill_id,
                  skill_version_id,
                  evolution_transaction_id,
                  status,
                  critical,
                  reason,
                  metrics
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                RETURNING *, $9::text AS workspace_key
                """,
                workspace_id,
                skill_id,
                skill_version_id,
                evolution_transaction_id,
                status,
                critical,
                reason,
                _json(metrics or {}),
                workspace_key,
            )
            canary = CanaryResultRecord.from_row(canary_row)
            skill = None
            if critical:
                skill = await _set_skill_lifecycle(
                    conn,
                    workspace_id=workspace_id,
                    workspace_key=workspace_key,
                    skill_id=skill_id,
                    lifecycle_state="frozen",
                    last_canary_status=status,
                    freeze_reason=reason or "critical canary failure",
                )
            else:
                skill = await _update_last_canary_status(
                    conn,
                    workspace_id=workspace_id,
                    workspace_key=workspace_key,
                    skill_id=skill_id,
                    status=status,
                )
        revocation = None
        if skill is not None and evolution_transaction_id is not None and self._governance:
            activation_state = "frozen" if critical else skill.lifecycle_state
            await self._governance.record_transaction_item(
                evolution_transaction_id=evolution_transaction_id,
                item_kind="canary_result",
                item_id=canary.canary_result_id,
                activation_state=activation_state,
                rollback_action={
                    "kind": "restore_lifecycle",
                    "skill_id": str(skill_id),
                    "status": status,
                    "critical": critical,
                },
            )
            if critical:
                revocation = await self._governance.request_revocation(
                    workspace_key=workspace_key,
                    request_kind="rollback",
                    root_object_type="evolution_transaction",
                    root_object_id=evolution_transaction_id,
                    traversal_summary={
                        "source": "critical_canary",
                        "canary_result_id": str(canary.canary_result_id),
                        "skill_id": str(skill_id),
                        "reason": reason or "critical canary failure",
                    },
                )
        return CanaryRecordResult(canary=canary, skill=skill, revocation=revocation)

    async def get_canary_result(
        self,
        *,
        workspace_key: str | None = None,
        canary_result_id: UUID,
    ) -> CanaryResultRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT cr.*, w.external_key AS workspace_key
                FROM autoskill.canary_results cr
                LEFT JOIN autoskill.workspaces w ON w.workspace_id = cr.workspace_id
                WHERE cr.canary_result_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                canary_result_id,
                workspace_key,
            )
        return CanaryResultRecord.from_row(row) if row else None

    async def list_canary_results(
        self,
        *,
        workspace_key: str | None = None,
        skill_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[CanaryResultRecord]:
        bounded_limit = max(1, min(limit, 500))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cr.*, w.external_key AS workspace_key
                FROM autoskill.canary_results cr
                LEFT JOIN autoskill.workspaces w ON w.workspace_id = cr.workspace_id
                WHERE ($1::text IS NULL OR w.external_key = $1)
                  AND ($2::uuid IS NULL OR cr.skill_id = $2)
                  AND ($3::text IS NULL OR cr.status = $3)
                ORDER BY cr.observed_at DESC, cr.canary_result_id DESC
                LIMIT $4
                """,
                workspace_key,
                skill_id,
                status,
                bounded_limit,
            )
        return [CanaryResultRecord.from_row(row) for row in rows]


async def _set_skill_lifecycle(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    workspace_key: str,
    skill_id: UUID,
    lifecycle_state: str,
    last_canary_status: str | None,
    freeze_reason: str | None,
) -> SkillLifecycleRecord | None:
    row = await conn.fetchrow(
        """
        UPDATE autoskill.skills
        SET lifecycle_state = $3,
            last_canary_status = $4,
            freeze_reason = $5,
            frozen_at = CASE WHEN $3 = 'frozen' THEN COALESCE(frozen_at, now()) ELSE NULL END,
            updated_at = now()
        WHERE workspace_id = $1
          AND skill_id = $2
        RETURNING *, $6::text AS workspace_key
        """,
        workspace_id,
        skill_id,
        lifecycle_state,
        last_canary_status,
        freeze_reason,
        workspace_key,
    )
    return SkillLifecycleRecord.from_row(row) if row else None


async def _update_last_canary_status(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    workspace_key: str,
    skill_id: UUID,
    status: str,
) -> SkillLifecycleRecord | None:
    row = await conn.fetchrow(
        """
        UPDATE autoskill.skills
        SET last_canary_status = $3,
            updated_at = now()
        WHERE workspace_id = $1
          AND skill_id = $2
        RETURNING *, $4::text AS workspace_key
        """,
        workspace_id,
        skill_id,
        status,
        workspace_key,
    )
    return SkillLifecycleRecord.from_row(row) if row else None


def _null_skill(
    *,
    workspace_key: str,
    skill_id: UUID,
    lifecycle_state: str,
    last_canary_status: str | None,
    freeze_reason: str | None,
) -> SkillLifecycleRecord:
    now = datetime.now(UTC)
    return SkillLifecycleRecord(
        skill_id=skill_id,
        workspace_id=None,
        workspace_key=workspace_key,
        slug="unknown",
        lifecycle_state=lifecycle_state,
        active_version_id=None,
        last_canary_status=last_canary_status,
        freeze_reason=freeze_reason,
        frozen_at=now if lifecycle_state == "frozen" else None,
        updated_at=now,
    )


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
