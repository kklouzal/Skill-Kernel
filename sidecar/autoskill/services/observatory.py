from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from autoskill.core.config import Settings
from autoskill.services.embedding_generation import embedding_provider_policy

OBSERVATORY_SCHEMA_VERSION = "skillkernel.observatory.v1"
LIVE_SCHEMA_VERSION = "skillkernel.observatory.live.v1"

HEALTH_ORDER = {
    "healthy": 0,
    "unknown": 1,
    "degraded": 2,
    "frozen": 3,
    "blocked": 4,
    "offline": 5,
}

EVALUATION_FAILURE_STATUSES = {"blocked", "failed"}

REQUIRED_METRICS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "ingest": ("ingest",),
    "historical": ("ingest",),
    "redaction": ("redaction_counts",),
    "vault": ("raw_vault_summary",),
    "fidelity": ("evidence_fidelity_status",),
    "spool": ("spool_backlog",),
    "evidence": ("ingest",),
    "adjudication": ("semantic_adjudication_status",),
    "autonomy": ("autonomy_decision_status",),
    "replay": ("broker_replay_episode_status",),
    "retrieval": ("retrieval_decisions", "embedding_backlog"),
    "broker": ("retrieval_decisions", "context_hint_injection_count"),
    "topology": ("skill_creation_improvement_counts",),
    "skills": ("skill_lifecycle_counts",),
    "artifact": ("skill_creation_improvement_counts",),
    "context": ("context_hint_token_cost", "context_hint_token_ledger_count"),
    "scanner": ("scanner_reject_counts",),
    "evaluator": ("evaluation_pass_fail_counts",),
    "writer": ("skill_creation_improvement_counts",),
    "lifecycle": ("skill_lifecycle_counts",),
    "rollback": ("rollback_freeze_counts",),
    "escalation": ("administrative_escalation_status",),
    "jobs": ("job_queue_depth",),
    "profiles": ("embedding_backlog",),
    "storage": ("postgres_table_index_growth",),
    "audit": ("audit",),
    "actions": ("audit",),
    "observatory": ("sidecar_latency_ms",),
}

LATENCY_OPERATION_KINDS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "ingest": ("plugin_capture", "ingest"),
    "redaction": ("redaction",),
    "vault": ("audit",),
    "evidence": ("evidence", "memory"),
    "adjudication": ("llm_call",),
    "autonomy": ("evolution", "scheduler"),
    "replay": ("retrieval", "evaluator"),
    "retrieval": ("retrieval", "embedding_call"),
    "broker": ("broker",),
    "topology": ("evolution",),
    "skills": ("compiler",),
    "artifact": ("compiler",),
    "context": ("compiler",),
    "scanner": ("scanner",),
    "evaluator": ("evaluator",),
    "writer": ("writer",),
    "lifecycle": ("archive", "promotion"),
    "rollback": ("rollback",),
    "escalation": ("audit",),
    "jobs": ("scheduler", "job"),
    "profiles": ("llm_call", "embedding_call"),
    "audit": ("tool_attribution",),
}


@dataclass(frozen=True)
class StationDefinition:
    component_id: str
    display_name: str
    subsystem_ids: tuple[str, ...]
    purpose: str
    object_kinds: tuple[str, ...]
    metric_family: str


STATIONS: tuple[StationDefinition, ...] = (
    StationDefinition(
        "openclaw_live_capture",
        "OpenClaw live capture",
        ("capture_bootstrap",),
        "Plugin hook and SDK-event capture from active OpenClaw sessions.",
        ("captured_event", "hook_matrix", "session_coverage"),
        "ingest",
    ),
    StationDefinition(
        "historical_ingestion",
        "Historical bootstrap",
        ("capture_bootstrap",),
        "Discovery and ingestion of existing transcripts, trajectories, memory files, "
        "task records, and skills.",
        ("historical_import_run", "historical_source", "parser_finding"),
        "historical",
    ),
    StationDefinition(
        "redaction_taint",
        "Redaction + taint",
        ("capture_bootstrap",),
        "Sensitive-content reduction, taint propagation, confidence, and storage eligibility.",
        ("redaction_finding", "taint_graph", "revocation_path"),
        "redaction",
    ),
    StationDefinition(
        "raw_evidence_vault",
        "Raw-evidence vault",
        ("autonomy_adjudication",),
        "Governed full-fidelity evidence retention, raw/declassified access policy, "
        "raw-access audit, retention, revocation, and derived-data traversal.",
        ("raw_vault_record", "declassification_report", "access_audit"),
        "vault",
    ),
    StationDefinition(
        "evidence_fidelity",
        "Evidence fidelity",
        ("learning_memory", "autonomy_adjudication"),
        "Evidence-fidelity tiers, degraded-autonomy states, and supported "
        "decision-family matrix.",
        ("evidence_fidelity_status", "source_item", "unsupported_decision_family"),
        "fidelity",
    ),
    StationDefinition(
        "spool_ingest",
        "Spool + ingest",
        ("capture_bootstrap",),
        "Plugin spool, sidecar ingest API, idempotency, and normalized forwarding.",
        ("spool_record", "ingest_batch", "normalization_result"),
        "spool",
    ),
    StationDefinition(
        "event_normalization",
        "Event normalization",
        ("capture_bootstrap",),
        "Canonical events, chunks, spans, and evidence inputs.",
        ("canonical_event", "span", "evidence_input"),
        "ingest",
    ),
    StationDefinition(
        "evidence_memory",
        "Evidence + memory",
        ("learning_memory",),
        "Evidence extraction, memory derivation, provenance, maturity, and poisoning defenses.",
        ("evidence_cluster", "memory_record", "provenance_path"),
        "evidence",
    ),
    StationDefinition(
        "semantic_adjudication",
        "LLM semantic adjudication",
        ("learning_memory", "autonomy_adjudication"),
        "Structured LLM verdicts for intent reconstruction, replay intent synthesis, "
        "memory declassification, topology choice, context equivalence, broker misses, "
        "and ambiguous evidence.",
        ("semantic_adjudication", "llm_verdict", "deterministic_admissibility"),
        "adjudication",
    ),
    StationDefinition(
        "autonomy_orchestrator",
        "Autonomy decision orchestrator",
        ("autonomy_adjudication", "lifecycle_governance"),
        "Calibrated selective-trust decisions, soft-threshold policy, fallback ladders, "
        "policy trials, threshold-deadlock findings, and selected autonomous actions.",
        ("autonomy_decision", "threshold_policy", "fallback_ladder"),
        "autonomy",
    ),
    StationDefinition(
        "replay_corpus",
        "Replay + canary corpus",
        ("autonomy_adjudication", "quality_gates"),
        "Replay episode synthesis, redacted intent, expected decisions, canary "
        "eligibility, and corpus evidence coverage.",
        ("broker_replay_episode", "redacted_intent", "canary_result"),
        "replay",
    ),
    StationDefinition(
        "retrieval_indexing",
        "Retrieval + indexing",
        ("learning_memory", "runtime_context"),
        "Lexical/vector indexing, pgvector status, re-embedding, exact rerank, "
        "and graph expansion indexes.",
        ("retrieval_audit", "embedding_profile", "rerank_example"),
        "retrieval",
    ),
    StationDefinition(
        "broker_runtime",
        "Runtime broker",
        ("runtime_context",),
        "Skill-context selection, no-skill decisions, shadowing control, and context "
        "hint rendering.",
        ("broker_decision", "scoring_waterfall", "rendered_hint"),
        "broker",
    ),
    StationDefinition(
        "opportunity_mining",
        "Opportunity miner",
        ("learning_memory", "topology_design"),
        "Candidate discovery from clustered evidence, repeated workflows, failures, "
        "corrections, and co-use.",
        ("opportunity", "rejected_candidate", "candidate_seed"),
        "topology",
    ),
    StationDefinition(
        "topology_operations",
        "Topology operations",
        ("topology_design",),
        "Create, improve, compose, decompose, merge, archive, promote, rollback, "
        "and freeze decisions.",
        ("topology_operation", "curation_decision", "skill_lineage"),
        "topology",
    ),
    StationDefinition(
        "skill_ir_graph_ir",
        "SkillIR / SkillGraphIR",
        ("topology_design",),
        "Canonical skill representation, graph workflows, version state, contracts, "
        "and effect signatures.",
        ("skill_ir", "skill_graph_ir", "effect_signature"),
        "skills",
    ),
    StationDefinition(
        "artifact_planner",
        "Skill package planner",
        ("topology_design", "artifact_mutation"),
        "Ancillary-file planning and support artifact risk decisions.",
        ("artifact_plan", "manifest", "support_file_preview"),
        "artifact",
    ),
    StationDefinition(
        "context_compiler",
        "Context compiler",
        ("runtime_context", "artifact_mutation"),
        "Compiles SkillIR to compact runtime skill text, broker hints, and context "
        "excerpts under token budgets.",
        ("compiled_skill_md", "broker_hint", "token_diff"),
        "context",
    ),
    StationDefinition(
        "scanner_security",
        "Scanner + security",
        ("quality_gates", "artifact_mutation"),
        "Static, semantic, capability, harmful-skill, injection, artifact, and bundle scanning.",
        ("scanner_finding", "risk_matrix", "taint_to_artifact_path"),
        "scanner",
    ),
    StationDefinition(
        "evaluator_probes",
        "Evaluator + probes",
        ("quality_gates", "artifact_mutation"),
        "Target, regression, adversarial, canary, benchmark, and counterfactual trials.",
        ("evaluation_run", "probe_fixture", "comparison_trial"),
        "evaluator",
    ),
    StationDefinition(
        "deterministic_writer",
        "Deterministic writer",
        ("artifact_mutation",),
        "Path-contained staging, manifest hashing, file writes, activation locks, "
        "and transactionality.",
        ("writer_transaction", "file_diff", "rollback_pointer"),
        "writer",
    ),
    StationDefinition(
        "activation_curation",
        "Activation + curation",
        ("artifact_mutation", "lifecycle_governance"),
        "Active/archive/promotion lifecycle, active budget, utility rollups, and "
        "skill technical debt.",
        ("skill_lifecycle", "curation_decision", "canary_result"),
        "lifecycle",
    ),
    StationDefinition(
        "canary_rollback",
        "Canary + rollback",
        ("runtime_context", "artifact_mutation", "lifecycle_governance"),
        "Runtime canary observation, rollback, freeze, and derived-data revocation.",
        ("evolution_transaction", "revocation_graph", "post_rollback_validation"),
        "rollback",
    ),
    StationDefinition(
        "administrative_escalation",
        "Administrative escalation",
        ("autonomy_adjudication", "lifecycle_governance"),
        "Exceptional authority-boundary cases, attempted autonomous alternatives, "
        "escalation reason codes, and resolution state.",
        ("administrative_escalation", "policy_boundary", "safe_next_action"),
        "escalation",
    ),
    StationDefinition(
        "scheduler_jobs",
        "Scheduler + jobs",
        ("control_storage",),
        "Sidecar schedules, jobs, leases, attempts, backoff, and queue pressure.",
        ("job", "schedule", "lease", "attempt_timeline"),
        "jobs",
    ),
    StationDefinition(
        "model_embedding",
        "Model + embedding profiles",
        ("quality_gates", "control_storage"),
        "Text model profile, embedding profile, qualification gates, and invocation health.",
        ("profile_qualification", "structured_output_failure", "embedding_sanity_probe"),
        "profiles",
    ),
    StationDefinition(
        "storage_db",
        "Postgres + pgvector",
        ("control_storage",),
        "DB health, migrations, index health, read models, partitions, and retention.",
        ("db_health_report", "index_status", "materialized_view_refresh"),
        "storage",
    ),
    StationDefinition(
        "audit_trace",
        "Audit + trace spine",
        ("lifecycle_governance", "control_storage"),
        "Correlation across events, jobs, actions, model calls, evaluations, artifacts, "
        "and mutations.",
        ("trace", "span_graph", "action_audit", "causal_attribution"),
        "audit",
    ),
    StationDefinition(
        "operator_action_gateway",
        "Operator action gateway",
        ("lifecycle_governance",),
        "Role checks, confirmations, idempotency, guarded action dispatch, and action audit links.",
        ("admin_action", "policy_check", "idempotency_key", "action_receipt"),
        "actions",
    ),
    StationDefinition(
        "observatory_admin",
        "Observatory self-health",
        ("control_storage",),
        "Admin API, frontend serving, live stream, read-model freshness, browser "
        "diagnostics, and dashboard performance.",
        ("admin_self_health", "frontend_error", "sequence_gap"),
        "observatory",
    ),
)

