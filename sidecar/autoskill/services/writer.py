from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Any
from uuid import UUID

from autoskill.core.hashing import sha256_bytes, sha256_json, sha256_text
from autoskill.services.scanner import (
    ScannerFinding,
    has_blocking_findings,
    scan_text,
    scan_text_bundle,
)


class PathContainmentError(ValueError):
    pass


class WriterPolicyError(ValueError):
    pass


SAFE_SKILL_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
SAFE_SUPPORT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
ALLOWED_ASSET_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".json", ".png", ".txt", ".webp"}
DEFAULT_MAX_CONTEXT_TOKENS = 1200


@dataclass(frozen=True)
class StagedFile:
    role: str
    relative_path: str
    target_relative_path: str
    sha256: str
    bytes: int
    metadata: dict[str, object] = field(default_factory=dict)

    def to_manifest(self) -> dict[str, object]:
        entry: dict[str, object] = {
            "role": self.role,
            "relative_path": self.relative_path,
            "target_relative_path": self.target_relative_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }
        if self.metadata:
            entry["metadata"] = self.metadata
        return entry


@dataclass(frozen=True)
class SupportArtifactContent:
    relative_path: str
    content: str | bytes
    kind: str
    load_policy: str = "never_loaded"
    sha256: str | None = None
    max_tokens: int = 400


@dataclass(frozen=True)
class StagedSkillArtifact:
    staging_id: UUID
    skill_version_id: UUID
    slug: str
    root: Path
    manifest_relative_path: str
    manifest_sha256: str
    files: list[StagedFile]
    scanner_findings: list[ScannerFinding]
    context_gate: dict[str, object]

    @property
    def ok(self) -> bool:
        return not has_blocking_findings(self.scanner_findings)

    def to_manifest(self) -> dict[str, object]:
        return _writer_manifest(
            staging_id=self.staging_id,
            skill_version_id=self.skill_version_id,
            slug=self.slug,
            files=self.files,
            scanner_findings=self.scanner_findings,
            context_gate=self.context_gate,
        )


@dataclass(frozen=True)
class ArchiveSnapshot:
    slug: str
    archive_relative_path: str
    manifest_relative_path: str
    manifest_sha256: str
    files: list[StagedFile]


@dataclass(frozen=True)
class AppliedSkillArtifact:
    slug: str
    active_relative_path: str
    manifest_sha256: str
    files: list[StagedFile]
    previous_snapshot: ArchiveSnapshot | None

    def to_json(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "active_relative_path": self.active_relative_path,
            "manifest_sha256": self.manifest_sha256,
            "files": [file.to_manifest() for file in self.files],
            "previous_snapshot": (
                {
                    "archive_relative_path": self.previous_snapshot.archive_relative_path,
                    "manifest_relative_path": self.previous_snapshot.manifest_relative_path,
                    "manifest_sha256": self.previous_snapshot.manifest_sha256,
                    "files": [
                        file.to_manifest()
                        for file in self.previous_snapshot.files
                    ],
                }
                if self.previous_snapshot
                else None
            ),
        }


def resolve_contained(root: Path, relative_path: str) -> Path:
    if relative_path.startswith("/") or "\x00" in relative_path:
        raise PathContainmentError("path must be relative and non-null")
    root_resolved = root.resolve()
    target = (root_resolved / relative_path).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise PathContainmentError(f"path escapes root: {relative_path}")
    return target


def stage_text(root: Path, relative_path: str, content: str, *, overwrite: bool = False) -> Path:
    reject_symlink_path(root, relative_path)
    target = resolve_contained(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)
    return target


