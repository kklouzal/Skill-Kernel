import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autoskill_readiness.py"
SPEC = importlib.util.spec_from_file_location("autoskill_readiness", SCRIPT_PATH)
assert SPEC is not None
readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)


def test_landscape_and_readiness_report_maps_unified_specification() -> None:
    report = readiness.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["landscape_rows"] == 52
    assert report["summary"]["stance_lines"] == 8
    assert report["summary"]["readiness_checklist_items"] == 17
    assert all(row["urls"] for row in report["landscape_matrix"])
    assert all(row["evidence"] for row in report["landscape_matrix"])
    assert all(item["status"] == "demonstrated" for item in report["readiness_checklist"])
    assert all(item["evidence"] for item in report["readiness_checklist"])
    checklist_text = " ".join(item["item"] for item in report["readiness_checklist"])
    for operation in ("Create", "improve", "compose", "decompose"):
        assert operation in checklist_text
