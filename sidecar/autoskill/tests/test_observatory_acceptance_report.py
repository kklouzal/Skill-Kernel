import importlib.util
import sys
from pathlib import Path

from autoskill.services.observatory import STATIONS, SUBSYSTEMS

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "autoskill_observatory_acceptance.py"
)
REPO_ROOT = SCRIPT_PATH.parents[1]
CLIENT_GENERATOR_PATH = REPO_ROOT / "scripts" / "generate_observatory_openapi_client.py"
FIXTURE_GENERATOR_PATH = REPO_ROOT / "scripts" / "autoskill_observatory_fixtures.py"
SPEC = importlib.util.spec_from_file_location("autoskill_observatory_acceptance", SCRIPT_PATH)
assert SPEC is not None
observatory_acceptance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = observatory_acceptance
SPEC.loader.exec_module(observatory_acceptance)

CLIENT_GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "generate_observatory_openapi_client",
    CLIENT_GENERATOR_PATH,
)
assert CLIENT_GENERATOR_SPEC is not None
client_generator = importlib.util.module_from_spec(CLIENT_GENERATOR_SPEC)
assert CLIENT_GENERATOR_SPEC.loader is not None
sys.modules[CLIENT_GENERATOR_SPEC.name] = client_generator
CLIENT_GENERATOR_SPEC.loader.exec_module(client_generator)

FIXTURE_GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "autoskill_observatory_fixtures",
    FIXTURE_GENERATOR_PATH,
)
assert FIXTURE_GENERATOR_SPEC is not None
fixture_generator = importlib.util.module_from_spec(FIXTURE_GENERATOR_SPEC)
assert FIXTURE_GENERATOR_SPEC.loader is not None
sys.modules[FIXTURE_GENERATOR_SPEC.name] = fixture_generator
FIXTURE_GENERATOR_SPEC.loader.exec_module(fixture_generator)


def test_observatory_acceptance_report_maps_ui_spec_and_checklist() -> None:
    report = observatory_acceptance.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["acceptance_criteria"] == 42
    assert report["summary"]["developer_checklist"] == 44
    assert report["summary"]["satisfied"] == 86
    assert observatory_acceptance.validate_items(
        (
            *observatory_acceptance.ACCEPTANCE_CRITERIA,
            *observatory_acceptance.DEVELOPER_CHECKLIST,
        )
    ) == []
    assert all(item["evidence"] for item in report["acceptance_criteria"])
    assert all(item["evidence"] for item in report["developer_checklist"])


def test_observatory_catalog_seed_migration_matches_runtime_catalog() -> None:
    migration = (REPO_ROOT / "migrations" / "0001_autoskill_schema.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS autoskill.admin_component_catalog" in migration
    assert "CREATE TABLE IF NOT EXISTS autoskill.admin_subsystem_catalog" in migration
    assert migration.count("INSERT INTO autoskill.admin_component_catalog") == 1
    assert migration.count("INSERT INTO autoskill.admin_subsystem_catalog") == 1
    for station in STATIONS:
        assert f"('{station.component_id}'," in migration
    for subsystem in SUBSYSTEMS:
        assert f"('{subsystem['subsystem_id']}'," in migration


def test_observatory_generated_openapi_client_is_fresh() -> None:
    generated_path = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/generated/observatoryClient.ts"
    )
    generated = generated_path.read_text(encoding="utf-8")
    schema = client_generator.load_openapi_schema()
    routes = client_generator._admin_routes(schema)
    route_paths = {route["path"] for route in routes}
    expected = client_generator.build_client_source(schema)

    assert generated == expected
    assert len(routes) >= 70
    assert len(route_paths) >= 70
    assert "/summary" in generated
    assert "/actions/summary" in generated
    assert "/actions/audit" in generated
    assert "/replay/traces/{trace_id}" in generated


def test_observatory_frontend_render_diagnostics_are_visible() -> None:
    app_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/App.tsx"
    ).read_text(encoding="utf-8")

    assert "FrontendDiagnostics" in app_source
    assert "app_render_count" in app_source
    assert "app_mount_count" in app_source
    assert "duplicate_snapshot_suppression_count" in app_source
    assert "sequence_gap_reload_count" in app_source
    assert "Frontend Diagnostics" in app_source


def test_observatory_frontend_broker_replay_corpus_is_visible() -> None:
    app_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/App.tsx"
    ).read_text(encoding="utf-8")
    api_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/api.ts"
    ).read_text(encoding="utf-8")
    styles = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/styles.css"
    ).read_text(encoding="utf-8")

    assert 'label="Replay"' in app_source
    assert "BrokerReplayCorpus" in app_source
    assert "Broker Replay Corpus" in app_source
    assert "raw_prompt_stored" in app_source
    assert "fetchBrokerReplayEpisodes" in api_source
    assert 'adminApiPath("/broker/replay-episodes")' in api_source
    assert "replay-layout" in styles


def test_observatory_frontend_trace_replay_read_model_is_visible() -> None:
    app_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/App.tsx"
    ).read_text(encoding="utf-8")
    types_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/types.ts"
    ).read_text(encoding="utf-8")

    assert "traceWaterfallFromReplay" in app_source
    assert "traceStationHighlightsFromReplay" in app_source
    assert "traceBadgesFromReplay" in app_source
    assert "traceDiffPanelsFromReplay" in app_source
    assert "Redacted Export Bundle" in app_source
    assert "Replay Provenance" in app_source
    assert "TraceReplayWaterfallRow" in types_source
    assert "TraceReplayStationHighlight" in types_source
    assert "TraceReplayBadge" in types_source


def test_observatory_frontend_topology_metrics_are_visible() -> None:
    app_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/App.tsx"
    ).read_text(encoding="utf-8")
    styles = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/styles.css"
    ).read_text(encoding="utf-8")

    assert "topologyOperationRows" in app_source
    assert "topologyTrialRows" in app_source
    assert "topologyOperationIdentifier" in app_source
    assert "Operation Evidence" in app_source
    assert '"topology_operation"' in app_source
    assert "Topology operation metrics" in app_source
    assert "Topology trial matrix" in app_source
    assert "Recent Operations" in app_source
    assert "topology-metrics-grid" in styles
    assert "topology-trial-matrix" in styles
    assert "topology-operation-detail" in styles


def test_observatory_guarded_action_dialog_is_present() -> None:
    app_source = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/App.tsx"
    ).read_text(encoding="utf-8")
    styles = (
        REPO_ROOT / "sidecar/autoskill/observatory/src/styles.css"
    ).read_text(encoding="utf-8")

    assert "pendingAction" in app_source
    assert 'role="dialog"' in app_source
    assert "aria-modal" in app_source
    assert "Confirm dry-run" in app_source
    assert "action-dialog" in styles


def test_observatory_e2e_load_and_visual_fixtures_are_fresh() -> None:
    fixture_path = (
        REPO_ROOT / "sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json"
    )
    generated = fixture_path.read_text(encoding="utf-8")
    expected = fixture_generator.render_json()
    report = fixture_generator.build_fixture_report()

    assert generated == expected
    assert report["ready"] is True
    assert report["summary"]["scenario_count"] == 11
    assert report["summary"]["missing_visual_states"] == []
    assert report["summary"]["high_load_skill_count"] >= 1000
    assert fixture_generator.validate_fixture_report(report["fixtures"]) == []
    assert all(fixture["e2e_journey"] for fixture in report["fixtures"])
    assert all(fixture["visual_assertions"] for fixture in report["fixtures"])
