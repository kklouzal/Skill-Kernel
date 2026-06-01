import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from autoskill.api.app import WriterApplyRequest, WriterRollbackRequest, create_app
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.enums import TrustClass
from autoskill.core.events import EventEnvelope
from autoskill.services.writer import (
    PathContainmentError,
    WriterPolicyError,
    apply_staged_manifest,
    apply_staged_manifest_with_governance,
    resolve_contained,
    rollback_active_skill,
    rollback_active_skill_with_governance,
    stage_compiled_skill,
    stage_text,
    validate_support_artifact_path,
    verify_archive_manifest,
    verify_staged_manifest,
)


def test_event_redacted_sets_hash() -> None:
    event = EventEnvelope(
        workspace_id="workspace",
        event_type="tool_call_end",
        trust=TrustClass.TOOL_OUTPUT,
        payload={"token": "secret", "safe": "ok"},
    ).redacted()
    assert event.payload["token"] == "[REDACTED]"
    assert event.payload_hash


def test_audit_hash_chain_verifies() -> None:
    first = AuditRecord(action="create", subject_type="skill", subject_id="one").sealed()
    second = AuditRecord(
        action="activate",
        subject_type="skill",
        subject_id="one",
        previous_hash=first.audit_hash,
    ).sealed()
    assert verify_hash_chain([first, second])


def test_writer_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(PathContainmentError):
        resolve_contained(tmp_path, "../outside")


def test_writer_stages_text(tmp_path: Path) -> None:
    path = stage_text(tmp_path, "skills/example/SKILL.md", "hello")
    assert path.read_text(encoding="utf-8") == "hello"


def test_writer_stages_compiled_skill_with_manifest(tmp_path: Path) -> None:
    staging_id = uuid4()
    skill_version_id = uuid4()
    artifact = stage_compiled_skill(
        tmp_path,
        staging_id=staging_id,
        skill_version_id=skill_version_id,
        slug="autoskill-example",
        compiled_skill_md="# autoskill-example\n\n## WHEN\n- Repeated evidence exists.\n",
    )

    assert artifact.ok
    assert artifact.manifest_sha256
    assert artifact.files[0].target_relative_path == "skills/autoskill/autoskill-example/SKILL.md"
    manifest = verify_staged_manifest(tmp_path, artifact.manifest_relative_path)
    assert manifest["schema"] == "autoskill.writer-manifest.v1"
    assert manifest["staging_id"] == str(staging_id)
    assert manifest["skill_version_id"] == str(skill_version_id)
    assert manifest["files"][0]["sha256"] == artifact.files[0].sha256


def test_writer_rejects_blocked_compiled_skill(tmp_path: Path) -> None:
    with pytest.raises(WriterPolicyError):
        stage_compiled_skill(
            tmp_path,
            staging_id=uuid4(),
            skill_version_id=uuid4(),
            slug="autoskill-example",
            compiled_skill_md="<!-- hidden -->\n# autoskill-example\n",
        )


def test_writer_rejects_unsafe_support_artifact_paths() -> None:
    assert validate_support_artifact_path("scripts/safe-tool.py") == "scripts/safe-tool.py"
    assert validate_support_artifact_path("references/notes.md") == "references/notes.md"
    assert validate_support_artifact_path("assets/sample.json") == "assets/sample.json"
    with pytest.raises(WriterPolicyError):
        validate_support_artifact_path("../escape.py")
    with pytest.raises(WriterPolicyError):
        validate_support_artifact_path("scripts/fetcher.exe")


def test_writer_rejects_symlink_path(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "skills"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathContainmentError):
        stage_text(tmp_path, "skills/example/SKILL.md", "hello")


