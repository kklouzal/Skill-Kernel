import asyncio
from uuid import uuid4

from autoskill.api.app import EvaluationRunRequest, create_app
from autoskill.db.evaluations import (
    EvaluationRunItem,
    EvaluationRunResult,
    _attach_contrastive_replays,
    _finish_evaluation,
)
from autoskill.db.observability import TraceSpanRecord
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


def test_proposal_gate_attaches_contrastive_replay_from_evidence() -> None:
    workspace_id = uuid4()
    no_skill_evidence_id = uuid4()
    skill_visible_evidence_id = uuid4()
    probe = {
        "probe_hash": "no-skill-hash",
        "kind": "no_skill_control",
        "maturity": "observed",
        "spec": {
            "candidate_slug": "demo-skill",
            "evidence_ids": [str(no_skill_evidence_id), str(skill_visible_evidence_id)],
        },
        "expected": {"candidate_must_improve_or_reduce_retries": True},
    }
    conn = FakeContrastiveConnection(
        [
            {
                "evidence_id": no_skill_evidence_id,
                "payload": {
                    "redacted_payload": {
                        "autoskill_replay": {
                            "candidate_slug": "demo-skill",
                            "mode": "no_skill",
                            "success": False,
                            "retries": 3,
                        }
                    }
                },
            },
            {
                "evidence_id": skill_visible_evidence_id,
                "payload": {
                    "redacted_payload": {
                        "autoskill_replay": {
                            "candidate_slug": "demo-skill",
                            "mode": "skill_visible",
                            "success": True,
                            "retries": 1,
                        }
                    }
                },
            },
        ]
    )

    async def run():
        enriched, replays = await _attach_contrastive_replays(
            conn,
            workspace_id=workspace_id,
            probes=[probe],
        )
        return enriched, replays

    enriched, replays = asyncio.run(run())
    result = evaluate_proposal_gate(
        skill_ir=skill_ir(),
        scanner_status="passed",
        probes=[planned_probes()[0], enriched[0], planned_probes()[2]],
    )

    assert enriched[0]["maturity"] == "contrastive"
    assert enriched[0]["spec"]["intervention_replay"]["skill_visible"]["retries"] == 1.0
    assert replays[0]["probe_hash"] == "no-skill-hash"
    assert conn.updated_probe_hashes == ["no-skill-hash"]
    assert set(conn.maturity_evidence_ids) == {no_skill_evidence_id, skill_visible_evidence_id}
    assert result.status == "passed"


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


def test_evaluation_finish_records_executor_profile_compatibility() -> None:
    conn = FakeEvaluationConnection()
    workspace_id = uuid4()
    evaluation_id = uuid4()
    skill_version_id = uuid4()
    executor_profile_id = uuid4()
    trace_id = uuid4()
    span_id = uuid4()
    parent_span_id = uuid4()

    async def run() -> None:
        await _finish_evaluation(
            conn,
            workspace_id=workspace_id,
            evaluation_id=evaluation_id,
            skill_version_id=skill_version_id,
            executor_profile_id=executor_profile_id,
            status="needs_intervention",
            result={"reason_codes": ["intervention-required"]},
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
        )

    asyncio.run(run())

    compatibility = conn.compatibility_calls[0]
    assert compatibility["workspace_id"] == workspace_id
    assert compatibility["skill_version_id"] == skill_version_id
    assert compatibility["executor_profile_id"] == executor_profile_id
    assert compatibility["status"] == "degraded"
    assert compatibility["evidence"]["source"] == "proposal_gate_evaluation"
    assert compatibility["evidence"]["evaluation_id"] == str(evaluation_id)
    assert compatibility["evidence"]["reason_codes"] == ["intervention-required"]
    assert compatibility["evidence"]["trace_id"] == str(trace_id)


class MemoryEvaluationStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run_pending_proposal_gates(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
        trace_id=None,
        span_id=None,
        parent_span_id=None,
    ) -> EvaluationRunResult:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "limit": limit,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
            }
        )
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
                    executor_profile_id=None,
                    status="needs_intervention",
                    result={"workspace_key": workspace_key, "limit": limit},
                )
            ],
        )


