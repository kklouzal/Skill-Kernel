#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sidecar"))

from autoskill.api.app import create_app
from autoskill.core.config import get_settings
from autoskill.db.audit import NullAuditStore
from autoskill.db.observatory_admin import AsyncpgObservatoryAdminStore


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real-Postgres Observatory live-stream smoke. The smoke verifies "
            "that timestamp-based snapshot sequence values do not suppress later "
            "admin_live_event_outbox deltas."
        )
    )
    parser.add_argument("--database-url", default=_default_database_url())
    parser.add_argument("--workspace-id", default="dev-01")
    parser.add_argument("--event-timeout-seconds", type=float, default=7.0)
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Assume migrations have already been applied.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.skip_migrate:
        await _apply_migration(args.database_url)
    os.environ["AUTOSKILL_DATABASE_URL"] = args.database_url
    get_settings.cache_clear()
    settings = get_settings()
    auth = settings.web_admin_token or settings.control_token
    authorization = f"Bearer {auth}" if auth else None
    smoke_id = f"observatory-live-smoke-{uuid4()}"
    store = AsyncpgObservatoryAdminStore(
        args.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    try:
        await _delete_smoke_rows(args.database_url, smoke_id)
        stale_event = await store.append_live_event(
            kind="component_health_changed",
            component_id="scheduler_jobs",
            object_type="observatory_live_smoke",
            object_id=f"{smoke_id}:stale",
            payload={"health": "degraded", "smoke_id": smoke_id, "phase": "stale"},
        )
        app = create_app(
            audit_store=NullAuditStore(),
            observatory_admin_store=store,
        )
        route = _routes(app)[("/admin/live-sse", "GET")]
        response = await route.endpoint(
            authorization=authorization,
            workspace_id=args.workspace_id,
            last_seq=None,
        )
        try:
            snapshot_event, snapshot_payload = await _next_sse_frame(response.body_iterator)
            live_event = await store.append_live_event(
                kind="component_health_changed",
                component_id="observatory_admin",
                object_type="observatory_live_smoke",
                object_id=f"{smoke_id}:live",
                payload={"health": "degraded", "smoke_id": smoke_id, "phase": "live"},
            )
            live_event_name, live_payload = await _wait_for_smoke_event(
                response.body_iterator,
                smoke_id=smoke_id,
                timeout_seconds=args.event_timeout_seconds,
            )
        finally:
            await response.body_iterator.aclose()
        _assert_smoke(
            snapshot_event=snapshot_event,
            snapshot_payload=snapshot_payload,
            stale_seq=stale_event.seq,
            live_event_name=live_event_name,
            live_payload=live_payload,
            live_seq=live_event.seq,
            smoke_id=smoke_id,
        )
        return _summarize_smoke(
            workspace_id=args.workspace_id,
            smoke_id=smoke_id,
            snapshot_payload=snapshot_payload,
            stale_seq=stale_event.seq,
            live_payload=live_payload,
            live_seq=live_event.seq,
        )
    finally:
        await _delete_smoke_rows(args.database_url, smoke_id)
        await store.close()
        get_settings.cache_clear()


def _assert_smoke(
    *,
    snapshot_event: str,
    snapshot_payload: dict[str, Any],
    stale_seq: int,
    live_event_name: str,
    live_payload: dict[str, Any],
    live_seq: int,
    smoke_id: str,
) -> None:
    if snapshot_event != "snapshot":
        raise SystemExit(f"expected first SSE event to be snapshot, got {snapshot_event!r}")
    if snapshot_payload.get("event_type") != "snapshot":
        raise SystemExit("snapshot frame did not carry event_type=snapshot")
    if int(snapshot_payload.get("cursor_seq", -1)) < stale_seq:
        raise SystemExit("snapshot cursor did not fence pre-existing outbox rows")
    if live_event_name != "component_health_changed":
        raise SystemExit(f"expected live outbox delta, got {live_event_name!r}")
    if live_payload.get("event_type") != "component_health_changed":
        raise SystemExit("live frame did not carry the persisted event type")
    if int(live_payload.get("seq", -1)) != live_seq:
        raise SystemExit("live frame did not preserve the outbox event sequence")
    if int(live_payload.get("cursor_seq", -1)) != live_seq:
        raise SystemExit("live frame did not expose a reconnect-safe outbox cursor")
    payload = live_payload.get("payload")
    if not isinstance(payload, dict) or payload.get("smoke_id") != smoke_id:
        raise SystemExit("live frame did not replay the smoke event payload")


def _summarize_smoke(
    *,
    workspace_id: str,
    smoke_id: str,
    snapshot_payload: dict[str, Any],
    stale_seq: int,
    live_payload: dict[str, Any],
    live_seq: int,
) -> dict[str, Any]:
    return {
        "schema": "autoskill.observatory-live-smoke.v1",
        "ok": True,
        "workspace_id": workspace_id,
        "smoke_id": smoke_id,
        "snapshot_seq": snapshot_payload["seq"],
        "snapshot_cursor_seq": snapshot_payload["cursor_seq"],
        "stale_outbox_seq": stale_seq,
        "live_outbox_seq": live_seq,
        "live_event_type": live_payload["event_type"],
        "raw_vault_exposure": False,
        "runtime_skill_writes": False,
        "plugin_activation": False,
        "autonomous_apply": False,
        "live_openclaw_mutation": False,
    }


async def _wait_for_smoke_event(
    frames: AsyncIterator[str],
    *,
    smoke_id: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise SystemExit("timed out waiting for persisted outbox event")
        event_name, payload = await asyncio.wait_for(_next_sse_frame(frames), timeout=remaining)
        body = payload.get("payload")
        if isinstance(body, dict) and body.get("smoke_id") == smoke_id:
            return event_name, payload


async def _next_sse_frame(frames: AsyncIterator[str]) -> tuple[str, dict[str, Any]]:
    event_chunk = await anext(frames)
    data_chunk = await anext(frames)
    event_name = event_chunk.removeprefix("event: ").strip()
    payload = json.loads(data_chunk.removeprefix("data: ").strip())
    if not isinstance(payload, dict):
        raise SystemExit("SSE frame payload was not an object")
    return event_name, payload


def _routes(app: Any) -> dict[tuple[str, str], Any]:
    return {
        (route.path, next(iter(route.methods - {"HEAD", "OPTIONS"}))): route
        for route in app.routes
        if hasattr(route, "methods")
    }


async def _apply_migration(database_url: str) -> None:
    migration = (ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(
        encoding="utf-8"
    )
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(migration)
    finally:
        await conn.close()


async def _delete_smoke_rows(database_url: str, smoke_id: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(
            """
            DELETE FROM autoskill.admin_live_event_outbox
            WHERE object_type = 'observatory_live_smoke'
              AND (
                object_id LIKE $1
                OR payload->>'smoke_id' = $2
              )
            """,
            f"{smoke_id}:%",
            smoke_id,
        )
    finally:
        await conn.close()


def _default_database_url() -> str:
    explicit = os.environ.get("AUTOSKILL_DATABASE_URL") or os.environ.get(
        "SKILLKERNEL_DATABASE_URL"
    )
    if explicit:
        return explicit
    password = os.environ.get("AUTOSKILL_POSTGRES_PASSWORD", "autoskill-dev")
    return f"postgresql://autoskill:{password}@127.0.0.1:55432/autoskill"


if __name__ == "__main__":
    main()
