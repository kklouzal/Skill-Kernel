import asyncio
from uuid import uuid4

from autoskill.api.app import EvaluationRunRequest, create_app
from autoskill.db.evaluations import EvaluationRunItem, EvaluationRunResult
from autoskill.services.evaluator import evaluate_proposal_gate


def skill_ir() -> dict[str, object]:
    return {
        "schema": "skillir.v1",
        "slug": "autoskill-message-received-repair",
        "applicability": ["Repeated message_received workflow."],
        "steps": ["Repair the workflow."],
        "verification": ["Verify the repair."],
        "failure_handling": ["Leave a safe no-op."],
        "do_not_use_when": ["A matching active skill already exists."],
        "never": ["Do not include secrets or activate skills from proposal evaluation."],
        "evidence_ids": [str(uuid4())],
    }


def planned_probes() -> list[dict[str, object]]:
    evidence_ids = skill_ir()["evidence_ids"]
    return [
        {
            "probe_hash": "target-hash",
            "kind": "target",
            "spec": {"evidence_ids": evidence_ids, "checks": ["traceability"]},
            "expected": {"status": "pass"},
        },
        {
            "probe_hash": "no-skill-hash",
            "kind": "no_skill_control",
            "spec": {"evidence_ids": evidence_ids},
            "expected": {"candidate_must_improve_or_reduce_retries": True},
        },
        {
            "probe_hash": "regression-hash",
            "kind": "regression",
            "spec": {"checks": ["scope"]},
            "expected": {"status": "pass"},
        },
    ]


def replayed_probes() -> list[dict[str, object]]:
    probes = planned_probes()
    probes[1] = {
        **probes[1],
        "spec": {
            "evidence_ids": skill_ir()["evidence_ids"],
            "intervention_replay": {
                "no_skill": {"success": False, "retries": 3, "latency_ms": 1200},
                "skill_visible": {"success": True, "retries": 1, "latency_ms": 800},
            },
        },
    }
    return probes


def test_proposal_gate_reports_target_no_skill_and_regression_results() -> None:
    result = evaluate_proposal_gate(
        skill_ir=skill_ir(),
        scanner_status="passed",
        probes=planned_probes(),
    )

    payload = result.to_json()

    assert payload["status"] == "needs_intervention"
    assert [probe["kind"] for probe in payload["probe_results"]] == [
        "target",
        "no_skill_control",
        "regression",
    ]
    assert payload["probe_results"][0]["status"] == "passed"
    assert payload["probe_results"][1]["status"] == "needs_intervention"
    assert payload["probe_results"][2]["status"] == "passed"
    assert payload["reason_codes"] == ["intervention-required"]


def test_proposal_gate_passes_with_intervention_replay_improvement() -> None:
    result = evaluate_proposal_gate(
        skill_ir=skill_ir(),
        scanner_status="passed",
        probes=replayed_probes(),
    )

    payload = result.to_json()

    assert payload["status"] == "passed"
    assert payload["probe_results"][1]["status"] == "passed"
    assert (
        payload["probe_results"][1]["reason"]
        == "skill-visible replay outperformed no-skill control"
    )
    assert payload["reason_codes"] == ["all-deterministic-probes-passed"]


def test_proposal_gate_fails_when_intervention_replay_does_not_improve() -> None:
    probes = replayed_probes()
    probes[1] = {
        **probes[1],
        "spec": {
            "evidence_ids": skill_ir()["evidence_ids"],
            "intervention_replay": {
                "no_skill": {"success": True, "retries": 1},
                "skill_visible": {"success": True, "retries": 2},
            },
        },
    }

    result = evaluate_proposal_gate(
        skill_ir=skill_ir(),
        scanner_status="passed",
        probes=probes,
    )

    payload = result.to_json()

    assert payload["status"] == "failed"
    assert payload["probe_results"][1]["status"] == "failed"
    assert payload["reason_codes"] == ["probe-failed"]


def test_proposal_gate_blocks_when_scanner_failed() -> None:
    result = evaluate_proposal_gate(
        skill_ir=skill_ir(),
        scanner_status="blocked",
        probes=planned_probes(),
    )

    payload = result.to_json()

    assert payload["status"] == "blocked"
    assert {probe["status"] for probe in payload["probe_results"]} == {"blocked"}
    assert payload["reason_codes"] == ["scanner-blocked"]


class MemoryEvaluationStore:
    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> EvaluationRunResult:
        return EvaluationRunResult(
            scanned=1,
            evaluated=1,
            blocked=0,
            failed=0,
            needs_intervention=1,
            passed=0,
            evaluations=[
                EvaluationRunItem(
                    evaluation_id=uuid4(),
                    skill_version_id=uuid4(),
                    status="needs_intervention",
                    result={"workspace_key": workspace_key, "limit": limit},
                )
            ],
        )


def test_evaluation_run_api_uses_configured_store() -> None:
    app = create_app(evaluation_store=MemoryEvaluationStore())
    route = next(route for route in app.routes if route.path == "/v1/evaluations/run")

    async def run():
        return await route.endpoint(
            request=EvaluationRunRequest(workspace_id="dev-01", limit=7)
        )

    response = asyncio.run(run())

    assert response.evaluated == 1
    assert response.needs_intervention == 1
    assert response.evaluations[0]["result"] == {"workspace_key": "dev-01", "limit": 7}
