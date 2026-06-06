import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autoskill_conformance.py"
SPEC = importlib.util.spec_from_file_location("autoskill_conformance", SCRIPT_PATH)
assert SPEC is not None
conformance = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = conformance
SPEC.loader.exec_module(conformance)


def test_part_v_static_conformance_report_covers_required_checks() -> None:
    report = conformance.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["checks"] == 17
    assert report["summary"]["passed"] == 17
    assert all(check["evidence"] for check in report["checks"])
    assert {
        "SKX-STATIC-001",
        "SKX-STATIC-002",
        "SKX-STATIC-003",
        "SKX-STATIC-004",
        "SKX-STATIC-005",
        "SKX-STATIC-006",
        "SKX-STATIC-006B",
        "SKX-STATIC-006C",
        "SKX-STATIC-006D",
        "SKX-STATIC-007",
        "SKX-STATIC-008",
        "SKX-STATIC-009",
        "SKX-STATIC-010",
        "SKX-STATIC-011",
        "SKX-STATIC-012",
        "SKX-STATIC-013",
        "SKX-STATIC-014",
    } == {check["check_id"] for check in report["checks"]}
