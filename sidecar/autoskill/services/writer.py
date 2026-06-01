from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from autoskill.core.hashing import sha256_json, sha256_text
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
