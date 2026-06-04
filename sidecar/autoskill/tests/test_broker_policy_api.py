import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from autoskill.api.app import (
    BrokerPolicyActivateRequest,
    BrokerPolicyCanaryRequest,
    BrokerPolicyReplayRequest,
    BrokerPolicyUpsertRequest,
    BrokerPolicyUsageProposalRequest,
    BrokerReplayEpisodeRecordRequest,
    BrokerReplayEpisodeSynthesizeRequest,
    create_app,
)
from autoskill.db.broker_policy import NullBrokerPolicyStore
from autoskill.db.retrieval import RetrievalCandidate, RetrievalLog
from autoskill.db.usage import UsageTopologyRecommendation
from autoskill.services.broker import BrokerReplayEpisode
from autoskill.tests.test_broker import MemoryBrokerRetrievalStore


class MemoryUsageRecommendationStore:
    def __init__(self, recommendations: list[UsageTopologyRecommendation]) -> None:
        self.recommendations = recommendations
        self.calls: list[dict[str, object]] = []

    async def recommend_topology_operations(
        self,
        *,
        workspace_key: str,
        limit: int = 25,
        min_support: int = 3,
        min_success_count: int = 1,
        max_failure_ratio: float = 0.25,
        min_sequence_count: int = 1,
    ) -> list[UsageTopologyRecommendation]:
        self.calls.append(
            {
                "workspace_key": workspace_key,
                "limit": limit,
                "min_support": min_support,
                "min_success_count": min_success_count,
                "max_failure_ratio": max_failure_ratio,
                "min_sequence_count": min_sequence_count,
            }
        )
        return self.recommendations[:limit]


class TelemetryReplayRetrievalStore(MemoryBrokerRetrievalStore):
    def __init__(
        self,
        candidates: list[RetrievalCandidate],
        logs: list[RetrievalLog],
    ) -> None:
        super().__init__(candidates)
        self.logs = logs
        self.recent_logs = logs
        self.list_calls: list[dict[str, object]] = []

    async def list_recent_logs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[RetrievalLog]:
        self.list_calls.append({"workspace_key": workspace_key, "limit": limit})
        return self.recent_logs[:limit]

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


class FakeReplayIntentLLM:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[object] = []

    async def complete(self, completion):
        self.calls.append(completion)
        return type("LLMResponse", (), {"text": self.text})()


class FailingReplayIntentLLM:
    async def complete(self, completion):
        raise ValueError("unknown url type")


def test_broker_policy_api_activates_policy_and_replay_uses_it() -> None:
    policy_store = NullBrokerPolicyStore()
    skill_id = uuid4()
    retrieval = MemoryBrokerRetrievalStore(
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
            )
        ]
    )
    app = create_app(
        broker_policy_store=policy_store,
        retrieval_store=retrieval,
    )
    upsert = next(route for route in app.routes if route.path == "/v1/broker/policies")
    activate = next(
        route for route in app.routes if route.path == "/v1/broker/policies/activate"
    )
    replay = next(route for route in app.routes if route.path == "/v1/broker/policies/replay")

    async def run():
        created = await upsert.endpoint(
            request=BrokerPolicyUpsertRequest(
                workspace_id="dev-01",
                version="broker-policy-test.v1",
                policy={
                    "runtime_context_broker": {
                        "lexical_limit": 2,
                        "graph_limit": 0,
                        "max_rendered_skills": 1,
                    }
                },
            )
        )
        activated = await activate.endpoint(
            request=BrokerPolicyActivateRequest(
                workspace_id="dev-01",
                broker_policy_version_id=created.policy_version[
                    "broker_policy_version_id"
                ],
            )
        )
        replayed = await replay.endpoint(
            request=BrokerPolicyReplayRequest(
                workspace_id="dev-01",
                episodes=[
                    BrokerReplayEpisode(
                        episode_id="pdf-table",
                        user_intent="repair pdf table",
                        expected_decision="skill_hint",
                        expected_skill_ids=[str(skill_id)],
                    )
                ],
            )
        )
        return activated, replayed

    activated, replayed = asyncio.run(run())

    assert activated.policy_version["status"] == "active"
    assert replayed.replay.matched == 1
    assert replayed.replay.policy["version"] == "broker-policy-test.v1"
    assert retrieval.calls[0]["limit"] == 2


