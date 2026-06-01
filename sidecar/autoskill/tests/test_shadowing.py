import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import ShadowingDetectRequest, create_app
from autoskill.db.attribution import AttributionEventRecord
from autoskill.db.evidence import EvidenceRecord
from autoskill.services.shadowing import detect_shadowing_events


class MemoryShadowEvidenceStore:
    def __init__(self, records: list[EvidenceRecord]) -> None:
        self.records = records

    async def list_evidence(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        return self.records[:limit]

    async def derive_from_raw_events(self, **_kwargs):
        raise NotImplementedError


class MemoryAttributionStore:
    def __init__(self) -> None:
        self.events: list[AttributionEventRecord] = []

    async def record_event(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        action_kind: str,
        risk_level: str,
        skill_ids: list[UUID],
        outcome: str | None,
        metadata: dict[str, object],
    ) -> AttributionEventRecord:
        event = AttributionEventRecord(
            attribution_event_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            session_id=session_id,
            turn_id=turn_id,
            action_kind=action_kind,
            risk_level=risk_level,
            skill_ids=skill_ids,
            outcome=outcome,
            metadata=metadata,
            created_at=datetime.now(UTC),
        )
        self.events.append(event)
        return event


@dataclass(frozen=True)
class ShadowSkills:
    selected: UUID
    expected: UUID


def shadow_evidence(
    payload: dict[str, object],
    skills: ShadowSkills | None = None,
) -> EvidenceRecord:
    source = {"event_type": "runtime_outcome", "session_id": "s", "turn_id": "t"}
    if skills:
        payload = payload | {
            "selected_skill_id": str(skills.selected),
            "expected_skill_id": str(skills.expected),
        }
    return EvidenceRecord(
        evidence_id=uuid4(),
        workspace_id=uuid4(),
        workspace_key="dev-01",
        source_event_id=uuid4(),
        evidence_hash=str(uuid4()),
        kind="event_observation",
        maturity="observed",
        trust="system_owned",
        taint=[],
        summary="Observed redacted runtime outcome event.",
        payload={"source_event": source, "redacted_payload": payload},
        created_at=datetime.now(UTC),
    )


def test_shadowing_detection_records_explicit_outcome() -> None:
    store = MemoryShadowEvidenceStore([shadow_evidence({"outcome": "skill_shadowed"})])
    attribution = MemoryAttributionStore()

    async def run():
        return await detect_shadowing_events(
            store,
            attribution,
            workspace_key="dev-01",
        )

    result = asyncio.run(run())
    event = result.events[0]

    assert result.scanned == 1
    assert result.detected == 1
    assert event.outcome == "skill_shadowed"
    assert event.metadata["reason"] == "explicit outcome skill_shadowed"


def test_shadowing_detection_records_selected_expected_mismatch() -> None:
    skills = ShadowSkills(selected=uuid4(), expected=uuid4())
    store = MemoryShadowEvidenceStore([shadow_evidence({}, skills)])
    attribution = MemoryAttributionStore()

    async def run():
        return await detect_shadowing_events(
            store,
            attribution,
            workspace_key="dev-01",
        )

    result = asyncio.run(run())
    event = result.events[0]

    assert event.skill_ids == [skills.selected, skills.expected]
    assert event.metadata["reason"] == "selected skill differed from expected skill"


def test_shadowing_detection_api_uses_stores() -> None:
    store = MemoryShadowEvidenceStore(
        [shadow_evidence({"content": "That used the wrong skill; should have used the PDF one."})]
    )
    attribution = MemoryAttributionStore()
    app = create_app(evidence_store=store, attribution_store=attribution)
    route = next(route for route in app.routes if route.path == "/v1/shadowing/detect")

    async def run():
        return await route.endpoint(request=ShadowingDetectRequest(workspace_id="dev-01"))

    response = asyncio.run(run())

    assert response.detected == 1
    assert response.events[0]["metadata"]["reason"] == "user correction indicated skill shadowing"
