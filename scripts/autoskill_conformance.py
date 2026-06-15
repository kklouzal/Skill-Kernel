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
REQUIRED_CONTAINER_ASSETS = (
    "Dockerfile.core",
    "Dockerfile.observatory",
    "containers/core/Dockerfile",
    "containers/core/entrypoint.sh",
    "containers/core/healthcheck.py",
    "containers/observatory/Dockerfile",
    "containers/observatory/entrypoint.sh",
    "containers/observatory/healthcheck.py",
    "compose/compose.example.yml",
    "compose/compose.local-llm.example.yml",
    "compose/env.core.example",
    "compose/env.observatory.example",
    "compose/env.postgres.example",
    "compose/README.md",
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
        _check_raw_vault_schema_contract(),
        _check_text_model_profile_schema_contract(),
        _check_autonomy_control_schema_contract(),
        _check_canonical_evidence_schema_contract(),
        _check_skillir_package_schema_contract(),
        _check_retrieval_attribution_audit_schema_contract(),
        _check_runtime_memory_control_schema_contract(),
        _check_topology_operation_schema_contract(),
        _check_historical_ingestion_schema_contract(),
        _check_no_unstable_react_keys(),
        _check_migration_deduplicated_and_ordered(),
        _check_architecture_invariants(spec_path),
        _check_inter_container_compatibility(),
        _check_container_packaging_assets(),
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


def _check_raw_vault_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    app = (ROOT / "sidecar" / "autoskill" / "api" / "app.py").read_text(encoding="utf-8")
    envelope = (ROOT / "plugin" / "autoskill" / "src" / "event-envelope.js").read_text(
        encoding="utf-8"
    )
    client = (ROOT / "plugin" / "autoskill" / "src" / "client" / "index.js").read_text(
        encoding="utf-8"
    )
    details: list[str] = []
    required_tables = (
        "CREATE TABLE IF NOT EXISTS autoskill.raw_evidence_records",
        "CREATE TABLE IF NOT EXISTS autoskill.raw_evidence_access_log",
        "CREATE TABLE IF NOT EXISTS autoskill.declassification_reports",
    )
    for table in required_tables:
        if table not in migration:
            details.append(f"migration missing {table}")
    for required in (
        "raw_events_raw_evidence_record_fk",
        "FOREIGN KEY (raw_evidence_record_id)",
        '"/v1/ingest/raw-evidence"',
        '"raw_vault_policy_version": "skillkernel.raw-vault-policy.v1"',
        '"redaction_policy_version": "skillkernel.redaction-policy.v1"',
    ):
        if required not in migration + app:
            details.append(f"raw-vault contract missing {required}")
    if "captureRawConversation: false" not in envelope:
        details.append("plugin event envelope does not force normal payload redaction")
    if "storeRawEvidenceRecord" not in client:
        details.append("plugin client cannot store raw-vault records separately")
    return _result(
        "SKX-STATIC-006B",
        "raw-vault persistence, handshake, and redacted event contract are present",
        (
            "migrations/0001_autoskill_schema.sql raw-vault tables",
            "sidecar/autoskill/api/app.py raw-vault capability and ingest route",
            "plugin/autoskill/src event envelope/client",
        ),
        details,
    )


def _check_text_model_profile_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.text_model_profiles",
        "text_model_profile_id uuid PRIMARY KEY",
        "route_type text NOT NULL CHECK (route_type IN ('openclaw','openai_compatible'))",
        "endpoint_kind text NOT NULL DEFAULT 'chat_completions'",
        "max_input_tokens integer NOT NULL DEFAULT 80000",
        "sync_text_model_profile_from_model_profile",
        "model_profiles_sync_text_model_profiles",
        "llm_invocations_text_model_profile_fk",
        "model_profile_qualification_runs_text_model_profile_fk",
        "sync_llm_invocation_text_model_profile_id",
        "sync_model_profile_qualification_text_model_profile_id",
    ):
        if required not in migration:
            details.append(f"text model control-plane bridge missing {required}")
    return _result(
        "SKX-STATIC-006J",
        "canonical text_model_profiles table mirrors the active text model profile write path",
        (
            "migrations/0001_autoskill_schema.sql text_model_profiles",
            "model_profiles, llm_invocations, and qualification sync triggers",
        ),
        details,
    )


