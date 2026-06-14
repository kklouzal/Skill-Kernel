import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from autoskill.db.activation import ActivationReadiness

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "autoskill_activation_context_smoke.py"
SPEC = importlib.util.spec_from_file_location(
    "autoskill_activation_context_smoke",
    SCRIPT_PATH,
)
assert SPEC is not None
smoke = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(smoke)


def test_activation_context_smoke_summary_is_content_safe_and_assertable() -> None:
    skill_version_id = uuid4()
    min_context_value_per_token = 0.0
    min_semantic_equivalence_score = 0.9

    summary = {
        "schema": "autoskill.activation-context-smoke.v1",
        "ok": True,
        "workspace_id": "activation-context-smoke-test",
        "smoke_id": "activation-context-smoke-test",
        "skill_id": str(uuid4()),
        "skill_version_id": str(skill_version_id),
        "min_context_value_per_token": min_context_value_per_token,
        "min_semantic_equivalence_score": min_semantic_equivalence_score,
        "cases": [
            _case_summary(
                "missing",
                skill_version_id=skill_version_id,
                min_context_value_per_token=min_context_value_per_token,
                min_semantic_equivalence_score=min_semantic_equivalence_score,
                context_value_per_token=None,
                allowed=False,
                blockers=["context-marginal-value-missing"],
            ),
            _case_summary(
                "below_threshold",
                skill_version_id=skill_version_id,
                min_context_value_per_token=min_context_value_per_token,
                min_semantic_equivalence_score=min_semantic_equivalence_score,
                context_value_per_token=-0.01,
                allowed=False,
                blockers=["context-marginal-value-below-threshold"],
            ),
            _case_summary(
                "passing",
                skill_version_id=skill_version_id,
                min_context_value_per_token=min_context_value_per_token,
                min_semantic_equivalence_score=min_semantic_equivalence_score,
                context_value_per_token=0.02,
                allowed=True,
                blockers=[],
            ),
        ],
        "raw_evidence_returned": False,
        "runtime_skill_writes": False,
        "activation_authority": False,
        "live_openclaw_mutation": False,
    }

    smoke._assert_smoke(summary)
    assert summary["raw_evidence_returned"] is False
    assert summary["runtime_skill_writes"] is False
    assert summary["activation_authority"] is False
    assert summary["live_openclaw_mutation"] is False
    assert summary["cases"][2]["context_value_per_token"] == 0.02
    assert summary["cases"][2]["context_semantic_equivalence_score"] == 0.95
    assert summary["cases"][2]["effective_min_context_value_per_token"] == 0.0
    assert summary["cases"][2]["effective_min_semantic_equivalence_score"] == 0.9


def test_activation_context_smoke_rejects_missing_case_that_allows_activation() -> None:
    summary = _assertable_summary()
    summary["cases"][0]["allowed"] = True
    summary["cases"][0]["blockers"] = []

    with pytest.raises(SystemExit, match="missing activation allowed"):
        smoke._assert_smoke(summary)


def test_activation_context_smoke_rejects_passing_case_below_policy() -> None:
    summary = _assertable_summary()
    summary["cases"][2]["context_value_per_token"] = -0.01

    with pytest.raises(SystemExit, match="passing case did not meet"):
        smoke._assert_smoke(summary)


def test_activation_context_smoke_derives_cases_from_positive_threshold() -> None:
    context_cases = smoke._context_cases(0.05)

    assert context_cases["missing"]["context_value_per_token"] is None
    assert context_cases["below_threshold"]["context_value_per_token"] == 0.025
    assert context_cases["below_threshold"]["context_value_per_token"] < 0.05
    assert context_cases["passing"]["context_value_per_token"] == 0.05
    assert context_cases["passing"]["context_value_per_token"] >= 0.05

    summary = _assertable_summary(min_context_value_per_token=0.05)
    summary["cases"][1]["context_value_per_token"] = context_cases[
        "below_threshold"
    ]["context_value_per_token"]
    summary["cases"][2]["context_value_per_token"] = context_cases["passing"][
        "context_value_per_token"
    ]

    smoke._assert_smoke(summary)


