from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from autoskill.core.hashing import sha256_bytes, sha256_json, sha256_text
from autoskill.services.scanner import ScannerFinding, has_blocking_findings, scan_text


class PathContainmentError(ValueError):
    pass


class WriterPolicyError(ValueError):
    pass


SAFE_SKILL_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
SAFE_SUPPORT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
ALLOWED_ASSET_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".json", ".png", ".txt", ".webp"}


@dataclass(frozen=True)
class StagedFile:
    role: str
    relative_path: str
    target_relative_path: str
    sha256: str
    bytes: int

    def to_manifest(self) -> dict[str, object]:
        return {
            "role": self.role,
            "relative_path": self.relative_path,
            "target_relative_path": self.target_relative_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
        }


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
    overwrite: bool = False,
) -> StagedSkillArtifact:
    """Stage a scanned runtime SKILL.md and manifest without activating it."""

    if not SAFE_SKILL_SLUG.fullmatch(slug):
        raise WriterPolicyError("skill slug is not a safe autoskill slug")
    scanner_findings = scan_text(compiled_skill_md)
    if has_blocking_findings(scanner_findings):
        raise WriterPolicyError("compiled skill has blocking scanner findings")

    skill_relative_path = f"{staging_id}/{slug}/SKILL.md"
    target_relative_path = f"skills/autoskill/{slug}/SKILL.md"
    stage_text(root, skill_relative_path, compiled_skill_md, overwrite=overwrite)
    staged_file = StagedFile(
        role="runtime_skill",
        relative_path=skill_relative_path,
        target_relative_path=target_relative_path,
        sha256=sha256_text(compiled_skill_md),
        bytes=len(compiled_skill_md.encode("utf-8")),
    )
    manifest = _writer_manifest(
        staging_id=staging_id,
        skill_version_id=skill_version_id,
        slug=slug,
        files=[staged_file],
        scanner_findings=scanner_findings,
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
        files=[staged_file],
        scanner_findings=scanner_findings,
    )


def verify_staged_manifest(root: Path, manifest_relative_path: str) -> dict[str, object]:
    manifest_path = resolve_contained(root, manifest_relative_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("files", []):
        relative_path = entry["relative_path"]
        path = resolve_contained(root, relative_path)
        digest = sha256_text(path.read_text(encoding="utf-8"))
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


def _writer_manifest(
    *,
    staging_id: UUID,
    skill_version_id: UUID,
    slug: str,
    files: list[StagedFile],
    scanner_findings: list[ScannerFinding],
) -> dict[str, object]:
    return {
        "schema": "autoskill.writer-manifest.v1",
        "staging_id": str(staging_id),
        "skill_version_id": str(skill_version_id),
        "slug": slug,
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
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise WriterPolicyError("writer manifest must contain files")
    for entry in files:
        target_relative_path = str(entry["target_relative_path"])
        _target_path_inside_skill(slug, target_relative_path)


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
