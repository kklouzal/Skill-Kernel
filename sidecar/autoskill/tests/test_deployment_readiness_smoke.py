import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "autoskill_deployment_readiness_smoke.py"
SPEC = importlib.util.spec_from_file_location(
    "autoskill_deployment_readiness_smoke",
    SCRIPT_PATH,
)
assert SPEC is not None
smoke = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(smoke)


def test_deployment_readiness_smoke_summary_is_content_safe_and_assertable() -> None:
    response = {
        "workspace_id": "deployment-readiness-smoke-test",
        "ready": True,
        "blockers": [],
        "warnings": [],
        "checks": {
            "storage_plane_schema_ready": {
                "status": "passed",
                "reachable": True,
                "pgvector_available": True,
                "migration_version": "0001_autoskill_schema",
                "schema_contract": "0001_autoskill_schema",
                "missing_tables": [],
            },
            "read_model_contract_compatible": {
                "status": "passed",
                "compatible": True,
                "reason_code": "read_model_contract_compatible",
                "advertised_contract_version": "skillkernel.readmodels.v1",
                "expected_contract_version": "skillkernel.readmodels.v1",
                "missing_catalogs": [],
            },
            "scheduler_worker_heartbeat": {
                "status": "passed",
                "observed": 1,
                "ready_worker_ids": ["deployment-readiness-smoke:scheduler"],
            },
            "active_executor_profile": {
                "status": "passed",
                "count": 1,
                "profile_keys": ["deployment-readiness-smoke-executor"],
                "compatible_profiles": [
                    {
                        "profile_key": "deployment-readiness-smoke-executor",
                        "status": "active",
                        "agent_backend": "codex",
                        "model_family": "gpt",
                        "sandbox": "danger-full-access",
                        "os_name": "linux",
                        "tool_count": 1,
                        "tool_keys": ["exec"],
                        "binary_count": 2,
                        "binary_keys": ["git", "uv"],
                        "api_contract_count": 1,
                        "api_contract_keys": ["skillkernel"],
                        "permission_keys": ["filesystem"],
                        "reason_codes": [],
                    }
                ],
                "blocked_profiles": [],
            },
            "qualified_text_model_profile": {
                "status": "passed",
                "count": 1,
                "profile_keys": ["deployment-readiness-smoke-text"],
            },
            "active_embedding_profile": {
                "status": "passed",
                "count": 1,
                "profile_keys": ["deployment-readiness-smoke-embedding"],
            },
            "active_broker_policy": {
                "status": "passed",
                "version": "deployment-readiness-smoke.policy.v1",
                "broker_policy_version_id": "policy-id",
            },
            "broker_replay_corpus": {
                "status": "passed",
                "sampled": 1,
                "operator_reviewed": 1,
                "source_linked": 1,
                "telemetry_derived": 1,
                "degraded_fidelity": 0,
                "expected_decisions": {"skill_hint": 1},
                "episode_keys": ["internal-key-is-not-returned-by-summary"],
            },
            "operator_reviewed_broker_replay_corpus": {
                "status": "passed",
                "operator_reviewed": 1,
                "sampled": 1,
            },
        },
    }

    summary = smoke._summarize_response(
        response=response,
        seeded={
            "workspace_id": "deployment-readiness-smoke-test",
            "broker_policy_version_id": "policy-id",
            "replay_episode_id": "replay-id",
            "retrieval_log_id": "retrieval-id",
            "scheduler_worker_id": "deployment-readiness-smoke:scheduler",
        },
        smoke_id="deployment-readiness-smoke-test",
    )

    smoke._assert_smoke(summary)
    assert summary["raw_evidence_returned"] is False
    assert summary["runtime_skill_writes"] is False
    assert summary["activation_authority"] is False
    assert summary["live_openclaw_mutation"] is False
    assert "episode_keys" not in summary["key_checks"]["broker_replay_corpus"]


def test_deployment_readiness_smoke_asserts_failed_readiness() -> None:
    with pytest.raises(SystemExit, match="deployment readiness was not ready"):
        smoke._assert_smoke(
            {
                "ok": False,
                "blockers": ["storage_plane_schema_ready"],
                "key_checks": {},
                "raw_evidence_returned": False,
                "runtime_skill_writes": False,
                "activation_authority": False,
                "live_openclaw_mutation": False,
            }
        )