def test_broker_policy_synthesizes_replay_episodes_from_redacted_telemetry() -> None:
    policy_store = NullBrokerPolicyStore()
    skill_id = uuid4()
    retrieval_log_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
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
            )
        ],
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=uuid4(),
                span_id=uuid4(),
                parent_span_id=None,
                session_id="sess-redacted",
                turn_id="turn-redacted",
                broker_policy_version_id=None,
                decision="candidates_found",
                candidate_skill_ids=[skill_id],
                rendered_skill_ids=[skill_id],
                no_skill_control=False,
                metadata={
                    "evidence_fidelity": "raw_vault_linked",
                    "redacted_user_intent": "repair redacted pdf table",
                    "redacted_intent_source": "llm_synthesized_redacted_intent",
                    "deterministic_validation": {
                        "status": "passed",
                        "schema": "redacted-intent.v1",
                    },
                },
                created_at=datetime.now(UTC),
            )
        ],
    )
    app = create_app(
        broker_policy_store=policy_store,
        retrieval_store=retrieval,
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )
    replay = next(route for route in app.routes if route.path == "/v1/broker/policies/replay")

    async def run():
        synthesized = await synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(
                workspace_id="dev-01",
                tags=["operator-reviewed"],
            )
        )
        replayed = await replay.endpoint(
            request=BrokerPolicyReplayRequest(
                workspace_id="dev-01",
                include_stored_episodes=True,
                stored_episode_tags=["telemetry-derived"],
            )
        )
        return synthesized, replayed

    synthesized, replayed = asyncio.run(run())

    assert synthesized.skipped == []
    assert len(synthesized.episodes) == 1
    episode = synthesized.episodes[0]
    assert episode["episode_key"] == f"telemetry-{str(retrieval_log_id)[:12]}"
    assert episode["redacted_user_intent"] == "repair redacted pdf table"
    assert episode["expected_decision"] == "skill_hint"
    assert episode["expected_skill_ids"] == [str(skill_id)]
    assert set(episode["tags"]) >= {
        "production",
        "redacted",
        "telemetry-derived",
        "llm-synthesized",
        "operator-reviewed",
    }
    assert episode["metadata"]["operator_plan_required"] is False
    assert episode["metadata"]["raw_prompt_stored"] is False
    assert episode["source_retrieval_log_id"] == str(retrieval_log_id)
    assert replayed.replay.total == 1
    assert replayed.replay.matched == 1


def test_broker_policy_synthesizes_missing_intent_from_safe_retrieval_context() -> None:
    policy_store = NullBrokerPolicyStore()
    retrieval_log_id = uuid4()
    skill_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
        [
            RetrievalCandidate(
                object_type="body_index_document",
                object_id=uuid4(),
                skill_id=skill_id,
                summary=(
                    "WHEN tables in exported PDFs need deterministic repair, "
                    "use the table repair workflow."
                ),
                rank=0.8,
                metadata={"secret_scan_status": "passed", "lifecycle_state": "active"},
            )
        ],
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=uuid4(),
                span_id=uuid4(),
                parent_span_id=None,
                session_id="sess-redacted",
                turn_id=None,
                broker_policy_version_id=None,
                decision="candidates_found",
                candidate_skill_ids=[skill_id],
                rendered_skill_ids=[skill_id],
                no_skill_control=False,
                metadata={"candidate_count": 1},
                created_at=datetime.now(UTC),
            )
        ],
    )
    llm = FakeReplayIntentLLM(
        '{"redacted_user_intent":"repair redacted pdf table export"}'
    )
    app = create_app(
        broker_policy_store=policy_store,
        retrieval_store=retrieval,
        llm_client=llm,
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )

    response = asyncio.run(
        synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(workspace_id="dev-01")
        )
    )

    assert response.skipped == []
    assert len(response.episodes) == 1
    episode = response.episodes[0]
    assert episode["redacted_user_intent"] == "repair redacted pdf table export"
    assert episode["expected_decision"] == "skill_hint"
    assert episode["expected_skill_ids"] == [str(skill_id)]
    assert episode["metadata"]["evidence_fidelity"] == "redacted_derivative"
    assert episode["metadata"]["redacted_intent_source"] == (
        "llm_synthesized_from_content_safe_retrieval"
    )
    assert episode["metadata"]["deterministic_validation"]["status"] == "passed"
    assert episode["metadata"]["raw_prompt_stored"] is False
    assert llm.calls[0].purpose == "broker_replay.redacted_intent_synthesis"
    assert retrieval.replay_context_calls[0]["retrieval_log_id"] == retrieval_log_id


