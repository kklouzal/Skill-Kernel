from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from autoskill.core.config import Settings, get_settings
from autoskill.db.activation import AsyncpgActivationGateStore
from autoskill.db.attribution import AsyncpgAttributionStore
from autoskill.db.audit import AsyncpgAuditStore
from autoskill.db.candidates import AsyncpgCandidateStore
from autoskill.db.context import AsyncpgContextGovernanceStore
from autoskill.db.contracts import AsyncpgContractStore
from autoskill.db.diagnostics import AsyncpgDiagnosticMomentumStore
from autoskill.db.embeddings import AsyncpgEmbeddingStore
from autoskill.db.evaluations import AsyncpgEvaluationStore
from autoskill.db.evidence import AsyncpgEvidenceStore
from autoskill.db.external_skills import AsyncpgExternalSkillStore
from autoskill.db.governance import AsyncpgGovernanceStore
from autoskill.db.historical import AsyncpgHistoricalImportStore
from autoskill.db.jobs import AsyncpgJobStore
from autoskill.db.memory import AsyncpgMemoryGovernanceStore
from autoskill.db.observability import AsyncpgObservabilityStore
from autoskill.db.profiles import AsyncpgProfileStore
from autoskill.db.retrieval import AsyncpgRetrievalStore
from autoskill.db.scheduler import AsyncpgSchedulerStore
from autoskill.db.topology import AsyncpgTopologyStore
from autoskill.db.usage import AsyncpgUsageStore
from autoskill.db.utility import AsyncpgUtilityStore
from autoskill.services.embedding_generation import (
    build_text_embedder_from_settings,
    embedding_provider_policy,
)
from autoskill.services.external_inventory import ensure_external_skill_scan_schedule
from autoskill.services.historical_discovery import (
    ensure_historical_discovery_schedule,
    resolve_historical_import_roots,
)
from autoskill.services.scheduler_defaults import ensure_core_schedules
from autoskill.services.worker import (
    CANONICAL_WORKER_POOLS,
    WorkerLoopConfig,
    WorkerPool,
    WorkerStores,
    normalize_worker_pool,
    run_worker_loop,
)


