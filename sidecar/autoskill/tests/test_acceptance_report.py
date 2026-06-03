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
    assert report["summary"]["production_criteria"] == 44
    assert report["summary"]["context_criteria"] == 7
    assert report["summary"]["implemented"] == 51
    assert (
        acceptance.validate_criteria(
            (*acceptance.PRODUCTION_CRITERIA, *acceptance.CONTEXT_CRITERIA)
        )
        == []
    )
    assert all(item["evidence"] for item in report["production_criteria"])
    assert all(item["evidence"] for item in report["context_criteria"])
