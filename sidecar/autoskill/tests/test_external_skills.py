import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from autoskill.api.app import (
    ExternalSkillInventoryItem,
    ExternalSkillInventoryUpsertRequest,
    create_app,
)
from autoskill.db.external_skills import (
    ExternalSkillInput,
    ExternalSkillRecord,
    ExternalSkillUpsertResult,
)
from autoskill.services.external_inventory import scan_external_skill_roots


class MemoryExternalSkillStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.records: list[ExternalSkillRecord] = []

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
