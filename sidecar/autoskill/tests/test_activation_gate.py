from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import asyncpg
import pytest
from autoskill.db.activation import (
    AsyncpgActivationGateStore,
    NullActivationGateStore,
    _activation_blockers,
)


@dataclass(frozen=True)
class _ActivationSqlFixture:
    workspace_key: str
    skill_id: UUID
    skill_version_id: UUID
    context_artifact_ids: dict[str, UUID]
    context_compile_run_ids: dict[str, UUID]
    compiled_text_hashes: dict[str, str]
    output_manifest_hash: str


def _row(
    *,
    evaluator_status: str = "needs_intervention",
    latest_evaluation_status: str = "needs_intervention",
    autonomy_action: str | None = "stage_canary",
    autonomy_hard_invariants_passed: bool = True,
    context_compile_run_id: object | None = None,
    context_artifact_id: object | None = None,
    context_compile_status: str | None = None,
    context_semantic_equivalence_score: float | None = None,
    context_value_per_token: float | None = None,
    context_safety_status: str | None = None,
    context_equivalence_status: str | None = None,
    context_budget_status: str | None = None,
) -> dict[str, object]:
    return {
        "scanner_status": "passed",
        "evaluator_status": evaluator_status,
        "latest_evaluation_status": latest_evaluation_status,
        "compatibility_status": None,
        "context_compile_run_id": context_compile_run_id,
        "context_artifact_id": context_artifact_id,
        "context_compile_status": context_compile_status,
        "context_semantic_equivalence_score": context_semantic_equivalence_score,
        "context_value_per_token": context_value_per_token,
        "context_safety_status": context_safety_status,
        "context_equivalence_status": context_equivalence_status,
        "context_budget_status": context_budget_status,
        "autonomy_action": autonomy_action,
        "autonomy_decision_id": "decision-alpha",
        "autonomy_hard_invariants_passed": autonomy_hard_invariants_passed,
    }


def test_stage_canary_autonomy_action_unblocks_soft_evaluator_stall() -> None:
    assert (
        _activation_blockers(
            _row(),
            executor_profile_id=None,
            require_context_compile_proof=False,
            context_compile_run_id=None,
            context_artifact_id=None,
            compiled_text_hash=None,
            context_output_manifest_hash=None,
            allowed_autonomy_actions=("auto_accept", "stage_canary"),
        )
        == []
    )


def test_auto_accept_autonomy_action_allows_passed_evaluator_gate() -> None:
    assert (
        _activation_blockers(
            _row(
                evaluator_status="passed",
                latest_evaluation_status="passed",
                autonomy_action="auto_accept",
            ),
            executor_profile_id=None,
            require_context_compile_proof=False,
            context_compile_run_id=None,
            context_artifact_id=None,
            compiled_text_hash=None,
            context_output_manifest_hash=None,
            allowed_autonomy_actions=("auto_accept", "stage_canary"),
        )
        == []
    )


def test_missing_autonomy_action_keeps_soft_evaluator_stall_blocked() -> None:
    blockers = _activation_blockers(
        _row(autonomy_action=None),
        executor_profile_id=None,
        require_context_compile_proof=False,
        context_compile_run_id=None,
        context_artifact_id=None,
        compiled_text_hash=None,
        context_output_manifest_hash=None,
        allowed_autonomy_actions=("auto_accept", "stage_canary"),
    )

    assert blockers == [
        "autonomy-action-not-approved",
        "evaluator-not-passed",
        "proposal-gate-not-passed",
    ]


def test_stage_canary_does_not_override_hard_evaluator_failure() -> None:
    blockers = _activation_blockers(
        _row(evaluator_status="failed", latest_evaluation_status="failed"),
        executor_profile_id=None,
        require_context_compile_proof=False,
        context_compile_run_id=None,
        context_artifact_id=None,
        compiled_text_hash=None,
        context_output_manifest_hash=None,
        allowed_autonomy_actions=("auto_accept", "stage_canary"),
    )

    assert blockers == ["evaluator-not-passed", "proposal-gate-not-passed"]


