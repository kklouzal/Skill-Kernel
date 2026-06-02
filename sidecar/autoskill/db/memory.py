from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

import asyncpg

from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace

MEMORY_QUARANTINE_STATUSES = {"pending", "approved", "rejected", "expired"}
CONTROL_FLOW_SOURCE_KINDS = {
    "memory",
    "skill",
    "broker",
    "tool",
    "user",
    "system",
    "external_skill_inventory",
}
CONTROL_FLOW_INFLUENCE_KINDS = {
    "retrieval",
    "tool_selection",
    "skill_selection",
    "mutation",
    "archive",
    "promotion",
    "rollback",
}


@dataclass(frozen=True)
class MemoryQuarantineRecord:
    quarantine_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_object_type: str
    source_object_id: UUID
    proposed_memory: dict[str, Any]
    taint: dict[str, Any]
    status: str
    scanner_findings: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> MemoryQuarantineRecord:
        return cls(
            quarantine_id=row["quarantine_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_object_type=row["source_object_type"],
            source_object_id=row["source_object_id"],
            proposed_memory=_json_dict(row["proposed_memory"]),
            taint=_json_dict(row["taint"]),
            status=row["status"],
            scanner_findings=_json_dict(row["scanner_findings"]),
            created_at=row["created_at"],
            decided_at=_row_get(row, "decided_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "quarantine_id": str(self.quarantine_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_object_type": self.source_object_type,
            "source_object_id": str(self.source_object_id),
            "proposed_memory": self.proposed_memory,
            "taint": self.taint,
            "status": self.status,
            "scanner_findings": self.scanner_findings,
            "created_at": self.created_at.isoformat(),
            "decided_at": _iso_or_none(self.decided_at),
        }


@dataclass(frozen=True)
class ControlFlowEventRecord:
    control_flow_event_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    run_id: str | None
    source_kind: str
    source_id: UUID | None
    influence_kind: str
    decision: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(
        cls,
        row: asyncpg.Record | dict[str, Any],
    ) -> ControlFlowEventRecord:
        return cls(
            control_flow_event_id=row["control_flow_event_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            run_id=_row_get(row, "run_id"),
            source_kind=row["source_kind"],
            source_id=_row_get(row, "source_id"),
            influence_kind=row["influence_kind"],
            decision=_json_dict(row["decision"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "control_flow_event_id": str(self.control_flow_event_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "run_id": self.run_id,
            "source_kind": self.source_kind,
            "source_id": str(self.source_id) if self.source_id else None,
            "influence_kind": self.influence_kind,
            "decision": self.decision,
            "created_at": self.created_at.isoformat(),
        }


class MemoryGovernanceStore(Protocol):
    async def quarantine_memory(
        self,
        *,
        workspace_key: str,
        source_object_type: str,
        source_object_id: UUID,
        proposed_memory: dict[str, Any],
        taint: dict[str, Any],
        scanner_findings: dict[str, Any],
    ) -> MemoryQuarantineRecord:
        """Record a derived memory as inactive until deterministic review approves it."""

    async def decide_memory_quarantine(
        self,
        *,
        workspace_key: str,
        quarantine_id: UUID,
        status: str,
        operator_id: str | None = None,
        rationale: str | None = None,
    ) -> MemoryQuarantineRecord | None:
        """Approve, reject, or expire a quarantined memory candidate."""

    async def get_memory_quarantine(
        self,
        *,
        workspace_key: str,
        quarantine_id: UUID,
    ) -> MemoryQuarantineRecord | None:
        """Fetch one quarantined memory candidate for trust-state checks."""

    async def list_memory_quarantine(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MemoryQuarantineRecord]:
        """List quarantined memory candidates for operator/control-plane review."""

    async def record_control_flow_event(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        influence_kind: str,
        decision: dict[str, Any],
        run_id: str | None = None,
        source_id: UUID | None = None,
    ) -> ControlFlowEventRecord:
        """Record that memory/skill/broker/tool context influenced a control decision."""

    async def list_control_flow_events(
        self,
        *,
        workspace_key: str,
        source_kind: str | None = None,
        influence_kind: str | None = None,
        limit: int = 100,
    ) -> list[ControlFlowEventRecord]:
        """List recent control-flow integrity events."""


class NullMemoryGovernanceStore:
    def __init__(self) -> None:
        self.quarantined: list[MemoryQuarantineRecord] = []
        self.control_flow_events: list[ControlFlowEventRecord] = []

    async def quarantine_memory(
        self,
        *,
        workspace_key: str,
        source_object_type: str,
        source_object_id: UUID,
        proposed_memory: dict[str, Any],
        taint: dict[str, Any],
        scanner_findings: dict[str, Any],
    ) -> MemoryQuarantineRecord:
        now = datetime.now(UTC)
        record = MemoryQuarantineRecord(
            quarantine_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            proposed_memory=proposed_memory,
            taint=taint,
            status="pending",
            scanner_findings=scanner_findings,
            created_at=now,
            decided_at=None,
        )
        self.quarantined.append(record)
        return record

    async def decide_memory_quarantine(
        self,
        *,
        workspace_key: str,
        quarantine_id: UUID,
        status: str,
        operator_id: str | None = None,
        rationale: str | None = None,
    ) -> MemoryQuarantineRecord | None:
        _validate_quarantine_status(status, allow_pending=False)
        for index, record in enumerate(self.quarantined):
            if record.workspace_key != workspace_key or record.quarantine_id != quarantine_id:
                continue
            updated = MemoryQuarantineRecord(
                quarantine_id=record.quarantine_id,
                workspace_id=record.workspace_id,
                workspace_key=record.workspace_key,
                source_object_type=record.source_object_type,
                source_object_id=record.source_object_id,
                proposed_memory=record.proposed_memory,
                taint=record.taint,
                status=status,
                scanner_findings={
                    **record.scanner_findings,
                    "decision": {
                        "operator_id": operator_id,
                        "rationale": rationale,
                    },
                },
                created_at=record.created_at,
                decided_at=datetime.now(UTC),
            )
            self.quarantined[index] = updated
            return updated
        return None

    async def get_memory_quarantine(
        self,
        *,
        workspace_key: str,
        quarantine_id: UUID,
    ) -> MemoryQuarantineRecord | None:
        for record in self.quarantined:
            if record.workspace_key == workspace_key and record.quarantine_id == quarantine_id:
                return record
        return None

    async def list_memory_quarantine(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MemoryQuarantineRecord]:
        if status is not None:
            _validate_quarantine_status(status)
        records = [
            record
            for record in self.quarantined
            if record.workspace_key == workspace_key
            and (status is None or record.status == status)
        ]
        return list(reversed(records))[:limit]

    async def record_control_flow_event(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        influence_kind: str,
        decision: dict[str, Any],
        run_id: str | None = None,
        source_id: UUID | None = None,
    ) -> ControlFlowEventRecord:
        _validate_control_flow(source_kind=source_kind, influence_kind=influence_kind)
        record = ControlFlowEventRecord(
            control_flow_event_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            run_id=run_id,
            source_kind=source_kind,
            source_id=source_id,
            influence_kind=influence_kind,
            decision=decision,
            created_at=datetime.now(UTC),
        )
        self.control_flow_events.append(record)
        return record

    async def list_control_flow_events(
        self,
        *,
        workspace_key: str,
        source_kind: str | None = None,
        influence_kind: str | None = None,
        limit: int = 100,
    ) -> list[ControlFlowEventRecord]:
        if source_kind is not None:
            _validate_control_flow_source(source_kind)
        if influence_kind is not None:
            _validate_control_flow_influence(influence_kind)
        records = [
            record
            for record in self.control_flow_events
            if record.workspace_key == workspace_key
            and (source_kind is None or record.source_kind == source_kind)
            and (influence_kind is None or record.influence_kind == influence_kind)
        ]
        return list(reversed(records))[:limit]


class AsyncpgMemoryGovernanceStore(AsyncpgPoolOwner):
    async def quarantine_memory(
        self,
        *,
        workspace_key: str,
        source_object_type: str,
        source_object_id: UUID,
        proposed_memory: dict[str, Any],
        taint: dict[str, Any],
        scanner_findings: dict[str, Any],
    ) -> MemoryQuarantineRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.memory_quarantine (
                  quarantine_id,
                  workspace_id,
                  source_object_type,
                  source_object_id,
                  proposed_memory,
                  taint,
                  scanner_findings
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb)
                RETURNING *
                """,
                workspace_id,
                source_object_type,
                source_object_id,
                _json(proposed_memory),
                _json(taint),
                _json(scanner_findings),
            )
        return MemoryQuarantineRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def decide_memory_quarantine(
        self,
        *,
        workspace_key: str,
        quarantine_id: UUID,
        status: str,
        operator_id: str | None = None,
        rationale: str | None = None,
    ) -> MemoryQuarantineRecord | None:
        _validate_quarantine_status(status, allow_pending=False)
        decision = {
            "status": status,
            "operator_id": operator_id,
            "rationale": rationale,
            "decided_at": datetime.now(UTC).isoformat(),
        }
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE autoskill.memory_quarantine mq
                SET status = $3,
                    scanner_findings = mq.scanner_findings
                      || jsonb_build_object('decision', $4::jsonb),
                    decided_at = now()
                FROM autoskill.workspaces w
                WHERE mq.workspace_id = w.workspace_id
                  AND w.external_key = $1
                  AND mq.quarantine_id = $2
                RETURNING mq.*
                """,
                workspace_key,
                quarantine_id,
                status,
                _json(decision),
            )
        if row is None:
            return None
        return MemoryQuarantineRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def get_memory_quarantine(
        self,
        *,
        workspace_key: str,
        quarantine_id: UUID,
    ) -> MemoryQuarantineRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT mq.*
                FROM autoskill.memory_quarantine mq
                JOIN autoskill.workspaces w ON w.workspace_id = mq.workspace_id
                WHERE w.external_key = $1
                  AND mq.quarantine_id = $2
                """,
                workspace_key,
                quarantine_id,
            )
        if row is None:
            return None
        return MemoryQuarantineRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def list_memory_quarantine(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MemoryQuarantineRecord]:
        if status is not None:
            _validate_quarantine_status(status)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT mq.*
                FROM autoskill.memory_quarantine mq
                JOIN autoskill.workspaces w ON w.workspace_id = mq.workspace_id
                WHERE w.external_key = $1
                  AND ($2::text IS NULL OR mq.status = $2)
                ORDER BY mq.created_at DESC, mq.quarantine_id DESC
                LIMIT $3
                """,
                workspace_key,
                status,
                limit,
            )
        return [
            MemoryQuarantineRecord.from_row({**dict(row), "workspace_key": workspace_key})
            for row in rows
        ]

    async def record_control_flow_event(
        self,
        *,
        workspace_key: str,
        source_kind: str,
        influence_kind: str,
        decision: dict[str, Any],
        run_id: str | None = None,
        source_id: UUID | None = None,
    ) -> ControlFlowEventRecord:
        _validate_control_flow(source_kind=source_kind, influence_kind=influence_kind)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.control_flow_events (
                  control_flow_event_id,
                  workspace_id,
                  run_id,
                  source_kind,
                  source_id,
                  influence_kind,
                  decision
                )
                VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
                """,
                workspace_id,
                run_id,
                source_kind,
                source_id,
                influence_kind,
                _json(decision),
            )
        return ControlFlowEventRecord.from_row({**dict(row), "workspace_key": workspace_key})

    async def list_control_flow_events(
        self,
        *,
        workspace_key: str,
        source_kind: str | None = None,
        influence_kind: str | None = None,
        limit: int = 100,
    ) -> list[ControlFlowEventRecord]:
        if source_kind is not None:
            _validate_control_flow_source(source_kind)
        if influence_kind is not None:
            _validate_control_flow_influence(influence_kind)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cfe.*
                FROM autoskill.control_flow_events cfe
                JOIN autoskill.workspaces w ON w.workspace_id = cfe.workspace_id
                WHERE w.external_key = $1
                  AND ($2::text IS NULL OR cfe.source_kind = $2)
                  AND ($3::text IS NULL OR cfe.influence_kind = $3)
                ORDER BY cfe.created_at DESC, cfe.control_flow_event_id DESC
                LIMIT $4
                """,
                workspace_key,
                source_kind,
                influence_kind,
                limit,
            )
        return [
            ControlFlowEventRecord.from_row({**dict(row), "workspace_key": workspace_key})
            for row in rows
        ]


def _validate_quarantine_status(status: str, *, allow_pending: bool = True) -> None:
    allowed = (
        MEMORY_QUARANTINE_STATUSES
        if allow_pending
        else MEMORY_QUARANTINE_STATUSES - {"pending"}
    )
    if status not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"memory quarantine status must be one of: {allowed_text}")


def _validate_control_flow(
    *,
    source_kind: str,
    influence_kind: str,
) -> None:
    _validate_control_flow_source(source_kind)
    _validate_control_flow_influence(influence_kind)


def _validate_control_flow_source(source_kind: str) -> None:
    if source_kind not in CONTROL_FLOW_SOURCE_KINDS:
        allowed = ", ".join(sorted(CONTROL_FLOW_SOURCE_KINDS))
        raise ValueError(f"control-flow source_kind must be one of: {allowed}")


def _validate_control_flow_influence(influence_kind: str) -> None:
    if influence_kind not in CONTROL_FLOW_INFLUENCE_KINDS:
        allowed = ", ".join(sorted(CONTROL_FLOW_INFLUENCE_KINDS))
        raise ValueError(f"control-flow influence_kind must be one of: {allowed}")


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
