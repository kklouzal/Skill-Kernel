import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from autoskill.core.enums import AutonomyMode
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Sidecar settings.

    Environment variables use the AUTOSKILL_ prefix. The defaults intentionally
    match the v9 handoff's local-first development posture.
    """

    model_config = SettingsConfigDict(env_prefix="AUTOSKILL_", env_file=".env", extra="ignore")

    mode: AutonomyMode = AutonomyMode.AUTONOMOUS_GUARDED
    host: str = "127.0.0.1"
    port: int = 8765
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SKILLKERNEL_DATABASE_URL", "AUTOSKILL_DATABASE_URL"),
    )
    schema_name: str = "autoskill"
    statement_timeout_ms: int = 30_000
    build_sha: str = Field(
        default="local",
        validation_alias=AliasChoices("SKILLKERNEL_BUILD_SHA", "AUTOSKILL_BUILD_SHA"),
    )
    image_source: str = Field(
        default="local",
        validation_alias=AliasChoices("SKILLKERNEL_IMAGE_SOURCE", "AUTOSKILL_IMAGE_SOURCE"),
    )
    ingest_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SKILLKERNEL_SIDECAR_TOKEN", "AUTOSKILL_INGEST_TOKEN"),
    )
    control_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SKILLKERNEL_CONTROL_TOKEN", "AUTOSKILL_CONTROL_TOKEN"),
    )
    active_root: Path = Path("skills/autoskill")
    archive_root: Path = Path(".autoskill/archive")
    staging_root: Path = Path(".autoskill/staging")
    runtime_context_broker_enabled: bool = False
    runtime_context_timeout_ms: int = 150
    max_context_hint_tokens: int = 800
    llm_api_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SKILLKERNEL_LOCAL_LLM_BASE_URL",
            "AUTOSKILL_LLM_API_BASE_URL",
        ),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SKILLKERNEL_LOCAL_LLM_API_KEY", "AUTOSKILL_LLM_API_KEY"),
    )
    llm_thinking: str = "high"
    llm_thinking_fallback_policy: str = "strict"
    llm_max_input_tokens: int = 80_000
    llm_max_output_tokens: int = 8_000
    llm_timeout_ms: int = 180_000
    embedding_provider: str = "hash"
    embedding_hash_provider_allowed: bool = False
    embedding_model: str = "autoskill-hash-embedding.v1"
    embedding_dim: int = 1536
    embedding_api_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SKILLKERNEL_EMBEDDING_BASE_URL",
            "AUTOSKILL_EMBEDDING_API_BASE_URL",
        ),
    )
    embedding_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "SKILLKERNEL_EMBEDDING_API_KEY",
            "AUTOSKILL_EMBEDDING_API_KEY",
        ),
    )
    embedding_timeout_seconds: float = 30.0
    embedding_batch_size: int = 128
    worker_scheduler_concurrency: int = 1
    worker_ingest_concurrency: int = 2
    worker_backfill_concurrency: int = 1
    worker_embedding_concurrency: int = 1
    worker_retrieval_concurrency: int = 1
    worker_analysis_concurrency: int = 2
    worker_llm_generation_concurrency: int = 1
    worker_scanner_concurrency: int = 1
    worker_evaluation_concurrency: int = 1
    worker_filesystem_concurrency: int = 1
    worker_maintenance_concurrency: int = 2
    worker_mutation_concurrency: int = 1
    scheduler_tick_seconds: int = 30
    scheduler_worker_count: int = 4
    max_llm_jobs_concurrent: int = 2
    max_active_skills: int = 80
    max_runtime_skill_tokens: int = 900
    target_runtime_skill_tokens: int = 350
    max_frontmatter_description_chars: int = 160
    max_support_excerpt_tokens: int = 120
    min_marginal_success_per_1k_tokens: float = 0.0
    max_false_positive_load_delta: float = 0.02
    max_shadowing_delta: float = 0.01
    max_new_skills_per_day: int = 8
    context_compiler_enabled: bool = True
    tokenizer_profile: str = "model-specific-or-estimated"
    reject_human_prose: bool = True
    require_semantic_equivalence: bool = True
    min_semantic_equivalence_score: float = 0.90
    allow_examples_in_runtime_text: bool = False
    allow_support_files: bool = True
    support_files_require_loadability_class: bool = True
    approved_support_dirs: list[str] = Field(
        default_factory=lambda: [
            "scripts",
            "references",
            "templates",
            "schemas",
            "data",
            "assets",
            "examples",
            "tests",
            "probes",
            "adjunct_requests",
        ]
    )
    keep_tests_outside_active_skill_root: bool = True
    allow_generated_hook_files: bool = False
    allow_generated_cron_files: bool = False
    allow_generated_service_files: bool = False
    mutable_skill_state_location: str = "postgres_or_workspace_dot_autoskill"
    min_recurrence_count: int = 3
    min_evidence_confidence: float = 0.72
    target_probe_min_pass_rate: float = 0.85
    regression_failure_hard_budget: int = 0
    adversarial_critical_budget: int = 0
    allow_support_scripts: bool = True
    allow_network_in_generated_skills: bool = False
    allow_shell_in_generated_skills: bool = False
    forbid_hidden_markdown: bool = True
    redact_before_store: bool = True
    redact_before_embed: bool = True
    unix_socket_path: str | None = None
    run_as_non_root: bool = True
    allow_public_bind: bool = False
    openclaw_home_env: str = "OPENCLAW_HOME"
    openclaw_state_dir_env: str = "OPENCLAW_STATE_DIR"
    openclaw_config_path_env: str = "OPENCLAW_CONFIG_PATH"
    openclaw_state_dir_default: str = "~/.openclaw"
    workspace_roots: list[str] = Field(default_factory=list)
    session_store_roots: list[str] = Field(default_factory=list)
    trajectory_roots: list[str] = Field(default_factory=list)
    transcript_corpus_roots: list[str] = Field(default_factory=list)
    host_container_path_map: list[dict[str, str]] = Field(default_factory=list)
    historical_import_enabled: bool = True
    historical_import_mode: str = "incremental"
    historical_import_dry_run_inventory_on_start: bool = True
    historical_import_agents: str = "all"
    historical_import_max_age_days: int | None = None
    historical_import_max_bytes_per_run: int = 536_870_912
    historical_import_max_sessions_per_run: int = 2000
    historical_import_max_files_per_run: int = 10_000
    historical_import_max_llm_candidates_per_batch: int = 50
    historical_import_low_priority: bool = True
    historical_import_raw_content_policy: str = "redact_before_store"
    historical_import_embed_policy: str = "redacted_only"
    historical_import_llm_policy: str = "redacted_high_signal_clusters_only"
    compaction_summary_confidence_multiplier: float = 0.65
    stale_source_confidence_multiplier: float = 0.50
    historical_candidate_initial_maturity_cap: str = "recurring"
    require_normal_gates_for_activation: bool = True
    plugin_capture_tool_events: bool = True
    plugin_capture_messages: bool = True
    plugin_capture_raw_conversation: bool = False
    plugin_local_spool_max_mb: int = 256
    plugin_sidecar_url: str = Field(
        default="http://127.0.0.1:8765",
        validation_alias=AliasChoices(
            "SKILLKERNEL_SIDECAR_URL",
            "AUTOSKILL_PLUGIN_SIDECAR_URL",
            "AUTOSKILL_SIDECAR_URL",
        ),
    )
    plugin_runtime_context_fail_soft: bool = True
    web_admin_enabled: bool = True
    web_admin_base_path: str = "/admin"
    web_admin_auth_mode: str = "bearer_token"
    web_admin_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SKILLKERNEL_ADMIN_TOKEN", "AUTOSKILL_WEB_ADMIN_TOKEN"),
    )
    web_admin_raw_content_enabled: bool = False
    web_admin_csrf_enabled: bool = True
    web_admin_issue_board_enabled: bool = True
    web_admin_subsystem_lenses_enabled: bool = True
    web_admin_playbooks_enabled: bool = True
    web_admin_telemetry_staleness_warning_seconds: int = 30
    web_admin_telemetry_staleness_degraded_seconds: int = 120
    web_admin_cors_allowed_origins: list[str] = Field(default_factory=list)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    if os.environ.get("AUTOSKILL_IGNORE_ENV_FILE"):
        return Settings(_env_file=None)
    return Settings()


def effective_skillkernel_config(settings: Settings | None = None) -> dict[str, Any]:
    """Return the section-29-style effective SkillKernel config without secrets."""

    resolved = settings or get_settings()
    return {
        "mode": resolved.mode.value,
        "workspace_id": os.environ.get("AUTOSKILL_WORKSPACE_ID", "auto"),
        "active_root": str(resolved.active_root),
        "archive_root": str(resolved.archive_root),
        "staging_root": str(resolved.staging_root),
        "deployment": {
            "sidecar_bind": f"{resolved.host}:{resolved.port}",
            "sidecar_auth": "token_env",
            "sidecar_token_env": "SKILLKERNEL_SIDECAR_TOKEN",
            "sidecar_token_compat_env": "AUTOSKILL_INGEST_TOKEN",
            "control_token_env": "SKILLKERNEL_CONTROL_TOKEN",
            "control_token_compat_env": "AUTOSKILL_CONTROL_TOKEN",
            "unix_socket_path": resolved.unix_socket_path,
            "run_as_non_root": resolved.run_as_non_root,
            "allow_public_bind": resolved.allow_public_bind,
        },
        "paths": {
            "openclaw_home_env": resolved.openclaw_home_env,
            "openclaw_state_dir_env": resolved.openclaw_state_dir_env,
            "openclaw_config_path_env": resolved.openclaw_config_path_env,
            "openclaw_state_dir_default": resolved.openclaw_state_dir_default,
            "workspace_roots": resolved.workspace_roots,
            "session_store_roots": resolved.session_store_roots,
            "trajectory_roots": resolved.trajectory_roots,
            "transcript_corpus_roots": resolved.transcript_corpus_roots,
            "host_container_path_map": resolved.host_container_path_map,
        },
        "historical_ingestion": {
            "enabled": resolved.historical_import_enabled,
            "mode": resolved.historical_import_mode,
            "dry_run_inventory_on_start": resolved.historical_import_dry_run_inventory_on_start,
            "agents": resolved.historical_import_agents,
            "max_age_days": resolved.historical_import_max_age_days,
            "max_bytes_per_run": resolved.historical_import_max_bytes_per_run,
            "max_sessions_per_run": resolved.historical_import_max_sessions_per_run,
            "max_files_per_run": resolved.historical_import_max_files_per_run,
            "max_llm_candidates_per_batch": (
                resolved.historical_import_max_llm_candidates_per_batch
            ),
            "low_priority": resolved.historical_import_low_priority,
            "import_sources": _historical_import_sources(),
            "deny_globs": _historical_deny_globs(),
            "raw_content_policy": resolved.historical_import_raw_content_policy,
            "embed_policy": resolved.historical_import_embed_policy,
            "llm_policy": resolved.historical_import_llm_policy,
            "compaction_summary_confidence_multiplier": (
                resolved.compaction_summary_confidence_multiplier
            ),
            "stale_source_confidence_multiplier": resolved.stale_source_confidence_multiplier,
            "historical_candidate_initial_maturity_cap": (
                resolved.historical_candidate_initial_maturity_cap
            ),
            "require_normal_gates_for_activation": resolved.require_normal_gates_for_activation,
        },
        "plugin": {
            "capture_raw_conversation": resolved.plugin_capture_raw_conversation,
            "capture_tool_events": resolved.plugin_capture_tool_events,
            "capture_messages": resolved.plugin_capture_messages,
            "local_spool_max_mb": resolved.plugin_local_spool_max_mb,
            "sidecar_url": resolved.plugin_sidecar_url,
            "sidecar_url_env": "SKILLKERNEL_SIDECAR_URL",
            "sidecar_url_compat_envs": [
                "AUTOSKILL_PLUGIN_SIDECAR_URL",
                "AUTOSKILL_SIDECAR_URL",
            ],
            "runtime_context_broker": {
                "enabled": resolved.runtime_context_broker_enabled,
                "timeout_ms": resolved.runtime_context_timeout_ms,
                "max_tokens": resolved.max_context_hint_tokens,
                "fail_soft": resolved.plugin_runtime_context_fail_soft,
            },
        },
        "database": {
            "dsn_env": "SKILLKERNEL_DATABASE_URL",
            "dsn_compat_env": "AUTOSKILL_DATABASE_URL",
            "schema": resolved.schema_name,
            "statement_timeout_ms": resolved.statement_timeout_ms,
            "configured": bool(resolved.database_url),
        },
        "llm": {
            "active_profile": "service_reasoner",
            "profiles": {
                "service_reasoner": {
                    "route_type": "openai_compatible",
                    "provider": "configured-sidecar-provider",
                    "model": "configured-text-model",
                    "base_url_env": "SKILLKERNEL_LOCAL_LLM_BASE_URL",
                    "api_key_env": "SKILLKERNEL_LOCAL_LLM_API_KEY",
                    "base_url_compat_env": "AUTOSKILL_LLM_API_BASE_URL",
                    "api_key_compat_env": "AUTOSKILL_LLM_API_KEY",
                    "endpoint_kind": "chat_completions",
                    "thinking": resolved.llm_thinking,
                    "thinking_fallback_policy": resolved.llm_thinking_fallback_policy,
                    "temperature": 0,
                    "max_input_tokens": resolved.llm_max_input_tokens,
                    "max_output_tokens": resolved.llm_max_output_tokens,
                    "timeout_ms": resolved.llm_timeout_ms,
                    "max_concurrent": resolved.max_llm_jobs_concurrent,
                    "hosted_allowed": True,
                    "local_only": False,
                    "configured": bool(resolved.llm_api_base_url),
                },
            },
        },
        "embeddings": {
            "active_profile": "default_embedding",
            "profiles": {
                "default_embedding": {
                    "route_type": resolved.embedding_provider,
                    "provider": resolved.embedding_provider,
                    "model": resolved.embedding_model,
                    "base_url_env": "SKILLKERNEL_EMBEDDING_BASE_URL",
                    "api_key_env": "SKILLKERNEL_EMBEDDING_API_KEY",
                    "base_url_compat_env": "AUTOSKILL_EMBEDDING_API_BASE_URL",
                    "api_key_compat_env": "AUTOSKILL_EMBEDDING_API_KEY",
                    "dimensions": resolved.embedding_dim,
                    "distance_metric": "cosine",
                    "batch_size": resolved.embedding_batch_size,
                    "timeout_seconds": resolved.embedding_timeout_seconds,
                    "production_ready": (
                        resolved.embedding_provider == "openai_compatible"
                        and bool(resolved.embedding_api_base_url)
                        and bool(resolved.embedding_api_key)
                    ),
                    "degraded": (
                        resolved.embedding_provider == "hash"
                        or resolved.embedding_provider == "openclaw"
                        or (
                            resolved.embedding_provider == "openai_compatible"
                            and not (
                                resolved.embedding_api_base_url
                                and resolved.embedding_api_key
                            )
                        )
                        or resolved.embedding_provider not in {"openclaw", "openai_compatible"}
                    ),
                    "degraded_reason": (
                        "hash_embedding_provider_test_mode"
                        if resolved.embedding_provider == "hash"
                        else (
                            "embedding_endpoint_not_configured"
                            if resolved.embedding_provider == "openai_compatible"
                            and not (
                                resolved.embedding_api_base_url
                                and resolved.embedding_api_key
                            )
                            else (
                                "openclaw_embedding_route_unavailable"
                                if resolved.embedding_provider == "openclaw"
                                else (
                                    f"unsupported_embedding_provider:{resolved.embedding_provider}"
                                    if resolved.embedding_provider
                                    not in {"hash", "openai_compatible"}
                                    else None
                                )
                            )
                        )
                    ),
                    "jobs_paused_when_degraded": True,
                    "hash_provider_allowed_for_test": resolved.embedding_hash_provider_allowed,
                    "hosted_allowed": resolved.embedding_provider not in {"hash", "openclaw"},
                    "local_only": resolved.embedding_provider in {"hash", "openclaw"},
                },
            },
        },
        "skill_budget": {
            "max_active_skills": resolved.max_active_skills,
            "max_runtime_skill_tokens": resolved.max_runtime_skill_tokens,
            "target_runtime_skill_tokens": resolved.target_runtime_skill_tokens,
            "max_frontmatter_description_chars": resolved.max_frontmatter_description_chars,
            "max_context_hint_tokens": resolved.max_context_hint_tokens,
            "max_support_excerpt_tokens": resolved.max_support_excerpt_tokens,
            "min_marginal_success_per_1k_tokens": (resolved.min_marginal_success_per_1k_tokens),
            "max_false_positive_load_delta": resolved.max_false_positive_load_delta,
            "max_shadowing_delta": resolved.max_shadowing_delta,
            "max_new_skills_per_day": resolved.max_new_skills_per_day,
        },
        "context_compiler": {
            "enabled": resolved.context_compiler_enabled,
            "tokenizer_profile": resolved.tokenizer_profile,
            "reject_human_prose": resolved.reject_human_prose,
            "require_semantic_equivalence": resolved.require_semantic_equivalence,
            "min_semantic_equivalence_score": resolved.min_semantic_equivalence_score,
            "allow_examples_in_runtime_text": resolved.allow_examples_in_runtime_text,
            "allow_support_files": resolved.allow_support_files,
            "support_files_require_loadability_class": (
                resolved.support_files_require_loadability_class
            ),
            "approved_support_dirs": resolved.approved_support_dirs,
            "keep_tests_outside_active_skill_root": resolved.keep_tests_outside_active_skill_root,
            "allow_generated_hook_files": resolved.allow_generated_hook_files,
            "allow_generated_cron_files": resolved.allow_generated_cron_files,
            "allow_generated_service_files": resolved.allow_generated_service_files,
            "mutable_skill_state_location": resolved.mutable_skill_state_location,
        },
        "gates": {
            "min_recurrence_count": resolved.min_recurrence_count,
            "min_evidence_confidence": resolved.min_evidence_confidence,
            "target_probe_min_pass_rate": resolved.target_probe_min_pass_rate,
            "regression_failure_hard_budget": resolved.regression_failure_hard_budget,
            "adversarial_critical_budget": resolved.adversarial_critical_budget,
        },
        "security": {
            "allow_support_scripts": resolved.allow_support_scripts,
            "allow_network_in_generated_skills": resolved.allow_network_in_generated_skills,
            "allow_shell_in_generated_skills": resolved.allow_shell_in_generated_skills,
            "forbid_hidden_markdown": resolved.forbid_hidden_markdown,
            "redact_before_store": resolved.redact_before_store,
            "redact_before_embed": resolved.redact_before_embed,
        },
        "scheduler": {
            "tick_seconds": resolved.scheduler_tick_seconds,
            "worker_count": resolved.scheduler_worker_count,
            "max_llm_jobs_concurrent": resolved.max_llm_jobs_concurrent,
            "worker_concurrency": {
                "scheduler": resolved.worker_scheduler_concurrency,
                "ingest": resolved.worker_ingest_concurrency,
                "backfill": resolved.worker_backfill_concurrency,
                "embedding": resolved.worker_embedding_concurrency,
                "retrieval": resolved.worker_retrieval_concurrency,
                "analysis": resolved.worker_analysis_concurrency,
                "llm_generation": resolved.worker_llm_generation_concurrency,
                "scanner": resolved.worker_scanner_concurrency,
                "evaluation": resolved.worker_evaluation_concurrency,
                "filesystem": resolved.worker_filesystem_concurrency,
                "maintenance": resolved.worker_maintenance_concurrency,
            },
            "worker_pool_aliases": {"mutation": "filesystem"},
            "legacy_worker_concurrency": {
                "mutation": resolved.worker_mutation_concurrency,
            },
        },
        "web_admin": {
            "enabled": resolved.web_admin_enabled,
            "base_path": resolved.web_admin_base_path,
            "auth": {
                "mode": resolved.web_admin_auth_mode,
                "token_env": "SKILLKERNEL_ADMIN_TOKEN",
                "token_compat_env": "AUTOSKILL_WEB_ADMIN_TOKEN",
                "dedicated_token_configured": bool(resolved.web_admin_token),
                "control_token_fallback_configured": bool(resolved.control_token),
            },
            "static_serving": "observatory_container",
            "raw_content": {"enabled": resolved.web_admin_raw_content_enabled},
            "diagnostics": {
                "issue_board_enabled": resolved.web_admin_issue_board_enabled,
                "subsystem_lenses_enabled": resolved.web_admin_subsystem_lenses_enabled,
                "playbooks_enabled": resolved.web_admin_playbooks_enabled,
                "telemetry_staleness_warning_seconds": (
                    resolved.web_admin_telemetry_staleness_warning_seconds
                ),
                "telemetry_staleness_degraded_seconds": (
                    resolved.web_admin_telemetry_staleness_degraded_seconds
                ),
            },
            "csrf": {"enabled": resolved.web_admin_csrf_enabled},
            "cors": {"allowed_origins": resolved.web_admin_cors_allowed_origins},
        },
    }


def _historical_import_sources() -> dict[str, Any]:
    return {
        "session_stores": True,
        "raw_transcripts": True,
        "sanitized_session_history": True,
        "trajectories": True,
        "compaction_summaries": True,
        "workspace_memory_files": True,
        "workspace_context_files": True,
        "background_tasks": True,
        "task_flows": True,
        "lobster_workflows": False,
        "plugin_session_extensions": True,
        "queued_turn_injections": True,
        "active_memory_transcripts": False,
        "diagnostics_exports": False,
        "channel_media_artifacts": False,
        "transcription_artifacts": True,
        "preprocessed_message_artifacts": True,
        "existing_skills": True,
        "qmd_exports": False,
        "memory_capability_public_artifacts": False,
        "memory_wiki_exports": False,
        "honcho_exports": False,
        "allowlisted_project_docs": [],
        "allowlisted_workflow_docs": [],
        "diagnostics_export_paths": [],
        "media_artifact_allowlist": {
            "enabled": False,
            "mime_types": [
                "text/plain",
                "text/markdown",
                "application/json",
                "application/pdf",
                "image/png",
                "image/jpeg",
            ],
            "max_file_bytes": 10_485_760,
        },
    }


def _historical_deny_globs() -> list[str]:
    return [
        "**/.git/**",
        "**/.cache/**",
        "**/node_modules/**",
        "**/vendor/**",
        "**/dist/**",
        "**/build/**",
        "**/.env*",
        "**/*secret*",
        "**/*credential*",
    ]