SUBSYSTEMS: tuple[dict[str, Any], ...] = (
    {
        "subsystem_id": "capture_bootstrap",
        "display_name": "Capture + bootstrap workcell",
        "station_ids": [
            "openclaw_live_capture",
            "historical_ingestion",
            "redaction_taint",
            "spool_ingest",
            "event_normalization",
        ],
        "diagnostic_questions": [
            "Are live and historical inputs arriving?",
            "Are source items parsed, skipped, quarantined, or revoked?",
            "Is redaction removing too much useful structure?",
        ],
    },
    {
        "subsystem_id": "learning_memory",
        "display_name": "Learning + memory workcell",
        "station_ids": [
            "evidence_memory",
            "evidence_fidelity",
            "semantic_adjudication",
            "retrieval_indexing",
            "opportunity_mining",
        ],
        "diagnostic_questions": [
            "Is evidence maturing into useful memory?",
            "Are retrieval indexes fresh?",
            "Are useful opportunities being produced?",
        ],
    },
    {
        "subsystem_id": "autonomy_adjudication",
        "display_name": "Autonomy + adjudication workcell",
        "station_ids": [
            "raw_evidence_vault",
            "evidence_fidelity",
            "semantic_adjudication",
            "autonomy_orchestrator",
            "replay_corpus",
            "administrative_escalation",
            "model_embedding",
            "audit_trace",
        ],
        "diagnostic_questions": [
            "Is semantic autonomy supported by sufficient evidence?",
            "Are LLM adjudications bounded by deterministic gates?",
            "Are replay and escalation states visible?",
        ],
    },
    {
        "subsystem_id": "runtime_context",
        "display_name": "Runtime context workcell",
        "station_ids": [
            "retrieval_indexing",
            "broker_runtime",
            "context_compiler",
            "canary_rollback",
        ],
        "diagnostic_questions": [
            "Is the broker selecting fewer, better skills?",
            "Is context token pressure bounded?",
            "Are canaries feeding rollback safely?",
        ],
    },
    {
        "subsystem_id": "topology_design",
        "display_name": "Topology design workcell",
        "station_ids": [
            "opportunity_mining",
            "topology_operations",
            "skill_ir_graph_ir",
            "artifact_planner",
        ],
        "diagnostic_questions": [
            "Are create/improve/compose/decompose proposals well explained?",
            "Are duplicate and external-skill collisions visible?",
            "Does every proposal preserve provenance?",
        ],
    },
    {
        "subsystem_id": "quality_gates",
        "display_name": "Quality gates workcell",
        "station_ids": [
            "scanner_security",
            "evaluator_probes",
            "replay_corpus",
            "model_embedding",
        ],
        "diagnostic_questions": [
            "Which gates accepted or rejected work?",
            "Are scanner or evaluator failures concentrated?",
            "Are model and embedding profiles qualified?",
        ],
    },
    {
        "subsystem_id": "artifact_mutation",
        "display_name": "Artifact mutation workcell",
        "station_ids": [
            "artifact_planner",
            "context_compiler",
            "scanner_security",
            "evaluator_probes",
            "deterministic_writer",
            "activation_curation",
            "canary_rollback",
        ],
        "diagnostic_questions": [
            "Can every file mutation be traced to policy and evidence?",
            "Are manifests and rollback pointers valid?",
            "Are activation gates blocking unsafe changes?",
        ],
    },
    {
        "subsystem_id": "lifecycle_governance",
        "display_name": "Lifecycle governance workcell",
        "station_ids": [
            "activation_curation",
            "canary_rollback",
            "autonomy_orchestrator",
            "administrative_escalation",
            "audit_trace",
            "operator_action_gateway",
        ],
        "diagnostic_questions": [
            "Which skills are active, archived, frozen, or revoked?",
            "Can changes roll back with derived data revoked?",
            "Are operator actions policy checked and audited?",
        ],
    },
    {
        "subsystem_id": "control_storage",
        "display_name": "Control + storage workcell",
        "station_ids": [
            "scheduler_jobs",
            "model_embedding",
            "storage_db",
            "audit_trace",
            "observatory_admin",
        ],
        "diagnostic_questions": [
            "Is the sidecar scheduler moving work?",
            "Is storage/index/read-model health trustworthy?",
            "Is Observatory telemetry fresh enough to believe?",
        ],
    },
)

PIPELINE_EDGES: tuple[tuple[str, str, str], ...] = (
    ("openclaw_live_capture", "spool_ingest", "live_event"),
    ("historical_ingestion", "redaction_taint", "historical_source"),
    ("redaction_taint", "event_normalization", "redacted_event"),
    ("redaction_taint", "raw_evidence_vault", "raw_policy"),
    ("spool_ingest", "event_normalization", "ingested_event"),
    ("event_normalization", "evidence_memory", "evidence_input"),
    ("raw_evidence_vault", "evidence_fidelity", "fidelity_policy"),
    ("evidence_fidelity", "semantic_adjudication", "supported_decision"),
    ("semantic_adjudication", "autonomy_orchestrator", "semantic_verdict"),
    ("autonomy_orchestrator", "replay_corpus", "replay_candidate"),
    ("evidence_memory", "retrieval_indexing", "index_source"),
    ("retrieval_indexing", "broker_runtime", "runtime_candidate"),
    ("evidence_memory", "opportunity_mining", "evidence_cluster"),
    ("opportunity_mining", "topology_operations", "candidate"),
    ("topology_operations", "skill_ir_graph_ir", "skill_operation"),
    ("skill_ir_graph_ir", "artifact_planner", "skill_ir"),
    ("artifact_planner", "context_compiler", "artifact_plan"),
    ("context_compiler", "scanner_security", "compiled_context"),
    ("scanner_security", "evaluator_probes", "scan_pass"),
    ("replay_corpus", "evaluator_probes", "replay_trial"),
    ("evaluator_probes", "deterministic_writer", "gate_pass"),
    ("deterministic_writer", "activation_curation", "writer_transaction"),
    ("activation_curation", "canary_rollback", "active_skill"),
    ("canary_rollback", "broker_runtime", "runtime_feedback"),
    ("administrative_escalation", "operator_action_gateway", "guarded_request"),
    ("scheduler_jobs", "evidence_memory", "maintenance_job"),
    ("scheduler_jobs", "topology_operations", "mutation_job"),
    ("storage_db", "observatory_admin", "read_model"),
    ("audit_trace", "observatory_admin", "trace_snapshot"),
    ("operator_action_gateway", "scheduler_jobs", "guarded_action_job"),
    ("operator_action_gateway", "audit_trace", "action_audit"),
)

REASON_CODES: dict[str, str] = {
    "database-not-configured": (
        "The sidecar has no database DSN, so durable read models are unavailable."
    ),
    "admin-token-not-configured": "The web admin surface has no dedicated token configured.",
    "control-token-not-configured": "Control endpoints are not protected by a control token.",
    "ingest-token-not-configured": "Ingest endpoints are not protected by an ingest token.",
    "missing-required-signal": "The component lacks one or more required signal classes.",
    "read-model-missing": "No bounded Observatory read model exists for this object class yet.",
    "no-ingest-events-observed": (
        "The ingest read model is present but has not observed captured events."
    ),
    "telemetry-partial": "Telemetry exists but coverage is incomplete or sampled.",
    "telemetry-stale": "Read-model freshness exceeds the configured warning threshold.",
    "spool-diagnostics-required": "Plugin spool state is outside sidecar database visibility.",
    "failed-jobs-present": "One or more sidecar jobs are failed.",
    "queued-work-present": "Runnable work exists in the sidecar queue.",
    "scanner-rejections-present": "Scanner findings have rejected or blocked skill versions.",
    "evaluation-failures-present": "Evaluator/probe failures are present.",
    "frozen-skills-present": "One or more skills are frozen.",
    "critical-canary-present": "A critical canary state is present.",
    "drift-violations-present": "Environment contract drift violations exist.",
    "embedding-backlog-present": "Embeddings or embedding jobs are pending.",
    "audit-chain-unverified": "Audit chain verification failed or was unavailable.",
    "embedding-endpoint-not-configured": "The configured embedding provider has no endpoint URL.",
    "raw-content-disabled": "Raw content reveal is disabled by configuration.",
    "frontend-serving-unavailable": (
        "The Observatory frontend is not available through the configured serving mode."
    ),
}


def build_observatory_snapshot(
    *,
    settings: Settings,
    status: dict[str, Any],
    operator_metrics: dict[str, Any],
    worker_health: dict[str, Any],
    audit_chain_valid: bool,
    static_available: bool,
    workspace_id: str | None,
    window_minutes: int,
) -> dict[str, Any]:
    captured_at = datetime.now(UTC)
    snapshot_seq = _snapshot_seq(captured_at)
    metrics = _dict(operator_metrics.get("metrics"))
    dashboards = _dict(operator_metrics.get("dashboards"))
    read_model_age_seconds = _read_model_age_seconds(operator_metrics, captured_at)
    components = [
        _component_snapshot(
            station,
            settings=settings,
            status=status,
            metrics=metrics,
            worker_health=worker_health,
            audit_chain_valid=audit_chain_valid,
            static_available=static_available,
            captured_at=captured_at,
            read_model_age_seconds=read_model_age_seconds,
        )
        for station in STATIONS
    ]
    component_by_id = {component["component_id"]: component for component in components}
    edges = [
        _edge_snapshot(edge, metrics=metrics, component_by_id=component_by_id)
        for edge in PIPELINE_EDGES
    ]
    issues = _issue_board(
        settings=settings,
        status=status,
        metrics=metrics,
        components=components,
        audit_chain_valid=audit_chain_valid,
        static_available=static_available,
    )
    subsystems = [
        _subsystem_snapshot(subsystem, component_by_id=component_by_id, edges=edges, issues=issues)
        for subsystem in SUBSYSTEMS
    ]
    global_health = _rollup_health([component["health"] for component in components])
    if any(issue["severity"] == "critical" for issue in issues):
        global_health = "blocked"
    elif any(issue["severity"] == "high" for issue in issues) and global_health == "healthy":
        global_health = "degraded"

    return {
        "schema_version": OBSERVATORY_SCHEMA_VERSION,
        "snapshot_seq": snapshot_seq,
        "workspace_id": workspace_id,
        "captured_at": captured_at.isoformat(),
        "window_minutes": window_minutes,
        "base_path": _normalized_base_path(settings.web_admin_base_path),
        "auth": {
            "mode": settings.web_admin_auth_mode,
            "dedicated_admin_token_configured": bool(settings.web_admin_token),
            "control_token_fallback_configured": bool(settings.control_token),
            "roles": ["viewer", "auditor", "operator", "admin"],
            "raw_content_enabled": settings.web_admin_raw_content_enabled,
        },
        "global_health": global_health,
        "fitness": _system_fitness(components=components, issues=issues, metrics=metrics),
        "kpis": _kpis(metrics=metrics, status=status, components=components),
        "data_quality": _global_data_quality(
            settings=settings,
            metrics=metrics,
            static_available=static_available,
            read_model_age_seconds=read_model_age_seconds,
        ),
        "pipeline": {
            "stations": components,
            "edges": edges,
            "invariants": _pipeline_invariants(metrics=metrics, components=components),
        },
        "subsystems": subsystems,
        "issue_board": issues,
        "dashboards": dashboards,
        "search_facets": _search_facets(),
        "command_palette": _command_palette(),
        "reason_code_catalog": [
            {"reason_code": key, "description": value}
            for key, value in sorted(REASON_CODES.items())
        ],
    }


