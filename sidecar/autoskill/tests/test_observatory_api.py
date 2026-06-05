import asyncio
import inspect
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
from autoskill.db import observability as observability_module
from autoskill.db.attribution import NullAttributionStore
from autoskill.db.broker_policy import NullBrokerPolicyStore
from autoskill.db.context import NullContextGovernanceStore
from autoskill.db.embeddings import (
    EMBEDDING_OBJECT_TYPE_BODY_INDEX_DOCUMENT,
    EMBEDDING_OBJECT_TYPE_EVIDENCE_ITEM,
    EMBEDDING_OBJECT_TYPE_EXTERNAL_SKILL,
    EMBEDDING_OBJECT_TYPE_HISTORICAL_IMPORT_CHUNK,
)
from autoskill.db.evaluations import EvaluationReviewRecord, NullEvaluationStore
from autoskill.db.events import NullEventStore
from autoskill.db.governance import (
    EvolutionTransactionItemRecord,
    EvolutionTransactionRecord,
    NullGovernanceStore,
    RevocationRequestRecord,
)
from autoskill.db.jobs import JobQueueSummary, JobRecord, NullJobStore
from autoskill.db.llm_invocations import NullLLMInvocationStore
from autoskill.db.memory import NullMemoryGovernanceStore
from autoskill.db.observability import (
    TraceSpanRecord,
    TraceSummaryRecord,
    _operator_metrics_payload,
)
from autoskill.db.observatory_admin import (
    AdminAdministrativeEscalationStatusRecord,
    AdminAutonomyDecisionStatusRecord,
    AdminEvidenceFidelityStatusRecord,
    AdminSemanticAdjudicationStatusRecord,
    NullObservatoryAdminStore,
)
from autoskill.db.profile_qualifications import NullProfileQualificationStore
from autoskill.db.profiles import ModelProfileRecord, NullProfileStore
from autoskill.db.retrieval import RetrievalLog
from autoskill.db.scheduler import NullSchedulerStore, ScheduleRecord
from autoskill.db.topology import NullTopologyStore
from autoskill.services.observatory import (
    build_live_envelope,
    build_observatory_snapshot,
    object_microscope,
)
from fastapi import HTTPException, Response
from starlette.routing import Mount


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


class MemoryObservatoryJobStore(NullJobStore):
    def __init__(self, records: list[JobRecord]) -> None:
        self.records = records

    async def list_jobs(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[JobRecord]:
        records = [
            record
            for record in self.records
            if (workspace_key is None or record.workspace_key == workspace_key)
            and (status is None or record.status == status)
        ]
        return records[:limit]


class MemoryObservatorySchedulerStore(NullSchedulerStore):
    def __init__(self, records: list[ScheduleRecord]) -> None:
        self.records = records

    async def list_schedules(self, *, limit: int = 50) -> list[ScheduleRecord]:
        return self.records[:limit]


class MemoryTopologyGovernanceStore(NullGovernanceStore):
    def __init__(
        self,
        transactions: list[EvolutionTransactionRecord],
        items: list[EvolutionTransactionItemRecord] | None = None,
        revocations: list[RevocationRequestRecord] | None = None,
    ) -> None:
        self.transactions = transactions
        self.items = items or []
        self.revocations = revocations or []

    async def list_transactions(
        self,
        *,
        workspace_key: str | None = None,
        transaction_kind_prefix: str | None = None,
        limit: int = 50,
    ) -> list[EvolutionTransactionRecord]:
        records = [
            transaction
            for transaction in self.transactions
            if (workspace_key is None or transaction.workspace_key == workspace_key)
            and (
                transaction_kind_prefix is None
                or transaction.transaction_kind.startswith(transaction_kind_prefix)
            )
        ]
        return records[:limit]

    async def get_transaction(
        self,
        *,
        workspace_key: str | None = None,
        evolution_transaction_id,
    ) -> EvolutionTransactionRecord | None:
        for transaction in self.transactions:
            if (
                transaction.evolution_transaction_id == evolution_transaction_id
                and (workspace_key is None or transaction.workspace_key == workspace_key)
            ):
                return transaction
        return None

    async def list_transaction_items(
        self,
        *,
        evolution_transaction_id,
    ) -> list[EvolutionTransactionItemRecord]:
        return [
            item
            for item in self.items
            if item.evolution_transaction_id == evolution_transaction_id
        ]

    async def get_revocation_request(
        self,
        *,
        workspace_key: str | None = None,
        revocation_request_id,
    ) -> RevocationRequestRecord | None:
        for revocation in self.revocations:
            if (
                revocation.revocation_request_id == revocation_request_id
                and (workspace_key is None or revocation.workspace_key == workspace_key)
            ):
                return revocation
        return None


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


class MemoryObservatoryProfileStore(NullProfileStore):
    def __init__(
        self,
        *,
        model_profile: ModelProfileRecord,
        embedding_profile: ModelProfileRecord,
    ) -> None:
        self.model_profile = model_profile
        self.embedding_profile = embedding_profile

    async def get_model_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        if (
            workspace_key == self.model_profile.workspace_key
            and profile_key == self.model_profile.profile_key
        ):
            return self.model_profile
        return None

    async def list_model_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        if workspace_key != self.model_profile.workspace_key:
            return []
        if status is not None and status != self.model_profile.status:
            return []
        return [self.model_profile][:limit]

    async def get_embedding_profile(
        self,
        *,
        workspace_key: str,
        profile_key: str,
    ) -> ModelProfileRecord | None:
        if (
            workspace_key == self.embedding_profile.workspace_key
            and profile_key == self.embedding_profile.profile_key
        ):
            return self.embedding_profile
        return None

    async def list_embedding_profiles(
        self,
        *,
        workspace_key: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ModelProfileRecord]:
        if workspace_key != self.embedding_profile.workspace_key:
            return []
        if status is not None and status != self.embedding_profile.status:
            return []
        return [self.embedding_profile][:limit]


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
    assert initial["kind"] == "snapshot"
    assert datetime.fromisoformat(initial["sent_at"]).tzinfo is not None
    assert initial["payload"] == snapshot
    assert heartbeat["seq"] == 42
    assert heartbeat["cursor_seq"] == 42
    assert heartbeat["event_type"] == "heartbeat"
    assert heartbeat["kind"] == "heartbeat"
    assert datetime.fromisoformat(heartbeat["sent_at"]).tzinfo is not None
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
            limit=20,
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
    playbook_ids = {item["playbook_id"] for item in playbooks.collection["items"]}
    assert {
        "candidate-drought",
        "skill-improvements-rejected",
        "context-pressure",
        "harm-after-activation",
        "historical-bootstrap-validation",
        "broker-misses-relevant-skills",
        "read-model-staleness",
        "llm-maintenance-stalled",
    }.issubset(playbook_ids)
    assert ready.object["schema_version"] == "skillkernel.observatory.ready.v1"
    assert ready.object["ready"] is False


def test_observatory_playbook_detail_exposes_current_signal_state() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    routes = _routes(app)

    async def run():
        detail = await routes[("/admin/api/v1/playbooks/{playbook_id}", "GET")].endpoint(
            playbook_id="context-pressure",
            workspace_id="dev-01",
            window_minutes=10,
        )
        microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="playbook",
            object_id="context-pressure",
            workspace_id="dev-01",
            window_minutes=10,
        )
        return detail, microscope

    detail, microscope = asyncio.run(run())

    assert detail.object["object_type"] == "playbook"
    state = detail.object["current_signal_state"]
    assert state["severity"] in {"critical", "high", "medium", "low", "none"}
    assert 0.0 <= state["confidence"] <= 1.0
    assert state["first_checks"]
    assert state["typical_next_views"]
    assert state["safe_next_diagnostic_actions"]
    assert state["blocked_policy_actions"] == [
        {
            "action": "execute_hidden_action",
            "blocked_by": "playbooks_are_read_only",
            "summary": "Playbooks link to views and guarded actions but never execute hidden work.",
        },
        {
            "action": "reveal_raw_content",
            "blocked_by": "raw-content-disabled",
            "summary": "Raw content remains unavailable from playbook read models.",
        },
        {
            "action": "activate_or_rewrite_runtime_skill",
            "blocked_by": "control-plane-immutability",
            "summary": (
                "Skill activation still requires deterministic writer, policy, "
                "and audit gates."
            ),
        },
    ]
    assert detail.object["supporting_records"]
    assert detail.object["content_policy"]["raw_available"] is False
    assert microscope.object["current_signal_state"]["first_checks"] == state["first_checks"]


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