def _check_autonomy_control_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    required_tables = (
        "autonomous_adjudications",
        "autonomy_policy_versions",
        "autonomy_calibration_observations",
        "autonomy_reliability_metrics",
        "autonomy_policy_trials",
        "autonomy_decisions",
        "administrative_escalation_events",
        "threshold_deadlock_findings",
        "intent_interpretations",
    )
    details = [
        f"migration missing autoskill.{table}"
        for table in required_tables
        if f"CREATE TABLE IF NOT EXISTS autoskill.{table}" not in migration
    ]
    required_contract_terms = (
        "input_raw_evidence_ids",
        "deterministic_checks",
        "confidence_decomposition",
        "decision_band",
        "attempted_autonomous_alternatives",
        "recommended_action",
        "redacted_user_intent",
        "calibration_support",
    )
    for term in required_contract_terms:
        if term not in migration:
            details.append(f"autonomy control-plane contract missing {term}")
    return _result(
        "SKX-STATIC-006C",
        "autonomy adjudication, calibration, decision, escalation, deadlock, and intent tables are present",
        (
            "migrations/0001_autoskill_schema.sql autonomy control-plane tables",
            "Part I section 9.3 semantic autonomy schema",
        ),
        details,
    )


def _check_canonical_evidence_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.evidence",
        "source_event_ids uuid[] NOT NULL",
        "evidence_type text NOT NULL",
        "confidence numeric NOT NULL",
        "CREATE OR REPLACE FUNCTION autoskill.sync_evidence_from_items()",
        "CREATE TRIGGER evidence_items_sync_evidence",
        "FROM autoskill.evidence_items",
    ):
        if required not in migration:
            details.append(f"canonical evidence bridge missing {required}")
    return _result(
        "SKX-STATIC-006D",
        "canonical evidence table mirrors the existing evidence_items write path",
        (
            "migrations/0001_autoskill_schema.sql autoskill.evidence",
            "evidence_items sync trigger",
        ),
        details,
    )


def _check_skillir_package_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.skill_files",
        "CREATE TABLE IF NOT EXISTS autoskill.skill_ir_revisions",
        "CREATE TABLE IF NOT EXISTS autoskill.skill_components",
        "sync_skill_file_from_compiled",
        "sync_skill_file_from_support_artifact",
        "sync_skill_ir_revision_from_version",
        "sync_skill_component_from_version",
        "digest(NEW.skill_ir::text, 'sha256')",
        "component_type text NOT NULL",
        "file_role text NOT NULL",
    ):
        if required not in migration:
            details.append(f"SkillIR/package bridge missing {required}")
    return _result(
        "SKX-STATIC-006E",
        "canonical SkillIR revision, skill file, and skill component tables mirror live compiler outputs",
        (
            "migrations/0001_autoskill_schema.sql skill_ir_revisions",
            "compiled_files/support_artifacts/skill_versions sync triggers",
        ),
        details,
    )


def _check_retrieval_attribution_audit_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.retrieval_events",
        "CREATE TABLE IF NOT EXISTS autoskill.skill_attributions",
        "CREATE TABLE IF NOT EXISTS autoskill.audit_log",
        "sync_retrieval_event_from_log",
        "sync_skill_attribution_from_event",
        "sync_skill_attribution_from_action_check",
        "sync_audit_log_from_record",
        "CREATE TRIGGER retrieval_logs_sync_retrieval_events",
        "CREATE TRIGGER attribution_events_sync_skill_attributions",
        "CREATE TRIGGER action_attribution_checks_sync_skill_attributions",
        "CREATE TRIGGER audit_records_sync_audit_log",
        "query_hash text NOT NULL",
        "attribution_kind text NOT NULL",
        "prev_audit_hash text",
    ):
        if required not in migration:
            details.append(f"retrieval/attribution/audit bridge missing {required}")
    return _result(
        "SKX-STATIC-006F",
        "canonical retrieval, skill attribution, and audit tables mirror live telemetry/write paths",
        (
            "migrations/0001_autoskill_schema.sql retrieval_events",
            "retrieval_logs/attribution_events/action_attribution_checks/audit_records sync triggers",
        ),
        details,
    )


