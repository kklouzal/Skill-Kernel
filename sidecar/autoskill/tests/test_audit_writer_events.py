from pathlib import Path
from uuid import uuid4

import pytest
from autoskill.core.audit import AuditRecord, verify_hash_chain
from autoskill.core.enums import TrustClass
from autoskill.core.events import EventEnvelope
from autoskill.services.writer import (
    PathContainmentError,
    WriterPolicyError,
    resolve_contained,
    stage_compiled_skill,
    stage_text,
    validate_support_artifact_path,
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
