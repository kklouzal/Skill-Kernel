from datetime import UTC, datetime
from uuid import uuid4

from autoskill.db.usage import _skill_pairs, _stable_skill_ids, _usage_window_from_row


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
