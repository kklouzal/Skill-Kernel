from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.enums import EvidenceMaturity
from autoskill.core.hashing import sha256_json
from autoskill.db.pool import AsyncpgPoolOwner


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    source_event_id: UUID | None
    evidence_hash: str
    kind: str
    maturity: str
    trust: str
    taint: list[str]
    summary: str
    payload: dict[str, Any]
    created_at: datetime
    revoked_at: datetime | None = None

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> EvidenceRecord:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return cls(
            evidence_id=row["evidence_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            source_event_id=_row_get(row, "source_event_id"),
            evidence_hash=row["evidence_hash"],
            kind=row["kind"],
            maturity=row["maturity"],
            trust=row["trust"],
            taint=list(row["taint"]),
            summary=row["summary"],
            payload=payload,
            created_at=row["created_at"],
            revoked_at=_row_get(row, "revoked_at"),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "evidence_id": str(self.evidence_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "source_event_id": str(self.source_event_id) if self.source_event_id else None,
            "evidence_hash": self.evidence_hash,
            "kind": self.kind,
            "maturity": self.maturity,
            "trust": self.trust,
            "taint": self.taint,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
        }


@dataclass(frozen=True)
class EvidenceDeriveResult:
    scanned: int
    created: int
    duplicate: int
    evidence: list[EvidenceRecord]


class EvidenceStore(Protocol):
    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        """Create observed evidence items from already-redacted raw events."""

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        """List recent non-revoked evidence."""


class NullEvidenceStore:
    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        return EvidenceDeriveResult(scanned=0, created=0, duplicate=0, evidence=[])

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        return []


class AsyncpgEvidenceStore(AsyncpgPoolOwner):
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        super().__init__(database_url, statement_timeout_ms=statement_timeout_ms)

    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        pool = await self._get_pool()
        evidence: list[EvidenceRecord] = []
        duplicate = 0
        async with pool.acquire() as conn, conn.transaction():
            events = await conn.fetch(
                """
                SELECT e.*, w.external_key AS workspace_key
                FROM autoskill.raw_events e
                JOIN autoskill.workspaces w USING (workspace_id)
                LEFT JOIN autoskill.evidence_items i
                  ON i.source_event_id = e.event_id
                 AND i.kind = 'event_observation'
                WHERE i.evidence_id IS NULL
                  AND ($1::text IS NULL OR w.external_key = $1)
                ORDER BY e.occurred_at ASC
                LIMIT $2
                FOR UPDATE OF e SKIP LOCKED
                """,
                workspace_key,
                limit,
            )
            for event in events:
                inserted = await _insert_event_evidence(conn, event)
                if inserted is None:
                    duplicate += 1
                    continue
                evidence.append(inserted)

        return EvidenceDeriveResult(
            scanned=len(events),
            created=len(evidence),
            duplicate=duplicate,
            evidence=evidence,
        )

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT i.*, w.external_key AS workspace_key
                FROM autoskill.evidence_items i
                JOIN autoskill.workspaces w USING (workspace_id)
                WHERE i.revoked_at IS NULL
                  AND ($1::text IS NULL OR w.external_key = $1)
                ORDER BY i.created_at DESC
                LIMIT $2
                """,
                workspace_key,
                limit,
            )
            return [EvidenceRecord.from_row(row) for row in rows]


async def _insert_event_evidence(
    conn: asyncpg.Connection,
    event: asyncpg.Record,
) -> EvidenceRecord | None:
    payload = _evidence_payload(event)
    evidence_hash = sha256_json(
        {
            "kind": "event_observation",
            "workspace_id": str(event["workspace_id"]),
            "source_event_id": str(event["event_id"]),
            "payload_hash": event["payload_hash"],
        }
    )
    row = await conn.fetchrow(
        """
        INSERT INTO autoskill.evidence_items (
          evidence_id,
          workspace_id,
          source_event_id,
          evidence_hash,
          kind,
          maturity,
          trust,
          taint,
          summary,
          payload
        )
        VALUES (
          gen_random_uuid(), $1, $2, $3, 'event_observation', $4, $5, $6, $7, $8::jsonb
        )
        ON CONFLICT (workspace_id, evidence_hash) DO NOTHING
        RETURNING *
        """,
        event["workspace_id"],
        event["event_id"],
        evidence_hash,
        str(EvidenceMaturity.OBSERVED),
        event["trust"],
        event["taint"],
        _summary(event),
        _json(payload),
    )
    if row is None:
        return None

    await conn.execute(
        """
        INSERT INTO autoskill.provenance_edges (
          provenance_edge_id,
          workspace_id,
          source_kind,
          source_id,
          derived_kind,
          derived_id,
          relation
        )
        VALUES (gen_random_uuid(), $1, 'raw_event', $2, 'evidence_item', $3, 'derived_from')
        ON CONFLICT DO NOTHING
        """,
        event["workspace_id"],
        event["event_id"],
        row["evidence_id"],
    )
    return EvidenceRecord.from_row({**dict(row), "workspace_key": event["workspace_key"]})


def _summary(event: asyncpg.Record) -> str:
    session = event["session_id"] or "unknown-session"
    turn = event["turn_id"] or "unknown-turn"
    return (
        f"Observed redacted {event['event_type']} event from {event['source']} "
        f"in {session}/{turn}."
    )


def _evidence_payload(event: asyncpg.Record) -> dict[str, Any]:
    event_payload = event["payload"]
    if isinstance(event_payload, str):
        event_payload = json.loads(event_payload)
    return {
        "schema_version": 1,
        "source_event": {
            "event_id": str(event["event_id"]),
            "event_type": event["event_type"],
            "occurred_at": event["occurred_at"].isoformat(),
            "session_id": event["session_id"],
            "turn_id": event["turn_id"],
            "source": event["source"],
            "redaction_state": event["redaction_state"],
            "payload_hash": event["payload_hash"],
            "plugin_version": event["plugin_version"],
            "openclaw_version": event["openclaw_version"],
        },
        "redacted_payload": event_payload,
    }


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None
