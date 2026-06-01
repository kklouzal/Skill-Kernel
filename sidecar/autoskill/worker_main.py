from __future__ import annotations

import argparse
import asyncio
import signal
from pathlib import Path

from autoskill.core.config import Settings, get_settings
from autoskill.db.context import AsyncpgContextGovernanceStore
from autoskill.db.contracts import AsyncpgContractStore
from autoskill.db.embeddings import AsyncpgEmbeddingStore
from autoskill.db.evaluations import AsyncpgEvaluationStore
from autoskill.db.evidence import AsyncpgEvidenceStore
from autoskill.db.external_skills import AsyncpgExternalSkillStore
from autoskill.db.governance import AsyncpgGovernanceStore
from autoskill.db.jobs import AsyncpgJobStore
from autoskill.db.observability import AsyncpgObservabilityStore
from autoskill.db.retrieval import AsyncpgRetrievalStore
from autoskill.db.scheduler import AsyncpgSchedulerStore
from autoskill.db.topology import AsyncpgTopologyStore
from autoskill.db.utility import AsyncpgUtilityStore
from autoskill.services.embedding_generation import build_text_embedder_from_settings
from autoskill.services.worker import WorkerLoopConfig, WorkerPool, WorkerStores, run_worker_loop


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
    embeddings = AsyncpgEmbeddingStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    evaluations = AsyncpgEvaluationStore(
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
    utility = AsyncpgUtilityStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    contracts = AsyncpgContractStore(
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
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)

    try:
        workspace_root, archive_root = _writer_worker_roots(settings, args.workspace_root)
        summary = await run_worker_loop(
            WorkerStores(
                jobs=jobs,
                scheduler=scheduler,
                evidence=evidence,
                external_skills=external_skills,
                embeddings=embeddings,
                evaluations=evaluations,
                retrieval=retrieval,
                governance=governance,
                utility=utility,
                contracts=contracts,
                context_governance=context_governance,
                topology=topology,
                observability=observability,
                embedder=build_text_embedder_from_settings(settings),
                workspace_root=workspace_root,
                archive_root=archive_root,
                external_skill_roots=args.external_skill_root,
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
        await embeddings.close()
        await evaluations.close()
        await retrieval.close()
        await governance.close()
        await utility.close()
        await contracts.close()
        await context_governance.close()
        await observability.close()
        await topology.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SkillKernel sidecar worker loop")
    parser.add_argument("--worker-id", default="autoskill-worker")
    parser.add_argument(
        "--pool",
        choices=["scheduler", "maintenance", "mutation"],
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
    return parser.parse_args()


def _configured_concurrency(settings: Settings, pool: WorkerPool) -> int:
    if pool == "scheduler":
        return settings.worker_scheduler_concurrency
    if pool == "mutation":
        return settings.worker_mutation_concurrency
    return settings.worker_maintenance_concurrency


def _writer_worker_roots(settings: Settings, workspace_root: Path) -> tuple[Path, Path]:
    root = workspace_root.resolve()
    active_root = (
        settings.active_root if settings.active_root.is_absolute() else root / settings.active_root
    ).resolve()
    expected_active_root = (root / "skills" / "autoskill").resolve()
    if active_root != expected_active_root:
        raise SystemExit("mutation worker requires AUTOSKILL_ACTIVE_ROOT=skills/autoskill")
    archive_root = (
        settings.archive_root
        if settings.archive_root.is_absolute()
        else root / settings.archive_root
    ).resolve()
    try:
        archive_root.relative_to(root)
    except ValueError as error:
        raise SystemExit("mutation worker archive root must stay under workspace root") from error
    return root, archive_root


def main() -> None:
    raise SystemExit(asyncio.run(run_worker(parse_args())))


if __name__ == "__main__":
    main()
