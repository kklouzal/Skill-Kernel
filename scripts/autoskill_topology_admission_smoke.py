#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "sidecar"))

from autoskill.core.hashing import sha256_json
from autoskill.core.skillir import EffectSignature
from autoskill.db.autonomy import AsyncpgAutonomyControlStore
from autoskill.db.evidence import AsyncpgEvidenceStore
from autoskill.db.governance import AsyncpgGovernanceStore
from autoskill.db.topology import AsyncpgTopologyStore
from autoskill.db.workspaces import ensure_workspace
from autoskill.services.topology import (
    CreateTopologyRequest,
    TopologyProposalResult,
    TopologySkill,
    persist_topology_proposal,
    propose_creation,
)
from migrate import run_migration

LOW_FIDELITY_CASES = ("hash_only", "metadata_only", "unavailable")
ADMISSIBLE_FIDELITY_CASES = ("redacted_derivative", "declassified_summary")


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real-Postgres topology admission smoke proving governed "
            "evidence-fidelity state controls propose-only topology persistence."
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
    smoke_id = f"topology-admission-smoke-{uuid4()}"
    workspace_key = args.workspace_id or smoke_id
    evidence_store = AsyncpgEvidenceStore(args.database_url)
    topology_store = AsyncpgTopologyStore(args.database_url)
    governance_store = AsyncpgGovernanceStore(args.database_url)
    autonomy_store = AsyncpgAutonomyControlStore(args.database_url)
    try:
        await _delete_smoke_workspace(args.database_url, workspace_key)
        evidence_by_fidelity = await _seed_governed_evidence(
            args.database_url,
            workspace_key=workspace_key,
            smoke_id=smoke_id,
            fidelity_values=[
                *[item for item in LOW_FIDELITY_CASES if item != "unavailable"],
                *ADMISSIBLE_FIDELITY_CASES,
            ],
        )
        cases = []
        for fidelity in LOW_FIDELITY_CASES:
            evidence_id = (
                uuid4()
                if fidelity == "unavailable"
                else evidence_by_fidelity[fidelity]
            )
            case = await _run_case(
                evidence_store=evidence_store,
                topology_store=topology_store,
                governance_store=governance_store,
                autonomy_store=autonomy_store,
                workspace_key=workspace_key,
                fidelity=fidelity,
                evidence_id=evidence_id,
            )
            _assert_low_fidelity_case(case)
            cases.append(case)
        for fidelity in ADMISSIBLE_FIDELITY_CASES:
            case = await _run_case(
                evidence_store=evidence_store,
                topology_store=topology_store,
                governance_store=governance_store,
                autonomy_store=autonomy_store,
                workspace_key=workspace_key,
                fidelity=fidelity,
                evidence_id=evidence_by_fidelity[fidelity],
            )
            _assert_admissible_case(case)
            cases.append(case)
        return {
            "schema": "autoskill.topology-admission-smoke.v1",
            "ok": True,
            "workspace_id": workspace_key,
            "smoke_id": smoke_id,
            "cases": cases,
            "raw_evidence_returned": False,
            "runtime_skill_writes": False,
            "activation_authority": False,
            "live_openclaw_mutation": False,
        }
    finally:
        await evidence_store.close()
        await topology_store.close()
        await governance_store.close()
        await autonomy_store.close()
        if not args.keep_rows:
            await _delete_smoke_workspace(args.database_url, workspace_key)


