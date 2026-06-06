
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC_PATH = ROOT / "unified-implementation-specification.md"
SECTION_35 = "### 35. Comprehensive landscape assimilation matrix"
SECTION_35_END = "\n# Part II"
SECTION_READINESS = "## 8. Implementation readiness checklist"
SECTION_READINESS_END = "\n## 9. Implementation integrity rule"

EXPECTED_LANDSCAPE_ROWS = 52
EXPECTED_STANCE_LINES = 8
EXPECTED_READINESS_CHECKLIST_ITEMS = 17

LANDSCAPE_EVIDENCE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("transcript", "trajectory", "experience", "historical", "rag ingestion"),
        (
            "historical import/discovery/parser pipeline",
            "redacted evidence derivation and bootstrap consolidation",
        ),
    ),
    (
        ("similar-skill", "matching", "duplicate", "merge", "active/archived"),
        (
            "active/archived matching and external collision review",
            "utility curation merge/archive/promote actions",
        ),
    ),
    (
        ("bounded", "validation", "rejected", "held-out", "regression"),
        (
            "proposal-gate evaluator with target/regression/no-skill/adversarial probes",
            "repair materialization remains staged until activation gates pass",
        ),
    ),
    (
        ("memory", "poison"),
        (
            "memory quarantine, taint, provenance, and revocation traversal",
            "memory-influenced broker and writer paths fail closed without approval",
        ),
    ),
    (
        ("skillir", "pseudocode", "typed", "structure", "runtime artifact"),
        (
            "canonical SkillIR plus deterministic compiler",
            "compiled runtime SKILL.md uses fixed AI-facing sections",
        ),
    ),
    (
        ("graph", "compose", "decompose", "topology", "granularity", "orchestration"),
        (
            "SkillGraphIR create/improve/compose/decompose operations",
            "topology planners, trials, metrics, and rollback actions",
        ),
    ),
    (
        ("failed", "contrast", "intervention", "no-skill", "utility", "marginal"),
        (
            "contrastive evidence and no-skill controls",
            "context-value/token utility rollups and curation actions",
        ),
    ),
    (
        ("verifier", "probe", "benchmark", "validator", "grade", "skillsbench", "openskill"),
        (
            "probe planner and deterministic evaluator records",
            "external benchmark/validator adapter seam in evaluator-compatible outputs",
        ),
    ),
    (
        ("tenant", "cross-user", "federation"),
        (
            "workspace-scoped provenance and source roots",
            "no default cross-user sharing in v1",
        ),
    ),
    (
        ("broker", "router", "routing", "injection", "context", "token", "compression"),
        (
            "runtime broker, body-aware retrieval, and broker policy canaries",
            "context compiler, token budget governor, and context artifacts",
        ),
    ),
    (
        ("support", "script", "package", "manifest", "skill packages", "immutable"),
        (
            "support artifact planner and writer hash manifests",
            "archive-backed immutable active package snapshots",
        ),
    ),
    (
        ("harmful", "inject", "malicious", "security", "owasp", "slsa", "trojan", "trap", "backdoor"),
        (
            "deterministic scanner/red-team smoke and capability manifests",
            "audit hash chain, action attribution, and deterministic writer gates",
        ),
    ),
    (
        ("profile", "model", "embedding", "executor", "harness", "vm"),
        (
            "executor/model/embedding profile APIs and qualification gates",
            "profile-scoped embedding generation and compatibility records",
        ),
    ),
    (
        ("repair", "maintenance", "retire", "adapter"),
        (
            "diagnostic momentum and conservative repair execution",
            "utility curation archive/merge/repair planning",
        ),
    ),
    (
        ("curation", "delayed-feedback", "long-horizon"),
        (
            "utility rollups preserve delayed outcome and context-value features",
            "curation actions remain evidence-gated before mutation",
        ),
    ),
    (
        ("codex", "cross-agent", "ecosystem isolation"),
        (
            "OpenClaw-compatible SKILL.md artifacts are emitted from SkillIR",
            "no Codex-specific runtime dependency is introduced",
        ),
    ),
)

