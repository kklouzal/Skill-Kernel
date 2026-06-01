import asyncio
from uuid import uuid4

from autoskill.api.app import SkillProfileCompatibilityUpsertRequest, create_app
from autoskill.db.compatibility import NullCompatibilityStore


def test_compatibility_api_records_executor_profile_status() -> None:
    store = NullCompatibilityStore()
    app = create_app(compatibility_store=store)
    route = next(route for route in app.routes if route.path == "/v1/profiles/compatibility")
    skill_version_id = uuid4()
    executor_profile_id = uuid4()

    async def run():
        return await route.endpoint(
            request=SkillProfileCompatibilityUpsertRequest(
                workspace_id="dev-01",
                skill_version_id=skill_version_id,
                executor_profile_id=executor_profile_id,
                status="blocked",
                evidence={"reason": "missing binary"},
            )
        )

    response = asyncio.run(run())

    assert response.compatibility["status"] == "blocked"
    assert response.compatibility["evidence"] == {"reason": "missing binary"}
    assert asyncio.run(
        store.list_statuses(
            workspace_key="dev-01",
            executor_profile_id=executor_profile_id,
            skill_version_ids=[skill_version_id],
        )
    ) == {skill_version_id: "blocked"}
