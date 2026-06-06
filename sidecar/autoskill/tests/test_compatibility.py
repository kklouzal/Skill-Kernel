import asyncio
from uuid import uuid4

from autoskill.api.app import SkillProfileCompatibilityUpsertRequest, create_app
from autoskill.core.config import get_settings
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


def test_core_compatibility_handshake_endpoints_report_contract(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_IGNORE_ENV_FILE", "1")
    monkeypatch.delenv("AUTOSKILL_DATABASE_URL", raising=False)
    monkeypatch.delenv("SKILLKERNEL_DATABASE_URL", raising=False)
    monkeypatch.delenv("AUTOSKILL_LLM_API_BASE_URL", raising=False)
    monkeypatch.delenv("AUTOSKILL_EMBEDDING_API_BASE_URL", raising=False)
    get_settings.cache_clear()
    app = create_app()
    routes = {
        (route.path, method): route
        for route in app.routes
        for method in route.methods
    }

    version = asyncio.run(routes[("/v1/version", "GET")].endpoint())
    capabilities = asyncio.run(routes[("/v1/capabilities", "GET")].endpoint())
    contract = asyncio.run(routes[("/v1/read-model-contract", "GET")].endpoint())
    ready = asyncio.run(routes[("/v1/health/ready", "GET")].endpoint())

    assert version.service == "skillkernel-core"
    assert version.api_contract_version == "skillkernel.api.v1"
    assert version.schema_migration_version == "0001_autoskill_schema"
    assert version.read_model_contract_version == "skillkernel.readmodels.v1"
    assert "guarded_action_requests" in version.features
    assert "semantic_adjudication" in version.degraded_features
    assert capabilities.capabilities["topology_operations"] == [
        "create",
        "improve",
        "compose",
        "decompose",
    ]
    assert contract.contract["admin_base_path"] == "/admin/api/v1"
    assert contract.contract["content_policy"]["live_stream_raw_content"] == "forbidden"
    assert ready.ready is False
    assert ready.checks["database_configured"] is False
    assert ready.checks["read_model_contract_version"] == "skillkernel.readmodels.v1"

    get_settings.cache_clear()