ARCHITECTURE_EVIDENCE_BY_ITEM: dict[str, tuple[str, ...]] = {
    "one OpenClaw plugin": (
        "plugin/autoskill package with typed hook registration",
        "plugin/autoskill/test/hook-smoke.test.js",
    ),
    "one Python sidecar": (
        "sidecar/autoskill API, stores, services, and worker entrypoint",
        "uv run pytest -q",
    ),
    "one Postgres database": (
        "single SKILLKERNEL_DATABASE_URL/AUTOSKILL_DATABASE_URL setting",
        "docker compose config --quiet",
    ),
    "one autoskill schema": (
        "migrations/0001_autoskill_schema.sql creates one autoskill schema",
        "scripts/autoskill_acceptance.py criterion 31.4",
    ),
    "pgvector": (
        "profile-scoped pgvector embedding records and recall audit",
        "sidecar/autoskill/tests/test_embedding_generation.py",
    ),
    "SkillIR as canonical source of truth": (
        "sidecar/autoskill/core/skillir.py",
        "SkillIR compiler renders runtime artifacts from canonical SkillIR",
    ),
    "OpenClaw SKILL.md as compiled runtime artifact": (
        "deterministic SkillIR -> SKILL.md compiler",
        "writer manifest hashes SKILL.md before activation",
    ),
    "sidecar-owned scheduler": (
        "autoskill.db.scheduler and scheduler_defaults",
        "sidecar/autoskill/tests/test_scheduler_api.py",
    ),
    "runtime skill-context broker": (
        "autoskill.services.broker and /v1/runtime/context-hint",
        "sidecar/autoskill/tests/test_broker.py",
    ),
    "calibrated selective-trust controller": (
        "proposal-gate autonomy_assurance separates hard invariants from soft thresholds",
        "sidecar/autoskill/tests/test_evaluator.py",
    ),
    "autonomy calibration corpus": (
        "broker replay episodes, policy replay/canary feedback, and evaluator autonomy-assurance outputs",
        "sidecar/autoskill/tests/test_broker_policy_api.py and test_evaluator.py",
    ),
    "context compiler + token budget governor": (
        "context_artifacts/context_compile_runs and compiler token gates",
        "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
    ),
    "diagnostic momentum store": (
        "autoskill.db.diagnostics and /v1/diagnostics/momentum",
        "sidecar/autoskill/tests/test_admin_surfaces.py",
    ),
    "SkillIR effect signatures": (
        "SkillIR.effect_signature() and effect-signature validation",
        "sidecar/autoskill/core/skillir.py",
    ),
    "SkillGraphIR for composed/decomposed workflow topology": (
        "SkillGraphIR operation kinds and topology services",
        "sidecar/autoskill/tests/test_topology_services.py",
    ),
    "ephemeral candidate lane": (
        "candidate lifecycle states and inactive proposal persistence",
        "candidate proposals stay inactive until scanner/evaluator gates pass",
    ),
    "co-evolved verifier/probe lane": (
        "probe planner and proposal-gate evaluator",
        "external verifier/benchmark adapter seam in evaluator outputs",
    ),
    "external benchmark/validator adapter seam": (
        "executor-profile-aware evaluator records",
        "profile compatibility and external grader adapter-compatible metadata",
    ),
    "runtime immutability lock": (
        "writer stages new manifests and archive-backed snapshots",
        "active artifacts are not rewritten in place during broker use",
    ),
    "trace-spine observability": (
        "trace_id/span_id propagation across jobs, events, retrieval, embeddings, and writer spans",
        "sidecar/autoskill/tests/test_admin_surfaces.py",
    ),
    "operator-configurable text LLM profile": (
        "model profile APIs and text profile qualification",
        "sidecar/autoskill/tests/test_profile_qualification.py",
    ),
    "operator-configurable embedding profile": (
        "embedding profile APIs and production validation",
        "sidecar/autoskill/tests/test_profile_qualification.py",
    ),
    "model/embedding profile qualification gates": (
        "/v1/profiles/models/qualify and /v1/profiles/embeddings/qualify",
        "sidecar/autoskill/tests/test_profile_qualification.py",
    ),
    "SLSA-style artifact provenance manifests": (
        "writer manifests include hashes, gate status, provenance, and rollback pointers",
        "sidecar/autoskill/tests/test_audit_writer_events.py",
    ),
    "no direct dollar-cost tracker/analyzer": (
        "v1 records model/embedding invocations as content-safe telemetry, not dollar-cost optimization",
        "unified readiness report preserves the explicit exclusion",
    ),
    "no per-operation model-routing matrix in v1": (
        "operator-configurable profiles are explicit; no per-operation routing matrix is implemented",
        "unified readiness report preserves the explicit exclusion",
    ),
    "no per-skill databases": (
        "README Non-Negotiables",
        "scripts/autoskill_acceptance.py criterion 31.3",
    ),
    "no per-skill schemas in v1": (
        "README Non-Negotiables",
        "scripts/autoskill_acceptance.py criterion 31.4",
    ),
    "no OpenClaw Cron dependency": (
        "sidecar-owned scheduler",
        "scripts/autoskill_acceptance.py criterion 31.1",
    ),
    "no Skill Workshop dependency": (
        "sidecar-owned proposal/scanner/evaluator/writer lifecycle",
        "scripts/autoskill_acceptance.py criterion 31.2",
    ),
}

