from __future__ import annotations

import importlib.util
import json
import sys
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_ROOT = Path(__file__).resolve().parents[3] / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPT_ROOT))
    spec = importlib.util.spec_from_file_location(name, SCRIPT_ROOT / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_repo_file(name: str, path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_migrate_split_sql_statements_preserves_postgres_blocks() -> None:
    migrate = _load_script("migrate")

    statements = migrate.split_sql_statements(
        """
        CREATE TABLE demo (value text DEFAULT ';');
        -- comment with ; must not split
        INSERT INTO demo VALUES ('a'';b');
        /* block ; comment */
        DO $$
        BEGIN
          RAISE NOTICE 'inside; block';
        END;
        $$;
        CREATE FUNCTION demo_fn() RETURNS void
        LANGUAGE plpgsql
        AS $body$
        BEGIN
          PERFORM ';';
        END;
        $body$;
        """
    )

    assert len(statements) == 4
    assert statements[0].startswith("CREATE TABLE demo")
    assert "a'';b" in statements[1]
    assert statements[2].startswith("/* block ; comment */\n        DO $$")
    assert statements[3].endswith("$body$;")


def test_migrate_split_sql_statements_ignores_invalid_dollar_tag_lookalike() -> None:
    migrate = _load_script("migrate")

    statements = migrate.split_sql_statements("SELECT $1$not a dollar block; SELECT 2;")

    assert statements == ["SELECT $1$not a dollar block;", "SELECT 2;"]


@pytest.mark.asyncio
async def test_migrate_run_migration_executes_each_statement_in_order(capsys) -> None:
    migrate = _load_script("migrate")

    class FakeConnection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        async def execute(self, query: str) -> str:
            self.statements.append(query)
            return "OK"

    conn = FakeConnection()

    await migrate.run_migration(conn, "SELECT 1; SELECT ';';")

    assert conn.statements == ["SELECT 1;", "SELECT ';';"]
    assert capsys.readouterr().err == ""


@pytest.mark.asyncio
async def test_migrate_run_migration_reports_failing_statement(capsys) -> None:
    migrate = _load_script("migrate")

    class FakeConnection:
        def __init__(self) -> None:
            self.statements: list[str] = []

        async def execute(self, query: str) -> str:
            self.statements.append(query)
            if "broken" in query:
                raise RuntimeError("boom")
            return "OK"

    conn = FakeConnection()

    try:
        await migrate.run_migration(conn, "SELECT 1; SELECT broken; SELECT 3;")
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("expected migration failure")

    assert conn.statements == ["SELECT 1;", "SELECT broken;"]
    assert "migration statement 2 failed: SELECT broken;" in capsys.readouterr().err


def test_schema_migration_deduplicates_historical_source_backfill() -> None:
    migration = (SCRIPT_ROOT.parents[0] / "migrations" / "0001_autoskill_schema.sql").read_text(
        encoding="utf-8"
    )

    assert "WITH ranked_historical_import_sources AS" in migration
    assert "row_number() OVER" in migration
    assert (
        "PARTITION BY\n"
        "        workspace_id,\n"
        "        autoskill.map_historical_source_type(source_kind),\n"
        "        source_key"
    ) in migration
    assert "FROM ranked_historical_import_sources\nWHERE source_rank = 1" in migration
    assert "ON CONFLICT (workspace_id, source_type, source_uri) DO UPDATE SET" in migration


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


def test_admin_token_script_verifies_observatory_config_endpoint() -> None:
    admin_token = _load_script("autoskill_admin_token")

    assert admin_token.DEFAULT_API_BASE == "http://127.0.0.1:8757/admin/api/v1"
    assert admin_token._verification_url("http://127.0.0.1:8757/admin/api/v1/") == (
        "http://127.0.0.1:8757/admin/api/v1/config"
    )


def test_admin_token_script_discovers_repo_root_from_nested_cwd(tmp_path: Path) -> None:
    admin_token = _load_script("autoskill_admin_token")
    repo = tmp_path / "repo"
    nested = repo / "nested"
    (repo / "scripts").mkdir(parents=True)
    nested.mkdir()
    (repo / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (repo / "scripts" / "autoskill_admin_token.py").write_text("", encoding="utf-8")

    assert admin_token._repo_root(nested) == repo


def test_observatory_healthcheck_sends_admin_token_to_local_ready_route(monkeypatch) -> None:
    healthcheck = _load_repo_file(
        "observatory_healthcheck",
        "containers/observatory/healthcheck.py",
    )

    monkeypatch.setenv(
        "SKILLKERNEL_OBSERVATORY_HEALTH_URL",
        "http://127.0.0.1:8757/admin/api/v1/health/ready",
    )
    monkeypatch.setenv("SKILLKERNEL_ADMIN_TOKEN", "admin-token")
    monkeypatch.setattr(sys, "argv", ["healthcheck.py", "observatory"])

    class FakeResponse:
        status = 200

    class FakeConnection:
        request_headers: dict[str, str] | None = None

        def __init__(self, host: str, port: int | None, timeout: int) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def request(self, method: str, path: str, headers: dict[str, str]) -> None:
            assert method == "GET"
            assert path == "/admin/api/v1/health/ready"
            FakeConnection.request_headers = headers

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            pass

    monkeypatch.setattr(healthcheck, "HTTPConnection", FakeConnection)

    assert healthcheck.main() == 0
    assert FakeConnection.request_headers == {"Authorization": "Bearer admin-token"}


def test_observatory_healthcheck_does_not_send_admin_token_to_remote_url(monkeypatch) -> None:
    healthcheck = _load_repo_file(
        "observatory_healthcheck_remote",
        "containers/observatory/healthcheck.py",
    )

    monkeypatch.setenv(
        "SKILLKERNEL_OBSERVATORY_HEALTH_URL",
        "https://observatory.example.invalid/admin/api/v1/health/ready",
    )
    monkeypatch.setenv("SKILLKERNEL_ADMIN_TOKEN", "admin-token")

    assert healthcheck._healthcheck_headers(
        "observatory.example.invalid",
        "/admin/api/v1/health/ready",
    ) == {}