async def run_worker(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("AUTOSKILL_DATABASE_URL is required for worker mode")

    jobs = AsyncpgJobStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    scheduler = AsyncpgSchedulerStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    evidence = AsyncpgEvidenceStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    external_skills = AsyncpgExternalSkillStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    historical_import = AsyncpgHistoricalImportStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    embeddings = AsyncpgEmbeddingStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    evaluations = AsyncpgEvaluationStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    audit = AsyncpgAuditStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    retrieval = AsyncpgRetrievalStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    governance = AsyncpgGovernanceStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    candidates = AsyncpgCandidateStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    utility = AsyncpgUtilityStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    usage = AsyncpgUsageStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    contracts = AsyncpgContractStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    diagnostics = AsyncpgDiagnosticMomentumStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    context_governance = AsyncpgContextGovernanceStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    observability = AsyncpgObservabilityStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    topology = AsyncpgTopologyStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    attribution = AsyncpgAttributionStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    activation_gate = AsyncpgActivationGateStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    memory_governance = AsyncpgMemoryGovernanceStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    profiles = AsyncpgProfileStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)

    try:
        workspace_root, archive_root = _writer_worker_roots(settings, args.workspace_root)
        historical_import_roots = resolve_historical_import_roots(
            settings,
            explicit_roots=args.historical_import_root,
            workspace_root=workspace_root,
        )
        historical_import_max_files = (
            args.historical_import_max_files or settings.historical_import_max_files_per_run
        )
        historical_import_max_bytes = (
            args.historical_import_max_bytes or settings.historical_import_max_bytes_per_run
        )
        utility.set_writer_roots(
            workspace_root=workspace_root,
            archive_root=archive_root,
        )
        if args.pool == "scheduler":
            await ensure_core_schedules(
                scheduler,
                workspace_key=args.workspace_id,
            )
        await ensure_external_skill_scan_schedule(
            scheduler,
            workspace_key=args.workspace_id,
            external_skill_roots=args.external_skill_root,
            interval_seconds=args.external_skill_scan_interval_seconds,
            source=args.external_skill_source,
        )
        await ensure_historical_discovery_schedule(
            scheduler,
            workspace_key=args.workspace_id,
            roots=historical_import_roots,
            interval_seconds=args.historical_import_scan_interval_seconds,
            max_files=historical_import_max_files,
            max_bytes=historical_import_max_bytes,
        )
        embedding_policy = embedding_provider_policy(settings)
        settings_embedder = None
        if embedding_policy.production_ready or settings.embedding_hash_provider_allowed:
            settings_embedder = build_text_embedder_from_settings(settings)
        summary = await run_worker_loop(
            WorkerStores(
                jobs=jobs,
                scheduler=scheduler,
                evidence=evidence,
                external_skills=external_skills,
                candidates=candidates,
                historical_import=historical_import,
                embeddings=embeddings,
                evaluations=evaluations,
                audit=audit,
                retrieval=retrieval,
                governance=governance,
                utility=utility,
                contracts=contracts,
                diagnostics=diagnostics,
                context_governance=context_governance,
                topology=topology,
                usage=usage,
                attribution=attribution,
                activation_gate=activation_gate,
                memory_governance=memory_governance,
                observability=observability,
                profiles=profiles,
                embedder=settings_embedder,
                embedding_api_key=settings.embedding_api_key,
                embedding_api_base_url=settings.embedding_api_base_url,
                embedding_hash_provider_allowed=settings.embedding_hash_provider_allowed,
                workspace_root=workspace_root,
                archive_root=archive_root,
                external_skill_roots=args.external_skill_root,
                historical_import_roots=historical_import_roots,
            ),
            WorkerLoopConfig(
                worker_id=args.worker_id,
                pool=args.pool,
                concurrency=args.concurrency or _configured_concurrency(settings, args.pool),
                lease_seconds=args.lease_seconds,
                idle_sleep_seconds=args.idle_sleep_seconds,
            ),
            stop_event=stop_event,
        )
        print(summary.to_json())
        return 0
    finally:
        await jobs.close()
        await scheduler.close()
        await evidence.close()
        await external_skills.close()
        await historical_import.close()
        await embeddings.close()
        await evaluations.close()
        await audit.close()
        await retrieval.close()
        await governance.close()
        await utility.close()
        await contracts.close()
        await diagnostics.close()
        await context_governance.close()
        await observability.close()
        await topology.close()
        await usage.close()
        await attribution.close()
        await activation_gate.close()
        await memory_governance.close()
        await profiles.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SkillKernel sidecar worker loop")
    parser.add_argument("--worker-id", default="autoskill-worker")
    parser.add_argument("--workspace-id", default="default")
    parser.add_argument(
        "--pool",
        choices=[*CANONICAL_WORKER_POOLS, "mutation"],
        default="maintenance",
    )
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--idle-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--workspace-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--external-skill-root",
        action="append",
        type=Path,
        default=[],
        help="Read-only skill root to inventory for external-skill collision awareness.",
    )
    parser.add_argument(
        "--external-skill-scan-interval-seconds",
        type=int,
        default=6 * 60 * 60,
        help="Default durable scan cadence for configured external skill roots.",
    )
    parser.add_argument(
        "--external-skill-source",
        default="workspace-skill-root",
        help="Public source label for external skill inventory records.",
    )
    parser.add_argument(
        "--historical-import-root",
        action="append",
        type=Path,
        default=[],
        help="Read-only root to inventory for historical import discovery.",
    )
    parser.add_argument(
        "--historical-import-scan-interval-seconds",
        type=int,
        default=12 * 60 * 60,
        help="Default durable scan cadence for configured historical import roots.",
    )
    parser.add_argument("--historical-import-max-files", type=int, default=None)
    parser.add_argument("--historical-import-max-bytes", type=int, default=None)
    return parser.parse_args()


def _configured_concurrency(settings: Settings, pool: WorkerPool) -> int:
    requested_pool = pool
    pool = normalize_worker_pool(pool)
    if pool == "scheduler":
        return settings.worker_scheduler_concurrency
    if pool == "ingest":
        return settings.worker_ingest_concurrency
    if pool == "backfill":
        return settings.worker_backfill_concurrency
    if pool == "embedding":
        return settings.worker_embedding_concurrency
    if pool == "retrieval":
        return settings.worker_retrieval_concurrency
    if pool == "analysis":
        return settings.worker_analysis_concurrency
    if pool == "llm_generation":
        return settings.worker_llm_generation_concurrency
    if pool == "scanner":
        return settings.worker_scanner_concurrency
    if pool == "evaluation":
        return settings.worker_evaluation_concurrency
    if pool == "filesystem":
        if requested_pool == "mutation":
            return settings.worker_mutation_concurrency
        return settings.worker_filesystem_concurrency
    return settings.worker_maintenance_concurrency


def _writer_worker_roots(settings: Settings, workspace_root: Path) -> tuple[Path, Path]:
    root = workspace_root.resolve()
    active_root = (
        settings.active_root if settings.active_root.is_absolute() else root / settings.active_root
    ).resolve()
    expected_active_root = (root / "skills" / "autoskill").resolve()
    if active_root != expected_active_root:
        raise SystemExit("filesystem worker requires AUTOSKILL_ACTIVE_ROOT=skills/autoskill")
    archive_root = (
        settings.archive_root
        if settings.archive_root.is_absolute()
        else root / settings.archive_root
    ).resolve()
    try:
        archive_root.relative_to(root)
    except ValueError as error:
        raise SystemExit("filesystem worker archive root must stay under workspace root") from error
    return root, archive_root


def main() -> None:
    raise SystemExit(asyncio.run(run_worker(parse_args())))


if __name__ == "__main__":
    main()
