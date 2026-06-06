import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autoskill_acceptance.py"
SPEC = importlib.util.spec_from_file_location("autoskill_acceptance", SCRIPT_PATH)
assert SPEC is not None
acceptance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = acceptance
SPEC.loader.exec_module(acceptance)


def test_production_acceptance_report_maps_every_concrete_criterion() -> None:
    report = acceptance.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["production_criteria"] == 63
    assert report["summary"]["context_criteria"] == 7
    assert report["summary"]["implemented"] == 70
    assert (
        acceptance.validate_criteria(
            (*acceptance.PRODUCTION_CRITERIA, *acceptance.CONTEXT_CRITERIA)
        )
        == []
    )
    assert all(item["evidence"] for item in report["production_criteria"])
    assert all(item["evidence"] for item in report["context_criteria"])


def test_production_acceptance_ids_match_current_spec_sequence() -> None:
    report = acceptance.build_report()
    criteria = {
        item["criterion_id"]: item["text"] for item in report["production_criteria"]
    }

    assert list(criteria) == [f"31.{index}" for index in range(1, 64)]
    assert criteria["31.33"].startswith(
        "No active SkillKernel-owned skill exists without a complete data-to-skill trace"
    )
    assert "Seeded datasets prove the bridge" in criteria["31.34"]
    assert "Every bridge stage has inspectable input IDs" in criteria["31.35"]
    assert criteria["31.36"].startswith("Every context-loadable artifact")
    assert criteria["31.63"].startswith("Observatory exposes calibration support")
    assert not any(
        item["text"].startswith("New implementation-spec criteria")
        for item in report["production_criteria"]
    )
