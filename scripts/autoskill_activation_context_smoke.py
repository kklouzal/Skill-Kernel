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
sys.path.insert(0, str(ROOT / "sidecar"))

from autoskill.db.activation import ActivationReadiness, AsyncpgActivationGateStore
from autoskill.db.workspaces import ensure_workspace

CONTEXT_CASES = {
    "missing": {
        "semantic_equivalence_score": 0.95,
        "context_value_per_token": None,
        "expected_allowed": False,
        "expected_blockers": ["context-marginal-value-missing"],
    },
    "below_threshold": {
        "semantic_equivalence_score": 0.95,
        "context_value_per_token": -0.01,
        "expected_allowed": False,
        "expected_blockers": ["context-marginal-value-below-threshold"],
    },
    "passing": {
        "semantic_equivalence_score": 0.95,
        "context_value_per_token": 0.02,
        "expected_allowed": True,
        "expected_blockers": [],
    },
}


def main() -> None:
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a real-Postgres activation context smoke proving "
            "AsyncpgActivationGateStore enforces marginal context value per token."
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
    parser.add_argument(
        "--min-context-value-per-token",
        type=float,
        default=0.0,
        help="Minimum context value per token required for passing activation.",
    )
    parser.add_argument(
        "--min-semantic-equivalence-score",
        type=float,
        default=0.9,
        help="Minimum semantic-equivalence score required by the activation gate.",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.skip_migrate:
        await _apply_migration(args.database_url)
    smoke_id = f"activation-context-smoke-{uuid4()}"
    workspace_key = args.workspace_id or smoke_id
    activation = AsyncpgActivationGateStore(args.database_url)
    try:
        await _delete_smoke_workspace(args.database_url, workspace_key)
        seeded = await _seed_activation_context_cases(
            args.database_url,
            workspace_key=workspace_key,
            smoke_id=smoke_id,
        )
        cases = []
        for case_name in CONTEXT_CASES:
            readiness = await activation.check_activation_readiness(
                workspace_key=workspace_key,
                skill_version_id=seeded["skill_version_id"],
                require_context_compile_proof=True,
                context_compile_run_id=seeded["context_compile_run_ids"][case_name],
                context_artifact_id=seeded["context_artifact_ids"][case_name],
                compiled_text_hash=seeded["compiled_text_hash"],
                context_output_manifest_hash=seeded["output_manifest_hash"],
                require_semantic_equivalence=True,
                min_semantic_equivalence_score=args.min_semantic_equivalence_score,
                require_context_value=True,
                min_context_value_per_token=args.min_context_value_per_token,
                allowed_autonomy_actions=("auto_accept",),
            )
            cases.append(_case_summary(case_name, readiness))
        summary = {
            "schema": "autoskill.activation-context-smoke.v1",
            "ok": True,
            "workspace_id": workspace_key,
            "smoke_id": smoke_id,
            "skill_id": str(seeded["skill_id"]),
            "skill_version_id": str(seeded["skill_version_id"]),
            "min_context_value_per_token": args.min_context_value_per_token,
            "min_semantic_equivalence_score": args.min_semantic_equivalence_score,
            "cases": cases,
            "raw_evidence_returned": False,
            "runtime_skill_writes": False,
            "activation_authority": False,
            "live_openclaw_mutation": False,
        }
        _assert_smoke(summary)
        return summary
    finally:
        await activation.close()
        if not args.keep_rows:
            await _delete_smoke_workspace(args.database_url, workspace_key)


def _case_summary(case_name: str, readiness: ActivationReadiness) -> dict[str, Any]:
    return {
        "case": case_name,
        "allowed": readiness.allowed,
        "blockers": readiness.blockers,
        "context_compile_run_id": (
            str(readiness.context_compile_run_id)
            if readiness.context_compile_run_id
            else None
        ),
        "context_artifact_id": (
            str(readiness.context_artifact_id) if readiness.context_artifact_id else None
        ),
        "context_compile_status": readiness.context_compile_status,
        "context_semantic_equivalence_score": (
            readiness.context_semantic_equivalence_score
        ),
        "context_value_per_token": readiness.context_value_per_token,
        "context_safety_status": readiness.context_safety_status,
        "context_equivalence_status": readiness.context_equivalence_status,
        "context_budget_status": readiness.context_budget_status,
        "autonomy_action": readiness.autonomy_action,
        "raw_evidence_returned": False,
    }


def _assert_smoke(summary: dict[str, Any]) -> None:
    if not summary.get("ok"):
        raise SystemExit("activation context smoke did not complete")
    for flag in (
        "raw_evidence_returned",
        "runtime_skill_writes",
        "activation_authority",
        "live_openclaw_mutation",
    ):
        if summary.get(flag) is not False:
            raise SystemExit(f"activation context smoke safety flag failed: {flag}")

    by_case = {case["case"]: case for case in summary.get("cases", [])}
    if set(by_case) != set(CONTEXT_CASES):
        raise SystemExit(
            "activation context smoke did not report expected cases: "
            f"{sorted(by_case)}"
        )
    for case_name, expected in CONTEXT_CASES.items():
        case = by_case[case_name]
        if case["allowed"] is not expected["expected_allowed"]:
            raise SystemExit(f"{case_name} activation allowed state was unexpected")
        if case["blockers"] != expected["expected_blockers"]:
            raise SystemExit(
                f"{case_name} blockers were unexpected: {case['blockers']}"
            )
        if case["context_semantic_equivalence_score"] is None:
            raise SystemExit(f"{case_name} did not carry semantic equivalence proof")
        if case["context_semantic_equivalence_score"] < summary[
            "min_semantic_equivalence_score"
        ]:
            raise SystemExit(f"{case_name} semantic equivalence was below policy")
        for status_key in (
            "context_compile_status",
            "context_safety_status",
            "context_equivalence_status",
            "context_budget_status",
        ):
            if case[status_key] != "passed":
                raise SystemExit(f"{case_name} {status_key} did not pass")
        if case["autonomy_action"] != "auto_accept":
            raise SystemExit(f"{case_name} autonomy action was not approved")
    if by_case["missing"]["context_value_per_token"] is not None:
        raise SystemExit("missing case unexpectedly carried context value")
    if by_case["below_threshold"]["context_value_per_token"] >= summary[
        "min_context_value_per_token"
    ]:
        raise SystemExit("below-threshold case did not fall below policy")
    if by_case["passing"]["context_value_per_token"] < summary[
        "min_context_value_per_token"
    ]:
        raise SystemExit("passing case did not meet marginal-value policy")

    unsafe_terms = ("secret", "credential", "transcript", "prompt body")
    encoded = json.dumps(summary, sort_keys=True).lower()
    if any(term in encoded for term in unsafe_terms):
        raise SystemExit("activation context smoke summary contains unsafe terms")


async def _seed_activation_context_cases(
    database_url: str,
    *,
    workspace_key: str,
    smoke_id: str,
) -> dict[str, Any]:
    conn = await asyncpg.connect(database_url)
    try:
        workspace_id = await ensure_workspace(conn, workspace_key)
        skill_id = uuid4()
        skill_version_id = uuid4()
        compiled_text_hash = f"sha256:compiled-{uuid4().hex}"
        output_manifest_hash = f"sha256:manifest-{uuid4().hex}"
        await conn.execute(
            """
            INSERT INTO autoskill.skills (skill_id, workspace_id, slug, name)
            VALUES ($1, $2, $3, $4)
            """,
            skill_id,
            workspace_id,
            f"activation-context-smoke-{uuid4().hex}",
            "Activation context marginal value smoke",
        )
        await conn.execute(
            """
            INSERT INTO autoskill.skill_versions (
              skill_version_id,
              skill_id,
              version,
              skill_ir,
              manifest,
              scanner_status,
              evaluator_status
            )
            VALUES ($1, $2, 1, $3::jsonb, '{}'::jsonb, 'passed', 'passed')
            """,
            skill_version_id,
            skill_id,
            json.dumps(
                {
                    "name": "Activation context marginal value smoke",
                    "description": "Content-safe activation context gate fixture.",
                    "granularity": "functional",
                    "requirements": [
                        "prove marginal context value before activation"
                    ],
                },
                sort_keys=True,
            ),
        )
        await _insert_passing_proposal_gate(
            conn,
            workspace_id=workspace_id,
            skill_version_id=skill_version_id,
        )
        context_artifact_ids: dict[str, UUID] = {}
        context_compile_run_ids: dict[str, UUID] = {}
        for case_name, case in CONTEXT_CASES.items():
            context_artifact_id = uuid4()
            context_compile_run_id = uuid4()
            context_artifact_ids[case_name] = context_artifact_id
            context_compile_run_ids[case_name] = context_compile_run_id
            await _insert_context_case(
                conn,
                workspace_id=workspace_id,
                skill_id=skill_id,
                skill_version_id=skill_version_id,
                context_artifact_id=context_artifact_id,
                context_compile_run_id=context_compile_run_id,
                case_name=case_name,
                compiled_text_hash=compiled_text_hash,
                output_manifest_hash=output_manifest_hash,
                semantic_equivalence_score=case["semantic_equivalence_score"],
                context_value_per_token=case["context_value_per_token"],
                smoke_id=smoke_id,
            )
        return {
            "workspace_id": workspace_id,
            "workspace_key": workspace_key,
            "skill_id": skill_id,
            "skill_version_id": skill_version_id,
            "context_artifact_ids": context_artifact_ids,
            "context_compile_run_ids": context_compile_run_ids,
            "compiled_text_hash": compiled_text_hash,
            "output_manifest_hash": output_manifest_hash,
        }
    finally:
        await conn.close()


async def _insert_passing_proposal_gate(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_version_id: UUID,
) -> None:
    await conn.execute(
        """
        INSERT INTO autoskill.evaluations (
          evaluation_id,
          workspace_id,
          skill_version_id,
          category,
          status,
          result
        )
        VALUES ($1, $2, $3, 'proposal_gate', 'passed', $4::jsonb)
        """,
        uuid4(),
        workspace_id,
        skill_version_id,
        json.dumps(
            {
                "autonomy_fallback": {
                    "selected_action": "auto_accept",
                    "autonomy_decision_id": "activation-context-smoke",
                    "deterministic_checks": {
                        "hard_invariants_passed": True,
                    },
                },
            },
            sort_keys=True,
        ),
    )


async def _insert_context_case(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    skill_id: UUID,
    skill_version_id: UUID,
    context_artifact_id: UUID,
    context_compile_run_id: UUID,
    case_name: str,
    compiled_text_hash: str,
    output_manifest_hash: str,
    semantic_equivalence_score: float,
    context_value_per_token: float | None,
    smoke_id: str,
) -> None:
    metadata: dict[str, Any] = {
        "schema": "autoskill.activation-context-smoke.artifact.v1",
        "smoke_id": smoke_id,
        "case": case_name,
        "loadability_class": "runtime_on_skill_load",
        "relative_path": "SKILL.md",
        "content_safe": True,
    }
    if context_value_per_token is not None:
        metadata["last_context_value_per_token"] = context_value_per_token
    await conn.execute(
        """
        INSERT INTO autoskill.context_artifacts (
          context_artifact_id,
          workspace_id,
          artifact_kind,
          source_object_type,
          source_object_id,
          skill_id,
          skill_version_id,
          text_hash,
          token_count,
          max_tokens,
          semantic_density_score,
          safety_status,
          equivalence_status,
          budget_status,
          shadowing_status,
          metadata
        )
        VALUES (
          $1, $2, 'skill_md', 'skill_version', $3, $4, $3, $5, 120, 900,
          0.82, 'passed', 'passed', 'passed', 'passed', $6::jsonb
        )
        """,
        context_artifact_id,
        workspace_id,
        skill_version_id,
        skill_id,
        compiled_text_hash,
        json.dumps(metadata, sort_keys=True),
    )
    await conn.execute(
        """
        INSERT INTO autoskill.context_compile_runs (
          context_compile_run_id,
          workspace_id,
          skill_id,
          skill_version_id,
          context_artifact_id,
          compiler_version,
          input_skillir_hash,
          output_manifest_hash,
          actual_runtime_tokens,
          compression_ratio,
          semantic_equivalence_score,
          status,
          metadata
        )
        VALUES (
          $1, $2, $3, $4, $5, 'autoskill-compiler.smoke',
          $6, $7, 120, 0.42, $8, 'passed', $9::jsonb
        )
        """,
        context_compile_run_id,
        workspace_id,
        skill_id,
        skill_version_id,
        context_artifact_id,
        f"sha256:skillir-{case_name}-{skill_version_id.hex}",
        output_manifest_hash,
        semantic_equivalence_score,
        json.dumps(
            {
                "schema": "autoskill.activation-context-smoke.compile-run.v1",
                "case": case_name,
                "content_safe": True,
            },
            sort_keys=True,
        ),
    )


async def _apply_migration(database_url: str) -> None:
    migration = (ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(
        encoding="utf-8"
    )
    conn = await asyncpg.connect(database_url)
    try:
        await conn.execute(migration)
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
                "DELETE FROM autoskill.context_compile_runs WHERE workspace_id = $1",
                "DELETE FROM autoskill.runtime_artifacts WHERE workspace_id = $1",
                "DELETE FROM autoskill.context_artifacts WHERE workspace_id = $1",
                "DELETE FROM autoskill.evaluations WHERE workspace_id = $1",
                """
                DELETE FROM autoskill.skill_components
                WHERE skill_version_id IN (
                  SELECT sv.skill_version_id
                  FROM autoskill.skill_versions sv
                  JOIN autoskill.skills s ON s.skill_id = sv.skill_id
                  WHERE s.workspace_id = $1
                )
                """,
                """
                DELETE FROM autoskill.skill_ir_revisions
                WHERE skill_version_id IN (
                  SELECT sv.skill_version_id
                  FROM autoskill.skill_versions sv
                  JOIN autoskill.skills s ON s.skill_id = sv.skill_id
                  WHERE s.workspace_id = $1
                )
                """,
                """
                DELETE FROM autoskill.skill_versions
                WHERE skill_id IN (
                  SELECT skill_id FROM autoskill.skills WHERE workspace_id = $1
                )
                """,
                "DELETE FROM autoskill.skill_state_records WHERE workspace_id = $1",
                "DELETE FROM autoskill.memory_contracts WHERE workspace_id = $1",
                "DELETE FROM autoskill.skills WHERE workspace_id = $1",
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