async def _run_case(
    *,
    evidence_store: AsyncpgEvidenceStore,
    topology_store: AsyncpgTopologyStore,
    governance_store: AsyncpgGovernanceStore,
    autonomy_store: AsyncpgAutonomyControlStore,
    workspace_key: str,
    fidelity: str,
    evidence_id: UUID,
) -> dict[str, Any]:
    fidelity_by_id = await _fidelity_by_id(
        evidence_store,
        workspace_key=workspace_key,
        evidence_ids=[evidence_id],
    )
    proposal = propose_creation(
        CreateTopologyRequest(
            proposed=TopologySkill(
                slug=f"smoke-{fidelity.replace('_', '-')}",
                effects=EffectSignature(outputs=[f"smoke-{fidelity}-output"]),
            ),
            evidence_ids=[str(evidence_id)],
            creation_reasons=[f"smoke topology admission case: {fidelity}"],
            evidence_fidelity_by_id=fidelity_by_id,
        )
    )
    persisted = await persist_topology_proposal(
        topology_store,
        governance_store,
        workspace_key=workspace_key,
        proposal=proposal,
        autonomy=autonomy_store,
    )
    detail = await topology_store.get_operation_detail(
        workspace_key=workspace_key,
        skill_graph_operation_id=persisted.operation.skill_graph_operation_id,
    )
    if detail is None:
        raise SystemExit("persisted topology operation could not be detail-read")
    transaction = await governance_store.get_transaction(
        workspace_key=workspace_key,
        evolution_transaction_id=persisted.operation.evolution_transaction_id,
    )
    if transaction is None:
        raise SystemExit("persisted topology transaction could not be detail-read")
    return _case_summary(
        fidelity=fidelity,
        evidence_id=evidence_id,
        proposal=proposal,
        trial_statuses=[trial.status for trial in detail.trials],
        transaction_status=transaction.status,
        transaction_metrics=transaction.metrics,
    )


async def _fidelity_by_id(
    evidence_store: AsyncpgEvidenceStore,
    *,
    workspace_key: str,
    evidence_ids: list[UUID],
) -> dict[str, str]:
    fetched = await evidence_store.get_evidence_fidelity_by_id(
        workspace_key=workspace_key,
        evidence_ids=evidence_ids,
    )
    return {
        str(evidence_id): fetched.get(str(evidence_id), "unavailable")
        for evidence_id in evidence_ids
    }


def _case_summary(
    *,
    fidelity: str,
    evidence_id: UUID,
    proposal: TopologyProposalResult,
    trial_statuses: list[str],
    transaction_status: str,
    transaction_metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "fidelity": fidelity,
        "evidence_id": str(evidence_id),
        "proposal_status": proposal.status,
        "persistence_status": transaction_metrics.get("topology_status"),
        "transaction_status": transaction_status,
        "operation_kind": proposal.operation_kind,
        "trial_statuses": trial_statuses,
        "blockers": proposal.blockers,
        "evidence_fidelity_by_id": proposal.evidence_fidelity_by_id,
        "low_fidelity_evidence_count": transaction_metrics.get(
            "low_fidelity_evidence_count"
        ),
        "requires_trial_before_apply": transaction_metrics.get(
            "requires_trial_before_apply"
        ),
        "writes": transaction_metrics.get("writes"),
        "raw_evidence_returned": False,
    }


def _assert_low_fidelity_case(case: dict[str, Any]) -> None:
    expected_fidelity = case["fidelity"]
    if case["proposal_status"] != "blocked":
        raise SystemExit(f"{expected_fidelity} case did not fail closed")
    if case["persistence_status"] != "blocked":
        raise SystemExit(f"{expected_fidelity} case was not persisted as blocked")
    if case["transaction_status"] != "blocked":
        raise SystemExit(f"{expected_fidelity} transaction was not blocked")
    if case["low_fidelity_evidence_count"] != 1:
        raise SystemExit(f"{expected_fidelity} low-fidelity metric was not recorded")
    if not case["blockers"]:
        raise SystemExit(f"{expected_fidelity} case did not record blockers")
    if set(case["trial_statuses"]) != {"blocked"}:
        raise SystemExit(f"{expected_fidelity} trials were not persisted blocked")


def _assert_admissible_case(case: dict[str, Any]) -> None:
    expected_fidelity = case["fidelity"]
    if case["proposal_status"] != "candidate":
        raise SystemExit(f"{expected_fidelity} case was not admissible")
    if case["persistence_status"] != "candidate":
        raise SystemExit(f"{expected_fidelity} operation was not persisted candidate")
    if case["transaction_status"] != "staged":
        raise SystemExit(f"{expected_fidelity} transaction was not staged")
    if case["low_fidelity_evidence_count"] != 0:
        raise SystemExit(f"{expected_fidelity} case recorded low-fidelity evidence")
    if case["blockers"]:
        raise SystemExit(f"{expected_fidelity} case unexpectedly recorded blockers")
    if set(case["trial_statuses"]) != {"planned"}:
        raise SystemExit(f"{expected_fidelity} trials were not propose-only planned")
    if case["requires_trial_before_apply"] is not True:
        raise SystemExit(f"{expected_fidelity} case did not require trials before apply")


