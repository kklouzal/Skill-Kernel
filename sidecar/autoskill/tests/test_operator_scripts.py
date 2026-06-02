from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType

SCRIPT_ROOT = Path(__file__).resolve().parents[3] / "scripts"


def _load_script(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPT_ROOT))
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_red_team_default_cases_pass() -> None:
    red_team = _load_script("autoskill_red_team")

    result = red_team.run_red_team_cases(red_team.DEFAULT_CASES)

    assert result["failed"] == 0
    assert result["total"] == 9


def test_backup_manifest_verification_detects_content_hashes(tmp_path: Path) -> None:
    backup = _load_script("autoskill_backup")
    restore = _load_script("autoskill_restore")
    backup_root = tmp_path / "autoskill-backup-test"
    (backup_root / "db").mkdir(parents=True)
    (backup_root / "filesystem").mkdir()
    db_dump = backup_root / "db" / "autoskill.dump"
    db_dump.write_bytes(b"pg custom dump placeholder")
    fs_archive = backup_root / "filesystem" / "autoskill-roots.tar.gz"
    with tarfile.open(fs_archive, "w:gz"):
        pass
    manifest = {
        "schema": backup.SCHEMA,
        "backup_id": "autoskill-backup-test",
        "database": {
            "dump_path": "db/autoskill.dump",
            "dump_sha256": backup._file_sha256(db_dump),
        },
        "filesystem": {
            "archive_path": "filesystem/autoskill-roots.tar.gz",
            "archive_sha256": backup._file_sha256(fs_archive),
            "roots": [],
        },
    }
    (backup_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    loaded = restore._load_manifest(backup_root / "manifest.json")
    restore._verify_manifest(backup_root, loaded)
