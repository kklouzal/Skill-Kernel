import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autoskill_handoff.py"
SPEC = importlib.util.spec_from_file_location("autoskill_handoff", SCRIPT_PATH)
assert SPEC is not None
handoff = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = handoff
SPEC.loader.exec_module(handoff)


def test_handoff_report_maps_risk_register_and_developer_checklist() -> None:
    report = handoff.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["risks"] == 31
    assert report["summary"]["before_coding"] == 23
    assert report["summary"]["during_implementation"] == 18
    assert report["summary"]["ship_gates"] == 1
    assert report["summary"]["satisfied"] == 73
    assert report["summary"]["total_items"] == 73
    assert handoff.validate_report_items(
        handoff.RISK_REGISTER,
        (
            *handoff.BEFORE_CODING_CHECKLIST,
            *handoff.DURING_IMPLEMENTATION_CHECKLIST,
            handoff.SHIP_GATE,
        ),
    ) == []
    assert all(item["mitigation"] for item in report["risk_register"])
    assert all(item["evidence"] for item in report["risk_register"])
    assert all(
        item["evidence"]
        for section in report["developer_handoff"].values()
        for item in section
    )
