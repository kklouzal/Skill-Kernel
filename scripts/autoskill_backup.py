#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA = "autoskill.backup.v1"
DEFAULT_CONFIRM_RESTORE = "I_UNDERSTAND_THIS_OVERWRITES_AUTOSKILL_STATE"


def main() -> None:
    args = _parse_args()
    repo_root = Path(args.repo_root).resolve()
    workspace_root = Path(args.workspace_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    backup_id = datetime.now(UTC).strftime("autoskill-backup-%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix=f"{backup_id}-") as tmp_name:
        tmp_dir = Path(tmp_name)
        staging = tmp_dir / backup_id
        staging.mkdir()

        db_dump = staging / "db" / "autoskill.dump"
        db_dump.parent.mkdir()
        _dump_database(
            db_dump,
            repo_root=repo_root,
            compose_file=args.compose_file,
            service=args.database_service,
            database=args.database_name,
            user=args.database_user,
        )

        fs_archive = staging / "filesystem" / "autoskill-roots.tar.gz"
        fs_archive.parent.mkdir()
        fs_roots = _archive_filesystem_roots(
            fs_archive,
            workspace_root=workspace_root,
            roots=[
                args.active_root,
                args.archive_root,
                args.staging_root if args.include_staging else None,
            ],
        )

        manifest = {
            "schema": SCHEMA,
            "backup_id": backup_id,
            "created_at": datetime.now(UTC).isoformat(),
            "repo": {
                "root": str(repo_root),
                "commit": _git_commit(repo_root),
                "dirty": _git_dirty(repo_root),
            },
            "workspace_root": str(workspace_root),
            "database": {
                "service": args.database_service,
                "database": args.database_name,
                "user": args.database_user,
                "schema": args.schema_name,
                "dump_path": "db/autoskill.dump",
                "dump_sha256": _file_sha256(db_dump),
                "format": "pg_dump custom",
            },
            "filesystem": {
                "archive_path": "filesystem/autoskill-roots.tar.gz",
                "archive_sha256": _file_sha256(fs_archive),
                "roots": fs_roots,
            },
            "restore": {
                "script": "scripts/autoskill_restore.py",
                "required_confirmation": DEFAULT_CONFIRM_RESTORE,
                "note": "Restore overwrites autoskill DB schema and selected runtime roots.",
            },
        }
        _write_json(staging / "manifest.json", manifest)

        bundle_path = output_dir / f"{backup_id}.tar.gz"
        with tarfile.open(bundle_path, "w:gz") as tar:
            tar.add(staging, arcname=backup_id)

    print(
        json.dumps(
            {
                "backup": str(bundle_path),
                "backup_id": backup_id,
                "database_dump_sha256": manifest["database"]["dump_sha256"],
                "filesystem_archive_sha256": manifest["filesystem"]["archive_sha256"],
                "filesystem_roots": fs_roots,
            },
            indent=2,
            sort_keys=True,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a SkillKernel AutoSkill disaster-recovery backup bundle."
    )
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("AUTOSKILL_WORKSPACE_ROOT", Path.cwd()),
        help="Runtime workspace containing active/archive/staging autoskill roots.",
    )
    parser.add_argument("--output-dir", default=".autoskill/backups")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument("--database-service", default="postgres")
    parser.add_argument("--database-name", default="autoskill")
    parser.add_argument("--database-user", default="autoskill")
    parser.add_argument("--schema-name", default="autoskill")
    parser.add_argument("--active-root", default="skills/autoskill")
    parser.add_argument("--archive-root", default=".autoskill/archive")
    parser.add_argument("--staging-root", default=".autoskill/staging")
    parser.add_argument("--include-staging", action="store_true")
    return parser.parse_args()


def _dump_database(
    output: Path,
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
        "pg_dump",
        "--format=custom",
        "--schema=autoskill",
        f"--dbname={database}",
        f"--username={user}",
    ]
    result = subprocess.run(
        cmd,
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "pg_dump failed: " + result.stderr.decode("utf-8", errors="replace").strip()
        )
    output.write_bytes(result.stdout)


def _archive_filesystem_roots(
    output: Path,
    *,
    workspace_root: Path,
    roots: list[str | None],
) -> list[dict[str, Any]]:
    archived: list[dict[str, Any]] = []
    with tarfile.open(output, "w:gz") as tar:
        for root in roots:
            if root is None:
                continue
            relative = Path(root)
            if relative.is_absolute() or ".." in relative.parts:
                raise SystemExit(f"refusing unsafe runtime root: {root}")
            source = workspace_root / relative
            if not source.exists():
                archived.append({"path": root, "exists": False})
                continue
            tar.add(source, arcname=str(relative))
            archived.append(
                {
                    "path": root,
                    "exists": True,
                    "kind": "directory" if source.is_dir() else "file",
                }
            )
    return archived


def _git_commit(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _git_dirty(repo_root: Path) -> bool | None:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_tree_replace(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


if __name__ == "__main__":
    main()
