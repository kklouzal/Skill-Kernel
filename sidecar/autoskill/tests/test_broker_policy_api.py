import asyncio
from uuid import uuid4

from autoskill.api.app import (
    BrokerPolicyActivateRequest,
    BrokerPolicyCanaryRequest,
    BrokerPolicyReplayRequest,
    BrokerPolicyUpsertRequest,
    BrokerReplayEpisodeRecordRequest,
    create_app,
)
from autoskill.db.broker_policy import NullBrokerPolicyStore
from autoskill.db.retrieval import RetrievalCandidate
from autoskill.services.broker import BrokerReplayEpisode
from autoskill.tests.test_broker import MemoryBrokerRetrievalStore


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