def test_writer_applies_staged_manifest_and_snapshots_previous_active(
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    workspace_root.mkdir()
    previous_active = workspace_root / "skills" / "autoskill" / "autoskill-example"
    previous_active.mkdir(parents=True)
    (previous_active / "SKILL.md").write_text("# Old\n\n## WHEN\n- Old.\n", encoding="utf-8")

    staging_id = uuid4()
    skill_version_id = uuid4()
    staged = stage_compiled_skill(
        staging_root,
        staging_id=staging_id,
        skill_version_id=skill_version_id,
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )

    applied = apply_staged_manifest(
        staging_root,
        workspace_root,
        archive_root,
        staged.manifest_relative_path,
    )

    assert applied.active_relative_path == "skills/autoskill/autoskill-example"
    assert applied.previous_snapshot is not None
    active_skill = previous_active / "SKILL.md"
    assert active_skill.read_text(encoding="utf-8").startswith("# New")
    archived_manifest = verify_archive_manifest(
        archive_root,
        applied.previous_snapshot.manifest_relative_path,
    )
    assert archived_manifest["schema"] == "autoskill.archive-manifest.v1"
    archived_skill = archive_root / applied.previous_snapshot.archive_relative_path / "SKILL.md"
    assert archived_skill.read_text(encoding="utf-8").startswith("# Old")


def test_writer_rolls_back_active_skill_from_archive_snapshot(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    workspace_root.mkdir()
    active_path = workspace_root / "skills" / "autoskill" / "autoskill-example"
    active_path.mkdir(parents=True)
    (active_path / "SKILL.md").write_text("# Old\n\n## WHEN\n- Old.\n", encoding="utf-8")
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )
    applied = apply_staged_manifest(
        staging_root,
        workspace_root,
        archive_root,
        staged.manifest_relative_path,
    )
    assert applied.previous_snapshot is not None

    rolled_back = rollback_active_skill(
        workspace_root,
        archive_root,
        archive_manifest_relative_path=applied.previous_snapshot.manifest_relative_path,
    )

    assert rolled_back.slug == "autoskill-example"
    assert (active_path / "SKILL.md").read_text(encoding="utf-8").startswith("# Old")


def test_writer_apply_records_governance_items(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    workspace_root.mkdir()
    active_path = workspace_root / "skills" / "autoskill" / "autoskill-example"
    active_path.mkdir(parents=True)
    (active_path / "SKILL.md").write_text("# Old\n\n## WHEN\n- Old.\n", encoding="utf-8")
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )
    governance = MemoryWriterGovernance()
    transaction_id = uuid4()

    async def run():
        return await apply_staged_manifest_with_governance(
            governance,
            evolution_transaction_id=transaction_id,
            staging_root=staging_root,
            workspace_root=workspace_root,
            archive_root=archive_root,
            manifest_relative_path=staged.manifest_relative_path,
        )

    applied = asyncio.run(run())

    assert applied.previous_snapshot is not None
    assert governance.statuses[-1]["status"] == "applied"
    assert governance.statuses[-1]["metrics"]["previous_snapshot"] == (
        applied.previous_snapshot.manifest_relative_path
    )
    assert [item["item_kind"] for item in governance.items] == [
        "compiled_skill_file",
        "archive_snapshot",
    ]
    assert governance.items[0]["activation_state"] == "active"
    assert governance.items[0]["relative_path"] == "skills/autoskill/autoskill-example"
    assert governance.items[0]["rollback_action"]["operation"] == "restore_archive_manifest"
    assert governance.items[1]["activation_state"] == "archived"


def test_writer_apply_restores_previous_active_if_governance_recording_fails(
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    workspace_root.mkdir()
    active_path = workspace_root / "skills" / "autoskill" / "autoskill-example"
    active_path.mkdir(parents=True)
    (active_path / "SKILL.md").write_text("# Old\n\n## WHEN\n- Old.\n", encoding="utf-8")
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )
    governance = MemoryWriterGovernance(fail_record_item=True)

    async def run():
        await apply_staged_manifest_with_governance(
            governance,
            evolution_transaction_id=uuid4(),
            staging_root=staging_root,
            workspace_root=workspace_root,
            archive_root=archive_root,
            manifest_relative_path=staged.manifest_relative_path,
        )

    with pytest.raises(RuntimeError, match="governance unavailable"):
        asyncio.run(run())

    assert (active_path / "SKILL.md").read_text(encoding="utf-8").startswith("# Old")
    assert governance.statuses[-1]["status"] == "failed"


def test_writer_rollback_records_governance_item(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    workspace_root.mkdir()
    active_path = workspace_root / "skills" / "autoskill" / "autoskill-example"
    active_path.mkdir(parents=True)
    (active_path / "SKILL.md").write_text("# Old\n\n## WHEN\n- Old.\n", encoding="utf-8")
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )
    applied = apply_staged_manifest(
        staging_root,
        workspace_root,
        archive_root,
        staged.manifest_relative_path,
    )
    assert applied.previous_snapshot is not None
    governance = MemoryWriterGovernance()

    async def run():
        return await rollback_active_skill_with_governance(
            governance,
            evolution_transaction_id=uuid4(),
            workspace_root=workspace_root,
            archive_root=archive_root,
            archive_manifest_relative_path=applied.previous_snapshot.manifest_relative_path,
        )

    rolled_back = asyncio.run(run())

    assert rolled_back.slug == "autoskill-example"
    assert governance.statuses[-1]["status"] == "rolled_back"
    assert governance.items[0]["activation_state"] == "rolled_back"
    assert governance.items[0]["rollback_action"]["operation"] == "operator_review"


def test_writer_api_applies_and_rolls_back_with_workspace_roots(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    staging_root = workspace_root / ".autoskill" / "staging"
    workspace_root.mkdir()
    active_path = workspace_root / "skills" / "autoskill" / "autoskill-example"
    active_path.mkdir(parents=True)
    (active_path / "SKILL.md").write_text("# Old\n\n## WHEN\n- Old.\n", encoding="utf-8")
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )
    governance = MemoryWriterGovernance()
    app = create_app(governance_store=governance, writer_workspace_root=workspace_root)
    apply_route = next(route for route in app.routes if route.path == "/v1/writer/apply")
    rollback_route = next(route for route in app.routes if route.path == "/v1/writer/rollback")

    async def run():
        applied = await apply_route.endpoint(
            request=WriterApplyRequest(
                evolution_transaction_id=uuid4(),
                manifest_relative_path=staged.manifest_relative_path,
            )
        )
        previous_snapshot = applied.artifact["previous_snapshot"]
        assert isinstance(previous_snapshot, dict)
        rolled_back = await rollback_route.endpoint(
            request=WriterRollbackRequest(
                evolution_transaction_id=uuid4(),
                archive_manifest_relative_path=str(
                    previous_snapshot["manifest_relative_path"]
                ),
            )
        )
        return applied, rolled_back

    applied, rolled_back = asyncio.run(run())

    assert applied.artifact["active_relative_path"] == "skills/autoskill/autoskill-example"
    assert rolled_back.artifact["slug"] == "autoskill-example"
    assert (active_path / "SKILL.md").read_text(encoding="utf-8").startswith("# Old")
    assert [entry["status"] for entry in governance.statuses] == [
        "applying",
        "applied",
        "rolling_back",
        "rolled_back",
    ]
    assert [item["activation_state"] for item in governance.items] == [
        "active",
        "archived",
        "rolled_back",
    ]


def test_writer_rejects_manifest_target_outside_active_root(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# Safe\n\n## WHEN\n- Safe.\n",
    )
    manifest_path = staging_root / staged.manifest_relative_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["target_relative_path"] = "skills/autoskill/other/SKILL.md"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with pytest.raises(WriterPolicyError):
        apply_staged_manifest(
            staging_root,
            workspace_root,
            archive_root,
            staged.manifest_relative_path,
        )


def test_writer_rejects_active_snapshot_symlink(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"
    workspace_root = tmp_path / "workspace"
    archive_root = workspace_root / ".autoskill" / "archive"
    active_path = workspace_root / "skills" / "autoskill" / "autoskill-example"
    active_path.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    (active_path / "SKILL.md").symlink_to(outside)
    staged = stage_compiled_skill(
        staging_root,
        staging_id=uuid4(),
        skill_version_id=uuid4(),
        slug="autoskill-example",
        compiled_skill_md="# New\n\n## WHEN\n- New.\n",
    )

    with pytest.raises(PathContainmentError):
        apply_staged_manifest(
            staging_root,
            workspace_root,
            archive_root,
            staged.manifest_relative_path,
        )


class MemoryWriterGovernance:
    def __init__(self, *, fail_record_item: bool = False) -> None:
        self.fail_record_item = fail_record_item
        self.statuses: list[dict[str, object]] = []
        self.items: list[dict[str, object]] = []

    async def update_transaction_status(
        self,
        *,
        evolution_transaction_id,
        status,
        metrics=None,
    ):
        self.statuses.append(
            {
                "evolution_transaction_id": evolution_transaction_id,
                "status": status,
                "metrics": metrics or {},
            }
        )

    async def record_transaction_item(
        self,
        *,
        evolution_transaction_id,
        item_kind,
        activation_state,
        item_id=None,
        relative_path=None,
        before_hash=None,
        after_hash=None,
        rollback_action=None,
    ):
        if self.fail_record_item:
            raise RuntimeError("governance unavailable")
        self.items.append(
            {
                "evolution_transaction_id": evolution_transaction_id,
                "item_kind": item_kind,
                "activation_state": activation_state,
                "item_id": item_id,
                "relative_path": relative_path,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "rollback_action": rollback_action or {},
            }
        )