def test_broker_policy_synthesis_fails_closed_without_safe_context() -> None:
    retrieval_log_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
        [],
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                session_id=None,
                turn_id=None,
                broker_policy_version_id=None,
                decision="no_candidates",
                candidate_skill_ids=[],
                rendered_skill_ids=[],
                no_skill_control=True,
                metadata={},
                created_at=datetime.now(UTC),
            )
        ],
    )
    llm = FakeReplayIntentLLM('{"redacted_user_intent":"should not be called"}')
    app = create_app(
        broker_policy_store=NullBrokerPolicyStore(),
        retrieval_store=retrieval,
        llm_client=llm,
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )

    response = asyncio.run(
        synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(workspace_id="dev-01")
        )
    )

    assert response.episodes == []
    assert response.skipped == [
        {
            "retrieval_log_id": str(retrieval_log_id),
            "reason": "missing-content-safe-replay-context",
        }
    ]
    assert llm.calls == []


def test_broker_policy_synthesis_preserves_defer_for_non_runtime_candidates() -> None:
    retrieval_log_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
        [
            RetrievalCandidate(
                object_type="evidence_item",
                object_id=uuid4(),
                skill_id=None,
                summary="Repeated redacted evidence indicates skill vetting intent.",
                rank=0.7,
                metadata={"source": "evidence_item"},
            )
        ],
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                session_id=None,
                turn_id=None,
                broker_policy_version_id=None,
                decision="candidates_found",
                candidate_skill_ids=[],
                rendered_skill_ids=[],
                no_skill_control=True,
                metadata={"candidate_count": 1},
                created_at=datetime.now(UTC),
            )
        ],
    )
    llm = FakeReplayIntentLLM('{"redacted_user_intent":"check skill vetting"}')
    app = create_app(
        broker_policy_store=NullBrokerPolicyStore(),
        retrieval_store=retrieval,
        llm_client=llm,
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )

    response = asyncio.run(
        synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(workspace_id="dev-01")
        )
    )

    assert response.skipped == []
    assert response.episodes[0]["expected_decision"] == "defer_skill"
    assert response.episodes[0]["expected_skill_ids"] == []


def test_broker_policy_synthesis_repairs_stale_telemetry_episode_decision() -> None:
    policy_store = NullBrokerPolicyStore()
    retrieval_log_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
        [
            RetrievalCandidate(
                object_type="evidence_item",
                object_id=uuid4(),
                skill_id=None,
                summary="Repeated redacted evidence indicates skill vetting intent.",
                rank=0.7,
                metadata={"source": "evidence_item"},
            )
        ],
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                session_id=None,
                turn_id=None,
                broker_policy_version_id=None,
                decision="candidates_found",
                candidate_skill_ids=[],
                rendered_skill_ids=[],
                no_skill_control=True,
                metadata={},
                created_at=datetime.now(UTC),
            )
        ],
    )
    retrieval.recent_logs = []
    app = create_app(
        broker_policy_store=policy_store,
        retrieval_store=retrieval,
        llm_client=FakeReplayIntentLLM('{"redacted_user_intent":"unused"}'),
    )
    record = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes"
        and "POST" in getattr(route, "methods", set())
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )

    async def run():
        stale = await record.endpoint(
            request=BrokerReplayEpisodeRecordRequest(
                workspace_id="dev-01",
                episode_key=f"telemetry-{str(retrieval_log_id)[:12]}",
                redacted_user_intent="check skill vetting",
                expected_decision="no_skill",
                tags=["telemetry-derived"],
                metadata={
                    "source": "automatic_replay_synthesis",
                    "evidence_fidelity": "redacted_derivative",
                    "redacted_intent_source": (
                        "llm_synthesized_from_content_safe_retrieval"
                    ),
                    "deterministic_validation": {"status": "passed"},
                },
                source_retrieval_log_id=retrieval_log_id,
            )
        )
        repaired = await synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(
                workspace_id="dev-01",
                repair_existing_telemetry_episodes=True,
            )
        )
        return stale, repaired

    stale, repaired = asyncio.run(run())

    assert stale.episode["expected_decision"] == "no_skill"
    assert repaired.skipped == []
    assert len(repaired.episodes) == 1
    assert repaired.episodes[0]["expected_decision"] == "defer_skill"
    assert repaired.episodes[0]["redacted_user_intent"] == "check skill vetting"
    assert repaired.episodes[0]["metadata"]["candidate_count"] == 1


