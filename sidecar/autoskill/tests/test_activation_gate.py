from __future__ import annotations

from autoskill.db.activation import _activation_blockers


def _row(
    *,
    evaluator_status: str = "needs_intervention",
    latest_evaluation_status: str = "needs_intervention",
    autonomy_action: str | None = "stage_canary",
    autonomy_hard_invariants_passed: bool = True,
) -> dict[str, object]:
    return {
        "scanner_status": "passed",
        "evaluator_status": evaluator_status,
        "latest_evaluation_status": latest_evaluation_status,
        "compatibility_status": None,
        "context_compile_run_id": None,
        "context_artifact_id": None,
        "context_compile_status": None,
        "context_safety_status": None,
        "context_equivalence_status": None,
        "context_budget_status": None,
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