def test_observatory_context_compiler_read_models_are_store_backed_and_content_safe() -> None:
    context = NullContextGovernanceStore()
    skill_id = uuid4()
    skill_version_id = uuid4()

    async def seed():
        artifact = await context.record_artifact(
            workspace_key="dev-01",
            artifact_kind="skill_md",
            source_object_type="skill_version",
            source_object_id=skill_version_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            text="WHEN raw operator request appears DO never expose this text",
            max_tokens=30,
            safety_status="passed",
            equivalence_status="passed",
            shadowing_status="passed",
            metadata={"gate": "context-loadability", "raw_note": "do not render"},
        )
        run = await context.record_compile_run(
            workspace_key="dev-01",
            compiler_version="context-compiler.v1",
            input_skillir_hash="skillir-hash",
            output_manifest_hash="manifest-hash",
            actual_runtime_tokens=14,
            status="passed",
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            context_artifact_id=artifact.context_artifact_id,
            target_runtime_tokens=30,
            compression_ratio=0.42,
            semantic_equivalence_score=0.97,
            metadata={"compile": "passed", "note": "do not render"},
        )
        event = await context.record_budget_event(
            workspace_key="dev-01",
            event_type="skill_md_budget",
            decision="accept",
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            context_artifact_id=artifact.context_artifact_id,
            tokens_delta=-12,
            marginal_success_delta=0.1,
            evidence={"private_probe": "do not render"},
            metadata={"budget": "passed"},
        )
        trial = await context.record_semantic_compression_trial(
            workspace_key="dev-01",
            skill_id=skill_id,
            source_context_artifact_id=artifact.context_artifact_id,
            candidate_context_artifact_id=artifact.context_artifact_id,
            source_tokens=40,
            candidate_tokens=14,
            preserved_requirements=5,
            lost_requirements=0,
            added_unsupported_requirements=0,
            equivalence_score=0.97,
            status="passed",
            metadata={"trial": "passed", "note": "do not render"},
        )
        return artifact, run, event, trial

    artifact, run, event, trial = asyncio.run(seed())
    app = create_app(
        audit_store=MemoryAuditStore(),
        context_governance_store=context,
    )
    routes = _routes(app)

    async def read():
        artifacts = await routes[("/admin/api/v1/context/artifacts", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        artifact_detail = await routes[
            ("/admin/api/v1/context/artifacts/{artifact_id}", "GET")
        ].endpoint(
            artifact_id=str(artifact.context_artifact_id),
            workspace_id="dev-01",
        )
        artifact_alias_detail = await routes[
            ("/admin/api/v1/artifacts/{artifact_id}", "GET")
        ].endpoint(
            artifact_id=str(artifact.context_artifact_id),
            workspace_id="dev-01",
        )
        runs = await routes[("/admin/api/v1/context/compile-runs", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        run_detail = await routes[
            ("/admin/api/v1/context/compile-runs/{run_id}", "GET")
        ].endpoint(
            run_id=str(run.context_compile_run_id),
            workspace_id="dev-01",
        )
        events = await routes[("/admin/api/v1/context/budget-events", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        event_detail = await routes[
            ("/admin/api/v1/context/budget-events/{event_id}", "GET")
        ].endpoint(
            event_id=str(event.context_budget_event_id),
            workspace_id="dev-01",
        )
        trials = await routes[
            ("/admin/api/v1/context/compression-trials", "GET")
        ].endpoint(workspace_id="dev-01", limit=10)
        trial_detail = await routes[
            ("/admin/api/v1/context/compression-trials/{trial_id}", "GET")
        ].endpoint(
            trial_id=str(trial.semantic_compression_trial_id),
            workspace_id="dev-01",
        )
        artifact_microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="artifact",
            object_id=str(artifact.context_artifact_id),
            workspace_id="dev-01",
        )
        compile_run_microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="context_compile_run",
            object_id=str(run.context_compile_run_id),
            workspace_id="dev-01",
        )
        return (
            artifacts,
            artifact_detail,
            artifact_alias_detail,
            runs,
            run_detail,
            events,
            event_detail,
            trials,
            trial_detail,
            artifact_microscope,
            compile_run_microscope,
        )

    (
        artifacts,
        artifact_detail,
        artifact_alias_detail,
        runs,
        run_detail,
        events,
        event_detail,
        trials,
        trial_detail,
        artifact_microscope,
        compile_run_microscope,
    ) = asyncio.run(read())

    artifact_item = artifacts.collection["items"][0]
    assert artifacts.collection["source"] == "context_governance_store.list_artifacts"
    assert artifact_item["object_type"] == "context_artifact"
    assert artifact_item["text_hash"] == artifact.text_hash
    assert artifact_item["metadata_keys"] == ["gate", "raw_note"]
    assert artifact_detail.object["effects"]["raw_text_returned"] is False
    assert artifact_alias_detail.object["object_type"] == "context_artifact"
    assert artifact_alias_detail.object["object_id"] == str(artifact.context_artifact_id)
    assert artifact_alias_detail.object["content_policy"]["compiled_text_returned"] is False
    assert artifact_microscope.object["object_type"] == "context_artifact"

    run_item = runs.collection["items"][0]
    assert runs.collection["source"] == "context_governance_store.list_compile_runs"
    assert run_item["status"] == "passed"
    assert run_item["input_skillir_hash"] == "skillir-hash"
    assert run_detail.object["content_policy"]["skillir_returned"] is False
    assert run_detail.object["effects"]["activation_proof_candidate"] is True
    assert compile_run_microscope.object["object_type"] == "context_compile_run"

    event_item = events.collection["items"][0]
    assert events.collection["source"] == "context_governance_store.list_budget_events"
    assert event_item["decision"] == "accept"
    assert event_item["evidence_keys"] == ["private_probe"]
    assert event_detail.object["content_policy"]["evidence_payload_returned"] is False

    trial_item = trials.collection["items"][0]
    assert trials.collection["source"] == (
        "context_governance_store.list_semantic_compression_trials"
    )
    assert trial_item["equivalence_score"] == 0.97
    assert trial_detail.object["effects"]["token_delta"] == -26
    assert trial_detail.object["content_policy"]["artifact_text_returned"] is False

    combined = json.dumps(
        [
            artifacts.collection,
            artifact_detail.object,
            artifact_alias_detail.object,
            runs.collection,
            run_detail.object,
            events.collection,
            event_detail.object,
            trials.collection,
            trial_detail.object,
            artifact_microscope.object,
            compile_run_microscope.object,
        ],
        sort_keys=True,
    )
    assert "WHEN raw operator request appears" not in combined
    assert "do not render" not in combined


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


def test_observatory_static_serving_is_external_container_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("AUTOSKILL_WEB_ADMIN_STATIC_SERVING_MODE", "sidecar")
    monkeypatch.setenv("AUTOSKILL_WEB_ADMIN_STATIC_DIR", "/tmp/ignored-observatory-dist")
    get_settings.cache_clear()
    try:
        app = create_app(audit_store=MemoryAuditStore())
        routes = _routes(app)

        async def run():
            config = await routes[("/admin/api/v1/config", "GET")].endpoint()
            ready = await routes[("/admin/api/v1/health/ready", "GET")].endpoint()
            return config, ready

        config, ready = asyncio.run(run())
        admin_mounts = [
            route
            for route in app.routes
            if isinstance(route, Mount) and route.path == "/admin"
        ]

        assert admin_mounts == []
        assert config.config["static_serving"] == "observatory_container"
        assert "static_serving_mode" not in config.config
        assert "static_dir" not in config.config
        assert config.config["static_available"] is True
        assert "frontend_serving" not in ready.object["data_quality"]["missing_signals"]
        assert all(
            "frontend-serving-unavailable" not in issue["reason_codes"]
            for issue in ready.object["issues"]
        )
    finally:
        get_settings.cache_clear()


def test_observatory_required_admin_route_matrix_and_microscope_objects_exist() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    routes = _routes(app)

    required_routes = {
        ("/admin/api/v1/health/live", "GET"),
        ("/admin/api/v1/health/ready", "GET"),
        ("/admin/api/v1/search", "GET"),
        ("/admin/api/v1/evidence/fidelity", "GET"),
        ("/admin/api/v1/evidence/fidelity/{fidelity_id}", "GET"),
        ("/admin/api/v1/raw-vault/summary", "GET"),
        ("/admin/api/v1/adjudications", "GET"),
        ("/admin/api/v1/adjudications/{adjudication_run_id}", "GET"),
        ("/admin/api/v1/autonomy/decisions", "GET"),
        ("/admin/api/v1/autonomy/decisions/{decision_id}", "GET"),
        ("/admin/api/v1/autonomy/threshold-deadlocks", "GET"),
        ("/admin/api/v1/autonomy/threshold-deadlocks/{decision_id}", "GET"),
        ("/admin/api/v1/escalations", "GET"),
        ("/admin/api/v1/escalations/{event_id}", "GET"),
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
        ("/admin/api/v1/scanner-findings/{finding_id}", "GET"),
        ("/admin/api/v1/artifacts/{artifact_id}", "GET"),
        ("/admin/api/v1/historical/imports", "GET"),
        ("/admin/api/v1/historical/imports/{historical_import_id}", "GET"),
        ("/admin/api/v1/broker/decisions", "GET"),
        ("/admin/api/v1/broker/decisions/{decision_id}", "GET"),
        ("/admin/api/v1/broker/replay-episodes", "GET"),
        ("/admin/api/v1/broker/replay-episodes/{episode_id}", "GET"),
        ("/admin/api/v1/context/artifacts", "GET"),
        ("/admin/api/v1/context/artifacts/{artifact_id}", "GET"),
        ("/admin/api/v1/context/compile-runs", "GET"),
        ("/admin/api/v1/context/compile-runs/{run_id}", "GET"),
        ("/admin/api/v1/context/budget-events", "GET"),
        ("/admin/api/v1/context/budget-events/{event_id}", "GET"),
        ("/admin/api/v1/context/compression-trials", "GET"),
        ("/admin/api/v1/context/compression-trials/{trial_id}", "GET"),
        ("/admin/api/v1/model-profile", "GET"),
        ("/admin/api/v1/model-profile/{profile_key}", "GET"),
        ("/admin/api/v1/embedding-profile", "GET"),
        ("/admin/api/v1/embedding-profile/{profile_key}", "GET"),
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
        ("/admin/api/v1/actions/summary", "GET"),
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
        scanner_finding = await routes[
            ("/admin/api/v1/scanner-findings/{finding_id}", "GET")
        ].endpoint(
            finding_id="scanner_reject_counts",
            workspace_id="dev-01",
            window_minutes=10,
        )
        return reason_code, invariants, scanner_finding

    reason_code, invariants, scanner_finding = asyncio.run(run())

    assert reason_code.object["object_type"] == "reason_code"
    assert reason_code.object["content_policy"]["raw_available"] is False
    assert scanner_finding.object["object_type"] == "scanner_finding"
    assert scanner_finding.object["content_policy"]["raw_available"] is False
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


def test_observatory_job_object_microscope_resolves_scheduler_read_model() -> None:
    now = datetime.now(UTC)
    job_id = uuid4()
    trace_id = uuid4()
    span_id = uuid4()
    job_store = MemoryObservatoryJobStore(
        [
            JobRecord(
                job_id=job_id,
                workspace_id=None,
                workspace_key="dev-01",
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                job_kind="revocations.rollback",
                status="queued",
                idempotency_key="revocation-job-1",
                payload={"revocation_request_id": "request-1"},
                priority=25,
                lease_owner=None,
                lease_expires_at=None,
                attempts=0,
                max_attempts=3,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
        ]
    )
    app = create_app(audit_store=MemoryAuditStore(), job_store=job_store)
    routes = _routes(app)

    async def run():
        direct = await routes[("/admin/api/v1/jobs/{job_id}", "GET")].endpoint(
            job_id=str(job_id),
        )
        microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="job",
            object_id=str(job_id),
            workspace_id="dev-01",
        )
        scheduler_alias = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="scheduler_job",
            object_id="revocation-job-1",
            workspace_id="dev-01",
        )
        return direct, microscope, scheduler_alias

    direct, microscope, scheduler_alias = asyncio.run(run())

    assert direct.object["object_type"] == "job"
    assert microscope.object["object_type"] == "job"
    assert scheduler_alias.object["object_type"] == "job"
    assert microscope.object["diagnostics"]["job_kind"] == "revocations.rollback"
    assert scheduler_alias.object["diagnostics"]["job_id"] == str(job_id)
    assert microscope.object["diagnostics"] == direct.object["diagnostics"]
    assert microscope.object["content_policy"]["raw_available"] is False
    assert {"object_type": "trace", "object_id": str(trace_id)} in microscope.object[
        "provenance"
    ]["downstream"]
    assert {"object_type": "trace_span", "object_id": str(span_id)} in microscope.object[
        "provenance"
    ]["downstream"]


def test_observatory_schedule_object_microscope_redacts_payload() -> None:
    now = datetime.now(UTC)
    schedule_id = uuid4()
    scheduler_store = MemoryObservatorySchedulerStore(
        [
            ScheduleRecord(
                schedule_id=schedule_id,
                workspace_key="dev-01",
                name="audit-hash-verification",
                job_kind="audit.verify_hash_chain",
                enabled=True,
                interval_seconds=86_400,
                next_run_at=now,
                payload={
                    "workspace_id": "dev-01",
                    "operator_note": "raw schedule note must not be returned",
                },
                misfire_policy="catch_up_limited",
            )
        ]
    )
    app = create_app(audit_store=MemoryAuditStore(), scheduler_store=scheduler_store)
    routes = _routes(app)

    async def run():
        collection = await routes[("/admin/api/v1/schedules", "GET")].endpoint()
        microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="schedule",
            object_id=str(schedule_id),
            workspace_id="dev-01",
        )
        alias = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="scheduler_schedule",
            object_id="audit-hash-verification",
            workspace_id="dev-01",
        )
        return collection, microscope, alias

    collection, microscope, alias = asyncio.run(run())

    item = collection.collection["items"][0]
    assert item["object_type"] == "schedule"
    assert item["object_id"] == str(schedule_id)
    assert item["payload_available"] is False
    assert item["payload_keys"] == ["operator_note", "workspace_id"]
    assert "payload" not in item

    payload = microscope.object
    assert payload["object_type"] == "schedule"
    assert payload["diagnostics"]["schedule_id"] == str(schedule_id)
    assert payload["diagnostics"]["job_kind"] == "audit.verify_hash_chain"
    assert payload["diagnostics"]["misfire_policy"] == "catch_up_limited"
    assert payload["diagnostics"]["payload_available"] is False
    assert payload["diagnostics"]["payload_keys"] == ["operator_note", "workspace_id"]
    assert "payload" not in payload["diagnostics"]
    assert payload["content_policy"]["raw_available"] is False
    assert payload["content_policy"]["payload_available"] is False
    assert alias.object["diagnostics"] == payload["diagnostics"]
    assert alias.object["object_id"] == str(schedule_id)


def test_observatory_profile_microscopes_show_redacted_qualification_state() -> None:
    now = datetime.now(UTC)
    model_profile_id = uuid4()
    embedding_profile_id = uuid4()
    model_profile = ModelProfileRecord(
        profile_id=model_profile_id,
        workspace_id=None,
        workspace_key="dev-01",
        profile_key="semantic-main",
        provider="openai_compatible",
        model="reasoning-model",
        route_kind="openai_compatible",
        endpoint_ref="https://provider.local/v1",
        timeout_seconds=45.0,
        thinking_level="medium",
        thinking_fallback_policy="downgrade",
        status="qualified",
        qualification={},
        kind="model",
        embedding_dim=None,
        created_at=now,
        updated_at=now,
        endpoint_kind="responses",
    )
    embedding_profile = ModelProfileRecord(
        profile_id=embedding_profile_id,
        workspace_id=None,
        workspace_key="dev-01",
        profile_key="retrieval-main",
        provider="hash",
        model="hash-embedding",
        route_kind="hash",
        endpoint_ref="https://embedding.local/v1",
        timeout_seconds=10.0,
        thinking_level="off",
        thinking_fallback_policy="omit",
        status="active",
        qualification={},
        kind="embedding",
        embedding_dim=16,
        created_at=now,
        updated_at=now,
        endpoint_kind="embeddings",
    )
    qualifications = NullProfileQualificationStore()
    app = create_app(
        audit_store=MemoryAuditStore(),
        profile_store=MemoryObservatoryProfileStore(
            model_profile=model_profile,
            embedding_profile=embedding_profile,
        ),
        profile_qualification_store=qualifications,
    )
    routes = _routes(app)

    async def run():
        await qualifications.record_model_qualification_run(
            workspace_key="dev-01",
            model_profile_id=model_profile_id,
            profile_key="semantic-main",
            route_kind="openai_compatible",
            provider="openai_compatible",
            model="reasoning-model",
            thinking_level="medium",
            probe_set_version="probe.v1",
            verdict="qualified_autonomous",
            probe_results={
                "checks": {
                    "json_adherence": True,
                    "evidence_id_preserved": True,
                },
                "output_token_estimate": 42,
                "invocation_id": str(uuid4()),
                "error": "provider leaked sk-live-secret in a raw error",
            },
        )
        await qualifications.record_embedding_qualification_run(
            workspace_key="dev-01",
            embedding_profile_id=embedding_profile_id,
            profile_key="retrieval-main",
            route_kind="hash",
            provider="hash",
            model="hash-embedding",
            embedding_dim=16,
            distance_metric="cosine",
            probe_set_version="embedding-probe.v1",
            verdict="qualified",
            probe_results={
                "checks": {
                    "dimension_matches": True,
                    "finite_values": True,
                    "non_zero": True,
                },
                "positive_similarity": 1.0,
                "negative_similarity": 0.2,
                "error": "embedding endpoint https://embedding.local/v1 failed",
            },
        )
        model_detail = await routes[
            ("/admin/api/v1/model-profile/{profile_key}", "GET")
        ].endpoint(profile_key="semantic-main", workspace_id="dev-01")
        model_object = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="model_profile",
            object_id="semantic-main",
            workspace_id="dev-01",
        )
        embedding_detail = await routes[
            ("/admin/api/v1/embedding-profile/{profile_key}", "GET")
        ].endpoint(profile_key="retrieval-main", workspace_id="dev-01")
        return model_detail, model_object, embedding_detail

    model_detail, model_object, embedding_detail = asyncio.run(run())

    model_payload = model_detail.object
    assert model_payload["object_type"] == "model_profile"
    assert model_payload["configuration"]["endpoint_ref_present"] is True
    assert "endpoint_ref" not in model_payload["configuration"]
    assert model_payload["qualification_runs"][0]["checks"]["json_adherence"] is True
    assert model_payload["qualification_runs"][0]["metrics"]["output_token_estimate"] == 42
    assert model_payload["qualification_runs"][0]["raw_error_returned"] is False
    assert model_object.object["profile_id"] == str(model_profile_id)

    embedding_payload = embedding_detail.object
    assert embedding_payload["object_type"] == "embedding_profile"
    assert embedding_payload["configuration"]["embedding_dim"] == 16
    assert embedding_payload["qualification_runs"][0]["checks"]["dimension_matches"] is True
    assert embedding_payload["qualification_runs"][0]["metrics"]["positive_similarity"] == 1.0
    serialized = json.dumps(
        {
            "model": model_payload,
            "embedding": embedding_payload,
        },
        sort_keys=True,
    )
    assert "provider.local" not in serialized
    assert "embedding.local" not in serialized
    assert "sk-live-secret" not in serialized


def test_observatory_llm_invocation_object_microscope_is_content_safe() -> None:
    invocations = NullLLMInvocationStore()
    app = create_app(
        audit_store=MemoryAuditStore(),
        llm_invocation_store=invocations,
    )
    routes = _routes(app)
    trace_id = uuid4()
    span_id = uuid4()

    async def run():
        record = await invocations.record_invocation(
            workspace_key="dev-01",
            purpose="model_profile_qualification",
            profile_key="semantic-main",
            route_kind="openai_compatible",
            provider="test-provider",
            model="reasoning-model",
            status="error",
            trace_id=trace_id,
            span_id=span_id,
            requested_thinking_level="high",
            effective_thinking_level="medium",
            thinking_fallback_policy="downgrade",
            thinking_downgraded=True,
            prompt_token_estimate=17,
            output_token_estimate=5,
            error="provider https://provider.local leaked sk-live-secret in raw error",
            audit={
                "endpoint_route": "responses",
                "finish_reason": "error",
                "provider_request_id": "req-secret-provider-id",
                "prompt": "Return a JSON proposal.",
                "api_key": "sk-live-secret",
                "raw_response": "sensitive model output",
            },
        )
        return await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="llm_invocation",
            object_id=str(record.llm_invocation_id),
            workspace_id="dev-01",
        )

    detail = asyncio.run(run())

    payload = detail.object
    assert payload["object_type"] == "llm_invocation"
    assert payload["workspace_key"] == "dev-01"
    assert payload["profile"]["profile_key"] == "semantic-main"
    assert payload["thinking"]["downgraded"] is True
    assert payload["token_estimates"] == {"prompt": 17, "output": 5}
    assert payload["status"]["state"] == "error"
    assert payload["status"]["error_present"] is True
    assert payload["status"]["error_sha256"]
    assert payload["status"]["raw_error_returned"] is False
    assert payload["audit"]["endpoint_route"] == "responses"
    assert payload["audit"]["finish_reason"] == "error"
    assert payload["audit"]["provider_request_id_sha256"]
    assert payload["audit"]["raw_audit_payload_returned"] is False
    assert {"object_type": "trace", "object_id": str(trace_id)} in payload[
        "provenance"
    ]["downstream"]
    assert {"object_type": "trace_span", "object_id": str(span_id)} in payload[
        "provenance"
    ]["downstream"]
    serialized = json.dumps(payload, sort_keys=True)
    assert "provider.local" not in serialized
    assert "sk-live-secret" not in serialized
    assert "Return a JSON proposal." not in serialized
    assert "sensitive model output" not in serialized
    assert "req-secret-provider-id" not in serialized


