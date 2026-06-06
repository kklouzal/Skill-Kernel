
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC_PATH = ROOT / "unified-implementation-specification.md"
SECTION_START = "### 34. References and research traceability"
SECTION_END = "\n### 35."

EXPECTED_ANCHOR_COUNTS = {
    "34.1": 44,
    "34.2": 4,
    "34.3": 17,
    "34.4": 5,
    "34.5": 9,
    "34.6": 21,
}
EXPECTED_MATRIX_ROWS = 25
EXPECTED_ANCHORS_WITH_URLS = 88

SECTION_RE = re.compile(r"^#### (?P<section_id>34\.\d+) (?P<title>.+)$")
ANCHOR_RE = re.compile(r"^- \*\*(?P<title>.+?)\*\*: (?P<body>.+)$")
URL_RE = re.compile(r"https?://[^\s,)]+")

TRACEABILITY_EVIDENCE_BY_FINDING: dict[str, tuple[str, ...]] = {
    "OpenClaw skills are context-loaded `SKILL.md` artifacts.": (
        "SkillIR compiler renders normal OpenClaw SKILL.md artifacts",
        "writer manifests hash SKILL.md and support files before activation",
        "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
    ),
    "OpenClaw hooks are in-process and timeout-sensitive.": (
        "plugin/autoskill/src/index.js keeps capture/context hooks thin",
        "sidecar owns scheduler, analysis, evaluation, filesystem, and rollback pools",
        "plugin/autoskill/test/hook-smoke.test.js",
    ),
    "OpenClaw Cron is user/Gateway-facing automation.": (
        "sidecar-owned scheduler store and scheduler_defaults",
        "README Non-Negotiables: No OpenClaw Cron dependency",
        "sidecar/autoskill/tests/test_scheduler_defaults.py",
    ),
    "Skill Workshop is useful but unstable as a dependency.": (
        "proposal/scanner/evaluator/writer/archive/promotion stores are sidecar-owned",
        "README Non-Negotiables: No Skill Workshop dependency",
        "scripts/autoskill_acceptance.py criteria 31.1 and 31.2",
    ),
    "Self-generated skills can be neutral or harmful.": (
        "evidence maturity ladder and proposal-gate evaluator",
        "deterministic scanner red-team smoke",
        "critical canary freeze and rollback revocation paths",
    ),
    "Skill libraries degrade as they grow.": (
        "Settings.max_active_skills and utility active-bank curation",
        "runtime broker can abstain/defer and records no-skill controls",
        "shadowing detection and marginal-value utility rollups",
    ),
    "Names/descriptions are insufficient for routing.": (
        "body_index_documents and body-aware retrieval paths",
        "SkillIR, compiled body, contracts, probes, manifests, and support summaries feed retrieval",
        "sidecar/autoskill/tests/test_broker.py",
    ),
    "Retrieval, incorporation, and execution fail separately.": (
        "retrieval logs track retrieved/rendered/injected/used/outcome",
        "context token ledgers distinguish visibility and usefulness outcomes",
        "attribution outcome taxonomy records helped/harmful/missing/shadowed/independent states",
    ),
    "Co-used skills may represent higher-order workflows.": (
        "usage.aggregate mines co-use and sequence windows",
        "topology compose proposals include component-vs-composed trials",
        "sidecar/autoskill/tests/test_topology_services.py",
    ),
    "Broad skills can become black-hole routers.": (
        "utility/context-value signals drive decompose and broker-abstain recommendations",
        "topology decompose proposals include original-vs-successor trials",
        "false-positive load metrics feed curation",
    ),
    "Free-form Markdown is ambiguous and verbose.": (
        "SkillIR is canonical and compiler renders fixed runtime sections",
        "no-human-prose and no-raw-transcript gates",
        "context artifact scanner/budget tests",
    ),
    "Context is finite and long context degrades.": (
        "context compiler and token budget governor",
        "Settings.max_context_hint_tokens and artifact budget status",
        "context-value-per-token utility features",
    ),
    "Compression can lose task-critical meaning.": (
        "routing-equivalence and information-preservation metadata",
        "proposal regression probes and semantic-equivalence checks",
        "writer rollback on context regressions",
    ),
    "Tool/API/package behavior drifts.": (
        "executor profiles and environment contracts",
        "drift probes cover path/command/env/package/schema/TCP/HTTP checks",
        "sidecar/autoskill/tests/test_contracts.py",
    ),
    "Skill files and support artifacts are supply-chain inputs.": (
        "capability manifests, scanner findings, hash manifests, and writer quarantine",
        "support artifact scanner/loadability/budget coverage",
        "scripts/autoskill_red_team.py",
    ),
    "Workspace/bootstrap guidance can steer behavior persistently.": (
        "historical importer treats workspace context and memory files as tainted evidence",
        "workspace guidance is scanned and never compiled directly into general skills",
        "memory quarantine and provenance gates",
    ),
    "OpenClaw runtime security benefits from plugin-side observation plus Core policy.": (
        "thin plugin hooks observe runtime boundaries without slow work",
        "sidecar owns scanner/evaluator/attribution/audit decisions",
        "runtime action-attribution check recording",
    ),
    "Memory can be poisoned and persist.": (
        "memory quarantine APIs and broker trust-gating",
        "taint, provenance, declassification, and revocation traversal",
        "repair/writer paths log approved or blocked memory influence",
    ),
    "Unsafe actions can be caused indirectly.": (
        "action_attribution_checks store and /v1/attribution/action-checks",
        "plugin before_tool_call boundary check path",
        "sidecar/autoskill/tests/test_attribution.py",
    ),
    "Rollback can leave derived state behind.": (
        "evolution transactions and transaction items",
        "provenance/revocation traversal invalidates derived artifacts",
        "writer rollback restores archive-backed active skill state",
    ),
    "LLM reasoning is useful but nondeterministic.": (
        "LLM outputs are staged as structured proposals/plans",
        "deterministic scanner/evaluator/writer/scheduler gates own decisions",
        "LLM invocation audit rows are content-safe",
    ),
    "Context-loaded skill docs are AI-facing, not operator-facing.": (
        "compiled runtime SKILL.md uses compact AI-facing fixed sections",
        "full rationale/history stays in SkillIR/Postgres",
        "no-human-prose and context artifact gates",
    ),
    "Reliable composition requires precondition-effect structure.": (
        "SkillIR effect signatures and typed SkillGraphIR edges",
        "topology planners emit node-level trials and rollback actions",
        "composition/decomposition evaluators gate autonomous topology changes",
    ),
    "One-off reflection can overfit.": (
        "diagnostic momentum store accumulates repeated failures/corrections",
        "contrastive support counts and counterevidence feed repair thresholds",
        "proposal-gate regression/no-skill/adversarial probes",
    ),
    "Autonomous control-plane behavior must be explainable across services.": (
        "trace spine propagates trace_id/span_id/parent_span_id across jobs and services",
        "audit hash chain and content-safe trace spans",
        "optional OpenTelemetry-compatible trace model",
    ),
}