ORDER_EVIDENCE_BY_STEP: dict[str, tuple[str, ...]] = {
    "redaction": (
        "autoskill.core.redaction and plugin redaction",
        "sidecar/autoskill/tests/test_ingest_auth.py",
    ),
    "storage": (
        "migrations/0001_autoskill_schema.sql",
        "event/job/skill/evidence/retrieval/governance stores",
    ),
    "executor profiles": (
        "executor/model/embedding profile APIs and compatibility records",
        "sidecar/autoskill/tests/test_admin_surfaces.py",
    ),
    "scheduler": (
        "sidecar-owned scheduler store/default schedules",
        "sidecar/autoskill/tests/test_scheduler_defaults.py",
    ),
    "trace spine": (
        "trace_id/span_id propagation and content-safe spans",
        "sidecar/autoskill/tests/test_admin_surfaces.py",
    ),
    "evolution transaction/provenance/revocation tables": (
        "autoskill.db.governance transaction/provenance/revocation stores",
        "sidecar/autoskill/tests/test_governance.py",
    ),
    "historical ingestion bootstrap": (
        "historical discovery/import/bootstrap services",
        "sidecar/autoskill/tests/test_historical_bootstrap.py",
    ),
    "event/evidence/memory pipeline": (
        "redacted ingest -> evidence derivation -> memory quarantine/control flow",
        "sidecar/autoskill/tests/test_event_store.py and test_historical_import.py",
    ),
    "memory quarantine": (
        "memory quarantine APIs and broker/writer trust gates",
        "TASKFLOW.md memory quarantine validation checkpoint",
    ),
    "autonomous semantic adjudication": (
        "typed LLM invocation audit plus deterministic proposal-gate autonomy assurance",
        "sidecar/autoskill/tests/test_llm_client.py and test_evaluator.py",
    ),
    "autonomy calibration corpus and selective-trust policy trials": (
        "broker replay/canary policy records plus threshold-deadlock candidate summaries",
        "sidecar/autoskill/tests/test_broker_policy_api.py and test_evaluator.py",
    ),
    "external-skill inventory": (
        "external skill root scanning/inventory/review APIs",
        "sidecar/autoskill/tests/test_external_skills.py",
    ),
    "body-level index documents": (
        "body_index_documents retrieval path",
        "sidecar/autoskill/tests/test_broker.py",
    ),
    "retrieval logs": (
        "retrieval log store and context token ledger",
        "scripts/autoskill_acceptance.py criterion 31.25",
    ),
    "context artifact registry": (
        "context_artifacts and context_compile_runs stores",
        "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
    ),
    "token budget governor": (
        "compiler/writer token_count, max_tokens, budget_status gates",
        "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
    ),
    "semantic compression/equivalence gates": (
        "semantic compression trials and routing-equivalence evidence",
        "sidecar/autoskill/tests/test_admin_surfaces.py",
    ),
    "scanner": (
        "deterministic scanner and red-team smoke",
        "scripts/autoskill_red_team.py",
    ),
    "evaluator/probes": (
        "proposal-gate evaluator and probe planner",
        "sidecar/autoskill/tests/test_evaluator.py",
    ),
    "deterministic writer": (
        "path-contained writer apply/archive/rollback",
        "sidecar/autoskill/tests/test_audit_writer_events.py",
    ),
    "rollback": (
        "archive-backed rollback and revocation rollback worker paths",
        "sidecar/autoskill/tests/test_lifecycle.py",
    ),
    "action-attribution logs/checks": (
        "action_attribution_checks and before_tool_call boundary path",
        "sidecar/autoskill/tests/test_attribution.py",
    ),
    "SkillIR effect-signature validation": (
        "SkillIR effect_signature fields and validation",
        "sidecar/autoskill/core/skillir.py",
    ),
    "SkillIR compiler": (
        "autoskill.services.compiler",
        "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
    ),
    "diagnostic momentum store": (
        "autoskill.db.diagnostics and repair execution from momentum",
        "sidecar/autoskill/tests/test_worker.py",
    ),
    "runtime broker": (
        "autoskill.services.broker and runtime context-hint API",
        "sidecar/autoskill/tests/test_broker.py",
    ),
    "topology operation candidate generation": (
        "usage-backed topology proposals and topology services",
        "sidecar/autoskill/tests/test_topology_services.py",
    ),
    "composition/decomposition evaluators": (
        "broker replay/canary trials for compose/decompose",
        "sidecar/autoskill/tests/test_topology_services.py",
    ),
    "autonomous apply": (
        "mutation worker apply remains policy-approved and activation-gated",
        "scripts/autoskill_handoff.py ship gate",
    ),
    "marginal-value curation": (
        "utility rollups and curation repair/archive/merge/promote planning",
        "sidecar/autoskill/tests/test_utility.py",
    ),
    "broker policy canaries": (
        "broker policy versions and canary feedback rollback",
        "sidecar/autoskill/tests/test_broker_policy_api.py",
    ),
}