async def _seed_governed_evidence(
    database_url: str,
    *,
    workspace_key: str,
    smoke_id: str,
    fidelity_values: list[str],
) -> dict[str, UUID]:
    conn = await asyncpg.connect(database_url)
    try:
        workspace_id = await ensure_workspace(conn, workspace_key)
        evidence_by_fidelity: dict[str, UUID] = {}
        for fidelity in fidelity_values:
            event_id = await _insert_raw_event(
                conn,
                workspace_id=workspace_id,
                smoke_id=smoke_id,
                fidelity=fidelity,
            )
            evidence_id = await _insert_evidence_item(
                conn,
                workspace_id=workspace_id,
                source_event_id=event_id,
                smoke_id=smoke_id,
                fidelity=fidelity,
            )
            evidence_by_fidelity[fidelity] = evidence_id
        return evidence_by_fidelity
    finally:
        await conn.close()


async def _insert_raw_event(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    smoke_id: str,
    fidelity: str,
) -> UUID:
    payload = {
        "schema": "autoskill.topology-admission-smoke.event.v1",
        "smoke_id": smoke_id,
        "evidence_fidelity": fidelity,
        "raw_payload_included": False,
    }
    event_key = f"{smoke_id}:{fidelity}"
    return await conn.fetchval(
        """
        INSERT INTO autoskill.raw_events (
          event_id,
          workspace_id,
          event_type,
          occurred_at,
          source,
          source_event_key,
          trust,
          taint,
          redaction_state,
          evidence_fidelity,
          payload_hash,
          payload
        )
        VALUES (
          gen_random_uuid(),
          $1,
          'topology_admission_smoke',
          now(),
          'autoskill_topology_admission_smoke',
          $2,
          'observed',
          ARRAY['smoke']::text[],
          'redacted',
          $3,
          $4,
          $5::jsonb
        )
        RETURNING event_id
        """,
        workspace_id,
        event_key,
        fidelity,
        sha256_json(payload),
        json.dumps(payload, sort_keys=True),
    )


async def _insert_evidence_item(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    source_event_id: UUID,
    smoke_id: str,
    fidelity: str,
) -> UUID:
    payload = {
        "schema": "autoskill.topology-admission-smoke.evidence.v1",
        "smoke_id": smoke_id,
        "evidence_fidelity": fidelity,
        "semantic_payload": "content-safe topology admission fixture",
    }
    evidence_hash = sha256_json(
        {
            "workspace_id": str(workspace_id),
            "source_event_id": str(source_event_id),
            "fidelity": fidelity,
            "smoke_id": smoke_id,
        }
    )
    return await conn.fetchval(
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
          gen_random_uuid(),
          $1,
          $2,
          $3,
          'event_observation',
          'observed',
          'observed',
          ARRAY['smoke']::text[],
          $4,
          $5::jsonb
        )
        RETURNING evidence_id
        """,
        workspace_id,
        source_event_id,
        evidence_hash,
        f"content-safe topology admission smoke evidence: {fidelity}",
        json.dumps(payload, sort_keys=True),
    )


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
                "DELETE FROM autoskill.topology_operation_trials WHERE workspace_id = $1",
                "DELETE FROM autoskill.topology_operation_results WHERE workspace_id = $1",
                "DELETE FROM autoskill.topology_candidates WHERE workspace_id = $1",
                "DELETE FROM autoskill.planned_topology_trials WHERE workspace_id = $1",
                "DELETE FROM autoskill.provenance_edges WHERE workspace_id = $1",
                """
                DELETE FROM autoskill.evolution_transaction_items item
                USING autoskill.evolution_transactions tx
                WHERE item.evolution_transaction_id = tx.evolution_transaction_id
                  AND tx.workspace_id = $1
                """,
                "DELETE FROM autoskill.skill_graph_operations WHERE workspace_id = $1",
                "DELETE FROM autoskill.evolution_transactions WHERE workspace_id = $1",
                "DELETE FROM autoskill.autonomy_reliability_metrics WHERE workspace_id = $1",
                "DELETE FROM autoskill.autonomy_calibration_observations WHERE workspace_id = $1",
                "DELETE FROM autoskill.evidence WHERE workspace_id = $1",
                "DELETE FROM autoskill.evidence_items WHERE workspace_id = $1",
                "DELETE FROM autoskill.raw_events WHERE workspace_id = $1",
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
