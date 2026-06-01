import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import EvidenceDeriveRequest, create_app
from autoskill.core.enums import EvidenceMaturity
from autoskill.db.evidence import EvidenceDeriveResult, EvidenceRecord


class MemoryEvidenceStore:
    def __init__(self) -> None:
        self.evidence: list[EvidenceRecord] = []
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def derive_from_raw_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> EvidenceDeriveResult:
        if self.evidence:
            return EvidenceDeriveResult(scanned=0, created=0, duplicate=0, evidence=[])
        now = datetime.now(UTC)
        record = EvidenceRecord(
            evidence_id=uuid4(),
            workspace_id=uuid4(),
            workspace_key=workspace_key or "dev-01",
            source_event_id=uuid4(),
            evidence_hash="hash-1",
            kind="event_observation",
            maturity=str(EvidenceMaturity.OBSERVED),
            trust="tool_output",
            taint=["tool"],
            summary="Observed redacted tool_call_end event from openclaw-plugin in s/t.",
            payload={"redacted_payload": {"safe": "ok"}},
            created_at=now,
        )
        self.evidence.append(record)
        return EvidenceDeriveResult(scanned=1, created=1, duplicate=0, evidence=[record])

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        records = self.evidence
        if workspace_key:
            records = [record for record in records if record.workspace_key == workspace_key]
        return records[:limit]


def test_evidence_api_derives_and_lists_records() -> None:
    store = MemoryEvidenceStore()
    app = create_app(evidence_store=store)
    derive_route = next(route for route in app.routes if route.path == "/v1/evidence/derive")
    list_route = next(route for route in app.routes if route.path == "/v1/evidence")

    async def run() -> tuple[object, dict[str, object]]:
        derived = await derive_route.endpoint(
            request=EvidenceDeriveRequest(workspace_id="dev-01", limit=10)
        )
        listed = await list_route.endpoint(workspace_id="dev-01")
        return derived, listed

    derived, listed = asyncio.run(run())

    assert derived.created == 1
    assert derived.evidence[0]["kind"] == "event_observation"
    assert derived.evidence[0]["maturity"] == "observed"
    assert listed["evidence"][0]["evidence_hash"] == "hash-1"


def test_evidence_record_json_preserves_provenance_ids() -> None:
    now = datetime.now(UTC)
    source_event_id = uuid4()
    record = EvidenceRecord(
        evidence_id=UUID("00000000-0000-0000-0000-000000000001"),
        workspace_id=UUID("00000000-0000-0000-0000-000000000002"),
        workspace_key="dev-01",
        source_event_id=source_event_id,
        evidence_hash="hash-2",
        kind="event_observation",
        maturity="observed",
        trust="agent_output",
        taint=[],
        summary="Observed redacted llm_output event from openclaw-plugin in s/t.",
        payload={"source_event": {"event_id": str(source_event_id)}},
        created_at=now,
    )

    payload = record.to_json()

    assert payload["workspace_key"] == "dev-01"
    assert payload["source_event_id"] == str(source_event_id)
    assert payload["payload"]["source_event"]["event_id"] == str(source_event_id)
