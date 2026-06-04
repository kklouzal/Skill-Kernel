import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from autoskill.api.app import (
    ADMIN_ACTION_RATE_LIMIT,
    ObservatoryActionRequest,
    create_app,
)
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.config import get_settings
from autoskill.core.enums import TrustClass
from autoskill.core.events import EventEnvelope
from autoskill.core.hashing import sha256_text
from autoskill.db.broker_policy import NullBrokerPolicyStore
from autoskill.db.events import NullEventStore
from autoskill.db.jobs import JobQueueSummary
from autoskill.db.memory import NullMemoryGovernanceStore
from autoskill.db.observability import (
    TraceSpanRecord,
    TraceSummaryRecord,
    _operator_metrics_payload,
)
from autoskill.db.observatory_admin import NullObservatoryAdminStore
from autoskill.db.retrieval import RetrievalLog
from autoskill.services.observatory import build_live_envelope, build_observatory_snapshot
from fastapi import HTTPException, Response


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


class MemorySummaryJobStore:
    def __init__(self) -> None:
        self.summary_calls: list[str | None] = []
        self.heartbeat_calls = 0

    async def summary(self, *, workspace_key: str | None = None) -> JobQueueSummary:
        self.summary_calls.append(workspace_key)
        return JobQueueSummary(counts={}, by_kind={})

    async def list_worker_heartbeats(self, **_kwargs):
        self.heartbeat_calls += 1
        return []


class CaptureObservabilityStore:
    def __init__(self) -> None:
        self.operator_metric_calls: list[dict[str, object]] = []

    async def operator_metrics(self, **kwargs):
        self.operator_metric_calls.append(kwargs)
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


def test_observatory_live_fallback_uses_snapshot_sequence_for_heartbeats() -> None:
    snapshot = {
        "snapshot_seq": 42,
        "captured_at": "2026-06-04T03:30:00+00:00",
        "global_health": "degraded",
        "issue_board": [{"issue_id": "issue-1"}],
        "pipeline": {
            "stations": [
                {"component_id": "observatory_admin", "health": "degraded"},
                {"component_id": "audit_trace", "health": "healthy"},
            ]
        },
    }

    initial = build_live_envelope(snapshot, last_seq=None)
    heartbeat = build_live_envelope(snapshot, last_seq=int(initial["seq"]))

    assert initial["seq"] == 42
    assert initial["cursor_seq"] == 0
    assert initial["event_type"] == "snapshot"
    assert initial["payload"] == snapshot
    assert heartbeat["seq"] == 42
    assert heartbeat["cursor_seq"] == 42
    assert heartbeat["event_type"] == "heartbeat"
    assert heartbeat["requires_snapshot_reload"] is False
    assert heartbeat["payload"] == {
        "global_health": "degraded",
        "issue_count": 1,
        "component_health": {
            "observatory_admin": "degraded",
            "audit_trace": "healthy",
        },
    }


async def _asgi_get(app, path: str) -> tuple[int, dict[str, str]]:
    messages = [{"type": "http.request", "body": b"", "more_body": False}]
    sent: list[dict[str, object]] = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 0),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    headers = {
        key.decode().lower(): value.decode()
        for key, value in start.get("headers", [])
    }
    return int(start["status"]), headers


async def _asgi_post(
    app,
    path: str,
    *,
    body: dict[str, object],
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    payload = json.dumps(body).encode()
    messages = [{"type": "http.request", "body": payload, "more_body": False}]
    sent: list[dict[str, object]] = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    encoded_headers = [
        (b"content-type", b"application/json"),
        *[
            (key.lower().encode(), value.encode())
            for key, value in (headers or {}).items()
        ],
    ]
    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": encoded_headers,
            "client": ("testclient", 0),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = {
        key.decode().lower(): value.decode()
        for key, value in start.get("headers", [])
    }
    body_text = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    ).decode()
    return int(start["status"]), response_headers, body_text


def test_observatory_summary_exposes_all_pipeline_stations_and_truth_states() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/summary", "GET")]
    http_response = Response()

    async def run():
        return await route.endpoint(
            workspace_id="dev-01",
            window_minutes=30,
            response=http_response,
        )

    response = asyncio.run(run())
    snapshot = response.snapshot

    assert http_response.headers["Cache-Control"] == "no-store, max-age=0"
    assert http_response.headers["Pragma"] == "no-cache"
    assert response.ok is True
    assert response.data["snapshot"]["schema_version"] == "skillkernel.observatory.v1"
    assert str(response.meta["request_id"]).startswith("req_")
    assert response.meta["redaction_level"] == "default"
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


def test_observatory_summary_defaults_to_effective_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOSKILL_WORKSPACE_ID", "prod-ops")
    get_settings.cache_clear()
    jobs = MemorySummaryJobStore()
    observability = CaptureObservabilityStore()
    audit = MemoryAuditStore()
    app = create_app(
        job_store=jobs,
        observability_store=observability,
        audit_store=audit,
    )
    route = _routes(app)[("/admin/api/v1/summary", "GET")]
    http_response = Response()

    async def run():
        return await route.endpoint(window_minutes=30, response=http_response)

    response = asyncio.run(run())

    assert http_response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.snapshot["workspace_id"] == "prod-ops"
    assert jobs.summary_calls == ["prod-ops", "prod-ops"]
    assert observability.operator_metric_calls[0]["workspace_key"] == "prod-ops"

    get_settings.cache_clear()


