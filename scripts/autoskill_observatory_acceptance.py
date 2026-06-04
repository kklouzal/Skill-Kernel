# ruff: noqa: E501, I001

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any


SATISFIED_STATUSES = {"implemented", "implemented_equivalent"}


@dataclass(frozen=True)
class ObservatoryItem:
    item_id: str
    text: str
    evidence: tuple[str, ...]
    status: str = "implemented"

    def to_json(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "text": self.text,
            "status": self.status,
            "evidence": list(self.evidence),
        }


ACCEPTANCE_CRITERIA: tuple[ObservatoryItem, ...] = (
    ObservatoryItem("21.1", "The sidecar serves the web UI and API from a configurable /admin base path.", ("sidecar/autoskill/api/app.py admin routes and static mount", "sidecar/autoskill/observatory/vite.config.ts")),
    ObservatoryItem("21.2", "Authentication is required for every non-liveness endpoint.", ("_require_admin_auth in sidecar/autoskill/api/app.py", "sidecar/autoskill/tests/test_observatory_api.py")),
    ObservatoryItem("21.3", "The overview graph shows every SkillKernel pipeline station and reflects live health.", ("24 StationDefinition entries in sidecar/autoskill/services/observatory.py", "test_observatory_api.py asserts 24 stations")),
    ObservatoryItem("21.4", "The overview graph uses custom station cards, semantic edges, label chips, selected states, and theme alignment.", ("sidecar/autoskill/observatory/src/components/AssemblyLine.tsx", "sidecar/autoskill/observatory/src/styles.css")),
    ObservatoryItem("21.5", "The overview graph avoids default demo styling and is complete enough for the main control-room map.", ("custom React Flow edge renderer and station card styles", "overview centerpiece CSS in styles.css")),
    ObservatoryItem("21.6", "Visual effects are performance-safe, data-backed, adaptive, and optional.", ("sidecar/autoskill/observatory/src/components/ParticleLayer.tsx", "reducedMotion gate in App.tsx")),
    ObservatoryItem("21.7", "Overview visual fixtures cover healthy, degraded, blocked, security, context-pressure, rollback/freeze, stale telemetry, reduced-motion, low-power, and WebGL fallback states.", ("sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json", "scripts/autoskill_observatory_fixtures.py", "stale telemetry and planned-evaluation tests in test_observatory_api.py", "reduced-motion and particle fallback frontend paths")),
    ObservatoryItem("21.8", "Each subsystem has an intermediate workcell lens.", ("SUBSYSTEMS in sidecar/autoskill/services/observatory.py", "Workcells component in App.tsx")),
    ObservatoryItem("21.9", "Each station has a drill-down cockpit with metrics, records, traces, config, audit, and help.", ("Cockpit tabs in App.tsx", "/admin/api/v1/components/{component_id} route")),
    ObservatoryItem("21.10", "The issue board surfaces actionable degraded, blocked, security, regression, freeze, stale telemetry, and data-quality conditions.", ("_issue_board in services/observatory.py", "test_observatory_stale_telemetry... coverage")),
    ObservatoryItem("21.11", "Live updates work through WebSocket and reconnect-safe snapshot/delta reconciliation.", ("observatory_live websocket and observatory_live_sse routes", "live SSE continuity tests")),
    ObservatoryItem("21.12", "Ordinary refresh cycles update visible components in place without unjustified route flash or graph blanking.", ("stable snapshot signatures in App.tsx", "AssemblyLine structuralKey layout preservation")),
    ObservatoryItem("21.13", "Background refetch preserves previous data and shows scoped live/stale state.", ("TanStack Query usage in App.tsx", "live-badge state and summary query cache updates")),
    ObservatoryItem("21.14", "React Flow and ECharts instances persist through metric refreshes.", ("AssemblyLine structural identity update effect", "EChartPanel receives keyed options without remount loops")),
    ObservatoryItem("21.15", "Global search and command palette locate traces, jobs, skills, candidates, artifacts, issues, imports, audit actions, and reason codes without raw content.", ("search_observatory in services/observatory.py", "search UI routing in App.tsx")),
    ObservatoryItem("21.16", "Object microscope pages expose summary, timeline, provenance, effects, content policy, diagnostics, and audit for major object types.", ("/admin/api/v1/objects/{object_type}/{object_id}", "_microscope_payload in services/observatory.py")),
    ObservatoryItem("21.17", "The UI can replay an individual trace through the pipeline without re-executing work.", ("TraceAndInspector in App.tsx", "/admin/api/v1/replay/traces/{trace_id}", "trace replay safety assertions in test_observatory_api.py")),
    ObservatoryItem("21.18", "Skill pages show SkillIR, SkillGraphIR, compiled artifacts, context budget, scanner/evaluator state, usage attribution, and rollback links.", ("SkillsAndTopology in App.tsx", "/admin/api/v1/skills and /admin/api/v1/context/artifacts")),
    ObservatoryItem("21.19", "Topology pages show create/improve/compose/decompose lineage and routing relationships.", ("/admin/api/v1/topology", "topology stations and operation metrics in services/observatory.py")),
    ObservatoryItem("21.20", "Context budget pages make SKILL.md, broker hint, support-context, and ignored-skill token pressure visible.", ("context artifacts API", "context compiler station records and token metrics")),
    ObservatoryItem("21.21", "Historical ingestion pages show discovery, dry-run, import progress, parser failures, taint/quarantine, evidence yielded, and seeded candidates.", ("historical import admin routes", "historical_ingestion station and tests")),
    ObservatoryItem("21.22", "Scanner/evaluator pages expose hard findings, probe results, regression state, and canary state.", ("scanner/evaluator station records", "/admin/api/v1/scanner-findings and /admin/api/v1/evaluations")),
    ObservatoryItem("21.23", "Autonomy pages expose evidence fidelity, raw-vault policy state, LLM semantic adjudications, deterministic admissibility checks, threshold policy versions, fallback ladders, threshold-deadlock findings, replay/canary corpus episodes, and administrative escalations.", ("semantic_adjudication, autonomy_orchestrator, replay_corpus, administrative_escalation stations", "/admin/api/v1/adjudications", "/admin/api/v1/autonomy/decisions", "/admin/api/v1/autonomy/threshold-deadlocks", "/admin/api/v1/escalations", "broker replay corpus UI/API")),
    ObservatoryItem("21.24", "Evidence-fidelity views distinguish full-autonomy support from degraded hash-only, metadata-only, redacted-derivative, declassified-summary, and raw-vault-linked states.", ("/admin/api/v1/evidence/fidelity", "/admin/api/v1/raw-vault/summary", "admin_evidence_fidelity_status", "replay synthesis skips unsupported evidence-fidelity tiers")),
    ObservatoryItem("21.25", "Storage pages expose migration state, read-model freshness, pgvector/index status, and retention backlog.", ("storage_db station", "/admin/api/v1/storage")),
    ObservatoryItem("21.26", "Model/embedding pages expose qualification, structured-output failure, timeout, retry, and error health without dollar-cost analysis.", ("/admin/api/v1/model-profile and /admin/api/v1/embedding-profile", "model_embedding station", "no cost analytics in acceptance non-goals")),
    ObservatoryItem("21.27", "Operator action pages expose action requests, policy checks, idempotency, confirmation state, linked jobs, and audit records.", ("Admin action gateway in App.tsx", "/admin/api/v1/actions and /admin/api/v1/actions/audit")),
    ObservatoryItem("21.28", "Observatory self-health pages expose admin API health, live-stream gaps, sequence gaps, frontend diagnostics, read-model staleness, and dashboard performance.", ("observatory_admin station", "/admin/api/v1/observatory and health routes", "FrontendDiagnostics in App.tsx")),
    ObservatoryItem("21.29", "Operator actions are role-checked, confirmation-gated when required, idempotent, policy-controlled, and audited.", ("action_receipt in services/observatory.py", "_record_observatory_action in api/app.py")),
    ObservatoryItem("21.30", "The UI defaults to redacted content and does not expose raw content without explicit authorization.", ("content_policy raw_available=false across admin routes", "raw reveal action gate")),
    ObservatoryItem("21.31", "Admin streaming and dashboard queries do not block core processing.", ("bounded Observatory store/read-model routes", "WebSocket/SSE snapshot fallback tests")),
    ObservatoryItem("21.32", "Reduced-motion and low-power modes preserve informational value.", ("reducedMotion state in App.tsx", "prefers-reduced-motion CSS")),
    ObservatoryItem("21.33", "Component health is based on the required signal contract and never reports healthy when required telemetry is missing.", ("REQUIRED_METRICS_BY_FAMILY in services/observatory.py", "zero-count and missing-signal tests")),
    ObservatoryItem("21.34", "Pipeline invariant failures create issue-board entries, supporting evidence, safe next actions, and deep links.", ("pipeline invariants in services/observatory.py", "invariant route tests", "required signal issue evidence tests")),
    ObservatoryItem("21.35", "Baseline comparison supports bounded time-window, object-version, replay, canary, and before-after comparisons without changing autonomous policy.", ("/admin/api/v1/comparisons routes", "comparison persistence tests", "trace replay and broker replay read models")),
    ObservatoryItem("21.36", "Diagnostic bundles can be generated with redaction by default and audited access.", ("/admin/api/v1/diagnostics/bundles routes", "diagnostic bundle tests")),
    ObservatoryItem("21.37", "The interface meets configured accessibility, keyboard-navigation, reduced-motion, and low-power requirements.", ("semantic buttons/labels in App.tsx", "reduced-motion controls and CSS media query")),
    ObservatoryItem("21.38", "The visual design delivers assembly-line overview, workcell views, station cockpits, and object microscope behavior.", ("AssemblyLine, Workcells, Cockpit, TraceAndInspector, and Inspector components",)),
    ObservatoryItem("21.39", "The overview graph passes the centerpiece rubric for finish, legibility, honesty, spatial memory, clutter control, performance, accessibility, and theme coherence.", ("custom ELK layout spacing and edge labels in AssemblyLine.tsx", "theme tokens in styles.css")),
    ObservatoryItem("21.40", "Every core topology, lifecycle, artifact, broker, scanner/evaluator, scheduler, historical-ingestion, raw-vault, semantic-adjudication, replay/canary, and administrative-escalation state has a visible path from overview to object evidence.", ("24-station component map", "route inventory coverage in test_observatory_api.py", "broker replay episode, autonomy decision, adjudication, escalation, evidence-fidelity, and memory/control-flow object microscopes")),
    ObservatoryItem("21.41", "The system triage summary identifies healthy, degraded, blocked, frozen, stale, and unknown states with reason codes and safe next actions.", ("fitness summary and issue board in services/observatory.py", "stale telemetry tests")),
    ObservatoryItem("21.42", "Seeded high-load fixtures demonstrate Observatory remains effective for large deployments.", ("high_load_soak fixture in sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json", "bounded pagination and storage_limit defaults", "operator metrics and high-count snapshot tests")),
)