def _check_runtime_memory_control_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.runtime_guard_templates",
        "CREATE TABLE IF NOT EXISTS autoskill.memory_contracts",
        "CREATE TABLE IF NOT EXISTS autoskill.runtime_artifacts",
        "CREATE TABLE IF NOT EXISTS autoskill.integration_proposals",
        "CREATE TABLE IF NOT EXISTS autoskill.skill_state_records",
        "CREATE TABLE IF NOT EXISTS autoskill.skill_marginal_value_trials",
        "sync_default_memory_contracts_for_workspace",
        "sync_runtime_artifact_from_compiled_file",
        "sync_runtime_artifact_from_support_artifact",
        "sync_runtime_artifact_from_context_artifact",
        "sync_skill_state_record_from_skill",
        "sync_skill_marginal_value_trial_from_context_ledger",
        "workspaces_sync_default_memory_contracts",
        "compiled_files_sync_runtime_artifacts",
        "context_artifacts_sync_runtime_artifacts",
        "context_token_ledgers_sync_skill_marginal_value_trials",
        '"executable_logic_allowed":false',
        "external_content_policy",
    ):
        if required not in migration:
            details.append(f"runtime/memory/control schema missing {required}")
    return _result(
        "SKX-STATIC-006G",
        "canonical runtime guard, memory contract, artifact, proposal, state, and marginal-value tables are present",
        (
            "migrations/0001_autoskill_schema.sql runtime/memory/control tables",
            "compiled/support/context/skill/token-ledger sync triggers",
        ),
        details,
    )


def _check_topology_operation_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.topology_candidates",
        "CREATE TABLE IF NOT EXISTS autoskill.topology_operation_trials",
        "CREATE TABLE IF NOT EXISTS autoskill.topology_operation_results",
        "sync_topology_candidate_from_skill_graph_operation",
        "sync_topology_operation_trial_from_planned_trial",
        "skill_graph_operations_sync_topology_candidates",
        "planned_topology_trials_sync_topology_operation_trials",
        "source_skill_graph_operation_id uuid UNIQUE",
        "source_planned_topology_trial_id uuid UNIQUE",
        "legacy_trial_kind",
        "topology_candidates_kind_status_idx",
    ):
        if required not in migration:
            details.append(f"topology operation schema missing {required}")
    return _result(
        "SKX-STATIC-006H",
        "canonical topology candidate, trial, and result tables mirror live topology operations",
        (
            "migrations/0001_autoskill_schema.sql topology operation tables",
            "skill_graph_operations/planned_topology_trials sync triggers",
        ),
        details,
    )