def test_status_defaults_to_effective_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOSKILL_WORKSPACE_ID", "prod-ops")
    get_settings.cache_clear()
    jobs = MemorySummaryJobStore()
    app = create_app(job_store=jobs)
    route = _routes(app)[("/v1/status", "GET")]

    async def run():
        return await route.endpoint(workspace_id=None)

    response = asyncio.run(run())

    assert response.workspace_id == "prod-ops"
    assert jobs.summary_calls == ["prod-ops", "prod-ops"]

    get_settings.cache_clear()


def test_observatory_live_sse_fallback_preserves_snapshot_sequence() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/live-sse", "GET")]

    async def run():
        response = await route.endpoint(workspace_id="dev-01")
        event_chunk = await anext(response.body_iterator)
        data_chunk = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return event_chunk, data_chunk

    event_chunk, data_chunk = asyncio.run(run())
    payload = json.loads(data_chunk.removeprefix("data: ").strip())

    assert event_chunk == "event: snapshot\n"
    assert payload["event_type"] == "snapshot"
    assert payload["seq"] == payload["payload"]["snapshot_seq"]
    assert payload["seq"] > 0


def test_observatory_live_sse_starts_with_fresh_snapshot_when_events_exist() -> None:
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=MemoryAuditStore(),
        observatory_admin_store=observatory_admin,
    )
    route = _routes(app)[("/admin/live-sse", "GET")]

    async def run():
        stale_event = await observatory_admin.append_live_event(
            kind="component_health_changed",
            component_id="scheduler_jobs",
            payload={"reason_codes": ["failed-jobs-present"]},
        )
        response = await route.endpoint(workspace_id="dev-01", last_seq=stale_event.seq - 1)
        event_chunk = await anext(response.body_iterator)
        data_chunk = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return response, event_chunk, data_chunk, stale_event

    response, event_chunk, data_chunk, stale_event = asyncio.run(run())
    payload = json.loads(data_chunk.removeprefix("data: ").strip())

    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert event_chunk == "event: snapshot\n"
    assert payload["event_type"] == "snapshot"
    assert payload["cursor_seq"] == stale_event.seq - 1
    assert payload["payload"]["pipeline"]["stations"]
    scheduler = next(
        station
        for station in payload["payload"]["pipeline"]["stations"]
        if station["component_id"] == "scheduler_jobs"
    )
    assert "failed-jobs-present" not in scheduler["reason_codes"]
    assert not [
        issue
        for issue in payload["payload"]["issue_board"]
        if issue["issue_id"] == "scheduler_jobs:failed-jobs-present"
    ]


def test_observatory_live_sse_replays_outbox_after_timestamp_snapshot() -> None:
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=MemoryAuditStore(),
        observatory_admin_store=observatory_admin,
    )
    route = _routes(app)[("/admin/live-sse", "GET")]

    async def run():
        response = await route.endpoint(workspace_id="dev-01")
        snapshot_event_chunk = await anext(response.body_iterator)
        snapshot_data_chunk = await anext(response.body_iterator)
        live_event = await observatory_admin.append_live_event(
            kind="component_health_changed",
            component_id="broker_runtime",
            payload={"health": "degraded", "reason_codes": ["broker-replay-stale"]},
        )
        live_event_chunk = await anext(response.body_iterator)
        live_data_chunk = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return (
            snapshot_event_chunk,
            json.loads(snapshot_data_chunk.removeprefix("data: ").strip()),
            live_event,
            live_event_chunk,
            json.loads(live_data_chunk.removeprefix("data: ").strip()),
        )

    (
        snapshot_event_chunk,
        snapshot_payload,
        live_event,
        live_event_chunk,
        live_payload,
    ) = asyncio.run(run())

    assert snapshot_event_chunk == "event: snapshot\n"
    assert snapshot_payload["event_type"] == "snapshot"
    assert snapshot_payload["seq"] > live_event.seq
    assert snapshot_payload["cursor_seq"] == 0
    assert live_event_chunk == "event: component_health_changed\n"
    assert live_payload["event_type"] == "component_health_changed"
    assert live_payload["seq"] == live_event.seq
    assert live_payload["cursor_seq"] == live_event.seq
    assert live_payload["component_id"] == "broker_runtime"
    assert live_payload["payload"]["reason_codes"] == ["broker-replay-stale"]


