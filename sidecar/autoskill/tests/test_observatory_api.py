import asyncio

import pytest
from autoskill.api.app import ObservatoryActionRequest, create_app
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.config import get_settings
from fastapi import HTTPException


class MemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def append_record(self, record: AuditRecord, *, workspace_key: str) -> AuditRecord:
        previous_hash = self.records[-1].audit_hash if self.records else None
        sealed = record.model_copy(update={"previous_hash": previous_hash}).sealed()
        self.records.append(sealed)
        return sealed

    async def list_recent(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        return list(reversed(self.records))[:limit]

    async def verify_chain(self, *, workspace_key: str | None = None, limit: int = 1000) -> bool:
        return verify_hash_chain(self.records[-limit:])


def _routes(app):
    return {
        (route.path, next(iter(route.methods - {"HEAD", "OPTIONS"}))): route
        for route in app.routes
        if hasattr(route, "methods")
    }


def test_observatory_summary_exposes_all_pipeline_stations_and_truth_states() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/summary", "GET")]

    async def run():
        return await route.endpoint(workspace_id="dev-01", window_minutes=30)

    response = asyncio.run(run())
    snapshot = response.snapshot

    assert snapshot["schema_version"] == "skillkernel.observatory.v1"
    assert snapshot["workspace_id"] == "dev-01"
    assert len(snapshot["pipeline"]["stations"]) == 24
    assert len(snapshot["subsystems"]) == 8
    assert snapshot["global_health"] in {"blocked", "degraded", "unknown"}
    assert any(
        issue["reason_codes"] == ["database-not-configured"] for issue in snapshot["issue_board"]
    )
    for station in snapshot["pipeline"]["stations"]:
        assert {"input", "processing", "output", "quality", "control", "evidence"} == set(
            station["signal_contract"]
        )
        assert station["data_quality"]["raw_content_available"] is False
        assert station["details_url"].startswith("/admin/components/")


def test_observatory_pipeline_component_and_search_routes_are_bounded() -> None:
    app = create_app(audit_store=MemoryAuditStore())
    routes = _routes(app)

    async def run():
        pipeline = await routes[("/admin/api/v1/pipeline", "GET")].endpoint(
            workspace_id="dev-01",
            window_minutes=10,
        )
        component = await routes[("/admin/api/v1/components/{component_id}", "GET")].endpoint(
            component_id="scheduler_jobs",
            workspace_id="dev-01",
            window_minutes=10,
        )
        search = await routes[("/admin/api/v1/search", "GET")].endpoint(
            workspace_id="dev-01",
            query="scheduler",
            limit=5,
        )
        return pipeline, component, search

    pipeline, component, search = asyncio.run(run())

    assert "pipeline" in pipeline.snapshot
    assert component.object["object_type"] == "component"
    assert component.object["object_id"] == "scheduler_jobs"
    assert component.object["content_policy"]["raw_available"] is False
    assert search.results
    assert len(search.results) <= 5
    assert all(
        "scheduler"
        in " ".join(
            [
                result["object_id"],
                result["title"],
                result["summary"],
                result["url"],
            ]
        ).lower()
        for result in search.results
    )


def test_observatory_action_records_audited_policy_receipt() -> None:
    audit_store = MemoryAuditStore()
    app = create_app(audit_store=audit_store)
    route = _routes(app)[("/admin/api/v1/actions", "POST")]

    async def run():
        return await route.endpoint(
            request=ObservatoryActionRequest(
                workspace_id="dev-01",
                action="verify_audit_chain",
                idempotency_key="obs-test-1",
                reason="operator requested audit proof",
            )
        )

    response = asyncio.run(run())

    assert response.receipt["accepted"] is True
    assert response.receipt["policy"]["allowed"] is True
    assert response.receipt["audit"]["subject_id"] == "obs-test-1"
    assert audit_store.records[0].action == "observatory.verify_audit_chain"


def test_observatory_admin_token_is_enforced(monkeypatch) -> None:
    monkeypatch.setenv("SKILLKERNEL_ADMIN_TOKEN", "admin-token")
    get_settings.cache_clear()
    app = create_app(audit_store=MemoryAuditStore())
    route = _routes(app)[("/admin/api/v1/config", "GET")]

    async def unauthorized():
        return await route.endpoint()

    async def authorized():
        return await route.endpoint(authorization="Bearer admin-token")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(unauthorized())
    assert exc.value.status_code == 401

    response = asyncio.run(authorized())
    assert response.config["principal"]["auth_configured"] is True

    get_settings.cache_clear()
