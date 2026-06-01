import asyncio
from uuid import uuid4

from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.broker import ContextHintRequest, build_context_hint


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

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "query": query,
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


def test_context_broker_renders_scanned_skill_candidates() -> None:
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

    async def run():
        return await build_context_hint(
            store,
            ContextHintRequest(
                workspace_id="dev-01",
                session_id="session-1",
                turn_id="turn-1",
                user_intent="repair pdf table extraction",
                max_tokens=120,
            ),
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
    assert store.graph_calls[0]["limit"] == 12


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
