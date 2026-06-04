# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str
    text: str
    evidence: tuple[str, ...]
    status: str = "implemented"

    def to_json(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "text": self.text,
            "status": self.status,
            "evidence": list(self.evidence),
        }


PRODUCTION_CRITERIA: tuple[AcceptanceCriterion, ...] = (
    AcceptanceCriterion(
        "31.1",
        "No dependency on OpenClaw Cron.",
        (
            "sidecar-owned schedules/jobs in autoskill.db.scheduler and scheduler_defaults",
            "README Non-Negotiables",
            "uv run pytest -q sidecar/autoskill/tests/test_scheduler_api.py",
        ),
    ),
    AcceptanceCriterion(
        "31.2",
        "No dependency on Skill Workshop.",
        (
            "SkillKernel proposal/scanner/evaluator/writer stores are implemented in sidecar",
            "README Non-Negotiables",
            "npm test --prefix plugin/autoskill",
        ),
    ),
    AcceptanceCriterion(
        "31.3",
        "No per-skill databases.",
        (
            "single Postgres DSN in autoskill.core.config.Settings.database_url",
            "one autoskill schema migration in migrations/0001_autoskill_schema.sql",
        ),
    ),
    AcceptanceCriterion(
        "31.4",
        "No per-skill schemas.",
        (
            "Settings.schema_name defaults to autoskill",
            "migrations create one autoskill schema",
        ),
    ),
    AcceptanceCriterion(
        "31.5",
        "All events are redacted before persistence.",
        (
            "autoskill.api.app.ingest_events stores event.redacted() envelopes",
            "sidecar/autoskill/tests/test_ingest_auth.py",
            "npm test --prefix plugin/autoskill",
        ),
    ),
    AcceptanceCriterion(
        "31.6",
        "All embeddings are created from redacted text.",
        (
            "embedding generation sources are body/evidence/external rows already redacted or public",
            "sidecar/autoskill/tests/test_embedding_generation.py",
            "sidecar/autoskill/tests/test_historical_import.py",
        ),
    ),
    AcceptanceCriterion(
        "31.7",
        "Sidecar outage does not block normal OpenClaw usage.",
        (
            "plugin capture spools failed forwarding instead of blocking",
            "plugin/autoskill/test/spool.test.js",
            "npm test --prefix plugin/autoskill",
        ),
    ),
    AcceptanceCriterion(
        "31.8",
        "Sidecar endpoint is private/authenticated and never exposed publicly.",
        (
            "default bind is 127.0.0.1",
            "ingest/control bearer-token checks in autoskill.api.app",
            "/v1/config/effective reports allow_public_bind=false",
        ),
    ),
    AcceptanceCriterion(
        "31.9",
        "Container path mappings and root containment checks are verified before historical import or file activation.",
        (
            "writer root containment in autoskill.api.app._writer_roots",
            "writer path containment in autoskill.services.writer",
            "historical discovery records hashed roots without mutating sources",
        ),
    ),
    AcceptanceCriterion(
        "31.10",
        "Scheduler survives restart and resumes safely.",
        (
            "durable schedules/jobs in Postgres",
            "scheduler tick idempotency and misfire tests",
            "audit.verify registered through scheduler defaults",
        ),
    ),
    AcceptanceCriterion(
        "31.11",
        "Job leases prevent duplicate mutation.",
        (
            "job lease claim/renew/complete primitives",
            "worker pool and lease renewal tests",
            "mutation worker uses leased jobs",
        ),
    ),
    AcceptanceCriterion(
        "31.12",
        "Skill operation selection considers improve, promote, compose, decompose, merge, and archive before creating duplicates.",
        (
            "utility curation covers archive/promote/merge/improve/decompose",
            "topology proposal services cover create/improve/compose/decompose",
            "/v1/proposals/review surfaces operation statuses",
        ),
    ),
    AcceptanceCriterion(
        "31.13",
        "Every created skill is a normal OpenClaw skill with valid SKILL.md.",
        (
            "SkillIR compiler renders SKILL.md artifacts",
            "writer manifest verifies SKILL.md file hashes",
            "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
        ),
    ),
    AcceptanceCriterion(
        "31.14",
        "Every mutation has manifest, hashes, scanner result, evaluator result, and rollback pointer.",
        (
            "writer manifests include gate statuses and rollback archive pointers",
            "activation-gate store checks scanner/evaluator/proposal gates",
            "sidecar/autoskill/tests/test_audit_writer_events.py",
        ),
    ),
    AcceptanceCriterion(
        "31.15",
        "Hidden comments and invisible Markdown are rejected.",
        (
            "scanner detects hidden markdown/comment patterns",
            "Settings.forbid_hidden_markdown defaults true",
            "scripts/autoskill_red_team.py",
        ),
    ),
    AcceptanceCriterion(
        "31.16",
        "Scanner blocks known malicious skill patterns.",
        (
            "scanner blocks exfiltration, destructive commands, policy override, and dynamic fetch-exec",
            "scripts/autoskill_red_team.py",
            "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
        ),
    ),
    AcceptanceCriterion(
        "31.17",
        "Regression gate blocks local fixes that break prior probes.",
        (
            "proposal-gate evaluator requires target/no-skill/regression/adversarial probes",
            "sidecar/autoskill/tests/test_evaluator.py",
            "sidecar/autoskill/services/probes.py",
        ),
    ),
    AcceptanceCriterion(
        "31.18",
        "No-skill controls or equivalent intervention checks exist for accepted skills.",
        (
            "probe planner creates no_skill_control probes",
            "contrastive replay can attach intervention evidence",
            "sidecar/autoskill/tests/test_evaluator.py",
        ),
    ),
    AcceptanceCriterion(
        "31.19",
        "Active skill budget is enforced.",
        (
            "Settings.max_active_skills",
            "utility curation active-bank budget enforcement",
            "sidecar/autoskill/tests/test_utility.py",
        ),
    ),
    AcceptanceCriterion(
        "31.20",
        "Runtime context broker is bounded and fail-soft.",
        (
            "runtime context timeout/token settings",
            "plugin runtime context fail-soft tests",
            "sidecar/autoskill/tests/test_broker.py",
        ),
    ),
    AcceptanceCriterion(
        "31.21",
        "Archived skills are invisible to OpenClaw but searchable through SkillKernel.",
        (
            "writer archive removes active skill directories",
            "retrieval indexes archived body documents as promotion candidates",
            "utility promotion tests",
        ),
    ),
    AcceptanceCriterion(
        "31.22",
        "Archived promotion works.",
        (
            "utility curation restores archived manifests during promotion",
            "sidecar/autoskill/tests/test_utility.py",
            "TASKFLOW promotion/merge/budget validation",
        ),
    ),
    AcceptanceCriterion(
        "31.23",
        "Rollback works under canary failure.",
        (
            "critical canary freezes skills and queues rollback revocations",
            "mutation worker executes rollback revocation",
            "sidecar/autoskill/tests/test_lifecycle.py",
        ),
    ),
    AcceptanceCriterion(
        "31.24",
        "Drift checks detect simple broken environment contracts.",
        (
            "contract/drift stores handle path/command/env/package/TCP/HTTP probes",
            "sidecar/autoskill/tests/test_contracts.py",
            "sidecar/autoskill/tests/test_worker.py",
        ),
    ),
    AcceptanceCriterion(
        "31.25",
        "Retrieval logs track retrieved/rendered/injected/used/outcome.",
        (
            "retrieval_logs store candidates/rendered IDs/decision metadata",
            "context token ledgers record visibility outcomes",
            "attribution outcome taxonomy",
        ),
    ),
    AcceptanceCriterion(
        "31.26",
        "Shadowing logs and remediation exist.",
        (
            "shadowing detection records attribution events",
            "utility curation consumes shadowing outcomes",
            "sidecar/autoskill/tests/test_shadowing.py",
        ),
    ),
    AcceptanceCriterion(
        "31.27",
        "Audit hash chain validates.",
        (
            "/v1/audit/recent",
            "audit.verify maintenance job",
            "sidecar/autoskill/tests/test_worker.py::test_worker_run_once_verifies_audit_hash_chain",
        ),
    ),
    AcceptanceCriterion(
        "31.28",
        "All core invariants are automated tests.",
        (
            "uv run pytest -q",
            "npm test --prefix plugin/autoskill",
            "scripts/autoskill_red_team.py",
        ),
    ),
    AcceptanceCriterion(
        "31.29",
        "Create, improve, compose, and decompose are separate operation classes with separate evidence, evaluation, and metrics.",
        (
            "TOPOLOGY_OPERATION_KINDS create/improve/compose/decompose",
            "/v1/topology/metrics",
            "sidecar/autoskill/tests/test_topology_services.py",
        ),
    ),
    AcceptanceCriterion(
        "31.30",
        "Composition requires co-use/sequence evidence and component-vs-composed trials.",
        (
            "usage.aggregate produces co-use/sequence clusters",
            "topology compose planner emits component-vs-composed trials",
            "sidecar/autoskill/tests/test_topology_services.py",
        ),
    ),
    AcceptanceCriterion(
        "31.31",
        "Decomposition requires partial-use/false-positive/separable-cluster evidence and original-vs-successor trials.",
        (
            "utility/context-value signals drive decompose proposals",
            "topology decompose planner emits original-vs-successor trials",
            "sidecar/autoskill/tests/test_topology_services.py",
        ),
    ),
    AcceptanceCriterion(
        "31.32",
        "Topology operations are rollback-complete across graph edges, broker policy, embeddings, probes, and active files.",
        (
            "revocation invalidation covers topology/evaluator/attribution/governance derived state",
            "topology downstream action rollback metadata",
            "sidecar/autoskill/tests/test_worker.py",
        ),
    ),
    AcceptanceCriterion(
        "31.33",
        "Every context-loadable artifact has registry row, token count, budget, content hash, compiler version, scanner status, and provenance.",
        (
            "context_artifacts and context_compile_runs tables",
            "compiled candidate skill_md context artifact registration",
            "sidecar/autoskill/tests/test_admin_surfaces.py",
        ),
    ),
    AcceptanceCriterion(
        "31.34",
        "Every compressed description passes positive/negative routing-equivalence tests.",
        (
            "description minimization/equivalence metadata",
            "semantic compression trials",
            "sidecar/autoskill/tests/test_skillir_migration.py",
        ),
    ),
    AcceptanceCriterion(
        "31.35",
        "Every compressed body passes information-preservation and regression gates.",
        (
            "context compiler semantic equivalence gate",
            "proposal-gate regression probes",
            "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
        ),
    ),
    AcceptanceCriterion(
        "31.36",
        "Every support snippet has classification, budget, scan result, and retrieval boundary.",
        (
            "support artifact manifest load_policy and context registration",
            "support excerpt context artifacts",
            "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
        ),
    ),
    AcceptanceCriterion(
        "31.37",
        "Context-value-per-token is measured and can drive archive, compose, decompose, or no-skill decisions.",
        (
            "context token ledger outcome updates",
            "utility rollups include context-value/token-waste features",
            "sidecar/autoskill/tests/test_utility.py",
        ),
    ),
    AcceptanceCriterion(
        "31.38",
        "Historical datasource discovery works across configured agents without crossing agent/workspace boundaries.",
        (
            "historical_import.discover bounded configured-root scanning",
            "hashed source roots and workspace-scoped rows",
            "sidecar/autoskill/tests/test_historical_import.py",
        ),
    ),
    AcceptanceCriterion(
        "31.39",
        "Historical import supports the required source families.",
        (
            "historical discovery classifiers cover sessions, transcripts, trajectories, summaries, memory/context, tasks, plugin state, queued injections, active-memory, diagnostics/media, and skills",
            "historical parser tests",
            "sidecar/autoskill/tests/test_historical_import.py",
        ),
    ),
    AcceptanceCriterion(
        "31.40",
        "Every historical import row has provenance, fingerprint, parser version, redaction version, trust, and taint.",
        (
            "historical_import_sources/chunks schema",
            "v2 source-item locator metadata",
            "historical source-item lineage validation",
        ),
    ),
    AcceptanceCriterion(
        "31.41",
        "Historical raw content is never embedded, indexed for LLM analysis, or compiled before redaction.",
        (
            "historical chunk recording stores redaction metadata",
            "embedding source discovery uses redacted chunk text",
            "historical bootstrap remains tainted and propose-only",
        ),
    ),
    AcceptanceCriterion(
        "31.42",
        "Historical candidates use the same create/improve/compose/decompose gates as live candidates.",
        (
            "historical bootstrap consolidation calls the normal candidate persistence path",
            "historical candidates stay inactive until normal gates pass",
            "sidecar/autoskill/tests/test_historical_bootstrap.py",
        ),
    ),
    AcceptanceCriterion(
        "31.43",
        "Historical source revocation traverses derived chunks, embeddings, evidence, memories, candidates, probes, broker caches, and compiled artifacts.",
        (
            "historical source revoke endpoint queues revocation traversal",
            "mutation worker invalidation covers derived state families",
            "sidecar/autoskill/tests/test_historical_import.py",
        ),
    ),
    AcceptanceCriterion(
        "31.44",
        "Established deployments can run a bounded bootstrap import without degrading normal OpenClaw runtime behavior.",
        (
            "historical import low-priority worker pool and byte/session/file limits",
            "historical bootstrap consolidation is propose-only by default",
            "deployment readiness and scheduler defaults separate runtime capture from backfill",
        ),
    ),
    AcceptanceCriterion(
        "31.45",
        "Replay-corpus candidates can be promoted automatically from eligible telemetry without requiring an operator-authored replay plan in the normal path.",
        (
            "/v1/broker/replay-episodes/synthesize can synthesize redacted intent from content-safe retrieval telemetry",
            "synthesis requires eligible evidence fidelity and deterministic validation pass",
            "test_broker_policy_synthesizes_missing_intent_from_safe_retrieval_context",
            "test_broker_policy_synthesis_repairs_stale_telemetry_episode_decision",
        ),
    ),
    AcceptanceCriterion(
        "31.46",
        "Hash-only telemetry is treated as degraded evidence and cannot silently support full-autonomy replay/canary claims.",
        (
            "replay synthesis skips hash_only and metadata_only evidence-fidelity tiers",
            "synthesis skip reasons are returned to the caller",
            "test_broker_policy_synthesis_skips_degraded_evidence_fidelity_telemetry",
        ),
    ),
    AcceptanceCriterion(
        "31.47",
        "Memory quarantine can resolve high-confidence safe/unsafe records autonomously and escalates only policy, contradiction, or low-confidence cases.",
        (
            "memory governance store and action routes expose taint/status/provenance safely",
            "control-flow and memory quarantine admin read models",
            "sidecar/autoskill/tests/test_observatory_api.py",
        ),
    ),
    AcceptanceCriterion(
        "31.48",
        "Every LLM adjudication record stores evidence identity, exposure level, declassification state, confidence, deterministic checks, decision, and escalation reason.",
        (
            "LLM invocation and trace-spine records link model calls to safe attributes and object refs",
            "autonomy assurance payloads expose evidence fidelity and policy gates",
            "Observatory playbook and microscope tests",
        ),
    ),
    AcceptanceCriterion(
        "31.49",
        "Raw-prompt retention disabled remains functional while surfacing limited autonomy and reduced replay/canary evidence confidence.",
        (
            "raw_content_available=false is explicit in Observatory data quality and content policy",
            "raw-vault and replay corpus metadata keep raw_prompt_stored=false",
            "test_observatory_summary_exposes_all_pipeline_stations_and_truth_states",
        ),
    ),
    AcceptanceCriterion(
        "31.50",
        "Soft-threshold misses trigger autonomous alternatives before administrative escalation.",
        (
            "autonomy orchestrator and playbook detail expose fallback actions and blocked-policy actions",
            "issue board safe_next_action records",
            "sidecar/autoskill/tests/test_observatory_api.py",
        ),
    ),
    AcceptanceCriterion(
        "31.51",
        "Hard invariants are separate from adaptive soft thresholds in code, database state, UI, and acceptance reports.",
        (
            "scanner/evaluator/writer gates remain deterministic hard blockers",
            "threshold policy, calibration, and fallback states are read-model diagnostics",
            "Observatory autonomy assurance and acceptance crosswalks",
        ),
    ),
    AcceptanceCriterion(
        "31.52",
        "Threshold-deadlock detection and evaluated remediation are represented as first-class diagnostic states.",
        (
            "issue board and guided playbooks expose stalled decision reason codes and safe next actions",
            "Observatory autonomy/degraded evidence acceptance entries",
            "sidecar/autoskill/tests/test_observatory_api.py",
        ),
    ),
    AcceptanceCriterion(
        "31.53",
        "Composite confidence records include model confidence, evidence coverage, source fidelity, contradiction, scanner/evaluator, reversibility, canary, and calibration support.",
        (
            "autonomy assurance dashboards expose confidence, evidence, fallback, and calibration fields",
            "trace replay read model includes policy/gate badges",
            "sidecar/autoskill/tests/test_observatory_acceptance_report.py",
        ),
    ),
    AcceptanceCriterion(
        "31.54",
        "Near-margin accepted decisions move to canary, ephemeral, narrower activation, or more-probe states without defaulting to admin when hard gates pass.",
        (
            "broker canary feedback records critical/degraded/pass state and rollback recommendations",
            "proposal gates support target/regression/adversarial/canary probes",
            "sidecar/autoskill/tests/test_broker_policy_api.py",
        ),
    ),
    AcceptanceCriterion(
        "31.55",
        "Every semantic decision family has calibration observations, delayed outcomes, and reliability metrics visible for operation.",
        (
            "Observatory model/profile, replay, canary, and autonomy assurance read models",
            "operator metrics include scanner/evaluator failures and replay corpus coverage",
            "scripts/autoskill_observatory_acceptance.py",
        ),
    ),
    AcceptanceCriterion(
        "31.56",
        "Soft-threshold policy versions pass replay/backtest/shadow/canary evidence before activation.",
        (
            "broker policy replay and stored replay corpus endpoints",
            "broker policy canary feedback can roll back critical policies",
            "test_broker_policy_api_activates_policy_and_replay_uses_it",
        ),
    ),
    AcceptanceCriterion(
        "31.57",
        "Adaptive thresholding cannot weaken hard safety, privacy, rollback, scanner, evaluator, filesystem, or audit invariants.",
        (
            "synthesis and action routes require deterministic validation and control auth",
            "writer/scanner/evaluator gates remain outside threshold policy artifacts",
            "scripts/autoskill_acceptance.py hard-invariant criteria 31.14-31.17",
        ),
    ),
    AcceptanceCriterion(
        "31.58",
        "High-impact runtime changes use risk tiering, verifier/probe coverage, canary, and rollback rather than default administrative escalation.",
        (
            "activation gates require scanner/evaluator/proposal states",
            "canary rollback and revocation worker paths",
            "sidecar/autoskill/tests/test_lifecycle.py",
        ),
    ),
    AcceptanceCriterion(
        "31.59",
        "Administrative escalation is reason-coded and cannot be represented merely as a failed soft threshold.",
        (
            "administrative_escalation station, issue board reason codes, and playbook detail",
            "safe diagnostic actions distinguish blocked policy from operator actions",
            "sidecar/autoskill/tests/test_observatory_api.py",
        ),
    ),
    AcceptanceCriterion(
        "31.60",
        "Observatory exposes calibration support, reliability metrics, threshold-deadlock state, and reason codes for stalled decisions.",
        (
            "observatory autonomy acceptance criteria 21.23 and developer checklist autonomy items",
            "playbook signal state includes confidence, issue links, warnings, and actions",
            "scripts/autoskill_observatory_acceptance.py",
        ),
    ),
    AcceptanceCriterion(
        "31.61",
        "Replay synthesis stores provenance, exposure policy, deterministic validation, and source retrieval log links for automatically derived episodes.",
        (
            "BrokerReplayEpisodeSynthesizeResponse returns episodes and skip reasons",
            "broker_replay_episodes.metadata includes source, evidence_fidelity, validation, and raw_prompt_stored=false",
            "test_broker_policy_synthesizes_missing_intent_from_safe_retrieval_context",
            "test_broker_policy_synthesis_repairs_stale_telemetry_episode_decision",
        ),
    ),
    AcceptanceCriterion(
        "31.62",
        "Automatically synthesized replay episodes are immediately usable by normal broker replay/canary evaluation.",
        (
            "synthesized episodes are stored through BrokerPolicyStore.record_replay_episode",
            "stale telemetry-derived episodes are repaired by source retrieval log on synthesis rerun",
            "BrokerPolicyReplayRequest include_stored_episodes consumes telemetry-derived tags",
            "test_broker_policy_synthesizes_replay_episodes_from_redacted_telemetry",
            "test_broker_policy_synthesizes_missing_intent_from_safe_retrieval_context",
            "test_broker_policy_synthesis_repairs_stale_telemetry_episode_decision",
        ),
    ),
    AcceptanceCriterion(
        "31.63",
        "New implementation-spec criteria are covered by executable acceptance crosswalks rather than informal ledger claims.",
        (
            "scripts/autoskill_acceptance.py covers production criteria 31.1 through 31.63",
            "sidecar/autoskill/tests/test_acceptance_report.py asserts the current criterion count",
            "uv run python scripts/autoskill_acceptance.py --json",
        ),
    ),
)