def test_observatory_live_sse_clamps_snapshot_style_last_seq_to_outbox_cursor() -> None:
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=MemoryAuditStore(),
        observatory_admin_store=observatory_admin,
    )
    route = _routes(app)[("/admin/live-sse", "GET")]

    async def run():
        stale_event = await observatory_admin.append_live_event(
            kind="component_health_changed",
            component_id="observatory_admin",
            payload={"health": "healthy", "phase": "before-reconnect"},
        )
        response = await route.endpoint(
            workspace_id="dev-01",
            last_seq=9_999_999_999_999,
        )
        snapshot_event_chunk = await anext(response.body_iterator)
        snapshot_data_chunk = await anext(response.body_iterator)
        live_event = await observatory_admin.append_live_event(
            kind="component_health_changed",
            component_id="scheduler_jobs",
            payload={"health": "degraded", "phase": "after-reconnect"},
        )
        live_event_chunk = await anext(response.body_iterator)
        live_data_chunk = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return (
            stale_event,
            snapshot_event_chunk,
            json.loads(snapshot_data_chunk.removeprefix("data: ").strip()),
            live_event,
            live_event_chunk,
            json.loads(live_data_chunk.removeprefix("data: ").strip()),
        )

    (
        stale_event,
        snapshot_event_chunk,
        snapshot_payload,
        live_event,
        live_event_chunk,
        live_payload,
    ) = asyncio.run(run())

    assert snapshot_event_chunk == "event: snapshot\n"
    assert snapshot_payload["cursor_seq"] == stale_event.seq
    assert live_event_chunk == "event: component_health_changed\n"
    assert live_payload["event_type"] == "component_health_changed"
    assert live_payload["seq"] == live_event.seq
    assert live_payload["cursor_seq"] == live_event.seq
    assert live_payload["component_id"] == "scheduler_jobs"
    assert live_payload["payload"]["phase"] == "after-reconnect"


def test_observatory_live_sse_ignores_snapshot_style_last_seq_without_outbox_rows() -> None:
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=MemoryAuditStore(),
        observatory_admin_store=observatory_admin,
    )
    route = _routes(app)[("/admin/live-sse", "GET")]

    async def run():
        response = await route.endpoint(
            workspace_id="dev-01",
            last_seq=9_999_999_999_999,
        )
        snapshot_event_chunk = await anext(response.body_iterator)
        snapshot_data_chunk = await anext(response.body_iterator)
        live_event = await observatory_admin.append_live_event(
            kind="component_health_changed",
            component_id="observatory_admin",
            payload={"health": "degraded", "phase": "first-outbox-event"},
        )
        live_event_chunk = await anext(response.body_iterator)
        live_data_chunk = await anext(response.body_iterator)
        await response.body_iterator.aclose()
        return (
            snapshot_event_chunk,
            json.loads(snapshot_data_chunk.removeprefix("data: ").strip()),
            live_event,
            live_event_chunk,
            json.loads(live_data_chunk.removeprefix("data: ").strip()),
        )

    (
        snapshot_event_chunk,
        snapshot_payload,
        live_event,
        live_event_chunk,
        live_payload,
    ) = asyncio.run(run())

    assert snapshot_event_chunk == "event: snapshot\n"
    assert snapshot_payload["cursor_seq"] == 0
    assert live_event_chunk == "event: component_health_changed\n"
    assert live_payload["seq"] == live_event.seq
    assert live_payload["cursor_seq"] == live_event.seq
    assert live_payload["payload"]["phase"] == "first-outbox-event"


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
    assert component.ok is True
    assert component.data["object"]["object_id"] == "scheduler_jobs"
    assert search.results
    assert len(search.results) <= 5
    assert search.ok is True
    assert search.data["query"] == "scheduler"
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
        components_next = await routes[("/admin/api/v1/components", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
            limit=2,
            cursor=components.collection["next_cursor"],
        )
        return components, components_next, reason_codes, playbooks, ready

    components, components_next, reason_codes, playbooks, ready = asyncio.run(run())

    assert components.collection["object_type"] == "component"
    assert components.collection["count"] == 2
    assert components.collection["has_more"] is True
    assert components.collection["next_cursor"]
    assert components.meta["pagination"]["next_cursor"] == components.collection["next_cursor"]
    assert components_next.collection["cursor"] == components.collection["next_cursor"]
    assert components_next.collection["items"][0]["component_id"] != (
        components.collection["items"][0]["component_id"]
    )
    assert components.collection["content_policy"]["raw_available"] is False
    assert components.ok is True
    assert components.data["collection"]["object_type"] == "component"
    assert len(reason_codes.collection["items"]) == 3
    assert reason_codes.collection["source"] == "observatory_snapshot.reason_code_catalog"
    assert playbooks.collection["items"]
    assert playbooks.collection["content_policy"]["raw_available"] is False
    assert ready.object["schema_version"] == "skillkernel.observatory.ready.v1"
    assert ready.object["ready"] is False


def test_observatory_memory_and_control_flow_read_models_are_content_safe() -> None:
    memory = NullMemoryGovernanceStore()
    source_object_id = uuid4()
    app = create_app(
        audit_store=MemoryAuditStore(),
        memory_governance_store=memory,
    )
    routes = _routes(app)

    async def run():
        pending = await memory.quarantine_memory(
            workspace_key="dev-01",
            source_object_type="evidence_item",
            source_object_id=source_object_id,
            proposed_memory={
                "summary": "redacted operator preference should not render here",
                "support_ids": ["ev-1"],
            },
            taint={"raw_content": False, "trust": "derived"},
            scanner_findings={"codes": ["passed"], "secret_count": 0},
        )
        approved = await memory.decide_memory_quarantine(
            workspace_key="dev-01",
            quarantine_id=pending.quarantine_id,
            status="approved",
            operator_id="operator-1",
            rationale="redacted approval rationale",
        )
        assert approved is not None
        control_event = await memory.record_control_flow_event(
            workspace_key="dev-01",
            source_kind="memory",
            source_id=pending.quarantine_id,
            influence_kind="retrieval",
            run_id="broker-run-1",
            decision={
                "decision": "approved_memory_influence",
                "cache_status": "miss",
            },
        )
        memories = await routes[("/admin/api/v1/memory/quarantine", "GET")].endpoint(
            workspace_id="dev-01",
            status="approved",
            limit=10,
        )
        memory_detail = await routes[
            ("/admin/api/v1/memory/quarantine/{quarantine_id}", "GET")
        ].endpoint(
            quarantine_id=str(pending.quarantine_id),
            workspace_id="dev-01",
        )
        events = await routes[("/admin/api/v1/control-flow/events", "GET")].endpoint(
            workspace_id="dev-01",
            source_kind="memory",
            influence_kind="retrieval",
            limit=10,
        )
        event_detail = await routes[
            ("/admin/api/v1/control-flow/events/{control_flow_event_id}", "GET")
        ].endpoint(
            control_flow_event_id=str(control_event.control_flow_event_id),
            workspace_id="dev-01",
        )
        memory_object = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="memory_quarantine",
            object_id=str(pending.quarantine_id),
            workspace_id="dev-01",
        )
        event_object = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="control_flow_event",
            object_id=str(control_event.control_flow_event_id),
            workspace_id="dev-01",
        )
        return memories, memory_detail, events, event_detail, memory_object, event_object

    memories, memory_detail, events, event_detail, memory_object, event_object = asyncio.run(
        run()
    )

    memory_item = memories.collection["items"][0]
    assert memories.collection["source"] == "memory_governance_store.list_memory_quarantine"
    assert memories.collection["object_type"] == "memory_quarantine"
    assert memories.collection["diagnostics"]["memory_content_returned"] is False
    assert memory_item["status"] == "approved"
    assert memory_item["source_object_type"] == "evidence_item"
    assert memory_item["proposed_memory_hash"].startswith("sha256:")
    assert memory_item["proposed_memory_keys"] == ["summary", "support_ids"]
    assert "proposed_memory" not in memory_item
    assert "redacted operator preference" not in str(memory_item)
    assert memory_detail.object["object_id"] == memory_item["object_id"]
    assert memory_detail.object["effects"]["runtime_loaded"] is False
    assert memory_detail.object["content_policy"]["memory_content_returned"] is False
    assert memory_object.object["object_type"] == "memory_quarantine"

    event_item = events.collection["items"][0]
    assert events.collection["source"] == "memory_governance_store.list_control_flow_events"
    assert events.collection["object_type"] == "control_flow_event"
    assert events.collection["diagnostics"]["content_safe_decisions_only"] is True
    assert event_item["source_kind"] == "memory"
    assert event_item["influence_kind"] == "retrieval"
    assert event_item["decision_keys"] == ["cache_status", "decision"]
    assert event_detail.object["provenance"]["upstream"][0]["object_type"] == "memory"
    assert event_detail.object["effects"]["policy_mutated"] is False
    assert event_object.object["object_type"] == "control_flow_event"


