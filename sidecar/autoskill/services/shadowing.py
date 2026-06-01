from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from autoskill.db.attribution import AttributionEventRecord, AttributionStore
from autoskill.db.evidence import EvidenceRecord, EvidenceStore

_SHADOW_OUTCOMES = {"skill_shadowed", "shadowed", "wrong_skill"}
_CORRECTION_PHRASES = (
    "wrong skill",
    "shadowed",
    "should have used",
    "used the wrong",
    "better skill",
)


@dataclass(frozen=True)
class ShadowingDetectionResult:
    scanned: int
    detected: int
    events: list[AttributionEventRecord]
    controls: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "detected": self.detected,
            "events": [event.to_json() for event in self.events],
            "controls": self.controls,
        }


async def detect_shadowing_events(
    evidence_store: EvidenceStore,
    attribution_store: AttributionStore,
    *,
    workspace_key: str,
    limit: int = 100,
    min_support: int = 2,
) -> ShadowingDetectionResult:
    evidence = await evidence_store.list_evidence(workspace_key=workspace_key, limit=limit)
    events: list[AttributionEventRecord] = []
    grouped: dict[tuple[UUID, UUID], list[UUID]] = {}
    for record in evidence:
        signal = _shadowing_signal(record)
        if signal is None:
            continue
        source_event = record.payload.get("source_event", {})
        event = await attribution_store.record_event(
            workspace_key=workspace_key,
            session_id=_optional_str(source_event.get("session_id")),
            turn_id=_optional_str(source_event.get("turn_id")),
            action_kind="skill_shadowing_detection",
            risk_level="medium",
            skill_ids=signal["skill_ids"],
            outcome="skill_shadowed",
            metadata={
                "source_evidence_id": str(record.evidence_id),
                "reason": signal["reason"],
                "selected_skill_id": signal.get("selected_skill_id"),
                "expected_skill_id": signal.get("expected_skill_id"),
            },
        )
        events.append(event)
        selected_skill_id = signal.get("selected_skill_uuid")
        expected_skill_id = signal.get("expected_skill_uuid")
        if isinstance(selected_skill_id, UUID) and isinstance(expected_skill_id, UUID):
            pair = (selected_skill_id, expected_skill_id)
            grouped.setdefault(pair, []).append(record.evidence_id)
    controls = await _materialize_shadowing_controls(
        attribution_store,
        workspace_key=workspace_key,
        grouped=grouped,
        min_support=max(2, min_support),
    )
    return ShadowingDetectionResult(
        scanned=len(evidence),
        detected=len(events),
        events=events,
        controls=controls,
    )


def _shadowing_signal(record: EvidenceRecord) -> dict[str, Any] | None:
    payload = record.payload.get("redacted_payload", {})
    if not isinstance(payload, dict):
        return None

    outcome = str(payload.get("outcome") or payload.get("classification") or "").lower()
    selected = _optional_str(payload.get("selected_skill_id") or payload.get("actual_skill_id"))
    expected = _optional_str(payload.get("expected_skill_id") or payload.get("better_skill_id"))
    content_value = payload.get("content") or payload.get("message") or payload.get("correction")
    content = str(content_value or "")
    content_lc = content.lower()

    reason: str | None = None
    if outcome in _SHADOW_OUTCOMES:
        reason = f"explicit outcome {outcome}"
    elif selected and expected and selected != expected:
        reason = "selected skill differed from expected skill"
    elif any(phrase in content_lc for phrase in _CORRECTION_PHRASES):
        reason = "user correction indicated skill shadowing"

    if reason is None:
        return None

    selected_uuid = _parse_uuid(selected)
    expected_uuid = _parse_uuid(expected)
    skill_ids = [_uuid for _uuid in (selected_uuid, expected_uuid) if _uuid is not None]
    return {
        "reason": reason,
        "selected_skill_id": selected,
        "selected_skill_uuid": selected_uuid,
        "expected_skill_id": expected,
        "expected_skill_uuid": expected_uuid,
        "skill_ids": skill_ids,
    }


async def _materialize_shadowing_controls(
    attribution_store: AttributionStore,
    *,
    workspace_key: str,
    grouped: dict[tuple[UUID, UUID], list[UUID]],
    min_support: int,
) -> list[dict[str, Any]]:
    record_control = getattr(attribution_store, "record_shadowing_control", None)
    if record_control is None:
        return []
    controls: list[dict[str, Any]] = []
    for (selected_skill_id, expected_skill_id), evidence_ids in sorted(
        grouped.items(),
        key=lambda item: (str(item[0][0]), str(item[0][1])),
    ):
        if len(evidence_ids) < min_support:
            continue
        controls.append(
            await record_control(
                workspace_key=workspace_key,
                selected_skill_id=selected_skill_id,
                expected_skill_id=expected_skill_id,
                evidence_ids=evidence_ids,
                support_count=len(evidence_ids),
            )
        )
    return controls


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
