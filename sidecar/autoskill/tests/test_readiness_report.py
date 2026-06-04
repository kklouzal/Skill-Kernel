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


def test_landscape_and_readiness_report_maps_sections_35_and_36() -> None:
    report = readiness.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["landscape_rows"] == 52
    assert report["summary"]["stance_lines"] == 8
    assert report["summary"]["architecture_items"] == 30
    assert report["summary"]["product_operations"] == 4
    assert report["summary"]["implementation_order_steps"] == 31
    assert report["sequencing_gates"] == {
        "do_not_build_autonomous_skill_writing_first": True,
        "future_design_changes_require_concrete_failure_mode": True,
    }
    assert {
        item["item"].split(":", 1)[0]
        for item in report["product_operations"]
    } == {"create", "improve", "compose", "decompose"}
    assert all(row["urls"] for row in report["landscape_matrix"])
    assert all(row["evidence"] for row in report["landscape_matrix"])
    assert all(item["evidence"] for item in report["architecture"])
    assert all(item["evidence"] for item in report["implementation_order"])