def test_stage_canary_requires_autonomy_hard_invariants_to_pass() -> None:
    blockers = _activation_blockers(
        _row(autonomy_hard_invariants_passed=False),
        executor_profile_id=None,
        require_context_compile_proof=False,
        context_compile_run_id=None,
        context_artifact_id=None,
        compiled_text_hash=None,
        context_output_manifest_hash=None,
        allowed_autonomy_actions=("auto_accept", "stage_canary"),
    )

    assert blockers == [
        "autonomy-hard-invariants-not-passed",
        "evaluator-not-passed",
        "proposal-gate-not-passed",
    ]


def test_null_activation_gate_requires_context_compile_proof() -> None:
    skill_version_id = uuid4()

    readiness = asyncio.run(
        NullActivationGateStore().check_activation_readiness(
            workspace_key="workspace-alpha",
            skill_version_id=skill_version_id,
            require_context_compile_proof=True,
        )
    )

    assert readiness.allowed is False
    assert readiness.skill_version_id == skill_version_id
    assert readiness.blockers == ["context-compile-proof-missing"]
    assert readiness.context_compile_run_id is None
    assert readiness.context_artifact_id is None
    assert readiness.context_compile_status == "passed"
    assert readiness.context_semantic_equivalence_score is None
    assert readiness.context_value_per_token is None
    assert readiness.context_safety_status == "passed"
    assert readiness.context_equivalence_status == "passed"
    assert readiness.context_budget_status == "passed"


def test_activation_blockers_require_context_semantic_equivalence_score() -> None:
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    blockers = _activation_blockers(
        _row(
            evaluator_status="passed",
            latest_evaluation_status="passed",
            autonomy_action="auto_accept",
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_semantic_equivalence_score=None,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
        ),
        executor_profile_id=None,
        require_context_compile_proof=True,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        compiled_text_hash="sha256:compiled",
        context_output_manifest_hash="sha256:manifest",
        require_semantic_equivalence=True,
        min_semantic_equivalence_score=0.9,
        allowed_autonomy_actions=("auto_accept",),
    )

    assert blockers == ["context-semantic-equivalence-missing"]


def test_activation_blockers_reject_below_threshold_context_semantic_equivalence() -> None:
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    blockers = _activation_blockers(
        _row(
            evaluator_status="passed",
            latest_evaluation_status="passed",
            autonomy_action="auto_accept",
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_semantic_equivalence_score=0.89,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
        ),
        executor_profile_id=None,
        require_context_compile_proof=True,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        compiled_text_hash="sha256:compiled",
        context_output_manifest_hash="sha256:manifest",
        require_semantic_equivalence=True,
        min_semantic_equivalence_score=0.9,
        allowed_autonomy_actions=("auto_accept",),
    )

    assert blockers == ["context-semantic-equivalence-below-threshold"]


def test_activation_blockers_accept_passing_context_semantic_equivalence() -> None:
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    blockers = _activation_blockers(
        _row(
            evaluator_status="passed",
            latest_evaluation_status="passed",
            autonomy_action="auto_accept",
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_semantic_equivalence_score=0.91,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
        ),
        executor_profile_id=None,
        require_context_compile_proof=True,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        compiled_text_hash="sha256:compiled",
        context_output_manifest_hash="sha256:manifest",
        require_semantic_equivalence=True,
        min_semantic_equivalence_score=0.9,
        allowed_autonomy_actions=("auto_accept",),
    )

    assert blockers == []


def test_null_activation_gate_fails_closed_when_semantic_threshold_required() -> None:
    readiness = asyncio.run(
        NullActivationGateStore().check_activation_readiness(
            workspace_key="workspace-alpha",
            skill_version_id=uuid4(),
            require_context_compile_proof=True,
            context_compile_run_id=uuid4(),
            context_artifact_id=uuid4(),
            compiled_text_hash="sha256:compiled",
            context_output_manifest_hash="sha256:manifest",
            require_semantic_equivalence=True,
            min_semantic_equivalence_score=0.9,
        )
    )

    assert readiness.allowed is False
    assert readiness.blockers == ["context-semantic-equivalence-missing"]
    assert readiness.context_semantic_equivalence_score is None


