from __future__ import annotations

import argparse
import asyncio
import signal

from autoskill.core.config import Settings, get_settings
from autoskill.db.embeddings import AsyncpgEmbeddingStore
from autoskill.db.evidence import AsyncpgEvidenceStore
from autoskill.db.jobs import AsyncpgJobStore
from autoskill.db.retrieval import AsyncpgRetrievalStore
from autoskill.db.scheduler import AsyncpgSchedulerStore
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
    embeddings = AsyncpgEmbeddingStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    retrieval = AsyncpgRetrievalStore(
        settings.database_url,
        statement_timeout_ms=settings.statement_timeout_ms,
    )
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)

    try:
        summary = await run_worker_loop(
            WorkerStores(
                jobs=jobs,
                scheduler=scheduler,
                evidence=evidence,
                embeddings=embeddings,
                retrieval=retrieval,
                embedder=build_text_embedder_from_settings(settings),
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
        await embeddings.close()
        await retrieval.close()


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
    return parser.parse_args()


def _configured_concurrency(settings: Settings, pool: WorkerPool) -> int:
    if pool == "scheduler":
        return settings.worker_scheduler_concurrency
    if pool == "mutation":
        return settings.worker_mutation_concurrency
    return settings.worker_maintenance_concurrency


def main() -> None:
    raise SystemExit(asyncio.run(run_worker(parse_args())))


if __name__ == "__main__":
    main()