def build_live_envelope(
    snapshot: dict[str, Any],
    *,
    last_seq: int | None = None,
    cursor_seq: int | None = None,
) -> dict[str, Any]:
    seq = int(snapshot["snapshot_seq"])
    event_type = "snapshot" if last_seq is None or last_seq < seq else "heartbeat"
    sent_at = datetime.now(UTC).isoformat()
    return {
        "schema_version": LIVE_SCHEMA_VERSION,
        "seq": seq,
        "cursor_seq": int(cursor_seq) if cursor_seq is not None else int(last_seq or 0),
        "event_type": event_type,
        "kind": event_type,
        "sent_at": sent_at,
        "captured_at": snapshot["captured_at"],
        "requires_snapshot_reload": bool(last_seq is not None and last_seq + 10_000 < seq),
        "payload": snapshot
        if event_type == "snapshot"
        else {
            "global_health": snapshot["global_health"],
            "issue_count": len(snapshot["issue_board"]),
            "component_health": {
                component["component_id"]: component["health"]
                for component in snapshot["pipeline"]["stations"]
            },
        },
    }


def search_observatory(snapshot: dict[str, Any], query: str, *, limit: int = 25) -> dict[str, Any]:
    needle = query.strip().casefold()
    results: list[dict[str, Any]] = []
    for component in snapshot["pipeline"]["stations"]:
        _append_match(
            results,
            needle=needle,
            object_type="component",
            object_id=component["component_id"],
            title=component["display_name"],
            summary=component["purpose"],
            url=f"/admin/components/{component['component_id']}",
            reason_codes=component.get("reason_codes", []),
        )
    for subsystem in snapshot["subsystems"]:
        _append_match(
            results,
            needle=needle,
            object_type="subsystem",
            object_id=subsystem["subsystem_id"],
            title=subsystem["display_name"],
            summary="; ".join(subsystem["diagnostic_questions"]),
            url=f"/admin/subsystems/{subsystem['subsystem_id']}",
            reason_codes=subsystem.get("reason_codes", []),
        )
    for issue in snapshot["issue_board"]:
        _append_match(
            results,
            needle=needle,
            object_type="issue",
            object_id=issue["issue_id"],
            title=issue["title"],
            summary=issue["summary"],
            url=issue["deep_link"],
            reason_codes=issue["reason_codes"],
        )
    for invariant in snapshot["pipeline"]["invariants"]:
        _append_match(
            results,
            needle=needle,
            object_type="pipeline_invariant",
            object_id=str(invariant["invariant_id"]),
            title=str(invariant["invariant_id"]).replace("-", " ").title(),
            summary=str(invariant["description"]),
            url=str(invariant["deep_link"]),
            reason_codes=list(invariant.get("reason_codes", [])),
        )
    for subsystem in snapshot["subsystems"]:
        for playbook in subsystem.get("playbooks", []):
            playbook_id = str(playbook["playbook_id"])
            _append_match(
                results,
                needle=needle,
                object_type="playbook",
                object_id=playbook_id,
                title=playbook_id.replace("-", " ").title(),
                summary=str(playbook["summary"]),
                url=f"/admin/playbooks/{playbook_id}",
                reason_codes=list(subsystem.get("reason_codes", [])),
            )
    for command in snapshot.get("command_palette", []):
        command_id = str(command["command"])
        _append_match(
            results,
            needle=needle,
            object_type="command",
            object_id=command_id,
            title=str(command["label"]),
            summary=str(command["target"]),
            url=str(command["target"]),
            reason_codes=[],
        )
    for reason_code, description in REASON_CODES.items():
        _append_match(
            results,
            needle=needle,
            object_type="reason_code",
            object_id=reason_code,
            title=reason_code,
            summary=description,
            url=f"/admin/search?query={reason_code}",
            reason_codes=[reason_code],
        )
    return {
        "query": query,
        "limit": max(1, min(limit, 100)),
        "results": results[: max(1, min(limit, 100))],
    }


def object_microscope(
    snapshot: dict[str, Any],
    *,
    object_type: str,
    object_id: str,
) -> dict[str, Any]:
    if object_type in {"storage", "storage_db", "db_health_report"} and object_id in {
        "storage",
        "storage_db",
        "db_health_report",
    }:
        return storage_microscope(snapshot)
    for component in snapshot["pipeline"]["stations"]:
        if object_type == "component" and component["component_id"] == object_id:
            return _microscope_payload(
                object_type=object_type,
                object_id=object_id,
                title=component["display_name"],
                summary=component["purpose"],
                diagnostics=component,
                upstream=_upstream_edges(snapshot, component["component_id"]),
                downstream=_downstream_edges(snapshot, component["component_id"]),
            )
    for subsystem in snapshot["subsystems"]:
        if object_type == "subsystem" and subsystem["subsystem_id"] == object_id:
            return _microscope_payload(
                object_type=object_type,
                object_id=object_id,
                title=subsystem["display_name"],
                summary="; ".join(subsystem["diagnostic_questions"]),
                diagnostics=subsystem,
                upstream=[],
                downstream=[
                    {"object_type": "component", "object_id": station_id}
                    for station_id in subsystem["station_ids"]
                ],
            )
    for issue in snapshot["issue_board"]:
        if object_type == "issue" and issue["issue_id"] == object_id:
            return _microscope_payload(
                object_type=object_type,
                object_id=object_id,
                title=issue["title"],
                summary=issue["summary"],
                diagnostics=issue,
                upstream=issue.get("evidence_refs", []),
                downstream=issue.get("safe_next_actions", []),
            )
    for invariant in snapshot["pipeline"]["invariants"]:
        if object_type in {"pipeline_invariant", "invariant"} and str(
            invariant["invariant_id"]
        ) == object_id:
            return _microscope_payload(
                object_type="pipeline_invariant",
                object_id=object_id,
                title=str(invariant["invariant_id"]).replace("-", " ").title(),
                summary=str(invariant["description"]),
                diagnostics=invariant,
                upstream=[{"object_type": "component", "object_id": invariant["component_id"]}],
                downstream=[{"object_type": "issue", "object_id": invariant["deep_link"]}],
            )
    if object_type in {"scanner_finding", "scanner-finding"}:
        for component in snapshot["pipeline"]["stations"]:
            if component["component_id"] != "scanner_security":
                continue
            for record in component.get("records", []):
                if not isinstance(record, dict):
                    continue
                record_id = str(
                    record.get("object_id")
                    or record.get("scanner_finding_id")
                    or record.get("finding_id")
                    or record.get("record_type")
                    or ""
                )
                if record_id != object_id:
                    continue
                diagnostics = {
                    "component_id": component["component_id"],
                    "component_health": component["health"],
                    "reason_codes": list(component.get("reason_codes", [])),
                    "data_quality": component.get("data_quality", {}),
                    "record": record,
                    "gate_effect": (
                        "blocks_writer_activation"
                        if int(component.get("blocked_count") or 0) > 0
                        else "no_current_block"
                    ),
                }
                return _microscope_payload(
                    object_type="scanner_finding",
                    object_id=record_id,
                    title=str(record.get("record_type") or record_id).replace("_", " ").title(),
                    summary=(
                        "Content-safe scanner/security gate signal derived from the "
                        "sidecar Observatory snapshot."
                    ),
                    diagnostics=diagnostics,
                    upstream=[
                        {
                            "object_type": "component",
                            "object_id": component["component_id"],
                            "relationship": "owning_gate",
                        },
                        *_upstream_edges(snapshot, component["component_id"]),
                    ],
                    downstream=[
                        *_downstream_edges(snapshot, component["component_id"]),
                        {
                            "object_type": "pipeline_invariant",
                            "object_id": "gates-cover-writer-activation",
                        },
                    ],
                )
    for reason_code, description in REASON_CODES.items():
        if object_type == "reason_code" and reason_code == object_id:
            supporting_components = [
                component
                for component in snapshot["pipeline"]["stations"]
                if reason_code in component.get("reason_codes", [])
            ]
            return _microscope_payload(
                object_type=object_type,
                object_id=object_id,
                title=reason_code,
                summary=description,
                diagnostics={
                    "reason_code": reason_code,
                    "description": description,
                    "supporting_component_ids": [
                        component["component_id"] for component in supporting_components
                    ],
                },
                upstream=[
                    {"object_type": "component", "object_id": component["component_id"]}
                    for component in supporting_components
                ],
                downstream=[
                    {"object_type": "issue", "object_id": issue["issue_id"]}
                    for issue in snapshot["issue_board"]
                    if reason_code in issue.get("reason_codes", [])
                ],
            )
    for subsystem in snapshot["subsystems"]:
        for playbook in subsystem.get("playbooks", []):
            if object_type == "playbook" and playbook["playbook_id"] == object_id:
                return playbook_detail(snapshot, str(object_id))
    for command in snapshot.get("command_palette", []):
        if object_type == "command" and command["command"] == object_id:
            return _microscope_payload(
                object_type=object_type,
                object_id=object_id,
                title=str(command["label"]),
                summary=str(command["target"]),
                diagnostics=command,
                upstream=[],
                downstream=[{"object_type": "route", "object_id": str(command["target"])}],
            )
    return _microscope_payload(
        object_type=object_type,
        object_id=object_id,
        title=f"{object_type}:{object_id}",
        summary="No bounded read model exists for this object yet.",
        diagnostics={
            "health": "unknown",
            "reason_codes": ["read-model-missing"],
            "supporting_component": "observatory_admin",
            "content_policy": {"raw_available": False, "redaction": "not_loaded"},
        },
        upstream=[],
        downstream=[],
    )