def test_observatory_autonomy_evidence_read_models_are_content_safe() -> None:
    observatory_admin = NullObservatoryAdminStore()
    now = datetime.now(UTC)
    decision_id = uuid4()
    adjudication_id = uuid4()
    escalation_id = uuid4()
    observatory_admin.evidence_fidelity.append(
        AdminEvidenceFidelityStatusRecord(
            workspace_key="dev-01",
            source_kind="historical_chunk",
            decision_family="intent_reconstruction",
            evidence_fidelity="metadata_only",
            item_count=7,
            autonomy_support_state="evidence_insufficient_for_autonomy",
            dominant_reason_code="metadata_only_without_redacted_derivative",
            updated_at=now,
        )
    )
    observatory_admin.autonomy_decisions.append(
        AdminAutonomyDecisionStatusRecord(
            decision_id=decision_id,
            workspace_key="dev-01",
            decision_family="skill_plan_semantic_adjudication",
            target_kind="candidate",
            target_id="candidate-1",
            action_risk_tier="T2_trial_artifact",
            hard_invariant_state="passed",
            soft_threshold_state="threshold_deadlock_candidate",
            selected_action="run_more_probes",
            confidence_band="improve_evidence",
            evidence_fidelity="redacted_derivative",
            autonomy_support_state="degraded",
            dominant_reason_code="threshold_deadlock",
            created_at=now,
            updated_at=now,
        )
    )
    observatory_admin.semantic_adjudications.append(
        AdminSemanticAdjudicationStatusRecord(
            adjudication_run_id=adjudication_id,
            workspace_key="dev-01",
            decision_family="skill_plan_semantic_adjudication",
            model_profile_id=None,
            schema_status="valid",
            confidence_band="improve_evidence",
            evidence_fidelity="redacted_derivative",
            verifier_state="not_run",
            raw_vault_exposure_class="not_exposed",
            dominant_reason_code="needs_more_probe_margin",
            started_at=now,
            completed_at=now,
        )
    )
    observatory_admin.administrative_escalations.append(
        AdminAdministrativeEscalationStatusRecord(
            event_id=escalation_id,
            workspace_key="dev-01",
            hard_boundary_kind="raw_reveal_requested",
            decision_family="memory_declassification",
            target_kind="raw_vault_record",
            target_id="vault-record-1",
            attempted_autonomous_alternatives=[
                {"action": "declassified_summary", "status": "insufficient"}
            ],
            resolution_state="open",
            dominant_reason_code="raw_reveal_requires_admin",
            opened_at=now,
            resolved_at=None,
        )
    )
    app = create_app(
        audit_store=MemoryAuditStore(),
        observatory_admin_store=observatory_admin,
    )
    routes = _routes(app)

    async def run():
        evidence = await routes[("/admin/api/v1/evidence/fidelity", "GET")].endpoint(
            workspace_id="dev-01",
            decision_family="intent_reconstruction",
            limit=10,
        )
        raw_vault = await routes[("/admin/api/v1/raw-vault/summary", "GET")].endpoint(
            workspace_id="dev-01",
            limit=10,
        )
        adjudications = await routes[("/admin/api/v1/adjudications", "GET")].endpoint(
            workspace_id="dev-01",
            decision_family="skill_plan_semantic_adjudication",
            limit=10,
        )
        adjudication_detail = await routes[
            ("/admin/api/v1/adjudications/{adjudication_run_id}", "GET")
        ].endpoint(adjudication_run_id=str(adjudication_id))
        decisions = await routes[("/admin/api/v1/autonomy/decisions", "GET")].endpoint(
            workspace_id="dev-01",
            decision_family="skill_plan_semantic_adjudication",
            limit=10,
        )
        deadlocks = await routes[
            ("/admin/api/v1/autonomy/threshold-deadlocks", "GET")
        ].endpoint(workspace_id="dev-01", limit=10)
        deadlock_detail = await routes[
            ("/admin/api/v1/autonomy/threshold-deadlocks/{decision_id}", "GET")
        ].endpoint(decision_id=str(decision_id))
        decision_detail = await routes[
            ("/admin/api/v1/autonomy/decisions/{decision_id}", "GET")
        ].endpoint(decision_id=str(decision_id))
        escalations = await routes[("/admin/api/v1/escalations", "GET")].endpoint(
            workspace_id="dev-01",
            resolution_state="open",
            limit=10,
        )
        escalation_detail = await routes[
            ("/admin/api/v1/escalations/{event_id}", "GET")
        ].endpoint(event_id=str(escalation_id))
        object_detail = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="autonomy_decision",
            object_id=str(decision_id),
            workspace_id="dev-01",
        )
        deadlock_object_detail = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="threshold_deadlock",
            object_id=str(decision_id),
            workspace_id="dev-01",
        )
        fidelity_detail = await routes[
            ("/admin/api/v1/evidence/fidelity/{fidelity_id}", "GET")
        ].endpoint(
            fidelity_id="dev-01:historical_chunk:intent_reconstruction:metadata_only"
        )
        return (
            evidence,
            raw_vault,
            adjudications,
            adjudication_detail,
            decisions,
            deadlocks,
            deadlock_detail,
            decision_detail,
            escalations,
            escalation_detail,
            object_detail,
            deadlock_object_detail,
            fidelity_detail,
        )

    (
        evidence,
        raw_vault,
        adjudications,
        adjudication_detail,
        decisions,
        deadlocks,
        deadlock_detail,
        decision_detail,
        escalations,
        escalation_detail,
        object_detail,
        deadlock_object_detail,
        fidelity_detail,
    ) = asyncio.run(run())

    evidence_item = evidence.collection["items"][0]
    assert evidence.collection["source"] == (
        "observatory_admin_store.list_evidence_fidelity_status"
    )
    assert evidence_item["autonomy_support_state"] == (
        "evidence_insufficient_for_autonomy"
    )
    assert evidence_item["content_policy"]["raw_available"] is False
    assert raw_vault.collection["diagnostics"]["raw_vault_records_returned"] is False

    adjudication_item = adjudications.collection["items"][0]
    assert adjudications.collection["diagnostics"]["verdict_payload_returned"] is False
    assert adjudication_item["object_id"] == str(adjudication_id)
    assert adjudication_detail.object["raw_vault_exposure_class"] == "not_exposed"

    decision_item = decisions.collection["items"][0]
    assert decision_item["selected_action"] == "run_more_probes"
    assert decision_detail.object["hard_invariant_state"] == "passed"
    assert object_detail.object["object_type"] == "autonomy_decision"
    assert deadlocks.collection["items"][0]["object_type"] == "threshold_deadlock"
    assert deadlocks.collection["items"][0]["object_id"] == str(decision_id)
    assert deadlock_detail.object["autonomy_decision"]["object_type"] == (
        "autonomy_decision"
    )
    assert deadlock_detail.object["diagnostics"]["safe_next_action"] == (
        "inspect_adjudication_and_collect_more_evidence"
    )
    assert deadlock_detail.object["content_policy"]["raw_available"] is False
    assert deadlock_object_detail.object["object_type"] == "threshold_deadlock"

    escalation_item = escalations.collection["items"][0]
    assert escalation_item["hard_boundary_kind"] == "raw_reveal_requested"
    assert escalation_detail.object["attempted_autonomous_alternatives"] == [
        {"action": "declassified_summary", "status": "insufficient"}
    ]
    assert fidelity_detail.object["object_type"] == "evidence_fidelity_status"
    combined = json.dumps(
        [
            evidence.collection,
            raw_vault.collection,
            adjudications.collection,
            decisions.collection,
            escalations.collection,
        ],
        sort_keys=True,
    )
    assert "raw operator transcript" not in combined
    assert "verbatim_llm_verdict" not in combined