def test_evaluation_run_api_uses_configured_store() -> None:
    observability = MemoryObservabilityStore()
    evaluations = MemoryEvaluationStore()
    trace_id = uuid4()
    parent_span_id = uuid4()
    app = create_app(
        evaluation_store=evaluations,
        observability_store=observability,
    )
    route = next(route for route in app.routes if route.path == "/v1/evaluations/run")

    async def run():
        return await route.endpoint(
            request=EvaluationRunRequest(
                workspace_id="dev-01",
                limit=7,
                trace_id=trace_id,
                span_id=parent_span_id,
            )
        )

    response = asyncio.run(run())

    assert response.evaluated == 1
    assert response.needs_intervention == 1
    assert response.evaluations[0]["result"] == {"workspace_key": "dev-01", "limit": 7}
    assert observability.started[0].trace_id == trace_id
    assert observability.started[0].parent_span_id == parent_span_id
    assert observability.started[0].operation_kind == "evaluator"
    assert observability.started[0].safe_attributes == {"source": "api", "limit": 7}
    assert evaluations.calls[0]["trace_id"] == trace_id
    assert evaluations.calls[0]["span_id"] == observability.started[0].span_id
    assert evaluations.calls[0]["parent_span_id"] == parent_span_id
    assert observability.finished[0]["status"] == "ok"
    assert observability.finished[0]["safe_attributes"]["evaluated"] == 1
    assert {ref["object_type"] for ref in observability.finished[0]["object_refs"]} == {
        "evaluation",
        "skill_version",
    }


class MemoryObservabilityStore:
    def __init__(self) -> None:
        self.started: list[TraceSpanRecord] = []
        self.finished: list[dict[str, object]] = []

    async def start_span(
        self,
        *,
        workspace_key: str,
        operation_name: str,
        operation_kind: str,
        trace_id=None,
        parent_span_id=None,
        safe_attributes=None,
        object_refs=None,
    ) -> TraceSpanRecord:
        from datetime import UTC, datetime

        span = TraceSpanRecord(
            trace_id=trace_id or uuid4(),
            span_id=uuid4(),
            parent_span_id=parent_span_id,
            workspace_id=None,
            workspace_key=workspace_key,
            operation_name=operation_name,
            operation_kind=operation_kind,
            status="running",
            safe_attributes=safe_attributes or {},
            object_refs=object_refs or [],
            started_at=datetime.now(UTC),
            ended_at=None,
        )
        self.started.append(span)
        return span

    async def finish_span(
        self,
        *,
        span_id,
        status="ok",
        safe_attributes=None,
        object_refs=None,
    ) -> TraceSpanRecord | None:
        self.finished.append(
            {
                "span_id": span_id,
                "status": status,
                "safe_attributes": safe_attributes or {},
                "object_refs": object_refs or [],
            }
        )
        return None

    async def link_spans(self, **_kwargs) -> bool:
        return True

    async def list_trace(self, **_kwargs) -> list[TraceSpanRecord]:
        return []


class FakeContrastiveConnection:
    def __init__(self, evidence_rows: list[dict[str, object]]) -> None:
        self.evidence_rows = evidence_rows
        self.updated_probe_hashes: list[str] = []
        self.maturity_evidence_ids: list[object] = []

    async def fetch(self, _query: str, *_args):
        return self.evidence_rows

    async def execute(self, query: str, *_args):
        if "UPDATE autoskill.probes" in query:
            self.updated_probe_hashes.append(str(_args[1]))
        if "INSERT INTO autoskill.evidence_maturity" in query:
            self.maturity_evidence_ids.append(_args[1])


class FakeEvaluationConnection:
    def __init__(self) -> None:
        self.compatibility_calls: list[dict[str, object]] = []

    async def execute(self, query: str, *_args):
        if "INSERT INTO autoskill.skill_profile_compatibility" not in query:
            return "UPDATE 1"
        import json

        self.compatibility_calls.append(
            {
                "workspace_id": _args[0],
                "skill_version_id": _args[1],
                "executor_profile_id": _args[2],
                "status": _args[3],
                "evidence": json.loads(_args[4]),
            }
        )
        return "INSERT 1"
