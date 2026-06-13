from __future__ import annotations

import asyncio
from uuid import uuid4

from autoskill.db.activation import NullActivationGateStore, _activation_blockers


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
    assert readiness.context_safety_status == "passed"
    assert readiness.context_equivalence_status == "passed"
    assert readiness.context_budget_status == "passed"
    assert readiness.autonomy_action == "auto_accept"
    assert readiness.autonomy_action_required is True