def test_observatory_topology_exposes_operation_metrics_read_model() -> None:
    topology = NullTopologyStore()
    transaction_id = uuid4()

    async def seed() -> None:
        operation = await topology.record_operation(
            workspace_key="dev-01",
            operation_kind="decompose",
            status="accepted",
            subject_skill_ids=[uuid4()],
            output_skill_ids=[uuid4(), uuid4()],
            evolution_transaction_id=transaction_id,
            effect_coverage={"context_value_gate": "passed"},
            trial_summary={"decision": "split broad context"},
        )
        await topology.record_planned_trial(
            workspace_key="dev-01",
            skill_graph_operation_id=operation.skill_graph_operation_id,
            trial_kind="context_value",
            objective="successors preserve utility while lowering token waste",
            expected={"token_waste_reduction": True},
            status="passed",
        )

    asyncio.run(seed())
    governance = MemoryTopologyGovernanceStore(
        [
            EvolutionTransactionRecord(
                evolution_transaction_id=transaction_id,
                workspace_id=uuid4(),
                workspace_key="dev-01",
                transaction_kind="topology_decompose",
                status="staged",
                idempotency_key="topology:decompose:safe",
                plan_hash="topology-plan-hash",
                actor="autoskill-sidecar",
                cause={"redacted": True},
                source_evidence_ids=[uuid4(), uuid4()],
                source_memory_ids=[],
                policy_snapshot={"policy": "topology_policy.v1"},
                metrics={
                    "topology_operation_kind": "decompose",
                    "topology_status": "accepted",
                    "plan_hash": "topology-plan-hash",
                    "evidence_count": 2,
                    "planned_trials": 1,
                    "trial_kinds": ["context_value"],
                    "blockers": 0,
                    "graph_node_count": 3,
                    "graph_edge_count": 2,
                    "graph_node_roles": {"subject": 1, "successor": 2},
                    "graph_edge_kinds": {"decomposes_to": 2},
                    "effect_coverage_count": 1,
                    "rollback_blockers": 0,
                    "rollback_actions": 1,
                    "rollback_actions_planned": True,
                    "writes": ["skills/autoskill/split-successor"],
                    "requires_trial_before_apply": True,
                    "data_to_skill_trace": {
                        "schema_version": "skillkernel.data-to-skill-trace.topology.v1",
                        "operation_kind": "decompose",
                        "status": "candidate",
                        "plan_hash": "topology-plan-hash",
                        "terminal_stage": "planned_trials",
                        "failure_exit": None,
                        "stage_count": 2,
                        "stages": [
                            {
                                "name": "evidence_packet",
                                "status": "present",
                                "reason_codes": ["cited-evidence"],
                                "input_refs": [
                                    {
                                        "object_type": "evidence_item",
                                        "object_id": "safe-evidence-id",
                                        "raw_text": "raw supporting transcript",
                                    }
                                ],
                                "output_refs": [
                                    {
                                        "object_type": "topology_evidence_packet",
                                        "object_id": "topology-plan-hash",
                                    }
                                ],
                                "raw_stage_payload": "raw skill body must not leak",
                            },
                            {
                                "name": "planned_trials",
                                "status": "planned",
                                "reason_codes": ["trial-before-apply-required"],
                                "input_refs": [],
                                "output_refs": [
                                    {
                                        "object_type": "planned_topology_trial",
                                        "object_id": "trial-id",
                                    }
                                ],
                            },
                        ],
                        "raw_trace_payload": "raw operator content",
                    },
                    "raw_plan_text": "raw skill body must not leak",
                },
                rollback_of_transaction_id=None,
                started_at=datetime.now(UTC),
                committed_at=None,
                rolled_back_at=None,
            )
        ]
    )
    app = create_app(
        topology_store=topology,
        governance_store=governance,
        audit_store=MemoryAuditStore(),
    )
    route = next(route for route in app.routes if route.path == "/admin/api/v1/topology")

    async def run():
        return await route.endpoint(
            authorization=None,
            x_skillkernel_roles=None,
            workspace_id="dev-01",
            window_minutes=60,
            limit=10,
        )

    response = asyncio.run(run())
    payload = response.object
    metrics = payload["operation_metrics"]

    assert (
        payload["read_model"]["source"]
        == "topology_store.metrics+governance.evolution_transactions.metrics"
    )
    assert payload["content_policy"]["raw_available"] is False
    assert metrics["operations_by_kind"]["decompose"]["accepted"] == 1
    assert metrics["operations_by_kind"]["create"]["total"] == 0
    assert metrics["trials_by_operation_kind"]["decompose"]["context_value"]["passed"] == 1
    assert metrics["recent_operations"][0]["operation_kind"] == "decompose"
    review = payload["transaction_review"]
    assert review["source"] == "governance.evolution_transactions.metrics"
    assert review["counts_by_transaction_kind"]["topology_decompose"] == 1
    assert review["counts_by_status"]["staged"] == 1
    assert review["content_policy"]["raw_available"] is False
    assert review["recent"][0]["evolution_transaction_id"] == str(transaction_id)
    assert review["recent"][0]["topology_operation_kind"] == "decompose"
    assert review["recent"][0]["evidence_count"] == 2
    assert review["recent"][0]["graph_node_roles"] == {"subject": 1, "successor": 2}
    assert review["recent"][0]["requires_trial_before_apply"] is True
    trace = review["recent"][0]["data_to_skill_trace"]
    assert trace["schema_version"] == "skillkernel.data-to-skill-trace.topology.v1"
    assert trace["terminal_stage"] == "planned_trials"
    assert trace["content_policy"]["raw_available"] is False
    assert trace["stages"][0]["input_refs"] == [
        {"object_type": "evidence_item", "object_id": "safe-evidence-id"}
    ]
    assert trace["stages"][1]["output_refs"] == [
        {"object_type": "planned_topology_trial", "object_id": "trial-id"}
    ]
    assert "raw skill body" not in json.dumps(review, sort_keys=True)
    assert "raw supporting transcript" not in json.dumps(review, sort_keys=True)
    assert "raw operator content" not in json.dumps(review, sort_keys=True)