@dataclass(frozen=True)
class LandscapeRow:
    row_id: str
    source: str
    useful_finding: str
    adoption: str
    not_adopted: str
    urls: tuple[str, ...]
    evidence: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "source": self.source,
            "useful_finding": self.useful_finding,
            "adoption": self.adoption,
            "not_adopted": self.not_adopted,
            "urls": list(self.urls),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class ReadinessItem:
    item_id: str
    item: str
    status: str
    evidence: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item": self.item,
            "status": self.status,
            "evidence": list(self.evidence),
        }


def build_report(spec_path: Path = DEFAULT_SPEC_PATH) -> dict[str, Any]:
    spec = spec_path.read_text(encoding="utf-8")
    section_35 = _read_between(spec, SECTION_35, SECTION_35_END)
    readiness_section = _read_between(spec, SECTION_READINESS, SECTION_READINESS_END)
    landscape_rows = parse_landscape_rows(section_35)
    stance = parse_stance(section_35)
    readiness_checklist = parse_readiness_checklist(readiness_section)
    validation_errors = validate_readiness_report(
        landscape_rows,
        stance,
        readiness_checklist,
    )
    return {
        "schema": "autoskill.landscape-readiness-report.v2",
        "ready": not validation_errors,
        "source": str(spec_path),
        "summary": {
            "landscape_rows": len(landscape_rows),
            "stance_lines": len(stance),
            "readiness_checklist_items": len(readiness_checklist),
            "validation_errors": validation_errors,
        },
        "landscape_matrix": [row.to_json() for row in landscape_rows],
        "adopted_stance": stance,
        "readiness_checklist": [item.to_json() for item in readiness_checklist],
    }