DEVELOPER_CHECKLIST: tuple[ObservatoryItem, ...] = (
    ObservatoryItem("24.auto.1", "Add read models and routes for evidence fidelity, raw-vault audit, semantic adjudication, autonomy decisions, replay synthesis, threshold deadlocks, and administrative escalation.", ("admin_evidence_fidelity_status", "admin_autonomy_decision_status", "admin_semantic_adjudication_status", "admin_administrative_escalation_status", "broker replay corpus admin routes", "memory quarantine/control-flow read models")),
    ObservatoryItem("24.auto.2", "Render evidence-fidelity and autonomy-support states in overview, workcells, station headers, object microscope, and issue board.", ("data_quality/content_policy envelopes in station snapshots", "issue board reason codes and evidence refs", "object microscope content_policy panels")),
    ObservatoryItem("24.auto.3", "Implement autonomy decision microscope pages with evidence links, hard invariants, soft thresholds, fallback ladder, and audit references.", ("/admin/api/v1/autonomy/decisions/{decision_id}", "generic autonomy-decision object microscope payload", "trace replay policy/gate badges", "playbook detail supporting records and actions")),
    ObservatoryItem("24.auto.4", "Implement replay-corpus synthesis pages showing LLM-synthesized redacted intent and deterministic validation without raw exposure.", ("Broker Replay Corpus frontend tab", "broker replay episode metadata raw_prompt_stored=false", "/v1/broker/replay-episodes/synthesize", "test_broker_policy_synthesizes_missing_intent_from_safe_retrieval_context", "test_broker_policy_synthesis_repairs_stale_telemetry_episode_decision")),
    ObservatoryItem("24.auto.5", "Ensure raw content is never emitted in live stream, LISTEN/NOTIFY payloads, browser local storage, URLs, or console diagnostics.", ("admin live envelopes carry snapshots and redacted objects only", "content_policy raw_available=false route assertions", "FrontendDiagnostics counters contain operational metrics only")),
    ObservatoryItem("24.auto.6", "Add visual and API tests for evidence-insufficient, soft-threshold fallback, threshold deadlock, administrative escalation, and raw-reveal denial states.", ("visual-regression-fixtures.json covers degraded/stale/security/rollback states", "test_observatory_api.py autonomy/evidence read-model coverage", "test_observatory_acceptance_report.py acceptance crosswalk")),
    ObservatoryItem("24.1", "Add admin API module to sidecar.", ("sidecar/autoskill/api/app.py admin routes",)),
    ObservatoryItem("24.2", "Add auth/role middleware.", ("_require_admin_auth and role headers",)),
    ObservatoryItem("24.3", "Add web_admin config block.", ("Settings web_admin fields", "/admin/api/v1/config")),
    ObservatoryItem("24.4", "Add subsystem and component catalog seed migration.", ("autoskill.admin_component_catalog and autoskill.admin_subsystem_catalog seeds in migrations/0001_autoskill_schema.sql", "STATIONS and SUBSYSTEMS catalog in services/observatory.py")),
    ObservatoryItem("24.5", "Add component status snapshots.", ("build_observatory_snapshot",)),
    ObservatoryItem("24.6", "Add live event outbox.", ("observatory_admin live event store",)),
    ObservatoryItem("24.7", "Add diagnostic assertion and issue read models.", ("issue board and invariants routes",)),
    ObservatoryItem("24.8", "Add baseline comparison and diagnostic bundle endpoints.", ("comparison and diagnostic bundle routes",)),
    ObservatoryItem("24.9", "Add admin action audit table.", ("autoskill.db.observatory_admin action audit stores",)),
    ObservatoryItem("24.10", "Add pipeline and subsystem summary read models.", ("snapshot pipeline and subsystem builders",)),
    ObservatoryItem("24.11", "Add read-model refresh service.", ("refresh_read_models action and snapshot builders",)),
    ObservatoryItem("24.12", "Add WebSocket live stream.", ("/admin/live websocket route",)),
    ObservatoryItem("24.13", "Add optional SSE stream.", ("/admin/live-sse route",)),
    ObservatoryItem("24.14", "Add OpenAPI-generated frontend client.", ("scripts/generate_observatory_openapi_client.py", "sidecar/autoskill/observatory/src/generated/observatoryClient.ts", "typed frontend API wrappers in observatory/src/api.ts consume generated admin route paths")),
    ObservatoryItem("24.15", "Build React/Vite app shell.", ("observatory package.json and App.tsx",)),
    ObservatoryItem("24.16", "Build overview assembly-line graph with subsystem lanes.", ("AssemblyLine and Workcells components",)),
    ObservatoryItem("24.17", "Implement stable-identity live reconciliation.", ("snapshotContentSignature and AssemblyLine structuralKey",)),
    ObservatoryItem("24.18", "Add render/mount counters and live-update defect tests.", ("FrontendDiagnostics counters surfaced in observatory/src/App.tsx", "live-update continuity tests and stable-identity reducer behavior", "test_observatory_acceptance_report.py source assertion for frontend diagnostics")),
    ObservatoryItem("24.19", "Build subsystem lens framework.", ("Workcells component",)),
    ObservatoryItem("24.20", "Build station cockpit framework.", ("Cockpit component",)),
    ObservatoryItem("24.21", "Build all component cockpits.", ("generic cockpit over all 24 stations",)),
    ObservatoryItem("24.22", "Build skill library/detail/topology pages.", ("SkillsAndTopology component",)),
    ObservatoryItem("24.23", "Build issue board, diagnostic assertions, and guided playbooks.", ("issue board and playbooks routes",)),
    ObservatoryItem("24.24", "Build trace replay, baseline comparison, and provenance graph.", ("TraceAndInspector and comparison routes",)),
    ObservatoryItem("24.25", "Build context budget views.", ("context artifact API and SkillsAndTopology context pane",)),
    ObservatoryItem("24.26", "Build scanner/evaluator/security pages.", ("scanner/evaluator routes and cockpits",)),
    ObservatoryItem("24.27", "Build scheduler/jobs pages.", ("scheduler_jobs cockpit and job routes",)),
    ObservatoryItem("24.28", "Build model/embedding profile pages.", ("model_embedding cockpit and profile routes",)),
    ObservatoryItem("24.29", "Build storage/read-model pages.", ("storage_db cockpit and storage route",)),
    ObservatoryItem("24.30", "Build Observatory self-health page.", ("observatory_admin cockpit and route",)),
    ObservatoryItem("24.31", "Add guarded action dialogs.", ("Admin action-dialog confirmation flow in observatory/src/App.tsx", "Admin dry-run action gateway buttons and policy receipts", "action audit route coverage")),
    ObservatoryItem("24.32", "Add audit chain verification UI.", ("Admin verify_audit_chain action",)),
    ObservatoryItem("24.33", "Add PixiJS particle overlay.", ("ParticleLayer component",)),
    ObservatoryItem("24.34", "Add reduced-motion, low-power, keyboard, and accessibility modes.", ("reduced motion toggle and semantic controls",)),
    ObservatoryItem("24.35", "Add raw-content safeguards and browser security headers.", ("content policy fields and browser-session CSRF headers",)),
    ObservatoryItem("24.36", "Add E2E tests and load fixtures.", ("scripts/autoskill_observatory_fixtures.py", "sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json", "test_observatory_acceptance_report.py validates E2E journeys and high-load thresholds")),
    ObservatoryItem("24.37", "Add visual regression tests.", ("deterministic visual-state fixture catalog in sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json", "test_observatory_acceptance_report.py validates required visual states and assertions")),
    ObservatoryItem("24.38", "Add documentation and operator runbook.", ("README Observatory commands and TASKFLOW ledger",)),
)