def test_observatory_evolution_transaction_object_microscope_is_content_safe() -> None:
    transaction_id = uuid4()
    evidence_id = uuid4()
    item_id = uuid4()
    governance = MemoryTopologyGovernanceStore(
        [
            EvolutionTransactionRecord(
                evolution_transaction_id=transaction_id,
                workspace_id=uuid4(),
                workspace_key="dev-01",
                transaction_kind="topology_compose",
                status="committed",
                idempotency_key="raw operator idempotency text",
                plan_hash="compose-plan-hash",
                actor="autoskill-sidecar",
                cause={"raw_reason": "raw operator rationale"},
                source_evidence_ids=[evidence_id],
                source_memory_ids=[],
                policy_snapshot={"policy": "topology_policy.v1"},
                metrics={
                    "topology_operation_kind": "compose",
                    "topology_status": "accepted",
                    "evidence_count": 1,
                    "planned_trials": 2,
                    "trial_kinds": ["component_only", "composed"],
                    "graph_node_count": 3,
                    "graph_edge_count": 2,
                    "rollback_actions": 1,
                    "rollback_actions_planned": True,
                    "writes": ["skills/autoskill/compose-workflow"],
                    "requires_trial_before_apply": True,
                    "data_to_skill_trace": {
                        "schema_version": "skillkernel.data-to-skill-trace.topology.v1",
                        "operation_kind": "compose",
                        "status": "candidate",
                        "plan_hash": "compose-plan-hash",
                        "terminal_stage": "transaction",
                        "failure_exit": None,
                        "stages": [
                            {
                                "name": "transaction",
                                "status": "recorded",
                                "reason_codes": ["transaction-recorded"],
                                "input_refs": [
                                    {
                                        "object_type": "evidence_item",
                                        "object_id": str(evidence_id),
                                        "raw_text": "raw evidence text",
                                    }
                                ],
                                "output_refs": [
                                    {
                                        "object_type": "evolution_transaction",
                                        "object_id": str(transaction_id),
                                    }
                                ],
                            }
                        ],
                    },
                    "raw_plan_text": "raw skill body",
                },
                rollback_of_transaction_id=None,
                started_at=datetime.now(UTC),
                committed_at=datetime.now(UTC),
                rolled_back_at=None,
            )
        ],
        items=[
            EvolutionTransactionItemRecord(
                transaction_item_id=uuid4(),
                evolution_transaction_id=transaction_id,
                item_kind="compiled_skill_package",
                item_id=item_id,
                relative_path="skills/autoskill/compose-workflow/SKILL.md",
                before_hash=None,
                after_hash="package-after-hash",
                activation_state="staged",
                rollback_action={
                    "operation": "archive_created_skill",
                    "raw_instruction": "raw rollback text",
                },
                created_at=datetime.now(UTC),
            )
        ],
    )
    app = create_app(governance_store=governance, audit_store=MemoryAuditStore())
    route = next(
        route for route in app.routes if route.path == "/admin/api/v1/objects/{object_type}/{object_id}"
    )

    async def run():
        return await route.endpoint(
            object_type="evolution_transaction",
            object_id=str(transaction_id),
            authorization=None,
            x_skillkernel_roles=None,
            workspace_id="dev-01",
            window_minutes=60,
        )

    response = asyncio.run(run())
    payload = response.object

    assert payload["object_type"] == "evolution_transaction"
    assert payload["object_id"] == str(transaction_id)
    assert payload["content_policy"]["raw_available"] is False
    assert payload["idempotency_key_hash"] == sha256_text("raw operator idempotency text")
    assert payload["provenance"]["upstream"] == [
        {"object_type": "evidence", "object_id": str(evidence_id)}
    ]
    assert payload["effects"]["items"][0]["item_kind"] == "compiled_skill_package"
    assert payload["effects"]["items"][0]["item_id"] == str(item_id)
    assert payload["effects"]["items"][0]["rollback_operation"] == "archive_created_skill"
    metrics = payload["diagnostics"]["metrics"]
    assert metrics["topology_operation_kind"] == "compose"
    assert metrics["requires_trial_before_apply"] is True
    assert metrics["data_to_skill_trace"]["stages"][0]["input_refs"] == [
        {"object_type": "evidence_item", "object_id": str(evidence_id)}
    ]
    rendered = json.dumps(payload, sort_keys=True)
    assert "raw operator idempotency text" not in rendered
    assert "raw operator rationale" not in rendered
    assert "raw evidence text" not in rendered
    assert "raw skill body" not in rendered
    assert "raw rollback text" not in rendered