def storage_microscope(snapshot: dict[str, Any]) -> dict[str, Any]:
    component = _component_by_id(snapshot, "storage_db")
    observatory = _component_by_id(snapshot, "observatory_admin")
    audit = _component_by_id(snapshot, "audit_trace")
    relations = _storage_relations(component)
    total_table_bytes = sum(_int(row.get("table_bytes")) for row in relations)
    total_index_bytes = sum(_int(row.get("index_bytes")) for row in relations)
    total_bytes = sum(_int(row.get("total_bytes")) for row in relations)
    estimated_rows = sum(_int(row.get("estimated_rows")) for row in relations)
    largest_relations = sorted(
        relations,
        key=lambda row: (_int(row.get("total_bytes")), str(row.get("table_name") or "")),
        reverse=True,
    )[:10]
    data_quality = _dict(component.get("data_quality"))
    reason_codes = sorted(
        {
            *[str(code) for code in component.get("reason_codes", [])],
            *[
                str(code)
                for code in observatory.get("reason_codes", [])
                if str(code) in {"telemetry-stale", "missing-required-signal"}
            ],
        }
    )
    diagnostics = {
        "supporting_component": "storage_db",
        "health": component.get("health", "unknown"),
        "reason_codes": reason_codes,
        "data_quality": data_quality,
        "read_model": {
            "freshness_seconds": data_quality.get("read_model_age_seconds"),
            "coverage_state": data_quality.get("coverage_state"),
            "missing_signals": data_quality.get("missing_signals", []),
            "missing_signal_keys": data_quality.get("missing_signal_keys", []),
        },
        "migration_state": {
            "version_available": False,
            "state": "not_reported_by_operator_metrics",
            "reason": "static migrations are deterministic; runtime migration version telemetry is not yet persisted",
        },
        "relation_count": len(relations),
        "relation_totals": {
            "table_bytes": total_table_bytes,
            "index_bytes": total_index_bytes,
            "total_bytes": total_bytes,
            "estimated_rows": estimated_rows,
        },
        "index_health": {
            "index_bytes": total_index_bytes,
            "indexed_relation_count": sum(
                1 for row in relations if _int(row.get("index_bytes")) > 0
            ),
            "pgvector_status": "covered_by_storage_relation_metrics"
            if relations
            else "not_reported",
        },
        "retention": {
            "backlog_available": False,
            "state": "not_reported_by_operator_metrics",
        },
        "slow_queries": {
            "p50_latency_ms": component.get("p50_latency_ms"),
            "p95_latency_ms": component.get("p95_latency_ms"),
            "source": "component latency rollup",
        },
        "largest_relations": largest_relations,
        "content_policy": {
            "raw_available": False,
            "raw_reason": "raw-content-disabled",
            "relation_names_only": True,
            "connection_details_returned": False,
        },
    }
    return _microscope_payload(
        object_type="storage_db",
        object_id="storage_db",
        title="Postgres + pgvector storage",
        summary=(
            f"{component.get('health', 'unknown')} storage/read-model signal; "
            f"relations={len(relations)}; total_bytes={total_bytes}; "
            f"read_model_age_seconds={data_quality.get('read_model_age_seconds')}"
        ),
        diagnostics=diagnostics,
        upstream=[
            {"object_type": "subsystem", "object_id": "control_storage"},
            {"object_type": "component", "object_id": "scheduler_jobs"},
            {"object_type": "component", "object_id": "model_embedding"},
        ],
        downstream=[
            {"object_type": "component", "object_id": observatory["component_id"]},
            {"object_type": "component", "object_id": audit["component_id"]},
            {"object_type": "pipeline_invariant", "object_id": "read-models-fresh"},
            {"object_type": "admin_action", "object_id": "storage_health_check"},
            {"object_type": "admin_action", "object_id": "storage_retention_dry_run"},
        ],
    )


def playbook_detail(snapshot: dict[str, Any], playbook_id: str) -> dict[str, Any]:
    for subsystem in snapshot["subsystems"]:
        playbook = _playbook_by_id(subsystem, playbook_id)
        if playbook is None:
            continue
        station_ids = {str(station_id) for station_id in subsystem.get("station_ids", [])}
        components = [
            component
            for component in snapshot["pipeline"]["stations"]
            if str(component["component_id"]) in station_ids
        ]
        issues = [
            issue
            for issue in snapshot["issue_board"]
            if issue.get("subsystem_id") == subsystem.get("subsystem_id")
            or str(issue.get("component_id")) in station_ids
        ]
        missing_warnings = _playbook_missing_telemetry(components)
        safe_actions = _playbook_safe_actions(playbook, issues, components)
        affected_objects = _playbook_affected_objects(subsystem, components, issues)
        current_state = {
            **playbook,
            "subsystem_id": subsystem["subsystem_id"],
            "subsystem_health": subsystem["health"],
            "severity": _playbook_severity(str(subsystem["health"]), issues),
            "confidence": _playbook_confidence(components, missing_warnings),
            "reason_codes": sorted(
                {
                    code
                    for code in [
                        *subsystem.get("reason_codes", []),
                        *[
                            reason_code
                            for issue in issues
                            for reason_code in issue.get("reason_codes", [])
                        ],
                    ]
                }
            ),
            "first_checks": list(playbook.get("first_checks", [])),
            "typical_next_views": list(playbook.get("typical_next_views", [])),
            "missing_telemetry_warnings": missing_warnings,
            "affected_objects": affected_objects,
            "safe_next_diagnostic_actions": safe_actions,
            "blocked_policy_actions": _playbook_blocked_policy_actions(),
        }
        supporting_records = [
            *[
                {
                    "object_type": "issue",
                    "object_id": issue["issue_id"],
                    "severity": issue["severity"],
                    "reason_codes": list(issue.get("reason_codes", [])),
                    "summary": issue["summary"],
                }
                for issue in issues[:8]
            ],
            *[
                {
                    "object_type": "component",
                    "object_id": component["component_id"],
                    "health": component["health"],
                    "reason_codes": list(component.get("reason_codes", [])),
                    "data_quality": component.get("data_quality", {}),
                }
                for component in components
                if component.get("reason_codes")
            ][:8],
        ]
        return {
            "schema_version": "skillkernel.observatory.playbook.v1",
            "object_type": "playbook",
            "object_id": playbook_id,
            "title": str(playbook_id).replace("-", " ").title(),
            "summary": playbook["summary"],
            "current_signal_state": current_state,
            "supporting_records": supporting_records,
            "provenance": {
                "upstream": [
                    {"object_type": "subsystem", "object_id": subsystem["subsystem_id"]},
                    *[
                        {"object_type": "component", "object_id": component["component_id"]}
                        for component in components
                    ],
                ],
                "downstream": [
                    {"object_type": "issue", "object_id": issue["issue_id"]}
                    for issue in issues
                ],
            },
            "effects": safe_actions,
            "diagnostics": current_state,
            "timeline": [{"at": snapshot["captured_at"], "event": "playbook_snapshot_loaded"}],
            "audit": {"links": [], "chain_visible": True},
            "content_policy": {
                "raw_available": False,
                "raw_reason": "raw-content-disabled",
                "redaction_state": "redacted_or_not_applicable",
            },
        }
    return {
        "schema_version": "skillkernel.observatory.playbook.v1",
        "object_type": "playbook",
        "object_id": playbook_id,
        "title": playbook_id,
        "summary": "No playbook read model found.",
        "current_signal_state": {
            "health": "unknown",
            "reason_codes": ["read-model-missing"],
            "summary": "No bounded Observatory playbook exists for this id.",
        },
        "supporting_records": [],
        "provenance": {"upstream": [], "downstream": []},
        "effects": [],
        "diagnostics": {"reason_codes": ["read-model-missing"]},
        "timeline": [{"at": snapshot["captured_at"], "event": "playbook_missing"}],
        "audit": {"links": [], "chain_visible": True},
        "content_policy": {
            "raw_available": False,
            "raw_reason": "raw-content-disabled",
            "redaction_state": "redacted_or_not_applicable",
        },
    }


def action_receipt(
    *,
    action: str,
    role: str,
    idempotency_key: str,
    accepted: bool,
    reason_codes: list[str],
    linked_job: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
    action_audit: dict[str, Any] | None = None,
    action_attribution_check: dict[str, Any] | None = None,
    live_event: dict[str, Any] | None = None,
    raw_reveal_grant: dict[str, Any] | None = None,
    idempotency_replay: bool = False,
    idempotency_collision: bool = False,
) -> dict[str, Any]:
    return {
        "action": action,
        "accepted": accepted,
        "role": role,
        "idempotency_key": idempotency_key,
        "idempotency": {
            "replay": idempotency_replay,
            "collision": idempotency_collision,
        },
        "policy": {
            "allowed": accepted,
            "reason_codes": reason_codes,
            "confirmation_required": action
            in {
                "freeze_skill",
                "historical_import",
                "quarantine_candidate",
                "revoke_source",
                "rollback_skill",
                "unfreeze_skill",
                "rollback_transaction",
                "start_historical_import",
                "reveal_raw_content",
            },
        },
        "linked_job": linked_job,
        "audit": audit,
        "action_audit": action_audit,
        "action_attribution_check": action_attribution_check,
        "live_event": live_event,
        "raw_reveal_grant": raw_reveal_grant,
    }