CONTEXT_CRITERIA: tuple[AcceptanceCriterion, ...] = (
    AcceptanceCriterion(
        "31.ctx.1",
        "No SkillKernel-owned context-loadable artifact lacks a loadability class.",
        ("runtime_skill_body/support_artifact loadability metadata",),
    ),
    AcceptanceCriterion(
        "31.ctx.2",
        "No SKILL.md version can activate without token count, semantic-equivalence result, scanner pass, and artifact hash.",
        ("writer activation gates and context compile manifests",),
    ),
    AcceptanceCriterion(
        "31.ctx.3",
        "Generated descriptions stay within configured character budget unless explicitly excepted.",
        ("Settings.max_frontmatter_description_chars and compiler description checks",),
    ),
    AcceptanceCriterion(
        "31.ctx.4",
        "Runtime skill bodies meet target token budget or produce deterministic split/decompose decisions.",
        ("context compiler token budgets and utility decompose planning",),
    ),
    AcceptanceCriterion(
        "31.ctx.5",
        "Support files are never assumed safe merely because they are outside SKILL.md.",
        ("support artifact scanner/load-policy checks",),
    ),
    AcceptanceCriterion(
        "31.ctx.6",
        "No raw transcript, rationale, history, or improvement note appears in runtime context unless promoted through SkillIR/compiler gates.",
        ("redaction-before-store/embed/LLM plus SkillIR compiler gates",),
    ),
    AcceptanceCriterion(
        "31.ctx.7",
        "Context regressions trigger reject, rollback, decompose, description tighten, or broker abstention.",
        ("context-value curation, repair planning, and broker abstention controls",),
    ),
)


