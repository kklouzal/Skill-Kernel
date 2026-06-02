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
class BrokerPolicyVersionRecord:
    broker_policy_version_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    version: str
    policy: dict[str, Any]
    status: str
    created_at: datetime
    activated_at: datetime | None
    rolled_back_at: datetime | None

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> BrokerPolicyVersionRecord:
        return cls(
            broker_policy_version_id=row["broker_policy_version_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            version=row["version"],
            policy=_json_dict(row["policy"]),
            status=row["status"],
            created_at=row["created_at"],
            activated_at=_row_get(row, "activated_at"),
            rolled_back_at=_row_get(row, "rolled_back_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "broker_policy_version_id": str(self.broker_policy_version_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "version": self.version,
            "policy": self.policy,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "rolled_back_at": (
                self.rolled_back_at.isoformat() if self.rolled_back_at else None
            ),
        }


class BrokerPolicyStore(Protocol):
    async def get_policy_version(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
    ) -> BrokerPolicyVersionRecord | None:
        """Return one persisted broker policy artifact."""

    async def get_active_policy(
        self,
        *,
        workspace_key: str,
    ) -> BrokerPolicyVersionRecord | None:
        """Return the active broker policy artifact for a workspace."""

    async def upsert_policy_version(
        self,
        *,
        workspace_key: str,
        version: str,
        policy: dict[str, Any],
        status: str = "candidate",
        broker_policy_version_id: UUID | None = None,
    ) -> BrokerPolicyVersionRecord:
        """Create or replace a versioned broker policy artifact."""

    async def activate_policy_version(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
    ) -> BrokerPolicyVersionRecord | None:
        """Activate one broker policy version and deactivate sibling active policies."""

    async def record_canary_feedback(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
        status: str,
        metrics: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> BrokerPolicyVersionRecord | None:
        """Attach bounded canary feedback and roll back critical policy versions."""


class NullBrokerPolicyStore:
    def __init__(self) -> None:
        self.policies: dict[tuple[str, UUID], BrokerPolicyVersionRecord] = {}
        self.active_by_workspace: dict[str, UUID] = {}

    async def get_active_policy(
        self,
        *,
        workspace_key: str,
    ) -> BrokerPolicyVersionRecord | None:
        policy_id = self.active_by_workspace.get(workspace_key)
        if policy_id is None:
            return None
        return self.policies.get((workspace_key, policy_id))

    async def get_policy_version(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
    ) -> BrokerPolicyVersionRecord | None:
        return self.policies.get((workspace_key, broker_policy_version_id))

    async def upsert_policy_version(
        self,
        *,
        workspace_key: str,
        version: str,
        policy: dict[str, Any],
        status: str = "candidate",
        broker_policy_version_id: UUID | None = None,
    ) -> BrokerPolicyVersionRecord:
        now = datetime.now()
        policy_id = broker_policy_version_id or uuid4()
        record = BrokerPolicyVersionRecord(
            broker_policy_version_id=policy_id,
            workspace_id=None,
            workspace_key=workspace_key,
            version=version,
            policy=policy,
            status=status,
            created_at=now,
            activated_at=now if status == "active" else None,
            rolled_back_at=None,
        )
        self.policies[(workspace_key, policy_id)] = record
        if status == "active":
            self.active_by_workspace[workspace_key] = policy_id
        return record

    async def activate_policy_version(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
    ) -> BrokerPolicyVersionRecord | None:
        record = self.policies.get((workspace_key, broker_policy_version_id))
        if record is None:
            return None
        activated = BrokerPolicyVersionRecord(
            broker_policy_version_id=record.broker_policy_version_id,
            workspace_id=record.workspace_id,
            workspace_key=record.workspace_key,
            version=record.version,
            policy=record.policy,
            status="active",
            created_at=record.created_at,
            activated_at=datetime.now(),
            rolled_back_at=None,
        )
        self.policies[(workspace_key, broker_policy_version_id)] = activated
        self.active_by_workspace[workspace_key] = broker_policy_version_id
        return activated

    async def record_canary_feedback(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
        status: str,
        metrics: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> BrokerPolicyVersionRecord | None:
        record = self.policies.get((workspace_key, broker_policy_version_id))
        if record is None:
            return None
        feedback = {
            "last_canary": {
                "status": status,
                "metrics": metrics or {},
                "reason": reason,
                "observed_at": datetime.now().isoformat(),
            }
        }
        updated = BrokerPolicyVersionRecord(
            broker_policy_version_id=record.broker_policy_version_id,
            workspace_id=record.workspace_id,
            workspace_key=record.workspace_key,
            version=record.version,
            policy=record.policy | {"runtime_feedback": feedback},
            status="rolled_back" if status == "critical" else record.status,
            created_at=record.created_at,
            activated_at=record.activated_at,
            rolled_back_at=datetime.now() if status == "critical" else record.rolled_back_at,
        )
        self.policies[(workspace_key, broker_policy_version_id)] = updated
        if status == "critical":
            self.active_by_workspace.pop(workspace_key, None)
        return updated


class AsyncpgBrokerPolicyStore(AsyncpgPoolOwner):
    async def get_policy_version(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
    ) -> BrokerPolicyVersionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT p.*, w.external_key AS workspace_key
                FROM autoskill.broker_policy_versions p
                JOIN autoskill.workspaces w ON w.workspace_id = p.workspace_id
                WHERE w.external_key = $1
                  AND p.broker_policy_version_id = $2
                """,
                workspace_key,
                broker_policy_version_id,
            )
        return BrokerPolicyVersionRecord.from_row(row) if row else None

    async def get_active_policy(
        self,
        *,
        workspace_key: str,
    ) -> BrokerPolicyVersionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT p.*, w.external_key AS workspace_key
                FROM autoskill.broker_policy_versions p
                JOIN autoskill.workspaces w ON w.workspace_id = p.workspace_id
                WHERE w.external_key = $1
                  AND p.status = 'active'
                  AND p.rolled_back_at IS NULL
                ORDER BY p.activated_at DESC NULLS LAST, p.created_at DESC
                LIMIT 1
                """,
                workspace_key,
            )
        return BrokerPolicyVersionRecord.from_row(row) if row else None

    async def upsert_policy_version(
        self,
        *,
        workspace_key: str,
        version: str,
        policy: dict[str, Any],
        status: str = "candidate",
        broker_policy_version_id: UUID | None = None,
    ) -> BrokerPolicyVersionRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            if status == "active":
                await _deactivate_active_policies(conn, workspace_id)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.broker_policy_versions (
                  broker_policy_version_id,
                  workspace_id,
                  version,
                  policy,
                  status,
                  activated_at,
                  rolled_back_at
                )
                VALUES (
                  COALESCE($1, gen_random_uuid()),
                  $2,
                  $3,
                  $4::jsonb,
                  $5,
                  CASE WHEN $5 = 'active' THEN now() ELSE NULL END,
                  NULL
                )
                ON CONFLICT (workspace_id, version)
                DO UPDATE SET
                  policy = EXCLUDED.policy,
                  status = EXCLUDED.status,
                  activated_at = EXCLUDED.activated_at,
                  rolled_back_at = NULL
                RETURNING *, $6::text AS workspace_key
                """,
                broker_policy_version_id,
                workspace_id,
                version,
                _json(policy),
                status,
                workspace_key,
            )
        return BrokerPolicyVersionRecord.from_row(row)

    async def activate_policy_version(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
    ) -> BrokerPolicyVersionRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            await _deactivate_active_policies(conn, workspace_id)
            row = await conn.fetchrow(
                """
                UPDATE autoskill.broker_policy_versions
                SET status = 'active',
                    activated_at = now(),
                    rolled_back_at = NULL
                WHERE workspace_id = $1
                  AND broker_policy_version_id = $2
                RETURNING *, $3::text AS workspace_key
                """,
                workspace_id,
                broker_policy_version_id,
                workspace_key,
            )
        return BrokerPolicyVersionRecord.from_row(row) if row else None

    async def record_canary_feedback(
        self,
        *,
        workspace_key: str,
        broker_policy_version_id: UUID,
        status: str,
        metrics: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> BrokerPolicyVersionRecord | None:
        pool = await self._get_pool()
        feedback = {
            "last_canary": {
                "status": status,
                "metrics": metrics or {},
                "reason": reason,
                "observed_at": datetime.now().isoformat(),
            }
        }
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                UPDATE autoskill.broker_policy_versions
                SET policy = policy || jsonb_build_object('runtime_feedback', $3::jsonb),
                    status = CASE WHEN $4 = 'critical' THEN 'rolled_back' ELSE status END,
                    rolled_back_at = CASE
                      WHEN $4 = 'critical' THEN now()
                      ELSE rolled_back_at
                    END
                WHERE workspace_id = $1
                  AND broker_policy_version_id = $2
                RETURNING *, $5::text AS workspace_key
                """,
                workspace_id,
                broker_policy_version_id,
                _json(feedback),
                status,
                workspace_key,
            )
        return BrokerPolicyVersionRecord.from_row(row) if row else None


async def _deactivate_active_policies(
    conn: asyncpg.Connection,
    workspace_id: UUID,
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.broker_policy_versions
        SET status = 'superseded'
        WHERE workspace_id = $1
          AND status = 'active'
        """,
        workspace_id,
    )


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return dict(value)


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