def test_activation_blockers_require_context_value_per_token() -> None:
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    blockers = _activation_blockers(
        _row(
            evaluator_status="passed",
            latest_evaluation_status="passed",
            autonomy_action="auto_accept",
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_semantic_equivalence_score=0.95,
            context_value_per_token=None,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
        ),
        executor_profile_id=None,
        require_context_compile_proof=True,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        compiled_text_hash="sha256:compiled",
        context_output_manifest_hash="sha256:manifest",
        require_context_value=True,
        min_context_value_per_token=0.0,
        allowed_autonomy_actions=("auto_accept",),
    )

    assert blockers == ["context-marginal-value-missing"]


def test_activation_blockers_reject_below_threshold_context_value_per_token() -> None:
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    blockers = _activation_blockers(
        _row(
            evaluator_status="passed",
            latest_evaluation_status="passed",
            autonomy_action="auto_accept",
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_semantic_equivalence_score=0.95,
            context_value_per_token=-0.01,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
        ),
        executor_profile_id=None,
        require_context_compile_proof=True,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        compiled_text_hash="sha256:compiled",
        context_output_manifest_hash="sha256:manifest",
        require_context_value=True,
        min_context_value_per_token=0.0,
        allowed_autonomy_actions=("auto_accept",),
    )

    assert blockers == ["context-marginal-value-below-threshold"]


def test_activation_blockers_accept_passing_context_value_per_token() -> None:
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    blockers = _activation_blockers(
        _row(
            evaluator_status="passed",
            latest_evaluation_status="passed",
            autonomy_action="auto_accept",
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            context_compile_status="passed",
            context_semantic_equivalence_score=0.95,
            context_value_per_token=0.01,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
        ),
        executor_profile_id=None,
        require_context_compile_proof=True,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        compiled_text_hash="sha256:compiled",
        context_output_manifest_hash="sha256:manifest",
        require_context_value=True,
        min_context_value_per_token=0.0,
        allowed_autonomy_actions=("auto_accept",),
    )

    assert blockers == []


def test_null_activation_gate_fails_closed_when_context_value_required() -> None:
    readiness = asyncio.run(
        NullActivationGateStore().check_activation_readiness(
            workspace_key="workspace-alpha",
            skill_version_id=uuid4(),
            require_context_compile_proof=True,
            context_compile_run_id=uuid4(),
            context_artifact_id=uuid4(),
            compiled_text_hash="sha256:compiled",
            context_output_manifest_hash="sha256:manifest",
            require_context_value=True,
            min_context_value_per_token=0.0,
        )
    )

    assert readiness.allowed is False
    assert readiness.blockers == ["context-marginal-value-missing"]
    assert readiness.context_value_per_token is None


def test_null_activation_gate_accepts_complete_context_compile_proof() -> None:
    skill_version_id = uuid4()
    executor_profile_id = uuid4()
    context_compile_run_id = uuid4()
    context_artifact_id = uuid4()

    readiness = asyncio.run(
        NullActivationGateStore().check_activation_readiness(
            workspace_key="workspace-alpha",
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            require_context_compile_proof=True,
            context_compile_run_id=context_compile_run_id,
            context_artifact_id=context_artifact_id,
            compiled_text_hash="sha256:compiled",
            context_output_manifest_hash="sha256:manifest",
            allowed_autonomy_actions=("auto_accept",),
        )
    )

    assert readiness.allowed is True
    assert readiness.blockers == []
    assert readiness.skill_version_id == skill_version_id
    assert readiness.executor_profile_id == executor_profile_id
    assert readiness.context_compile_run_id == context_compile_run_id
    assert readiness.context_artifact_id == context_artifact_id
    assert readiness.scanner_status == "passed"
    assert readiness.evaluator_status == "passed"
    assert readiness.latest_evaluation_status == "passed"
    assert readiness.compatibility_status == "compatible"
    assert readiness.context_compile_status == "passed"
    assert readiness.context_semantic_equivalence_score is None
    assert readiness.context_value_per_token is None
    assert readiness.context_safety_status == "passed"
    assert readiness.context_equivalence_status == "passed"
    assert readiness.context_budget_status == "passed"
    assert readiness.autonomy_action == "auto_accept"
    assert readiness.autonomy_action_required is True


