from __future__ import annotations

import json
from typing import Protocol

import asyncpg

from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


class AuditStore(Protocol):
    async def append_record(self, record: AuditRecord, *, workspace_key: str) -> AuditRecord:
        """Append a sealed audit record to the workspace hash chain."""

    async def list_recent(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """Return recent audit records newest-first."""

    async def verify_chain(self, *, workspace_key: str | None = None, limit: int = 1000) -> bool:
        """Verify a bounded audit hash chain."""


class NullAuditStore:
    async def append_record(self, record: AuditRecord, *, workspace_key: str) -> AuditRecord:
        return record.sealed()

    async def list_recent(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        return []

    async def verify_chain(self, *, workspace_key: str | None = None, limit: int = 1000) -> bool:
        return True


class AsyncpgAuditStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def append_record(self, record: AuditRecord, *, workspace_key: str) -> AuditRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            previous_hash = await conn.fetchval(
                """
                SELECT audit_hash
                FROM autoskill.audit_records
                WHERE workspace_id = $1
                ORDER BY occurred_at DESC, audit_id DESC
                LIMIT 1
                FOR UPDATE
                """,
                workspace_id,
            )
            sealed = record.model_copy(update={"previous_hash": previous_hash}).sealed()
            await conn.execute(
                """
                INSERT INTO autoskill.audit_records (
                  audit_id,
                  workspace_id,
                  occurred_at,
                  action,
                  actor,
                  subject_type,
                  subject_id,
                  previous_hash,
                  audit_hash,
                  details
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                """,
                sealed.audit_id,
                workspace_id,
                sealed.occurred_at,
                sealed.action,
                sealed.actor,
                sealed.subject_type,
                sealed.subject_id,
                sealed.previous_hash,
                sealed.audit_hash,
                json.dumps(sealed.details, sort_keys=True, separators=(",", ":")),
            )
            return sealed

    async def list_recent(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ar.*
                FROM autoskill.audit_records ar
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE ($1::text IS NULL OR w.external_key = $1)
                ORDER BY ar.occurred_at DESC, ar.audit_id DESC
                LIMIT $2
                """,
                workspace_key,
                max(1, min(limit, 1000)),
            )
            return [_record_from_row(row) for row in rows]

    async def verify_chain(self, *, workspace_key: str | None = None, limit: int = 1000) -> bool:
        records = await self.list_recent(workspace_key=workspace_key, limit=limit)
        return verify_hash_chain(list(reversed(records)))


def _record_from_row(row: asyncpg.Record) -> AuditRecord:
    details = row["details"]
    if isinstance(details, str):
        details = json.loads(details)
    return AuditRecord(
        audit_id=row["audit_id"],
        occurred_at=row["occurred_at"],
        action=row["action"],
        actor=row["actor"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        previous_hash=row["previous_hash"],
        details=details,
        audit_hash=row["audit_hash"],
    )