def test_observatory_admin_routes_include_browser_security_headers() -> None:
    app = create_app(audit_store=MemoryAuditStore())

    admin_status, admin_headers = asyncio.run(_asgi_get(app, "/admin/api/v1/config"))
    health_status, health_headers = asyncio.run(_asgi_get(app, "/v1/health"))

    assert admin_status == 200
    assert health_status == 200
    assert "frame-ancestors 'none'" in admin_headers["content-security-policy"]
    assert admin_headers["x-content-type-options"] == "nosniff"
    assert admin_headers["x-frame-options"] == "DENY"
    assert admin_headers["referrer-policy"] == "no-referrer"
    assert "content-security-policy" not in health_headers


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
        ("/admin/api/v1/memory/quarantine", "GET"),
        ("/admin/api/v1/memory/quarantine/{quarantine_id}", "GET"),
        ("/admin/api/v1/control-flow/events", "GET"),
        ("/admin/api/v1/control-flow/events/{control_flow_event_id}", "GET"),
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
        ("/admin/api/v1/broker/replay-episodes", "GET"),
        ("/admin/api/v1/broker/replay-episodes/{episode_id}", "GET"),
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
        ("/admin/api/v1/actions/audit", "GET"),
        ("/admin/api/v1/actions/audit/{action_id}", "GET"),
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