@pytest.mark.asyncio
async def test_asyncpg_activation_gate_reads_semantic_equivalence_score() -> None:
    database_url = _activation_sql_database_url()
    conn = await _connect_activation_sql_database(database_url)
    fixture: _ActivationSqlFixture | None = None
    store = AsyncpgActivationGateStore(database_url)
    try:
        fixture = await _seed_activation_sql_fixture(conn)

        missing = await store.check_activation_readiness(
            workspace_key=fixture.workspace_key,
            skill_version_id=fixture.skill_version_id,
            require_context_compile_proof=True,
            context_compile_run_id=fixture.context_compile_run_ids["missing"],
            context_artifact_id=fixture.context_artifact_ids["missing"],
            compiled_text_hash=fixture.compiled_text_hashes["missing"],
            context_output_manifest_hash=fixture.output_manifest_hash,
            require_semantic_equivalence=True,
            min_semantic_equivalence_score=0.9,
            allowed_autonomy_actions=("auto_accept",),
        )
        below_threshold = await store.check_activation_readiness(
            workspace_key=fixture.workspace_key,
            skill_version_id=fixture.skill_version_id,
            require_context_compile_proof=True,
            context_compile_run_id=fixture.context_compile_run_ids["below_threshold"],
            context_artifact_id=fixture.context_artifact_ids["below_threshold"],
            compiled_text_hash=fixture.compiled_text_hashes["below_threshold"],
            context_output_manifest_hash=fixture.output_manifest_hash,
            require_semantic_equivalence=True,
            min_semantic_equivalence_score=0.9,
            allowed_autonomy_actions=("auto_accept",),
        )
        passing = await store.check_activation_readiness(
            workspace_key=fixture.workspace_key,
            skill_version_id=fixture.skill_version_id,
            require_context_compile_proof=True,
            context_compile_run_id=fixture.context_compile_run_ids["passing"],
            context_artifact_id=fixture.context_artifact_ids["passing"],
            compiled_text_hash=fixture.compiled_text_hashes["passing"],
            context_output_manifest_hash=fixture.output_manifest_hash,
            require_semantic_equivalence=True,
            min_semantic_equivalence_score=0.9,
            allowed_autonomy_actions=("auto_accept",),
        )
    finally:
        await store.close()
        if fixture is not None:
            await _delete_activation_sql_fixture(conn, fixture)
        await conn.close()

    assert missing.allowed is False
    assert missing.context_semantic_equivalence_score is None
    assert missing.context_safety_status == "passed"
    assert missing.context_equivalence_status == "passed"
    assert missing.context_budget_status == "passed"
    assert missing.blockers == ["context-semantic-equivalence-missing"]

    assert below_threshold.allowed is False
    assert below_threshold.context_semantic_equivalence_score == 0.89
    assert below_threshold.context_safety_status == "passed"
    assert below_threshold.context_equivalence_status == "passed"
    assert below_threshold.context_budget_status == "passed"
    assert below_threshold.blockers == [
        "context-semantic-equivalence-below-threshold"
    ]

    assert passing.allowed is True
    assert passing.context_semantic_equivalence_score == 0.91
    assert passing.context_safety_status == "passed"
    assert passing.context_equivalence_status == "passed"
    assert passing.context_budget_status == "passed"
    assert passing.blockers == []


