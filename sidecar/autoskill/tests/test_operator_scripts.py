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


def test_replay_corpus_tags_are_deduplicated() -> None:
    replay_corpus = _load_script("autoskill_replay_corpus")

    assert replay_corpus._tags(["production", "redacted", "production", " "]) == [
        "production",
        "redacted",
    ]


def test_replay_corpus_rejects_sensitive_redacted_intent() -> None:
    replay_corpus = _load_script("autoskill_replay_corpus")

    try:
        replay_corpus._required_redacted_intent(
            {"redacted_user_intent": "Authorization: Bearer secret"}
        )
    except SystemExit as exc:
        assert "sensitive" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected sensitive intent rejection")


def test_replay_corpus_candidate_json_is_content_safe() -> None:
    replay_corpus = _load_script("autoskill_replay_corpus")

    candidate = replay_corpus.ReplayCandidate(
        retrieval_log_id="log-1",
        created_at="2026-06-02T16:00:00+00:00",
        decision="skill_hint",
        query_hash="hash-only",
        reason_codes=["exact-rerank"],
        candidate_skill_ids=["skill-1"],
        rendered_skill_ids=["skill-1"],
        rendered_skill_slugs=["diagram-accessibility"],
        candidate_count=1,
        rendered_skill_count=1,
        already_recorded=False,
        query_hash_recorded=False,
    ).to_json()

    assert candidate["query_hash"] == "hash-only"
    assert candidate["query_hash_recorded"] is False
    assert "redacted_user_intent" not in candidate
    assert "prompt" not in candidate


def test_admin_token_script_reads_dotenv_and_masks_value(tmp_path: Path) -> None:
    admin_token = _load_script("autoskill_admin_token")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "\n".join(
            [
                "AUTOSKILL_CONTROL_TOKEN=control-token",
                "AUTOSKILL_WEB_ADMIN_TOKEN='admin-token-value'",
            ]
        ),
        encoding="utf-8",
    )

    assert admin_token._token_from_dotenv(dotenv) == "admin-token-value"
    assert admin_token.mask_token("1234567890abcdef") == "123456...abcdef (16 chars)"
