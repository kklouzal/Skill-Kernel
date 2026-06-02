import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from autoskill.api.app import ActionAttributionCheckRequest, ShadowingDetectRequest, create_app
from autoskill.db.attribution import ActionAttributionCheckRecord, AttributionEventRecord
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
        self.controls: list[dict[str, object]] = []
        self.action_checks: list[ActionAttributionCheckRecord] = []

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

    async def record_shadowing_control(
        self,
        *,
        workspace_key: str,
        selected_skill_id: UUID,
        expected_skill_id: UUID,
        evidence_ids: list[UUID],
        support_count: int,
    ) -> dict[str, object]:
        control = {
            "workspace_key": workspace_key,
            "selected_skill_id": str(selected_skill_id),
            "expected_skill_id": str(expected_skill_id),
            "evidence_ids": [str(evidence_id) for evidence_id in evidence_ids],
            "support_count": support_count,
            "edge_created": True,
            "probe_created": True,
            "probe_hash": "shadow-probe",
        }
        self.controls.append(control)
        return control

    async def record_action_check(
        self,
        *,
        workspace_key: str,
        session_id: str | None,
        turn_id: str | None,
        tool_call_id: str | None,
        action_kind: str,
        risk_tier: str,
        verdict: str,
        metrics: dict[str, object],
        user_intent_hash: str | None = None,
        contributing_skill_ids: list[UUID] | None = None,
        contributing_memory_ids: list[UUID] | None = None,
        contributing_evidence_ids: list[UUID] | None = None,
        broker_policy_version_id: UUID | None = None,
        counterfactual_kind: str | None = None,
    ) -> ActionAttributionCheckRecord:
        record = ActionAttributionCheckRecord(
            action_attribution_check_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            session_id=session_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
            action_kind=action_kind,
            risk_tier=risk_tier,
            user_intent_hash=user_intent_hash,
            contributing_skill_ids=contributing_skill_ids or [],
            contributing_memory_ids=contributing_memory_ids or [],
            contributing_evidence_ids=contributing_evidence_ids or [],
            broker_policy_version_id=broker_policy_version_id,
            counterfactual_kind=counterfactual_kind,
            verdict=verdict,
            metrics=metrics,
            created_at=datetime.now(UTC),
        )
        self.action_checks.append(record)
        return record


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


def test_shadowing_detection_materializes_controls_after_repeated_mismatch() -> None:
    skills = ShadowSkills(selected=uuid4(), expected=uuid4())
    store = MemoryShadowEvidenceStore(
        [
            shadow_evidence({}, skills),
            shadow_evidence({"classification": "wrong_skill"}, skills),
        ]
    )
    attribution = MemoryAttributionStore()

    async def run():
        return await detect_shadowing_events(
            store,
            attribution,
            workspace_key="dev-01",
            min_support=2,
        )

    result = asyncio.run(run())

    assert result.detected == 2
    assert len(result.controls) == 1
    assert result.controls[0]["selected_skill_id"] == str(skills.selected)
    assert result.controls[0]["expected_skill_id"] == str(skills.expected)
    assert result.controls[0]["support_count"] == 2


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


def test_action_attribution_check_api_records_boundary_verdict() -> None:
    attribution = MemoryAttributionStore()
    app = create_app(attribution_store=attribution)
    route = next(
        route for route in app.routes if route.path == "/v1/attribution/action-checks"
    )

    async def run():
        return await route.endpoint(
            request=ActionAttributionCheckRequest(
                workspace_id="dev-01",
                session_id="session-1",
                turn_id="turn-1",
                tool_call_id="tool-1",
                action_kind="exec",
                risk_tier="high",
                verdict="blocked",
                counterfactual_kind="runtime_boundary",
                metrics={"boundary_code": "sensitive-file-harvest"},
            ),
            authorization=None,
        )

    response = asyncio.run(run())

    assert len(attribution.action_checks) == 1
    assert response.check["verdict"] == "blocked"
    assert response.check["counterfactual_kind"] == "runtime_boundary"
    assert response.check["metrics"]["boundary_code"] == "sensitive-file-harvest"
