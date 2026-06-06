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
            candidates=self.candidates[:limit],
        )

    async def expand_skill_graph(self, **_kwargs):
        return []

    async def record_context_hint(self, **_kwargs) -> None:
        return None


class QuerySensitiveSkillMatchRetrievalStore:
    def __init__(
        self,
        candidates_by_query: dict[str, list[RetrievalCandidate]],
    ) -> None:
        self.candidates_by_query = candidates_by_query
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
        candidates = self.candidates_by_query.get(query, [])
        return RetrievalResult(
            retrieval_log_id=uuid4(),
            decision="candidates_found" if candidates else "no_candidates",
            candidates=candidates[:limit],
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


def test_skill_match_retries_runtime_text_when_broad_paraphrase_is_too_strict() -> None:
    active_skill_id = uuid4()
    store = QuerySensitiveSkillMatchRetrievalStore(
        {
            "repair diagrams unreadable labels accessibility annotations": [
                RetrievalCandidate(
                    object_type="body_index_document",
                    object_id=uuid4(),
                    skill_id=active_skill_id,
                    summary=(
                        "WHEN diagrams have unreadable labels, repair accessibility "
                        "annotations."
                    ),
                    rank=0.5,
                    metadata={
                        "lifecycle_state": "active",
                        "slug": "diagram-accessibility-9b03d262",
                    },
                )
            ]
        }
    )

    async def run():
        return await match_existing_skills(
            store,
            SkillMatchRequest(
                workspace_key="dev-01",
                candidate_slug="diagram-accessibility-probe",
                candidate_description=(
                    "Fix unreadable diagram labels and add accessibility annotations."
                ),
                candidate_runtime_text=(
                    "Repair diagrams with unreadable labels and add accessibility "
                    "annotations."
                ),
            ),
        )

    result = asyncio.run(run())

    assert result.decision == "reuse_active"
    assert result.active_matches[0].skill_id == str(active_skill_id)
    assert store.queries == [
        "unreadable diagram labels accessibility annotations repair",
        "repair diagrams unreadable labels accessibility annotations",
        "unreadable diagram labels accessibility annotations",
        "diagram accessibility probe",
    ]


def test_skill_match_keeps_stronger_runtime_match_after_weak_broad_hit() -> None:
    weak_skill_id = uuid4()
    active_skill_id = uuid4()
    store = QuerySensitiveSkillMatchRetrievalStore(
        {
            "unreadable diagram labels accessibility annotations repair": [
                RetrievalCandidate(
                    object_type="body_index_document",
                    object_id=uuid4(),
                    skill_id=weak_skill_id,
                    summary="Diagram export metadata normalization.",
                    rank=0.05,
                    metadata={
                        "lifecycle_state": "active",
                        "slug": "diagram-export-metadata",
                    },
                )
            ],
            "repair diagrams unreadable labels accessibility annotations": [
                RetrievalCandidate(
                    object_type="body_index_document",
                    object_id=uuid4(),
                    skill_id=active_skill_id,
                    summary=(
                        "WHEN diagrams have unreadable labels, repair accessibility "
                        "annotations."
                    ),
                    rank=0.5,
                    metadata={
                        "lifecycle_state": "active",
                        "slug": "diagram-accessibility-9b03d262",
                    },
                )
            ],
        }
    )

    async def run():
        return await match_existing_skills(
            store,
            SkillMatchRequest(
                workspace_key="dev-01",
                candidate_slug="diagram-accessibility-probe",
                candidate_description=(
                    "Fix unreadable diagram labels and add accessibility annotations."
                ),
                candidate_runtime_text=(
                    "Repair diagrams with unreadable labels and add accessibility "
                    "annotations."
                ),
            ),
        )

    result = asyncio.run(run())

    assert result.decision == "reuse_active"
    assert result.active_matches[0].skill_id == str(active_skill_id)


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


def test_skill_match_surfaces_external_collision_without_reuse() -> None:
    external_skill_id = uuid4()
    store = MemorySkillMatchRetrievalStore(
        [
            RetrievalCandidate(
                object_type="external_skill",
                object_id=external_skill_id,
                skill_id=None,
                summary="PDF table cleanup: external workflow for repairing malformed cells.",
                rank=0.7,
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
        return await match_existing_skills(
            store,
            SkillMatchRequest(
                workspace_key="dev-01",
                candidate_slug="pdf-table-repair",
                candidate_description="Repair malformed PDF table extraction boundaries.",
            ),
        )

    result = asyncio.run(run())

    assert result.decision == "external_collision_review"
    assert result.active_matches == []
    assert result.archived_matches == []
    assert result.external_matches[0].external_skill_id == str(external_skill_id)
    assert result.external_matches[0].source == "workspace-skill-root"
    assert result.external_matches[0].collision_risk == "high"
    assert result.external_matches[0].collision_score >= 0.75
    assert result.external_matches[0].recommendation == (
        "operator_review_import_or_reuse_external_skill"
    )
    assert "high_similarity" in result.external_matches[0].reason_codes
    assert "slug_family_overlap" in result.external_matches[0].reason_codes


def test_skill_match_flags_changed_external_skill_for_review() -> None:
    store = MemorySkillMatchRetrievalStore(
        [
            RetrievalCandidate(
                object_type="external_skill",
                object_id=uuid4(),
                skill_id=None,
                summary="PDF table cleanup: external workflow for repairing malformed cells.",
                rank=0.4,
                metadata={
                    "ownership": "external",
                    "source": "workspace-skill-root",
                    "status": "changed",
                    "slug": "pdf-table-cleanup",
                },
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

    assert result.decision == "external_collision_review"
    assert result.external_matches[0].status == "changed"
    assert result.external_matches[0].recommendation == (
        "review_changed_external_skill_before_candidate_creation"
    )
    assert "external_skill_changed" in result.external_matches[0].reason_codes


def test_skill_match_blocks_quarantined_external_skill_import_recommendation() -> None:
    store = MemorySkillMatchRetrievalStore(
        [
            RetrievalCandidate(
                object_type="external_skill",
                object_id=uuid4(),
                skill_id=None,
                summary="PDF table cleanup: external workflow for repairing malformed cells.",
                rank=0.8,
                metadata={
                    "ownership": "external",
                    "source": "workspace-skill-root",
                    "status": "quarantined",
                    "slug": "pdf-table-cleanup",
                    "risk_summary": {"scanner_status": "blocked"},
                },
            )
        ]
    )

    async def run():
        return await match_existing_skills(
            store,
            SkillMatchRequest(
                workspace_key="dev-01",
                candidate_slug="pdf-table-cleanup",
                candidate_description="Repair malformed PDF table extraction boundaries.",
            ),
        )

    result = asyncio.run(run())

    assert result.decision == "external_collision_review"
    assert result.external_matches[0].collision_risk == "blocked"
    assert result.external_matches[0].recommendation == (
        "do_not_import_external_skill_until_unquarantined"
    )
    assert "external_skill_scanner_blocked" in result.external_matches[0].reason_codes


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
    assert response.external_matches == []
    assert store.queries[0] == "brand new"