def test_broker_policy_synthesis_fails_closed_on_llm_provider_error() -> None:
    retrieval_log_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
        [
            RetrievalCandidate(
                object_type="evidence_item",
                object_id=uuid4(),
                skill_id=None,
                summary="Repeated redacted evidence indicates PDF table repair intent.",
                rank=0.7,
                metadata={"source": "evidence_item"},
            )
        ],
        [
            RetrievalLog(
                retrieval_log_id=retrieval_log_id,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                session_id=None,
                turn_id=None,
                broker_policy_version_id=None,
                decision="candidates_found",
                candidate_skill_ids=[],
                rendered_skill_ids=[],
                no_skill_control=True,
                metadata={"candidate_count": 1},
                created_at=datetime.now(UTC),
            )
        ],
    )
    app = create_app(
        broker_policy_store=NullBrokerPolicyStore(),
        retrieval_store=retrieval,
        llm_client=FailingReplayIntentLLM(),
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )

    response = asyncio.run(
        synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(workspace_id="dev-01")
        )
    )

    assert response.episodes == []
    assert response.skipped == [
        {
            "retrieval_log_id": str(retrieval_log_id),
            "reason": "llm-synthesis-failed:ValueError",
        }
    ]


def test_broker_policy_synthesis_skips_degraded_evidence_fidelity_telemetry() -> None:
    hash_only_log_id = uuid4()
    metadata_only_log_id = uuid4()
    retrieval = TelemetryReplayRetrievalStore(
        [],
        [
            RetrievalLog(
                retrieval_log_id=hash_only_log_id,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                session_id=None,
                turn_id=None,
                broker_policy_version_id=None,
                decision="no_candidates",
                candidate_skill_ids=[],
                rendered_skill_ids=[],
                no_skill_control=True,
                metadata={
                    "evidence_fidelity": "hash_only",
                    "redacted_user_intent": "repair redacted pdf table",
                    "redacted_intent_source": "llm_synthesized_redacted_intent",
                    "deterministic_validation": {"status": "passed"},
                },
                created_at=datetime.now(UTC),
            ),
            RetrievalLog(
                retrieval_log_id=metadata_only_log_id,
                trace_id=None,
                span_id=None,
                parent_span_id=None,
                session_id=None,
                turn_id=None,
                broker_policy_version_id=None,
                decision="no_candidates",
                candidate_skill_ids=[],
                rendered_skill_ids=[],
                no_skill_control=True,
                metadata={
                    "evidence_fidelity": "metadata_only",
                    "redacted_user_intent": "repair redacted pdf table",
                    "redacted_intent_source": "llm_synthesized_redacted_intent",
                    "deterministic_validation": {"status": "passed"},
                },
                created_at=datetime.now(UTC),
            ),
        ],
    )
    app = create_app(
        broker_policy_store=NullBrokerPolicyStore(),
        retrieval_store=retrieval,
    )
    synthesize = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/replay-episodes/synthesize"
    )

    response = asyncio.run(
        synthesize.endpoint(
            request=BrokerReplayEpisodeSynthesizeRequest(workspace_id="dev-01")
        )
    )

    assert response.episodes == []
    assert response.skipped == [
        {
            "retrieval_log_id": str(hash_only_log_id),
            "reason": "unsupported-evidence-fidelity:hash_only",
        },
        {
            "retrieval_log_id": str(metadata_only_log_id),
            "reason": "unsupported-evidence-fidelity:metadata_only",
        },
    ]