def _check_historical_ingestion_schema_contract() -> StaticCheck:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")
    details: list[str] = []
    for required in (
        "CREATE TABLE IF NOT EXISTS autoskill.historical_sources",
        "CREATE TABLE IF NOT EXISTS autoskill.historical_source_items",
        "CREATE TABLE IF NOT EXISTS autoskill.historical_chunks",
        "CREATE TABLE IF NOT EXISTS autoskill.historical_import_checkpoints",
        "CREATE TABLE IF NOT EXISTS autoskill.historical_import_findings",
        "stable_historical_source_id",
        "map_historical_source_type",
        "historical_taint_jsonb_to_text_array",
        "sync_historical_source_from_import_source",
        "sync_historical_item_and_chunk_from_import_chunk",
        "sync_historical_checkpoint_from_import_run",
        "historical_import_sources_sync_historical_sources",
        "historical_import_chunks_sync_historical_items",
        "historical_import_runs_sync_checkpoints",
        "historical_chunks_text_idx",
        "historical_chunks_taint_idx",
    ):
        if required not in migration:
            details.append(f"historical ingestion schema missing {required}")
    return _result(
        "SKX-STATIC-006I",
        "canonical historical source, item, chunk, checkpoint, and finding tables mirror live import rows",
        (
            "migrations/0001_autoskill_schema.sql historical ingestion tables",
            "historical_import_sources/chunks/runs sync triggers",
        ),
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
    for route in (
        '"/v1/version"',
        '"/v1/capabilities"',
        '"/v1/read-model-contract"',
        '"/v1/health/ready"',
        '"/v1/config/effective"',
        '"/v1/profiles/compatibility"',
    ):
        if route not in app:
            details.append(f"missing compatibility/readiness route: {route}")
    for field in (
        "api_contract_version",
        "schema_migration_version",
        "read_model_contract_version",
        "minimum_supported_observatory_version",
        "maximum_tested_observatory_version",
    ):
        if field not in app:
            details.append(f"missing compatibility response field: {field}")
    if "/v1/profiles/compatibility" not in tests:
        details.append("compatibility profile route is not exercised by test_compatibility.py")
    if "/v1/read-model-contract" not in tests or "/v1/health/ready" not in tests:
        details.append("core compatibility handshake routes are not exercised by test_compatibility.py")
    return _result(
        "SKX-STATIC-010",
        "inter-container API compatibility/version endpoints present and exercised",
        ("health/config/compatibility API routes", "sidecar/autoskill/tests/test_compatibility.py"),
        details,
    )


def _check_container_packaging_assets() -> StaticCheck:
    details: list[str] = []
    for rel_path in REQUIRED_CONTAINER_ASSETS:
        path = ROOT / rel_path
        if not path.exists():
            details.append(f"missing container packaging asset: {rel_path}")
    core_dockerfiles = _read_files(ROOT / "Dockerfile.core", ROOT / "containers" / "core" / "Dockerfile")
    observatory_dockerfiles = _read_files(
        ROOT / "Dockerfile.observatory",
        ROOT / "containers" / "observatory" / "Dockerfile",
    )
    compose = _read_files(ROOT / "docker-compose.yml", ROOT / "compose" / "compose.example.yml")
    workflow = (ROOT / ".github" / "workflows" / "publish-ghcr.yml").read_text(encoding="utf-8")
    if "USER skillkernel" not in core_dockerfiles:
        details.append("core Dockerfiles do not switch to non-root skillkernel user")
    if "USER skillkernel" not in observatory_dockerfiles:
        details.append("Observatory Dockerfiles do not switch to non-root skillkernel user")
    if "autoskill.observatory_main:app" not in observatory_dockerfiles:
        details.append("Observatory Dockerfiles do not start the Observatory API app")
    if "default.conf.template" in observatory_dockerfiles or "nginx" in observatory_dockerfiles:
        details.append("Observatory Dockerfiles still reference nginx proxy packaging")
    if "HEALTHCHECK" not in core_dockerfiles or "HEALTHCHECK" not in observatory_dockerfiles:
        details.append("Dockerfiles do not declare health checks")
    if (
        "ARG SKILLKERNEL_BUILD_SHA=local" not in core_dockerfiles
        or "ARG SKILLKERNEL_BUILD_SHA=local" not in observatory_dockerfiles
        or "org.opencontainers.image.revision" not in core_dockerfiles
        or "org.opencontainers.image.revision" not in observatory_dockerfiles
    ):
        details.append("Dockerfiles do not expose deterministic OCI revision labels")
    if (
        "ARG SKILLKERNEL_IMAGE_SOURCE=local" not in core_dockerfiles
        or "ARG SKILLKERNEL_IMAGE_SOURCE=local" not in observatory_dockerfiles
        or "org.opencontainers.image.source" not in core_dockerfiles
        or "org.opencontainers.image.source" not in observatory_dockerfiles
    ):
        details.append("Dockerfiles do not expose deterministic OCI source labels")
    if "containers/core/Dockerfile" not in compose:
        details.append("compose files do not build the first-class Core Dockerfile")
    if "containers/observatory/Dockerfile" not in compose:
        details.append("compose files do not build the first-class Observatory Dockerfile")
    if "SKILLKERNEL_BUILD_SHA: ${SKILLKERNEL_BUILD_SHA:-local}" not in compose:
        details.append("compose files do not pass the revision build arg")
    if "SKILLKERNEL_IMAGE_SOURCE: ${SKILLKERNEL_IMAGE_SOURCE:-local}" not in compose:
        details.append("compose files do not pass the source build arg")
    if "SKILLKERNEL_BUILD_SHA=${{ github.sha }}" not in workflow:
        details.append("publish workflow does not pass the GitHub SHA build arg")
    if "SKILLKERNEL_IMAGE_SOURCE=https://github.com/${{ github.repository }}" not in workflow:
        details.append("publish workflow does not pass the GitHub source build arg")
    if "SKILLKERNEL_DATABASE_URL_FILE" not in compose:
        details.append("reference compose does not mount database URL as a Core secret file")
    if "SKILLKERNEL_SIDECAR_TOKEN_FILE" not in compose:
        details.append("reference compose does not mount plugin ingest token as a Core secret file")
    if "SKILLKERNEL_CONTROL_TOKEN_FILE" not in compose:
        details.append("reference compose does not mount control token as a Core secret file")
    if "SKILLKERNEL_ADMIN_TOKEN_FILE" not in compose:
        details.append("reference compose does not mount admin token as a Core secret file")
    reference_compose = (ROOT / "compose" / "compose.example.yml").read_text(encoding="utf-8")
    observatory_section = _read_between(reference_compose, "  observatory:", "\nnetworks:")
    if "depends_on:" in observatory_section:
        details.append("reference Observatory service has a startup dependency despite independence contract")
    if "SKILLKERNEL_CORE_UPSTREAM" in observatory_section:
        details.append("reference Observatory service still proxies admin API to Core")
    if "SKILLKERNEL_DATABASE_URL_FILE" not in observatory_section:
        details.append("reference Observatory service does not mount database URL secret")
    if "SKILLKERNEL_ADMIN_TOKEN_FILE" not in observatory_section:
        details.append("reference Observatory service does not mount admin token secret")
    core_entrypoint = (ROOT / "containers" / "core" / "entrypoint.sh").read_text(encoding="utf-8")
    for expected in (
        'load_secret_file "SKILLKERNEL_DATABASE_URL"',
        'load_secret_file "SKILLKERNEL_SIDECAR_TOKEN"',
        'load_secret_file "SKILLKERNEL_CONTROL_TOKEN"',
        'load_secret_file "SKILLKERNEL_ADMIN_TOKEN"',
    ):
        if expected not in core_entrypoint:
            details.append(f"core entrypoint missing secret-file expansion: {expected}")
    return _result(
        "SKX-STATIC-011",
        "first-class split-container packaging assets are present",
        ("containers/* Dockerfiles", "compose reference topology", "root Dockerfile aliases"),
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
        "SKX-STATIC-012",
        "all four topology operations present: create, improve, compose, decompose",
        ("topology API/service", "canonical migration"),
        details,
    )


def _check_evidence_modes_present() -> StaticCheck:
    corpus = _read_files(MIGRATION_PATH, ROOT / "sidecar" / "autoskill" / "api" / "app.py")
    details = [f"missing evidence mode: {mode}" for mode in EVIDENCE_MODES if mode not in corpus]
    return _result(
        "SKX-STATIC-013",
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
        "SKX-STATIC-014",
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
