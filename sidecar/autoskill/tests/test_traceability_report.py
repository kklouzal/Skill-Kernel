import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "autoskill_traceability.py"
SPEC = importlib.util.spec_from_file_location("autoskill_traceability", SCRIPT_PATH)
assert SPEC is not None
traceability = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = traceability
SPEC.loader.exec_module(traceability)


def test_research_traceability_report_maps_section_34() -> None:
    report = traceability.build_report()

    assert report["ready"] is True
    assert report["summary"]["validation_errors"] == []
    assert report["summary"]["anchor_sections"] == 7
    assert report["summary"]["anchors"] == 100
    assert report["summary"]["anchors_with_urls"] == 88
    assert report["summary"]["traceability_rows"] == 25
    anchor_counts = {
        section["section_id"]: section["anchor_count"]
        for section in report["anchor_sections"]
    }
    assert anchor_counts == {
        "34.1": 44,
        "34.2": 4,
        "34.3": 17,
        "34.4": 5,
        "34.5": 9,
        "34.6": 21,
    }
    assert traceability.validate_traceability_report(
        [
            traceability.ResearchAnchor(
                anchor_id=item["anchor_id"],
                section_id=item["section_id"],
                section_title=item["section_title"],
                title=item["title"],
                body=item["body"],
                urls=tuple(item["urls"]),
            )
            for item in report["anchors"]
        ],
        [
            traceability.TraceabilityRow(
                row_id=item["row_id"],
                finding=item["finding"],
                design_response=item["design_response"],
                evidence=tuple(item["evidence"]),
            )
            for item in report["traceability_matrix"]
        ],
        {
            section["section_id"]: section["title"]
            for section in report["anchor_sections"]
        }
        | {"34.7": "Research-to-design traceability matrix"},
    ) == []
    assert all(row["evidence"] for row in report["traceability_matrix"])