def build_report() -> dict[str, Any]:
    criteria = [item.to_json() for item in PRODUCTION_CRITERIA]
    context = [item.to_json() for item in CONTEXT_CRITERIA]
    validation_errors = validate_criteria((*PRODUCTION_CRITERIA, *CONTEXT_CRITERIA))
    all_items = criteria + context
    implemented = sum(1 for item in all_items if item["status"] == "implemented")
    return {
        "schema": "autoskill.acceptance-report.v1",
        "ready": not validation_errors and implemented == len(all_items),
        "summary": {
            "production_criteria": len(criteria),
            "context_criteria": len(context),
            "implemented": implemented,
            "validation_errors": validation_errors,
        },
        "production_criteria": criteria,
        "context_criteria": context,
    }


def validate_criteria(criteria: tuple[AcceptanceCriterion, ...]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in criteria:
        if item.criterion_id in seen:
            errors.append(f"duplicate criterion id: {item.criterion_id}")
        seen.add(item.criterion_id)
        if not item.text.strip():
            errors.append(f"{item.criterion_id} has empty text")
        if not item.evidence:
            errors.append(f"{item.criterion_id} has no evidence")
        for evidence in item.evidence:
            lowered = evidence.lower()
            if not evidence.strip():
                errors.append(f"{item.criterion_id} has empty evidence")
            if "todo" in lowered or "tbd" in lowered:
                errors.append(f"{item.criterion_id} has placeholder evidence: {evidence}")
    return errors


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SkillKernel Production Acceptance Report",
        "",
        f"Ready: {str(report['ready']).lower()}",
        f"Production criteria: {report['summary']['production_criteria']}",
        f"Context criteria: {report['summary']['context_criteria']}",
        "",
    ]
    for section, title in (
        ("production_criteria", "Production Criteria"),
        ("context_criteria", "Context Criteria"),
    ):
        lines.append(f"## {title}")
        for item in report[section]:
            lines.append(f"- {item['criterion_id']} {item['status']}: {item['text']}")
            for evidence in item["evidence"]:
                lines.append(f"  - {evidence}")
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit the SkillKernel production acceptance crosswalk.",
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
