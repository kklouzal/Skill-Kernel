from uuid import uuid4

import pytest
from autoskill.core.enums import TrustClass
from autoskill.core.events import EventEnvelope
from autoskill.db.events import EventIngestSummary


class MemoryEventStore:
    def __init__(self) -> None:
        self.event_ids: set[str] = set()
        self.events: list[EventEnvelope] = []

    async def ingest_events(self, events: list[EventEnvelope]) -> EventIngestSummary:
        accepted = 0
        duplicate = 0
        for event in events:
            key = str(event.event_id)
            if key in self.event_ids:
                duplicate += 1
                continue
            self.event_ids.add(key)
            self.events.append(event)
            accepted += 1
        return EventIngestSummary(accepted=accepted, duplicate=duplicate)


def event() -> EventEnvelope:
    return EventEnvelope(
        workspace_id="dev-01",
        trace_id=uuid4(),
        span_id=uuid4(),
        session_id="session-1",
        turn_id="turn-1",
        event_type="tool_call_end",
        trust=TrustClass.TOOL_OUTPUT,
        payload={"token": "secret", "safe": "ok"},
    ).redacted()


@pytest.mark.asyncio
async def test_event_store_ingest_is_idempotent() -> None:
    store = MemoryEventStore()
    first = event()

    first_result = await store.ingest_events([first])
    second_result = await store.ingest_events([first])

    assert first_result.accepted == 1
    assert second_result.duplicate == 1
    assert len(store.events) == 1
    assert store.events[0].payload["token"] == "[REDACTED]"
    assert store.events[0].payload_hash
    assert store.events[0].trace_id
    assert store.events[0].span_id
