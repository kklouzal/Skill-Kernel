import asyncio
from types import SimpleNamespace
from uuid import uuid4

from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.broker import ContextHintCache, ContextHintRequest, build_context_hint


class MemoryBrokerRetrievalStore:
    def __init__(
        self,
        candidates: list[RetrievalCandidate],
        graph_candidates: list[RetrievalCandidate] | None = None,
    ) -> None:
        self.candidates = candidates
        self.graph_candidates = graph_candidates or []
        self.calls: list[dict[str, object]] = []
        self.graph_calls: list[dict[str, object]] = []
        self.records: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "query": query,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "limit": limit,
            }
        )
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found" if self.candidates else "no_candidates",
            candidates=self.candidates,
        )

    async def expand_skill_graph(
        self,
        *,
        workspace_key: str,
        skill_ids: list,
        edge_kinds: list[str] | None = None,
        limit: int = 25,
    ) -> list[RetrievalCandidate]:
        self.graph_calls.append(
            {
                "workspace_key": workspace_key,
                "skill_ids": skill_ids,
                "edge_kinds": edge_kinds,
                "limit": limit,
            }
        )
        return self.graph_candidates[:limit]

    async def record_context_hint(
        self,
        *,
        retrieval_log_id,
        rendered_skill_ids: list,
        decision: str,
        suppressed: list[dict[str, object]],
        reason_codes: list[str],
    ) -> None:
        self.records.append(
            {
                "retrieval_log_id": retrieval_log_id,
                "rendered_skill_ids": rendered_skill_ids,
                "decision": decision,
                "suppressed": suppressed,
                "reason_codes": reason_codes,
            }
        )


class MemoryContextGovernanceStore:
    def __init__(self) -> None:
        self.artifacts: list[dict[str, object]] = []
        self.ledgers: list[dict[str, object]] = []

    async def record_artifact(self, **kwargs):
        artifact_id = uuid4()
        self.artifacts.append(kwargs | {"context_artifact_id": artifact_id})
        return SimpleNamespace(
            context_artifact_id=artifact_id,
            token_count=max(1, (len(str(kwargs["text"])) + 3) // 4),
        )

    async def record_token_ledger(self, **kwargs):
        self.ledgers.append(kwargs)
        return SimpleNamespace(context_token_ledger_id=uuid4())


def test_context_broker_renders_scanned_skill_candidates() -> None:
    skill_id = uuid4()
    trace_id = uuid4()
    span_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="Duplicate body for the same skill should be suppressed.",
                rank=0.8,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    context = MemoryContextGovernanceStore()

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                trace_id=trace_id,
                span_id=span_id,
                session_id="session-1",
                turn_id="turn-1",
                user_intent="repair pdf table extraction",
                max_tokens=120,
            ),
            context_governance=context,
        )

    response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert response.skill_ids == [str(skill_id)]
    assert "AutoSkill broker hint" in response.hint
    assert "PDF tables" in response.hint
    assert "pdf-table-repair" in response.hint
    assert response.suppressed[0]["reason"] == "duplicate-skill"
    assert "exact-rerank" in response.reason_codes
    assert store.calls[0]["limit"] == 8
    assert store.calls[0]["trace_id"] == trace_id
    assert store.calls[0]["span_id"] == span_id
    assert store.graph_calls[0]["limit"] == 12
    assert store.records[0]["decision"] == "skill_hint"
    assert store.records[0]["rendered_skill_ids"] == [skill_id]
    assert context.artifacts[0]["artifact_kind"] == "broker_hint"
    assert context.artifacts[0]["source_object_type"] == "retrieval_log"
    assert context.artifacts[0]["max_tokens"] == 120
    assert context.ledgers[0]["visibility_state"] == "skill_visible"
    assert context.ledgers[0]["context_artifact_id"] == context.artifacts[0]["context_artifact_id"]


def test_context_broker_records_no_skill_token_ledger() -> None:
    store = MemoryBrokerRetrievalStore([])
    context = MemoryContextGovernanceStore()

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                session_id="session-1",
                turn_id="turn-1",
                user_intent="unknown operation",
            ),
            context_governance=context,
        )

    response = asyncio.run(run())

    assert response.decision == "no_skill"
    assert context.artifacts == []
    assert context.ledgers[0]["visibility_state"] == "no_skill"
    assert context.ledgers[0]["token_count"] == 0
    assert context.ledgers[0]["session_id"] == "session-1"