def test_activation_context_smoke_echoes_and_asserts_non_default_thresholds() -> None:
    summary = _assertable_summary(
        min_context_value_per_token=0.05,
        min_semantic_equivalence_score=0.95,
    )
    summary["cases"][1]["context_value_per_token"] = 0.025
    summary["cases"][2]["context_value_per_token"] = 0.05

    smoke._assert_smoke(summary)
    for case in summary["cases"]:
        assert case["effective_min_context_value_per_token"] == 0.05
        assert case["effective_min_semantic_equivalence_score"] == 0.95


@pytest.mark.parametrize(
    ("case_index", "policy_key", "case_key", "message"),
    [
        (
            0,
            "min_context_value_per_token",
            "effective_min_context_value_per_token",
            "context-value threshold",
        ),
        (
            2,
            "min_semantic_equivalence_score",
            "effective_min_semantic_equivalence_score",
            "semantic-equivalence threshold",
        ),
    ],
)
def test_activation_context_smoke_rejects_mismatched_effective_thresholds(
    case_index: int,
    policy_key: str,
    case_key: str,
    message: str,
) -> None:
    summary = _assertable_summary(
        min_context_value_per_token=0.05,
        min_semantic_equivalence_score=0.95,
    )
    summary["cases"][1]["context_value_per_token"] = 0.025
    summary["cases"][2]["context_value_per_token"] = 0.05
    summary["cases"][case_index][case_key] = summary[policy_key] - 0.01

    with pytest.raises(SystemExit, match=message):
        smoke._assert_smoke(summary)


def test_activation_context_smoke_rejects_missing_semantic_proof() -> None:
    summary = _assertable_summary()
    summary["cases"][2]["context_semantic_equivalence_score"] = None

    with pytest.raises(SystemExit, match="semantic equivalence proof"):
        smoke._assert_smoke(summary)


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--min-context-value-per-token", "nan"),
        ("--min-context-value-per-token", "inf"),
        ("--min-context-value-per-token", "-0.01"),
        ("--min-semantic-equivalence-score", "nan"),
        ("--min-semantic-equivalence-score", "inf"),
        ("--min-semantic-equivalence-score", "-0.01"),
        ("--min-semantic-equivalence-score", "1.01"),
    ],
)
def test_activation_context_smoke_rejects_invalid_thresholds_before_run(
    flag: str,
    value: str,
) -> None:
    with pytest.raises(SystemExit):
        smoke._parse_args([flag, value])


def test_activation_context_smoke_accepts_default_threshold_policy() -> None:
    args = smoke._parse_args([])

    assert args.min_context_value_per_token == 0.0
    assert args.min_semantic_equivalence_score == 0.9


def test_activation_context_smoke_uses_distinct_compiled_hashes_per_case() -> None:
    compiled_hashes = {
        case_name: f"sha256:compiled-{case_name}-{uuid4().hex}"
        for case_name in smoke.CONTEXT_CASE_EXPECTATIONS
    }

    assert set(compiled_hashes) == set(smoke.CONTEXT_CASE_EXPECTATIONS)
    assert len(set(compiled_hashes.values())) == len(smoke.CONTEXT_CASE_EXPECTATIONS)


def test_activation_context_smoke_cleanup_skips_absent_optional_tables() -> None:
    statements = smoke._cleanup_statements_for_existing_tables(
        smoke.REQUIRED_CLEANUP_TABLES
    )
    rendered = "\n".join(statements)

    assert "autoskill.context_compile_runs" in rendered
    assert "autoskill.context_artifacts" in rendered
    assert "autoskill.skill_versions" in rendered
    assert "autoskill.workspaces" in rendered
    assert "autoskill.runtime_artifacts" not in rendered
    assert "autoskill.skill_components" not in rendered
    assert "autoskill.skill_ir_revisions" not in rendered
    assert "autoskill.skill_state_records" not in rendered
    assert "autoskill.memory_contracts" not in rendered


