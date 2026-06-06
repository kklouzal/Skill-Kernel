from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import HistoricalBootstrapConsolidateRequest, create_app
from autoskill.db.evidence import EvidenceRecord
from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.historical_bootstrap import consolidate_historical_bootstrap
from autoskill.services.worker import WorkerStores, run_worker_once
from autoskill.tests.test_embedding_generation import MemoryPendingEmbeddingStore
from autoskill.tests.test_jobs_api import MemoryJobStore
from autoskill.tests.test_worker import MemorySchedulerWorkerStore


class MemoryHistoricalBootstrapEvidenceStore:
    def __init__(self, records: list[EvidenceRecord]) -> None:
        self.records = records

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        return self.records[:limit]

    async def derive_from_raw_events(self, **_kwargs):
        raise NotImplementedError


class MemoryHistoricalBootstrapRetrievalStore:
    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        self.candidates = candidates
        self.queries: list[str] = []

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        trace_id=None,
        span_id=None,
        parent_span_id=None,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
        record_decision: bool = True,
    ) -> RetrievalResult:
        self.queries.append(query)
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found" if self.candidates else "no_candidates",
            candidates=self.candidates,
        )

    async def expand_skill_graph(self, **_kwargs):
        return []

    async def record_context_hint(self, **_kwargs) -> None:
        return None


def test_historical_bootstrap_consolidates_only_historical_evidence() -> None:
    live = _event_evidence("message_received", "live-only workflow")
    historical_one = _historical_evidence("taskflow", "repair repeated task ledger")
    historical_two = _historical_evidence("taskflow", "repair repeated task ledger")
    evidence = MemoryHistoricalBootstrapEvidenceStore(
        [live, historical_one, historical_two]
    )
    retrieval = MemoryHistoricalBootstrapRetrievalStore([])

    async def run():
        return await consolidate_historical_bootstrap(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )

    result = asyncio.run(run())

    assert result.scanned == 3
    assert result.historical_scanned == 2
    assert result.proposals.proposed == 1
    proposal = result.proposals.proposals[0].to_json()
    assert proposal["evidence_ids"] == [
        str(historical_one.evidence_id),
        str(historical_two.evidence_id),
    ]
    assert "write files" in " ".join(proposal["skillir"]["never"]).lower()
    assert result.to_json()["activation_allowed"] is False


def test_historical_bootstrap_ignores_legacy_string_payload_evidence() -> None:
    historical_one = _historical_evidence("taskflow", "repair repeated task ledger")
    historical_two = _historical_evidence("taskflow", "repair repeated task ledger")
    legacy_payload = EvidenceRecord(
        evidence_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        source_event_id=None,
        evidence_hash=str(uuid4()),
        kind="historical_chunk_observation",
        maturity="observed",
        trust="historical_import",
        taint=["historical", "raw_historical"],
        summary="Legacy historical payload shape.",
        payload="legacy-payload",  # type: ignore[arg-type]
        created_at=datetime.now(UTC),
    )
    evidence = MemoryHistoricalBootstrapEvidenceStore(
        [legacy_payload, historical_one, historical_two]
    )
    retrieval = MemoryHistoricalBootstrapRetrievalStore([])

    async def run():
        return await consolidate_historical_bootstrap(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )

    result = asyncio.run(run())

    assert result.scanned == 3
    assert result.historical_scanned == 2
    assert result.proposals.proposed == 1


def test_historical_bootstrap_suppresses_candidate_when_active_match_exists() -> None:
    skill_id = uuid4()
    evidence = MemoryHistoricalBootstrapEvidenceStore(
        [
            _historical_evidence("taskflow", "repair repeated task ledger"),
            _historical_evidence("taskflow", "repair repeated task ledger"),
        ]
    )
    retrieval = MemoryHistoricalBootstrapRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="Repeated historical chunk observation taskflow repair workflow.",
                rank=0.9,
                metadata={
                    "lifecycle_state": "active",
                    "slug": "autoskill-historical-chunk-observation",
                },
            )
        ]
    )

    result = asyncio.run(
        consolidate_historical_bootstrap(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )
    )

    assert result.proposals.proposed == 0
    assert result.proposals.skipped == 1
    assert result.opportunities.candidates[0].recommendation == "reuse_active"


def test_historical_bootstrap_api_route_returns_propose_only_payload() -> None:
    evidence = MemoryHistoricalBootstrapEvidenceStore(
        [
            _historical_evidence("transcript", "repeat redacted correction"),
            _historical_evidence("transcript", "repeat redacted correction"),
        ]
    )
    app = create_app(
        evidence_store=evidence,
        retrieval_store=MemoryHistoricalBootstrapRetrievalStore([]),
    )
    route = next(
        route for route in app.routes if route.path == "/v1/historical-bootstrap/consolidate"
    )

    response = asyncio.run(
        route.endpoint(
            request=HistoricalBootstrapConsolidateRequest(
                workspace_id="dev-01",
                min_support=2,
            )
        )
    )

    assert response.activation_allowed is False
    assert response.historical_scanned == 2
    assert response.proposals["proposed"] == 1


def test_worker_dispatches_historical_bootstrap_consolidation_job() -> None:
    jobs = MemoryJobStore()
    evidence = MemoryHistoricalBootstrapEvidenceStore(
        [
            _historical_evidence("session", "repeat redacted workflow"),
            _historical_evidence("session", "repeat redacted workflow"),
        ]
    )

    async def run():
        await jobs.enqueue_job(
            workspace_key="dev-01",
            job_kind="historical_bootstrap.consolidate",
            idempotency_key="historical-bootstrap:one",
            payload={"workspace_id": "dev-01", "min_support": 2},
        )
        stores = WorkerStores(
            jobs=jobs,
            scheduler=MemorySchedulerWorkerStore(),
            evidence=evidence,
            embeddings=MemoryPendingEmbeddingStore(),
            retrieval=MemoryHistoricalBootstrapRetrievalStore([]),
        )
        return await run_worker_once(stores, worker_id="worker-1", pool="maintenance")

    result = asyncio.run(run())

    assert result.status == "succeeded"
    assert result.output["activation_allowed"] is False
    assert result.output["historical_scanned"] == 2
    assert result.output["proposals"]["proposed"] == 1


def _event_evidence(event_type: str, content: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        source_event_id=uuid4(),
        evidence_hash=str(uuid4()),
        kind="event_observation",
        maturity="observed",
        trust="system_owned",
        taint=[],
        summary=f"Observed redacted {event_type} event.",
        payload={
            "source_event": {"event_type": event_type},
            "redacted_payload": {"content": content},
        },
        created_at=datetime.now(UTC),
    )


def _historical_evidence(source_kind: str, content: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        source_event_id=None,
        evidence_hash=str(uuid4()),
        kind="historical_chunk_observation",
        maturity="observed",
        trust="historical_import",
        taint=["historical", "raw_historical"],
        summary=f"Observed historical {source_kind} chunk.",
        payload={
            "source_event": {
                "event_type": "historical_chunk_observation",
                "source": source_kind,
            },
            "redacted_payload": {"content": content},
        },
        created_at=datetime.now(UTC),
    )