def test_observatory_broker_replay_episode_read_model_is_content_safe() -> None:
    broker_policy_store = NullBrokerPolicyStore()
    expected_skill_id = uuid4()
    retrieval_log_id = uuid4()

    async def seed_episode():
        return await broker_policy_store.record_replay_episode(
            workspace_key="dev-01",
            episode_key="operator-reviewed-broker-paraphrase",
            redacted_user_intent="fix unreadable labels in a generated diagram",
            expected_decision="skill_hint",
            expected_skill_ids=[expected_skill_id],
            tags=["production", "operator-reviewed"],
            metadata={
                "query_hash": "sha256:retrieval-query",
                "operator_notes": "redacted review note",
            },
            source_retrieval_log_id=retrieval_log_id,
        )

    episode = asyncio.run(seed_episode())
    app = create_app(
        audit_store=MemoryAuditStore(),
        broker_policy_store=broker_policy_store,
    )
    routes = _routes(app)

    async def run():
        collection = await routes[
            ("/admin/api/v1/broker/replay-episodes", "GET")
        ].endpoint(
            workspace_id="dev-01",
            tags=["production"],
            limit=10,
        )
        detail = await routes[
            ("/admin/api/v1/broker/replay-episodes/{episode_id}", "GET")
        ].endpoint(
            episode_id=str(episode.broker_replay_episode_id),
            workspace_id="dev-01",
        )
        object_detail = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="broker_replay_episode",
            object_id=str(episode.broker_replay_episode_id),
            workspace_id="dev-01",
        )
        return collection, detail, object_detail

    collection, detail, object_detail = asyncio.run(run())

    assert collection.collection["source"] == "broker_policy_store.list_replay_episodes"
    assert collection.collection["items"][0]["object_id"] == str(
        episode.broker_replay_episode_id
    )
    assert collection.collection["items"][0]["content_policy"]["raw_prompt_stored"] is False
    assert collection.collection["content_policy"]["raw_available"] is False
    assert detail.object["object_type"] == "broker_replay_episode"
    assert detail.object["effects"]["expected_skill_ids"] == [str(expected_skill_id)]
    assert detail.object["provenance"]["upstream"][0]["object_id"] == str(retrieval_log_id)
    assert detail.object["diagnostics"]["redacted_intent_hash"] == sha256_text(
        "fix unreadable labels in a generated diagram"
    )
    assert detail.object["content_policy"]["raw_prompt_stored"] is False
    assert object_detail.object["object_id"] == str(episode.broker_replay_episode_id)
    assert object_detail.object["diagnostics"]["metadata_keys"] == [
        "operator_notes",
        "query_hash",
    ]


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
        replay = await routes[("/admin/api/v1/replay/traces/{trace_id}", "GET")].endpoint(
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
        return events, traces, detail, replay, object_detail

    events, traces, detail, replay, object_detail = asyncio.run(run())

    assert events.collection["source"] == "event_store.list_events"
    assert events.collection["items"][0]["event_id"] == str(event.event_id)
    assert events.collection["items"][0]["payload_keys"] == ["safe", "secret"]
    assert events.collection["items"][0]["content_policy"]["raw_available"] is False
    assert "nope" not in str(events.collection["items"][0])
    assert traces.collection["source"] == "observability_store.list_traces"
    assert traces.collection["items"][0]["trace_id"] == str(trace_id)
    assert detail.object["timeline"][0]["object_refs"][0]["object_id"] == str(event.event_id)
    assert replay.object["schema_version"] == "skillkernel.observatory.trace-replay.v1"
    assert replay.object["timeline"][0]["object_refs"][0]["object_id"] == str(event.event_id)
    assert replay.object["replay_safety"]["reexecutes_work"] is False
    assert replay.object["replay_safety"]["raw_content_included"] is False
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
    assert bundle.object["live_event"]["object_type"] == "diagnostic_bundle"
    assert bundle.object["live_event"]["redaction_level"] == "default"


def test_observatory_zero_count_read_models_are_not_missing_required_signals() -> None:
    settings = get_settings().model_copy(
        update={
            "database_url": "postgresql://autoskill:autoskill-dev@127.0.0.1/autoskill",
            "control_token": "control-token",
        }
    )
    zero_count_metrics = {
        "ingest": {
            "events_in_window": 0,
            "total_events": 1,
            "event_rate_per_minute": 0.0,
        },
        "redaction_counts": {},
        "spool_backlog": {},
        "retrieval_decisions": {},
        "embedding_backlog": {},
        "context_hint_injection_count": 0,
        "context_hint_token_cost": 0,
        "context_hint_token_ledger_count": 0,
        "skill_creation_improvement_counts": {},
        "skill_lifecycle_counts": {},
        "scanner_reject_counts": {},
        "evaluation_pass_fail_counts": {},
        "rollback_freeze_counts": {},
        "job_queue_depth": {},
        "postgres_table_index_growth": [],
        "audit": {},
        "sidecar_latency_ms": {},
    }
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
            "captured_at": datetime.now(UTC).isoformat(),
            "metrics": zero_count_metrics,
            "dashboards": {},
        },
        worker_health={},
        audit_chain_valid=True,
        static_available=True,
        workspace_id="dev-01",
        window_minutes=10,
    )

    stations = snapshot["pipeline"]["stations"]
    assert not [
        station
        for station in stations
        if "missing-required-signal" in station["reason_codes"]
    ]
    assert all(station["data_quality"]["missing_signal_keys"] == [] for station in stations)
    assert any(
        station["reason_codes"] == ["spool-diagnostics-required"]
        for station in stations
        if station["component_id"] == "spool_ingest"
    )