def _component_snapshot(
    station: StationDefinition,
    *,
    settings: Settings,
    status: dict[str, Any],
    metrics: dict[str, Any],
    worker_health: dict[str, Any],
    audit_chain_valid: bool,
    static_available: bool,
    captured_at: datetime,
    read_model_age_seconds: int,
) -> dict[str, Any]:
    reason_codes: list[str] = []
    health = "healthy"
    mode = "active"
    input_rate = 0.0
    output_rate = 0.0
    queue_depth = 0
    blocked_count = 0
    warning_count = 0
    p50_latency = 0.0
    p95_latency = 0.0
    token_pressure = 0.0
    risk_pressure = 0.0
    evaluator_pressure = 0.0
    coverage = "complete"

    if not status.get("database_configured"):
        health = "unknown"
        coverage = "missing"
        reason_codes.append("database-not-configured")

    jobs = _dict(metrics.get("job_queue_depth"))
    failed_jobs = int(jobs.get("failed") or 0)
    queued_jobs = int(jobs.get("queued") or 0)
    leased_jobs = int(jobs.get("leased") or 0)
    job_backlog = queued_jobs + leased_jobs
    p50_latency, p95_latency = _component_latency_ms(station.metric_family, metrics)

    if station.metric_family == "ingest":
        ingest = _dict(metrics.get("ingest"))
        input_rate = float(ingest.get("event_rate_per_minute") or 0.0)
        output_rate = input_rate
        if status.get("database_configured") and int(ingest.get("total_events") or 0) == 0:
            health = _worse(health, "unknown")
            coverage = "partial"
            reason_codes.append("no-ingest-events-observed")
    elif station.metric_family == "redaction":
        redaction = _dict(metrics.get("redaction_counts"))
        output_rate = float(sum(int(value or 0) for value in redaction.values()))
    elif station.metric_family == "spool":
        health = _worse(health, "degraded")
        coverage = "partial"
        reason_codes.append("spool-diagnostics-required")
        warning_count += 1
    elif station.metric_family == "retrieval":
        decisions = _dict(metrics.get("retrieval_decisions"))
        retrieval_decision_count = sum(int(value or 0) for value in decisions.values())
        embedding_generation = _dict(metrics.get("embedding_generation"))
        embedding_generation_rate = float(
            embedding_generation.get("generated_per_minute") or 0.0
        )
        output_rate = (
            embedding_generation_rate
            if embedding_generation_rate > 0.0
            else float(retrieval_decision_count)
        )
        embedding_backlog = sum(
            int(value or 0) for value in _dict(metrics.get("embedding_backlog")).values()
        )
        queue_depth = embedding_backlog
        if embedding_backlog:
            health = _worse(health, "degraded")
            reason_codes.append("embedding-backlog-present")
    elif station.metric_family == "broker":
        output_rate = float(metrics.get("context_hint_injection_count") or 0)
        token_cost = int(metrics.get("context_hint_token_cost") or 0)
        token_pressure = min(1.0, token_cost / max(1, settings.max_context_hint_tokens * 10))
    elif station.metric_family == "context":
        token_cost = int(metrics.get("context_hint_token_cost") or 0)
        token_pressure = min(1.0, token_cost / max(1, settings.max_runtime_skill_tokens * 10))
    elif station.metric_family == "scanner":
        rejects = int(_dict(metrics.get("scanner_reject_counts")).get("skill_versions") or 0)
        risk_pressure = min(1.0, rejects / 10)
        blocked_count = rejects
        if rejects:
            health = _worse(health, "degraded")
            reason_codes.append("scanner-rejections-present")
    elif station.metric_family == "evaluator":
        evals = _dict(metrics.get("evaluation_pass_fail_counts"))
        failures = _evaluation_failure_count(evals)
        evaluator_pressure = min(1.0, failures / 10)
        blocked_count = failures
        if failures:
            health = _worse(health, "degraded")
            reason_codes.append("evaluation-failures-present")
    elif station.metric_family == "lifecycle":
        lifecycle = _dict(metrics.get("skill_lifecycle_counts"))
        frozen = int(lifecycle.get("frozen") or 0)
        output_rate = float(sum(int(value or 0) for value in lifecycle.values()))
        if frozen:
            health = _worse(health, "frozen")
            reason_codes.append("frozen-skills-present")
    elif station.metric_family == "rollback":
        rollback = _dict(metrics.get("rollback_freeze_counts"))
        frozen = int(rollback.get("frozen_skills") or 0)
        critical = int(rollback.get("critical_canary_skills") or 0)
        queue_depth = _nested_total(_dict(rollback.get("revocations")))
        if frozen:
            health = _worse(health, "frozen")
            reason_codes.append("frozen-skills-present")
        if critical:
            health = _worse(health, "blocked")
            reason_codes.append("critical-canary-present")
    elif station.metric_family == "jobs":
        queue_depth = job_backlog
        blocked_count = failed_jobs
        output_rate = float(int(jobs.get("succeeded") or 0))
        if failed_jobs:
            health = _worse(health, "blocked")
            reason_codes.append("failed-jobs-present")
        elif job_backlog:
            health = _worse(health, "degraded")
            reason_codes.append("queued-work-present")
    elif station.metric_family == "profiles":
        embedding_policy = embedding_provider_policy(settings)
        if embedding_policy.degraded:
            health = _worse(health, "degraded")
            reason_codes.append(embedding_policy.reason_code or "embedding-profile-degraded")
    elif station.metric_family == "storage":
        if not status.get("database_configured"):
            health = "blocked"
            reason_codes.append("database-not-configured")
        output_rate = float(len(metrics.get("postgres_table_index_growth") or []))
    elif station.metric_family == "audit":
        if not audit_chain_valid:
            health = _worse(health, "blocked")
            reason_codes.append("audit-chain-unverified")
        audit = _dict(metrics.get("audit"))
        output_rate = float(audit.get("audit_records") or 0)
    elif station.metric_family == "actions":
        if not settings.web_admin_token and not settings.control_token:
            health = _worse(health, "degraded")
            reason_codes.append("admin-token-not-configured")
    elif station.metric_family == "observatory":
        if not static_available:
            health = _worse(health, "degraded")
            reason_codes.append("frontend-serving-unavailable")
        if not settings.web_admin_token and not settings.control_token:
            health = _worse(health, "degraded")
            reason_codes.append("admin-token-not-configured")

    if read_model_age_seconds > settings.web_admin_telemetry_staleness_warning_seconds:
        reason_codes.append("telemetry-stale")
        coverage = "partial"
        health = _worse(
            health,
            "degraded"
            if read_model_age_seconds
            > settings.web_admin_telemetry_staleness_degraded_seconds
            else "unknown",
        )

    missing_metric_keys = _missing_metric_keys(station.metric_family, metrics, status)
    missing_signals = _missing_signal_classes(station.metric_family, missing_metric_keys, status)
    if missing_signals and health == "healthy":
        health = "unknown"
        coverage = "partial"
        reason_codes.append("missing-required-signal")
    elif missing_signals:
        coverage = "partial"
        reason_codes.append("missing-required-signal")

    return {
        "component_id": station.component_id,
        "display_name": station.display_name,
        "purpose": station.purpose,
        "health": health,
        "mode": mode,
        "freeze_state": "frozen" if health == "frozen" else "none",
        "last_success_at": captured_at.isoformat() if health in {"healthy", "degraded"} else None,
        "last_error_at": captured_at.isoformat() if health in {"blocked", "offline"} else None,
        "input_rate_1m": round(input_rate, 4),
        "output_rate_1m": round(output_rate, 4),
        "queue_depth": int(queue_depth),
        "backlog_seconds": int(queue_depth) * 30,
        "p50_latency_ms": round(p50_latency, 3),
        "p95_latency_ms": round(p95_latency, 3),
        "error_rate_15m": 1.0 if health in {"blocked", "offline"} else 0.0,
        "warning_count": int(warning_count + len(missing_signals)),
        "blocked_count": int(blocked_count),
        "token_pressure": round(token_pressure, 4),
        "risk_pressure": round(risk_pressure, 4),
        "evaluator_pressure": round(evaluator_pressure, 4),
        "details_url": f"/admin/components/{station.component_id}",
        "subsystem_ids": list(station.subsystem_ids),
        "object_kinds": list(station.object_kinds),
        "reason_codes": sorted(set(reason_codes)),
        "signal_contract": {
            "input": {
                "rate_1m": round(input_rate, 4),
                "backlog": int(queue_depth),
                "oldest_age_seconds": int(queue_depth) * 30,
            },
            "processing": {
                "rate_1m": round(output_rate, 4),
                "p50_ms": round(p50_latency, 3),
                "p95_ms": round(p95_latency, 3),
                "error_rate_1m": 1.0 if health in {"blocked", "offline"} else 0.0,
            },
            "output": {
                "rate_1m": round(output_rate, 4),
                "success_rate_1m": 0.0 if health in {"blocked", "offline"} else 1.0,
                "reject_rate_1m": 1.0 if blocked_count else 0.0,
            },
            "quality": {
                "data_completeness": 1.0 if coverage == "complete" else 0.4,
                "coverage": coverage,
                "freshness_seconds": read_model_age_seconds,
            },
            "control": {"mode": mode, "freeze_state": "frozen" if health == "frozen" else "none"},
            "evidence": {"trace_sample_ids": [], "issue_links": [], "audit_links": []},
        },
        "data_quality": {
            "component_id": station.component_id,
            "telemetry_freshness_seconds": read_model_age_seconds,
            "expected_input_rate_1m": 0.0,
            "observed_input_rate_1m": round(input_rate, 4),
            "output_conversion_rate_15m": 1.0
            if input_rate == 0
            else round(min(1.0, output_rate / input_rate), 4),
            "sampling_rate": 1.0,
            "redaction_level": "default",
            "raw_content_available": False,
            "read_model_age_seconds": read_model_age_seconds,
            "coverage_state": coverage,
            "missing_signals": missing_signals,
            "missing_signal_keys": missing_metric_keys,
        },
        "records": _station_records(
            station.metric_family, metrics=metrics, worker_health=worker_health
        ),
    }