@dataclass(frozen=True)
class ResearchAnchor:
    anchor_id: str
    section_id: str
    section_title: str
    title: str
    body: str
    urls: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "section_id": self.section_id,
            "section_title": self.section_title,
            "title": self.title,
            "body": self.body,
            "urls": list(self.urls),
        }


@dataclass(frozen=True)
class TraceabilityRow:
    row_id: str
    finding: str
    design_response: str
    evidence: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "finding": self.finding,
            "design_response": self.design_response,
            "evidence": list(self.evidence),
        }


def build_report(spec_path: Path = DEFAULT_SPEC_PATH) -> dict[str, Any]:
    section_text = _read_section_34(spec_path)
    anchors, matrix_rows, section_titles = parse_section_34(section_text)
    validation_errors = validate_traceability_report(anchors, matrix_rows, section_titles)
    return {
        "schema": "autoskill.research-traceability-report.v1",
        "ready": not validation_errors,
        "source": str(spec_path),
        "summary": {
            "anchor_sections": len(section_titles) - 1,
            "anchors": len(anchors),
            "anchors_with_urls": sum(1 for anchor in anchors if anchor.urls),
            "traceability_rows": len(matrix_rows),
            "validation_errors": validation_errors,
        },
        "anchor_sections": [
            {
                "section_id": section_id,
                "title": section_titles[section_id],
                "anchor_count": sum(1 for anchor in anchors if anchor.section_id == section_id),
            }
            for section_id in sorted(EXPECTED_ANCHOR_COUNTS)
        ],
        "anchors": [anchor.to_json() for anchor in anchors],
        "traceability_matrix": [row.to_json() for row in matrix_rows],
    }


def parse_section_34(
    section_text: str,
) -> tuple[list[ResearchAnchor], list[TraceabilityRow], dict[str, str]]:
    section_titles: dict[str, str] = {}
    anchors: list[ResearchAnchor] = []
    matrix_rows: list[TraceabilityRow] = []
    current_section: str | None = None
    anchor_counts: dict[str, int] = {}
    matrix_count = 0

    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        section_match = SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group("section_id")
            section_titles[current_section] = section_match.group("title")
            anchor_counts.setdefault(current_section, 0)
            continue
        if current_section in EXPECTED_ANCHOR_COUNTS:
            anchor_match = ANCHOR_RE.match(line)
            if anchor_match:
                anchor_counts[current_section] += 1
                urls = tuple(url.rstrip(".,") for url in URL_RE.findall(line))
                anchors.append(
                    ResearchAnchor(
                        anchor_id=f"{current_section}.{anchor_counts[current_section]}",
                        section_id=current_section,
                        section_title=section_titles[current_section],
                        title=anchor_match.group("title"),
                        body=anchor_match.group("body"),
                        urls=urls,
                    )
                )
            continue
        if current_section == "34.7" and line.startswith("|"):
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) != 2 or _is_table_header_or_separator(parts):
                continue
            matrix_count += 1
            finding, design_response = parts
            matrix_rows.append(
                TraceabilityRow(
                    row_id=f"34.7.{matrix_count}",
                    finding=finding,
                    design_response=design_response,
                    evidence=TRACEABILITY_EVIDENCE_BY_FINDING.get(finding, ()),
                )
            )
    return anchors, matrix_rows, section_titles