def test_broker_policy_replay_uses_stored_redacted_episode_corpus() -> None:
    policy_store = NullBrokerPolicyStore()
    skill_id = uuid4()
    retrieval = MemoryBrokerRetrievalStore(
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
            )
        ]
    )
    app = create_app(
        broker_policy_store=policy_store,
        retrieval_store=retrieval,
    )
    record = next(
        route for route in app.routes if route.path == "/v1/broker/replay-episodes"
    )
    replay = next(route for route in app.routes if route.path == "/v1/broker/policies/replay")

    async def run():
        stored = await record.endpoint(
            request=BrokerReplayEpisodeRecordRequest(
                workspace_id="dev-01",
                episode_key="pdf-table-prod-1",
                redacted_user_intent="repair redacted pdf table",
                expected_decision="skill_hint",
                expected_skill_ids=[skill_id],
                tags=["production", "pdf"],
            )
        )
        replayed = await replay.endpoint(
            request=BrokerPolicyReplayRequest(
                workspace_id="dev-01",
                include_stored_episodes=True,
                stored_episode_tags=["production"],
            )
        )
        return stored, replayed

    stored, replayed = asyncio.run(run())

    assert stored.episode["episode_key"] == "pdf-table-prod-1"
    assert replayed.replay.total == 1
    assert replayed.replay.matched == 1
    assert retrieval.calls[0]["query"] == "repair redacted pdf table"


def test_broker_policy_canary_rolls_back_critical_policy() -> None:
    policy_store = NullBrokerPolicyStore()
    app = create_app(broker_policy_store=policy_store)
    upsert = next(route for route in app.routes if route.path == "/v1/broker/policies")
    canary = next(route for route in app.routes if route.path == "/v1/broker/policies/canary")

    async def run():
        created = await upsert.endpoint(
            request=BrokerPolicyUpsertRequest(
                workspace_id="dev-01",
                version="broker-policy-test.v2",
                policy={"runtime_context_broker": {"lexical_limit": 4}},
                status="active",
            )
        )
        return await canary.endpoint(
            request=BrokerPolicyCanaryRequest(
                workspace_id="dev-01",
                broker_policy_version_id=created.policy_version[
                    "broker_policy_version_id"
                ],
                metrics={"harmful_rate": 1.0},
            )
        )

    response = asyncio.run(run())

    assert response.feedback.status == "critical"
    assert response.feedback.rollback_recommended is True
    assert response.policy_version["status"] == "rolled_back"


def test_broker_policy_review_reports_active_policy_replay_and_audit_state() -> None:
    policy_store = NullBrokerPolicyStore()
    app = create_app(broker_policy_store=policy_store)
    upsert = next(route for route in app.routes if route.path == "/v1/broker/policies")
    record = next(
        route for route in app.routes if route.path == "/v1/broker/replay-episodes"
    )
    review = next(route for route in app.routes if route.path == "/v1/broker/policies/review")

    async def run():
        await upsert.endpoint(
            request=BrokerPolicyUpsertRequest(
                workspace_id="dev-01",
                version="broker-policy-review.v1",
                policy={"runtime_context_broker": {"lexical_limit": 4}},
                status="active",
            )
        )
        await record.endpoint(
            request=BrokerReplayEpisodeRecordRequest(
                workspace_id="dev-01",
                episode_key="prod-review-1",
                redacted_user_intent="redacted runtime intent",
                expected_decision="no_skill",
                tags=["production", "operator-reviewed"],
            )
        )
        return await review.endpoint(workspace_id="dev-01")

    response = asyncio.run(run())

    assert response.review_status == "pass"
    assert response.blockers == []
    assert response.warnings == []
    assert response.active_policy["version"] == "broker-policy-review.v1"
    assert response.replay_corpus["sampled_total"] == 1
    assert response.replay_corpus["sampled_production"] == 1
    assert response.audit["chain_valid"] is True


def test_broker_policy_review_blocks_missing_active_policy_and_warns_empty_replay() -> None:
    app = create_app(broker_policy_store=NullBrokerPolicyStore())
    review = next(route for route in app.routes if route.path == "/v1/broker/policies/review")

    response = asyncio.run(review.endpoint(workspace_id="dev-01"))

    assert response.review_status == "blocked"
    assert response.blockers == ["active broker policy is missing"]
    assert response.warnings == [
        "broker replay corpus is empty",
        "production-tagged broker replay corpus is empty",
    ]