def test_activation_context_smoke_cleanup_retains_existing_optional_tables() -> None:
    statements = smoke._cleanup_statements_for_existing_tables(
        smoke.REQUIRED_CLEANUP_TABLES
        | {
            "runtime_artifacts",
            "skill_components",
            "skill_ir_revisions",
            "skill_state_records",
            "memory_contracts",
        }
    )
    rendered = "\n".join(statements)

    assert "autoskill.runtime_artifacts" in rendered
    assert "autoskill.skill_components" in rendered
    assert "autoskill.skill_ir_revisions" in rendered
    assert "autoskill.skill_state_records" in rendered
    assert "autoskill.memory_contracts" in rendered


def test_activation_context_smoke_cleanup_requires_core_tables() -> None:
    existing_tables = smoke.REQUIRED_CLEANUP_TABLES - {"context_compile_runs"}

    with pytest.raises(RuntimeError, match="context_compile_runs"):
        smoke._cleanup_statements_for_existing_tables(existing_tables)


def _assertable_summary(
    min_context_value_per_token: float = 0.0,
    min_semantic_equivalence_score: float = 0.9,
) -> dict:
    skill_version_id = uuid4()
    return {
        "ok": True,
        "min_context_value_per_token": min_context_value_per_token,
        "min_semantic_equivalence_score": min_semantic_equivalence_score,
        "cases": [
            _case_summary(
                "missing",
                skill_version_id=skill_version_id,
                min_context_value_per_token=min_context_value_per_token,
                min_semantic_equivalence_score=min_semantic_equivalence_score,
                context_value_per_token=None,
                allowed=False,
                blockers=["context-marginal-value-missing"],
            ),
            _case_summary(
                "below_threshold",
                skill_version_id=skill_version_id,
                min_context_value_per_token=min_context_value_per_token,
                min_semantic_equivalence_score=min_semantic_equivalence_score,
                context_value_per_token=-0.01,
                allowed=False,
                blockers=["context-marginal-value-below-threshold"],
            ),
            _case_summary(
                "passing",
                skill_version_id=skill_version_id,
                min_context_value_per_token=min_context_value_per_token,
                min_semantic_equivalence_score=min_semantic_equivalence_score,
                context_value_per_token=0.02,
                allowed=True,
                blockers=[],
            ),
        ],
        "raw_evidence_returned": False,
        "runtime_skill_writes": False,
        "activation_authority": False,
        "live_openclaw_mutation": False,
    }


def _case_summary(
    case_name: str,
    *,
    skill_version_id: object,
    min_context_value_per_token: float,
    min_semantic_equivalence_score: float,
    context_value_per_token: float | None,
    allowed: bool,
    blockers: list[str],
) -> dict:
    return smoke._case_summary(
        case_name,
        ActivationReadiness(
            allowed=allowed,
            skill_version_id=skill_version_id,
            executor_profile_id=None,
            scanner_status="passed",
            evaluator_status="passed",
            latest_evaluation_status="passed",
            compatibility_status=None,
            context_compile_run_id=uuid4(),
            context_artifact_id=uuid4(),
            context_compile_status="passed",
            context_semantic_equivalence_score=0.95,
            context_value_per_token=context_value_per_token,
            context_safety_status="passed",
            context_equivalence_status="passed",
            context_budget_status="passed",
            blockers=blockers,
            autonomy_action="auto_accept",
            autonomy_decision_id="activation-context-smoke",
            autonomy_action_required=True,
        ),
        min_context_value_per_token=min_context_value_per_token,
        min_semantic_equivalence_score=min_semantic_equivalence_score,
    )
