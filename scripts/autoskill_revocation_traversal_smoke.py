#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "sidecar"))

from autoskill.core.hashing import sha256_json
from autoskill.db.governance import AsyncpgGovernanceStore
from migrate import run_migration

WRITER_ITEM_KINDS = ("compiled_skill_file", "support_artifact")


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real-Postgres revocation traversal smoke proving evidence-root "
            "provenance and writer transaction items expand to affected skill versions."
        )
    )
    parser.add_argument("--database-url", default=_default_database_url())
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Optional workspace key. Defaults to an isolated smoke workspace.",
    )
    parser.add_argument(
        "--skip-migrate",
        action="store_true",
        help="Assume migrations have already been applied.",
    )
    parser.add_argument(
        "--keep-rows",
        action="store_true",
        help="Leave smoke rows in Postgres for manual inspection.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.skip_migrate:
        await _apply_migration(args.database_url)
    smoke_id = f"revocation-traversal-smoke-{uuid4()}"
    workspace_key = args.workspace_id or smoke_id
    governance_store = AsyncpgGovernanceStore(args.database_url)
    try:
        await _delete_smoke_workspace(args.database_url, workspace_key)
        seeded = await _seed_governance_graph(
            governance_store,
            workspace_key=workspace_key,
            smoke_id=smoke_id,
        )
        traversal = await governance_store.preview_revocation_traversal(
            workspace_key=workspace_key,
            root_object_type="evidence_item",
            root_object_id=seeded["evidence_id"],
            max_depth=8,
            max_nodes=50,
        )
        traversal_json = traversal.to_json()
        expanded_impacts = await governance_store.expand_writer_item_impacts(
            workspace_key=workspace_key,
            objects=traversal_json["impacted_objects"],
        )
        revocation = await governance_store.request_revocation(
            workspace_key=workspace_key,
            request_kind="operator_revoke",
            root_object_type="evidence_item",
            root_object_id=seeded["evidence_id"],
            traversal_summary={
                "schema": "autoskill.revocation-traversal-smoke.summary.v1",
                "impacted_count": traversal_json["impacted_count"],
                "edge_count": len(traversal_json["edges"]),
                "expanded_writer_item_impacts": len(expanded_impacts),
                "content_safe": True,
            },
        )
        fetched_revocation = await governance_store.get_revocation_request(
            workspace_key=workspace_key,
            revocation_request_id=revocation.revocation_request_id,
        )
        if fetched_revocation is None:
            raise SystemExit("queued revocation request could not be detail-read")

        _assert_smoke(
            seeded=seeded,
            traversal=traversal_json,
            expanded_impacts=expanded_impacts,
            revocation=fetched_revocation.to_json(),
        )
        return {
            "schema": "autoskill.revocation-traversal-smoke.v1",
            "ok": True,
            "workspace_id": workspace_key,
            "smoke_id": smoke_id,
            "root_object": {
                "object_type": "evidence_item",
                "object_id": str(seeded["evidence_id"]),
            },
            "transaction_id": str(seeded["transaction_id"]),
            "transaction_item_ids": [
                str(item_id) for item_id in seeded["transaction_item_ids"]
            ],
            "skill_version_ids": [
                str(skill_version_id)
                for skill_version_id in seeded["skill_version_ids"]
            ],
            "traversal": {
                "impacted_count": traversal_json["impacted_count"],
                "edge_count": len(traversal_json["edges"]),
                "object_types": sorted(
                    {item["object_type"] for item in traversal_json["impacted_objects"]}
                ),
                "truncated": traversal_json["truncated"],
            },
            "expanded_impacts": expanded_impacts,
            "revocation": {
                "revocation_request_id": str(revocation.revocation_request_id),
                "request_kind": revocation.request_kind,
                "status": revocation.status,
                "traversal_summary": revocation.traversal_summary,
            },
            "raw_evidence_returned": False,
            "runtime_skill_writes": False,
            "activation_authority": False,
            "live_openclaw_mutation": False,
        }
    finally:
        await governance_store.close()
        if not args.keep_rows:
            await _delete_smoke_workspace(args.database_url, workspace_key)


async def _seed_governance_graph(
    governance_store: AsyncpgGovernanceStore,
    *,
    workspace_key: str,
    smoke_id: str,
) -> dict[str, Any]:
    evidence_id = uuid4()
    memory_id = uuid4()
    skill_version_ids = [uuid4(), uuid4()]
    started = await governance_store.start_transaction(
        workspace_key=workspace_key,
        transaction_kind="compile",
        idempotency_key=f"{smoke_id}:compile",
        plan_hash=sha256_json(
            {
                "schema": "autoskill.revocation-traversal-smoke.plan.v1",
                "smoke_id": smoke_id,
                "raw_evidence_included": False,
            }
        ),
        cause={
            "schema": "autoskill.revocation-traversal-smoke.cause.v1",
            "smoke_id": smoke_id,
            "content_safe": True,
        },
        source_evidence_ids=[evidence_id],
        source_memory_ids=[memory_id],
        policy_snapshot={
            "schema": "autoskill.revocation-traversal-smoke.policy.v1",
            "derived_data_revocation": True,
            "raw_evidence_included": False,
        },
    )
    transaction_id = started.transaction.evolution_transaction_id
    items = []
    for index, (item_kind, skill_version_id) in enumerate(
        zip(WRITER_ITEM_KINDS, skill_version_ids, strict=True),
        start=1,
    ):
        items.append(
            await governance_store.record_transaction_item(
                evolution_transaction_id=transaction_id,
                item_kind=item_kind,
                activation_state="staged",
                item_id=skill_version_id,
                relative_path=f"skills/autoskill/revocation-smoke-{index}/SKILL.md",
                after_hash=sha256_json(
                    {
                        "smoke_id": smoke_id,
                        "item_kind": item_kind,
                        "skill_version_id": str(skill_version_id),
                    }
                ),
                rollback_action={
                    "action": "delete_compiled_artifact",
                    "content_safe": True,
                },
            )
        )
    await governance_store.update_transaction_status(
        evolution_transaction_id=transaction_id,
        status="staged",
        metrics={
            "schema": "autoskill.revocation-traversal-smoke.metrics.v1",
            "writer_items": len(items),
            "runtime_skill_writes": False,
        },
    )
    for item in items:
        await governance_store.record_provenance_edge(
            workspace_key=workspace_key,
            source_kind="evidence_item",
            source_id=evidence_id,
            derived_kind="transaction_item",
            derived_id=item.transaction_item_id,
            relation="source_for_writer_item",
        )
        await governance_store.record_provenance_edge(
            workspace_key=workspace_key,
            source_kind="evolution_transaction",
            source_id=transaction_id,
            derived_kind="transaction_item",
            derived_id=item.transaction_item_id,
            relation="contains_writer_item",
        )
    await governance_store.record_provenance_edge(
        workspace_key=workspace_key,
        source_kind="memory",
        source_id=memory_id,
        derived_kind="evolution_transaction",
        derived_id=transaction_id,
        relation="source_for_transaction",
    )
    return {
        "evidence_id": evidence_id,
        "memory_id": memory_id,
        "transaction_id": transaction_id,
        "transaction_item_ids": [item.transaction_item_id for item in items],
        "skill_version_ids": skill_version_ids,
    }


def _assert_smoke(
    *,
    seeded: dict[str, Any],
    traversal: dict[str, Any],
    expanded_impacts: list[dict[str, str]],
    revocation: dict[str, Any],
) -> None:
    impacted = {
        (item["object_type"], item["object_id"]) for item in traversal["impacted_objects"]
    }
    expected = {
        ("evidence_item", str(seeded["evidence_id"])),
        *[
            ("transaction_item", str(item_id))
            for item_id in seeded["transaction_item_ids"]
        ],
    }
    missing = expected - impacted
    if missing:
        raise SystemExit(f"revocation traversal missed expected objects: {sorted(missing)}")
    if traversal["truncated"]:
        raise SystemExit("revocation traversal unexpectedly truncated")
    if not any(
        edge["relation"] == "source_for_writer_item"
        for edge in traversal["edges"]
    ):
        raise SystemExit("revocation traversal did not include writer provenance edges")

    expanded = {
        (item["object_type"], item["object_id"]) for item in expanded_impacts
    }
    expected_skill_versions = {
        ("skill_version", str(skill_version_id))
        for skill_version_id in seeded["skill_version_ids"]
    }
    if expanded != expected_skill_versions:
        raise SystemExit(
            "writer-item expansion did not yield expected skill versions: "
            f"expected={sorted(expected_skill_versions)} actual={sorted(expanded)}"
        )
    summary = revocation["traversal_summary"]
    if revocation["status"] != "queued":
        raise SystemExit("revocation request was not queued")
    if summary.get("expanded_writer_item_impacts") != len(expected_skill_versions):
        raise SystemExit("revocation summary did not record writer expansion count")
    unsafe_terms = ("raw text", "prompt", "message", "secret", "credential")
    encoded = json.dumps(revocation, sort_keys=True).lower()
    if any(term in encoded for term in unsafe_terms):
        raise SystemExit("revocation request summary contains unsafe content terms")


async def _apply_migration(database_url: str) -> None:
    migration = (ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(
        encoding="utf-8"
    )
    conn = await asyncpg.connect(database_url)
    try:
        await run_migration(conn, migration)
    finally:
        await conn.close()


async def _delete_smoke_workspace(database_url: str, workspace_key: str) -> None:
    conn = await asyncpg.connect(database_url)
    try:
        workspace_id = await conn.fetchval(
            "SELECT workspace_id FROM autoskill.workspaces WHERE external_key = $1",
            workspace_key,
        )
        if workspace_id is None:
            return
        async with conn.transaction():
            for statement in (
                "DELETE FROM autoskill.revocation_requests WHERE workspace_id = $1",
                "DELETE FROM autoskill.provenance_edges WHERE workspace_id = $1",
                """
                DELETE FROM autoskill.evolution_transaction_items item
                USING autoskill.evolution_transactions tx
                WHERE item.evolution_transaction_id = tx.evolution_transaction_id
                  AND tx.workspace_id = $1
                """,
                "DELETE FROM autoskill.evolution_transactions WHERE workspace_id = $1",
                "DELETE FROM autoskill.memory_contracts WHERE workspace_id = $1",
                "DELETE FROM autoskill.workspaces WHERE workspace_id = $1",
            ):
                await conn.execute(statement, workspace_id)
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
