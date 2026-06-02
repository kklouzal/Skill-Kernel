import asyncio
from uuid import uuid4

from autoskill.db.contracts import (
    DriftCheckResult,
    _check_contract,
    _contracts_from_skill_ir,
    _is_false_positive_contract,
    _retire_resolved_drift_probes,
    _upsert_drift_probe,
)


def test_contract_extraction_classifies_static_probe_methods() -> None:
    contracts = _contracts_from_skill_ir(
        {
            "environment_contracts": [
                {
                    "kind": "path",
                    "name": "repo root",
                    "expectation": "path exists",
                    "probe": "static:exists:/tmp",
                },
                {
                    "kind": "cli",
                    "name": "python",
                    "expectation": "python is available",
                    "probe": "static:which:python",
                },
                {
                    "kind": "env",
                    "name": "token",
                    "expectation": "env var exists",
                    "probe": "static:env:AUTOSKILL_TEST_TOKEN",
                },
                {
                    "kind": "package",
                    "name": "pytest",
                    "expectation": "pytest package exists",
                    "probe": "static:python-package:pytest",
                },
                {
                    "kind": "schema",
                    "name": "schema file",
                    "expectation": "schema can load",
                    "probe": "static:json-schema:/tmp/schema.json",
                },
                {
                    "kind": "service",
                    "name": "local service",
                    "expectation": "service port is reachable",
                    "probe": "static:tcp:127.0.0.1:9",
                },
            ]
        }
    )

    assert [contract["validation_method"] for contract in contracts] == [
        "static_path_exists",
        "static_command_exists",
        "static_env_present",
        "static_python_package_present",
        "static_json_schema_loadable",
        "static_tcp_reachable",
    ]


def test_drift_check_handles_command_env_and_package_probes(monkeypatch) -> None:
    monkeypatch.setenv("AUTOSKILL_TEST_TOKEN", "set")

    assert _check_contract({"metadata": {"probe": "static:which:python"}})[0] == "valid"
    assert _check_contract({"metadata": {"probe": "static:which:autoskill-missing-command"}}) == (
        "violated",
        "command missing: autoskill-missing-command",
    )
    assert _check_contract({"metadata": {"probe": "static:env:AUTOSKILL_TEST_TOKEN"}})[0] == "valid"
    assert _check_contract({"metadata": {"probe": "static:env:AUTOSKILL_MISSING_TOKEN"}}) == (
        "violated",
        "environment variable missing: AUTOSKILL_MISSING_TOKEN",
    )
    assert _check_contract({"metadata": {"probe": "static:python-package:pytest"}})[0] == "valid"
    missing_package = _check_contract(
        {"metadata": {"probe": "static:python-package:autoskill-missing-pkg"}}
    )
    assert missing_package == (
        "violated",
        "python package missing: autoskill-missing-pkg",
    )


def test_drift_check_handles_schema_and_service_probes(tmp_path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_connect(target, timeout):
        assert target == ("127.0.0.1", 443)
        assert timeout == 0.25
        return FakeSocket()

    monkeypatch.setattr("socket.create_connection", fake_connect)

    assert _check_contract({"metadata": {"probe": f"static:json-schema:{schema}"}})[0] == "valid"
    missing_schema = _check_contract(
        {"metadata": {"probe": f"static:json-schema:{tmp_path / 'missing'}"}}
    )
    assert missing_schema == (
        "violated",
        f"json schema path missing: {tmp_path / 'missing'}",
    )
    assert _check_contract({"metadata": {"probe": "static:tcp:127.0.0.1:443"}}) == (
        "valid",
        "tcp service reachable: 127.0.0.1:443",
    )
    assert _check_contract({"metadata": {"probe": "static:tcp:not-a-service"}}) == (
        "unknown",
        "tcp service probe must be host:port",
    )


def test_drift_probe_upsert_and_retire_are_contract_scoped() -> None:
    contract_id = uuid4()
    skill_id = uuid4()
    version_id = uuid4()

    class FakeConn:
        def __init__(self) -> None:
            self.upserts = []
            self.retire_args = None

        async def fetchrow(self, _query, *_args):
            self.upserts.append(_args)
            return {"created": True}

        async def execute(self, _query, *_args):
            self.retire_args = _args
            return "UPDATE 1"

    conn = FakeConn()

    async def run():
        probe_hash, created = await _upsert_drift_probe(
            conn,
            workspace_id=uuid4(),
            contract={
                "environment_contract_id": contract_id,
                "skill_id": skill_id,
                "skill_version_id": version_id,
                "name": "schema",
                "contract_type": "schema",
                "expectation": "schema loads",
                "validation_method": "static_json_schema_loadable",
                "metadata": {"probe": "static:json-schema:/tmp/missing"},
            },
            reason="json schema path missing: /tmp/missing",
        )
        retired = await _retire_resolved_drift_probes(
            conn,
            workspace_id=uuid4(),
            contract_id=contract_id,
        )
        return probe_hash, created, retired

    probe_hash, created, retired = asyncio.run(run())

    assert probe_hash
    assert created is True
    assert retired == 1
    assert f'"environment_contract_id":"{contract_id}"' in conn.upserts[0][2]
    assert conn.retire_args[1] == str(contract_id)


def test_false_positive_contracts_are_serialized_and_detected() -> None:
    assert _is_false_positive_contract(
        {
            "status": "violated",
            "metadata": {"false_positive": {"operator_id": "tester"}},
        }
    )
    assert _is_false_positive_contract({"status": "false_positive", "metadata": {}})

    payload = DriftCheckResult(
        scanned=2,
        valid=0,
        violated=1,
        unknown=0,
        false_positive=1,
        events=[],
    ).to_json()

    assert payload["false_positive"] == 1
