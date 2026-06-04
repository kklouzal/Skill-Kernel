import importlib.util
import sys
from pathlib import Path

from autoskill.services.observatory import STATIONS, SUBSYSTEMS

SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "autoskill_observatory_acceptance.py"
)
REPO_ROOT = SCRIPT_PATH.parents[1]
SPEC = importlib.util.spec_from_file_location("autoskill_observatory_acceptance", SCRIPT_PATH)
assert SPEC is not None
observatory_acceptance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = observatory_acceptance
SPEC.loader.exec_module(observatory_acceptance)


def test_observatory_acceptance_report_maps_ui_spec_and_checklist() -> None:
    report = observatory_acceptance.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["acceptance_criteria"] == 40
    assert report["summary"]["developer_checklist"] == 38
    assert report["summary"]["satisfied"] == 78
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
