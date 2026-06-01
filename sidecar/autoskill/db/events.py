from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import asyncpg

from autoskill.core.events import EventEnvelope


@dataclass(frozen=True)
class EventIngestSummary:
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0


class EventStore(Protocol):
    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        """Persist already-redacted events idempotently."""


class NullEventStore:
    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        return EventIngestSummary(accepted=len(events))


class AsyncpgEventStore:
    def __init__(self, database_url: str, *, statement_timeout_ms: int = 30_000) -> None:
        self._database_url = database_url
        self._statement_timeout_ms = statement_timeout_ms
        self._pool: asyncpg.Pool | None = None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._database_url,
                server_settings={"statement_timeout": str(self._statement_timeout_ms)},
            )
        return self._pool

    async def ingest_events(self, events: Sequence[EventEnvelope]) -> EventIngestSummary:
        if not events:
            return EventIngestSummary()

        pool = await self._get_pool()
        accepted = 0
        duplicate = 0

        async with pool.acquire() as conn, conn.transaction():
            workspace_ids: dict[str, UUID] = {}
            for event in events:
                workspace_id = workspace_ids.get(event.workspace_id)
                if workspace_id is None:
                    workspace_id = await _ensure_workspace(conn, event.workspace_id)
                    workspace_ids[event.workspace_id] = workspace_id

                inserted = await _insert_event(conn, workspace_id, event)
                if inserted:
                    accepted += 1
                else:
                    duplicate += 1

        return EventIngestSummary(accepted=accepted, duplicate=duplicate)


async def _ensure_workspace(conn: asyncpg.Connection, external_key: str) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO autoskill.workspaces (workspace_id, external_key)
        VALUES (gen_random_uuid(), $1)
        ON CONFLICT (external_key) DO UPDATE
        SET external_key = EXCLUDED.external_key
        RETURNING workspace_id
        """,
        external_key,
    )


async def _insert_event(conn: asyncpg.Connection, workspace_id: UUID, event: EventEnvelope) -> bool:
    event_id = await conn.fetchval(
        """
        INSERT INTO autoskill.raw_events (
          event_id,
          workspace_id,
          session_id,
          turn_id,
          event_type,
          occurred_at,
          source,
          trust,
          taint,
          redaction_state,
          payload_hash,
          payload,
          plugin_version,
          openclaw_version
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13, $14)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
        """,
        event.event_id,
        workspace_id,
        event.session_id,
        event.turn_id,
        event.event_type,
        event.occurred_at,
        event.source,
        str(event.trust),
        event.taint,
        str(event.redaction_state),
        event.payload_hash,
        json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
        event.plugin_version,
        event.openclaw_version,
    )
    return event_id is not None