def test_observatory_writer_transaction_object_microscope_is_content_safe() -> None:
    transaction_id = uuid4()
    manifest_item_id = uuid4()
    file_item_id = uuid4()
    governance = MemoryTopologyGovernanceStore(
        [
            EvolutionTransactionRecord(
                evolution_transaction_id=transaction_id,
                workspace_id=uuid4(),
                workspace_key="dev-01",
                transaction_kind="compile_skill",
                status="applied",
                idempotency_key="raw writer idempotency text",
                plan_hash="writer-plan-hash",
                actor="autoskill-sidecar",
                cause={"raw_reason": "raw writer rationale"},
                source_evidence_ids=[],
                source_memory_ids=[],
                policy_snapshot={"policy": "writer_policy.v1"},
                metrics={
                    "slug": "context-repair",
                    "active_relative_path": "skills/autoskill/context-repair",
                    "manifest_sha256": "manifest-safe-hash",
                    "file_count": 2,
                    "previous_snapshot": ".autoskill/archive/skill/v1/.autoskill-manifest.json",
                    "manifest_relative_path": "staged/context-repair/.autoskill-manifest.json",
                    "activation_deferred": True,
                    "activation_window": {
                        "allowed": False,
                        "status": "deferred",
                        "reason": "session_active",
                        "raw_session_note": "raw session content",
                    },
                    "raw_manifest_payload": "raw generated skill text",
                },
                rollback_of_transaction_id=None,
                started_at=datetime.now(UTC),
                committed_at=datetime.now(UTC),
                rolled_back_at=None,
            )
        ],
        items=[
            EvolutionTransactionItemRecord(
                transaction_item_id=uuid4(),
                evolution_transaction_id=transaction_id,
                item_kind="artifact_manifest",
                item_id=manifest_item_id,
                relative_path="skills/autoskill/context-repair/.autoskill-manifest.json",
                before_hash=None,
                after_hash="manifest-safe-hash",
                activation_state="active",
                rollback_action={
                    "operation": "restore_archive_manifest",
                    "raw_instruction": "raw rollback text",
                },
                created_at=datetime.now(UTC),
            ),
            EvolutionTransactionItemRecord(
                transaction_item_id=uuid4(),
                evolution_transaction_id=transaction_id,
                item_kind="compiled_skill_file",
                item_id=file_item_id,
                relative_path="skills/autoskill/context-repair/SKILL.md",
                before_hash="old-hash",
                after_hash="new-hash",
                activation_state="active",
                rollback_action={"operation": "restore_archive_manifest"},
                created_at=datetime.now(UTC),
            ),
        ],
    )
    app = create_app(governance_store=governance, audit_store=MemoryAuditStore())
    route = next(
        route for route in app.routes if route.path == "/admin/api/v1/objects/{object_type}/{object_id}"
    )

    async def run():
        return await route.endpoint(
            object_type="writer_transaction",
            object_id=str(transaction_id),
            authorization=None,
            x_skillkernel_roles=None,
            workspace_id="dev-01",
            window_minutes=60,
        )

    response = asyncio.run(run())
    payload = response.object

    assert payload["schema_version"] == "skillkernel.observatory.writer-transaction.v1"
    assert payload["object_type"] == "writer_transaction"
    assert payload["object_id"] == str(transaction_id)
    assert payload["content_policy"]["raw_available"] is False
    assert payload["diagnostics"]["supporting_component"] == "deterministic_writer"
    assert payload["diagnostics"]["activation_deferred"] is True
    assert payload["effects"]["writer_metrics"]["manifest_sha256"] == "manifest-safe-hash"
    assert payload["effects"]["writer_metrics"]["activation_window"] == {
        "raw_window_payload_returned": False,
        "key_count": 4,
        "allowed": False,
        "status": "deferred",
        "reason": "session_active",
    }
    assert payload["effects"]["items"][0]["item_kind"] == "artifact_manifest"
    assert payload["effects"]["items"][0]["rollback_operation"] == (
        "restore_archive_manifest"
    )
    assert payload["effects"]["rollback_metadata_present"] is True
    assert payload["audit"]["links"] == [
        {"object_type": "evolution_transaction", "object_id": str(transaction_id)},
        {"object_type": "writer_transaction", "object_id": str(transaction_id)},
    ]
    rendered = json.dumps(payload, sort_keys=True)
    assert "raw writer idempotency text" not in rendered
    assert "raw writer rationale" not in rendered
    assert "raw generated skill text" not in rendered
    assert "raw session content" not in rendered
    assert "raw rollback text" not in rendered


def test_observatory_revocation_request_object_microscope_is_content_safe() -> None:
    revocation_request_id = uuid4()
    root_object_id = uuid4()
    skill_version_id = uuid4()
    rollback_transaction_id = uuid4()
    created_by_job_id = uuid4()
    governance = MemoryTopologyGovernanceStore(
        [],
        revocations=[
            RevocationRequestRecord(
                revocation_request_id=revocation_request_id,
                workspace_id=uuid4(),
                workspace_key="dev-01",
                request_kind="rollback",
                root_object_type="evolution_transaction",
                root_object_id=root_object_id,
                status="completed",
                traversal_summary={
                    "source": "critical_canary",
                    "raw_operator_reason": "raw rollback rationale",
                    "impacted_count": 2,
                    "impacted_objects": [
                        {
                            "object_type": "evolution_transaction",
                            "object_id": str(root_object_id),
                            "depth": 0,
                            "raw_payload": "raw root payload",
                        },
                        {
                            "object_type": "skill_version",
                            "object_id": str(skill_version_id),
                            "depth": 1,
                            "raw_skill_text": "raw generated skill text",
                        },
                    ],
                    "edges": [
                        {
                            "source_kind": "evolution_transaction",
                            "source_id": str(root_object_id),
                            "derived_kind": "skill_version",
                            "derived_id": str(skill_version_id),
                            "relation": "created_version",
                            "raw_edge_note": "raw provenance note",
                        }
                    ],
                    "rollback_transaction_id": str(rollback_transaction_id),
                    "invalidation": {
                        "objects": 2,
                        "embeddings_deleted": 1,
                        "raw_error": "raw invalidation detail",
                    },
                },
                created_by_job_id=created_by_job_id,
                created_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        ],
    )
    app = create_app(governance_store=governance, audit_store=MemoryAuditStore())
    route = next(
        route for route in app.routes if route.path == "/admin/api/v1/objects/{object_type}/{object_id}"
    )

    async def run():
        return await route.endpoint(
            object_type="revocation_request",
            object_id=str(revocation_request_id),
            authorization=None,
            x_skillkernel_roles=None,
            workspace_id="dev-01",
            window_minutes=60,
        )

    response = asyncio.run(run())
    payload = response.object

    assert payload["schema_version"] == "skillkernel.observatory.revocation-request.v1"
    assert payload["object_type"] == "revocation_request"
    assert payload["object_id"] == str(revocation_request_id)
    assert payload["status"] == "completed"
    assert payload["root"] == {
        "object_type": "evolution_transaction",
        "object_id": str(root_object_id),
        "relationship": "revocation_root",
    }
    assert payload["provenance"]["upstream"] == [
        {
            "object_type": "evolution_transaction",
            "object_id": str(root_object_id),
            "relationship": "revocation_root",
        },
        {
            "object_type": "job",
            "object_id": str(created_by_job_id),
            "relationship": "created_by_job",
        },
    ]
    assert {
        "object_type": "skill_version",
        "object_id": str(skill_version_id),
        "relationship": "impacted_by_revocation",
    } in payload["provenance"]["downstream"]
    traversal = payload["effects"]["traversal"]
    assert traversal["impacted_count"] == 2
    assert traversal["impacted_objects"][1] == {
        "object_type": "skill_version",
        "object_id": str(skill_version_id),
        "depth": 1,
    }
    assert traversal["edges"][0] == {
        "source_kind": "evolution_transaction",
        "source_id": str(root_object_id),
        "derived_kind": "skill_version",
        "derived_id": str(skill_version_id),
        "relation": "created_version",
    }
    assert traversal["invalidation"]["objects"] == 2
    assert traversal["invalidation"]["embeddings_deleted"] == 1
    assert payload["content_policy"]["raw_available"] is False
    assert payload["diagnostics"]["raw_traversal_summary_returned"] is False
    rendered = json.dumps(payload, sort_keys=True)
    assert "raw rollback rationale" not in rendered
    assert "raw root payload" not in rendered
    assert "raw generated skill text" not in rendered
    assert "raw provenance note" not in rendered
    assert "raw invalidation detail" not in rendered


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
                            "raw_candidate_summary": "raw candidate body text",
                        }
                    ],
                    "reason_codes": ["vector-fused"],
                    "suppressed": [
                        {
                            "object_type": "skill",
                            "object_id": str(rendered_skill_id),
                            "reason": "duplicate-skill",
                            "raw_suppression_context": "raw suppressed body text",
                        }
                    ],
                    "raw_query_text": "operator secret retrieval query",
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
        object_detail = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="broker_decision",
            object_id=str(retrieval_log_id),
            workspace_id="dev-01",
        )
        return collection, detail, object_detail

    collection, detail, object_detail = asyncio.run(run())

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
    assert object_detail.object == detail.object
    assert detail.object["effects"]["suppressed"][0]["reason"] == "duplicate-skill"
    assert detail.object["content_policy"]["metadata_values_returned"] is False
    rendered = json.dumps(detail.object, sort_keys=True)
    assert "operator secret retrieval query" not in rendered
    assert "raw candidate body text" not in rendered
    assert "raw suppressed body text" not in rendered


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
    started_at = datetime.now(UTC)
    span_id = uuid4()
    child_span_id = uuid4()
    span = TraceSpanRecord(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=None,
        workspace_id=None,
        workspace_key="dev-01",
        operation_name="broker decision",
        operation_kind="broker",
        status="ok",
        safe_attributes={
            "decision": "skill_hint",
            "policy_gate_passed": True,
            "manifest_hash": "manifest-safe-hash",
        },
        object_refs=[{"object_type": "captured_event", "object_id": str(event.event_id)}],
        started_at=started_at,
        ended_at=started_at + timedelta(milliseconds=25),
    )
    child_span = TraceSpanRecord(
        trace_id=trace_id,
        span_id=child_span_id,
        parent_span_id=span_id,
        workspace_id=None,
        workspace_key="dev-01",
        operation_name="writer apply",
        operation_kind="writer",
        status="denied",
        safe_attributes={
            "activation_gate_status": "blocked",
            "after_hash": "candidate-safe-hash",
        },
        object_refs=[
            {"object_type": "captured_event", "object_id": str(event.event_id)},
            {"object_type": "skill_version", "object_id": "version-1"},
        ],
        started_at=started_at + timedelta(milliseconds=30),
        ended_at=started_at + timedelta(milliseconds=45),
    )
    app = create_app(
        audit_store=MemoryAuditStore(),
        event_store=event_store,
        observability_store=MemoryTraceStore([child_span, span]),
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
        trace_object_detail = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="trace",
            object_id=str(trace_id),
            workspace_id="dev-01",
        )
        return events, traces, detail, replay, object_detail, trace_object_detail

    events, traces, detail, replay, object_detail, trace_object_detail = asyncio.run(
        run()
    )

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
    assert replay.object["timeline"][0]["component_id"] == "broker_runtime"
    assert replay.object["timeline"][0]["duration_ms"] == 25
    assert replay.object["timeline"][1]["component_id"] == "deterministic_writer"
    assert replay.object["span_waterfall"][1]["parent_span_id"] == str(span_id)
    assert {
        item["component_id"] for item in replay.object["station_highlights"]
    } == {"broker_runtime", "deterministic_writer"}
    assert replay.object["policy_gate_badges"][0]["label"] == "policy_gate_passed"
    assert replay.object["policy_gate_badges"][0]["status"] == "passed"
    assert any(
        item["label"] == "activation_gate_status" and item["status"] == "blocked"
        for item in replay.object["policy_gate_badges"]
    )
    assert replay.object["diff_panels"][0]["raw_diff_available"] is False
    assert replay.object["redacted_export_bundle"]["raw_content_included"] is False
    assert replay.object["redacted_export_bundle"]["span_count"] == 2
    assert len(replay.object["provenance"]["downstream"]) == 2
    assert replay.object["replay_safety"]["reexecutes_work"] is False
    assert replay.object["replay_safety"]["raw_content_included"] is False
    assert replay.object["replay_safety"]["uses_persisted_state_only"] is True
    assert replay.object["content_policy"]["raw_available"] is False
    assert object_detail.object["object_type"] == "captured_event"
    assert object_detail.object["effects"]["payload_hash"] == event.payload_hash
    assert object_detail.object["content_policy"]["raw_available"] is False
    assert trace_object_detail.object["object_type"] == "trace"
    assert trace_object_detail.object["object_id"] == str(trace_id)
    assert trace_object_detail.object["diagnostics"]["supporting_component"] == (
        "audit_trace"
    )
    assert trace_object_detail.object["diagnostics"]["span_count"] == 2
    assert trace_object_detail.object["diagnostics"]["raw_span_attributes_returned"] is False
    assert trace_object_detail.object["provenance"]["downstream"][0]["object_id"] == str(
        event.event_id
    )
    assert trace_object_detail.object["content_policy"]["raw_available"] is False


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


