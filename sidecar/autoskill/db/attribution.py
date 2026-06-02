from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_json
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class AttributionEventRecord:
    attribution_event_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    session_id: str | None
    turn_id: str | None
    action_kind: str
    risk_level: str
    skill_ids: list[UUID]
    outcome: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> AttributionEventRecord:
        metadata = row["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        return cls(
            attribution_event_id=row["attribution_event_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            action_kind=row["action_kind"],
            risk_level=row["risk_level"],
            skill_ids=list(row["skill_ids"]),
            outcome=_row_get(row, "outcome"),
            metadata=metadata,
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "attribution_event_id": str(self.attribution_event_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "action_kind": self.action_kind,
            "risk_level": self.risk_level,
            "skill_ids": [str(skill_id) for skill_id in self.skill_ids],
            "outcome": self.outcome,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ActionAttributionCheckRecord:
    action_attribution_check_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    session_id: str | None
    turn_id: str | None
    tool_call_id: str | None
    action_kind: str
    risk_tier: str
    user_intent_hash: str | None
    contributing_skill_ids: list[UUID]
    contributing_memory_ids: list[UUID]
    contributing_evidence_ids: list[UUID]
    broker_policy_version_id: UUID | None
    counterfactual_kind: str | None
    verdict: str
    metrics: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> ActionAttributionCheckRecord:
        metrics = row["metrics"]
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        return cls(
            action_attribution_check_id=row["action_attribution_check_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            tool_call_id=_row_get(row, "tool_call_id"),
            action_kind=row["action_kind"],
            risk_tier=row["risk_tier"],
            user_intent_hash=_row_get(row, "user_intent_hash"),
            contributing_skill_ids=list(row["contributing_skill_ids"]),
            contributing_memory_ids=list(row["contributing_memory_ids"]),
            contributing_evidence_ids=list(row["contributing_evidence_ids"]),
            broker_policy_version_id=_row_get(row, "broker_policy_version_id"),
            counterfactual_kind=_row_get(row, "counterfactual_kind"),
            verdict=row["verdict"],
            metrics=metrics,
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "action_attribution_check_id": str(self.action_attribution_check_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "tool_call_id": self.tool_call_id,
            "action_kind": self.action_kind,
            "risk_tier": self.risk_tier,
            "user_intent_hash": self.user_intent_hash,
            "contributing_skill_ids": [
                str(skill_id) for skill_id in self.contributing_skill_ids
            ],
            "contributing_memory_ids": [
                str(memory_id) for memory_id in self.contributing_memory_ids
            ],
            "contributing_evidence_ids": [
                str(evidence_id) for evidence_id in self.contributing_evidence_ids
            ],
            "broker_policy_version_id": (
                str(self.broker_policy_version_id)
                if self.broker_policy_version_id
                else None
            ),
            "counterfactual_kind": self.counterfactual_kind,
            "verdict": self.verdict,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
        }


class AttributionStore(Protocol):
    async def record_event(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        action_kind: str,
        risk_level: str,
        skill_ids: list[UUID],
        outcome: str | None,
        metadata: dict[str, Any],
    ) -> AttributionEventRecord:
        """Record an auditable outcome-attribution event."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Mark attribution records influenced by revoked objects."""

    async def record_action_check(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        tool_call_id: str | None,
        action_kind: str,
        risk_tier: str,
        verdict: str,
        metrics: dict[str, Any],
        user_intent_hash: str | None = None,
        contributing_skill_ids: list[UUID] | None = None,
        contributing_memory_ids: list[UUID] | None = None,
        contributing_evidence_ids: list[UUID] | None = None,
        broker_policy_version_id: UUID | None = None,
        counterfactual_kind: str | None = None,
    ) -> ActionAttributionCheckRecord:
        """Record a deterministic risky-action attribution check."""


class NullAttributionStore:
    def __init__(self) -> None:
        self.checks: list[ActionAttributionCheckRecord] = []

    async def record_event(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        action_kind: str,
        risk_level: str,
        skill_ids: list[UUID],
        outcome: str | None,
        metadata: dict[str, Any],
    ) -> AttributionEventRecord:
        return AttributionEventRecord(
            attribution_event_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            session_id=session_id,
            turn_id=turn_id,
            action_kind=action_kind,
            risk_level=risk_level,
            skill_ids=skill_ids,
            outcome=outcome,
            metadata=metadata,
            created_at=datetime.now().astimezone(),
        )

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0

    async def record_action_check(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        tool_call_id: str | None,
        action_kind: str,
        risk_tier: str,
        verdict: str,
        metrics: dict[str, Any],
        user_intent_hash: str | None = None,
        contributing_skill_ids: list[UUID] | None = None,
        contributing_memory_ids: list[UUID] | None = None,
        contributing_evidence_ids: list[UUID] | None = None,
        broker_policy_version_id: UUID | None = None,
        counterfactual_kind: str | None = None,
    ) -> ActionAttributionCheckRecord:
        record = ActionAttributionCheckRecord(
            action_attribution_check_id=UUID("00000000-0000-0000-0000-000000000000"),
            workspace_id=None,
            workspace_key=workspace_key,
            session_id=session_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            action_kind=action_kind,
            risk_tier=risk_tier,
            user_intent_hash=user_intent_hash,
            contributing_skill_ids=contributing_skill_ids or [],
            contributing_memory_ids=contributing_memory_ids or [],
            contributing_evidence_ids=contributing_evidence_ids or [],
            broker_policy_version_id=broker_policy_version_id,
            counterfactual_kind=counterfactual_kind,
            verdict=verdict,
            metrics=metrics,
            created_at=datetime.now().astimezone(),
        )
        self.checks.append(record)
        return record


class AsyncpgAttributionStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def record_event(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        action_kind: str,
        risk_level: str,
        skill_ids: list[UUID],
        outcome: str | None,
        metadata: dict[str, Any],
    ) -> AttributionEventRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.attribution_events (
                  attribution_event_id,
                  workspace_id,
                  session_id,
                  turn_id,
                  action_kind,
                  risk_level,
                  skill_ids,
                  outcome,
                  metadata
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                RETURNING *
                """,
                workspace_id,
                session_id,
                turn_id,
                action_kind,
                risk_level,
                skill_ids,
                outcome,
                json.dumps(metadata, sort_keys=True, separators=(",", ":")),
            )
            return AttributionEventRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def record_action_check(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        tool_call_id: str | None,
        action_kind: str,
        risk_tier: str,
        verdict: str,
        metrics: dict[str, Any],
        user_intent_hash: str | None = None,
        contributing_skill_ids: list[UUID] | None = None,
        contributing_memory_ids: list[UUID] | None = None,
        contributing_evidence_ids: list[UUID] | None = None,
        broker_policy_version_id: UUID | None = None,
        counterfactual_kind: str | None = None,
    ) -> ActionAttributionCheckRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.action_attribution_checks (
                  action_attribution_check_id,
                  workspace_id,
                  session_id,
                  turn_id,
                  tool_call_id,
                  action_kind,
                  risk_tier,
                  user_intent_hash,
                  contributing_skill_ids,
                  contributing_memory_ids,
                  contributing_evidence_ids,
                  broker_policy_version_id,
                  counterfactual_kind,
                  verdict,
                  metrics
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7,
                  $8::uuid[], $9::uuid[], $10::uuid[], $11, $12, $13, $14::jsonb
                )
                RETURNING *
                """,
                workspace_id,
                session_id,
                turn_id,
                tool_call_id,
                action_kind,
                risk_tier,
                user_intent_hash,
                contributing_skill_ids or [],
                contributing_memory_ids or [],
                contributing_evidence_ids or [],
                broker_policy_version_id,
                counterfactual_kind,
                verdict,
                json.dumps(metrics, sort_keys=True, separators=(",", ":")),
            )
            return ActionAttributionCheckRecord.from_row(
                {**dict(row), "workspace_key": workspace_key}
            )

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        object_keys = _object_keys(objects)
        if not object_keys:
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            result = await conn.fetchval(
                """
                WITH targets AS (
                  SELECT *
                  FROM unnest($2::text[], $3::uuid[]) AS target(object_type, object_id)
                ),
                skill_targets AS (
                  SELECT object_id AS skill_id
                  FROM targets
                  WHERE object_type = 'skill'
                  UNION
                  SELECT sv.skill_id
                  FROM autoskill.skill_versions sv
                  JOIN targets t ON t.object_type = 'skill_version'
                    AND t.object_id = sv.skill_version_id
                ),
                revoked_events AS (
                  UPDATE autoskill.attribution_events ae
                  SET metadata = ae.metadata || jsonb_build_object(
                        'revoked', true,
                        'revoked_at', now(),
                        'revocation_reason', 'derived_object_revoked'
                      )
                  FROM autoskill.workspaces w
                  WHERE ae.workspace_id = w.workspace_id
                    AND w.external_key = $1
                    AND ae.metadata->>'revoked' IS DISTINCT FROM 'true'
                    AND (
                      ae.attribution_event_id IN (
                        SELECT object_id FROM targets WHERE object_type = 'attribution_event'
                      )
                      OR ae.skill_ids && ARRAY(SELECT skill_id FROM skill_targets)
                      OR ae.memory_ids && ARRAY(
                        SELECT object_id FROM targets WHERE object_type = 'memory'
                      )
                      OR ae.retrieved_artifact_ids && ARRAY(
                        SELECT object_id FROM targets
                        WHERE object_type IN (
                          'body_index_document',
                          'context_artifact',
                          'retrieved_artifact'
                        )
                      )
                    )
                  RETURNING ae.attribution_event_id
                ),
                revoked_checks AS (
                  UPDATE autoskill.action_attribution_checks ac
                  SET verdict = 'revoked',
                      metrics = ac.metrics || jsonb_build_object(
                        'revoked', true,
                        'revoked_at', now(),
                        'revocation_reason', 'derived_object_revoked'
                      )
                  FROM autoskill.workspaces w
                  WHERE ac.workspace_id = w.workspace_id
                    AND w.external_key = $1
                    AND ac.metrics->>'revoked' IS DISTINCT FROM 'true'
                    AND (
                      ac.action_attribution_check_id IN (
                        SELECT object_id
                        FROM targets
                        WHERE object_type = 'action_attribution_check'
                      )
                      OR ac.contributing_skill_ids && ARRAY(SELECT skill_id FROM skill_targets)
                      OR ac.contributing_memory_ids && ARRAY(
                        SELECT object_id FROM targets WHERE object_type = 'memory'
                      )
                      OR ac.contributing_evidence_ids && ARRAY(
                        SELECT object_id FROM targets WHERE object_type = 'evidence'
                      )
                      OR ac.broker_policy_version_id IN (
                        SELECT object_id FROM targets WHERE object_type = 'broker_policy_version'
                      )
                    )
                  RETURNING ac.action_attribution_check_id
                )
                SELECT
                  (SELECT count(*) FROM revoked_events)
                  + (SELECT count(*) FROM revoked_checks) AS invalidated
                """,
                workspace_key,
                [object_type for object_type, _object_id in object_keys],
                [object_id for _object_type, object_id in object_keys],
            )
        return int(result or 0)

    async def record_shadowing_control(
        self,
        *,
        workspace_key: str,
        selected_skill_id: UUID,
        expected_skill_id: UUID,
        evidence_ids: list[UUID],
        support_count: int,
    ) -> dict[str, Any]:
        pool = await self._get_pool()
        payload = {
            "schema": "autoskill.probe.v1",
            "kind": "shadowing",
            "selected_skill_id": str(selected_skill_id),
            "expected_skill_id": str(expected_skill_id),
            "evidence_ids": [str(evidence_id) for evidence_id in evidence_ids],
        }
        probe_hash = sha256_json(payload)
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            edge = await conn.fetchrow(
                """
                INSERT INTO autoskill.skill_edges (
                  edge_id, workspace_id, from_skill_id, to_skill_id, edge_kind
                )
                VALUES (gen_random_uuid(), $1, $2, $3, 'shadow')
                ON CONFLICT (from_skill_id, to_skill_id, edge_kind) DO UPDATE
                SET revoked_at = NULL,
                    revocation_metadata = '{}'::jsonb
                RETURNING edge_id
                """,
                workspace_id,
                selected_skill_id,
                expected_skill_id,
            )
            probe = await conn.fetchrow(
                """
                INSERT INTO autoskill.probes (
                  probe_id, workspace_id, probe_hash, kind, maturity, spec, expected, active
                )
                VALUES (
                  gen_random_uuid(), $1, $2, 'shadowing', 'contrastive', $3::jsonb, $4::jsonb, true
                )
                ON CONFLICT (workspace_id, probe_hash) DO NOTHING
                RETURNING probe_id
                """,
                workspace_id,
                probe_hash,
                _json(
                    {
                        **payload,
                        "mode": "skill_hidden",
                        "support_count": support_count,
                    }
                ),
                _json(
                    {
                        "status": "compare",
                        "selected_skill_should_not_shadow_expected": True,
                    }
                ),
            )
            return {
                "edge_created": edge is not None,
                "probe_created": probe is not None,
                "probe_hash": probe_hash,
                "selected_skill_id": str(selected_skill_id),
                "expected_skill_id": str(expected_skill_id),
                "support_count": support_count,
            }


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _object_keys(objects: list[dict[str, str]]) -> list[tuple[str, UUID]]:
    keys: list[tuple[str, UUID]] = []
    for item in objects:
        object_type = item.get("object_type")
        object_id = item.get("object_id")
        if not object_type or not object_id:
            continue
        try:
            parsed = UUID(str(object_id))
        except (TypeError, ValueError):
            continue
        keys.append((str(object_type), parsed))
    return keys