def reject_symlink_path(root: Path, relative_path: str) -> None:
    root_resolved = root.resolve()
    current = root_resolved
    for part in Path(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise PathContainmentError(f"symlink paths are forbidden: {relative_path}")


def validate_support_artifact_path(relative_path: str) -> str:
    path = Path(relative_path)
    parts = path.parts
    if len(parts) != 2:
        raise WriterPolicyError("support artifact path must be exactly one directory and one file")
    directory, filename = parts
    if directory not in {"scripts", "references", "assets"}:
        raise WriterPolicyError("support artifact directory is not allowed")
    if not SAFE_SUPPORT_NAME.fullmatch(filename):
        raise WriterPolicyError("support artifact filename is not safe")
    suffix = Path(filename).suffix.lower()
    if directory == "scripts" and suffix not in {".py", ".sh"}:
        raise WriterPolicyError("script artifacts must be .py or .sh")
    if directory == "references" and suffix != ".md":
        raise WriterPolicyError("reference artifacts must be .md")
    if directory == "assets" and suffix not in ALLOWED_ASSET_EXTENSIONS:
        raise WriterPolicyError("asset extension is not allowed")
    return f"{directory}/{filename}"


def stage_compiled_skill(
    root: Path,
    *,
    staging_id: UUID,
    skill_version_id: UUID,
    slug: str,
    compiled_skill_md: str,
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    context_compile_run_id: UUID | None = None,
    context_artifact_id: UUID | None = None,
    context_output_manifest_hash: str | None = None,
    support_artifacts: list[SupportArtifactContent] | None = None,
    overwrite: bool = False,
) -> StagedSkillArtifact:
    """Stage a scanned runtime SKILL.md and manifest without activating it."""

    if not SAFE_SKILL_SLUG.fullmatch(slug):
        raise WriterPolicyError("skill slug is not a safe autoskill slug")
    scanner_findings = scan_text(compiled_skill_md)
    if has_blocking_findings(scanner_findings):
        raise WriterPolicyError("compiled skill has blocking scanner findings")
    context_gate = _context_gate(
        text=compiled_skill_md,
        max_context_tokens=max_context_tokens,
        scanner_findings=scanner_findings,
        context_compile_run_id=context_compile_run_id,
        context_artifact_id=context_artifact_id,
        context_output_manifest_hash=context_output_manifest_hash,
    )
    if context_gate["budget_status"] != "passed":
        raise WriterPolicyError("compiled skill exceeds context token budget")
    staged_support_files = _stage_support_artifacts(
        root,
        staging_id=staging_id,
        slug=slug,
        compiled_skill_md=compiled_skill_md,
        artifacts=support_artifacts or [],
        overwrite=overwrite,
    )

    skill_relative_path = f"{staging_id}/{slug}/SKILL.md"
    target_relative_path = f"skills/autoskill/{slug}/SKILL.md"
    stage_text(root, skill_relative_path, compiled_skill_md, overwrite=overwrite)
    staged_file = StagedFile(
        role="runtime_skill",
        relative_path=skill_relative_path,
        target_relative_path=target_relative_path,
        sha256=sha256_text(compiled_skill_md),
        bytes=len(compiled_skill_md.encode("utf-8")),
        metadata={
            "loadability_class": "runtime_skill_body",
            "artifact_kind": "skill_md",
        },
    )
    files = [staged_file, *staged_support_files]
    manifest = _writer_manifest(
        staging_id=staging_id,
        skill_version_id=skill_version_id,
        slug=slug,
        files=files,
        scanner_findings=scanner_findings,
        context_gate=context_gate,
    )
    manifest_relative_path = f"{staging_id}/{slug}/autoskill.manifest.json"
    manifest_text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    stage_text(root, manifest_relative_path, manifest_text, overwrite=overwrite)
    return StagedSkillArtifact(
        staging_id=staging_id,
        skill_version_id=skill_version_id,
        slug=slug,
        root=root,
        manifest_relative_path=manifest_relative_path,
        manifest_sha256=sha256_json(manifest),
        files=files,
        scanner_findings=scanner_findings,
        context_gate=context_gate,
    )


def verify_staged_manifest(root: Path, manifest_relative_path: str) -> dict[str, object]:
    manifest_path = resolve_contained(root, manifest_relative_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("files", []):
        relative_path = entry["relative_path"]
        path = resolve_contained(root, relative_path)
        digest = sha256_bytes(path.read_bytes())
        if digest != entry["sha256"]:
            raise WriterPolicyError(f"staged file hash mismatch: {relative_path}")
    return manifest


def apply_staged_manifest(
    staging_root: Path,
    workspace_root: Path,
    archive_root: Path,
    manifest_relative_path: str,
) -> AppliedSkillArtifact:
    """Atomically replace one active autoskill directory from a verified manifest."""

    manifest = verify_staged_manifest(staging_root, manifest_relative_path)
    _validate_manifest_for_apply(manifest)
    slug = str(manifest["slug"])
    staging_id = str(manifest["staging_id"])
    active_relative_path = f"skills/autoskill/{slug}"
    active_path = resolve_contained(workspace_root, active_relative_path)
    apply_tmp_root = resolve_contained(
        workspace_root,
        f".autoskill/apply-tmp/{staging_id}/{slug}",
    )
    previous_tmp_path = resolve_contained(
        workspace_root,
        f".autoskill/apply-tmp/{staging_id}/{slug}.previous",
    )
    _remove_path(apply_tmp_root)
    _remove_path(previous_tmp_path)
    apply_tmp_root.mkdir(parents=True, exist_ok=True)

    staged_files = [
        StagedFile(
            role=str(entry["role"]),
            relative_path=str(entry["relative_path"]),
            target_relative_path=str(entry["target_relative_path"]),
            sha256=str(entry["sha256"]),
            bytes=int(entry["bytes"]),
            metadata=dict(entry.get("metadata") or {}),
        )
        for entry in manifest["files"]
    ]
    for file in staged_files:
        source = resolve_contained(staging_root, file.relative_path)
        target_inside_skill = _target_path_inside_skill(slug, file.target_relative_path)
        reject_symlink_path(apply_tmp_root, target_inside_skill)
        destination = resolve_contained(apply_tmp_root, target_inside_skill)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    _verify_snapshot_files(apply_tmp_root, staged_files, slug=slug)
    previous_snapshot = None
    if active_path.exists():
        previous_snapshot = archive_active_skill(
            workspace_root,
            archive_root,
            slug=slug,
            snapshot_id=staging_id,
        )
        active_path.replace(previous_tmp_path)

    try:
        active_path.parent.mkdir(parents=True, exist_ok=True)
        apply_tmp_root.replace(active_path)
    except Exception:
        if previous_tmp_path.exists() and not active_path.exists():
            previous_tmp_path.replace(active_path)
        raise
    finally:
        _remove_path(previous_tmp_path)
        _remove_path(apply_tmp_root.parent)

    _verify_snapshot_files(active_path, staged_files, slug=slug)
    return AppliedSkillArtifact(
        slug=slug,
        active_relative_path=active_relative_path,
        manifest_sha256=sha256_json(manifest),
        files=staged_files,
        previous_snapshot=previous_snapshot,
    )


def archive_active_skill(
    workspace_root: Path,
    archive_root: Path,
    *,
    slug: str,
    snapshot_id: str,
) -> ArchiveSnapshot | None:
    if not SAFE_SKILL_SLUG.fullmatch(slug):
        raise WriterPolicyError("skill slug is not a safe autoskill slug")
    if not SAFE_SUPPORT_NAME.fullmatch(snapshot_id):
        raise WriterPolicyError("snapshot id is not safe")

    active_path = resolve_contained(workspace_root, f"skills/autoskill/{slug}")
    if not active_path.exists():
        return None
    if not active_path.is_dir():
        raise WriterPolicyError("active skill path is not a directory")
    reject_symlink_path(workspace_root, f"skills/autoskill/{slug}")

    snapshot_relative_path = f"{slug}/{snapshot_id}"
    snapshot_path = resolve_contained(archive_root, snapshot_relative_path)
    if snapshot_path.exists():
        raise FileExistsError(snapshot_path)
    snapshot_path.mkdir(parents=True, exist_ok=True)

    files: list[StagedFile] = []
    for path in sorted(active_path.rglob("*")):
        if path.is_symlink():
            raise PathContainmentError("active skill snapshots cannot contain symlinks")
        if not path.is_file():
            continue
        source = path
        relative_inside_skill = source.relative_to(active_path).as_posix()
        validate_active_skill_relative_path(relative_inside_skill)
        destination = resolve_contained(snapshot_path, relative_inside_skill)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        content = source.read_bytes()
        files.append(
            StagedFile(
                role="archive_snapshot",
                relative_path=relative_inside_skill,
                target_relative_path=f"skills/autoskill/{slug}/{relative_inside_skill}",
                sha256=sha256_bytes(content),
                bytes=len(content),
                metadata=_archive_file_metadata(relative_inside_skill),
            )
        )

    manifest = _archive_manifest(slug=slug, snapshot_id=snapshot_id, files=files)
    manifest_relative_path = f"{snapshot_relative_path}/autoskill.archive-manifest.json"
    manifest_text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    stage_text(archive_root, manifest_relative_path, manifest_text, overwrite=False)
    return ArchiveSnapshot(
        slug=slug,
        archive_relative_path=snapshot_relative_path,
        manifest_relative_path=manifest_relative_path,
        manifest_sha256=sha256_json(manifest),
        files=files,
    )


def rollback_active_skill(
    workspace_root: Path,
    archive_root: Path,
    *,
    archive_manifest_relative_path: str,
) -> AppliedSkillArtifact:
    manifest = verify_archive_manifest(archive_root, archive_manifest_relative_path)
    slug = str(manifest["slug"])
    active_relative_path = f"skills/autoskill/{slug}"
    active_path = resolve_contained(workspace_root, active_relative_path)
    staging_tmp_path = resolve_contained(
        workspace_root,
        f".autoskill/rollback-tmp/{manifest['snapshot_id']}/{slug}",
    )
    previous_tmp_path = resolve_contained(
        workspace_root,
        f".autoskill/rollback-tmp/{manifest['snapshot_id']}/{slug}.previous",
    )
    _remove_path(staging_tmp_path)
    _remove_path(previous_tmp_path)
    staging_tmp_path.mkdir(parents=True, exist_ok=True)

    files = [
        StagedFile(
            role=str(entry["role"]),
            relative_path=str(entry["relative_path"]),
            target_relative_path=str(entry["target_relative_path"]),
            sha256=str(entry["sha256"]),
            bytes=int(entry["bytes"]),
            metadata=dict(entry.get("metadata") or {}),
        )
        for entry in manifest["files"]
    ]
    snapshot_root = resolve_contained(
        archive_root,
        str(Path(archive_manifest_relative_path).parent),
    )
    for file in files:
        validate_active_skill_relative_path(file.relative_path)
        source = resolve_contained(snapshot_root, file.relative_path)
        destination = resolve_contained(staging_tmp_path, file.relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    _verify_snapshot_files(staging_tmp_path, files, slug=slug)

    if active_path.exists():
        active_path.replace(previous_tmp_path)
    try:
        active_path.parent.mkdir(parents=True, exist_ok=True)
        staging_tmp_path.replace(active_path)
    except Exception:
        if previous_tmp_path.exists() and not active_path.exists():
            previous_tmp_path.replace(active_path)
        raise
    finally:
        _remove_path(previous_tmp_path)
        _remove_path(staging_tmp_path.parent)

    _verify_snapshot_files(active_path, files, slug=slug)
    return AppliedSkillArtifact(
        slug=slug,
        active_relative_path=active_relative_path,
        manifest_sha256=sha256_json(manifest),
        files=files,
        previous_snapshot=None,
    )


async def apply_staged_manifest_with_governance(
    governance: Any,
    *,
    evolution_transaction_id: UUID,
    staging_root: Path,
    workspace_root: Path,
    archive_root: Path,
    manifest_relative_path: str,
) -> AppliedSkillArtifact:
    """Apply a staged manifest and record rollback-aware transaction items.

    The filesystem writer remains deterministic authority. If governance
    recording fails after the replace, the wrapper restores the previous active
    snapshot, or removes the newly-created active skill when no previous version
    existed, so apply is fail-closed instead of leaving untracked exposure.
    """

    applying_transaction = await governance.update_transaction_status(
        evolution_transaction_id=evolution_transaction_id,
        status="applying",
        metrics={"manifest_relative_path": manifest_relative_path},
    )
    workspace_key = _transaction_workspace_key(applying_transaction)
    applied = apply_staged_manifest(
        staging_root,
        workspace_root,
        archive_root,
        manifest_relative_path,
    )
    try:
        items = await _record_apply_transaction_items(
            governance,
            evolution_transaction_id=evolution_transaction_id,
            applied=applied,
        )
        await _record_writer_item_provenance(
            governance,
            workspace_key=workspace_key,
            evolution_transaction_id=evolution_transaction_id,
            items=items,
            relation="derived_from",
        )
        await governance.update_transaction_status(
            evolution_transaction_id=evolution_transaction_id,
            status="applied",
            metrics=_writer_metrics(applied),
        )
    except Exception:
        _recover_failed_governance_apply(
            workspace_root=workspace_root,
            archive_root=archive_root,
            applied=applied,
        )
        await governance.update_transaction_status(
            evolution_transaction_id=evolution_transaction_id,
            status="failed",
            metrics={
                "failed_stage": "governance_recording",
                "recovered_active_path": applied.active_relative_path,
            },
        )
        raise
    return applied


async def rollback_active_skill_with_governance(
    governance: Any,
    *,
    evolution_transaction_id: UUID,
    workspace_root: Path,
    archive_root: Path,
    archive_manifest_relative_path: str,
) -> AppliedSkillArtifact:
    """Restore an archive snapshot and record the rollback transaction item."""

    rolling_back_transaction = await governance.update_transaction_status(
        evolution_transaction_id=evolution_transaction_id,
        status="rolling_back",
        metrics={"archive_manifest_relative_path": archive_manifest_relative_path},
    )
    workspace_key = _transaction_workspace_key(rolling_back_transaction)
    rolled_back = rollback_active_skill(
        workspace_root,
        archive_root,
        archive_manifest_relative_path=archive_manifest_relative_path,
    )
    item = await governance.record_transaction_item(
        evolution_transaction_id=evolution_transaction_id,
        item_kind="compiled_skill_file",
        activation_state="rolled_back",
        relative_path=rolled_back.active_relative_path,
        before_hash=None,
        after_hash=rolled_back.manifest_sha256,
        rollback_action={
            "operation": "operator_review",
            "reason": "rollback transaction restored this archive snapshot",
        },
    )
    support_items = []
    for file in rolled_back.files:
        relative_inside_skill = _target_path_inside_skill(
            rolled_back.slug,
            file.target_relative_path,
        )
        if relative_inside_skill == "SKILL.md":
            continue
        support_items.append(
            await governance.record_transaction_item(
                evolution_transaction_id=evolution_transaction_id,
                item_kind="support_artifact",
                activation_state="rolled_back",
                relative_path=file.target_relative_path,
                before_hash=None,
                after_hash=file.sha256,
                rollback_action={
                    "operation": "operator_review",
                    "reason": "rollback transaction restored this support artifact",
                },
            )
        )
    await _record_writer_item_provenance(
        governance,
        workspace_key=workspace_key,
        evolution_transaction_id=evolution_transaction_id,
        items=[item, *support_items],
        relation="rolled_back_by",
    )
    await governance.update_transaction_status(
        evolution_transaction_id=evolution_transaction_id,
        status="rolled_back",
        metrics=_writer_metrics(rolled_back),
    )
    return rolled_back


async def delete_active_skill_with_governance(
    governance: Any,
    *,
    evolution_transaction_id: UUID,
    workspace_root: Path,
    active_relative_path: str,
) -> dict[str, Any]:
    """Delete a newly-created active skill path and record the rollback transaction item."""

    rolling_back_transaction = await governance.update_transaction_status(
        evolution_transaction_id=evolution_transaction_id,
        status="rolling_back",
        metrics={"active_relative_path": active_relative_path},
    )
    workspace_key = _transaction_workspace_key(rolling_back_transaction)
    active_path = resolve_contained(workspace_root, active_relative_path)
    if active_path != (workspace_root.resolve() / active_relative_path).resolve():
        raise PathContainmentError("active path failed containment check")
    _remove_path(active_path)
    item = await governance.record_transaction_item(
        evolution_transaction_id=evolution_transaction_id,
        item_kind="compiled_skill_file",
        activation_state="rolled_back",
        relative_path=active_relative_path,
        before_hash=None,
        after_hash=None,
        rollback_action={
            "operation": "operator_review",
            "reason": "rollback transaction deleted initial active path",
        },
    )
    await _record_writer_item_provenance(
        governance,
        workspace_key=workspace_key,
        evolution_transaction_id=evolution_transaction_id,
        items=[item],
        relation="rolled_back_by",
    )
    await governance.update_transaction_status(
        evolution_transaction_id=evolution_transaction_id,
        status="rolled_back",
        metrics={"active_relative_path": active_relative_path, "operation": "delete_active_path"},
    )
    return {
        "active_relative_path": active_relative_path,
        "operation": "delete_active_path",
    }


def verify_archive_manifest(root: Path, manifest_relative_path: str) -> dict[str, object]:
    manifest_path = resolve_contained(root, manifest_relative_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "autoskill.archive-manifest.v1":
        raise WriterPolicyError("unsupported archive manifest schema")
    slug = str(manifest.get("slug", ""))
    if not SAFE_SKILL_SLUG.fullmatch(slug):
        raise WriterPolicyError("archive manifest slug is not safe")
    snapshot_root = manifest_path.parent
    for entry in manifest.get("files", []):
        relative_path = str(entry["relative_path"])
        validate_active_skill_relative_path(relative_path)
        _target_path_inside_skill(slug, str(entry["target_relative_path"]))
        path = resolve_contained(snapshot_root, relative_path)
        digest = sha256_bytes(path.read_bytes())
        if digest != entry["sha256"]:
            raise WriterPolicyError(f"archive file hash mismatch: {relative_path}")
    return manifest


def validate_active_skill_relative_path(relative_path: str) -> str:
    if relative_path == "SKILL.md":
        return relative_path
    return validate_support_artifact_path(relative_path)


def _stage_support_artifacts(
    root: Path,
    *,
    staging_id: UUID,
    slug: str,
    compiled_skill_md: str,
    artifacts: list[SupportArtifactContent],
    overwrite: bool,
) -> list[StagedFile]:
    if not artifacts:
        return []
    co_loadable_texts = [compiled_skill_md]
    staged_files: list[StagedFile] = []
    seen_paths: set[str] = set()
    for artifact in artifacts:
        relative_inside_skill = validate_support_artifact_path(artifact.relative_path)
        if relative_inside_skill in seen_paths:
            raise WriterPolicyError("duplicate support artifact path")
        seen_paths.add(relative_inside_skill)
        content_bytes, text = _support_artifact_bytes_and_text(artifact.content)
        digest = sha256_bytes(content_bytes)
        if artifact.sha256 is not None and artifact.sha256 != digest:
            raise WriterPolicyError("support artifact hash mismatch")
        metadata = _support_artifact_metadata(
            relative_inside_skill=relative_inside_skill,
            artifact=artifact,
            content_bytes=content_bytes,
            text=text,
        )
        if metadata["safety_status"] != "passed":
            raise WriterPolicyError("support artifact has blocking scanner findings")
        if metadata["budget_status"] != "passed":
            raise WriterPolicyError("support artifact exceeds context token budget")
        if artifact.load_policy in {"agent_may_read", "broker_excerpt_only"} and text:
            co_loadable_texts.append(text)

        staged_relative_path = f"{staging_id}/{slug}/{relative_inside_skill}"
        target_relative_path = f"skills/autoskill/{slug}/{relative_inside_skill}"
        _stage_bytes(root, staged_relative_path, content_bytes, overwrite=overwrite)
        staged_files.append(
            StagedFile(
                role="support_artifact",
                relative_path=staged_relative_path,
                target_relative_path=target_relative_path,
                sha256=digest,
                bytes=len(content_bytes),
                metadata=metadata,
            )
        )

    bundle_findings = scan_text_bundle(co_loadable_texts)
    if has_blocking_findings(bundle_findings):
        raise WriterPolicyError("support artifact bundle has blocking scanner findings")
    return staged_files


def _stage_bytes(
    root: Path,
    relative_path: str,
    content: bytes,
    *,
    overwrite: bool = False,
) -> Path:
    reject_symlink_path(root, relative_path)
    target = resolve_contained(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_bytes(content)
    tmp.replace(target)
    return target


def _support_artifact_bytes_and_text(content: str | bytes) -> tuple[bytes, str | None]:
    if isinstance(content, str):
        return content.encode("utf-8"), content
    try:
        return content, content.decode("utf-8")
    except UnicodeDecodeError:
        return content, None


def _support_artifact_metadata(
    *,
    relative_inside_skill: str,
    artifact: SupportArtifactContent,
    content_bytes: bytes,
    text: str | None,
) -> dict[str, object]:
    if artifact.load_policy not in {
        "never_loaded",
        "agent_may_read",
        "broker_excerpt_only",
        "script_only",
        "probe_only",
        "operator_only",
    }:
        raise WriterPolicyError("unsupported support artifact load policy")
    if artifact.kind not in {"script", "template", "fixture", "manifest", "asset"}:
        raise WriterPolicyError("unsupported support artifact kind")
    token_count = _estimate_tokens(text or "") if text else 0
    findings = scan_text(text or "") if text is not None else []
    safety_status = "blocked" if has_blocking_findings(findings) else "passed"
    max_tokens = max(0, artifact.max_tokens)
    budget_status = "passed" if token_count <= max_tokens else "over_budget"
    return {
        "artifact_kind": "support_artifact",
        "support_kind": artifact.kind,
        "loadability_class": f"support_artifact:{artifact.load_policy}",
        "load_policy": artifact.load_policy,
        "relative_path": relative_inside_skill,
        "content_hash": sha256_bytes(content_bytes),
        "token_count": token_count,
        "max_tokens": max_tokens,
        "safety_status": safety_status,
        "budget_status": budget_status,
        "scanner_codes": [finding.code for finding in findings],
    }


def _archive_file_metadata(relative_inside_skill: str) -> dict[str, object]:
    if relative_inside_skill == "SKILL.md":
        return {
            "artifact_kind": "skill_md",
            "loadability_class": "runtime_skill_body",
        }
    return {
        "artifact_kind": "support_artifact",
        "loadability_class": "support_artifact:archived",
        "relative_path": relative_inside_skill,
    }


def _writer_manifest(
    *,
    staging_id: UUID,
    skill_version_id: UUID,
    slug: str,
    files: list[StagedFile],
    scanner_findings: list[ScannerFinding],
    context_gate: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema": "autoskill.writer-manifest.v1",
        "staging_id": str(staging_id),
        "skill_version_id": str(skill_version_id),
        "slug": slug,
        "context_gate": context_gate or {},
        "files": [file.to_manifest() for file in files],
        "scanner_findings": [
            {
                "severity": str(finding.severity),
                "code": finding.code,
                "message": finding.message,
            }
            for finding in scanner_findings
        ],
    }


def _archive_manifest(*, slug: str, snapshot_id: str, files: list[StagedFile]) -> dict[str, object]:
    return {
        "schema": "autoskill.archive-manifest.v1",
        "slug": slug,
        "snapshot_id": snapshot_id,
        "files": [file.to_manifest() for file in files],
    }


def _validate_manifest_for_apply(manifest: dict[str, object]) -> None:
    if manifest.get("schema") != "autoskill.writer-manifest.v1":
        raise WriterPolicyError("unsupported writer manifest schema")
    slug = str(manifest.get("slug", ""))
    if not SAFE_SKILL_SLUG.fullmatch(slug):
        raise WriterPolicyError("manifest skill slug is not safe")
    if manifest.get("scanner_findings"):
        for finding in manifest["scanner_findings"]:  # type: ignore[index]
            if str(finding.get("severity")) in {"error", "critical"}:
                raise WriterPolicyError("manifest contains blocking scanner findings")
    _validate_context_gate(manifest)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise WriterPolicyError("writer manifest must contain files")
    for entry in files:
        target_relative_path = str(entry["target_relative_path"])
        relative_inside_skill = _target_path_inside_skill(slug, target_relative_path)
        role = str(entry.get("role") or "")
        metadata = entry.get("metadata") or {}
        if role == "runtime_skill":
            if relative_inside_skill != "SKILL.md":
                raise WriterPolicyError("runtime skill file must target SKILL.md")
        elif role == "support_artifact":
            _validate_support_artifact_manifest_metadata(
                relative_inside_skill,
                metadata if isinstance(metadata, dict) else {},
            )
        elif role != "archive_snapshot":
            raise WriterPolicyError("unsupported writer manifest file role")


def _context_gate(
    *,
    text: str,
    max_context_tokens: int,
    scanner_findings: list[ScannerFinding],
    context_compile_run_id: UUID | None = None,
    context_artifact_id: UUID | None = None,
    context_output_manifest_hash: str | None = None,
) -> dict[str, object]:
    token_count = _estimate_tokens(text)
    safety_status = "blocked" if has_blocking_findings(scanner_findings) else "passed"
    gate: dict[str, object] = {
        "loadability_class": "runtime_skill_body",
        "artifact_kind": "skill_md",
        "text_hash": sha256_text(text),
        "token_count": token_count,
        "max_tokens": max(1, max_context_tokens),
        "safety_status": safety_status,
        "equivalence_status": "passed",
        "budget_status": "passed" if token_count <= max(1, max_context_tokens) else "over_budget",
        "scanner_codes": [finding.code for finding in scanner_findings],
    }
    if context_compile_run_id is not None:
        gate["context_compile_run_id"] = str(context_compile_run_id)
    if context_artifact_id is not None:
        gate["context_artifact_id"] = str(context_artifact_id)
    if context_output_manifest_hash is not None:
        gate["context_output_manifest_hash"] = context_output_manifest_hash
    return gate


def _validate_context_gate(manifest: dict[str, object]) -> None:
    context_gate = manifest.get("context_gate")
    if not isinstance(context_gate, dict):
        raise WriterPolicyError("writer manifest is missing context gate")
    if context_gate.get("loadability_class") != "runtime_skill_body":
        raise WriterPolicyError("compiled skill lacks runtime loadability class")
    if context_gate.get("artifact_kind") != "skill_md":
        raise WriterPolicyError("compiled skill context artifact kind must be skill_md")
    for key in ("text_hash", "token_count", "max_tokens"):
        if key not in context_gate:
            raise WriterPolicyError(f"compiled skill context gate missing {key}")
    for status_key in ("safety_status", "equivalence_status", "budget_status"):
        if context_gate.get(status_key) != "passed":
            raise WriterPolicyError(f"compiled skill context gate failed {status_key}")
    token_count = int(context_gate["token_count"])
    max_tokens = int(context_gate["max_tokens"])
    if token_count <= 0 or max_tokens <= 0 or token_count > max_tokens:
        raise WriterPolicyError("compiled skill context token budget failed")


def _validate_support_artifact_manifest_metadata(
    relative_inside_skill: str,
    metadata: dict[str, object],
) -> None:
    if metadata.get("artifact_kind") != "support_artifact":
        raise WriterPolicyError("support artifact manifest lacks artifact kind")
    if not str(metadata.get("loadability_class") or "").startswith("support_artifact:"):
        raise WriterPolicyError("support artifact manifest lacks loadability class")
    if metadata.get("relative_path") != relative_inside_skill:
        raise WriterPolicyError("support artifact metadata path mismatch")
    if metadata.get("safety_status") != "passed":
        raise WriterPolicyError("support artifact safety gate failed")
    if metadata.get("budget_status") != "passed":
        raise WriterPolicyError("support artifact budget gate failed")
    for key in ("content_hash", "token_count", "max_tokens"):
        if key not in metadata:
            raise WriterPolicyError(f"support artifact metadata missing {key}")


def _estimate_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4))


def _target_path_inside_skill(slug: str, target_relative_path: str) -> str:
    prefix = f"skills/autoskill/{slug}/"
    if not target_relative_path.startswith(prefix):
        raise WriterPolicyError("target path must be under the autoskill active root")
    inside_skill = target_relative_path.removeprefix(prefix)
    return validate_active_skill_relative_path(inside_skill)


def _verify_snapshot_files(root: Path, files: list[StagedFile], *, slug: str) -> None:
    for file in files:
        relative_path = _target_path_inside_skill(slug, file.target_relative_path)
        path = resolve_contained(root, relative_path)
        digest = sha256_bytes(path.read_bytes())
        if digest != file.sha256:
            raise WriterPolicyError(f"active file hash mismatch: {relative_path}")


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


async def _record_apply_transaction_items(
    governance: Any,
    *,
    evolution_transaction_id: UUID,
    applied: AppliedSkillArtifact,
) -> list[Any]:
    items: list[Any] = []
    active_item = await governance.record_transaction_item(
        evolution_transaction_id=evolution_transaction_id,
        item_kind="compiled_skill_file",
        activation_state="active",
        relative_path=applied.active_relative_path,
        before_hash=(
            applied.previous_snapshot.manifest_sha256 if applied.previous_snapshot else None
        ),
        after_hash=applied.manifest_sha256,
        rollback_action=_apply_rollback_action(applied),
    )
    items.append(active_item)
    for file in applied.files:
        relative_inside_skill = _target_path_inside_skill(applied.slug, file.target_relative_path)
        if relative_inside_skill == "SKILL.md":
            continue
        support_item = await governance.record_transaction_item(
            evolution_transaction_id=evolution_transaction_id,
            item_kind="support_artifact",
            activation_state="active",
            relative_path=file.target_relative_path,
            before_hash=None,
            after_hash=file.sha256,
            rollback_action=_apply_rollback_action(applied),
        )
        items.append(support_item)
    if applied.previous_snapshot is not None:
        archive_item = await governance.record_transaction_item(
            evolution_transaction_id=evolution_transaction_id,
            item_kind="archive_snapshot",
            activation_state="archived",
            relative_path=(
                f".autoskill/archive/{applied.previous_snapshot.manifest_relative_path}"
            ),
            before_hash=None,
            after_hash=applied.previous_snapshot.manifest_sha256,
            rollback_action={
                "operation": "retain",
                "reason": "archive snapshot is required for rollback traversal",
            },
        )
        items.append(archive_item)
    return items


async def _record_writer_item_provenance(
    governance: Any,
    *,
    workspace_key: str | None,
    evolution_transaction_id: UUID,
    items: list[Any],
    relation: str,
) -> None:
    if workspace_key is None:
        return
    record_edge = getattr(governance, "record_provenance_edge", None)
    if record_edge is None:
        return
    for item in items:
        item_id = _transaction_item_id(item)
        if item_id is None:
            continue
        await record_edge(
            workspace_key=workspace_key,
            source_kind="evolution_transaction",
            source_id=evolution_transaction_id,
            derived_kind="transaction_item",
            derived_id=item_id,
            relation=relation,
        )


def _transaction_workspace_key(transaction: Any) -> str | None:
    if transaction is None:
        return None
    if isinstance(transaction, dict):
        value = transaction.get("workspace_key")
    else:
        value = getattr(transaction, "workspace_key", None)
    return value if isinstance(value, str) and value else None


def _transaction_item_id(item: Any) -> UUID | None:
    if item is None:
        return None
    if isinstance(item, dict):
        value = item.get("transaction_item_id")
    else:
        value = getattr(item, "transaction_item_id", None)
    return value if isinstance(value, UUID) else None


def _apply_rollback_action(applied: AppliedSkillArtifact) -> dict[str, object]:
    if applied.previous_snapshot is None:
        return {
            "operation": "delete_active_path",
            "active_relative_path": applied.active_relative_path,
        }
    return {
        "operation": "restore_archive_manifest",
        "archive_manifest_relative_path": applied.previous_snapshot.manifest_relative_path,
        "archive_manifest_sha256": applied.previous_snapshot.manifest_sha256,
        "active_relative_path": applied.active_relative_path,
    }


def _recover_failed_governance_apply(
    *,
    workspace_root: Path,
    archive_root: Path,
    applied: AppliedSkillArtifact,
) -> None:
    if applied.previous_snapshot is None:
        _remove_path(resolve_contained(workspace_root, applied.active_relative_path))
        return
    rollback_active_skill(
        workspace_root,
        archive_root,
        archive_manifest_relative_path=applied.previous_snapshot.manifest_relative_path,
    )


def _writer_metrics(applied: AppliedSkillArtifact) -> dict[str, Any]:
    return {
        "slug": applied.slug,
        "active_relative_path": applied.active_relative_path,
        "manifest_sha256": applied.manifest_sha256,
        "file_count": len(applied.files),
        "previous_snapshot": (
            applied.previous_snapshot.manifest_relative_path
            if applied.previous_snapshot
            else None
        ),
    }
