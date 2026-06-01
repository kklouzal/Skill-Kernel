import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from autoskill.api.app import (
    CanaryResultRequest,
    FreezeSkillRequest,
    UnfreezeSkillRequest,
    create_app,
)
from autoskill.db.lifecycle import (
    CanaryRecordResult,
    CanaryResultRecord,
    SkillLifecycleRecord,
)


class MemoryLifecycleStore:
    def __init__(self) -> None:
        self.skills: dict[UUID, SkillLifecycleRecord] = {}
        self.canaries: list[CanaryResultRecord] = []

    async def freeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        reason: str,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        record = _skill_record(
            workspace_key=workspace_key,
            skill_id=skill_id,
            lifecycle_state="frozen",
            last_canary_status="critical",
            freeze_reason=reason,
        )
        self.skills[skill_id] = record
        return record

    async def unfreeze_skill(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        target_state: str = "candidate",
        reason: str | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> SkillLifecycleRecord | None:
        if target_state == "frozen":
            raise ValueError("target_state must not be frozen")
        record = _skill_record(
            workspace_key=workspace_key,
            skill_id=skill_id,
            lifecycle_state=target_state,
            last_canary_status=None,
            freeze_reason=None,
        )
        self.skills[skill_id] = record
        return record

    async def record_canary_result(
        self,
        *,
        workspace_key: str,
        skill_id: UUID,
        status: str,
        critical: bool = False,
        reason: str | None = None,
        metrics: dict[str, object] | None = None,
        skill_version_id: UUID | None = None,
        evolution_transaction_id: UUID | None = None,
    ) -> CanaryRecordResult:
        canary = CanaryResultRecord(
            canary_result_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            evolution_transaction_id=evolution_transaction_id,
            status=status,
            critical=critical,
            reason=reason,
            metrics=metrics or {},
            observed_at=datetime.now(UTC),
        )
        self.canaries.append(canary)
        skill = None
        if critical:
            skill = await self.freeze_skill(
                workspace_key=workspace_key,
                skill_id=skill_id,
                reason=reason or "critical canary failure",
                evolution_transaction_id=evolution_transaction_id,
            )
        return CanaryRecordResult(canary=canary, skill=skill)


def test_canary_api_freezes_skill_on_critical_failure() -> None:
    lifecycle = MemoryLifecycleStore()
    app = create_app(lifecycle_store=lifecycle)
    route = next(route for route in app.routes if route.path == "/v1/canary/results")
    skill_id = uuid4()

    async def run():
        return await route.endpoint(
            request=CanaryResultRequest(
                workspace_id="dev-01",
                skill_id=skill_id,
                status="critical",
                reason="canary regression exceeded rollback threshold",
                metrics={"failures": 2},
            )
        )

    response = asyncio.run(run())

    assert response.canary["status"] == "critical"
    assert response.canary["critical"] is True
    assert response.skill is not None
    assert response.skill["lifecycle_state"] == "frozen"
    assert response.skill["freeze_reason"] == "canary regression exceeded rollback threshold"
    assert response.revocation is None


def test_control_freeze_and_unfreeze_routes_update_lifecycle() -> None:
    lifecycle = MemoryLifecycleStore()
    app = create_app(lifecycle_store=lifecycle)
    freeze_route = next(route for route in app.routes if route.path == "/v1/control/freeze")
    unfreeze_route = next(route for route in app.routes if route.path == "/v1/control/unfreeze")
    skill_id = uuid4()

    async def run():
        frozen = await freeze_route.endpoint(
            request=FreezeSkillRequest(
                workspace_id="dev-01",
                skill_id=skill_id,
                reason="operator freeze",
            )
        )
        unfrozen = await unfreeze_route.endpoint(
            request=UnfreezeSkillRequest(
                workspace_id="dev-01",
                skill_id=skill_id,
                target_state="candidate",
                reason="repair staged",
            )
        )
        return frozen, unfrozen

    frozen, unfrozen = asyncio.run(run())

    assert frozen.skill["lifecycle_state"] == "frozen"
    assert unfrozen.skill["lifecycle_state"] == "candidate"
    assert unfrozen.skill["freeze_reason"] is None


def test_unfreeze_route_rejects_frozen_target_state() -> None:
    lifecycle = MemoryLifecycleStore()
    app = create_app(lifecycle_store=lifecycle)
    route = next(route for route in app.routes if route.path == "/v1/control/unfreeze")

    async def run():
        return await route.endpoint(
            request=UnfreezeSkillRequest(
                workspace_id="dev-01",
                skill_id=uuid4(),
                target_state="frozen",
            )
        )

    with pytest.raises(Exception) as error:
        asyncio.run(run())

    assert "target_state must not be frozen" in str(error.value)


def _skill_record(
    *,
    workspace_key: str,
    skill_id: UUID,
    lifecycle_state: str,
    last_canary_status: str | None,
    freeze_reason: str | None,
) -> SkillLifecycleRecord:
    now = datetime.now(UTC)
    return SkillLifecycleRecord(
        skill_id=skill_id,
        workspace_id=None,
        workspace_key=workspace_key,
        slug="autoskill-example",
        lifecycle_state=lifecycle_state,
        active_version_id=None,
        last_canary_status=last_canary_status,
        freeze_reason=freeze_reason,
        frozen_at=now if lifecycle_state == "frozen" else None,
        updated_at=now,
    )