def test_broker_policy_propose_from_usage_persists_candidate_review_actions() -> None:
    policy_store = NullBrokerPolicyStore()
    skill_id = uuid4()
    evidence_id = uuid4()
    cluster_id = uuid4()
    usage = MemoryUsageRecommendationStore(
        [
            UsageTopologyRecommendation(
                skill_usage_cluster_id=cluster_id,
                cluster_key=f"decompose:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[evidence_id],
                recommended_operation="decompose",
                support_count=6,
                success_count=0,
                failure_count=0,
                sequence_count=0,
                operation_score=12.0,
                blockers=[],
                metadata={
                    "source": "usage.aggregate",
                    "topology_signal": "context_waste_or_false_positive",
                    "context_signal_count": 4,
                    "token_waste": 900,
                    "avg_context_value_per_token": -0.025,
                    "min_context_value_per_token": -0.03,
                    "subject_skill_ids": [str(skill_id)],
                    "suggested_context_actions": [
                        "broker_abstain",
                        "tighten_description",
                    ],
                },
            )
        ]
    )
    app = create_app(broker_policy_store=policy_store, usage_store=usage)
    upsert = next(route for route in app.routes if route.path == "/v1/broker/policies")
    propose = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/policies/propose-from-usage"
    )

    async def run():
        active = await upsert.endpoint(
            request=BrokerPolicyUpsertRequest(
                workspace_id="dev-01",
                version="active-policy.v1",
                policy={"runtime_context_broker": {"lexical_limit": 4}},
                status="active",
            )
        )
        proposed = await propose.endpoint(
            request=BrokerPolicyUsageProposalRequest(
                workspace_id="dev-01",
                persist=True,
            )
        )
        still_active = await policy_store.get_active_policy(workspace_key="dev-01")
        return active, proposed, still_active

    active, response, still_active = asyncio.run(run())

    assert response.recommendations_scanned == 1
    assert response.skipped == []
    assert len(response.proposals) == 1
    assert [item["action"] for item in response.proposals[0]["review_actions"]] == [
        "broker_abstain",
        "tighten_description",
    ]
    assert response.policy_version is not None
    assert response.policy_version["status"] == "candidate"
    assert response.policy_version["version"].startswith("usage-broker-policy.")
    assert response.policy_version["policy"]["runtime_context_broker"]["lexical_limit"] == 4
    reviews = response.policy_version["policy"]["runtime_context_broker"][
        "usage_context_action_reviews"
    ]
    assert len(reviews) == 2
    assert reviews[0]["status"] == "operator_review_required"
    assert reviews[0]["subject_skill_ids"] == [str(skill_id)]
    assert reviews[0]["evidence_ids"] == [str(evidence_id)]
    assert reviews[0]["context_signal_count"] == 4
    assert reviews[0]["token_waste"] == 900
    assert "broker_abstain" in reviews[0]["reason_codes"]
    assert still_active is not None
    assert str(still_active.broker_policy_version_id) == active.policy_version[
        "broker_policy_version_id"
    ]


def test_broker_policy_propose_from_usage_skips_non_policy_signals() -> None:
    skill_id = uuid4()
    usage = MemoryUsageRecommendationStore(
        [
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"improve:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[],
                recommended_operation="improve",
                support_count=2,
                success_count=0,
                failure_count=1,
                sequence_count=0,
                operation_score=1.0,
                blockers=["usage cluster support below threshold"],
                metadata={"source": "usage.aggregate"},
            ),
            UsageTopologyRecommendation(
                skill_usage_cluster_id=uuid4(),
                cluster_key=f"compose:{skill_id}",
                skill_ids=[skill_id],
                evidence_ids=[],
                recommended_operation="compose",
                support_count=5,
                success_count=3,
                failure_count=0,
                sequence_count=2,
                operation_score=7.0,
                blockers=[],
                metadata={
                    "source": "usage.aggregate",
                    "suggested_context_actions": ["decompose_skill"],
                },
            ),
        ]
    )
    app = create_app(
        broker_policy_store=NullBrokerPolicyStore(),
        usage_store=usage,
    )
    propose = next(
        route
        for route in app.routes
        if route.path == "/v1/broker/policies/propose-from-usage"
    )

    response = asyncio.run(
        propose.endpoint(
            request=BrokerPolicyUsageProposalRequest(
                workspace_id="dev-01",
                persist=True,
            )
        )
    )

    assert response.recommendations_scanned == 2
    assert response.proposals == []
    assert response.policy_version is None
    assert [item["skipped_reason"] for item in response.skipped] == [
        "recommendation blocked by usage thresholds",
        "usage recommendation has no broker policy action",
    ]