def parse_readiness_checklist(readiness_section: str) -> list[ReadinessItem]:
    items: list[ReadinessItem] = []
    for line in readiness_section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- [ ] "):
            continue
        item = stripped.removeprefix("- [ ] ").strip()
        items.append(
            ReadinessItem(
                item_id=f"readiness.{len(items) + 1}",
                item=item,
                status="required",
                evidence=(),
            )
        )
    return items


def parse_landscape_rows(section_35: str) -> list[LandscapeRow]:
    rows: list[LandscapeRow] = []
    for line in section_35.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) != 4 or _is_table_header_or_separator(parts):
            continue
        source, useful_finding, adoption, not_adopted = parts
        rows.append(
            LandscapeRow(
                row_id=f"35.{len(rows) + 1}",
                source=source,
                useful_finding=useful_finding,
                adoption=adoption,
                not_adopted=not_adopted,
                urls=tuple(url.rstrip(".,") for url in re.findall(r"https?://[^\s,)]+", not_adopted)),
                evidence=_landscape_evidence_for(" ".join(parts)),
            )
        )
    return rows


def parse_stance(section_35: str) -> list[str]:
    match = re.search(
        r"The adopted SkillKernel stance is therefore:\s+```text\n(?P<stance>.*?)\n```",
        section_35,
        flags=re.S,
    )
    if not match:
        return []
    return [line.strip() for line in match.group("stance").splitlines() if line.strip()]


def parse_section_36(
    section_36: str,
) -> tuple[list[ReadinessItem], list[ReadinessItem], list[ReadinessItem]]:
    blocks = re.findall(r"```text\n(.*?)\n```", section_36, flags=re.S)
    if len(blocks) < 3:
        return [], [], []
    architecture_lines = [line.strip() for line in blocks[0].splitlines() if line.strip()]
    product_lines = [line.strip() for line in blocks[1].splitlines() if line.strip()]
    order_lines = [
        line.replace("->", "→").lstrip("→ ").strip()
        for line in blocks[2].splitlines()
        if line.strip()
    ]
    architecture = [
        ReadinessItem(
            item_id=f"36.arch.{index}",
            item=item,
            status="excluded" if item.startswith("no ") else "implemented",
            evidence=ARCHITECTURE_EVIDENCE_BY_ITEM.get(item, ()),
        )
        for index, item in enumerate(architecture_lines, start=1)
    ]
    operations = []
    for line in product_lines:
        if "=" not in line:
            continue
        operation, definition = [part.strip() for part in line.split("=", 1)]
        operations.append(
            ReadinessItem(
                item_id=f"36.product.{len(operations) + 1}",
                item=f"{operation}: {definition}",
                status="implemented",
                evidence=(
                    "SkillGraphIR operation kind and topology service support",
                    "sidecar/autoskill/tests/test_topology_services.py",
                ),
            )
        )
    implementation_order = [
        ReadinessItem(
            item_id=f"36.order.{index}",
            item=step,
            status="implemented",
            evidence=ORDER_EVIDENCE_BY_STEP.get(step, ()),
        )
        for index, step in enumerate(order_lines, start=1)
    ]
    return architecture, operations, implementation_order