def test_context_broker_defers_evidence_only_matches() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="evidence_item",
                object_id=uuid4(),
                skill_id=None,
                summary="Observed raw evidence should not be injected into prompt context.",
                rank=0.6,
                metadata={"maturity": "observed"},
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="raw evidence"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.hint == ""
    assert response.cache_status == "evidence-only"
    assert response.suppressed[0]["reason"] == "not-runtime-skill"


def test_context_broker_blocks_unscanned_body_documents() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=uuid4(),
                summary="This candidate lacks a passing scan.",
                rank=0.6,
                metadata={"secret_scan_status": "pending", "lifecycle_state": "active"},
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="candidate"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.skill_ids == []
    assert response.suppressed[0]["reason"] == "secret-scan-not-passed"


def test_context_broker_expands_prerequisite_graph_candidates() -> None:
    primary_skill_id = uuid4()
    prereq_skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=primary_skill_id,
                summary="WHEN repairing PDF tables, run the boundary repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ],
        graph_candidates=[
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=prereq_skill_id,
                summary="Before PDF table repair, inspect screenshots for missing visual rules.",
                rank=0.0,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-screenshot-inspection",
                    "graph_edge_kind": "prerequisite",
                },
            )
        ],
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                user_intent="repair pdf table extraction",
            ),
        )

    response = asyncio.run(run())

    assert response.decision == "skill_hint"
    assert str(primary_skill_id) in response.skill_ids
    assert str(prereq_skill_id) in response.skill_ids
    assert "[prerequisite]" in response.hint
    assert "graph-expanded" in response.reason_codes


def test_context_broker_suppresses_archived_matches_for_promotion() -> None:
    archived_skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=archived_skill_id,
                summary="Archived workflow still matches the request.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "archived",
                    "slug": "old-workflow",
                },
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="old workflow"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.archive_promotion_skill_ids == [str(archived_skill_id)]
    assert response.suppressed[0]["reason"] == "archived-promotion-candidate"


def test_context_broker_suppresses_external_skill_collisions() -> None:
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="external_skill",
                object_id=uuid4(),
                skill_id=None,
                summary="External PDF table cleanup workflow.",
                rank=0.9,
                metadata={
                    "ownership": "external",
                    "source": "workspace-skill-root",
                    "status": "visible",
                    "slug": "pdf-table-cleanup",
                },
            )
        ]
    )

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(workspace_id="dev-01", user_intent="pdf table cleanup"),
        )

    response = asyncio.run(run())

    assert response.decision == "defer_skill"
    assert response.skill_ids == []
    assert response.suppressed[0]["reason"] == "external-skill-collision"
    assert "external-skill-collision" in response.reason_codes


def test_context_broker_cache_avoids_duplicate_retrieval() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    cache = ContextHintCache(ttl_seconds=60)
    request = ContextHintRequest(
        workspace_id="dev-01",
        user_intent="repair pdf table extraction",
    )

    async def run():
        first = await build_context_hint(store, request, cache=cache)
        second = await build_context_hint(store, request, cache=cache)
        return first, second

    first, second = asyncio.run(run())

    assert first.decision == "skill_hint"
    assert second.decision == "skill_hint"
    assert second.cache_status == "cache-hit"
    assert len(store.calls) == 1
    assert len(store.records) == 1


def test_context_broker_cache_invalidates_by_workspace_and_skill() -> None:
    skill_id = uuid4()
    store = MemoryBrokerRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary="WHEN PDF tables are malformed, use the deterministic repair workflow.",
                rank=0.9,
                metadata={
                    "secret_scan_status": "passed",
                    "lifecycle_state": "active",
                    "slug": "pdf-table-repair",
                },
            ),
        ]
    )
    cache = ContextHintCache(ttl_seconds=60)
    request = ContextHintRequest(
        workspace_id="dev-01",
        user_intent="repair pdf table extraction",
    )

    async def run():
        await build_context_hint(store, request, cache=cache)
        removed = cache.invalidate(workspace_id="dev-01", skill_ids=[str(skill_id)])
        await build_context_hint(store, request, cache=cache)
        return removed

    removed = asyncio.run(run())

    assert removed == 1
    assert len(store.calls) == 2
