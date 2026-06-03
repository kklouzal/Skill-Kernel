# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

READY_STATUSES = {"mitigated", "satisfied"}


@dataclass(frozen=True)
class RiskRegisterEntry:
    risk_id: str
    risk: str
    mitigation: str
    evidence: tuple[str, ...]
    status: str = "mitigated"

    def to_json(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "risk": self.risk,
            "mitigation": self.mitigation,
            "status": self.status,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class HandoffChecklistEntry:
    checklist_id: str
    phase: str
    item: str
    evidence: tuple[str, ...]
    status: str = "satisfied"

    def to_json(self) -> dict[str, Any]:
        return {
            "checklist_id": self.checklist_id,
            "phase": self.phase,
            "item": self.item,
            "status": self.status,
            "evidence": list(self.evidence),
        }


RISK_REGISTER: tuple[RiskRegisterEntry, ...] = (
    RiskRegisterEntry(
        "32.1",
        "Skill bloat degrades context",
        "Active budget, context broker, compiler, curation, archive.",
        (
            "Settings.max_active_skills and Settings.max_context_hint_tokens",
            "utility curation active-bank budget and archive actions",
            "runtime context broker bounded/fail-soft tests",
        ),
    ),
    RiskRegisterEntry(
        "32.2",
        "Over-compression drops rare critical constraints",
        "Coverage map, information-preservation gate, semantic-equivalence probes, regression bank, rollback.",
        (
            "context compiler routing-equivalence/information-preservation metadata",
            "proposal-gate target/regression/no-skill/adversarial probes",
            "writer rollback endpoints and archive-backed rollback tests",
        ),
    ),
    RiskRegisterEntry(
        "32.3",
        "Support artifacts become hidden infrastructure",
        "Skill folders cannot silently register OpenClaw hooks, OpenClaw Cron routines, tools, services, or mutable stores; such needs become operator-review integration proposals.",
        (
            "support artifacts are SkillIR declarations with manifest/load-policy metadata",
            "writer path containment and support-artifact allowlists",
            "external integration needs are represented as operator-review proposals, not active hooks",
        ),
    ),
    RiskRegisterEntry(
        "32.4",
        "Verbose support files bypass SKILL.md compression",
        "Support-file classification, snippet budgets, progressive-disclosure gates, scanner and token governor.",
        (
            "support context artifact registry rows include classification/loadability/budget fields",
            "support artifacts are scanned before writer apply",
            "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
        ),
    ),
    RiskRegisterEntry(
        "32.5",
        "Description compression breaks routing",
        "Positive/negative routing-equivalence tests and delta-debugging rollback.",
        (
            "compiled context artifacts record routing-equivalence status",
            "semantic compression trials preserve positive/negative routing evidence",
            "sidecar/autoskill/tests/test_skillir_migration.py",
        ),
    ),
    RiskRegisterEntry(
        "32.6",
        "Context budget policy drifts by model/backend",
        "Executor-profile-specific token policies and artifact variants only when evaluated.",
        (
            "Settings exposes executor_profile and context-budget defaults through /v1/config/effective",
            "context artifacts carry compiler version, token count, and budget status",
            "embedding/profile control APIs keep model-specific configuration explicit",
        ),
    ),
    RiskRegisterEntry(
        "32.7",
        "Over-composition creates broad black-hole skills",
        "Co-use thresholds, component-vs-composed trials, shadowing probes, no-skill controls, canary rollback.",
        (
            "topology compose planner requires co-use/sequence evidence and component-vs-composed trials",
            "broker replay/canary scoring gates compose/decompose routing changes",
            "shadowing and no-skill-control outcomes feed evaluator/curation",
        ),
    ),
    RiskRegisterEntry(
        "32.8",
        "Over-decomposition creates fragmented skill clutter",
        "Successor coverage tests, broker replay, active-bank budget, composition reconsideration, rollback.",
        (
            "topology decompose planner emits original-vs-successor trials",
            "utility active-bank budget and composition/decomposition reconsideration actions",
            "topology rollback actions and downstream invalidation metadata",
        ),
    ),
    RiskRegisterEntry(
        "32.9",
        "Composition hides useful components",
        "Component standalone utility tracking and broker rules for composed vs component selection.",
        (
            "usage rollups preserve per-skill utility and co-use features",
            "runtime broker logs selected/rendered/used outcomes independently",
            "topology component-vs-composed trials keep component utility observable",
        ),
    ),
    RiskRegisterEntry(
        "32.10",
        "Decomposition loses original behavior",
        "Original probe preservation, successor-bundle regression tests, restore original on canary failure.",
        (
            "decompose proposals include original-vs-successor trial categories",
            "proposal-gate regression probes block harmful successors",
            "archive-backed writer rollback can restore previous active skill state",
        ),
    ),
    RiskRegisterEntry(
        "32.11",
        "Skill shadowing",
        "Sibling disambiguators, shadow edges, runtime hints, bank-level curation.",
        (
            "/v1/shadowing/detect records skill_shadowed attribution outcomes",
            "shadow graph edges and contrastive probes are materialized for repeated shadowing",
            "sidecar/autoskill/tests/test_shadowing.py",
        ),
    ),
    RiskRegisterEntry(
        "32.12",
        "Self-generated bad skills",
        "Evidence gate, contrastive induction, scanner, evaluator, canary, rollback.",
        (
            "candidate proposals stay inactive until scanner/evaluator gates pass",
            "deterministic scanner red-team smoke covers malicious generated artifacts",
            "critical canary failure freezes skills and queues rollback revocation",
        ),
    ),
    RiskRegisterEntry(
        "32.13",
        "Self-feedback drift",
        "No self-feedback-only acceptance. Require grounded evidence.",
        (
            "proposal-gate evaluator requires explicit probe/evidence categories",
            "no-skill controls and intervention evidence are represented separately from self-feedback",
            "sidecar/autoskill/tests/test_evaluator.py",
        ),
    ),
    RiskRegisterEntry(
        "32.14",
        "Local fix causes regression",
        "Hard regression gate and probe bank.",
        (
            "proposal-gate regression probes are required for accepted candidates",
            "repair materialization remains staged and activation-gated",
            "sidecar/autoskill/tests/test_utility.py",
        ),
    ),
    RiskRegisterEntry(
        "32.15",
        "Duplicate skills accumulate",
        "Active/archived matching, merge, supersede, no-create-before-search policy.",
        (
            "candidate creation includes active/archive duplicate-match guidance",
            "utility curation handles duplicate merge/archive actions",
            "external-skill collision review blocks changed or high-risk duplicate roots",
        ),
    ),
    RiskRegisterEntry(
        "32.16",
        "Archived skill should have been used",
        "Archived retrieval and promotion jobs.",
        (
            "archived skills remain searchable through body-index/retrieval rows",
            "utility curation can promote archived skills from archive manifests",
            "sidecar/autoskill/tests/test_utility.py",
        ),
    ),
    RiskRegisterEntry(
        "32.17",
        "Memory poisoning",
        "Taint, provenance, write-path filtering, no direct memory-to-skill compilation.",
        (
            "memory quarantine APIs and broker trust-gating block unapproved memory influence",
            "repair/writer mutation paths record approved or blocked memory influence",
            "historical import treats memory evidence as tainted/propose-only until governed",
        ),
    ),
    RiskRegisterEntry(
        "32.18",
        "Historical import poisoning",
        "Treat all historical transcripts, memory files, and external exports as tainted until redacted, declassified, and corroborated; activation still requires normal gates.",
        (
            "historical sources/chunks store trust, taint, redaction, parser, and provenance metadata",
            "historical bootstrap candidates stay inactive and use normal candidate gates",
            "sidecar/autoskill/tests/test_historical_import.py",
        ),
    ),
    RiskRegisterEntry(
        "32.19",
        "Historical import overfits stale workflows",
        "Recency weighting, environment-contract checks, stale-source confidence penalties, current-skill matching, canarying, and rollback.",
        (
            "historical bootstrap remains propose-only and policy-gated",
            "contract/drift probes check current environment assumptions",
            "utility/candidate matching compares historical proposals against active and archived skills",
        ),
    ),
    RiskRegisterEntry(
        "32.20",
        "Historical import leaks private facts into skills",
        "User-fact classifier, reusable-procedure separation, redaction-before-store/embed/LLM, and compiler ban on private facts.",
        (
            "redaction-before-store/embed/LLM policy in ingest and historical import paths",
            "scanner blocks secret-like/private unsafe runtime artifacts",
            "compiler gates prevent raw transcript/history/rationale from runtime context unless promoted through SkillIR",
        ),
    ),
    RiskRegisterEntry(
        "32.21",
        "Historical backfill overwhelms database or runtime",
        "Low-priority backfill pool, byte/session/file limits, checkpoints, rollups, and pause/cancel controls.",
        (
            "historical discovery/import settings expose bounded byte/session/file limits",
            "historical parser checkpoints and low-priority worker pool",
            "deployment readiness separates runtime capture from backfill work",
        ),
    ),
    RiskRegisterEntry(
        "32.22",
        "Skill prompt injection",
        "Scanner, no hidden comments, capability manifest, adversarial probes.",
        (
            "scanner blocks hidden Markdown, policy override, exfiltration, and dynamic fetch-exec patterns",
            "scripts/autoskill_red_team.py",
            "adversarial probes are part of proposal-gate evaluation",
        ),
    ),
    RiskRegisterEntry(
        "32.23",
        "Malicious support script",
        "Script scanner, capability policy, no unapproved shell/network.",
        (
            "support artifacts include loadability/context boundary and scanner metadata",
            "scanner blocks dynamic fetch-exec and destructive host commands",
            "generated skills cannot register tools/hooks/services by support-file side effect",
        ),
    ),
    RiskRegisterEntry(
        "32.24",
        "LLM writes dangerous file",
        "Structured plan only, deterministic path-contained writer.",
        (
            "LLM outputs are stored as candidate plans/proposals, not direct file writes",
            "writer applies deterministic manifests under contained active/staging/archive roots",
            "sidecar/autoskill/tests/test_audit_writer_events.py",
        ),
    ),
    RiskRegisterEntry(
        "32.25",
        "pgvector recall loss",
        "Hybrid retrieval, exact rerank, iterative scans, recall audits.",
        (
            "retrieval store combines lexical/body-index and embedding candidates",
            "/v1/embeddings/recall-audit",
            "stored replay corpus can audit retrieval policy quality",
        ),
    ),
    RiskRegisterEntry(
        "32.26",
        "Drift from changing tools/APIs",
        "Environment contracts and drift jobs.",
        (
            "contract/drift stores support path/command/env/package/schema/TCP/HTTP probes",
            "drift false-positive suppression and repair recheck queueing",
            "sidecar/autoskill/tests/test_contracts.py",
        ),
    ),
    RiskRegisterEntry(
        "32.27",
        "Scheduler duplicate jobs",
        "Idempotency keys, row locks, advisory locks.",
        (
            "scheduler/job stores use idempotency keys and leases",
            "worker pools claim and renew leased jobs",
            "sidecar/autoskill/tests/test_scheduler_api.py and test_jobs_api.py",
        ),
    ),
    RiskRegisterEntry(
        "32.28",
        "Postgres growth",
        "Partitioning, rollups, retention, vacuum/index maintenance.",
        (
            "deployment readiness, backup/restore, and bounded historical import controls",
            "usage rollups summarize retrieval/context/topology evidence",
            "retention/revocation traversal APIs invalidate derived data",
        ),
    ),
    RiskRegisterEntry(
        "32.29",
        "User-facing dependency changes",
        "No Cron/Skill Workshop dependency; narrow skill/hook compatibility surface.",
        (
            "README Non-Negotiables",
            "scripts/autoskill_acceptance.py criteria 31.1 and 31.2",
            "plugin hook compatibility smoke tests",
        ),
    ),
    RiskRegisterEntry(
        "32.30",
        "Evaluation too expensive",
        "Tiered probes, cached evals, canary sampling, multi-objective budget.",
        (
            "proposal-gate evaluator uses deterministic probe categories",
            "replay/canary policy surfaces allow bounded stored corpus evaluation",
            "Settings exposes evaluator/adversarial probe budgets",
        ),
    ),
    RiskRegisterEntry(
        "32.31",
        "Autonomy incident",
        "Freeze, quarantine, rollback, audit, operator controls.",
        (
            "core infrastructure is not autonomously self-rewritten in v1",
            "canary freeze and rollback revocation paths",
            "audit hash chain verification and operator review/status APIs",
        ),
    ),
)


BEFORE_CODING_CHECKLIST: tuple[HandoffChecklistEntry, ...] = (
    HandoffChecklistEntry(
        "33.before.1",
        "before_coding",
        "Confirm OpenClaw hook names and payloads.",
        (
            "plugin/autoskill/src/index.js registers typed capture hooks and before_prompt_build",
            "plugin/autoskill/test/hook-smoke.test.js validates hook names, handlers, and metadata",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.2",
        "before_coding",
        "Confirm plugin permissions for raw conversation and prompt/context contribution.",
        (
            "plugin config defaults raw conversation capture disabled and runtime context hints fail-soft",
            "hook smoke tests verify prompt bodies strip unless raw capture is enabled",
            "/v1/config/effective exposes plugin capture/context settings",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.3",
        "before_coding",
        "Confirm workspace skill root and watcher behavior.",
        (
            "writer roots are contained under configured workspace active/staging/archive roots",
            "effective config reports skill_root, staging_root, and archive_root",
            "writer apply/archive/rollback tests use normal OpenClaw skill directories",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.4",
        "before_coding",
        "Confirm whether skill invocation can be observed directly.",
        (
            "runtime broker logs retrieved/rendered/used/outcome telemetry",
            "tool-result and prompt-build hook smoke tests cover observable runtime boundaries",
            "attribution outcome taxonomy records skill_helped/missing/shadowed/harmful/independent outcomes",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.5",
        "before_coding",
        "Define redaction policy.",
        (
            "autoskill.core.redaction and plugin redaction strips secrets/private prompt bodies before persistence",
            "ingest stores event.redacted() envelopes",
            "historical import records redaction_policy_version per source/chunk",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.6",
        "before_coding",
        "Select embedding model and vector dimension.",
        (
            "Settings embedding_provider, embedding_model, and embedding_dim defaults",
            "embedding profile APIs support active qualified variable-dimension profiles",
            "/v1/config/effective reports configured embedding model/dimension without secrets",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.7",
        "before_coding",
        "Choose evaluation sandbox strategy.",
        (
            "deterministic evaluator/probe planner avoids unbounded generated execution",
            "scanner/evaluator gates run before writer activation",
            "policy-approved repair materialization remains staged until activation gates pass",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.8",
        "before_coding",
        "Define scanner rule pack.",
        (
            "scanner blocks hidden content, secrets, dynamic fetch-exec, policy override, exfiltration, destructive commands, and sensitive harvesting",
            "scripts/autoskill_red_team.py",
            "sidecar/autoskill/tests/test_skillir_compiler_scanner.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.9",
        "before_coding",
        "Define active skill budget.",
        (
            "Settings.max_active_skills",
            "utility curation active-bank budget enforcement",
            "scripts/autoskill_acceptance.py criterion 31.19",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.10",
        "before_coding",
        "Define context hint budget.",
        (
            "Settings.max_context_hint_tokens and runtime_context_timeout_ms",
            "plugin runtimeContextBroker maxTokens/timeoutMs config",
            "/v1/runtime/context-hint bounded/fail-soft tests",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.11",
        "before_coding",
        "Define context-loadable artifact classes and budgets: description, body, broker hint, support snippet, support manifest, external-skill summary, probe prompt.",
        (
            "context_artifacts and context_compile_runs schema",
            "SkillIR compiler records skill_md/support context artifacts and loadability classes",
            "external-skill summaries, support snippets, and probe prompts remain classified/budgeted",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.12",
        "before_coding",
        "Choose tokenizer/token counting implementation per executor profile.",
        (
            "context compiler records token_count and budget_status for runtime artifacts",
            "effective config exposes executor_profile and token budget defaults",
            "context artifact tests assert token-budget behavior",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.13",
        "before_coding",
        "Define semantic-density, information-preservation, and context-value thresholds.",
        (
            "Settings min_semantic_density, min_information_preservation, and min_context_value_per_token",
            "context-value/token ledgers feed utility rollups",
            "semantic compression/context regression criteria in scripts/autoskill_acceptance.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.14",
        "before_coding",
        "Define support-artifact planning, loadability classes, approved directories, manifest schema, script/test policy, and integration-proposal handling for hook/tool/cron/service needs.",
        (
            "support artifact paths constrained to approved scripts/references/templates/schemas/data/assets/examples directories",
            "writer manifests include support artifact scan/budget/provenance coverage",
            "hidden infrastructure requirements are operator-review integration proposals",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.15",
        "before_coding",
        "Define no-human-prose and no-raw-transcript gates for runtime artifacts.",
        (
            "compiler/runtime artifact gates ban raw transcript/history/rationale unless explicitly promoted through SkillIR",
            "scanner blocks human-facing unsafe guidance and hidden directives",
            "scripts/autoskill_acceptance.py context criterion 31.ctx.6",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.16",
        "before_coding",
        "Implement the skill-package artifact planner with support-file allowlists, inclusion rubric, scanner bindings, manifest generation, and adjunct-request handling.",
        (
            "SkillIR compiler support artifact planning and manifest generation",
            "writer apply/manifest tests cover support artifact hashes and scanner/budget statuses",
            "sidecar/autoskill/tests/test_audit_writer_events.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.17",
        "before_coding",
        "Define sidecar authentication.",
        (
            "ingest and control bearer-token checks in autoskill.api.app",
            "default bind host is 127.0.0.1 and allow_public_bind is false",
            "/v1/config/effective reports auth configuration without secrets",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.18",
        "before_coding",
        "Define backup, retention, revocation, and derived-data deletion policy.",
        (
            "scripts/autoskill_backup.py and scripts/autoskill_restore.py",
            "revocation traversal preview/request APIs",
            "mutation-worker invalidation covers derived state families",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.19",
        "before_coding",
        "Define evolution transaction semantics and rollback-complete invariants.",
        (
            "evolution transaction APIs record transaction items and rollback metadata",
            "writer/topology/candidate paths create governed transactions",
            "sidecar/autoskill/tests/test_governance.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.20",
        "before_coding",
        "Define action-attribution risk tiers and which tool calls require counterfactual checks.",
        (
            "canonical attribution outcome taxonomy and risk tiers",
            "plugin before_tool_call can record blocked high-risk tool-boundary checks",
            "sidecar/autoskill/tests/test_attribution.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.21",
        "before_coding",
        "Define harmful-capability and dual-use skill classifier policy.",
        (
            "scanner classifies exfiltration, destructive command, credential harvesting, and policy override patterns",
            "red-team smoke covers deterministic harmful skill bundles",
            "activation gates block scanner failures",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.22",
        "before_coding",
        "Define topology operation thresholds for create, improve, compose, and decompose.",
        (
            "SkillGraphIR operation kinds create/improve/compose/decompose are first-class",
            "topology planner/API/store persists trials, apply gates, metrics, and rollback actions",
            "/v1/topology/metrics",
        ),
    ),
    HandoffChecklistEntry(
        "33.before.23",
        "before_coding",
        "Define co-use, sequence, partial-use, and false-positive retrieval metrics.",
        (
            "usage.aggregate mines co-use/sequence/partial-use/false-positive topology signals",
            "retrieval/context token ledgers feed utility and topology consumers",
            "stored replay corpus captures broker policy outcomes",
        ),
    ),
)


DURING_IMPLEMENTATION_CHECKLIST: tuple[HandoffChecklistEntry, ...] = (
    HandoffChecklistEntry(
        "33.during.1",
        "during_implementation",
        "Build migrations before logic.",
        (
            "migrations/0001_autoskill_schema.sql",
            "scripts/migrate.py",
            "docker compose config --quiet plus full pytest gates",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.2",
        "during_implementation",
        "Build redaction before ingest.",
        (
            "autoskill.core.redaction and plugin redaction modules",
            "ingest persists redacted event envelopes",
            "sidecar/autoskill/tests/test_ingest_auth.py and plugin hook smoke tests",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.3",
        "during_implementation",
        "Build historical discovery as read-only inventory before historical import.",
        (
            "historical discovery records source inventory and hashed roots without mutating sources",
            "historical import parser checkpoints run after discovery",
            "sidecar/autoskill/tests/test_historical_import.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.4",
        "during_implementation",
        "Build scheduler before analysis jobs.",
        (
            "sidecar-owned scheduler store and scheduler_defaults",
            "worker_main scheduler/maintenance/mutation pools",
            "sidecar/autoskill/tests/test_scheduler_defaults.py and test_scheduler_api.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.5",
        "during_implementation",
        "Build scanner/evaluator before writer.",
        (
            "scanner and evaluator services block unsafe candidates before writer apply",
            "activation gate checks scanner/evaluator/proposal gates",
            "sidecar/autoskill/tests/test_evaluator.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.6",
        "during_implementation",
        "Build rollback before autonomous apply.",
        (
            "writer archive and rollback primitives",
            "critical canary freeze queues rollback revocations",
            "mutation worker executes rollback requests",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.7",
        "during_implementation",
        "Build evolution transaction tables before autonomous apply.",
        (
            "evolution_transactions and evolution_transaction_items schema/store",
            "/v1/evolution/transactions/* APIs",
            "governance tests cover transaction updates and items",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.8",
        "during_implementation",
        "Build provenance/revocation traversal before autonomous apply.",
        (
            "provenance_edges and revocation request stores",
            "/v1/revocations/preview and /v1/revocations/request",
            "historical source revocation queues derived invalidation jobs",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.9",
        "during_implementation",
        "Build retrieval logs before retrieval tuning.",
        (
            "retrieval_logs and broker telemetry stores",
            "context token ledger records retrieved/rendered/injected/used/outcomes",
            "sidecar/autoskill/tests/test_broker.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.10",
        "during_implementation",
        "Build context broker logs before enabling hints.",
        (
            "plugin runtime context hints are disabled/fail-soft by default",
            "broker audit and policy review endpoints require valid audit/replay evidence",
            "plugin before_prompt_build smoke tests",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.11",
        "during_implementation",
        "Build body-level indexing before retrieval tuning.",
        (
            "body_index_documents table and retrieval body-index candidate path",
            "embedding source discovery includes body-index documents",
            "usage rollups count body-index documents",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.12",
        "during_implementation",
        "Build context artifact registry before any compiler output activates.",
        (
            "context_artifacts and context_compile_runs schema/store",
            "SkillIR compiler registers skill_md and support context artifacts",
            "writer activation uses context artifact hashes and statuses",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.13",
        "during_implementation",
        "Build token-budget, routing-equivalence, and information-preservation gates before autonomous apply.",
        (
            "compiled artifacts record token budget, routing-equivalence, and preservation metadata",
            "activation gates reject missing/failed context proof",
            "scripts/autoskill_acceptance.py context criteria",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.14",
        "during_implementation",
        "Build action-attribution logs before high-risk runtime enforcement.",
        (
            "action_attribution_checks store and /v1/attribution/action-checks",
            "runtime tool-boundary blocking is available but disabled by default",
            "plugin before_tool_call tests record blocked high-risk decisions",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.15",
        "during_implementation",
        "Build archive before promotion.",
        (
            "writer archive manifests and archive_active_skill_and_remove",
            "utility promotion restores archived manifests",
            "sidecar/autoskill/tests/test_audit_writer_events.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.16",
        "during_implementation",
        "Build topology operation logs before enabling compose/decompose.",
        (
            "skill_graph_operations and trials are persisted before apply",
            "topology metrics expose create/improve/compose/decompose operation counts",
            "proposal review endpoint surfaces topology statuses",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.17",
        "during_implementation",
        "Build composition/decomposition evaluators before autonomous topology changes.",
        (
            "compose/decompose planners emit operation-specific evaluation trials",
            "broker replay/canary gates evaluate topology routing changes",
            "sidecar/autoskill/tests/test_topology_services.py",
        ),
    ),
    HandoffChecklistEntry(
        "33.during.18",
        "during_implementation",
        "Build audit before mutation.",
        (
            "audit store and hash-chain verifier",
            "audit.verify registered as a maintenance schedule",
            "writer/direct mutation APIs record content-safe trace/audit spans",
        ),
    ),
)


SHIP_GATE = HandoffChecklistEntry(
    "33.ship.1",
    "ship_gate",
    "Do not ship autonomous apply until scanner, evaluator, deterministic writer, rollback, evolution transactions, provenance/revocation traversal, action attribution, and audit are all operational.",
    (
        "scanner/evaluator/writer/rollback/governance/attribution/audit surfaces are implemented and tested",
        "mutation-worker apply fails closed unless explicitly policy-approved",
        "scripts/autoskill_acceptance.py and this handoff report provide executable operator crosswalks",
    ),
)


def build_report() -> dict[str, Any]:
    risks = [item.to_json() for item in RISK_REGISTER]
    before = [item.to_json() for item in BEFORE_CODING_CHECKLIST]
    during = [item.to_json() for item in DURING_IMPLEMENTATION_CHECKLIST]
    ship_gates = [SHIP_GATE.to_json()]
    validation_errors = validate_report_items(
        RISK_REGISTER,
        (*BEFORE_CODING_CHECKLIST, *DURING_IMPLEMENTATION_CHECKLIST, SHIP_GATE),
    )
    all_items = [*risks, *before, *during, *ship_gates]
    satisfied = sum(1 for item in all_items if item["status"] in READY_STATUSES)
    return {
        "schema": "autoskill.handoff-governance-report.v1",
        "ready": not validation_errors and satisfied == len(all_items),
        "summary": {
            "risks": len(risks),
            "before_coding": len(before),
            "during_implementation": len(during),
            "ship_gates": len(ship_gates),
            "satisfied": satisfied,
            "total_items": len(all_items),
            "validation_errors": validation_errors,
        },
        "risk_register": risks,
        "developer_handoff": {
            "before_coding": before,
            "during_implementation": during,
            "ship_gates": ship_gates,
        },
    }


def validate_report_items(
    risks: tuple[RiskRegisterEntry, ...],
    checklist: tuple[HandoffChecklistEntry, ...],
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in risks:
        _validate_common(
            errors=errors,
            seen=seen,
            item_id=item.risk_id,
            status=item.status,
            text=item.risk,
            evidence=item.evidence,
        )
        if not item.mitigation.strip():
            errors.append(f"{item.risk_id} has empty mitigation")
        _validate_no_placeholder(errors, item.risk_id, item.mitigation)
    for item in checklist:
        _validate_common(
            errors=errors,
            seen=seen,
            item_id=item.checklist_id,
            status=item.status,
            text=item.item,
            evidence=item.evidence,
        )
        if not item.phase.strip():
            errors.append(f"{item.checklist_id} has empty phase")
        _validate_no_placeholder(errors, item.checklist_id, item.phase)
    return errors


def _validate_common(
    *,
    errors: list[str],
    seen: set[str],
    item_id: str,
    status: str,
    text: str,
    evidence: tuple[str, ...],
) -> None:
    if item_id in seen:
        errors.append(f"duplicate item id: {item_id}")
    seen.add(item_id)
    if status not in READY_STATUSES:
        errors.append(f"{item_id} has non-ready status: {status}")
    if not text.strip():
        errors.append(f"{item_id} has empty text")
    _validate_no_placeholder(errors, item_id, text)
    if not evidence:
        errors.append(f"{item_id} has no evidence")
    for value in evidence:
        if not value.strip():
            errors.append(f"{item_id} has empty evidence")
        _validate_no_placeholder(errors, item_id, value)


def _validate_no_placeholder(errors: list[str], item_id: str, value: str) -> None:
    lowered = value.lower()
    if "todo" in lowered or "tbd" in lowered:
        errors.append(f"{item_id} has placeholder text: {value}")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SkillKernel Handoff Governance Report",
        "",
        f"Ready: {str(report['ready']).lower()}",
        f"Risks: {report['summary']['risks']}",
        f"Before-coding checklist: {report['summary']['before_coding']}",
        f"During-implementation checklist: {report['summary']['during_implementation']}",
        f"Ship gates: {report['summary']['ship_gates']}",
        "",
        "## Risk Register",
    ]
    for item in report["risk_register"]:
        lines.append(f"- {item['risk_id']} {item['status']}: {item['risk']}")
        lines.append(f"  - Mitigation: {item['mitigation']}")
        for evidence in item["evidence"]:
            lines.append(f"  - Evidence: {evidence}")
    lines.append("")
    for section, title in (
        ("before_coding", "Before Coding"),
        ("during_implementation", "During Implementation"),
        ("ship_gates", "Ship Gates"),
    ):
        lines.append(f"## {title}")
        for item in report["developer_handoff"][section]:
            lines.append(f"- {item['checklist_id']} {item['status']}: {item['item']}")
            for evidence in item["evidence"]:
                lines.append(f"  - Evidence: {evidence}")
        lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Emit the SkillKernel Section 32/33 risk and handoff crosswalk.",
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