def validate_traceability_report(
    anchors: list[ResearchAnchor],
    matrix_rows: list[TraceabilityRow],
    section_titles: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    for section_id, expected_count in EXPECTED_ANCHOR_COUNTS.items():
        if section_id not in section_titles:
            errors.append(f"missing anchor section: {section_id}")
            continue
        actual_count = sum(1 for anchor in anchors if anchor.section_id == section_id)
        if actual_count != expected_count:
            errors.append(
                f"{section_id} anchor count changed: expected {expected_count}, got {actual_count}"
            )
    if "34.7" not in section_titles:
        errors.append("missing traceability matrix section: 34.7")
    if len(anchors) != sum(EXPECTED_ANCHOR_COUNTS.values()):
        errors.append(
            "total anchor count changed: "
            f"expected {sum(EXPECTED_ANCHOR_COUNTS.values())}, got {len(anchors)}"
        )
    anchors_with_urls = sum(1 for anchor in anchors if anchor.urls)
    if anchors_with_urls != EXPECTED_ANCHORS_WITH_URLS:
        errors.append(
            f"URL-backed anchor count changed: expected {EXPECTED_ANCHORS_WITH_URLS}, got {anchors_with_urls}"
        )
    if len(matrix_rows) != EXPECTED_MATRIX_ROWS:
        errors.append(
            f"traceability row count changed: expected {EXPECTED_MATRIX_ROWS}, got {len(matrix_rows)}"
        )
    seen_anchor_ids: set[str] = set()
    for anchor in anchors:
        if anchor.anchor_id in seen_anchor_ids:
            errors.append(f"duplicate anchor id: {anchor.anchor_id}")
        seen_anchor_ids.add(anchor.anchor_id)
        if not anchor.title.strip():
            errors.append(f"{anchor.anchor_id} has empty title")
        if not anchor.body.strip():
            errors.append(f"{anchor.anchor_id} has empty body")
        _validate_no_placeholder(errors, anchor.anchor_id, anchor.title)
        _validate_no_placeholder(errors, anchor.anchor_id, anchor.body)
    seen_row_ids: set[str] = set()
    seen_findings: set[str] = set()
    for row in matrix_rows:
        if row.row_id in seen_row_ids:
            errors.append(f"duplicate traceability row id: {row.row_id}")
        seen_row_ids.add(row.row_id)
        if row.finding in seen_findings:
            errors.append(f"duplicate traceability finding: {row.finding}")
        seen_findings.add(row.finding)
        if not row.finding.strip():
            errors.append(f"{row.row_id} has empty finding")
        if not row.design_response.strip():
            errors.append(f"{row.row_id} has empty design response")
        if not row.evidence:
            errors.append(f"{row.row_id} has no repo evidence mapping for: {row.finding}")
        for value in (*row.evidence, row.finding, row.design_response):
            _validate_no_placeholder(errors, row.row_id, value)
    missing_evidence = sorted(set(TRACEABILITY_EVIDENCE_BY_FINDING) - seen_findings)
    for finding in missing_evidence:
        errors.append(f"unused traceability evidence mapping: {finding}")
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SkillKernel Research Traceability Report",
        "",
        f"Ready: {str(report['ready']).lower()}",
        f"Anchor sections: {report['summary']['anchor_sections']}",
        f"Research anchors: {report['summary']['anchors']}",
        f"URL-backed anchors: {report['summary']['anchors_with_urls']}",
        f"Traceability rows: {report['summary']['traceability_rows']}",
        "",
        "## Anchor Sections",
    ]
    for section in report["anchor_sections"]:
        lines.append(
            f"- {section['section_id']} {section['title']}: {section['anchor_count']} anchors"
        )
    lines.append("")
    lines.append("## Traceability Matrix")
    for row in report["traceability_matrix"]:
        lines.append(f"- {row['row_id']}: {row['finding']}")
        lines.append(f"  - Design: {row['design_response']}")
        for evidence in row["evidence"]:
            lines.append(f"  - Evidence: {evidence}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit the SkillKernel Section 34 research traceability crosswalk.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC_PATH,
        help="Path to the unified implementation specification.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.spec)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["ready"] else 1


def _read_section_34(spec_path: Path) -> str:
    text = spec_path.read_text(encoding="utf-8")
    try:
        after_start = text.split(SECTION_START, 1)[1]
    except IndexError as error:
        raise SystemExit(f"missing Section 34 marker in {spec_path}") from error
    if SECTION_END not in after_start:
        raise SystemExit(f"missing Section 35 marker after Section 34 in {spec_path}")
    return after_start.split(SECTION_END, 1)[0]


def _is_table_header_or_separator(parts: list[str]) -> bool:
    if parts == ["Research or platform finding", "design response"]:
        return True
    return all(part and set(part) <= {"-", " "} for part in parts)


def _validate_no_placeholder(errors: list[str], item_id: str, value: str) -> None:
    lowered = value.lower()
    if "todo" in lowered or "tbd" in lowered:
        errors.append(f"{item_id} has placeholder text: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
