from __future__ import annotations

from typing import Any
from uuid import UUID

from autoskill.db.evaluations import EvaluationRunResult, EvaluationStore
from autoskill.db.observability import NullObservabilityStore, ObservabilityStore
from autoskill.services.autonomy_orchestrator import ProposalGateAutonomyOrchestrator


async def run_pending_proposal_gates_with_trace(
    evaluations: EvaluationStore,
    *,
    observability: ObservabilityStore | None = None,
    workspace_key: str | None = None,
    limit: int = 50,
    trace_id: UUID | None = None,
    parent_span_id: UUID | None = None,
    source: str = "api",
    safe_attributes: dict[str, Any] | None = None,
    autonomy_orchestrator: ProposalGateAutonomyOrchestrator | None = None,
    job_id: UUID | None = None,
) -> EvaluationRunResult:
    """Run deterministic proposal gates inside a content-safe evaluator span."""
    observed = observability or NullObservabilityStore()
    workspace = workspace_key or "unknown"
    span = await observed.start_span(
        workspace_key=workspace,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        operation_name="evaluations.run",
        operation_kind="evaluator",
        safe_attributes={
            "source": source,
            "limit": limit,
            **(safe_attributes or {}),
        },
    )
    try:
        result = await evaluations.run_pending_proposal_gates(
            workspace_key=workspace_key,
            limit=limit,
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
        )
        if autonomy_orchestrator is not None and result.needs_intervention:
            result = await autonomy_orchestrator.resolve_run(
                result,
                workspace_key=workspace_key,
                job_id=job_id,
            )
    except Exception as error:
        await observed.finish_span(
            span_id=span.span_id,
            status="error",
            safe_attributes={
                "source": source,
                "error": f"{type(error).__name__}: {error}"[:500],
            },
        )
        raise

    await observed.finish_span(
        span_id=span.span_id,
        status="ok",
        safe_attributes={
            "source": source,
            "scanned": result.scanned,
            "evaluated": result.evaluated,
            "blocked": result.blocked,
            "failed": result.failed,
            "needs_intervention": result.needs_intervention,
            "passed": result.passed,
        },
        object_refs=_evaluation_object_refs(result),
    )
    return result


def _evaluation_object_refs(result: EvaluationRunResult) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in result.evaluations[:50]:
        refs.append(
            {
                "object_type": "evaluation",
                "object_id": str(item.evaluation_id),
            }
        )
        refs.append(
            {
                "object_type": "skill_version",
                "object_id": str(item.skill_version_id),
            }
        )
    return refs
