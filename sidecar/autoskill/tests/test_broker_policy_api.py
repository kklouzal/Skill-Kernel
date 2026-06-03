import asyncio
from uuid import uuid4

from autoskill.api.app import (
    BrokerPolicyActivateRequest,
    BrokerPolicyCanaryRequest,
    BrokerPolicyReplayRequest,
    BrokerPolicyUpsertRequest,
    BrokerPolicyUsageProposalRequest,
    BrokerReplayEpisodeRecordRequest,
    create_app,
)
from autoskill.db.broker_policy import NullBrokerPolicyStore
from autoskill.db.retrieval import RetrievalCandidate
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
