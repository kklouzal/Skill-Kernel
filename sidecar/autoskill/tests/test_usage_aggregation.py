from datetime import UTC, datetime
from uuid import uuid4

from autoskill.db.usage import (
    _skill_pairs,
    _stable_skill_ids,
    _topology_recommendation_from_row,
    _usage_window_from_row,
)


def test_usage_window_signature_is_stable_and_content_safe() -> None:
    first = uuid4()
    second = uuid4()
    observed_at = datetime(2026, 6, 2, tzinfo=UTC)
    row = {
        "source_kind": "retrieval_log",
        "source_id": uuid4(),
        "session_id": "session-1",
        "turn_id": "turn-1",
        "skill_ids": [first, second, first],
        "outcome": "rendered",
        "metadata": '{"redacted": true, "token_count": 42}',
        "observed_at": observed_at,
    }

    window = _usage_window_from_row(row)
    duplicate = _usage_window_from_row(row)

    assert window["sequence_signature_hash"] == duplicate["sequence_signature_hash"]
    assert window["skill_ids"] == [first, second]
    assert window["metadata"] == {
        "source_kind": "retrieval_log",
        "source_id": str(row["source_id"]),
        "source_metadata": {"token_count": 42, "redacted": True},
    }
    assert window["observed_at"] == observed_at


def test_usage_pair_generation_is_deterministic() -> None:
    high = uuid4()
    low = uuid4()
    if str(high) < str(low):
        high, low = low, high

    assert _stable_skill_ids([high, low, high]) == [high, low]
    assert _skill_pairs([high, low, high]) == [(low, high)]


def test_topology_recommendation_scores_stable_usage_cluster() -> None:
    first = uuid4()
    second = uuid4()
    cluster_id = uuid4()
    row = {
        "skill_usage_cluster_id": cluster_id,
        "cluster_key": f"compose:{first}:{second}",
        "skill_ids": [first, second],
        "evidence_ids": [],
        "support_count": 4,
        "recommended_operation": "compose",
        "metadata": {
            "source": "usage.aggregate",
            "success_count": 3,
            "failure_count": 0,
            "sequence_count": 4,
            "topology_signal": "recurring_co_usage",
        },
    }

    recommendation = _topology_recommendation_from_row(
        row,
        min_support=3,
        min_success_count=1,
        max_failure_ratio=0.25,
        min_sequence_count=1,
    )

    assert recommendation.accepted
    assert recommendation.operation_score == 14.0
    assert recommendation.to_json()["skill_ids"] == [str(first), str(second)]
    assert recommendation.metadata["failure_ratio"] == 0.0


def test_topology_recommendation_blocks_weak_or_harmful_cluster() -> None:
    row = {
        "skill_usage_cluster_id": uuid4(),
        "cluster_key": "compose:weak",
        "skill_ids": [uuid4()],
        "evidence_ids": [],
        "support_count": 2,
        "recommended_operation": "compose",
        "metadata": {
            "source": "usage.aggregate",
            "success_count": 0,
            "failure_count": 2,
            "sequence_count": 0,
        },
    }

    recommendation = _topology_recommendation_from_row(
        row,
        min_support=3,
        min_success_count=1,
        max_failure_ratio=0.25,
        min_sequence_count=1,
    )

    assert not recommendation.accepted
    assert recommendation.blockers == [
        "usage cluster support below threshold",
        "compose recommendation requires at least two skills",
        "usage cluster lacks successful outcome evidence",
        "usage cluster failure ratio above threshold",
        "usage cluster lacks stable sequence evidence",
    ]
