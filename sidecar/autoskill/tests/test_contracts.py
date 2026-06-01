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
            ]
        }
    )

    assert [contract["validation_method"] for contract in contracts] == [
        "static_path_exists",
        "static_command_exists",
        "static_env_present",
    ]


def test_drift_check_handles_command_and_env_probes(monkeypatch) -> None:
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
