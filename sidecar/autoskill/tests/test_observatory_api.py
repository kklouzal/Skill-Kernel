import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from autoskill.api.app import ObservatoryActionRequest, create_app
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.config import get_settings
from autoskill.core.enums import TrustClass
from autoskill.core.events import EventEnvelope
from autoskill.db.events import NullEventStore
from autoskill.db.observability import TraceSpanRecord, TraceSummaryRecord
from autoskill.db.retrieval import RetrievalLog
from autoskill.services.observatory import build_observatory_snapshot
from fastapi import HTTPException


class MemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def append_record(self, record: AuditRecord, *, workspace_key: str) -> AuditRecord:
        previous_hash = self.records[-1].audit_hash if self.records else None
        sealed = record.model_copy(update={"previous_hash": previous_hash}).sealed()
        self.records.append(sealed)
        return sealed

    async def list_recent(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        return list(reversed(self.records))[:limit]

    async def verify_chain(self, *, workspace_key: str | None = None, limit: int = 1000) -> bool:
        return verify_hash_chain(self.records[-limit:])


class MemoryRetrievalLogStore:
    def __init__(self, logs: list[RetrievalLog]) -> None:
        self.logs = logs

    async def list_recent_logs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[RetrievalLog]:
        return self.logs[:limit]

    async def get_log(
        self,
        *,
        workspace_key: str | None = None,
        retrieval_log_id,
    ) -> RetrievalLog | None:
        for log in self.logs:
            if log.retrieval_log_id == retrieval_log_id:
                return log
        return None


class MemoryTraceStore:
    def __init__(self, spans: list[TraceSpanRecord]) -> None:
        self.spans = spans

    async def list_trace(self, *, trace_id, limit: int = 100, **_kwargs) -> list[TraceSpanRecord]:
        return [span for span in self.spans if span.trace_id == trace_id][:limit]

    async def list_traces(self, *, limit: int = 50, **_kwargs) -> list[TraceSummaryRecord]:
        summaries: list[TraceSummaryRecord] = []
        trace_ids = []
        for span in self.spans:
            if span.trace_id not in trace_ids:
                trace_ids.append(span.trace_id)
        for trace_id in trace_ids:
            spans = [span for span in self.spans if span.trace_id == trace_id]
            summaries.append(
                TraceSummaryRecord(
                    trace_id=trace_id,
                    workspace_key=spans[0].workspace_key,
                    span_count=len(spans),
                    statuses=sorted({span.status for span in spans}),
                    operation_kinds=sorted({span.operation_kind for span in spans}),
                    object_refs=[
                        ref for span in spans for ref in span.object_refs if isinstance(ref, dict)
                    ],
                    started_at=min(span.started_at for span in spans),
                    last_event_at=max((span.ended_at or span.started_at) for span in spans),
                )
            )
        return summaries[:limit]

    async def operator_metrics(self, **_kwargs):
        return {
            "captured_at": datetime.now(UTC).isoformat(),
            "metrics": {},
            "dashboards": {},
        }


def _routes(app):
    return {
        (route.path, next(iter(route.methods - {"HEAD", "OPTIONS"}))): route
        for route in app.routes
        if hasattr(route, "methods")
    }


def test_observatory_summary_exposes_all_pipeline_stations_and_truth_states() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/summary", "GET")]

    async def run():
        return await route.endpoint(workspace_id="dev-01", window_minutes=30)

    response = asyncio.run(run())
    snapshot = response.snapshot

    assert snapshot["schema_version"] == "skillkernel.observatory.v1"
    assert snapshot["workspace_id"] == "dev-01"
    assert len(snapshot["pipeline"]["stations"]) == 24
    assert len(snapshot["subsystems"]) == 8
    assert snapshot["global_health"] in {"blocked", "degraded", "unknown"}
    assert any(
        issue["reason_codes"] == ["database-not-configured"] for issue in snapshot["issue_board"]
    )
    for station in snapshot["pipeline"]["stations"]:
        assert {"input", "processing", "output", "quality", "control", "evidence"} == set(
            station["signal_contract"]
        )
        assert station["data_quality"]["raw_content_available"] is False
        assert station["details_url"].startswith("/admin/components/")


def test_observatory_pipeline_component_and_search_routes_are_bounded() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    routes = _routes(app)

    async def run():
        pipeline = await routes[("/admin/api/v1/pipeline", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
        )
        component = await routes[("/admin/api/v1/components/{component_id}", "GET")].endpoint(
            component_id="scheduler_jobs",
            workspace_id="dev-01",
            window_minutes=10,
        )
        search = await routes[("/admin/api/v1/search", "GET")].endpoint(
            workspace_id="dev-01",
            query="scheduler",
            limit=5,
        )
        return pipeline, component, search

    pipeline, component, search = asyncio.run(run())

    assert "pipeline" in pipeline.snapshot
    assert component.object["object_type"] == "component"
    assert component.object["object_id"] == "scheduler_jobs"
    assert component.object["content_policy"]["raw_available"] is False
    assert search.results
    assert len(search.results) <= 5
    assert all(
        "scheduler"
        in " ".join(
            [
                result["object_id"],
                result["title"],
                result["summary"],
                result["url"],
            ]
        ).lower()
        for result in search.results
    )


def test_observatory_collection_routes_return_bounded_content_safe_envelopes() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    routes = _routes(app)

    async def run():
        components = await routes[("/admin/api/v1/components", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
            limit=2,
        )
        reason_codes = await routes[("/admin/api/v1/reason-codes", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
            limit=3,
        )
        playbooks = await routes[("/admin/api/v1/playbooks", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
            limit=3,
        )
        ready = await routes[("/admin/api/v1/health/ready", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
        )
        return components, reason_codes, playbooks, ready

    components, reason_codes, playbooks, ready = asyncio.run(run())

    assert components.collection["object_type"] == "component"
    assert components.collection["count"] == 2
    assert components.collection["has_more"] is True
    assert components.collection["content_policy"]["raw_available"] is False
    assert len(reason_codes.collection["items"]) == 3
    assert reason_codes.collection["source"] == "observatory_snapshot.reason_code_catalog"
    assert playbooks.collection["items"]
    assert playbooks.collection["content_policy"]["raw_available"] is False
    assert ready.object["schema_version"] == "skillkernel.observatory.ready.v1"
    assert ready.object["ready"] is False


def test_observatory_required_admin_route_matrix_and_microscope_objects_exist() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    routes = _routes(app)

    required_routes = {
        ("/admin/api/v1/health/live", "GET"),
        ("/admin/api/v1/health/ready", "GET"),
        ("/admin/api/v1/search", "GET"),
        ("/admin/api/v1/components", "GET"),
        ("/admin/api/v1/components/{component_id}/metrics", "GET"),
        ("/admin/api/v1/events", "GET"),
        ("/admin/api/v1/traces", "GET"),
        ("/admin/api/v1/traces/{trace_id}", "GET"),
        ("/admin/api/v1/jobs", "GET"),
        ("/admin/api/v1/jobs/{job_id}", "GET"),
        ("/admin/api/v1/schedules", "GET"),
        ("/admin/api/v1/skills", "GET"),
        ("/admin/api/v1/skills/{skill_id}", "GET"),
        ("/admin/api/v1/skills/{skill_id}/versions/{version_id}", "GET"),
        ("/admin/api/v1/topology", "GET"),
        ("/admin/api/v1/candidates", "GET"),
        ("/admin/api/v1/candidates/{candidate_id}", "GET"),
        ("/admin/api/v1/evaluations", "GET"),
        ("/admin/api/v1/evaluations/{evaluation_id}", "GET"),
        ("/admin/api/v1/scanner-findings", "GET"),
        ("/admin/api/v1/artifacts/{artifact_id}", "GET"),
        ("/admin/api/v1/historical/imports", "GET"),
        ("/admin/api/v1/historical/imports/{historical_import_id}", "GET"),
        ("/admin/api/v1/broker/decisions", "GET"),
        ("/admin/api/v1/broker/decisions/{decision_id}", "GET"),
        ("/admin/api/v1/context/artifacts", "GET"),
        ("/admin/api/v1/model-profile", "GET"),
        ("/admin/api/v1/embedding-profile", "GET"),
        ("/admin/api/v1/storage", "GET"),
        ("/admin/api/v1/audit", "GET"),
        ("/admin/api/v1/issues/{issue_id}", "GET"),
        ("/admin/api/v1/reason-codes", "GET"),
        ("/admin/api/v1/playbooks", "GET"),
        ("/admin/api/v1/playbooks/{playbook_id}", "GET"),
        ("/admin/api/v1/observatory", "GET"),
        ("/admin/api/v1/config/effective", "GET"),
        ("/admin/api/v1/invariants", "GET"),
        ("/admin/api/v1/comparisons", "GET"),
        ("/admin/api/v1/comparisons/query", "POST"),
        ("/admin/api/v1/diagnostics/bundles", "POST"),
        ("/admin/api/v1/diagnostics/bundles/{bundle_id}", "GET"),
        ("/admin/api/v1/actions/jobs/{id}/retry", "POST"),
        ("/admin/api/v1/actions/skills/{id}/freeze", "POST"),
        ("/admin/api/v1/actions/revocation/revoke-source", "POST"),
    }
    assert required_routes.issubset(routes)

    async def run():
        object_route = routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ]
        reason_code = await object_route.endpoint(
            object_type="reason_code", object_id="database-not-configured", workspace_id="dev-01"
        )
        invariants = await routes[("/admin/api/v1/invariants", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
        )
        return reason_code, invariants

    reason_code, invariants = asyncio.run(run())

    assert reason_code.object["object_type"] == "reason_code"
    assert reason_code.object["content_policy"]["raw_available"] is False
    invariant_ids = {
        item["invariant_id"] for item in invariants.collection["items"]
    }
    assert {
        "captured-events-accounted-for",
        "historical-sources-terminal-state",
        "evidence-preserves-provenance",
        "candidate-decisions-explicit",
        "llm-proposals-structured",
        "context-compiler-covered",
        "gates-cover-writer-activation",
        "writer-transactions-audited",
        "activated-versions-runtime-visible",
        "rollback-revokes-derived-data",
        "read-models-fresh",
    }.issubset(invariant_ids)


def test_observatory_broker_decisions_use_content_safe_retrieval_logs() -> None:
    retrieval_log_id = uuid4()
    trace_id = uuid4()
    rendered_skill_id = uuid4()
    candidate_object_id = uuid4()
    retrieval_store = MemoryRetrievalLogStore(
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=trace_id,
                span_id=uuid4(),
                parent_span_id=None,
                session_id="session-1",
                turn_id="turn-1",
                broker_policy_version_id=None,
                decision="skill_hint",
                candidate_skill_ids=[rendered_skill_id],
                rendered_skill_ids=[rendered_skill_id],
                no_skill_control=False,
                metadata={
                    "query_hash": "sha256:query",
                    "candidate_count": 1,
                    "candidate_objects": [
                        {
                            "object_type": "body_index_document",
                            "object_id": str(candidate_object_id),
                            "rank": 0.9,
                        }
                    ],
                    "reason_codes": ["vector-fused"],
                    "suppressed": [],
                },
                created_at=datetime.now(UTC),
            )
        ]
    )
    app = create_app(audit_store=MemoryAuditStore(), retrieval_store=retrieval_store)
    routes = _routes(app)

    async def run():
        collection = await routes[("/admin/api/v1/broker/decisions", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        detail = await routes[
            ("/admin/api/v1/broker/decisions/{decision_id}", "GET")
        ].endpoint(decision_id=str(retrieval_log_id), workspace_id="dev-01")
        return collection, detail

    collection, detail = asyncio.run(run())

    assert collection.collection["source"] == "retrieval_store.list_recent_logs"
    assert collection.collection["items"][0]["object_id"] == str(retrieval_log_id)
    assert collection.collection["content_policy"]["raw_available"] is False
    assert detail.object["object_type"] == "broker_decision"
    assert detail.object["diagnostics"]["query_hash"] == "sha256:query"
    assert detail.object["diagnostics"]["reason_codes"] == ["vector-fused"]
    assert detail.object["content_policy"]["raw_query_stored"] is False
    assert detail.object["provenance"]["candidate_objects"][0]["object_id"] == str(
        candidate_object_id
    )
    assert detail.object["effects"]["rendered_skill_ids"] == [str(rendered_skill_id)]


def test_observatory_event_and_trace_read_models_are_bounded_and_content_safe() -> None:
    trace_id = uuid4()
    event_store = NullEventStore()
    event = EventEnvelope(
        workspace_id="dev-01",
        trace_id=trace_id,
        span_id=uuid4(),
        session_id="session-1",
        turn_id="turn-1",
        event_type="tool_call_end",
        trust=TrustClass.TOOL_OUTPUT,
        payload={"secret": "nope", "safe": "ok"},
    ).redacted()
    asyncio.run(event_store.ingest_events([event]))
    span = TraceSpanRecord(
        trace_id=trace_id,
        span_id=uuid4(),
        parent_span_id=None,
        workspace_id=None,
        workspace_key="dev-01",
        operation_name="broker decision",
        operation_kind="broker",
        status="ok",
        safe_attributes={"decision": "skill_hint"},
        object_refs=[{"object_type": "captured_event", "object_id": str(event.event_id)}],
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
    )
    app = create_app(
        audit_store=MemoryAuditStore(),
        event_store=event_store,
        observability_store=MemoryTraceStore([span]),
    )
    routes = _routes(app)

    async def run():
        events = await routes[("/admin/api/v1/events", "GET")].endpoint(
            workspace_id="dev-01",
            event_type="tool_call_end",
            trace_id=trace_id,
            limit=10,
        )
        traces = await routes[("/admin/api/v1/traces", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        detail = await routes[("/admin/api/v1/traces/{trace_id}", "GET")].endpoint(
            trace_id=trace_id,
            workspace_id="dev-01",
            limit=10,
        )
        object_detail = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="captured_event",
            object_id=str(event.event_id),
            workspace_id="dev-01",
        )
        return events, traces, detail, object_detail

    events, traces, detail, object_detail = asyncio.run(run())

    assert events.collection["source"] == "event_store.list_events"
    assert events.collection["items"][0]["event_id"] == str(event.event_id)
    assert events.collection["items"][0]["payload_keys"] == ["safe", "secret"]
    assert events.collection["items"][0]["content_policy"]["raw_available"] is False
    assert "nope" not in str(events.collection["items"][0])
    assert traces.collection["source"] == "observability_store.list_traces"
    assert traces.collection["items"][0]["trace_id"] == str(trace_id)
    assert detail.object["timeline"][0]["object_refs"][0]["object_id"] == str(event.event_id)
    assert object_detail.object["object_type"] == "captured_event"
    assert object_detail.object["effects"]["payload_hash"] == event.payload_hash
    assert object_detail.object["content_policy"]["raw_available"] is False


def test_observatory_comparisons_and_diagnostic_bundles_are_persisted() -> None:
    audit_store = MemoryAuditStore()
    app = create_app(audit_store=audit_store)
    routes = _routes(app)

    async def run():
        comparison = await routes[("/admin/api/v1/comparisons/query", "POST")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
        )
        comparisons = await routes[("/admin/api/v1/comparisons", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        bundle = await routes[("/admin/api/v1/diagnostics/bundles", "POST")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
        )
        bundle_detail = await routes[
            ("/admin/api/v1/diagnostics/bundles/{bundle_id}", "GET")
        ].endpoint(bundle_id=bundle.object["object_id"], workspace_id="dev-01")
        comparison_object = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="baseline_comparison",
            object_id=comparison.object["object_id"],
            workspace_id="dev-01",
        )
        bundle_object = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="diagnostic_bundle",
            object_id=bundle.object["object_id"],
            workspace_id="dev-01",
        )
        return comparison, comparisons, bundle, bundle_detail, comparison_object, bundle_object

    comparison, comparisons, bundle, bundle_detail, comparison_object, bundle_object = asyncio.run(
        run()
    )

    assert comparison.object["object_type"] == "baseline_comparison"
    assert comparison.object["mutates_policy"] is False
    assert comparisons.collection["source"] == "observatory_admin_store.list_comparisons"
    assert comparisons.collection["items"][0]["object_id"] == comparison.object["object_id"]
    assert bundle.object["object_type"] == "diagnostic_bundle"
    assert bundle.object["content_policy"]["raw_available"] is False
    assert bundle_detail.object["object_id"] == bundle.object["object_id"]
    assert bundle_detail.object["manifest"]["component_count"] == 24
    assert comparison_object.object["effects"]["mutates_policy"] is False
    assert bundle_object.object["effects"]["manifest"]["component_count"] == 24
    assert audit_store.records[-1].subject_id == bundle.object["object_id"]


def test_observatory_stale_or_missing_telemetry_never_reports_healthy() -> None:
    settings = get_settings().model_copy(
        update={
            "database_url": "postgresql://autoskill:autoskill-dev@127.0.0.1/autoskill",
            "control_token": "control-token",
        }
    )
    snapshot = build_observatory_snapshot(
        settings=settings,
        status={
            "mode": "dev",
            "database_configured": True,
            "ingest_auth_configured": True,
            "control_auth_configured": True,
            "runtime_context_broker": {"enabled": True},
            "jobs": {},
            "workers": {},
        },
        operator_metrics={
            "captured_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "metrics": {},
            "dashboards": {},
        },
        worker_health={},
        audit_chain_valid=True,
        static_available=True,
        workspace_id="dev-01",
        window_minutes=10,
    )

    assert snapshot["data_quality"]["stale"] is True
    assert all(
        station["health"] != "healthy" for station in snapshot["pipeline"]["stations"]
    )
    assert any(
        "telemetry-stale" in issue["reason_codes"] for issue in snapshot["issue_board"]
    )


def test_observatory_action_records_audited_policy_receipt() -> None:
    audit_store = MemoryAuditStore()
    app = create_app(audit_store=audit_store)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        return await route.endpoint(
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="verify_audit_chain",
                idempotency_key="obs-test-1",
                reason="operator requested audit proof",
            )
        )

    response = asyncio.run(run())

    assert response.receipt["accepted"] is True
    assert response.receipt["policy"]["allowed"] is True
    assert response.receipt["audit"]["subject_id"] == "obs-test-1"
    assert audit_store.records[0].action == "observatory.verify_audit_chain"


def test_observatory_high_impact_action_requires_confirmation() -> None:
    audit_store = MemoryAuditStore()
    app = create_app(audit_store=audit_store)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        return await route.endpoint(
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="rollback_skill",
                idempotency_key="obs-test-rollback-1",
                reason="operator requested rollback",
                dry_run=False,
            )
        )

    response = asyncio.run(run())

    assert response.receipt["accepted"] is False
    assert response.receipt["policy"]["allowed"] is False
    assert response.receipt["policy"]["confirmation_required"] is True
    assert response.receipt["policy"]["reason_codes"] == ["confirmation-required"]
    assert audit_store.records[0].details["confirmation_required"] is True


def test_observatory_admin_token_is_enforced(monkeypatch) -> None:
    monkeypatch.setenv("SKILLKERNEL_ADMIN_TOKEN", "admin-token")
    get_settings.cache_clear()
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/config", "GET")]

    async def unauthorized():
        return await route.endpoint()

    async def authorized():
        return await route.endpoint(authorization="Bearer admin-token")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(unauthorized())
    assert exc.value.status_code == 401

    response = asyncio.run(authorized())
    assert response.config["principal"]["auth_configured"] is True

    get_settings.cache_clear()
