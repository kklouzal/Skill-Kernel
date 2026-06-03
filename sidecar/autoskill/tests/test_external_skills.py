import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from autoskill.api.app import (
    ExternalSkillInventoryItem,
    ExternalSkillInventoryUpsertRequest,
    ExternalSkillReviewActionRequest,
    create_app,
)
from autoskill.db.external_skills import (
    ExternalSkillInput,
    ExternalSkillRecord,
    ExternalSkillReviewActionRecord,
    ExternalSkillUpsertResult,
)
from autoskill.db.scheduler import ScheduleRecord, ScheduleUpsertResult
from autoskill.services.external_import import materialize_external_skill_import
from autoskill.services.external_inventory import (
    ensure_external_skill_scan_schedule,
    scan_external_skill_roots,
)


class MemoryScheduleStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []

    async def upsert_schedule(
        self,
        *,
        workspace_key: str,
        name: str,
        job_kind: str,
        interval_seconds: int,
        next_run_at: datetime,
        payload: dict[str, object] | None = None,
        enabled: bool = True,
    ) -> ScheduleUpsertResult:
        self.upserts.append(
            {
                "workspace_key": workspace_key,
                "name": name,
                "job_kind": job_kind,
                "interval_seconds": interval_seconds,
                "payload": payload or {},
                "enabled": enabled,
            }
        )
        return ScheduleUpsertResult(
            schedule=ScheduleRecord(
                schedule_id=uuid4(),
                workspace_key=workspace_key,
                name=name,
                job_kind=job_kind,
                enabled=enabled,
                interval_seconds=interval_seconds,
                next_run_at=next_run_at,
                payload=payload or {},
            ),
            created=True,
        )


class MemoryExternalSkillStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.records: list[ExternalSkillRecord] = []
        self.review_actions: list[ExternalSkillReviewActionRecord] = []

    async def upsert_external_skills(
        self,
        *,
        workspace_key: str,
        skills: list[ExternalSkillInput],
    ) -> ExternalSkillUpsertResult:
        self.upserts.append({"workspace_key": workspace_key, "skills": skills})
        now = datetime.now(UTC)
        self.records = [
            ExternalSkillRecord(
                external_skill_id=uuid4(),
                workspace_id=uuid4(),
                workspace_key=workspace_key,
                source=skill.source,
                root_path_hash=skill.root_path_hash,
                slug=skill.slug,
                name=skill.name,
                description=skill.description,
                frontmatter=skill.frontmatter or {},
                file_hash=skill.file_hash,
                status=skill.status,
                risk_summary=skill.risk_summary or {},
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            for skill in skills
        ]
        return ExternalSkillUpsertResult(created=len(skills), updated=0, skills=self.records)

    async def list_external_skills(
        self,
        *,
        workspace_key: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillRecord]:
        return [
            record
            for record in self.records[:limit]
            if (workspace_key is None or record.workspace_key == workspace_key)
            and (status is None or record.status == status)
        ]

    async def record_review_action(
        self,
        *,
        workspace_key: str,
        external_skill_id,
        action: str,
        status: str = "requested",
        operator_id: str | None = None,
        rationale: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ExternalSkillReviewActionRecord:
        if action not in {"reuse", "import", "ignore", "quarantine"}:
            raise ValueError("action must be one of")
        if status not in {"requested", "approved", "rejected", "completed"}:
            raise ValueError("status must be one of")
        record = next(
            item
            for item in self.records
            if item.external_skill_id == external_skill_id and item.workspace_key == workspace_key
        )
        now = datetime.now(UTC)
        review = ExternalSkillReviewActionRecord(
            external_skill_review_action_id=uuid4(),
            workspace_id=record.workspace_id,
            workspace_key=workspace_key,
            external_skill_id=external_skill_id,
            action=action,
            status=status,
            operator_id=operator_id,
            rationale=rationale,
            metadata=metadata or {},
            created_at=now,
        )
        self.review_actions.append(review)
        return review

    async def list_review_actions(
        self,
        *,
        workspace_key: str,
        external_skill_id=None,
        action: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ExternalSkillReviewActionRecord]:
        return [
            review
            for review in self.review_actions[:limit]
            if review.workspace_key == workspace_key
            and (external_skill_id is None or review.external_skill_id == external_skill_id)
            and (action is None or review.action == action)
            and (status is None or review.status == status)
        ]


def test_external_skill_inventory_api_uses_store() -> None:
    store = MemoryExternalSkillStore()
    app = create_app(external_skill_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/external-skills/upsert")
    list_route = next(route for route in app.routes if route.path == "/v1/external-skills")

    async def run():
        upsert_response = await upsert_route.endpoint(
            request=ExternalSkillInventoryUpsertRequest(
                workspace_id="dev-01",
                skills=[
                    ExternalSkillInventoryItem(
                        source="workspace-skill-root",
                        root_path_hash="root-hash",
                        slug="pdf-table-cleanup",
                        file_hash="file-hash",
                        name="PDF table cleanup",
                        description="External skill for repairing malformed PDF table cells.",
                    )
                ],
            )
        )
        list_response = await list_route.endpoint(workspace_id="dev-01")
        return upsert_response, list_response

    upsert_response, list_response = asyncio.run(run())

    assert upsert_response.created == 1
    assert upsert_response.updated == 0
    assert upsert_response.skills[0]["slug"] == "pdf-table-cleanup"
    assert list_response.skills[0]["source"] == "workspace-skill-root"
    assert store.upserts[0]["workspace_key"] == "dev-01"


def test_external_skill_review_action_api_records_operator_reuse_decision() -> None:
    store = MemoryExternalSkillStore()
    app = create_app(external_skill_store=store)
    upsert_route = next(route for route in app.routes if route.path == "/v1/external-skills/upsert")
    review_route = next(
        route for route in app.routes if route.path == "/v1/external-skills/review-actions"
    )

    async def run():
        upsert_response = await upsert_route.endpoint(
            request=ExternalSkillInventoryUpsertRequest(
                workspace_id="dev-01",
                skills=[
                    ExternalSkillInventoryItem(
                        source="workspace-skill-root",
                        root_path_hash="root-hash",
                        slug="pdf-table-cleanup",
                        file_hash="file-hash",
                        name="PDF table cleanup",
                        description="External skill for malformed PDF cells.",
                    )
                ],
            )
        )
        return await review_route.endpoint(
            request=ExternalSkillReviewActionRequest(
                workspace_id="dev-01",
                external_skill_id=uuid4()
                if not upsert_response.skills
                else store.records[0].external_skill_id,
                action="reuse",
                status="approved",
                operator_id="operator-1",
                rationale="Existing external skill is the correct owner.",
                metadata={"collision_risk": "high"},
            )
        )

    response = asyncio.run(run())

    assert response.review_action["action"] == "reuse"
    assert response.review_action["status"] == "approved"
    assert response.review_action["operator_id"] == "operator-1"
    assert response.review_action["metadata"] == {"collision_risk": "high"}
    assert store.review_actions[0].external_skill_id == store.records[0].external_skill_id


def test_external_skill_review_action_api_rejects_invalid_action() -> None:
    store = MemoryExternalSkillStore()
    app = create_app(external_skill_store=store)
    review_route = next(
        route for route in app.routes if route.path == "/v1/external-skills/review-actions"
    )

    async def run():
        return await review_route.endpoint(
            request=ExternalSkillReviewActionRequest(
                workspace_id="dev-01",
                external_skill_id=uuid4(),
                action="autonomous_import",
            )
        )

    try:
        asyncio.run(run())
    except Exception as error:
        raised = error
    else:  # pragma: no cover
        raise AssertionError("invalid external skill review action should fail")

    assert getattr(raised, "status_code", None) == 400
    assert "action must be one of" in str(getattr(raised, "detail", ""))


def test_external_skill_import_materialization_requires_operator_approval() -> None:
    store = MemoryExternalSkillStore()

    async def run():
        await store.upsert_external_skills(
            workspace_key="dev-01",
            skills=[
                ExternalSkillInput(
                    source="workspace-skill-root",
                    root_path_hash="root-hash",
                    slug="pdf-table-cleanup",
                    file_hash="file-hash",
                    name="PDF table cleanup",
                    description="External skill for malformed PDF cells.",
                    risk_summary={"scanner_status": "passed"},
                )
            ],
        )
        blocked = await materialize_external_skill_import(
            store,
            workspace_key="dev-01",
            external_skill_id=store.records[0].external_skill_id,
        )
        await store.record_review_action(
            workspace_key="dev-01",
            external_skill_id=store.records[0].external_skill_id,
            action="import",
            status="approved",
            operator_id="operator-1",
        )
        allowed = await materialize_external_skill_import(
            store,
            workspace_key="dev-01",
            external_skill_id=store.records[0].external_skill_id,
        )
        return blocked, allowed

    blocked, allowed = asyncio.run(run())

    assert blocked.allowed is False
    assert "requires approved operator review action" in blocked.blockers[0]
    assert allowed.allowed is True
    assert allowed.candidate["mode"] == "stage_only"
    assert allowed.candidate["mutates_external_root"] is False
    assert allowed.candidate["skill_ir"]["schema"] == "skillir.v1"
    assert allowed.candidate["skill_ir"]["slug"] == "external-pdf-table-cleanup"
    assert allowed.candidate["skill_ir"]["name"] == "external-pdf-table-cleanup"
    assert "use when" in allowed.candidate["skill_ir"]["description"]
    assert "not for" in allowed.candidate["skill_ir"]["description"]
    assert allowed.candidate["skill_ir"]["steps"]
    assert allowed.candidate["skill_ir"]["never"]
    assert allowed.candidate["external_source"]["external_skill_id"] == str(
        store.records[0].external_skill_id
    )
    assert allowed.candidate["external_source"]["root_path_hash"] == "root-hash"
    assert store.review_actions[-1].status == "completed"


def test_external_skill_scanner_hashes_roots_without_storing_paths(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    skill_dir = root / "pdf-table-cleanup"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: PDF table cleanup\n"
        "description: Repair malformed PDF table cells.\n"
        "---\n"
        "\n"
        "## WHEN\n"
        "- Tables are malformed.\n",
        encoding="utf-8",
    )
    store = MemoryExternalSkillStore()

    async def run():
        return await scan_external_skill_roots(
            store,
            workspace_key="dev-01",
            roots=[root],
            source="test-root",
        )

    result = asyncio.run(run())

    assert result.discovered == 1
    assert result.created == 1
    record = store.records[0]
    assert record.slug == "pdf-table-cleanup"
    assert record.name == "PDF table cleanup"
    assert record.description == "Repair malformed PDF table cells."
    assert record.status == "visible"
    assert record.risk_summary["scanner_status"] == "passed"
    assert record.risk_summary["stored_raw_root_path"] is False
    assert str(root) not in record.root_path_hash
    assert str(skill_dir) not in str(record.to_json())


def test_external_skill_scanner_quarantines_blocking_findings(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    skill_dir = root / "hidden-injection"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Hidden injection\n---\n<!-- hidden instruction -->\n",
        encoding="utf-8",
    )
    store = MemoryExternalSkillStore()

    async def run():
        return await scan_external_skill_roots(
            store,
            workspace_key="dev-01",
            roots=[root],
        )

    result = asyncio.run(run())

    assert result.discovered == 1
    assert store.records[0].status == "quarantined"
    assert store.records[0].risk_summary["scanner_status"] == "blocked"


def test_external_skill_schedule_default_does_not_store_raw_roots(tmp_path: Path) -> None:
    root = tmp_path / "external-skills"
    scheduler = MemoryScheduleStore()

    async def run():
        return await ensure_external_skill_scan_schedule(
            scheduler,
            workspace_key="dev-01",
            external_skill_roots=[root],
            interval_seconds=60,
            source="test-root",
        )

    result = asyncio.run(run())

    assert result is not None
    assert scheduler.upserts[0]["name"] == "external-skills.scan"
    assert scheduler.upserts[0]["job_kind"] == "external_skills.scan"
    assert scheduler.upserts[0]["interval_seconds"] == 300
    assert scheduler.upserts[0]["payload"] == {
        "workspace_id": "dev-01",
        "source": "test-root",
        "limit": 250,
    }
    assert str(root) not in str(scheduler.upserts[0])