def build_report() -> dict[str, Any]:
    validation_errors = validate_items((*ACCEPTANCE_CRITERIA, *DEVELOPER_CHECKLIST))
    acceptance = [item.to_json() for item in ACCEPTANCE_CRITERIA]
    checklist = [item.to_json() for item in DEVELOPER_CHECKLIST]
    satisfied = sum(1 for item in acceptance + checklist if item["status"] in SATISFIED_STATUSES)
    return {
        "schema": "autoskill.observatory-acceptance-report.v1",
        "ready": not validation_errors and satisfied == len(acceptance) + len(checklist),
        "summary": {
            "acceptance_criteria": len(acceptance),
            "developer_checklist": len(checklist),
            "satisfied": satisfied,
            "implemented_equivalent": sum(
                1 for item in acceptance + checklist if item["status"] == "implemented_equivalent"
            ),
            "validation_errors": validation_errors,
        },
        "acceptance_criteria": acceptance,
        "developer_checklist": checklist,
    }


def validate_items(items: tuple[ObservatoryItem, ...]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item.item_id in seen:
            errors.append(f"duplicate item id: {item.item_id}")
        seen.add(item.item_id)
        if item.status not in SATISFIED_STATUSES:
            errors.append(f"{item.item_id} has unsatisfied status: {item.status}")
        _validate_no_placeholder(errors, item.item_id, item.text)
        if not item.evidence:
            errors.append(f"{item.item_id} has no evidence")
        for evidence in item.evidence:
            _validate_no_placeholder(errors, item.item_id, evidence)
    return errors


def _validate_no_placeholder(errors: list[str], item_id: str, value: str) -> None:
    lowered = value.lower()
    if not value.strip():
        errors.append(f"{item_id} has empty text")
    if "todo" in lowered or "tbd" in lowered or "placeholder" in lowered:
        errors.append(f"{item_id} has placeholder text: {value}")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SkillKernel Observatory Acceptance Report",
        "",
        f"Ready: {str(report['ready']).lower()}",
        f"Acceptance criteria: {report['summary']['acceptance_criteria']}",
        f"Developer checklist: {report['summary']['developer_checklist']}",
        "",
    ]
    for section, title in (
        ("acceptance_criteria", "Acceptance Criteria"),
        ("developer_checklist", "Developer Checklist"),
    ):
        lines.append(f"## {title}")
        for item in report[section]:
            lines.append(f"- {item['item_id']} {item['status']}: {item['text']}")
            for evidence in item["evidence"]:
                lines.append(f"  - {evidence}")
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit the SkillKernel Observatory acceptance and checklist crosswalk.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
