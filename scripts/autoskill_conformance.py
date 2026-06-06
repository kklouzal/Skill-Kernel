#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC_PATH = ROOT / "unified-implementation-specification.md"
MIGRATION_PATH = ROOT / "migrations" / "0001_autoskill_schema.sql"
README_PATH = ROOT / "README.md"

PRODUCTION_PATHS = (
    ROOT / "sidecar" / "autoskill" / "api",
    ROOT / "sidecar" / "autoskill" / "core",
    ROOT / "sidecar" / "autoskill" / "db",
    ROOT / "sidecar" / "autoskill" / "services",
    ROOT / "sidecar" / "autoskill" / "observatory" / "src",
    ROOT / "plugin" / "autoskill" / "src",
    ROOT / "migrations",
)

TOPOLOGY_OPERATIONS = ("create", "improve", "compose", "decompose")
EVIDENCE_MODES = (
    "raw_vault_linked",
    "declassified_summary",
    "redacted_derivative",
    "metadata_only",
    "hash_only",
)
OBSERVATORY_LEVELS = (
    "system map",
    "subsystem workcell",
    "station cockpit",
    "object microscope",
)
ARCHITECTURE_INVARIANTS = (
    "one OpenClaw plugin",
    "one Python sidecar",
    "one Postgres database",
    "one autoskill schema",
    "generated OpenClaw `SKILL.md` files as runtime artifacts",
    "No OpenClaw Cron dependency",
    "No Skill Workshop dependency",
    "No LLM-controlled SQL",
)


@dataclass(frozen=True)
class StaticCheck:
    check_id: str
    description: str
    evidence: tuple[str, ...]
    passed: bool
    details: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "description": self.description,
            "passed": self.passed,
            "evidence": list(self.evidence),
            "details": list(self.details),
        }


def build_report(spec_path: Path = DEFAULT_SPEC_PATH) -> dict[str, Any]:
    checks = [
        _check_markdown_fences(),
        _check_no_planning_placeholders(),
        _check_no_external_gate_shortcuts(spec_path),
        _check_no_skill_package_self_registration(spec_path),
        _check_no_raw_vault_streaming(),
        _check_no_raw_private_read_model_defaults(),
        _check_no_unstable_react_keys(),
        _check_migration_deduplicated_and_ordered(),
        _check_architecture_invariants(spec_path),
        _check_inter_container_compatibility(),
        _check_topology_operations_present(),
        _check_evidence_modes_present(),
        _check_observatory_levels_present(spec_path),
    ]
    failures = [check for check in checks if not check.passed]
    return {
        "schema": "autoskill.implementation-conformance-report.v1",
        "ready": not failures,
        "source": str(spec_path),
        "summary": {
            "checks": len(checks),
            "passed": len(checks) - len(failures),
            "failed": len(failures),
            "validation_errors": [
                f"{check.check_id}: {detail or check.description}"
                for check in failures
                for detail in (check.details or ("failed",))
            ],
        },
        "checks": [check.to_json() for check in checks],
    }


def _check_markdown_fences() -> StaticCheck:
    details: list[str] = []
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        count = path.read_text(encoding="utf-8").count("```")
        if count % 2:
            details.append(f"{_rel(path)} has unbalanced fenced code blocks")
    return _result(
        "SKX-STATIC-001",
        "balanced Markdown code fences",
        ("all repository Markdown files",),
        details,
    )


def _check_no_planning_placeholders() -> StaticCheck:
    details = _scan_paths(
        PRODUCTION_PATHS,
        re.compile(
            r"\b(TODO|TBD|FIXME|STUB|NotImplementedError)\b|"
            r"placeholder migration|fake health|mocked green",
            re.I,
        ),
    )
    return _result(
        "SKX-STATIC-002",
        "no unresolved planning-placeholder markers in production paths",
        ("sidecar/plugin production code", "migrations"),
        details,
    )


def _check_no_external_gate_shortcuts(spec_path: Path) -> StaticCheck:
    spec = spec_path.read_text(encoding="utf-8")
    section = _read_between(
        spec,
        "## 2. Evidence sufficiency and autonomy assurance",
        "## 3. Semantic adjudication assurance",
    )
    forbidden = (
        "default to administrative escalation",
        "routine administrative escalation",
        "external gate replaces semantic adjudication",
    )
    details = [f"forbidden external-gate shortcut: {phrase}" for phrase in forbidden if phrase in section]
    return _result(
        "SKX-STATIC-003",
        "no normative ad hoc external-gate language in autonomous semantic paths",
        ("Part V evidence sufficiency assurance text",),
        details,
    )


