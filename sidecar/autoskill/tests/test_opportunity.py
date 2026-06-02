import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import OpportunityMineRequest, create_app
from autoskill.db.evidence import EvidenceRecord
from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.opportunity import mine_opportunities


class MemoryOpportunityEvidenceStore:
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


class MemoryOpportunityRetrievalStore:
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


def evidence_record(event_type: str, content: str) -> EvidenceRecord:
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


def recurring_evidence_record(signature: str, support_count: int) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        source_event_id=None,
        evidence_hash=str(uuid4()),
        kind="recurring_evidence_cluster",
        maturity="recurring",
        trust="tool_output",
        taint=["tool"],
        summary=f"Recurring redacted evidence cluster {signature!r}.",
        payload={
            "schema": "autoskill.recurring_evidence_cluster.v1",
            "signature": signature,
            "support_count": support_count,
            "support_evidence_ids": [str(uuid4()) for _ in range(support_count)],
            "redacted_payload": {"content": signature.replace(":", " ")},
        },
        created_at=datetime.now(UTC),
    )


def test_opportunity_miner_calls_duplicate_matching_before_recommending_candidate() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore([])

    async def run():
        return await mine_opportunities(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )

    result = asyncio.run(run())

    assert result.scanned == 2
    assert len(result.candidates) == 1
    assert result.candidates[0].recommendation == "propose_candidate"
    assert result.candidates[0].support_count == 2
    assert retrieval.queries


def test_opportunity_miner_uses_recurring_cluster_support() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [recurring_evidence_record("tool-call-end:pytest:missing:package", 3)]
    )
    retrieval = MemoryOpportunityRetrievalStore([])

    async def run():
        return await mine_opportunities(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )

    result = asyncio.run(run())

    assert result.scanned == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].key == "tool-call-end-pytest-missing-package"
    assert result.candidates[0].support_count == 3
    assert result.candidates[0].evidence_ids == [str(evidence.records[0].evidence_id)]


def test_opportunity_miner_recommends_reuse_for_active_match() -> None:
    skill_id = uuid4()
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="Repeated message received workflow evidence observed.",
                rank=0.8,
                metadata={"lifecycle_state": "active", "slug": "autoskill-message-received"},
            )
        ]
    )

    async def run():
        return await mine_opportunities(
            evidence,
            retrieval,
            workspace_key="dev-01",
            min_support=2,
        )

    result = asyncio.run(run())

    assert result.candidates[0].recommendation == "reuse_active"
    assert result.candidates[0].match.active_matches[0].skill_id == str(skill_id)


def test_opportunity_mine_api_uses_stores() -> None:
    evidence = MemoryOpportunityEvidenceStore(
        [
            evidence_record("message_received", "repair pdf table extraction"),
            evidence_record("message_received", "repair pdf table extraction"),
        ]
    )
    retrieval = MemoryOpportunityRetrievalStore([])
    app = create_app(evidence_store=evidence, retrieval_store=retrieval)
    route = next(route for route in app.routes if route.path == "/v1/opportunities/mine")

    async def run():
        return await route.endpoint(
            request=OpportunityMineRequest(workspace_id="dev-01", min_support=2)
        )

    response = asyncio.run(run())

    assert response.scanned == 2
    assert response.candidates[0]["recommendation"] == "propose_candidate"