@pytest.mark.asyncio
async def test_asyncpg_activation_gate_reads_context_value_per_token() -> None:
    database_url = _activation_sql_database_url()
    conn = await _connect_activation_sql_database(database_url)
    fixture: _ActivationSqlFixture | None = None
    store = AsyncpgActivationGateStore(database_url)
    try:
        fixture = await _seed_activation_sql_fixture(conn)

        missing = await store.check_activation_readiness(
            workspace_key=fixture.workspace_key,
            skill_version_id=fixture.skill_version_id,
            require_context_compile_proof=True,
            context_compile_run_id=fixture.context_compile_run_ids["missing"],
            context_artifact_id=fixture.context_artifact_ids["missing"],
            compiled_text_hash=fixture.compiled_text_hashes["missing"],
            context_output_manifest_hash=fixture.output_manifest_hash,
            require_semantic_equivalence=False,
            require_context_value=True,
            min_context_value_per_token=0.0,
            allowed_autonomy_actions=("auto_accept",),
        )
        below_threshold = await store.check_activation_readiness(
            workspace_key=fixture.workspace_key,
            skill_version_id=fixture.skill_version_id,
            require_context_compile_proof=True,
            context_compile_run_id=fixture.context_compile_run_ids["below_threshold"],
            context_artifact_id=fixture.context_artifact_ids["below_threshold"],
            compiled_text_hash=fixture.compiled_text_hashes["below_threshold"],
            context_output_manifest_hash=fixture.output_manifest_hash,
            require_semantic_equivalence=False,
            require_context_value=True,
            min_context_value_per_token=0.0,
            allowed_autonomy_actions=("auto_accept",),
        )
        passing = await store.check_activation_readiness(
            workspace_key=fixture.workspace_key,
            skill_version_id=fixture.skill_version_id,
            require_context_compile_proof=True,
            context_compile_run_id=fixture.context_compile_run_ids["passing"],
            context_artifact_id=fixture.context_artifact_ids["passing"],
            compiled_text_hash=fixture.compiled_text_hashes["passing"],
            context_output_manifest_hash=fixture.output_manifest_hash,
            require_semantic_equivalence=False,
            require_context_value=True,
            min_context_value_per_token=0.0,
            allowed_autonomy_actions=("auto_accept",),
        )
    finally:
        await store.close()
        if fixture is not None:
            await _delete_activation_sql_fixture(conn, fixture)
        await conn.close()

    assert missing.allowed is False
    assert missing.context_value_per_token is None
    assert missing.blockers == ["context-marginal-value-missing"]

    assert below_threshold.allowed is False
    assert below_threshold.context_value_per_token == -0.01
    assert below_threshold.blockers == [
        "context-marginal-value-below-threshold"
    ]

    assert passing.allowed is True
    assert passing.context_value_per_token == 0.01
    assert passing.blockers == []


def _activation_sql_database_url() -> str:
    explicit = os.environ.get("AUTOSKILL_DATABASE_URL") or os.environ.get(
        "SKILLKERNEL_DATABASE_URL"
    )
    if explicit:
        return explicit
    password = os.environ.get("AUTOSKILL_POSTGRES_PASSWORD", "autoskill-dev")
    return f"postgresql://autoskill:{password}@127.0.0.1:55432/autoskill"