def test_observatory_embedding_backlog_uses_canonical_embedding_object_types() -> None:
    operator_metrics_source = inspect.getsource(
        observability_module.AsyncpgObservabilityStore.operator_metrics
    )

    assert "active_embedding_profile AS" in operator_metrics_source
    assert "e.embedding_profile_id = (" in operator_metrics_source
    assert "e.object_type = $2" in operator_metrics_source
    assert "e.object_type = $3" in operator_metrics_source
    assert "e.object_type = $4" in operator_metrics_source
    assert "e.object_type = $5" in operator_metrics_source
    assert "e.object_type = 'evidence'" not in operator_metrics_source
    assert EMBEDDING_OBJECT_TYPE_EVIDENCE_ITEM == "evidence_item"
    assert EMBEDDING_OBJECT_TYPE_BODY_INDEX_DOCUMENT == "body_index_document"
    assert EMBEDDING_OBJECT_TYPE_EXTERNAL_SKILL == "external_skill"
    assert EMBEDDING_OBJECT_TYPE_HISTORICAL_IMPORT_CHUNK == "historical_import_chunk"


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
    generic_route = _routes(app)[("/admin/api/v1/objects/{object_type}/{object_id}", "GET")]

    async def run():
        artifact = await route.endpoint(artifact_id="artifact-123")
        generic = await generic_route.endpoint(
            object_type="unsupported_object",
            object_id="missing-123",
            workspace_id="dev-01",
        )
        return artifact, generic

    artifact, generic = asyncio.run(run())

    assert artifact.object["diagnostics"]["reason_codes"] == ["read-model-missing"]
    assert artifact.object["diagnostics"]["supporting_component"] == "deterministic_writer"
    assert generic.object["diagnostics"]["reason_codes"] == ["read-model-missing"]
    assert generic.object["diagnostics"]["supporting_component"] == "observatory_admin"
    assert generic.object["content_policy"]["raw_available"] is False


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


def test_observatory_missing_required_signal_issue_cites_metric_contract() -> None:
    settings = get_settings().model_copy(
        update={
            "database_url": "postgresql://autoskill:autoskill-dev@127.0.0.1/autoskill",
            "control_token": "control-token",
        }
    )
    metrics = {
        "ingest": {"events_in_window": 1, "total_events": 1},
        "redaction_counts": {},
        "spool_backlog": {},
        "retrieval_decisions": {},
        "embedding_backlog": {},
        "context_hint_injection_count": 0,
        "context_hint_token_cost": 0,
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
            "metrics": metrics,
            "dashboards": {},
        },
        worker_health={},
        audit_chain_valid=True,
        static_available=True,
        workspace_id="dev-01",
        window_minutes=10,
    )

    issue = next(
        issue
        for issue in snapshot["issue_board"]  # type: ignore[index]
        if issue["issue_id"] == "context_compiler:missing-required-signal"
    )
    assert issue["diagnostics"]["missing_metric_keys"] == [
        "context_hint_token_ledger_count"
    ]
    assert issue["evidence_refs"] == [
        {
            "object_type": "component",
            "object_id": "context_compiler",
            "relationship": "affected_component",
        },
        {
            "object_type": "required_signal_metric",
            "object_id": "context_hint_token_ledger_count",
            "relationship": "missing_metric_key",
            "component_id": "context_compiler",
        },
    ]

    detail = object_microscope(
        snapshot,
        object_type="issue",
        object_id="context_compiler:missing-required-signal",
    )
    assert detail["diagnostics"]["diagnostics"]["missing_signals"] == [
        "evidence",
        "quality",
    ]
    assert detail["provenance"]["upstream"][1]["object_type"] == "required_signal_metric"


def test_observatory_scanner_finding_microscope_exposes_gate_signal_without_raw_content() -> None:
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
                "scanner_reject_counts": {"skill_versions": 2},
                "evaluation_pass_fail_counts": {},
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

    scanner = next(
        station
        for station in snapshot["pipeline"]["stations"]  # type: ignore[index]
        if station["component_id"] == "scanner_security"
    )
    assert scanner["records"][0]["object_id"] == "scanner_reject_counts"

    detail = object_microscope(
        snapshot,
        object_type="scanner_finding",
        object_id="scanner_reject_counts",
    )

    assert detail["object_type"] == "scanner_finding"
    assert detail["diagnostics"]["gate_effect"] == "blocks_writer_activation"
    assert detail["diagnostics"]["record"]["summary"]["skill_versions"] == 2
    assert detail["content_policy"]["raw_available"] is False
    assert detail["provenance"]["upstream"][0] == {
        "object_type": "component",
        "object_id": "scanner_security",
        "relationship": "owning_gate",
    }
    assert {
        "object_type": "pipeline_invariant",
        "object_id": "gates-cover-writer-activation",
    } in detail["provenance"]["downstream"]


def test_observatory_evaluation_detail_exposes_autonomy_assurance() -> None:
    evaluation_id = uuid4()
    skill_version_id = uuid4()
    evaluation_store = NullEvaluationStore()
    evaluation_store.reviews = [
        EvaluationReviewRecord(
            workspace_id=uuid4(),
            workspace_key="dev-01",
            evaluation_id=evaluation_id,
            skill_version_id=skill_version_id,
            skill_slug="context-repair",
            skill_version=2,
            executor_profile_id=None,
            category="proposal_gate",
            status="needs_intervention",
            result_summary={
                "candidate_slug": "context-repair",
                "status": "needs_intervention",
                "reason_codes": ["intervention-required"],
                "autonomy_assurance": {
                    "decision_family": "skill_plan_semantic_adjudication",
                    "policy_version": "proposal_gate_acceptance_policy.v1",
                    "hard_invariant_failures": [],
                    "soft_threshold_misses": ["intervention-required"],
                    "autonomous_fallback_actions": [
                        "assemble_richer_permitted_evidence",
                        "generate_more_probes",
                    ],
                    "threshold_deadlock_candidate": True,
                    "administrative_escalation_allowed": False,
                    "calibration_support_status": "fixed_policy_pending_replay_calibration",
                    "evidence_mode": "semantic_derivative_only",
                },
            },
            created_at=datetime.now(UTC),
        )
    ]
    app = create_app(evaluation_store=evaluation_store)
    routes = _routes(app)

    async def run():
        direct = await routes[("/admin/api/v1/evaluations/{evaluation_id}", "GET")].endpoint(
            evaluation_id=str(evaluation_id),
            workspace_id="dev-01",
        )
        microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="evaluation",
            object_id=str(evaluation_id),
            workspace_id="dev-01",
        )
        return direct, microscope

    response, microscope_response = asyncio.run(run())
    detail = response.object
    microscope = microscope_response.object
    diagnostics = detail["diagnostics"]

    assert detail["content_policy"]["raw_available"] is False
    assert microscope["object_type"] == "evaluation"
    assert microscope["object_id"] == str(evaluation_id)
    assert microscope["diagnostics"]["autonomy_decision"] == diagnostics[
        "autonomy_decision"
    ]
    assert microscope["content_policy"]["raw_available"] is False
    assert diagnostics["autonomy_decision"]["state"] == "soft_threshold_stalled"
    assert diagnostics["autonomy_decision"]["threshold_deadlock_candidate"] is True
    assert diagnostics["soft_threshold_misses"] == ["intervention-required"]
    assert diagnostics["hard_invariant_failures"] == []
    assert diagnostics["operator_next_actions"] == [
        "assemble_richer_permitted_evidence",
        "generate_more_probes",
    ]
    assert diagnostics["policy_blocked_actions"] == [
        "raw_content_reveal_without_policy_reason",
        "manual_override_of_hard_invariants",
    ]
    assert {
        "object_type": "soft_threshold",
        "object_id": "intervention-required",
        "relationship": "calibrated_threshold_miss",
    } in detail["provenance"]["upstream"]
    assert {
        "object_type": "skill_version",
        "object_id": str(skill_version_id),
        "relationship": "evaluated_artifact",
    } in detail["provenance"]["upstream"]