def test_observatory_planned_evaluations_are_not_failures() -> None:
    settings = get_settings().model_copy(
        update={
            "database_url": "postgresql://autoskill:autoskill-dev@127.0.0.1/autoskill",
            "control_token": "control-token",
        }
    )

    def snapshot_for(evaluation_counts: dict[str, int]) -> dict[str, object]:
        return build_observatory_snapshot(
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
                "captured_at": datetime.now(UTC).isoformat(),
                "metrics": {
                    "ingest": {"events_in_window": 1, "total_events": 1},
                    "redaction_counts": {},
                    "spool_backlog": {},
                    "retrieval_decisions": {},
                    "embedding_backlog": {},
                    "context_hint_injection_count": 0,
                    "context_hint_token_cost": 0,
                    "context_hint_token_ledger_count": 0,
                    "skill_creation_improvement_counts": {},
                    "skill_lifecycle_counts": {},
                    "scanner_reject_counts": {},
                    "evaluation_pass_fail_counts": evaluation_counts,
                    "rollback_freeze_counts": {},
                    "job_queue_depth": {},
                    "postgres_table_index_growth": [],
                    "audit": {},
                    "sidecar_latency_ms": {},
                },
                "dashboards": {},
            },
            worker_health={},
            audit_chain_valid=True,
            static_available=True,
            workspace_id="dev-01",
            window_minutes=10,
        )

    planned_snapshot = snapshot_for(
        {"planned": 4, "passed": 1, "revoked": 2, "needs_intervention": 3}
    )
    evaluator = next(
        station
        for station in planned_snapshot["pipeline"]["stations"]  # type: ignore[index]
        if station["component_id"] == "evaluator_probes"
    )
    assert "evaluation-failures-present" not in evaluator["reason_codes"]
    assert not [
        issue
        for issue in planned_snapshot["issue_board"]  # type: ignore[index]
        if issue["issue_id"] == "evaluator_probes:evaluation-failures-present"
    ]

    failed_snapshot = snapshot_for({"planned": 4, "failed": 1})
    evaluator = next(
        station
        for station in failed_snapshot["pipeline"]["stations"]  # type: ignore[index]
        if station["component_id"] == "evaluator_probes"
    )
    assert "evaluation-failures-present" in evaluator["reason_codes"]


def test_operator_metrics_do_not_count_needs_intervention_as_evaluator_failure() -> None:
    payload = _operator_metrics_payload(
        workspace_key="dev-01",
        window_minutes=10,
        storage_limit=10,
        ingest={},
        redaction_counts={},
        latency={},
        latency_by_operation_kind={},
        job_status_counts={},
        job_kind_counts={},
        embedding_backlog={},
        retrieval_decisions={},
        context={},
        context_hints={},
        skill_lifecycle_counts={},
        skill_version_counts=[
            {"scanner_status": "passed", "evaluator_status": "needs_intervention", "count": 3},
            {"scanner_status": "passed", "evaluator_status": "failed", "count": 1},
        ],
        transaction_counts={},
        evaluation_counts={"needs_intervention": 3, "failed": 1},
        curation_counts={},
        revocation_counts={},
        freeze={},
        canary_counts={},
        drift={},
        utility={},
        audit={},
        storage=[],
    )

    assert payload["dashboards"]["scanner_evaluator_failures"]["evaluator_failures"] == 1
    assert payload["metrics"]["evaluation_pass_fail_counts"] == {
        "needs_intervention": 3,
        "failed": 1,
    }


def test_observatory_station_latency_uses_operation_specific_samples() -> None:
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
            "captured_at": datetime.now(UTC).isoformat(),
            "metrics": {
                "ingest": {"events_in_window": 1, "total_events": 1},
                "redaction_counts": {},
                "spool_backlog": {},
                "retrieval_decisions": {},
                "embedding_backlog": {},
                "context_hint_injection_count": 0,
                "context_hint_token_cost": 0,
                "context_hint_token_ledger_count": 0,
                "skill_creation_improvement_counts": {},
                "skill_lifecycle_counts": {},
                "scanner_reject_counts": {},
                "evaluation_pass_fail_counts": {},
                "rollback_freeze_counts": {},
                "job_queue_depth": {},
                "postgres_table_index_growth": [],
                "audit": {},
                "sidecar_latency_ms": {
                    "span_count": 10,
                    "avg": 100.0,
                    "p95": 999.0,
                    "max": 1100.0,
                },
                "latency_by_operation_kind": {
                    "job": {"span_count": 2, "avg": 25.0, "p95": 120.0, "max": 150.0},
                    "embedding_call": {
                        "span_count": 3,
                        "avg": 80.0,
                        "p95": 340.0,
                        "max": 360.0,
                    },
                },
            },
            "dashboards": {},
        },
        worker_health={},
        audit_chain_valid=True,
        static_available=True,
        workspace_id="dev-01",
        window_minutes=10,
    )

    stations = {
        station["component_id"]: station
        for station in snapshot["pipeline"]["stations"]  # type: ignore[index]
    }

    assert stations["observatory_admin"]["p95_latency_ms"] == 999.0
    assert stations["scheduler_jobs"]["p95_latency_ms"] == 120.0
    assert stations["model_embedding"]["p95_latency_ms"] == 340.0
    assert stations["retrieval_indexing"]["p95_latency_ms"] == 340.0
    assert stations["openclaw_live_capture"]["p95_latency_ms"] == 0.0