def _edge_snapshot(
    edge: tuple[str, str, str],
    *,
    metrics: dict[str, Any],
    component_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    from_id, to_id, item_kind = edge
    source = component_by_id[from_id]
    target = component_by_id[to_id]
    event_rate = max(float(source["output_rate_1m"]), float(target["input_rate_1m"]))
    backlog = max(int(source["queue_depth"]), int(target["queue_depth"]))
    health = _worse(str(source["health"]), str(target["health"]))
    return {
        "edge_id": f"{from_id}_to_{to_id}",
        "from": from_id,
        "to": to_id,
        "event_rate_1m": round(event_rate, 4),
        "job_rate_1m": round(_job_rate(metrics), 4),
        "error_rate_15m": 1.0 if health in {"blocked", "offline"} else 0.0,
        "backpressure": round(min(1.0, backlog / 100), 4),
        "oldest_item_age_seconds": backlog * 30,
        "dominant_item_kind": item_kind,
        "health": health,
    }


def _subsystem_snapshot(
    subsystem: dict[str, Any],
    *,
    component_by_id: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    station_ids = list(subsystem["station_ids"])
    components = [component_by_id[station_id] for station_id in station_ids]
    subsystem_edges = [
        edge for edge in edges if edge["from"] in station_ids or edge["to"] in station_ids
    ]
    health = _rollup_health([str(component["health"]) for component in components])
    issue_refs = [
        issue["issue_id"]
        for issue in issues
        if issue.get("component_id") in station_ids
        or issue.get("subsystem_id") == subsystem["subsystem_id"]
    ]
    return {
        "subsystem_id": subsystem["subsystem_id"],
        "display_name": subsystem["display_name"],
        "health": health,
        "station_ids": station_ids,
        "station_health": {
            component["component_id"]: component["health"] for component in components
        },
        "diagnostic_questions": list(subsystem["diagnostic_questions"]),
        "throughput_1m": round(
            sum(float(component["output_rate_1m"]) for component in components), 4
        ),
        "queue_depth": sum(int(component["queue_depth"]) for component in components),
        "oldest_item_age_seconds": max(
            [int(edge["oldest_item_age_seconds"]) for edge in subsystem_edges] or [0]
        ),
        "conversion_rate": _subsystem_conversion_rate(components),
        "reason_codes": sorted(
            {code for component in components for code in component.get("reason_codes", [])}
        ),
        "issue_ids": issue_refs,
        "edges": subsystem_edges,
        "playbooks": _playbooks_for_subsystem(str(subsystem["subsystem_id"])),
        "details_url": f"/admin/subsystems/{subsystem['subsystem_id']}",
    }


def _issue_board(
    *,
    settings: Settings,
    status: dict[str, Any],
    metrics: dict[str, Any],
    components: list[dict[str, Any]],
    audit_chain_valid: bool,
    static_available: bool,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not status.get("database_configured"):
        issues.append(_issue("database-not-configured", "critical", "storage_db"))
    if not settings.web_admin_token and not settings.control_token:
        issues.append(_issue("admin-token-not-configured", "high", "operator_action_gateway"))
    if not status.get("control_auth_configured"):
        issues.append(_issue("control-token-not-configured", "high", "operator_action_gateway"))
    if not status.get("ingest_auth_configured"):
        issues.append(_issue("ingest-token-not-configured", "medium", "spool_ingest"))
    jobs = _dict(metrics.get("job_queue_depth"))
    if int(jobs.get("failed") or 0):
        issues.append(_issue("failed-jobs-present", "critical", "scheduler_jobs"))
    if int(jobs.get("queued") or 0) + int(jobs.get("leased") or 0):
        issues.append(_issue("queued-work-present", "medium", "scheduler_jobs"))
    if _nested_total(_dict(metrics.get("embedding_backlog"))):
        issues.append(_issue("embedding-backlog-present", "medium", "retrieval_indexing"))
    if int(_dict(metrics.get("scanner_reject_counts")).get("skill_versions") or 0):
        issues.append(_issue("scanner-rejections-present", "high", "scanner_security"))
    eval_failures = _evaluation_failure_count(
        _dict(metrics.get("evaluation_pass_fail_counts"))
    )
    if eval_failures:
        issues.append(_issue("evaluation-failures-present", "high", "evaluator_probes"))
    rollback = _dict(metrics.get("rollback_freeze_counts"))
    if int(rollback.get("frozen_skills") or 0):
        issues.append(_issue("frozen-skills-present", "high", "activation_curation"))
    if int(rollback.get("critical_canary_skills") or 0):
        issues.append(_issue("critical-canary-present", "critical", "canary_rollback"))
    drift = _dict(metrics.get("drift_violation_counts"))
    if int(drift.get("violated_contracts") or 0):
        issues.append(_issue("drift-violations-present", "high", "model_embedding"))
    if not audit_chain_valid:
        issues.append(_issue("audit-chain-unverified", "critical", "audit_trace"))
    if not static_available:
        issues.append(_issue("frontend-serving-unavailable", "medium", "observatory_admin"))
    for component in components:
        if "missing-required-signal" in component.get("reason_codes", []):
            issues.append(_missing_required_signal_issue(component))
        if component["health"] == "unknown" and component.get("reason_codes"):
            code = str(component["reason_codes"][0])
            issues.append(_issue(code, "low", str(component["component_id"])))
        if "telemetry-stale" in component.get("reason_codes", []):
            issues.append(_issue("telemetry-stale", "high", str(component["component_id"])))
    return _dedupe_issues(issues)


def _issue(
    reason_code: str,
    severity: str,
    component_id: str,
    *,
    title: str | None = None,
    summary: str | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    safe_next_actions: list[dict[str, str]] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    description = REASON_CODES.get(reason_code, "The Observatory detected a diagnostic condition.")
    issue = {
        "issue_id": f"{component_id}:{reason_code}",
        "severity": severity,
        "component_id": component_id,
        "subsystem_id": _primary_subsystem(component_id),
        "title": title or reason_code.replace("-", " ").title(),
        "summary": summary or description,
        "reason_codes": [reason_code],
        "evidence_refs": evidence_refs
        or [{"object_type": "component", "object_id": component_id}],
        "safe_next_actions": safe_next_actions or _safe_next_actions(reason_code),
        "deep_link": f"/admin/components/{component_id}?issue={reason_code}",
    }
    if diagnostics is not None:
        issue["diagnostics"] = diagnostics
    return issue


def _missing_required_signal_issue(component: dict[str, Any]) -> dict[str, Any]:
    missing_signals = list(component.get("data_quality", {}).get("missing_signals", []))
    missing_metric_keys = list(
        component.get("data_quality", {}).get("missing_signal_keys", [])
    )
    component_id = str(component["component_id"])
    display_name = str(component.get("display_name") or component_id)
    metric_summary = ", ".join(missing_metric_keys) if missing_metric_keys else "unknown metrics"
    signal_summary = ", ".join(missing_signals) if missing_signals else "unknown signal classes"
    evidence_refs: list[dict[str, Any]] = [
        {
            "object_type": "component",
            "object_id": component_id,
            "relationship": "affected_component",
        },
        *[
            {
                "object_type": "required_signal_metric",
                "object_id": metric_key,
                "relationship": "missing_metric_key",
                "component_id": component_id,
            }
            for metric_key in missing_metric_keys
        ],
    ]
    return _issue(
        "missing-required-signal",
        "low",
        component_id,
        title=f"{display_name} Missing Required Signal",
        summary=(
            f"{display_name} is missing required {signal_summary} telemetry "
            f"from metric key(s): {metric_summary}."
        ),
        evidence_refs=evidence_refs,
        diagnostics={
            "component_id": component_id,
            "component_display_name": display_name,
            "missing_signals": missing_signals,
            "missing_metric_keys": missing_metric_keys,
            "coverage_state": component.get("data_quality", {}).get("coverage_state"),
            "telemetry_freshness_seconds": component.get("data_quality", {}).get(
                "telemetry_freshness_seconds"
            ),
        },
        safe_next_actions=[
            {
                "action": "inspect_required_signal_contract",
                "summary": (
                    "Open the component cockpit and check the listed metric keys "
                    "against the required signal contract."
                ),
            }
        ],
    )


def _pipeline_invariants(
    *, metrics: dict[str, Any], components: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    component_by_id = {component["component_id"]: component for component in components}
    return [
        _invariant(
            "captured-events-accounted-for",
            component_by_id["openclaw_live_capture"],
            "Captured events eventually reach ingest, quarantine, or explicit drop records.",
        ),
        _invariant(
            "historical-sources-terminal-state",
            component_by_id["historical_ingestion"],
            (
                "Historical source items eventually reach parsed, skipped, quarantined, "
                "or revoked state."
            ),
        ),
        _invariant(
            "evidence-preserves-provenance",
            component_by_id["evidence_memory"],
            "Evidence clusters feeding candidates preserve provenance to source records.",
        ),
        _invariant(
            "candidate-decisions-explicit",
            component_by_id["opportunity_mining"],
            "Candidate decisions have explicit accept, reject, quarantine, or watch reasons.",
        ),
        _invariant(
            "llm-proposals-structured",
            component_by_id["model_embedding"],
            "LLM-backed proposals have structured-output validation records.",
        ),
        _invariant(
            "context-compiler-covered",
            component_by_id["context_compiler"],
            "Context compiler outputs have token counts and semantic-equivalence results.",
        ),
        _invariant(
            "gates-cover-writer-activation",
            component_by_id["scanner_security"],
            "Scanner and evaluator gates have complete coverage before writer activation.",
        ),
        _invariant(
            "writer-transactions-audited",
            component_by_id["deterministic_writer"],
            "Writer transactions have rollback metadata and audit links.",
        ),
        _invariant(
            "activated-versions-runtime-visible",
            component_by_id["activation_curation"],
            "Activated versions have broker and canary visibility.",
        ),
        _invariant(
            "rollback-revokes-derived-data",
            component_by_id["canary_rollback"],
            "Rollback and revocation traverse derived memories, embeddings, artifacts, and caches.",
        ),
        _invariant(
            "read-models-fresh",
            component_by_id["observatory_admin"],
            "Dashboard read models are fresher than their configured staleness budget.",
        ),
        _invariant(
            "audit-chain-verifiable",
            component_by_id["audit_trace"],
            "Operator and autonomous actions are connected to the trace spine and audit chain.",
        ),
    ]


def _invariant(invariant_id: str, component: dict[str, Any], description: str) -> dict[str, Any]:
    passed = component["health"] not in {"blocked", "offline", "unknown"}
    return {
        "invariant_id": invariant_id,
        "description": description,
        "status": "passed" if passed else "attention",
        "component_id": component["component_id"],
        "reason_codes": component.get("reason_codes", []),
        "deep_link": f"/admin/components/{component['component_id']}",
    }


def _kpis(
    *, metrics: dict[str, Any], status: dict[str, Any], components: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ingest = _dict(metrics.get("ingest"))
    jobs = _dict(metrics.get("job_queue_depth"))
    rollback = _dict(metrics.get("rollback_freeze_counts"))
    return [
        {
            "label": "Global health",
            "value": _rollup_health([str(component["health"]) for component in components]),
            "unit": "state",
        },
        {
            "label": "Events/min",
            "value": round(float(ingest.get("event_rate_per_minute") or 0.0), 4),
            "unit": "events",
        },
        {"label": "Queued jobs", "value": int(jobs.get("queued") or 0), "unit": "jobs"},
        {"label": "Failed jobs", "value": int(jobs.get("failed") or 0), "unit": "jobs"},
        {
            "label": "Active skills",
            "value": int(metrics.get("active_skill_count") or 0),
            "unit": "skills",
        },
        {
            "label": "Frozen skills",
            "value": int(rollback.get("frozen_skills") or 0),
            "unit": "skills",
        },
        {
            "label": "Context tokens",
            "value": int(metrics.get("context_hint_token_cost") or 0),
            "unit": "tokens",
        },
        {
            "label": "Database",
            "value": "configured" if status.get("database_configured") else "missing",
            "unit": "state",
        },
    ]


def _system_fitness(
    *,
    components: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    healthy = sum(1 for component in components if component["health"] == "healthy")
    total = max(1, len(components))
    critical = sum(1 for issue in issues if issue["severity"] == "critical")
    high = sum(1 for issue in issues if issue["severity"] == "high")
    score = max(0, round(((healthy / total) * 100) - (critical * 18) - (high * 8)))
    return {
        "score": score,
        "component_health_counts": _count_values(
            [str(component["health"]) for component in components]
        ),
        "issue_counts": _count_values([str(issue["severity"]) for issue in issues]),
        "plain_language_summary": _fitness_summary(score, critical=critical, high=high),
    }


def _global_data_quality(
    *,
    settings: Settings,
    metrics: dict[str, Any],
    static_available: bool,
    read_model_age_seconds: int,
) -> dict[str, Any]:
    missing = []
    if not settings.database_url:
        missing.append("database_read_models")
    if not static_available:
        missing.append("frontend_serving")
    stale = read_model_age_seconds > settings.web_admin_telemetry_staleness_warning_seconds
    return {
        "telemetry_freshness_seconds": read_model_age_seconds,
        "read_model_age_seconds": read_model_age_seconds,
        "coverage_state": "partial" if missing or stale else "complete",
        "missing_signals": missing,
        "raw_content_available": False,
        "raw_content_reason": "raw-content-disabled",
        "sampling_rate": 1.0,
        "stale": stale,
    }


def _read_model_age_seconds(
    operator_metrics: dict[str, Any],
    captured_at: datetime,
) -> int:
    metrics_captured_at = operator_metrics.get("captured_at")
    if not isinstance(metrics_captured_at, str) or not metrics_captured_at:
        return 0
    try:
        parsed = datetime.fromisoformat(metrics_captured_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, int((captured_at - parsed.astimezone(UTC)).total_seconds()))


def _station_records(
    metric_family: str, *, metrics: dict[str, Any], worker_health: dict[str, Any]
) -> list[dict[str, Any]]:
    if metric_family == "jobs":
        return [
            {"record_type": "job_counts", "summary": metrics.get("job_queue_depth", {})},
            {"record_type": "worker_health", "summary": worker_health},
        ]
    if metric_family == "storage":
        return [
            {"record_type": "storage_relation", "summary": row}
            for row in (metrics.get("postgres_table_index_growth") or [])[:20]
            if isinstance(row, dict)
        ]
    if metric_family == "audit":
        return [{"record_type": "audit", "summary": metrics.get("audit", {})}]
    if metric_family == "retrieval":
        return [
            {
                "record_type": "retrieval_decisions",
                "summary": metrics.get("retrieval_decisions", {}),
            },
            {
                "record_type": "embedding_generation",
                "summary": metrics.get("embedding_generation", {}),
            },
            {"record_type": "embedding_backlog", "summary": metrics.get("embedding_backlog", {})},
        ]
    if metric_family == "context":
        return [
            {
                "record_type": "context_budget",
                "summary": {
                    "hint_token_cost": metrics.get("context_hint_token_cost", 0),
                    "ledger_count": metrics.get("context_hint_token_ledger_count", 0),
                },
            }
        ]
    if metric_family == "vault":
        return [
            {
                "record_type": "raw_vault_summary",
                "summary": metrics.get("raw_vault_summary", {}),
            }
        ]
    if metric_family == "fidelity":
        return [
            {
                "record_type": "evidence_fidelity_status",
                "summary": metrics.get("evidence_fidelity_status", {}),
            }
        ]
    if metric_family == "adjudication":
        return [
            {
                "record_type": "semantic_adjudication_status",
                "summary": metrics.get("semantic_adjudication_status", {}),
            }
        ]
    if metric_family == "autonomy":
        return [
            {
                "record_type": "autonomy_decision_status",
                "summary": metrics.get("autonomy_decision_status", {}),
            }
        ]
    if metric_family == "replay":
        return [
            {
                "record_type": "broker_replay_episode_status",
                "summary": metrics.get("broker_replay_episode_status", {}),
            }
        ]
    if metric_family == "scanner":
        return [
            {
                "object_type": "scanner_finding",
                "object_id": "scanner_reject_counts",
                "record_type": "scanner_reject_counts",
                "component_id": "scanner_security",
                "summary": metrics.get("scanner_reject_counts", {}),
            }
        ]
    if metric_family == "escalation":
        return [
            {
                "record_type": "administrative_escalation_status",
                "summary": metrics.get("administrative_escalation_status", {}),
            }
        ]
    return [{"record_type": metric_family, "summary": metrics.get(metric_family, {})}]


def _search_facets() -> list[dict[str, Any]]:
    return [
        {"facet": "trace", "object_kinds": ["trace", "span_graph", "action_audit"]},
        {"facet": "jobs", "object_kinds": ["job", "schedule", "lease"]},
        {"facet": "skills", "object_kinds": ["skill_lifecycle", "skill_ir", "compiled_skill_md"]},
        {"facet": "topology", "object_kinds": ["topology_operation", "skill_graph_ir"]},
        {"facet": "issues", "object_kinds": ["issue", "reason_code"]},
        {"facet": "storage", "object_kinds": ["db_health_report", "index_status"]},
    ]


def _command_palette() -> list[dict[str, Any]]:
    return [
        {"command": "open-overview", "label": "Open overview", "target": "/admin"},
        {"command": "open-issue-board", "label": "Open issue board", "target": "/admin/issues"},
        {"command": "open-trace-replay", "label": "Open trace replay", "target": "/admin/traces"},
        {"command": "open-skill-library", "label": "Open skill library", "target": "/admin/skills"},
        {
            "command": "open-storage-health",
            "label": "Open storage health",
            "target": "/admin/components/storage_db",
        },
        {
            "command": "open-action-gateway",
            "label": "Open action gateway",
            "target": "/admin/components/operator_action_gateway",
        },
    ]


def _playbooks_for_subsystem(subsystem_id: str) -> list[dict[str, Any]]:
    playbooks = {
        "capture_bootstrap": [
            (
                "candidate-drought",
                "Check capture, parser loss, redaction pressure, and evidence yield.",
                (
                    "capture coverage",
                    "historical import yield",
                    "redaction loss",
                    "evidence maturity",
                ),
                (
                    "/admin/subsystems/capture_bootstrap",
                    "/admin/components/historical_ingestion",
                    "/admin/components/redaction_taint",
                    "/admin/components/evidence_memory",
                ),
            ),
            (
                "historical-bootstrap-validation",
                "Follow source discovery through chunks, quarantine, evidence, "
                "and seeded candidates.",
                (
                    "source discovery",
                    "parser failures",
                    "deduplication",
                    "redaction",
                    "evidence yield by source",
                ),
                (
                    "/admin/components/historical_ingestion",
                    "/admin/components/redaction_taint",
                    "/admin/components/evidence_memory",
                ),
            ),
        ],
        "learning_memory": [
            (
                "candidate-drought",
                "Check recurring evidence, duplicate suppression, and opportunity recommendations.",
                (
                    "recurring evidence",
                    "duplicate suppression",
                    "candidate rejection",
                    "opportunity recommendations",
                ),
                (
                    "/admin/components/evidence_memory",
                    "/admin/components/opportunity_mining",
                    "/admin/components/topology_operations",
                ),
            ),
            (
                "recall-quality",
                "Compare lexical/vector decisions and embedding backlog.",
                (
                    "retrieval recall audit",
                    "embedding backlog",
                    "lexical/vector disagreement",
                    "shadowing suppression",
                ),
                (
                    "/admin/components/retrieval_indexing",
                    "/admin/components/broker_runtime",
                    "/admin/broker/decisions",
                ),
            ),
        ],
        "runtime_context": [
            (
                "context-pressure",
                "Inspect broker decisions, compiled context tokens, false-positive loads, "
                "and canary feedback.",
                (
                    "false-positive loads",
                    "broad-skill shadowing",
                    "support-context loadability",
                    "ignored-skill waste",
                ),
                (
                    "/admin/subsystems/runtime_context",
                    "/admin/components/broker_runtime",
                    "/admin/components/context_compiler",
                    "/admin/components/topology_operations",
                ),
            ),
            (
                "broker-misses-relevant-skills",
                "Inspect recall audit, embedding backlog, no-skill decisions, "
                "and broker suppression.",
                (
                    "retrieval recall audit",
                    "embedding backlog",
                    "lexical/vector disagreement",
                    "shadowing suppression",
                    "no-skill decisions",
                ),
                (
                    "/admin/components/retrieval_indexing",
                    "/admin/components/broker_runtime",
                    "/admin/components/topology_operations",
                ),
            ),
        ],
        "topology_design": [
            (
                "skill-package-inspection",
                "Inspect SkillIR, topology operation, artifact plan, and gate evidence.",
                (
                    "candidate rejection",
                    "duplicate suppression",
                    "SkillIR effect coverage",
                    "planned trial state",
                ),
                (
                    "/admin/components/topology_operations",
                    "/admin/components/skill_ir_graph_ir",
                    "/admin/components/artifact_planner",
                ),
            ),
            (
                "skill-improvements-rejected",
                "Trace rejected improvements through scanner, evaluator, equivalence, "
                "and token gates.",
                (
                    "scanner findings",
                    "regression failures",
                    "semantic equivalence failures",
                    "token-budget failures",
                    "stale probes",
                ),
                (
                    "/admin/components/context_compiler",
                    "/admin/components/scanner_security",
                    "/admin/components/evaluator_probes",
                    "/admin/components/skill_ir_graph_ir",
                ),
            ),
        ],
        "quality_gates": [
            (
                "harm-regression",
                "Follow scanner findings, evaluator probes, canary failures, and rollback options.",
                (
                    "canary failures",
                    "user corrections",
                    "action attribution",
                    "broker load decisions",
                    "regression drift",
                ),
                (
                    "/admin/components/canary_rollback",
                    "/admin/components/evaluator_probes",
                    "/admin/components/broker_runtime",
                    "/admin/components/audit_trace",
                ),
            ),
            (
                "harm-after-activation",
                "Trace post-activation harm through canary, attribution, broker, "
                "and rollback evidence.",
                (
                    "canary failures",
                    "user corrections",
                    "action attribution",
                    "broker load decisions",
                    "regression drift",
                ),
                (
                    "/admin/components/canary_rollback",
                    "/admin/components/evaluator_probes",
                    "/admin/components/broker_runtime",
                    "/admin/components/audit_trace",
                ),
            ),
        ],
        "artifact_mutation": [
            (
                "mutation-safety",
                "Follow manifest, scanner/evaluator gates, writer transaction, "
                "and rollback pointer.",
                (
                    "manifest hash",
                    "scanner gate",
                    "evaluator gate",
                    "writer transaction",
                    "rollback pointer",
                ),
                (
                    "/admin/components/deterministic_writer",
                    "/admin/components/scanner_security",
                    "/admin/components/evaluator_probes",
                    "/admin/components/canary_rollback",
                ),
            ),
        ],
        "lifecycle_governance": [
            (
                "rollback-revocation",
                "Trace evolution transaction impact and derived-data revocation.",
                (
                    "evolution transaction",
                    "revocation graph",
                    "freeze state",
                    "derived-data invalidation",
                ),
                (
                    "/admin/components/canary_rollback",
                    "/admin/components/activation_curation",
                    "/admin/components/audit_trace",
                ),
            ),
        ],
        "control_storage": [
            (
                "infrastructure-health",
                "Check jobs, profiles, DB/read models, audit chain, and Observatory self-health.",
                (
                    "migration state",
                    "read-model freshness",
                    "dashboard query latency",
                    "retention backlog",
                    "audit chain",
                ),
                (
                    "/admin/components/storage_db",
                    "/admin/components/observatory_admin",
                    "/admin/components/audit_trace",
                ),
            ),
            (
                "read-model-staleness",
                "Trace stale database and dashboard read models through storage and self-health.",
                (
                    "migration state",
                    "materialized view refresh",
                    "slow dashboard queries",
                    "LISTEN/NOTIFY bridge",
                    "retention backlog",
                ),
                (
                    "/admin/components/storage_db",
                    "/admin/components/observatory_admin",
                    "/admin/components/audit_trace",
                ),
            ),
            (
                "llm-maintenance-stalled",
                "Inspect profile qualification, structured-output failures, retries, "
                "and paused LLM jobs.",
                (
                    "text profile qualification",
                    "structured output failures",
                    "timeout/retry pressure",
                    "paused LLM jobs",
                ),
                (
                    "/admin/components/model_embedding",
                    "/admin/components/scheduler_jobs",
                    "/admin/components/opportunity_mining",
                ),
            ),
        ],
    }
    return [
        {
            "playbook_id": playbook_id,
            "summary": summary,
            "first_checks": list(first_checks),
            "typical_next_views": list(typical_next_views),
        }
        for playbook_id, summary, first_checks, typical_next_views in playbooks.get(
            subsystem_id, []
        )
    ]


def _playbook_by_id(subsystem: dict[str, Any], playbook_id: str) -> dict[str, Any] | None:
    for playbook in subsystem.get("playbooks", []):
        if str(playbook["playbook_id"]) == playbook_id:
            return playbook
    return None


def _playbook_missing_telemetry(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for component in components:
        data_quality = _dict(component.get("data_quality"))
        missing_signals = list(data_quality.get("missing_signals") or [])
        missing_metric_keys = list(data_quality.get("missing_signal_keys") or [])
        if not missing_signals and not missing_metric_keys:
            continue
        warnings.append(
            {
                "component_id": component["component_id"],
                "component_display_name": component["display_name"],
                "missing_signals": missing_signals,
                "missing_metric_keys": missing_metric_keys,
                "coverage_state": data_quality.get("coverage_state"),
                "telemetry_freshness_seconds": data_quality.get(
                    "telemetry_freshness_seconds"
                ),
            }
        )
    return warnings


def _playbook_safe_actions(
    playbook: dict[str, Any],
    issues: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = [
        {
            "action": "inspect_playbook_first_check",
            "summary": str(first_check),
            "target": str(playbook.get("typical_next_views", ["/admin"])[0]),
        }
        for first_check in playbook.get("first_checks", [])
    ]
    for issue in issues:
        for action in issue.get("safe_next_actions", []):
            actions.append(
                {
                    "action": str(action.get("action", "inspect_issue")),
                    "summary": str(action.get("summary", issue["summary"])),
                    "target": str(issue.get("deep_link", "/admin/issues")),
                }
            )
    for component in components:
        actions.append(
            {
                "action": "open_component_cockpit",
                "summary": f"Open {component['display_name']} cockpit.",
                "target": str(component["details_url"]),
            }
        )
    return _dedupe_action_dicts(actions)[:12]


def _playbook_affected_objects(
    subsystem: dict[str, Any],
    components: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = [
        {
            "object_type": "subsystem",
            "object_id": subsystem["subsystem_id"],
            "health": subsystem["health"],
        }
    ]
    objects.extend(
        {
            "object_type": "component",
            "object_id": component["component_id"],
            "health": component["health"],
            "object_kinds": list(component.get("object_kinds", [])),
        }
        for component in components
    )
    objects.extend(
        {
            "object_type": "issue",
            "object_id": issue["issue_id"],
            "severity": issue["severity"],
            "reason_codes": list(issue.get("reason_codes", [])),
        }
        for issue in issues
    )
    return objects[:16]


def _playbook_severity(subsystem_health: str, issues: list[dict[str, Any]]) -> str:
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    if issues:
        return min(
            (str(issue["severity"]) for issue in issues),
            key=lambda severity: severity_order.get(severity, 9),
        )
    health_severity = {
        "blocked": "critical",
        "offline": "critical",
        "frozen": "high",
        "degraded": "medium",
        "unknown": "low",
    }
    return health_severity.get(subsystem_health, "none")


def _playbook_confidence(
    components: list[dict[str, Any]],
    missing_warnings: list[dict[str, Any]],
) -> float:
    if not components:
        return 0.0
    unknown_count = sum(1 for component in components if component.get("health") == "unknown")
    confidence = 1.0 - (0.12 * len(missing_warnings)) - (0.05 * unknown_count)
    return round(max(0.25, min(1.0, confidence)), 3)


def _playbook_blocked_policy_actions() -> list[dict[str, str]]:
    return [
        {
            "action": "execute_hidden_action",
            "blocked_by": "playbooks_are_read_only",
            "summary": "Playbooks link to views and guarded actions but never execute hidden work.",
        },
        {
            "action": "reveal_raw_content",
            "blocked_by": "raw-content-disabled",
            "summary": "Raw content remains unavailable from playbook read models.",
        },
        {
            "action": "activate_or_rewrite_runtime_skill",
            "blocked_by": "control-plane-immutability",
            "summary": (
                "Skill activation still requires deterministic writer, policy, "
                "and audit gates."
            ),
        },
    ]


def _dedupe_action_dicts(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for action in actions:
        key = (
            str(action.get("action", "")),
            str(action.get("summary", "")),
            str(action.get("target", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _safe_next_actions(reason_code: str) -> list[dict[str, str]]:
    actions = {
        "database-not-configured": (
            "configure_database",
            "Set SKILLKERNEL_DATABASE_URL/AUTOSKILL_DATABASE_URL and run migrations.",
        ),
        "admin-token-not-configured": (
            "configure_admin_token",
            "Set SKILLKERNEL_ADMIN_TOKEN or AUTOSKILL_WEB_ADMIN_TOKEN.",
        ),
        "control-token-not-configured": (
            "configure_control_token",
            "Set SKILLKERNEL_CONTROL_TOKEN or AUTOSKILL_CONTROL_TOKEN.",
        ),
        "ingest-token-not-configured": (
            "configure_ingest_token",
            "Set SKILLKERNEL_SIDECAR_TOKEN or AUTOSKILL_INGEST_TOKEN.",
        ),
        "read-model-missing": (
            "implement_read_model",
            "Add a bounded content-safe Observatory read model for this object class.",
        ),
        "no-ingest-events-observed": (
            "verify_live_capture",
            "Check plugin hook capture, sidecar ingest auth, and recent raw event rows.",
        ),
        "failed-jobs-present": (
            "inspect_failed_jobs",
            "Open scheduler/jobs cockpit and inspect failed job records.",
        ),
        "embedding-endpoint-not-configured": (
            "configure_embedding_endpoint",
            "Set AUTOSKILL_EMBEDDING_API_BASE_URL or use the deterministic hash provider.",
        ),
        "embedding-backlog-present": (
            "run_embedding_worker",
            "Run the maintenance worker or embeddings.generate job.",
        ),
        "scanner-rejections-present": (
            "inspect_scanner_findings",
            "Open scanner cockpit and review hard findings.",
        ),
        "evaluation-failures-present": (
            "inspect_evaluation_runs",
            "Open evaluator cockpit and inspect failed probes.",
        ),
        "frontend-serving-unavailable": (
            "verify_observatory_frontend",
            "Verify the Observatory web container or explicit sidecar local-development mode.",
        ),
    }
    action, summary = actions.get(
        reason_code,
        ("inspect_component", "Open the linked component cockpit and inspect reason codes."),
    )
    return [{"action": action, "summary": summary}]


def _missing_metric_keys(
    metric_family: str, metrics: dict[str, Any], status: dict[str, Any]
) -> list[str]:
    if not status.get("database_configured"):
        return list(REQUIRED_METRICS_BY_FAMILY.get(metric_family, ()))
    return [
        key
        for key in REQUIRED_METRICS_BY_FAMILY.get(metric_family, ())
        if not _metric_present(metrics, key)
    ]


def _missing_signal_classes(
    metric_family: str, missing_metric_keys: list[str], status: dict[str, Any]
) -> list[str]:
    if not status.get("database_configured"):
        return ["input", "processing", "output", "quality", "evidence"]
    if not missing_metric_keys:
        return []
    signal_map = {
        "ingest": "input",
        "historical": "input",
        "redaction": "quality",
        "spool": "evidence",
        "evidence": "evidence",
        "retrieval": "processing",
        "broker": "output",
        "topology": "processing",
        "skills": "output",
        "artifact": "output",
        "context": "quality",
        "scanner": "quality",
        "evaluator": "quality",
        "writer": "control",
        "lifecycle": "control",
        "rollback": "control",
        "jobs": "processing",
        "profiles": "quality",
        "storage": "processing",
        "audit": "evidence",
        "actions": "control",
        "observatory": "processing",
    }
    primary = signal_map.get(metric_family, "evidence")
    return sorted({primary, "evidence"})


def _metric_present(metrics: dict[str, Any], key: str) -> bool:
    if key not in metrics:
        return False
    return metrics[key] is not None


def _append_match(
    results: list[dict[str, Any]],
    *,
    needle: str,
    object_type: str,
    object_id: str,
    title: str,
    summary: str,
    url: str,
    reason_codes: list[str],
) -> None:
    haystack = f"{object_type} {object_id} {title} {summary} {' '.join(reason_codes)}".casefold()
    if needle and needle not in haystack:
        return
    results.append(
        {
            "object_type": object_type,
            "object_id": object_id,
            "title": title,
            "summary": summary,
            "url": url,
            "reason_codes": reason_codes,
        }
    )


def _microscope_payload(
    *,
    object_type: str,
    object_id: str,
    title: str,
    summary: str,
    diagnostics: dict[str, Any],
    upstream: list[dict[str, Any]],
    downstream: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": OBSERVATORY_SCHEMA_VERSION,
        "object_type": object_type,
        "object_id": object_id,
        "title": title,
        "summary": summary,
        "content_policy": {
            "raw_available": False,
            "raw_reason": "raw-content-disabled",
            "redaction_state": "redacted_or_not_applicable",
        },
        "timeline": [{"at": datetime.now(UTC).isoformat(), "event": "snapshot_loaded"}],
        "provenance": {"upstream": upstream, "downstream": downstream},
        "effects": downstream,
        "diagnostics": diagnostics,
        "audit": {"links": [], "chain_visible": True},
    }


def _upstream_edges(snapshot: dict[str, Any], component_id: str) -> list[dict[str, Any]]:
    return [
        {"object_type": "component", "object_id": edge["from"], "edge_id": edge["edge_id"]}
        for edge in snapshot["pipeline"]["edges"]
        if edge["to"] == component_id
    ]


def _downstream_edges(snapshot: dict[str, Any], component_id: str) -> list[dict[str, Any]]:
    return [
        {"object_type": "component", "object_id": edge["to"], "edge_id": edge["edge_id"]}
        for edge in snapshot["pipeline"]["edges"]
        if edge["from"] == component_id
    ]


def _component_by_id(snapshot: dict[str, Any], component_id: str) -> dict[str, Any]:
    return next(
        (
            component
            for component in snapshot["pipeline"]["stations"]
            if component["component_id"] == component_id
        ),
        {
            "component_id": component_id,
            "health": "unknown",
            "reason_codes": ["read-model-missing"],
            "data_quality": {},
            "records": [],
        },
    )


def _storage_relations(component: dict[str, Any]) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    for record in component.get("records", []):
        if not isinstance(record, dict) or record.get("record_type") != "storage_relation":
            continue
        summary = _dict(record.get("summary"))
        if not summary:
            continue
        relations.append(
            {
                "table_name": str(summary.get("table_name") or "unknown"),
                "table_bytes": _int(summary.get("table_bytes")),
                "index_bytes": _int(summary.get("index_bytes")),
                "total_bytes": _int(summary.get("total_bytes")),
                "estimated_rows": _int(summary.get("estimated_rows")),
            }
        )
    return relations


def _int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for issue in issues:
        key = str(issue["issue_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        deduped,
        key=lambda issue: (severity_order.get(str(issue["severity"]), 9), issue["issue_id"]),
    )


def _primary_subsystem(component_id: str) -> str | None:
    for station in STATIONS:
        if station.component_id == component_id:
            return station.subsystem_ids[0] if station.subsystem_ids else None
    return None


def _subsystem_conversion_rate(components: list[dict[str, Any]]) -> float:
    input_rate = sum(float(component["input_rate_1m"]) for component in components)
    output_rate = sum(float(component["output_rate_1m"]) for component in components)
    if input_rate <= 0:
        return 1.0 if output_rate <= 0 else 0.0
    return round(min(1.0, output_rate / input_rate), 4)


def _job_rate(metrics: dict[str, Any]) -> float:
    jobs = _dict(metrics.get("job_queue_depth"))
    total = sum(int(value or 0) for value in jobs.values())
    return float(total)


def _nested_total(value: dict[str, Any]) -> int:
    total = 0
    for item in value.values():
        if isinstance(item, dict):
            total += _nested_total(item)
        else:
            total += int(item or 0)
    return total


def _component_latency_ms(metric_family: str, metrics: dict[str, Any]) -> tuple[float, float]:
    if metric_family == "observatory":
        latency = _dict(metrics.get("sidecar_latency_ms"))
        return float(latency.get("avg") or 0.0), float(latency.get("p95") or 0.0)

    latency_by_kind = _dict(metrics.get("latency_by_operation_kind"))
    selected = [
        _dict(latency_by_kind.get(operation_kind))
        for operation_kind in LATENCY_OPERATION_KINDS_BY_FAMILY.get(metric_family, ())
        if isinstance(latency_by_kind.get(operation_kind), dict)
    ]
    if not selected:
        return 0.0, 0.0

    span_count = sum(int(item.get("span_count") or 0) for item in selected)
    if span_count:
        avg_latency = sum(
            float(item.get("avg") or 0.0) * int(item.get("span_count") or 0)
            for item in selected
        ) / span_count
    else:
        avg_latency = max(float(item.get("avg") or 0.0) for item in selected)
    p95_latency = max(float(item.get("p95") or 0.0) for item in selected)
    return avg_latency, p95_latency


def _evaluation_failure_count(counts: dict[str, Any]) -> int:
    return sum(
        int(value or 0)
        for status, value in counts.items()
        if status in EVALUATION_FAILURE_STATUSES
    )


def _rollup_health(healths: list[str]) -> str:
    if not healths:
        return "unknown"
    return max(healths, key=lambda health: HEALTH_ORDER.get(health, 99))


def _worse(left: str, right: str) -> str:
    return left if HEALTH_ORDER.get(left, 99) >= HEALTH_ORDER.get(right, 99) else right


def _count_values(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _fitness_summary(score: int, *, critical: int, high: int) -> str:
    if critical:
        return (
            "Critical Observatory conditions need operator attention before trusting "
            "autonomous flow."
        )
    if high:
        return "The system is observable but degraded; follow high-severity issue links first."
    if score >= 85:
        return "The pipeline is observable and currently within expected diagnostic bounds."
    return (
        "The pipeline is partially observable; inspect unknown and degraded components "
        "before assuming health."
    )


def _snapshot_seq(captured_at: datetime) -> int:
    return int(captured_at.timestamp() * 1000)


def _read_model_age_seconds(operator_metrics: dict[str, Any], captured_at: datetime) -> int:
    captured_value = operator_metrics.get("captured_at")
    if not isinstance(captured_value, str):
        return 0
    try:
        metric_time = datetime.fromisoformat(captured_value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if metric_time.tzinfo is None:
        metric_time = metric_time.replace(tzinfo=UTC)
    return max(0, int((captured_at - metric_time.astimezone(UTC)).total_seconds()))


def _normalized_base_path(value: str) -> str:
    stripped = value.strip() or "/admin"
    if not stripped.startswith("/"):
        stripped = f"/{stripped}"
    return stripped.rstrip("/") or "/admin"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
