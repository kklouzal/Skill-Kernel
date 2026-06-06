from uuid import uuid4

import pytest
from autoskill.core.enums import TrustClass
from autoskill.core.events import EventEnvelope
from autoskill.db.events import EventIngestSummary, _insert_event


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
        agent_id="agent-1",
        session_id="session-1",
        turn_id="turn-1",
        event_type="tool_call_end",
        source_event_key="runtime-source-key-1",
        trust=TrustClass.TOOL_OUTPUT,
        evidence_fidelity="metadata_only",
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
    assert store.events[0].payload_hash.startswith("sha256:")
    assert store.events[0].trace_id
    assert store.events[0].span_id
    assert store.events[0].agent_id == "agent-1"
    assert store.events[0].source_event_key == "runtime-source-key-1"
    assert store.events[0].evidence_fidelity == "metadata_only"


@pytest.mark.asyncio
async def test_insert_event_binds_all_raw_event_columns() -> None:
    class Conn:
        def __init__(self) -> None:
            self.query = ""
            self.args: tuple[object, ...] = ()

        async def fetchval(self, query: str, *args: object) -> object:
            self.query = query
            self.args = args
            return args[0]

    conn = Conn()
    first = event()

    inserted = await _insert_event(conn, uuid4(), first)  # type: ignore[arg-type]

    assert inserted is True
    assert "$21" in conn.query
    assert len(conn.args) == 21
    assert conn.args[5] == first.agent_id
    assert conn.args[11] == first.source_event_key
    assert conn.args[14] == str(first.redaction_state)
    assert conn.args[15] == first.evidence_fidelity
    assert conn.args[17] == first.payload_hash
    assert isinstance(conn.args[18], str)
