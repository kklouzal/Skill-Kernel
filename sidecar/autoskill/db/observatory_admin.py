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
class AdminLiveEventRecord:
    seq: int
    kind: str
    component_id: str | None
    trace_id: str | None
    object_type: str | None
    object_id: str | None
    payload: dict[str, Any]
    redaction_level: str
    created_at: datetime
    delivered_hint: bool

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> AdminLiveEventRecord:
        return cls(
            seq=int(row["seq"]),
            kind=row["kind"],
            component_id=_row_get(row, "component_id"),
            trace_id=_row_get(row, "trace_id"),
            object_type=_row_get(row, "object_type"),
            object_id=_row_get(row, "object_id"),
            payload=_json_dict(row["payload"]),
            redaction_level=row["redaction_level"],
            created_at=row["created_at"],
            delivered_hint=bool(row["delivered_hint"]),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "skillkernel.observatory.live-event.v1",
            "seq": self.seq,
            "sent_at": self.created_at.isoformat(),
            "event_type": self.kind,
            "kind": self.kind,
            "component_id": self.component_id,
            "trace_id": self.trace_id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "payload": self.payload,
            "redaction_level": self.redaction_level,
            "requires_snapshot_reload": self.kind == "read_model_invalidated",
        }


@dataclass(frozen=True)
class AdminActionAuditRecord:
    action_id: UUID
    actor_id: str
    actor_roles: list[str]
    action_kind: str
    target_type: str
    target_id: str
    idempotency_key: str
    request_payload_redacted: dict[str, Any]
    reason: str
    result: str
    linked_job_id: UUID | None
    linked_audit_id: UUID | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> AdminActionAuditRecord:
        return cls(
            action_id=row["action_id"],
            actor_id=row["actor_id"],
            actor_roles=list(row["actor_roles"]),
            action_kind=row["action_kind"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            idempotency_key=row["idempotency_key"],
            request_payload_redacted=_json_dict(row["request_payload_redacted"]),
            reason=row["reason"],
            result=row["result"],
            linked_job_id=_row_get(row, "linked_job_id"),
            linked_audit_id=_row_get(row, "linked_audit_id"),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "skillkernel.observatory.admin-action-audit.v1",
            "object_type": "admin_action",
            "object_id": str(self.action_id),
            "action_id": str(self.action_id),
            "actor_id": self.actor_id,
            "actor_roles": self.actor_roles,
            "action_kind": self.action_kind,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "idempotency_key": self.idempotency_key,
            "request_payload_redacted": self.request_payload_redacted,
            "reason": self.reason,
            "result": self.result,
            "linked_job_id": str(self.linked_job_id) if self.linked_job_id else None,
            "linked_audit_id": str(self.linked_audit_id) if self.linked_audit_id else None,
            "created_at": self.created_at.isoformat(),
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
        }


@dataclass(frozen=True)
class AdminComparisonRecord:
    comparison_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    actor_id: str
    comparison_kind: str
    left_selector: dict[str, Any]
    right_selector: dict[str, Any]
    result_summary: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> AdminComparisonRecord:
        return cls(
            comparison_id=row["comparison_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            actor_id=row["actor_id"],
            comparison_kind=row["comparison_kind"],
            left_selector=_json_dict(row["left_selector"]),
            right_selector=_json_dict(row["right_selector"]),
            result_summary=_json_dict(row["result_summary"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "skillkernel.observatory.comparison.v1",
            "object_type": "baseline_comparison",
            "object_id": str(self.comparison_id),
            "comparison_id": str(self.comparison_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "actor_id": self.actor_id,
            "comparison_kind": self.comparison_kind,
            "left": self.left_selector,
            "right": self.right_selector,
            "result_summary": self.result_summary,
            "differences": self.result_summary.get("differences", []),
            "mutates_policy": False,
            "created_at": self.created_at.isoformat(),
            "title": f"Baseline comparison {self.comparison_id}",
            "summary": str(
                self.result_summary.get(
                    "summary",
                    "Bounded Observatory baseline comparison.",
                )
            ),
            "details_url": f"/admin/comparisons/{self.comparison_id}",
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
            },
        }


@dataclass(frozen=True)
class AdminDiagnosticBundleRecord:
    bundle_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    actor_id: str
    scope: dict[str, Any]
    redaction_level: str
    manifest: dict[str, Any]
    storage_uri: str
    created_at: datetime
    expires_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> AdminDiagnosticBundleRecord:
        return cls(
            bundle_id=row["bundle_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            actor_id=row["actor_id"],
            scope=_json_dict(row["scope"]),
            redaction_level=row["redaction_level"],
            manifest=_json_dict(row["manifest"]),
            storage_uri=row["storage_uri"],
            created_at=row["created_at"],
            expires_at=_row_get(row, "expires_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "skillkernel.observatory.diagnostic-bundle.v1",
            "object_type": "diagnostic_bundle",
            "object_id": str(self.bundle_id),
            "bundle_id": str(self.bundle_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "actor_id": self.actor_id,
            "scope": self.scope,
            "redaction_level": self.redaction_level,
            "manifest": self.manifest,
            "storage_uri": self.storage_uri,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "title": f"Diagnostic bundle {self.bundle_id}",
            "summary": "Persisted redacted diagnostic bundle descriptor.",
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_level": self.redaction_level,
            },
        }


class ObservatoryAdminStore(Protocol):
    async def append_live_event(
        self,
        *,
        kind: str,
        component_id: str | None = None,
        trace_id: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        payload: dict[str, Any] | None = None,
        redaction_level: str = "default",
    ) -> AdminLiveEventRecord:
        """Persist one UI-safe admin live event."""

    async def list_live_events(
        self,
        *,
        after_seq: int | None = None,
        limit: int = 50,
    ) -> list[AdminLiveEventRecord]:
        """Return bounded UI-safe live events newer than the given outbox sequence."""

    async def record_action_audit(
        self,
        *,
        actor_id: str,
        actor_roles: list[str],
        action_kind: str,
        target_type: str,
        target_id: str,
        idempotency_key: str,
        request_payload_redacted: dict[str, Any],
        reason: str,
        result: str,
        linked_audit_id: UUID | None = None,
        linked_job_id: UUID | None = None,
    ) -> AdminActionAuditRecord:
        """Persist a content-safe Observatory operator action audit row."""

    async def list_comparisons(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[AdminComparisonRecord]:
        """Return saved baseline comparisons."""

    async def create_comparison(
        self,
        *,
        workspace_key: str,
        actor_id: str,
        comparison_kind: str,
        left_selector: dict[str, Any],
        right_selector: dict[str, Any],
        result_summary: dict[str, Any],
    ) -> AdminComparisonRecord:
        """Persist one read-only comparison result."""

    async def get_comparison(
        self,
        *,
        comparison_id: UUID,
        workspace_key: str | None = None,
    ) -> AdminComparisonRecord | None:
        """Fetch one saved baseline comparison."""

    async def create_diagnostic_bundle(
        self,
        *,
        workspace_key: str,
        actor_id: str,
        scope: dict[str, Any],
        redaction_level: str,
        manifest: dict[str, Any],
        storage_uri: str,
    ) -> AdminDiagnosticBundleRecord:
        """Persist one redacted diagnostic bundle descriptor."""

    async def get_diagnostic_bundle(
        self,
        *,
        bundle_id: UUID,
        workspace_key: str | None = None,
    ) -> AdminDiagnosticBundleRecord | None:
        """Fetch one diagnostic bundle descriptor."""


class NullObservatoryAdminStore:
    def __init__(self) -> None:
        self.live_events: list[AdminLiveEventRecord] = []
        self.actions: list[AdminActionAuditRecord] = []
        self.comparisons: list[AdminComparisonRecord] = []
        self.bundles: list[AdminDiagnosticBundleRecord] = []

    async def append_live_event(
        self,
        *,
        kind: str,
        component_id: str | None = None,
        trace_id: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        payload: dict[str, Any] | None = None,
        redaction_level: str = "default",
    ) -> AdminLiveEventRecord:
        record = AdminLiveEventRecord(
            seq=len(self.live_events) + 1,
            kind=kind,
            component_id=component_id,
            trace_id=trace_id,
            object_type=object_type,
            object_id=object_id,
            payload=payload or {},
            redaction_level=redaction_level,
            created_at=datetime.now(UTC),
            delivered_hint=False,
        )
        self.live_events.append(record)
        return record

    async def list_live_events(
        self,
        *,
        after_seq: int | None = None,
        limit: int = 50,
    ) -> list[AdminLiveEventRecord]:
        bounded_limit = max(1, min(limit, 500))
        records = self.live_events
        if after_seq is not None:
            records = [record for record in records if record.seq > after_seq]
        return records[:bounded_limit]

    async def record_action_audit(
        self,
        *,
        actor_id: str,
        actor_roles: list[str],
        action_kind: str,
        target_type: str,
        target_id: str,
        idempotency_key: str,
        request_payload_redacted: dict[str, Any],
        reason: str,
        result: str,
        linked_audit_id: UUID | None = None,
        linked_job_id: UUID | None = None,
    ) -> AdminActionAuditRecord:
        for record in self.actions:
            if (
                record.actor_id == actor_id
                and record.action_kind == action_kind
                and record.target_type == target_type
                and record.target_id == target_id
                and record.idempotency_key == idempotency_key
            ):
                return record
        record = AdminActionAuditRecord(
            action_id=uuid4(),
            actor_id=actor_id,
            actor_roles=sorted(set(actor_roles)),
            action_kind=action_kind,
            target_type=target_type,
            target_id=target_id,
            idempotency_key=idempotency_key,
            request_payload_redacted=request_payload_redacted,
            reason=reason,
            result=result,
            linked_job_id=linked_job_id,
            linked_audit_id=linked_audit_id,
            created_at=datetime.now(UTC),
        )
        self.actions.append(record)
        return record

    async def list_comparisons(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[AdminComparisonRecord]:
        records = self.comparisons
        if workspace_key is not None:
            records = [record for record in records if record.workspace_key == workspace_key]
        return list(reversed(records))[: max(1, min(limit, 500))]

    async def create_comparison(
        self,
        *,
        workspace_key: str,
        actor_id: str,
        comparison_kind: str,
        left_selector: dict[str, Any],
        right_selector: dict[str, Any],
        result_summary: dict[str, Any],
    ) -> AdminComparisonRecord:
        record = AdminComparisonRecord(
            comparison_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            actor_id=actor_id,
            comparison_kind=comparison_kind,
            left_selector=left_selector,
            right_selector=right_selector,
            result_summary=result_summary,
            created_at=datetime.now(UTC),
        )
        self.comparisons.append(record)
        return record

    async def get_comparison(
        self,
        *,
        comparison_id: UUID,
        workspace_key: str | None = None,
    ) -> AdminComparisonRecord | None:
        for record in reversed(self.comparisons):
            if record.comparison_id == comparison_id and (
                workspace_key is None or record.workspace_key == workspace_key
            ):
                return record
        return None

    async def create_diagnostic_bundle(
        self,
        *,
        workspace_key: str,
        actor_id: str,
        scope: dict[str, Any],
        redaction_level: str,
        manifest: dict[str, Any],
        storage_uri: str,
    ) -> AdminDiagnosticBundleRecord:
        bundle_id = uuid4()
        record = AdminDiagnosticBundleRecord(
            bundle_id=bundle_id,
            workspace_id=None,
            workspace_key=workspace_key,
            actor_id=actor_id,
            scope=scope,
            redaction_level=redaction_level,
            manifest=manifest,
            storage_uri=storage_uri or f"memory://observatory/diagnostic-bundles/{bundle_id}",
            created_at=datetime.now(UTC),
            expires_at=None,
        )
        self.bundles.append(record)
        return record

    async def get_diagnostic_bundle(
        self,
        *,
        bundle_id: UUID,
        workspace_key: str | None = None,
    ) -> AdminDiagnosticBundleRecord | None:
        for record in reversed(self.bundles):
            if record.bundle_id == bundle_id and (
                workspace_key is None or record.workspace_key == workspace_key
            ):
                return record
        return None


class AsyncpgObservatoryAdminStore(AsyncpgPoolOwner):
    async def append_live_event(
        self,
        *,
        kind: str,
        component_id: str | None = None,
        trace_id: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        payload: dict[str, Any] | None = None,
        redaction_level: str = "default",
    ) -> AdminLiveEventRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.admin_live_event_outbox (
                  kind,
                  component_id,
                  trace_id,
                  object_type,
                  object_id,
                  payload,
                  redaction_level
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                RETURNING *
                """,
                kind,
                component_id,
                trace_id,
                object_type,
                object_id,
                _json(payload or {}),
                redaction_level,
            )
        return AdminLiveEventRecord.from_row(row)

    async def list_live_events(
        self,
        *,
        after_seq: int | None = None,
        limit: int = 50,
    ) -> list[AdminLiveEventRecord]:
        bounded_limit = max(1, min(limit, 500))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM autoskill.admin_live_event_outbox
                WHERE ($1::bigint IS NULL OR seq > $1)
                ORDER BY seq ASC
                LIMIT $2
                """,
                after_seq,
                bounded_limit,
            )
        return [AdminLiveEventRecord.from_row(row) for row in rows]

    async def record_action_audit(
        self,
        *,
        actor_id: str,
        actor_roles: list[str],
        action_kind: str,
        target_type: str,
        target_id: str,
        idempotency_key: str,
        request_payload_redacted: dict[str, Any],
        reason: str,
        result: str,
        linked_audit_id: UUID | None = None,
        linked_job_id: UUID | None = None,
    ) -> AdminActionAuditRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.admin_action_audit (
                  actor_id,
                  actor_roles,
                  action_kind,
                  target_type,
                  target_id,
                  idempotency_key,
                  request_payload_redacted,
                  reason,
                  result,
                  linked_job_id,
                  linked_audit_id
                )
                VALUES (
                  $1,
                  $2::text[],
                  $3,
                  $4,
                  $5,
                  $6,
                  $7::jsonb,
                  $8,
                  $9,
                  $10,
                  $11
                )
                ON CONFLICT (
                  actor_id,
                  action_kind,
                  target_type,
                  target_id,
                  idempotency_key
                )
                DO UPDATE SET
                  linked_audit_id = COALESCE(
                    autoskill.admin_action_audit.linked_audit_id,
                    EXCLUDED.linked_audit_id
                  ),
                  linked_job_id = COALESCE(
                    autoskill.admin_action_audit.linked_job_id,
                    EXCLUDED.linked_job_id
                  )
                RETURNING *
                """,
                actor_id,
                sorted(set(actor_roles)),
                action_kind,
                target_type,
                target_id,
                idempotency_key,
                _json(request_payload_redacted),
                reason,
                result,
                linked_job_id,
                linked_audit_id,
            )
        return AdminActionAuditRecord.from_row(row)

    async def list_comparisons(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[AdminComparisonRecord]:
        bounded_limit = max(1, min(limit, 500))
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT acr.*, w.external_key AS workspace_key
                FROM autoskill.admin_comparison_runs acr
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                ORDER BY acr.created_at DESC, acr.comparison_id DESC
                LIMIT $2
                """,
                workspace_key,
                bounded_limit,
            )
        return [AdminComparisonRecord.from_row(row) for row in rows]

    async def create_comparison(
        self,
        *,
        workspace_key: str,
        actor_id: str,
        comparison_kind: str,
        left_selector: dict[str, Any],
        right_selector: dict[str, Any],
        result_summary: dict[str, Any],
    ) -> AdminComparisonRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.admin_comparison_runs (
                  workspace_id,
                  actor_id,
                  comparison_kind,
                  left_selector,
                  right_selector,
                  result_summary
                )
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb)
                RETURNING *, $7::text AS workspace_key
                """,
                workspace_id,
                actor_id,
                comparison_kind,
                _json(left_selector),
                _json(right_selector),
                _json(result_summary),
                workspace_key,
            )
        return AdminComparisonRecord.from_row(row)

    async def get_comparison(
        self,
        *,
        comparison_id: UUID,
        workspace_key: str | None = None,
    ) -> AdminComparisonRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT acr.*, w.external_key AS workspace_key
                FROM autoskill.admin_comparison_runs acr
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE acr.comparison_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                comparison_id,
                workspace_key,
            )
        return AdminComparisonRecord.from_row(row) if row else None

    async def create_diagnostic_bundle(
        self,
        *,
        workspace_key: str,
        actor_id: str,
        scope: dict[str, Any],
        redaction_level: str,
        manifest: dict[str, Any],
        storage_uri: str,
    ) -> AdminDiagnosticBundleRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.admin_diagnostic_bundles (
                  workspace_id,
                  actor_id,
                  scope,
                  redaction_level,
                  manifest,
                  storage_uri
                )
                VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, $6)
                RETURNING *, $7::text AS workspace_key
                """,
                workspace_id,
                actor_id,
                _json(scope),
                redaction_level,
                _json(manifest),
                storage_uri,
                workspace_key,
            )
        return AdminDiagnosticBundleRecord.from_row(row)

    async def get_diagnostic_bundle(
        self,
        *,
        bundle_id: UUID,
        workspace_key: str | None = None,
    ) -> AdminDiagnosticBundleRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT adb.*, w.external_key AS workspace_key
                FROM autoskill.admin_diagnostic_bundles adb
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE adb.bundle_id = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                bundle_id,
                workspace_key,
            )
        return AdminDiagnosticBundleRecord.from_row(row) if row else None


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
