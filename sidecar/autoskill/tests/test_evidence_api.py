import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import EvidenceDeriveRequest, create_app
from autoskill.core.enums import EvidenceMaturity
from autoskill.db.evidence import (
    RECURRING_EVIDENCE_MIN_SUPPORT,
    EvidenceDeriveResult,
    EvidenceRecord,
    _historical_chunk_payload,
    _historical_chunk_taint,
    _recurring_payload,
    _recurring_signature,
)


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


def test_recurring_evidence_signature_uses_redacted_stable_terms() -> None:
    now = datetime.now(UTC)
    record = EvidenceRecord(
        evidence_id=UUID("00000000-0000-0000-0000-000000000011"),
        workspace_id=UUID("00000000-0000-0000-0000-000000000012"),
        workspace_key="dev-01",
        source_event_id=uuid4(),
        evidence_hash="hash-recurring-1",
        kind="event_observation",
        maturity="observed",
        trust="tool_output",
        taint=["tool", "redacted"],
        summary="Observed redacted tool_call_end event.",
        payload={
            "source_event": {"event_type": "tool_call_end", "source": "openclaw-plugin"},
            "redacted_payload": {
                "tool": "pytest",
                "error": {"code": "ModuleNotFoundError", "message": "missing package"},
            },
        },
        created_at=now,
    )

    signature = _recurring_signature(record)

    assert signature == "tool-call-end:modulenotfounderror:pytest"


def test_recurring_payload_is_runtime_safe_and_cites_support() -> None:
    now = datetime.now(UTC)
    workspace_id = UUID("00000000-0000-0000-0000-000000000022")
    records = [
        EvidenceRecord(
            evidence_id=UUID(f"00000000-0000-0000-0000-00000000003{index}"),
            workspace_id=workspace_id,
            workspace_key="dev-01",
            source_event_id=uuid4(),
            evidence_hash=f"hash-recurring-{index}",
            kind="event_observation",
            maturity="observed",
            trust="tool_output",
            taint=["tool"],
            summary="Observed redacted tool_call_end event.",
            payload={
                "source_event": {"event_type": "tool_call_end", "source": "openclaw-plugin"},
                "redacted_payload": {"content": "pytest missing package"},
            },
            created_at=now,
        )
        for index in range(RECURRING_EVIDENCE_MIN_SUPPORT)
    ]

    payload = _recurring_payload("tool-call-end:pytest:missing:package", records)

    assert payload["schema"] == "autoskill.recurring_evidence_cluster.v1"
    assert payload["support_count"] == RECURRING_EVIDENCE_MIN_SUPPORT
    assert len(payload["support_evidence_ids"]) == RECURRING_EVIDENCE_MIN_SUPPORT
    assert payload["redacted_payload"]["content"] == "tool-call-end pytest missing package"


def test_historical_chunk_evidence_payload_hashes_source_keys() -> None:
    chunk = {
        "historical_import_source_id": UUID("00000000-0000-0000-0000-000000000041"),
        "historical_import_chunk_id": UUID("00000000-0000-0000-0000-000000000042"),
        "source_kind": "taskflow_record",
        "source_key": "skillkernel-autoskill-v1",
        "fingerprint": "sha256:taskflow",
        "item_key": "taskflow#0",
        "chunk_index": 0,
        "chunk_kind": "redacted_text",
        "content_hash": "hash-redacted",
        "parser_version": "historical-import.v1",
        "redaction_policy_version": "redaction.v1",
        "redacted_text": "redacted historical checkpoint",
        "token_estimate": 4,
        "metadata": {"source": "test"},
        "taint": {"raw_text_stripped": True},
    }

    payload = _historical_chunk_payload(chunk)
    taint = _historical_chunk_taint(chunk)

    assert payload["source_event"]["event_type"] == "historical_import_chunk"
    assert payload["source_event"]["source_key_hash"]
    assert payload["source_event"]["item_key_hash"]
    assert "skillkernel-autoskill-v1" not in str(payload["source_event"])
    assert payload["redacted_payload"]["content"] == "redacted historical checkpoint"
    assert taint == ["historical", "historical:raw_text_stripped", "redacted"]