def test_observatory_missing_object_read_model_uses_specific_reason_code() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/artifacts/{artifact_id}", "GET")]

    async def run():
        return await route.endpoint(artifact_id="artifact-123")

    response = asyncio.run(run())

    assert response.object["diagnostics"]["reason_codes"] == ["read-model-missing"]
    assert response.object["diagnostics"]["supporting_component"] == "deterministic_writer"


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
        station["data_quality"]["missing_signal_keys"]
        for station in snapshot["pipeline"]["stations"]
    )
    assert any(
        "telemetry-stale" in issue["reason_codes"] for issue in snapshot["issue_board"]
    )


def test_observatory_action_records_audited_policy_receipt() -> None:
    audit_store = MemoryAuditStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=audit_store, observatory_admin_store=observatory_admin)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        return await route.endpoint(
            http_request=None,
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
    assert response.receipt["action_audit"]["action_kind"] == "verify_audit_chain"
    assert response.receipt["action_audit"]["target_type"] == "audit"
    assert response.receipt["action_audit"]["target_id"] == "verify_audit_chain"
    assert response.receipt["action_audit"]["linked_audit_id"] == str(
        audit_store.records[0].audit_id
    )
    assert response.receipt["action_audit"]["request_payload_redacted"]["request_id"] == (
        response.meta["request_id"]
    )
    assert response.receipt["action_audit"]["content_policy"]["raw_available"] is False
    assert response.receipt["live_event"]["event_type"] == "audit_record_appended"
    assert response.receipt["live_event"]["object_type"] == "audit"
    assert observatory_admin.live_events[0].seq == response.receipt["live_event"]["seq"]
    assert observatory_admin.actions[0].action_id.hex == (
        response.receipt["action_audit"]["action_id"].replace("-", "")
    )
    assert audit_store.records[0].action == "observatory.verify_audit_chain"


def test_observatory_action_audit_read_model_exposes_receipts_without_raw_content() -> None:
    audit_store = MemoryAuditStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=audit_store, observatory_admin_store=observatory_admin)
    routes = _routes(app)

    async def run():
        first = await routes[("/admin/api/v1/actions", "POST")].endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="verify_audit_chain",
                idempotency_key="obs-audit-list-1",
                reason="operator requested audit proof",
                metadata={"ticket": "INC-1"},
            ),
        )
        await routes[("/admin/api/v1/actions", "POST")].endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="refresh_read_models",
                idempotency_key="obs-audit-list-2",
                reason="operator requested read model refresh",
            ),
        )
        collection = await routes[("/admin/api/v1/actions/audit", "GET")].endpoint(
            workspace_id="dev-01",
            action_kind="verify_audit_chain",
            limit=1,
        )
        detail = await routes[
            ("/admin/api/v1/actions/audit/{action_id}", "GET")
        ].endpoint(action_id=first.receipt["action_audit"]["action_id"])
        microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="admin_action",
            object_id=first.receipt["action_audit"]["action_id"],
        )
        return first, collection, detail, microscope

    first, collection, detail, microscope = asyncio.run(run())

    assert collection.collection["source"] == "observatory_admin_store.list_action_audits"
    assert collection.collection["object_type"] == "admin_action"
    assert collection.collection["count"] == 1
    assert collection.collection["diagnostics"]["filter"]["workspace_id"] == "dev-01"
    assert collection.collection["items"][0]["action_kind"] == "verify_audit_chain"
    assert collection.collection["items"][0]["diagnostics"]["metadata_keys"] == ["ticket"]
    assert collection.collection["items"][0]["content_policy"]["raw_available"] is False
    assert detail.object["object_id"] == first.receipt["action_audit"]["action_id"]
    assert detail.object["provenance"]["upstream"][0]["object_type"] == "audit_record"
    assert detail.object["diagnostics"]["request_id"].startswith("req_")
    assert detail.object["effects"]["dry_run"] is True
    assert detail.object["content_policy"]["raw_available"] is False
    assert "operator requested audit proof" in detail.object["reason"]
    assert detail.object["request_payload_redacted"]["confirmation_hash"] is None
    assert "INC-1" not in str(detail.object["request_payload_redacted"])
    assert microscope.object["object_type"] == "admin_action"
    assert microscope.object["audit"]["chain_visible"] is True


def test_observatory_high_impact_action_requires_confirmation() -> None:
    audit_store = MemoryAuditStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=audit_store, observatory_admin_store=observatory_admin)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        return await route.endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="rollback_skill",
                idempotency_key="obs-test-rollback-1",
                target={"id": "skill-123"},
                reason="operator requested rollback",
                confirmation="skill-123",
                dry_run=False,
            )
        )

    response = asyncio.run(run())

    assert response.receipt["accepted"] is False
    assert response.receipt["policy"]["allowed"] is False
    assert response.receipt["policy"]["confirmation_required"] is True
    assert response.receipt["policy"]["reason_codes"] == ["confirmation-required"]
    assert response.receipt["action_audit"]["target_type"] == "skill"
    assert response.receipt["action_audit"]["target_id"] == "skill-123"
    assert response.receipt["action_audit"]["result"] == "rejected"
    assert response.receipt["action_audit"]["request_payload_redacted"][
        "confirmation_present"
    ] is True
    assert response.receipt["action_audit"]["request_payload_redacted"][
        "confirmation_hash"
    ].startswith("sha256:")
    assert "skill-123" not in str(
        response.receipt["action_audit"]["request_payload_redacted"]["confirmation_hash"]
    )
    assert observatory_admin.actions[0].linked_audit_id == audit_store.records[0].audit_id
    assert audit_store.records[0].details["confirmation_required"] is True