def _check_no_skill_package_self_registration(spec_path: Path) -> StaticCheck:
    spec = spec_path.read_text(encoding="utf-8")
    section = _read_between(
        spec,
        "## 5. Skill-package completeness assurance",
        "## 6. Capability-surface assurance",
    )
    forbidden = tuple(
        re.compile(pattern, re.I)
        for pattern in (
            r"\bmay\s+self-register\s+(?:hooks|tools|schedulers|cron)",
            r"\ballowed\s+to\s+self-register\s+(?:hooks|tools|schedulers|cron)",
            r"\bauto-install\s+(?:plugin|hook|tool|scheduler|cron)",
        )
    )
    details = [
        f"skill-package assurance implies self-registration: {match.group(0)}"
        for pattern in forbidden
        for match in pattern.finditer(section)
    ]
    return _result(
        "SKX-STATIC-004",
        "no skill-package examples imply hook/tool/scheduler self-registration",
        ("Part V skill-package completeness assurance",),
        details,
    )


def _check_no_raw_vault_streaming() -> StaticCheck:
    app = (ROOT / "sidecar" / "autoskill" / "api" / "app.py").read_text(encoding="utf-8")
    stream_sections = [
        _read_between(app, '@app.websocket("/admin/live")', '@app.get("/admin/live-sse")'),
        _read_between(app, '@app.get("/admin/live-sse")', 'return StreamingResponse('),
    ]
    details = []
    for index, section in enumerate(stream_sections, start=1):
        if re.search(r"raw[_-]?vault|raw_content|raw_payload|raw_prompt", section, re.I):
            details.append(f"admin live stream section {index} references raw-vault/raw content")
    return _result(
        "SKX-STATIC-005",
        "no raw-vault live-stream endpoint",
        ("sidecar/autoskill/api/app.py admin live routes",),
        details,
    )


def _check_no_raw_private_read_model_defaults() -> StaticCheck:
    app = (ROOT / "sidecar" / "autoskill" / "api" / "app.py").read_text(encoding="utf-8")
    details: list[str] = []
    if '"raw_vault_records_returned": False' not in app:
        details.append("raw-vault summary does not explicitly report raw_vault_records_returned=false")
    forbidden = re.compile(r"raw_(?:content|payload|prompt|message|transcript)\s*[:=]", re.I)
    for match in forbidden.finditer(app):
        line = app.count("\n", 0, match.start()) + 1
        details.append(f"raw private payload field assignment in app.py:{line}")
    return _result(
        "SKX-STATIC-006",
        "no read-model endpoint returns raw private payloads by default",
        ("raw-vault summary route content policy",),
        details,
    )


def _check_no_unstable_react_keys() -> StaticCheck:
    src = ROOT / "sidecar" / "autoskill" / "observatory" / "src"
    pattern = re.compile(
        r"key=\{[^}\n]*(?:Date\.now|Math\.random|randomUUID|snapshot_seq|snapshotSeq|snapshot\.seq|lastUpdatedAt|poll(?:ing)?Counter)[^}\n]*\}",
        re.I,
    )
    return _result(
        "SKX-STATIC-007",
        "no React keys based on snapshot sequence, refresh timestamp, polling counter, or random value",
        ("Observatory React source",),
        _scan_paths((src,), pattern),
    )


def _check_migration_deduplicated_and_ordered() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    if migration.count("CREATE EXTENSION IF NOT EXISTS vector") != 1:
        details.append("vector extension setup is missing or duplicated")
    if migration.count("CREATE SCHEMA IF NOT EXISTS autoskill") != 1:
        details.append("autoskill schema setup is missing or duplicated")
    first_table = _first_index(migration, "CREATE TABLE")
    for setup in ("CREATE EXTENSION IF NOT EXISTS vector", "CREATE EXTENSION IF NOT EXISTS pgcrypto", "CREATE SCHEMA IF NOT EXISTS autoskill"):
        setup_index = _first_index(migration, setup)
        if setup_index < 0:
            details.append(f"missing migration setup: {setup}")
        elif first_table >= 0 and setup_index > first_table:
            details.append(f"migration setup occurs after first table: {setup}")
    if "conceptual schema contract" in migration or "copy from specification" in migration.lower():
        details.append("migration contains conceptual/example-copy marker")
    return _result(
        "SKX-STATIC-008",
        "no migration example copied directly without deduplication and topological-order validation",
        ("migrations/0001_autoskill_schema.sql",),
        details,
    )