def test_observatory_action_records_audited_policy_receipt() -> None:
    audit_store = MemoryAuditStore()
    attribution_store = NullAttributionStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=audit_store,
        attribution_store=attribution_store,
        observatory_admin_store=observatory_admin,
    )
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
    attribution_link = response.receipt["action_attribution_check"]
    assert attribution_link["action_kind"] == "observatory.verify_audit_chain"
    assert attribution_link["risk_tier"] == "low"
    assert attribution_link["verdict"] == "allowed"
    assert response.receipt["action_audit"]["request_payload_redacted"][
        "action_attribution_check"
    ] == attribution_link
    assert len(attribution_store.checks) == 1
    assert attribution_store.checks[0].tool_call_id == response.meta["request_id"]
    assert attribution_store.checks[0].user_intent_hash.startswith("sha256:")
    assert attribution_store.checks[0].metrics["reason_codes"] == []
    assert attribution_store.checks[0].metrics["raw_content_included"] is False
    assert response.receipt["live_event"]["event_type"] == "audit_record_appended"
    assert response.receipt["live_event"]["object_type"] == "audit"
    assert observatory_admin.live_events[0].seq == response.receipt["live_event"]["seq"]
    assert observatory_admin.actions[0].action_id.hex == (
        response.receipt["action_audit"]["action_id"].replace("-", "")
    )
    assert audit_store.records[0].action == "observatory.verify_audit_chain"


def test_observatory_action_audit_read_model_exposes_receipts_without_raw_content() -> None:
    audit_store = MemoryAuditStore()
    attribution_store = NullAttributionStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=audit_store,
        attribution_store=attribution_store,
        observatory_admin_store=observatory_admin,
    )
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
        attribution_microscope = await routes[
            ("/admin/api/v1/objects/{object_type}/{object_id}", "GET")
        ].endpoint(
            object_type="action_attribution_check",
            object_id=first.receipt["action_attribution_check"][
                "action_attribution_check_id"
            ],
        )
        return first, collection, detail, microscope, attribution_microscope

    first, collection, detail, microscope, attribution_microscope = asyncio.run(run())

    assert collection.collection["source"] == "observatory_admin_store.list_action_audits"
    assert collection.collection["object_type"] == "admin_action"
    assert collection.collection["count"] == 1
    assert collection.collection["diagnostics"]["filter"]["workspace_id"] == "dev-01"
    assert collection.collection["items"][0]["action_kind"] == "verify_audit_chain"
    assert collection.collection["items"][0]["diagnostics"]["metadata_keys"] == ["ticket"]
    assert collection.collection["items"][0]["content_policy"]["raw_available"] is False
    assert (
        collection.collection["items"][0]["request_payload_redacted"]["reason_codes"]
        == []
    )
    assert detail.object["object_id"] == first.receipt["action_audit"]["action_id"]
    assert detail.object["provenance"]["upstream"][0]["object_type"] == "audit_record"
    assert detail.object["diagnostics"]["request_id"].startswith("req_")
    assert detail.object["diagnostics"]["action_attribution_check"]["verdict"] == (
        "allowed"
    )
    assert detail.object["provenance"]["upstream"][1]["object_type"] == (
        "action_attribution_check"
    )
    assert detail.object["effects"]["dry_run"] is True
    assert detail.object["content_policy"]["raw_available"] is False
    assert "operator requested audit proof" in detail.object["reason"]
    assert detail.object["request_payload_redacted"]["confirmation_hash"] is None
    assert "INC-1" not in str(detail.object["request_payload_redacted"])
    assert microscope.object["object_type"] == "admin_action"
    assert microscope.object["audit"]["chain_visible"] is True
    attribution_detail = attribution_microscope.object
    assert attribution_detail["object_type"] == "action_attribution_check"
    assert attribution_detail["verdict"] == "allowed"
    assert attribution_detail["risk_tier"] == "low"
    assert attribution_detail["metrics"]["request_id"] == first.meta["request_id"]
    assert attribution_detail["metrics"]["idempotency_key_hash"] == sha256_text(
        "obs-audit-list-1"
    )
    assert attribution_detail["metrics"]["source"] == {
        "ip_present": False,
        "proxy_present": False,
    }
    assert attribution_detail["effects"]["target_type"] == "audit"
    assert attribution_detail["effects"]["raw_content_included"] is False
    assert attribution_detail["diagnostics"]["reason_codes"] == []
    assert "operator requested audit proof" not in str(attribution_detail)
    assert "INC-1" not in str(attribution_detail)


def test_observatory_high_impact_action_requires_confirmation() -> None:
    audit_store = MemoryAuditStore()
    attribution_store = NullAttributionStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(
        audit_store=audit_store,
        attribution_store=attribution_store,
        observatory_admin_store=observatory_admin,
    )
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
    assert response.receipt["action_attribution_check"]["risk_tier"] == "high"
    assert response.receipt["action_attribution_check"]["verdict"] == "blocked"
    assert audit_store.records[0].details["action_attribution_verdict"] == "blocked"
    assert attribution_store.checks[0].metrics["confirmation_required"] is True
    assert attribution_store.checks[0].metrics["reason_codes"] == [
        "confirmation-required"
    ]
    assert "skill-123" not in str(
        response.receipt["action_audit"]["request_payload_redacted"]["confirmation_hash"]
    )
    assert observatory_admin.actions[0].linked_audit_id == audit_store.records[0].audit_id
    assert audit_store.records[0].details["confirmation_required"] is True


def test_observatory_action_gateway_summary_exposes_policy_counts_without_raw_content(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("AUTOSKILL_WEB_ADMIN_RAW_CONTENT_ENABLED", "true")
    get_settings.cache_clear()
    audit_store = MemoryAuditStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=audit_store, observatory_admin_store=observatory_admin)
    routes = _routes(app)

    async def run():
        await routes[("/admin/api/v1/actions", "POST")].endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="verify_audit_chain",
                idempotency_key="obs-summary-accepted",
                reason="operator requested audit proof",
            ),
        )
        rejected = await routes[("/admin/api/v1/actions", "POST")].endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="rollback_skill",
                idempotency_key="obs-summary-confirmation",
                target={"id": "skill-123"},
                reason="operator requested rollback",
                confirmation="wrong rollback confirmation text",
                dry_run=False,
            ),
        )
        await routes[("/admin/api/v1/actions", "POST")].endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="reveal_raw_content",
                idempotency_key="obs-summary-role",
                target={"object_type": "raw_event", "id": "event-123"},
                reason="operator requested reveal",
                confirmation="confirm",
                dry_run=False,
            ),
            x_skillkernel_roles="operator",
        )
        summary = await routes[("/admin/api/v1/actions/summary", "GET")].endpoint(
            workspace_id="dev-01"
        )
        return rejected, summary

    try:
        rejected, summary = asyncio.run(run())
    finally:
        get_settings.cache_clear()

    detail = summary.object
    assert detail["schema_version"] == (
        "skillkernel.observatory.admin-action-summary.v1"
    )
    assert detail["object_type"] == "admin_action_gateway_summary"
    assert detail["counts"]["by_result"] == {"rejected": 2, "accepted": 1}
    assert detail["counts"]["by_action_kind"]["rollback_skill"]["rejected"] == 1
    assert detail["counts"]["linked_audit_records"] == 3
    assert detail["counts"]["action_attribution_checks"] == 3
    assert detail["counts"]["blocked_action_attribution_checks"] == 2
    assert detail["counts"]["raw_content_reveal"]["rejected"] == 1
    assert detail["policy"]["confirmation_failures"] == 1
    assert detail["policy"]["role_failures"] == 1
    assert detail["policy"]["blocked_by_reason"] == {
        "admin-role-required": 1,
        "confirmation-required": 1,
    }
    assert detail["policy"]["idempotency_replays_return_existing_receipts"] is True
    assert len(detail["high_impact_history"]) == 2
    assert detail["high_impact_history"][0]["action_kind"] == "reveal_raw_content"
    assert detail["high_impact_history"][1]["action_kind"] == "rollback_skill"
    assert detail["high_impact_history"][1]["target_id"] == "skill-123"
    assert detail["high_impact_history"][1]["confirmation_hash_present"] is True
    assert "wrong rollback confirmation text" not in str(
        detail["high_impact_history"][1]
    )
    assert detail["content_policy"]["raw_available"] is False
    assert detail["data_quality"]["auth_failures_before_action_parsing_not_counted"] is True
    assert rejected.receipt["action_audit"]["request_payload_redacted"][
        "reason_codes"
    ] == ["confirmation-required"]


def test_observatory_action_idempotency_replays_existing_audit_without_side_effects() -> None:
    audit_store = MemoryAuditStore()
    observatory_admin = NullObservatoryAdminStore()
    app = create_app(audit_store=audit_store, observatory_admin_store=observatory_admin)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        first = await route.endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="verify_audit_chain",
                idempotency_key="obs-idempotent-1",
                reason="operator requested audit proof",
                metadata={"ticket": "INC-1"},
            ),
        )
        replay = await route.endpoint(
            http_request=None,
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="verify_audit_chain",
                idempotency_key="obs-idempotent-1",
                reason="operator retried with different local note",
                metadata={"ticket": "INC-2"},
            ),
        )
        return first, replay

    first, replay = asyncio.run(run())

    assert first.receipt["idempotency"] == {"replay": False, "collision": False}
    assert replay.receipt["accepted"] is True
    assert replay.receipt["idempotency"] == {"replay": True, "collision": True}
    assert replay.receipt["policy"]["reason_codes"] == [
        "idempotency-replay",
        "idempotency-collision",
    ]
    assert replay.receipt["action_audit"]["action_id"] == (
        first.receipt["action_audit"]["action_id"]
    )
    assert replay.receipt["action_audit"]["request_payload_redacted"][
        "request_fingerprint"
    ].startswith("sha256:")
    assert replay.receipt["live_event"] is None
    assert len(observatory_admin.actions) == 1
    assert len(observatory_admin.live_events) == 1
    assert len(audit_store.records) == 1


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