def test_observatory_raw_reveal_action_fails_closed_by_default() -> None:
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=MemoryAuditStore(), observatory_admin_store=observatory_admin)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        return await route.endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="reveal_raw_content",
                idempotency_key="raw-reveal-disabled",
                target={"object_type": "captured_event", "object_id": "event-123"},
                reason="operator needs incident diagnostics",
                confirmation="confirm",
                dry_run=False,
            ),
            x_skillkernel_roles="admin",
        )

    response = asyncio.run(run())

    assert response.receipt["accepted"] is False
    assert response.receipt["policy"]["reason_codes"] == ["raw-content-disabled"]
    assert response.receipt["raw_reveal_grant"] is None
    assert observatory_admin.actions[0].request_payload_redacted["confirmation_hash"].startswith(
        "sha256:"
    )


def test_observatory_raw_reveal_grant_is_admin_only_and_hash_audited(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("AUTOSKILL_WEB_ADMIN_RAW_CONTENT_ENABLED", "true")
    get_settings.cache_clear()
    audit_store = MemoryAuditStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=audit_store, observatory_admin_store=observatory_admin)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def operator_attempt():
        return await route.endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="reveal_raw_content",
                idempotency_key="raw-reveal-operator",
                target={"object_type": "captured_event", "object_id": "event-123"},
                reason="operator needs incident diagnostics",
                confirmation="confirm",
                dry_run=False,
            ),
            x_skillkernel_roles="operator",
        )

    async def admin_attempt():
        return await route.endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="reveal_raw_content",
                idempotency_key="raw-reveal-admin",
                target={"object_type": "captured_event", "object_id": "event-123"},
                reason="admin-approved incident diagnostics",
                confirmation="confirm",
                dry_run=False,
            ),
            x_skillkernel_roles="admin",
        )

    operator_response = asyncio.run(operator_attempt())
    admin_response = asyncio.run(admin_attempt())

    assert operator_response.receipt["accepted"] is False
    assert operator_response.receipt["policy"]["reason_codes"] == ["admin-role-required"]
    grant = admin_response.receipt["raw_reveal_grant"]
    assert admin_response.receipt["accepted"] is True
    assert grant["schema_version"] == "skillkernel.observatory.raw-reveal-grant.v1"
    assert grant["token"].startswith("skor_")
    assert grant["token_hash"] == f"sha256:{sha256_text(grant['token'])}"
    assert grant["raw_content_included"] is False
    audited_payload = observatory_admin.actions[-1].request_payload_redacted
    assert audited_payload["raw_reveal_grant"]["token_hash"] == grant["token_hash"]
    assert "token" not in audited_payload["raw_reveal_grant"]
    assert audit_store.records[-1].details["raw_reveal_grant_hash"] == grant["token_hash"]
    assert audit_store.records[-1].details["raw_content_included"] is False

    get_settings.cache_clear()


def test_observatory_browser_action_requires_csrf(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    get_settings.cache_clear()
    app = create_app(audit_store=MemoryAuditStore())
    body = {
        "workspace_id": "dev-01",
        "action": "verify_audit_chain",
        "idempotency_key": "csrf-test-1",
        "reason": "operator requested audit proof",
    }

    missing_status, _, missing_body = asyncio.run(
        _asgi_post(
            app,
            "/admin/api/v1/actions",
            body=body,
            headers={"X-SkillKernel-Browser-Session": "true"},
        )
    )
    token = sha256_text("skillkernel-observatory-csrf:local-dev-admin")[:32]
    ok_status, _, ok_body = asyncio.run(
        _asgi_post(
            app,
            "/admin/api/v1/actions",
            body={**body, "idempotency_key": "csrf-test-2"},
            headers={
                "X-SkillKernel-Browser-Session": "true",
                "X-SkillKernel-CSRF": token,
            },
        )
    )

    assert missing_status == 403
    assert "invalid admin csrf token" in missing_body
    assert ok_status == 200
    assert json.loads(ok_body)["receipt"]["accepted"] is True
    get_settings.cache_clear()


def test_observatory_action_rate_limit_is_enforced() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run() -> None:
        for index in range(ADMIN_ACTION_RATE_LIMIT):
            response = await route.endpoint(
                http_request=None,
                request=ObservatoryActionRequest(
                    workspace_id="dev-01",
                    action="verify_audit_chain",
                    idempotency_key=f"rate-limit-{index}",
                    reason="operator requested audit proof",
                ),
            )
            assert response.receipt["accepted"] is True
        with pytest.raises(HTTPException) as exc:
            await route.endpoint(
                http_request=None,
                request=ObservatoryActionRequest(
                    workspace_id="dev-01",
                    action="verify_audit_chain",
                    idempotency_key="rate-limit-overflow",
                    reason="operator requested audit proof",
                ),
            )
        assert exc.value.status_code == 429

    asyncio.run(run())


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
    assert response.ok is True
    assert response.data["config"]["principal"]["auth_configured"] is True
    assert response.config["principal"]["auth_configured"] is True

    get_settings.cache_clear()