def _check_architecture_invariants(spec_path: Path) -> StaticCheck:
    text = "\n".join(
        (
            spec_path.read_text(encoding="utf-8"),
            README_PATH.read_text(encoding="utf-8"),
        )
    )
    details = [f"missing architecture invariant: {item}" for item in ARCHITECTURE_INVARIANTS if item not in text]
    return _result(
        "SKX-STATIC-009",
        "all top-level architecture invariants present",
        ("unified implementation specification", "README Non-Negotiables"),
        details,
    )


def _check_inter_container_compatibility() -> StaticCheck:
    app = (ROOT / "sidecar" / "autoskill" / "api" / "app.py").read_text(encoding="utf-8")
    tests = (ROOT / "sidecar" / "autoskill" / "tests" / "test_compatibility.py").read_text(encoding="utf-8")
    details: list[str] = []
    for route in ('"/v1/health"', '"/v1/config/effective"', '"/v1/profiles/compatibility"'):
        if route not in app:
            details.append(f"missing compatibility/readiness route: {route}")
    if "/v1/profiles/compatibility" not in tests:
        details.append("compatibility profile route is not exercised by test_compatibility.py")
    return _result(
        "SKX-STATIC-010",
        "inter-container API compatibility/version endpoints present and exercised",
        ("health/config/compatibility API routes", "sidecar/autoskill/tests/test_compatibility.py"),
        details,
    )


def _check_topology_operations_present() -> StaticCheck:
    corpus = _read_files(
        ROOT / "sidecar" / "autoskill" / "api" / "app.py",
        ROOT / "sidecar" / "autoskill" / "services" / "topology.py",
        MIGRATION_PATH,
    )
    details = [f"missing topology operation: {operation}" for operation in TOPOLOGY_OPERATIONS if operation not in corpus]
    return _result(
        "SKX-STATIC-011",
        "all four topology operations present: create, improve, compose, decompose",
        ("topology API/service", "canonical migration"),
        details,
    )


def _check_evidence_modes_present() -> StaticCheck:
    corpus = _read_files(MIGRATION_PATH, ROOT / "sidecar" / "autoskill" / "api" / "app.py")
    details = [f"missing evidence mode: {mode}" for mode in EVIDENCE_MODES if mode not in corpus]
    return _result(
        "SKX-STATIC-012",
        "all evidence modes present",
        ("admin_evidence_fidelity_status migration", "replay synthesis API"),
        details,
    )


def _check_observatory_levels_present(spec_path: Path) -> StaticCheck:
    corpus = _read_files(
        spec_path,
        ROOT / "scripts" / "autoskill_observatory_acceptance.py",
        ROOT / "sidecar" / "autoskill" / "observatory" / "src" / "App.tsx",
    ).lower()
    details = [f"missing Observatory level: {level}" for level in OBSERVATORY_LEVELS if level not in corpus]
    return _result(
        "SKX-STATIC-013",
        "all Observatory levels present: system map, subsystem workcell, station cockpit, object microscope",
        ("Part V Observatory assurance", "Observatory acceptance crosswalk", "Observatory UI source"),
        details,
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SkillKernel Implementation Conformance Report",
        "",
        f"Ready: {str(report['ready']).lower()}",
        f"Checks: {report['summary']['checks']}",
        f"Passed: {report['summary']['passed']}",
        f"Failed: {report['summary']['failed']}",
        "",
        "## Static Checks",
    ]
    for check in report["checks"]:
        status = "passed" if check["passed"] else "failed"
        lines.append(f"- {check['check_id']} {status}: {check['description']}")
        for detail in check["details"]:
            lines.append(f"  - {detail}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SkillKernel Part V implementation conformance static checks.",
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


def _result(
    check_id: str,
    description: str,
    evidence: tuple[str, ...],
    details: list[str],
) -> StaticCheck:
    return StaticCheck(
        check_id=check_id,
        description=description,
        evidence=evidence,
        passed=not details,
        details=tuple(details),
    )


def _scan_paths(paths: tuple[Path, ...], pattern: re.Pattern[str]) -> list[str]:
    details: list[str] = []
    for base in paths:
        files = [base] if base.is_file() else sorted(path for path in base.rglob("*") if path.is_file())
        for path in files:
            if path.suffix not in {".py", ".js", ".ts", ".tsx", ".sql"}:
                continue
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                details.append(f"{_rel(path)}:{line}: {match.group(0)[:120]}")
    return details


def _read_files(*paths: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _read_between(text: str, start: str, end: str) -> str:
    try:
        after_start = text.split(start, 1)[1]
    except IndexError:
        return ""
    if end not in after_start:
        return after_start
    return after_start.split(end, 1)[0]


def _first_index(text: str, needle: str) -> int:
    return text.find(needle)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
