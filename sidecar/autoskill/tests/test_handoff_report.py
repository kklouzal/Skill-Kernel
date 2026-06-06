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
    assert report["summary"]["risks"] == 35
    assert report["summary"]["before_coding"] == 25
    assert report["summary"]["during_implementation"] == 18
    assert report["summary"]["ship_gates"] == 1
    assert report["summary"]["satisfied"] == 79
    assert report["summary"]["total_items"] == 79
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


def test_handoff_report_ids_match_current_spec_sequence() -> None:
    report = handoff.build_report()

    risk_items = {item["risk_id"]: item for item in report["risk_register"]}
    before_items = {
        item["checklist_id"]: item
        for item in report["developer_handoff"]["before_coding"]
    }
    during_items = {
        item["checklist_id"]: item
        for item in report["developer_handoff"]["during_implementation"]
    }

    assert list(risk_items) == [f"32.{index}" for index in range(1, 36)]
    assert list(before_items) == [
        f"33.before.{index}" for index in range(1, 26)
    ]
    assert list(during_items) == [
        f"33.during.{index}" for index in range(1, 19)
    ]
    assert risk_items["32.31"]["risk"] == "Soft-threshold rigidity stalls autonomy"
    assert risk_items["32.35"]["risk"] == "Autonomy incident"
    assert before_items["33.before.14"]["item"].startswith(
        "Define hard invariants versus soft decision bands"
    )
    assert before_items["33.before.15"]["item"].startswith(
        "Define Autonomous Decision Orchestrator action mapping"
    )
    assert before_items["33.before.17"]["item"].startswith(
        "Define no-operator-prose"
    )
    assert before_items["33.before.19"]["item"] == (
        "Define Core and Observatory authentication separately."
    )
