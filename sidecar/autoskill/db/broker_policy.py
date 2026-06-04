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


@dataclass(frozen=True)
class BrokerReplayEpisodeRecord:
    broker_replay_episode_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_retrieval_log_id: UUID | None
    episode_key: str
    redacted_user_intent: str
    expected_decision: str | None
    expected_skill_ids: list[UUID]
    tags: list[str]
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> BrokerReplayEpisodeRecord:
        return cls(
            broker_replay_episode_id=row["broker_replay_episode_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_retrieval_log_id=_row_get(row, "source_retrieval_log_id"),
            episode_key=row["episode_key"],
            redacted_user_intent=row["redacted_user_intent"],
            expected_decision=_row_get(row, "expected_decision"),
            expected_skill_ids=list(row["expected_skill_ids"] or []),
            tags=list(row["tags"] or []),
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "broker_replay_episode_id": str(self.broker_replay_episode_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_retrieval_log_id": (
                str(self.source_retrieval_log_id)
                if self.source_retrieval_log_id
                else None
            ),
            "episode_key": self.episode_key,
            "redacted_user_intent": self.redacted_user_intent,
            "expected_decision": self.expected_decision,
            "expected_skill_ids": [str(item) for item in self.expected_skill_ids],
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
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

    async def record_replay_episode(
        self,
        *,
        workspace_key: str,
        episode_key: str,
        redacted_user_intent: str,
        expected_decision: str | None = None,
        expected_skill_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source_retrieval_log_id: UUID | None = None,
    ) -> BrokerReplayEpisodeRecord:
        """Persist one content-safe broker replay episode for policy replay."""

    async def list_replay_episodes(
        self,
        *,
        workspace_key: str,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[BrokerReplayEpisodeRecord]:
        """List content-safe broker replay episodes for historical policy replay."""

    async def get_replay_episode(
        self,
        *,
        workspace_key: str | None,
        broker_replay_episode_id: UUID,
    ) -> BrokerReplayEpisodeRecord | None:
        """Return one content-safe broker replay episode."""


class NullBrokerPolicyStore:
    def __init__(self) -> None:
        self.policies: dict[tuple[str, UUID], BrokerPolicyVersionRecord] = {}
        self.active_by_workspace: dict[str, UUID] = {}
        self.replay_episodes: dict[tuple[str, str], BrokerReplayEpisodeRecord] = {}

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

    async def record_replay_episode(
        self,
        *,
        workspace_key: str,
        episode_key: str,
        redacted_user_intent: str,
        expected_decision: str | None = None,
        expected_skill_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source_retrieval_log_id: UUID | None = None,
    ) -> BrokerReplayEpisodeRecord:
        existing = self.replay_episodes.get((workspace_key, episode_key))
        record = BrokerReplayEpisodeRecord(
            broker_replay_episode_id=(
                existing.broker_replay_episode_id if existing else uuid4()
            ),
            workspace_id=None,
            workspace_key=workspace_key,
            source_retrieval_log_id=source_retrieval_log_id,
            episode_key=episode_key,
            redacted_user_intent=redacted_user_intent,
            expected_decision=expected_decision,
            expected_skill_ids=expected_skill_ids or [],
            tags=tags or [],
            metadata=metadata or {},
            created_at=existing.created_at if existing else datetime.now(),
        )
        self.replay_episodes[(workspace_key, episode_key)] = record
        return record

    async def list_replay_episodes(
        self,
        *,
        workspace_key: str,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[BrokerReplayEpisodeRecord]:
        tag_set = set(tags or [])
        records = [
            record
            for (record_workspace, _episode_key), record in self.replay_episodes.items()
            if record_workspace == workspace_key
            and (not tag_set or tag_set.issubset(set(record.tags)))
        ]
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records[:limit]

    async def get_replay_episode(
        self,
        *,
        workspace_key: str | None,
        broker_replay_episode_id: UUID,
    ) -> BrokerReplayEpisodeRecord | None:
        for (record_workspace, _episode_key), record in self.replay_episodes.items():
            if record.broker_replay_episode_id != broker_replay_episode_id:
                continue
            if workspace_key is not None and record_workspace != workspace_key:
                continue
            return record
        return None


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

    async def record_replay_episode(
        self,
        *,
        workspace_key: str,
        episode_key: str,
        redacted_user_intent: str,
        expected_decision: str | None = None,
        expected_skill_ids: list[UUID] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        source_retrieval_log_id: UUID | None = None,
    ) -> BrokerReplayEpisodeRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.broker_replay_episodes (
                  broker_replay_episode_id,
                  workspace_id,
                  source_retrieval_log_id,
                  episode_key,
                  redacted_user_intent,
                  expected_decision,
                  expected_skill_ids,
                  tags,
                  metadata
                )
                VALUES (
                  gen_random_uuid(),
                  $1,
                  $2,
                  $3,
                  $4,
                  $5,
                  $6,
                  $7,
                  $8::jsonb
                )
                ON CONFLICT (workspace_id, episode_key)
                DO UPDATE SET
                  source_retrieval_log_id = EXCLUDED.source_retrieval_log_id,
                  redacted_user_intent = EXCLUDED.redacted_user_intent,
                  expected_decision = EXCLUDED.expected_decision,
                  expected_skill_ids = EXCLUDED.expected_skill_ids,
                  tags = EXCLUDED.tags,
                  metadata = EXCLUDED.metadata
                RETURNING *, $9::text AS workspace_key
                """,
                workspace_id,
                source_retrieval_log_id,
                episode_key,
                redacted_user_intent,
                expected_decision,
                expected_skill_ids or [],
                tags or [],
                _json(metadata or {}),
                workspace_key,
            )
        return BrokerReplayEpisodeRecord.from_row(row)

    async def list_replay_episodes(
        self,
        *,
        workspace_key: str,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[BrokerReplayEpisodeRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.*, w.external_key AS workspace_key
                FROM autoskill.broker_replay_episodes e
                JOIN autoskill.workspaces w ON w.workspace_id = e.workspace_id
                WHERE w.external_key = $1
                  AND (
                    $2::text[] = '{}'::text[]
                    OR e.tags @> $2::text[]
                  )
                ORDER BY e.created_at DESC
                LIMIT $3
                """,
                workspace_key,
                tags or [],
                limit,
            )
        return [BrokerReplayEpisodeRecord.from_row(row) for row in rows]

    async def get_replay_episode(
        self,
        *,
        workspace_key: str | None,
        broker_replay_episode_id: UUID,
    ) -> BrokerReplayEpisodeRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT e.*, w.external_key AS workspace_key
                FROM autoskill.broker_replay_episodes e
                JOIN autoskill.workspaces w ON w.workspace_id = e.workspace_id
                WHERE e.broker_replay_episode_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                broker_replay_episode_id,
                workspace_key,
            )
        return BrokerReplayEpisodeRecord.from_row(row) if row else None

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