async def _connect_activation_sql_database(database_url: str) -> asyncpg.Connection:
    try:
        conn = await asyncpg.connect(database_url)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres activation smoke database unavailable: {exc}")
    try:
        schema_ready = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'autoskill'
                AND table_name = 'context_compile_runs'
                AND column_name = 'semantic_equivalence_score'
            )
            """
        )
    except asyncpg.PostgresError as exc:
        await conn.close()
        pytest.skip(f"autoskill schema unavailable for activation smoke: {exc}")
    if not schema_ready:
        await conn.close()
        pytest.skip(
            "autoskill.context_compile_runs.semantic_equivalence_score is not migrated"
        )
    return conn


async def _seed_activation_sql_fixture(
    conn: asyncpg.Connection,
) -> _ActivationSqlFixture:
    workspace_key = f"activation-semantic-equivalence-{uuid4()}"
    skill_id = uuid4()
    skill_version_id = uuid4()
    context_artifact_ids = {
        "missing": uuid4(),
        "below_threshold": uuid4(),
        "passing": uuid4(),
    }
    context_compile_run_ids = {
        "missing": uuid4(),
        "below_threshold": uuid4(),
        "passing": uuid4(),
    }
    compiled_text_hashes = {
        "missing": f"sha256:compiled-missing-{uuid4().hex}",
        "below_threshold": f"sha256:compiled-below-threshold-{uuid4().hex}",
        "passing": f"sha256:compiled-passing-{uuid4().hex}",
    }
    output_manifest_hash = f"sha256:manifest-{uuid4().hex}"

    workspace_id = await conn.fetchval(
        """
        INSERT INTO autoskill.workspaces (workspace_id, external_key)
        VALUES ($1, $2)
        RETURNING workspace_id
        """,
        uuid4(),
        workspace_key,
    )
    await conn.execute(
        """
        INSERT INTO autoskill.skills (skill_id, workspace_id, slug, name)
        VALUES ($1, $2, $3, $4)
        """,
        skill_id,
        workspace_id,
        f"activation-semantic-equivalence-{uuid4().hex}",
        "Activation semantic equivalence smoke",
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
                "name": "Activation semantic equivalence smoke",
                "description": "SQL fixture for activation semantic equivalence.",
                "granularity": "functional",
            },
            sort_keys=True,
        ),
    )
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
                    "autonomy_decision_id": "activation-semantic-equivalence",
                    "deterministic_checks": {
                        "hard_invariants_passed": True,
                    },
                },
            },
            sort_keys=True,
        ),
    )
    for fixture_key, semantic_score, context_value_per_token in (
        ("missing", None, None),
        ("below_threshold", 0.89, -0.01),
        ("passing", 0.91, 0.01),
    ):
        metadata = {
            "loadability_class": "runtime_on_skill_load",
            "relative_path": "SKILL.md",
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
            context_artifact_ids[fixture_key],
            workspace_id,
            skill_version_id,
            skill_id,
            compiled_text_hashes[fixture_key],
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
              $1, $2, $3, $4, $5, 'autoskill-compiler.test',
              $6, $7, 120, 0.42, $8, 'passed', '{}'::jsonb
            )
            """,
            context_compile_run_ids[fixture_key],
            workspace_id,
            skill_id,
            skill_version_id,
            context_artifact_ids[fixture_key],
            f"sha256:skillir-{fixture_key}-{skill_version_id.hex}",
            output_manifest_hash,
            semantic_score,
        )
    return _ActivationSqlFixture(
        workspace_key=workspace_key,
        skill_id=skill_id,
        skill_version_id=skill_version_id,
        context_artifact_ids=context_artifact_ids,
        context_compile_run_ids=context_compile_run_ids,
        compiled_text_hashes=compiled_text_hashes,
        output_manifest_hash=output_manifest_hash,
    )


async def _delete_activation_sql_fixture(
    conn: asyncpg.Connection,
    fixture: _ActivationSqlFixture,
) -> None:
    workspace_id = await conn.fetchval(
        "SELECT workspace_id FROM autoskill.workspaces WHERE external_key = $1",
        fixture.workspace_key,
    )
    if workspace_id is None:
        return
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM autoskill.context_compile_runs WHERE workspace_id = $1",
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.runtime_artifacts WHERE workspace_id = $1",
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.context_artifacts WHERE workspace_id = $1",
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.evaluations WHERE workspace_id = $1",
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.skill_components WHERE skill_version_id = $1",
            fixture.skill_version_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.skill_ir_revisions WHERE skill_version_id = $1",
            fixture.skill_version_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.skill_versions WHERE skill_version_id = $1",
            fixture.skill_version_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.skill_state_records WHERE workspace_id = $1",
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.memory_contracts WHERE workspace_id = $1",
            workspace_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.skills WHERE skill_id = $1",
            fixture.skill_id,
        )
        await conn.execute(
            "DELETE FROM autoskill.workspaces WHERE workspace_id = $1",
            workspace_id,
        )
