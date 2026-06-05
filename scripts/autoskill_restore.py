#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoskill_backup import (
    DEFAULT_CONFIRM_RESTORE,
    SCHEMA,
    _file_sha256,
    copy_tree_replace,
)


def main() -> None:
    args = _parse_args()
    bundle = Path(args.backup).resolve()
    repo_root = Path(args.repo_root).resolve()
    workspace_root = Path(args.workspace_root).resolve()

    with tempfile.TemporaryDirectory(prefix="autoskill-restore-") as tmp_name:
        tmp_dir = Path(tmp_name)
        with tarfile.open(bundle, "r:gz") as tar:
            _safe_extract(tar, tmp_dir)
        backup_root = _single_child(tmp_dir)
        manifest = _load_manifest(backup_root / "manifest.json")
        _verify_manifest(backup_root, manifest)

        summary = {
            "backup_id": manifest["backup_id"],
            "valid": True,
            "restore_db": args.restore_db,
            "restore_files": args.restore_files,
            "dry_run": args.dry_run,
        }
        if args.dry_run:
            print(json.dumps(summary, indent=2, sort_keys=True))
            return

        if args.confirm_restore != DEFAULT_CONFIRM_RESTORE:
            raise SystemExit(
                "restore requires --confirm-restore "
                + DEFAULT_CONFIRM_RESTORE
            )

        if args.restore_db:
            _restore_database(
                backup_root / manifest["database"]["dump_path"],
                repo_root=repo_root,
                compose_file=args.compose_file,
                service=args.database_service,
                database=args.database_name,
                user=args.database_user,
            )
        if args.restore_files:
            _restore_filesystem(backup_root, manifest, workspace_root)

    print(json.dumps(summary, indent=2, sort_keys=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify or restore a SkillKernel AutoSkill backup bundle."
    )
    parser.add_argument("backup")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workspace-root", default=Path.cwd())
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument("--database-service", default="postgres")
    parser.add_argument("--database-name", default="autoskill")
    parser.add_argument("--database-user", default="autoskill")
    parser.add_argument("--restore-db", action="store_true")
    parser.add_argument("--restore-files", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", dest="dry_run", action="store_false")
    parser.add_argument("--confirm-restore", default="")
    return parser.parse_args()


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise SystemExit(f"unsupported backup schema: {manifest.get('schema')}")
    return manifest


def _verify_manifest(backup_root: Path, manifest: dict[str, Any]) -> None:
    db_path = backup_root / manifest["database"]["dump_path"]
    fs_path = backup_root / manifest["filesystem"]["archive_path"]
    expected_db_hash = manifest["database"]["dump_sha256"]
    expected_fs_hash = manifest["filesystem"]["archive_sha256"]
    if _file_sha256(db_path) != expected_db_hash:
        raise SystemExit("database dump hash mismatch")
    if _file_sha256(fs_path) != expected_fs_hash:
        raise SystemExit("filesystem archive hash mismatch")


def _restore_database(
    dump_path: Path,
    *,
    repo_root: Path,
    compose_file: str,
    service: str,
    database: str,
    user: str,
) -> None:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        service,
        "pg_restore",
        "--clean",
        "--if-exists",
        f"--dbname={database}",
        f"--username={user}",
    ]
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        input=dump_path.read_bytes(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "pg_restore failed: " + result.stderr.decode("utf-8", errors="replace").strip()
        )


def _restore_filesystem(
    backup_root: Path,
    manifest: dict[str, Any],
    workspace_root: Path,
) -> None:
    pre_restore = workspace_root / ".autoskill" / "pre-restore"
    restore_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_existing_root = pre_restore / restore_id
    backup_existing_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="autoskill-fs-restore-") as tmp_name:
        tmp_dir = Path(tmp_name)
        fs_archive = backup_root / manifest["filesystem"]["archive_path"]
        with tarfile.open(fs_archive, "r:gz") as tar:
            _safe_extract(tar, tmp_dir)
        for root in manifest["filesystem"]["roots"]:
            if not root.get("exists"):
                continue
            relative = Path(root["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise SystemExit(f"refusing unsafe restore root: {relative}")
            destination = workspace_root / relative
            if destination.exists():
                copy_tree_replace(destination, backup_existing_root / relative)
            copy_tree_replace(tmp_dir / relative, destination)


def _single_child(path: Path) -> Path:
    children = list(path.iterdir())
    if len(children) != 1 or not children[0].is_dir():
        raise SystemExit("backup bundle must contain one root directory")
    return children[0]


def _safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tar.getmembers():
        target = (destination / member.name).resolve()
        if not str(target).startswith(str(destination)):
            raise SystemExit(f"refusing unsafe archive member: {member.name}")
    tar.extractall(destination)


if __name__ == "__main__":
    main()
