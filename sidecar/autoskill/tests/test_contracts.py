from autoskill.db.contracts import _check_contract, _contracts_from_skill_ir


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
