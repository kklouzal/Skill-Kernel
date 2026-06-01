import asyncio
from uuid import uuid4

from autoskill.api.app import SkillMatchApiRequest, create_app
from autoskill.db.retrieval import RetrievalCandidate, RetrievalResult
from autoskill.services.matching import SkillMatchRequest, match_existing_skills


class MemorySkillMatchRetrievalStore:
    def __init__(self, candidates: list[RetrievalCandidate]) -> None:
        self.candidates = candidates
        self.queries: list[str] = []

    async def lexical_query(
        self,
        *,
        workspace_key: str,
        query: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        limit: int = 10,
    ) -> RetrievalResult:
        self.queries.append(query)
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found" if self.candidates else "no_candidates",
            candidates=self.candidates[:limit],
        )

    async def expand_skill_graph(self, **_kwargs):
        return []

    async def record_context_hint(self, **_kwargs) -> None:
        return None


def test_skill_match_prefers_existing_active_skill() -> None:
    active_skill_id = uuid4()
    store = MemorySkillMatchRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=active_skill_id,
                summary="WHEN PDF table extraction is malformed, repair cell boundaries.",
                rank=0.6,
                metadata={"lifecycle_state": "active", "slug": "pdf-table-repair"},
            )
        ]
    )

    async def run():
        return await match_existing_skills(
            store,
            SkillMatchRequest(
                workspace_key="dev-01",
                candidate_slug="pdf-table-repair",
                candidate_description="Repair malformed PDF table extraction boundaries.",
            ),
        )

    result = asyncio.run(run())

    assert result.decision == "reuse_active"
    assert result.active_matches[0].skill_id == str(active_skill_id)
    assert result.archived_matches == []


def test_skill_match_surfaces_archived_promotion_candidate() -> None:
    archived_skill_id = uuid4()
    store = MemorySkillMatchRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=archived_skill_id,
                summary="WHEN PDF table extraction is malformed, repair cell boundaries.",
                rank=0.6,
                metadata={"lifecycle_state": "archived", "slug": "old-pdf-table-repair"},
            )
        ]
    )

    async def run():
        return await match_existing_skills(
            store,
            SkillMatchRequest(
                workspace_key="dev-01",
                candidate_slug="pdf-table-repair",
                candidate_description="Repair malformed PDF table extraction boundaries.",
            ),
        )

    result = asyncio.run(run())

    assert result.decision == "consider_archive_promotion"
    assert result.active_matches == []
    assert result.archived_matches[0].skill_id == str(archived_skill_id)


def test_skill_match_api_uses_retrieval_store() -> None:
    store = MemorySkillMatchRetrievalStore([])
    app = create_app(retrieval_store=store)
    route = next(route for route in app.routes if route.path == "/v1/skills/match")

    async def run():
        return await route.endpoint(
            request=SkillMatchApiRequest(
                workspace_id="dev-01",
                candidate_slug="new-skill",
                candidate_description="A brand new workflow.",
            )
        )

    response = asyncio.run(run())

    assert response.decision == "create_candidate"
    assert response.active_matches == []
    assert store.queries[0] == "brand new"