def validate_readiness_report(
    landscape_rows: list[LandscapeRow],
    stance: list[str],
    readiness_checklist: list[ReadinessItem],
) -> list[str]:
    errors: list[str] = []
    if len(landscape_rows) != EXPECTED_LANDSCAPE_ROWS:
        errors.append(
            f"landscape row count changed: expected {EXPECTED_LANDSCAPE_ROWS}, got {len(landscape_rows)}"
        )
    if len(stance) != EXPECTED_STANCE_LINES:
        errors.append(f"stance line count changed: expected {EXPECTED_STANCE_LINES}, got {len(stance)}")
    if len(readiness_checklist) != EXPECTED_READINESS_CHECKLIST_ITEMS:
        errors.append(
            "readiness checklist item count changed: "
            f"expected {EXPECTED_READINESS_CHECKLIST_ITEMS}, got {len(readiness_checklist)}"
        )
    for row in landscape_rows:
        if not row.source or not row.useful_finding or not row.adoption or not row.not_adopted:
            errors.append(f"{row.row_id} has empty landscape column")
        if not row.urls:
            errors.append(f"{row.row_id} has no source URL")
        if not row.evidence:
            errors.append(f"{row.row_id} has no implementation evidence mapping: {row.source}")
        _validate_no_placeholder(errors, row.row_id, row.source)
        _validate_no_placeholder(errors, row.row_id, row.adoption)
        _validate_no_placeholder(errors, row.row_id, row.not_adopted)
    seen_items: set[str] = set()
    for item in readiness_checklist:
        if item.item in seen_items:
            errors.append(f"duplicate readiness checklist item: {item.item}")
        seen_items.add(item.item)
        if item.status != "required":
            errors.append(f"{item.item_id} has unsupported status: {item.status}")
        _validate_no_placeholder(errors, item.item_id, item.item)
    required_stance = {
        "Generate less.",
        "Validate more.",
        "Compile tighter.",
        "Route smarter.",
        "Attribute causally.",
        "Evolve transactionally.",
        "Compose/decompose topology deliberately.",
        "Treat every context token and every support artifact as production surface area.",
    }
    if set(stance) != required_stance:
        errors.append("adopted stance changed")
    checklist_text = " ".join(item.item for item in readiness_checklist).lower()
    for operation in ("create", "improve", "compose", "decompose"):
        if operation not in checklist_text:
            errors.append(f"readiness checklist no longer mentions {operation}")
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SkillKernel Landscape And Readiness Report",
        "",
        f"Ready: {str(report['ready']).lower()}",
        f"Landscape rows: {report['summary']['landscape_rows']}",
        f"Readiness checklist items: {report['summary']['readiness_checklist_items']}",
        "",
        "## Adopted Stance",
    ]
    for line in report["adopted_stance"]:
        lines.append(f"- {line}")
    lines.append("")
    lines.append("## Implementation Readiness Checklist")
    for item in report["readiness_checklist"]:
        lines.append(f"- {item['item_id']} {item['status']}: {item['item']}")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit the SkillKernel unified landscape and readiness checklist crosswalk.",
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


def _read_between(text: str, start: str, end: str) -> str:
    try:
        after_start = text.split(start, 1)[1]
    except IndexError as error:
        raise SystemExit(f"missing marker: {start}") from error
    if end not in after_start:
        raise SystemExit(f"missing marker after {start}: {end}")
    return after_start.split(end, 1)[0]


def _landscape_evidence_for(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    evidence: list[str] = []
    for needles, mapped in LANDSCAPE_EVIDENCE_RULES:
        if any(needle in lowered for needle in needles):
            evidence.extend(mapped)
    deduped: list[str] = []
    for item in evidence:
        if item not in deduped:
            deduped.append(item)
    return tuple(deduped)


def _is_table_header_or_separator(parts: list[str]) -> bool:
    if parts == ["Source", "Useful finding", "SkillKernel adoption", "Not adopted / reason"]:
        return True
    return all(part and set(part) <= {"-", " "} for part in parts)


def _validate_no_placeholder(errors: list[str], item_id: str, value: str) -> None:
    lowered = value.lower()
    if "todo" in lowered or "tbd" in lowered:
        errors.append(f"{item_id} has placeholder text: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
