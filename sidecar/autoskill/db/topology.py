from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class SkillGraphOperationRecord:
    skill_graph_operation_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    operation_kind: str
    status: str
    subject_skill_ids: list[UUID]
    output_skill_ids: list[UUID]
    skill_graph_ir: dict[str, Any]
    evidence_ids: list[UUID]
    effect_coverage: dict[str, Any]
    trial_summary: dict[str, Any]
    evolution_transaction_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> SkillGraphOperationRecord:
        return cls(
            skill_graph_operation_id=row["skill_graph_operation_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            operation_kind=row["operation_kind"],
            status=row["status"],
            subject_skill_ids=list(row["subject_skill_ids"]),
            output_skill_ids=list(row["output_skill_ids"]),
            skill_graph_ir=_json_dict(row["skill_graph_ir"]),
            evidence_ids=list(row["evidence_ids"]),
            effect_coverage=_json_dict(row["effect_coverage"]),
            trial_summary=_json_dict(row["trial_summary"]),
            evolution_transaction_id=_row_get(row, "evolution_transaction_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_graph_operation_id": str(self.skill_graph_operation_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "operation_kind": self.operation_kind,
            "status": self.status,
            "subject_skill_ids": [str(item) for item in self.subject_skill_ids],
            "output_skill_ids": [str(item) for item in self.output_skill_ids],
            "skill_graph_ir": self.skill_graph_ir,
            "evidence_ids": [str(item) for item in self.evidence_ids],
            "effect_coverage": self.effect_coverage,
            "trial_summary": self.trial_summary,
            "evolution_transaction_id": (
                str(self.evolution_transaction_id)
                if self.evolution_transaction_id
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class PlannedTopologyTrialRecord:
    planned_topology_trial_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_graph_operation_id: UUID
    trial_kind: str
    objective: str
    expected: dict[str, Any]
    status: str
    result: dict[str, Any]
    evolution_transaction_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> PlannedTopologyTrialRecord:
        return cls(
            planned_topology_trial_id=row["planned_topology_trial_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_graph_operation_id=row["skill_graph_operation_id"],
            trial_kind=row["trial_kind"],
            objective=row["objective"],
            expected=_json_dict(row["expected"]),
            status=row["status"],
            result=_json_dict(row["result"]),
            evolution_transaction_id=_row_get(row, "evolution_transaction_id"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "planned_topology_trial_id": str(self.planned_topology_trial_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_graph_operation_id": str(self.skill_graph_operation_id),
            "trial_kind": self.trial_kind,
            "objective": self.objective,
            "expected": self.expected,
            "status": self.status,
            "result": self.result,
            "evolution_transaction_id": (
                str(self.evolution_transaction_id)
                if self.evolution_transaction_id
                else None
            ),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True)
class TopologyPersistenceRecord:
    operation: SkillGraphOperationRecord
    trials: list[PlannedTopologyTrialRecord]

    def to_json(self) -> dict[str, Any]:
        return {
            "operation": self.operation.to_json(),
            "trials": [trial.to_json() for trial in self.trials],
        }


@dataclass(frozen=True)
class TopologyApplyResult:
    allowed: bool
    operation: SkillGraphOperationRecord | None
    blockers: list[str]
    downstream_actions: list[dict[str, Any]] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "operation": self.operation.to_json() if self.operation else None,
            "blockers": self.blockers,
            "downstream_actions": self.downstream_actions or [],
        }


class TopologyStore(Protocol):
    async def record_operation(
        self,
        *,
        workspace_key: str,
        operation_kind: str,
        status: str,
        subject_skill_ids: list[UUID] | None = None,
        output_skill_ids: list[UUID] | None = None,
        skill_graph_ir: dict[str, Any] | None = None,
        evidence_ids: list[UUID] | None = None,
        effect_coverage: dict[str, Any] | None = None,
        trial_summary: dict[str, Any] | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillGraphOperationRecord:
        """Record a proposed skill-graph operation."""

    async def record_planned_trial(
        self,
        *,
        workspace_key: str,
        skill_graph_operation_id: UUID,
        trial_kind: str,
        objective: str,
        expected: dict[str, Any] | None = None,
        status: str = "planned",
        result: dict[str, Any] | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> PlannedTopologyTrialRecord:
        """Record one planned topology evaluation trial."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Mark revoked topology operations/trials inactive."""

    async def apply_operation(
        self,
        *,
        workspace_key: str,
        skill_graph_operation_id: UUID,
        applied_by: str = "autoskill-sidecar",
    ) -> TopologyApplyResult:
        """Mark a topology operation applied after deterministic trial gates pass."""


class NullTopologyStore:
    def __init__(self) -> None:
        self.operations: list[SkillGraphOperationRecord] = []
        self.trials: list[PlannedTopologyTrialRecord] = []

    async def record_operation(
        self,
        *,
        workspace_key: str,
        operation_kind: str,
        status: str,
        subject_skill_ids: list[UUID] | None = None,
        output_skill_ids: list[UUID] | None = None,
        skill_graph_ir: dict[str, Any] | None = None,
        evidence_ids: list[UUID] | None = None,
        effect_coverage: dict[str, Any] | None = None,
        trial_summary: dict[str, Any] | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillGraphOperationRecord:
        now = datetime.now(UTC)
        record = SkillGraphOperationRecord(
            skill_graph_operation_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            operation_kind=operation_kind,
            status=status,
            subject_skill_ids=subject_skill_ids or [],
            output_skill_ids=output_skill_ids or [],
            skill_graph_ir=skill_graph_ir or {},
            evidence_ids=evidence_ids or [],
            effect_coverage=effect_coverage or {},
            trial_summary=trial_summary or {},
            evolution_transaction_id=evolution_transaction_id,
            created_at=now,
            updated_at=now,
        )
        self.operations.append(record)
        return record

    async def record_planned_trial(
        self,
        *,
        workspace_key: str,
        skill_graph_operation_id: UUID,
        trial_kind: str,
        objective: str,
        expected: dict[str, Any] | None = None,
        status: str = "planned",
        result: dict[str, Any] | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> PlannedTopologyTrialRecord:
        now = datetime.now(UTC)
        record = PlannedTopologyTrialRecord(
            planned_topology_trial_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_graph_operation_id=skill_graph_operation_id,
            trial_kind=trial_kind,
            objective=objective,
            expected=expected or {},
            status=status,
            result=result or {},
            evolution_transaction_id=evolution_transaction_id,
            created_at=now,
            updated_at=now,
        )
        self.trials.append(record)
        return record

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        operation_ids = _object_ids(objects, "skill_graph_operation")
        trial_ids = _object_ids(objects, "planned_topology_trial")
        changed = 0
        updated_operations = []
        for operation in self.operations:
            if operation.skill_graph_operation_id not in operation_ids:
                updated_operations.append(operation)
                continue
            changed += 1
            updated_operations.append(
                SkillGraphOperationRecord(
                    **{
                        **operation.__dict__,
                        "status": "rolled_back",
                        "updated_at": datetime.now(UTC),
                    }
                )
            )
        self.operations = updated_operations

        updated_trials = []
        for trial in self.trials:
            should_retire = (
                trial.planned_topology_trial_id in trial_ids
                or trial.skill_graph_operation_id in operation_ids
            )
            if not should_retire:
                updated_trials.append(trial)
                continue
            changed += 1
            updated_trials.append(
                PlannedTopologyTrialRecord(
                    **{
                        **trial.__dict__,
                        "status": "retired",
                        "updated_at": datetime.now(UTC),
                    }
                )
            )
        self.trials = updated_trials
        return changed

    async def apply_operation(
        self,
        *,
        workspace_key: str,
        skill_graph_operation_id: UUID,
        applied_by: str = "autoskill-sidecar",
    ) -> TopologyApplyResult:
        operation = next(
            (
                item
                for item in self.operations
                if item.skill_graph_operation_id == skill_graph_operation_id
            ),
            None,
        )
        if operation is None:
            return TopologyApplyResult(
                allowed=False,
                operation=None,
                blockers=["topology operation not found"],
            )
        trials = [
            trial
            for trial in self.trials
            if trial.skill_graph_operation_id == skill_graph_operation_id
        ]
        blockers = _topology_apply_blockers(operation, trials)
        if blockers:
            return TopologyApplyResult(allowed=False, operation=operation, blockers=blockers)
        now = datetime.now(UTC)
        downstream_actions = _topology_downstream_actions(operation)
        updated = SkillGraphOperationRecord(
            **{
                **operation.__dict__,
                "status": "applied",
                "trial_summary": {
                    **operation.trial_summary,
                    "applied_by": applied_by,
                    "applied_at": now.isoformat(),
                    "downstream_orchestration": {
                        "status": "planned",
                        "actions": downstream_actions,
                        "action_count": len(downstream_actions),
                    },
                },
                "updated_at": now,
            }
        )
        self.operations = [
            updated if item.skill_graph_operation_id == skill_graph_operation_id else item
            for item in self.operations
        ]
        return TopologyApplyResult(
            allowed=True,
            operation=updated,
            blockers=[],
            downstream_actions=downstream_actions,
        )


class AsyncpgTopologyStore(AsyncpgPoolOwner):
    async def record_operation(
        self,
        *,
        workspace_key: str,
        operation_kind: str,
        status: str,
        subject_skill_ids: list[UUID] | None = None,
        output_skill_ids: list[UUID] | None = None,
        skill_graph_ir: dict[str, Any] | None = None,
        evidence_ids: list[UUID] | None = None,
        effect_coverage: dict[str, Any] | None = None,
        trial_summary: dict[str, Any] | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillGraphOperationRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.skill_graph_operations (
                  skill_graph_operation_id,
                  workspace_id,
                  operation_kind,
                  status,
                  subject_skill_ids,
                  output_skill_ids,
                  skill_graph_ir,
                  evidence_ids,
                  effect_coverage,
                  trial_summary,
                  evolution_transaction_id
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4::uuid[], $5::uuid[],
                  $6::jsonb, $7::uuid[], $8::jsonb, $9::jsonb, $10
                )
                RETURNING *, $11::text AS workspace_key
                """,
                workspace_id,
                operation_kind,
                status,
                subject_skill_ids or [],
                output_skill_ids or [],
                _json(skill_graph_ir or {}),
                evidence_ids or [],
                _json(effect_coverage or {}),
                _json(trial_summary or {}),
                evolution_transaction_id,
                workspace_key,
            )
            return SkillGraphOperationRecord.from_row(row)

    async def record_planned_trial(
        self,
        *,
        workspace_key: str,
        skill_graph_operation_id: UUID,
        trial_kind: str,
        objective: str,
        expected: dict[str, Any] | None = None,
        status: str = "planned",
        result: dict[str, Any] | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> PlannedTopologyTrialRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.planned_topology_trials (
                  planned_topology_trial_id,
                  workspace_id,
                  skill_graph_operation_id,
                  trial_kind,
                  objective,
                  expected,
                  status,
                  result,
                  evolution_transaction_id
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8
                )
                RETURNING *, $9::text AS workspace_key
                """,
                workspace_id,
                skill_graph_operation_id,
                trial_kind,
                objective,
                _json(expected or {}),
                status,
                _json(result or {}),
                evolution_transaction_id,
                workspace_key,
            )
            return PlannedTopologyTrialRecord.from_row(row)

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        operation_ids = _object_ids(objects, "skill_graph_operation")
        trial_ids = _object_ids(objects, "planned_topology_trial")
        if not operation_ids and not trial_ids:
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            operation_rows = await conn.fetch(
                """
                UPDATE autoskill.skill_graph_operations
                SET status = 'rolled_back',
                    updated_at = now()
                WHERE workspace_id = $1
                  AND skill_graph_operation_id = ANY($2::uuid[])
                  AND status <> 'rolled_back'
                RETURNING skill_graph_operation_id
                """,
                workspace_id,
                operation_ids,
            )
            trial_rows = await conn.fetch(
                """
                UPDATE autoskill.planned_topology_trials
                SET status = 'retired',
                    updated_at = now()
                WHERE workspace_id = $1
                  AND status <> 'retired'
                  AND (
                    planned_topology_trial_id = ANY($2::uuid[])
                    OR skill_graph_operation_id = ANY($3::uuid[])
                  )
                RETURNING planned_topology_trial_id
                """,
                workspace_id,
                trial_ids,
                operation_ids,
            )
            return len(operation_rows) + len(trial_rows)

    async def apply_operation(
        self,
        *,
        workspace_key: str,
        skill_graph_operation_id: UUID,
        applied_by: str = "autoskill-sidecar",
    ) -> TopologyApplyResult:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            operation_row = await conn.fetchrow(
                """
                SELECT o.*, w.external_key AS workspace_key
                FROM autoskill.skill_graph_operations o
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE o.workspace_id = $1
                  AND o.skill_graph_operation_id = $2
                FOR UPDATE
                """,
                workspace_id,
                skill_graph_operation_id,
            )
            if operation_row is None:
                return TopologyApplyResult(
                    allowed=False,
                    operation=None,
                    blockers=["topology operation not found"],
                )
            operation = SkillGraphOperationRecord.from_row(operation_row)
            trial_rows = await conn.fetch(
                """
                SELECT t.*, w.external_key AS workspace_key
                FROM autoskill.planned_topology_trials t
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE t.workspace_id = $1
                  AND t.skill_graph_operation_id = $2
                ORDER BY t.created_at ASC, t.planned_topology_trial_id ASC
                """,
                workspace_id,
                skill_graph_operation_id,
            )
            trials = [PlannedTopologyTrialRecord.from_row(row) for row in trial_rows]
            blockers = _topology_apply_blockers(operation, trials)
            if blockers:
                return TopologyApplyResult(
                    allowed=False,
                    operation=operation,
                    blockers=blockers,
                )
            downstream_actions = _topology_downstream_actions(operation)
            row = await conn.fetchrow(
                """
                UPDATE autoskill.skill_graph_operations o
                SET status = 'applied',
                    trial_summary = trial_summary || $3::jsonb,
                    updated_at = now()
                FROM autoskill.workspaces w
                WHERE o.workspace_id = w.workspace_id
                  AND o.workspace_id = $1
                  AND o.skill_graph_operation_id = $2
                RETURNING o.*, w.external_key AS workspace_key
                """,
                workspace_id,
                skill_graph_operation_id,
                _json(
                    {
                        "applied_by": applied_by,
                        "applied_at": datetime.now(UTC).isoformat(),
                        "downstream_orchestration": {
                            "status": "planned",
                            "actions": downstream_actions,
                            "action_count": len(downstream_actions),
                        },
                    }
                ),
            )
            return TopologyApplyResult(
                allowed=True,
                operation=SkillGraphOperationRecord.from_row(row),
                blockers=[],
                downstream_actions=downstream_actions,
            )


def _json(value: dict[str, Any] | list[Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _object_ids(objects: list[dict[str, str]], object_type: str) -> list[UUID]:
    values: list[UUID] = []
    for item in objects:
        if item.get("object_type") != object_type:
            continue
        try:
            values.append(UUID(str(item.get("object_id"))))
        except ValueError:
            continue
    return values


def _topology_apply_blockers(
    operation: SkillGraphOperationRecord,
    trials: list[PlannedTopologyTrialRecord],
) -> list[str]:
    blockers: list[str] = []
    if operation.status in {"applied", "rolled_back"}:
        blockers.append(f"topology operation already {operation.status}")
    elif operation.status not in {"candidate", "trial", "accepted"}:
        blockers.append(f"topology operation status is not applyable: {operation.status}")
    if not trials:
        blockers.append("topology operation requires at least one planned trial")
    for trial in trials:
        if trial.status != "passed":
            blockers.append(
                f"topology trial {trial.planned_topology_trial_id} is {trial.status}"
            )
    return blockers


def _topology_downstream_actions(operation: SkillGraphOperationRecord) -> list[dict[str, Any]]:
    subject_ids = [str(item) for item in operation.subject_skill_ids]
    output_ids = [str(item) for item in operation.output_skill_ids]
    edge_kinds = _graph_edge_kinds(operation.skill_graph_ir)
    actions: list[dict[str, Any]] = [
        {
            "operation": "record_topology_operation_applied",
            "status": "ready",
            "skill_graph_operation_id": str(operation.skill_graph_operation_id),
            "operation_kind": operation.operation_kind,
        }
    ]
    if edge_kinds:
        actions.append(
            {
                "operation": "materialize_skill_graph_edges",
                "status": "planned",
                "edge_kinds": edge_kinds,
                "edge_count": len(operation.skill_graph_ir.get("edges", [])),
            }
        )

    if operation.operation_kind == "improve":
        actions.extend(
            [
                {
                    "operation": "activate_successor_skill",
                    "status": "planned" if output_ids else "waiting_for_output_skill",
                    "skill_ids": output_ids,
                },
                {
                    "operation": "supersede_subject_skill",
                    "status": "planned" if subject_ids and output_ids else "waiting_for_skill_ids",
                    "subject_skill_ids": subject_ids,
                    "successor_skill_ids": output_ids,
                },
            ]
        )
    elif operation.operation_kind == "compose":
        actions.extend(
            [
                {
                    "operation": "activate_composed_skill",
                    "status": "planned" if output_ids else "waiting_for_output_skill",
                    "skill_ids": output_ids,
                },
                {
                    "operation": "route_components_to_composed_skill",
                    "status": "planned" if subject_ids and output_ids else "waiting_for_skill_ids",
                    "component_skill_ids": subject_ids,
                    "composed_skill_ids": output_ids,
                },
            ]
        )
    elif operation.operation_kind == "decompose":
        actions.extend(
            [
                {
                    "operation": "activate_successor_skills",
                    "status": "planned" if output_ids else "waiting_for_output_skill",
                    "skill_ids": output_ids,
                },
                {
                    "operation": "retire_or_demote_subject_skill",
                    "status": "planned" if subject_ids and output_ids else "waiting_for_skill_ids",
                    "subject_skill_ids": subject_ids,
                    "successor_skill_ids": output_ids,
                },
                {
                    "operation": "route_subject_intents_to_successors",
                    "status": "planned" if subject_ids and output_ids else "waiting_for_skill_ids",
                    "subject_skill_ids": subject_ids,
                    "successor_skill_ids": output_ids,
                },
            ]
        )
    else:
        actions.append(
            {
                "operation": "dispatch_topology_mutation",
                "status": "manual_review",
                "operation_kind": operation.operation_kind,
            }
        )
    return actions


def _graph_edge_kinds(skill_graph_ir: dict[str, Any]) -> list[str]:
    edge_kinds = {
        str(edge.get("edge_kind"))
        for edge in skill_graph_ir.get("edges", [])
        if isinstance(edge, dict) and edge.get("edge_kind")
    }
    return sorted(edge_kinds)
