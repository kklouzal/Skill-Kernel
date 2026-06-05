from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from autoskill.core.hashing import sha256_text
from autoskill.db.pool import AsyncpgPoolOwner
from autoskill.db.workspaces import ensure_workspace


@dataclass(frozen=True)
class ContextArtifactRecord:
    context_artifact_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    artifact_kind: str
    source_object_type: str
    source_object_id: UUID | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    broker_policy_version_id: UUID | None
    text_hash: str
    token_count: int
    max_tokens: int
    safety_status: str
    equivalence_status: str
    budget_status: str
    shadowing_status: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ContextArtifactRecord:
        return cls(
            context_artifact_id=row["context_artifact_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            artifact_kind=row["artifact_kind"],
            source_object_type=row["source_object_type"],
            source_object_id=_row_get(row, "source_object_id"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            broker_policy_version_id=_row_get(row, "broker_policy_version_id"),
            text_hash=row["text_hash"],
            token_count=int(row["token_count"]),
            max_tokens=int(row["max_tokens"]),
            safety_status=row["safety_status"],
            equivalence_status=row["equivalence_status"],
            budget_status=row["budget_status"],
            shadowing_status=row["shadowing_status"],
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "context_artifact_id": str(self.context_artifact_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "artifact_kind": self.artifact_kind,
            "source_object_type": self.source_object_type,
            "source_object_id": str(self.source_object_id) if self.source_object_id else None,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "broker_policy_version_id": (
                str(self.broker_policy_version_id) if self.broker_policy_version_id else None
            ),
            "text_hash": self.text_hash,
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
            "safety_status": self.safety_status,
            "equivalence_status": self.equivalence_status,
            "budget_status": self.budget_status,
            "shadowing_status": self.shadowing_status,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class TokenLedgerRecord:
    context_token_ledger_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    context_artifact_id: UUID | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    broker_policy_version_id: UUID | None
    session_id: str | None
    turn_id: str | None
    visibility_state: str
    token_count: int
    outcome: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> TokenLedgerRecord:
        return cls(
            context_token_ledger_id=row["context_token_ledger_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            context_artifact_id=_row_get(row, "context_artifact_id"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            broker_policy_version_id=_row_get(row, "broker_policy_version_id"),
            session_id=_row_get(row, "session_id"),
            turn_id=_row_get(row, "turn_id"),
            visibility_state=row["visibility_state"],
            token_count=int(row["token_count"]),
            outcome=_row_get(row, "outcome"),
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "context_token_ledger_id": str(self.context_token_ledger_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "context_artifact_id": (
                str(self.context_artifact_id) if self.context_artifact_id else None
            ),
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "broker_policy_version_id": (
                str(self.broker_policy_version_id) if self.broker_policy_version_id else None
            ),
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "visibility_state": self.visibility_state,
            "token_count": self.token_count,
            "outcome": self.outcome,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ContextCompileRunRecord:
    context_compile_run_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    candidate_id: UUID | None
    context_artifact_id: UUID | None
    compiler_version: str
    model_assist_used: bool
    input_skillir_hash: str
    output_manifest_hash: str
    target_runtime_tokens: int | None
    actual_runtime_tokens: int
    compression_ratio: float | None
    semantic_equivalence_score: float | None
    status: str
    reject_reason: str | None
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ContextCompileRunRecord:
        return cls(
            context_compile_run_id=row["context_compile_run_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            candidate_id=_row_get(row, "candidate_id"),
            context_artifact_id=_row_get(row, "context_artifact_id"),
            compiler_version=row["compiler_version"],
            model_assist_used=bool(row["model_assist_used"]),
            input_skillir_hash=row["input_skillir_hash"],
            output_manifest_hash=row["output_manifest_hash"],
            target_runtime_tokens=_optional_int(row, "target_runtime_tokens"),
            actual_runtime_tokens=int(row["actual_runtime_tokens"]),
            compression_ratio=_optional_float(row, "compression_ratio"),
            semantic_equivalence_score=_optional_float(row, "semantic_equivalence_score"),
            status=row["status"],
            reject_reason=_row_get(row, "reject_reason"),
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "context_compile_run_id": str(self.context_compile_run_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "candidate_id": str(self.candidate_id) if self.candidate_id else None,
            "context_artifact_id": (
                str(self.context_artifact_id) if self.context_artifact_id else None
            ),
            "compiler_version": self.compiler_version,
            "model_assist_used": self.model_assist_used,
            "input_skillir_hash": self.input_skillir_hash,
            "output_manifest_hash": self.output_manifest_hash,
            "target_runtime_tokens": self.target_runtime_tokens,
            "actual_runtime_tokens": self.actual_runtime_tokens,
            "compression_ratio": self.compression_ratio,
            "semantic_equivalence_score": self.semantic_equivalence_score,
            "status": self.status,
            "reject_reason": self.reject_reason,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ContextBudgetEventRecord:
    context_budget_event_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_id: UUID | None
    skill_version_id: UUID | None
    context_artifact_id: UUID | None
    event_type: str
    tokens_delta: int | None
    marginal_success_delta: float | None
    false_positive_load_delta: float | None
    ignored_load_delta: float | None
    shadowing_delta: float | None
    decision: str
    evidence: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> ContextBudgetEventRecord:
        return cls(
            context_budget_event_id=row["context_budget_event_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_id=_row_get(row, "skill_id"),
            skill_version_id=_row_get(row, "skill_version_id"),
            context_artifact_id=_row_get(row, "context_artifact_id"),
            event_type=row["event_type"],
            tokens_delta=_optional_int(row, "tokens_delta"),
            marginal_success_delta=_optional_float(row, "marginal_success_delta"),
            false_positive_load_delta=_optional_float(row, "false_positive_load_delta"),
            ignored_load_delta=_optional_float(row, "ignored_load_delta"),
            shadowing_delta=_optional_float(row, "shadowing_delta"),
            decision=row["decision"],
            evidence=_json_dict(row["evidence"]),
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "context_budget_event_id": str(self.context_budget_event_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "skill_version_id": str(self.skill_version_id) if self.skill_version_id else None,
            "context_artifact_id": (
                str(self.context_artifact_id) if self.context_artifact_id else None
            ),
            "event_type": self.event_type,
            "tokens_delta": self.tokens_delta,
            "marginal_success_delta": self.marginal_success_delta,
            "false_positive_load_delta": self.false_positive_load_delta,
            "ignored_load_delta": self.ignored_load_delta,
            "shadowing_delta": self.shadowing_delta,
            "decision": self.decision,
            "evidence": self.evidence,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class SemanticCompressionTrialRecord:
    semantic_compression_trial_id: UUID
    workspace_id: UUID | None
    workspace_key: str | None
    skill_id: UUID | None
    source_revision_id: UUID | None
    candidate_revision_id: UUID | None
    source_context_artifact_id: UUID | None
    candidate_context_artifact_id: UUID | None
    source_tokens: int
    candidate_tokens: int
    preserved_requirements: int
    lost_requirements: int
    added_unsupported_requirements: int
    equivalence_score: float
    target_probe_pass_rate: float | None
    regression_probe_pass_rate: float | None
    status: str
    metadata: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record | dict[str, Any]) -> SemanticCompressionTrialRecord:
        return cls(
            semantic_compression_trial_id=row["semantic_compression_trial_id"],
            workspace_id=_row_get(row, "workspace_id"),
            workspace_key=_row_get(row, "workspace_key"),
            skill_id=_row_get(row, "skill_id"),
            source_revision_id=_row_get(row, "source_revision_id"),
            candidate_revision_id=_row_get(row, "candidate_revision_id"),
            source_context_artifact_id=_row_get(row, "source_context_artifact_id"),
            candidate_context_artifact_id=_row_get(row, "candidate_context_artifact_id"),
            source_tokens=int(row["source_tokens"]),
            candidate_tokens=int(row["candidate_tokens"]),
            preserved_requirements=int(row["preserved_requirements"]),
            lost_requirements=int(row["lost_requirements"]),
            added_unsupported_requirements=int(row["added_unsupported_requirements"]),
            equivalence_score=float(row["equivalence_score"]),
            target_probe_pass_rate=_optional_float(row, "target_probe_pass_rate"),
            regression_probe_pass_rate=_optional_float(row, "regression_probe_pass_rate"),
            status=row["status"],
            metadata=_json_dict(row["metadata"]),
            created_at=row["created_at"],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "semantic_compression_trial_id": str(self.semantic_compression_trial_id),
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "workspace_key": self.workspace_key,
            "skill_id": str(self.skill_id) if self.skill_id else None,
            "source_revision_id": (
                str(self.source_revision_id) if self.source_revision_id else None
            ),
            "candidate_revision_id": (
                str(self.candidate_revision_id) if self.candidate_revision_id else None
            ),
            "source_context_artifact_id": (
                str(self.source_context_artifact_id)
                if self.source_context_artifact_id
                else None
            ),
            "candidate_context_artifact_id": (
                str(self.candidate_context_artifact_id)
                if self.candidate_context_artifact_id
                else None
            ),
            "source_tokens": self.source_tokens,
            "candidate_tokens": self.candidate_tokens,
            "preserved_requirements": self.preserved_requirements,
            "lost_requirements": self.lost_requirements,
            "added_unsupported_requirements": self.added_unsupported_requirements,
            "equivalence_score": self.equivalence_score,
            "target_probe_pass_rate": self.target_probe_pass_rate,
            "regression_probe_pass_rate": self.regression_probe_pass_rate,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class ContextGovernanceStore(Protocol):
    async def list_artifacts(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextArtifactRecord]:
        """Return bounded context-loadable artifact gate records."""

    async def get_artifact(
        self,
        *,
        context_artifact_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextArtifactRecord | None:
        """Return one context artifact gate record."""

    async def list_compile_runs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextCompileRunRecord]:
        """Return bounded context compiler run records."""

    async def get_compile_run(
        self,
        *,
        context_compile_run_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextCompileRunRecord | None:
        """Return one context compiler run record."""

    async def list_budget_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextBudgetEventRecord]:
        """Return bounded token-budget governor decisions."""

    async def get_budget_event(
        self,
        *,
        context_budget_event_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextBudgetEventRecord | None:
        """Return one token-budget governor decision."""

    async def list_semantic_compression_trials(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[SemanticCompressionTrialRecord]:
        """Return bounded semantic compression trial records."""

    async def get_semantic_compression_trial(
        self,
        *,
        semantic_compression_trial_id: UUID,
        workspace_key: str | None = None,
    ) -> SemanticCompressionTrialRecord | None:
        """Return one semantic compression trial record."""

    async def record_artifact(
        self,
        *,
        workspace_key: str,
        artifact_kind: str,
        source_object_type: str,
        text: str,
        max_tokens: int,
        source_object_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        safety_status: str = "pending",
        equivalence_status: str = "pending",
        shadowing_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> ContextArtifactRecord:
        """Persist context-loadable artifact budget and gate state."""

    async def record_token_ledger(
        self,
        *,
        workspace_key: str,
        visibility_state: str,
        token_count: int,
        context_artifact_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        """Record marginal context visibility accounting."""

    async def record_token_ledger_outcome(
        self,
        *,
        workspace_key: str,
        context_token_ledger_id: UUID,
        outcome: str,
        utility_delta: float = 0.0,
        task_success: bool | None = None,
        token_savings: int | None = None,
        latency_delta_ms: float | None = None,
        tool_call_delta: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        """Update a visibility ledger row with observed marginal-value outcome."""

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        """Mark context artifacts and ledgers derived from revoked objects."""

    async def record_compile_run(
        self,
        *,
        workspace_key: str,
        compiler_version: str,
        input_skillir_hash: str,
        output_manifest_hash: str,
        actual_runtime_tokens: int,
        status: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        candidate_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        model_assist_used: bool = False,
        target_runtime_tokens: int | None = None,
        compression_ratio: float | None = None,
        semantic_equivalence_score: float | None = None,
        reject_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextCompileRunRecord:
        """Persist a deterministic context compiler run and its gate result."""

    async def record_budget_event(
        self,
        *,
        workspace_key: str,
        event_type: str,
        decision: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        tokens_delta: int | None = None,
        marginal_success_delta: float | None = None,
        false_positive_load_delta: float | None = None,
        ignored_load_delta: float | None = None,
        shadowing_delta: float | None = None,
        evidence: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextBudgetEventRecord:
        """Persist a token-budget governor decision."""

    async def record_semantic_compression_trial(
        self,
        *,
        workspace_key: str,
        source_tokens: int,
        candidate_tokens: int,
        preserved_requirements: int,
        lost_requirements: int,
        added_unsupported_requirements: int,
        equivalence_score: float,
        status: str,
        skill_id: UUID | None = None,
        source_revision_id: UUID | None = None,
        candidate_revision_id: UUID | None = None,
        source_context_artifact_id: UUID | None = None,
        candidate_context_artifact_id: UUID | None = None,
        target_probe_pass_rate: float | None = None,
        regression_probe_pass_rate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticCompressionTrialRecord:
        """Persist a semantic compression acceptance trial."""


class NullContextGovernanceStore:
    def __init__(self) -> None:
        self.artifacts: list[ContextArtifactRecord] = []
        self.token_ledgers: list[TokenLedgerRecord] = []
        self.compile_runs: list[ContextCompileRunRecord] = []
        self.budget_events: list[ContextBudgetEventRecord] = []
        self.semantic_compression_trials: list[SemanticCompressionTrialRecord] = []

    async def list_artifacts(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextArtifactRecord]:
        return _bounded_recent(self.artifacts, workspace_key=workspace_key, limit=limit)

    async def get_artifact(
        self,
        *,
        context_artifact_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextArtifactRecord | None:
        return _find_record(
            self.artifacts,
            "context_artifact_id",
            context_artifact_id,
            workspace_key=workspace_key,
        )

    async def list_compile_runs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextCompileRunRecord]:
        return _bounded_recent(self.compile_runs, workspace_key=workspace_key, limit=limit)

    async def get_compile_run(
        self,
        *,
        context_compile_run_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextCompileRunRecord | None:
        return _find_record(
            self.compile_runs,
            "context_compile_run_id",
            context_compile_run_id,
            workspace_key=workspace_key,
        )

    async def list_budget_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextBudgetEventRecord]:
        return _bounded_recent(self.budget_events, workspace_key=workspace_key, limit=limit)

    async def get_budget_event(
        self,
        *,
        context_budget_event_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextBudgetEventRecord | None:
        return _find_record(
            self.budget_events,
            "context_budget_event_id",
            context_budget_event_id,
            workspace_key=workspace_key,
        )

    async def list_semantic_compression_trials(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[SemanticCompressionTrialRecord]:
        return _bounded_recent(
            self.semantic_compression_trials,
            workspace_key=workspace_key,
            limit=limit,
        )

    async def get_semantic_compression_trial(
        self,
        *,
        semantic_compression_trial_id: UUID,
        workspace_key: str | None = None,
    ) -> SemanticCompressionTrialRecord | None:
        return _find_record(
            self.semantic_compression_trials,
            "semantic_compression_trial_id",
            semantic_compression_trial_id,
            workspace_key=workspace_key,
        )

    async def record_artifact(
        self,
        *,
        workspace_key: str,
        artifact_kind: str,
        source_object_type: str,
        text: str,
        max_tokens: int,
        source_object_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        safety_status: str = "pending",
        equivalence_status: str = "pending",
        shadowing_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> ContextArtifactRecord:
        from uuid import uuid4

        token_count = _estimate_tokens(text)
        record = ContextArtifactRecord(
            context_artifact_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            artifact_kind=artifact_kind,
            source_object_type=source_object_type,
            source_object_id=source_object_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            broker_policy_version_id=broker_policy_version_id,
            text_hash=sha256_text(text),
            token_count=token_count,
            max_tokens=max_tokens,
            safety_status=safety_status,
            equivalence_status=equivalence_status,
            budget_status=_budget_status(token_count, max_tokens),
            shadowing_status=shadowing_status,
            metadata=metadata or {},
            created_at=datetime.now(),
        )
        self.artifacts.append(record)
        return record

    async def record_token_ledger(
        self,
        *,
        workspace_key: str,
        visibility_state: str,
        token_count: int,
        context_artifact_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        from uuid import uuid4

        record = TokenLedgerRecord(
            context_token_ledger_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            context_artifact_id=context_artifact_id,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            broker_policy_version_id=broker_policy_version_id,
            session_id=session_id,
            turn_id=turn_id,
            visibility_state=visibility_state,
            token_count=token_count,
            outcome=outcome,
            metadata=metadata or {},
            created_at=datetime.now(),
        )
        self.token_ledgers.append(record)
        return record

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        return 0

    async def record_token_ledger_outcome(
        self,
        *,
        workspace_key: str,
        context_token_ledger_id: UUID,
        outcome: str,
        utility_delta: float = 0.0,
        task_success: bool | None = None,
        token_savings: int | None = None,
        latency_delta_ms: float | None = None,
        tool_call_delta: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        from uuid import uuid4

        token_count = int((metadata or {}).get("token_count", 1))
        value = _marginal_value_score(
            token_count=token_count,
            utility_delta=utility_delta,
            task_success=task_success,
            token_savings=token_savings,
            latency_delta_ms=latency_delta_ms,
            tool_call_delta=tool_call_delta,
        )
        marginal = {
            "utility_delta": utility_delta,
            "task_success": task_success,
            "token_savings": token_savings,
            "latency_delta_ms": latency_delta_ms,
            "tool_call_delta": tool_call_delta,
            "marginal_value": value,
            "context_value_per_token": value / max(token_count, 1),
        }
        record = TokenLedgerRecord(
            context_token_ledger_id=context_token_ledger_id or uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            context_artifact_id=None,
            skill_id=None,
            skill_version_id=None,
            broker_policy_version_id=None,
            session_id=None,
            turn_id=None,
            visibility_state="skill_visible",
            token_count=token_count,
            outcome=outcome,
            metadata={
                **(metadata or {}),
                "marginal_value": marginal,
            },
            created_at=datetime.now(),
        )
        self.token_ledgers = [
            existing
            for existing in self.token_ledgers
            if existing.context_token_ledger_id != record.context_token_ledger_id
        ]
        self.token_ledgers.append(record)
        return record

    async def record_compile_run(
        self,
        *,
        workspace_key: str,
        compiler_version: str,
        input_skillir_hash: str,
        output_manifest_hash: str,
        actual_runtime_tokens: int,
        status: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        candidate_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        model_assist_used: bool = False,
        target_runtime_tokens: int | None = None,
        compression_ratio: float | None = None,
        semantic_equivalence_score: float | None = None,
        reject_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextCompileRunRecord:
        from uuid import uuid4

        record = ContextCompileRunRecord(
            context_compile_run_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            candidate_id=candidate_id,
            context_artifact_id=context_artifact_id,
            compiler_version=compiler_version,
            model_assist_used=model_assist_used,
            input_skillir_hash=input_skillir_hash,
            output_manifest_hash=output_manifest_hash,
            target_runtime_tokens=target_runtime_tokens,
            actual_runtime_tokens=actual_runtime_tokens,
            compression_ratio=compression_ratio,
            semantic_equivalence_score=semantic_equivalence_score,
            status=status,
            reject_reason=reject_reason,
            metadata=metadata or {},
            created_at=datetime.now(),
        )
        self.compile_runs.append(record)
        return record

    async def record_budget_event(
        self,
        *,
        workspace_key: str,
        event_type: str,
        decision: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        tokens_delta: int | None = None,
        marginal_success_delta: float | None = None,
        false_positive_load_delta: float | None = None,
        ignored_load_delta: float | None = None,
        shadowing_delta: float | None = None,
        evidence: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextBudgetEventRecord:
        from uuid import uuid4

        record = ContextBudgetEventRecord(
            context_budget_event_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_id=skill_id,
            skill_version_id=skill_version_id,
            context_artifact_id=context_artifact_id,
            event_type=event_type,
            tokens_delta=tokens_delta,
            marginal_success_delta=marginal_success_delta,
            false_positive_load_delta=false_positive_load_delta,
            ignored_load_delta=ignored_load_delta,
            shadowing_delta=shadowing_delta,
            decision=decision,
            evidence=evidence or {},
            metadata=metadata or {},
            created_at=datetime.now(),
        )
        self.budget_events.append(record)
        return record

    async def record_semantic_compression_trial(
        self,
        *,
        workspace_key: str,
        source_tokens: int,
        candidate_tokens: int,
        preserved_requirements: int,
        lost_requirements: int,
        added_unsupported_requirements: int,
        equivalence_score: float,
        status: str,
        skill_id: UUID | None = None,
        source_revision_id: UUID | None = None,
        candidate_revision_id: UUID | None = None,
        source_context_artifact_id: UUID | None = None,
        candidate_context_artifact_id: UUID | None = None,
        target_probe_pass_rate: float | None = None,
        regression_probe_pass_rate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticCompressionTrialRecord:
        from uuid import uuid4

        record = SemanticCompressionTrialRecord(
            semantic_compression_trial_id=uuid4(),
            workspace_id=None,
            workspace_key=workspace_key,
            skill_id=skill_id,
            source_revision_id=source_revision_id,
            candidate_revision_id=candidate_revision_id,
            source_context_artifact_id=source_context_artifact_id,
            candidate_context_artifact_id=candidate_context_artifact_id,
            source_tokens=source_tokens,
            candidate_tokens=candidate_tokens,
            preserved_requirements=preserved_requirements,
            lost_requirements=lost_requirements,
            added_unsupported_requirements=added_unsupported_requirements,
            equivalence_score=equivalence_score,
            target_probe_pass_rate=target_probe_pass_rate,
            regression_probe_pass_rate=regression_probe_pass_rate,
            status=status,
            metadata=metadata or {},
            created_at=datetime.now(),
        )
        self.semantic_compression_trials.append(record)
        return record


class AsyncpgContextGovernanceStore(AsyncpgPoolOwner):
    async def list_artifacts(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextArtifactRecord]:
        rows = await self._fetch_context_rows(
            table="context_artifacts",
            id_column="context_artifact_id",
            workspace_key=workspace_key,
            limit=limit,
        )
        return [ContextArtifactRecord.from_row(row) for row in rows]

    async def get_artifact(
        self,
        *,
        context_artifact_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextArtifactRecord | None:
        row = await self._fetch_context_row(
            table="context_artifacts",
            id_column="context_artifact_id",
            record_id=context_artifact_id,
            workspace_key=workspace_key,
        )
        return ContextArtifactRecord.from_row(row) if row is not None else None

    async def list_compile_runs(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextCompileRunRecord]:
        rows = await self._fetch_context_rows(
            table="context_compile_runs",
            id_column="context_compile_run_id",
            workspace_key=workspace_key,
            limit=limit,
        )
        return [ContextCompileRunRecord.from_row(row) for row in rows]

    async def get_compile_run(
        self,
        *,
        context_compile_run_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextCompileRunRecord | None:
        row = await self._fetch_context_row(
            table="context_compile_runs",
            id_column="context_compile_run_id",
            record_id=context_compile_run_id,
            workspace_key=workspace_key,
        )
        return ContextCompileRunRecord.from_row(row) if row is not None else None

    async def list_budget_events(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[ContextBudgetEventRecord]:
        rows = await self._fetch_context_rows(
            table="context_budget_events",
            id_column="context_budget_event_id",
            workspace_key=workspace_key,
            limit=limit,
        )
        return [ContextBudgetEventRecord.from_row(row) for row in rows]

    async def get_budget_event(
        self,
        *,
        context_budget_event_id: UUID,
        workspace_key: str | None = None,
    ) -> ContextBudgetEventRecord | None:
        row = await self._fetch_context_row(
            table="context_budget_events",
            id_column="context_budget_event_id",
            record_id=context_budget_event_id,
            workspace_key=workspace_key,
        )
        return ContextBudgetEventRecord.from_row(row) if row is not None else None

    async def list_semantic_compression_trials(
        self,
        *,
        workspace_key: str | None = None,
        limit: int = 100,
    ) -> list[SemanticCompressionTrialRecord]:
        rows = await self._fetch_context_rows(
            table="semantic_compression_trials",
            id_column="semantic_compression_trial_id",
            workspace_key=workspace_key,
            limit=limit,
        )
        return [SemanticCompressionTrialRecord.from_row(row) for row in rows]

    async def get_semantic_compression_trial(
        self,
        *,
        semantic_compression_trial_id: UUID,
        workspace_key: str | None = None,
    ) -> SemanticCompressionTrialRecord | None:
        row = await self._fetch_context_row(
            table="semantic_compression_trials",
            id_column="semantic_compression_trial_id",
            record_id=semantic_compression_trial_id,
            workspace_key=workspace_key,
        )
        return SemanticCompressionTrialRecord.from_row(row) if row is not None else None

    async def _fetch_context_rows(
        self,
        *,
        table: str,
        id_column: str,
        workspace_key: str | None,
        limit: int,
    ) -> list[asyncpg.Record]:
        pool = await self._get_pool()
        bounded_limit = max(1, min(limit, 500))
        async with pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT t.*, w.external_key AS workspace_key
                FROM autoskill.{table} t
                JOIN autoskill.workspaces w ON w.workspace_id = t.workspace_id
                WHERE ($1::text IS NULL OR w.external_key = $1)
                ORDER BY t.created_at DESC, t.{id_column} DESC
                LIMIT $2
                """,
                workspace_key,
                bounded_limit,
            )

    async def _fetch_context_row(
        self,
        *,
        table: str,
        id_column: str,
        record_id: UUID,
        workspace_key: str | None,
    ) -> asyncpg.Record | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                f"""
                SELECT t.*, w.external_key AS workspace_key
                FROM autoskill.{table} t
                JOIN autoskill.workspaces w ON w.workspace_id = t.workspace_id
                WHERE t.{id_column} = $1
                  AND ($2::text IS NULL OR w.external_key = $2)
                """,
                record_id,
                workspace_key,
            )

    async def record_artifact(
        self,
        *,
        workspace_key: str,
        artifact_kind: str,
        source_object_type: str,
        text: str,
        max_tokens: int,
        source_object_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        safety_status: str = "pending",
        equivalence_status: str = "pending",
        shadowing_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> ContextArtifactRecord:
        token_count = _estimate_tokens(text)
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.context_artifacts (
                  context_artifact_id,
                  workspace_id,
                  artifact_kind,
                  source_object_type,
                  source_object_id,
                  skill_id,
                  skill_version_id,
                  broker_policy_version_id,
                  text_hash,
                  token_count,
                  max_tokens,
                  safety_status,
                  equivalence_status,
                  budget_status,
                  shadowing_status,
                  metadata
                )
                VALUES (
                  gen_random_uuid(),
                  $1,
                  $2,
                  $3,
                  $4,
                  $5,
                  $6,
                  $7,
                  $8,
                  $9,
                  $10,
                  $11,
                  $12,
                  $13,
                  $14,
                  $15::jsonb
                )
                ON CONFLICT (
                  workspace_id,
                  artifact_kind,
                  source_object_type,
                  source_object_id,
                  text_hash
                )
                DO UPDATE SET
                  token_count = EXCLUDED.token_count,
                  max_tokens = EXCLUDED.max_tokens,
                  safety_status = EXCLUDED.safety_status,
                  equivalence_status = EXCLUDED.equivalence_status,
                  budget_status = EXCLUDED.budget_status,
                  shadowing_status = EXCLUDED.shadowing_status,
                  metadata = EXCLUDED.metadata
                RETURNING *, $16::text AS workspace_key
                """,
                workspace_id,
                artifact_kind,
                source_object_type,
                source_object_id,
                skill_id,
                skill_version_id,
                broker_policy_version_id,
                sha256_text(text),
                token_count,
                max_tokens,
                safety_status,
                equivalence_status,
                _budget_status(token_count, max_tokens),
                shadowing_status,
                _json(metadata or {}),
                workspace_key,
            )
        return ContextArtifactRecord.from_row(row)

    async def record_token_ledger(
        self,
        *,
        workspace_key: str,
        visibility_state: str,
        token_count: int,
        context_artifact_id: UUID | None = None,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        broker_policy_version_id: UUID | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        outcome: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.context_token_ledgers (
                  context_token_ledger_id,
                  workspace_id,
                  context_artifact_id,
                  skill_id,
                  skill_version_id,
                  broker_policy_version_id,
                  session_id,
                  turn_id,
                  visibility_state,
                  token_count,
                  outcome,
                  metadata
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb
                )
                RETURNING *, $12::text AS workspace_key
                """,
                workspace_id,
                context_artifact_id,
                skill_id,
                skill_version_id,
                broker_policy_version_id,
                session_id,
                turn_id,
                visibility_state,
                token_count,
                outcome,
                _json(metadata or {}),
                workspace_key,
            )
        return TokenLedgerRecord.from_row(row)

    async def invalidate_objects(
        self,
        *,
        workspace_key: str,
        objects: list[dict[str, str]],
    ) -> int:
        object_keys = _object_keys(objects)
        if not object_keys:
            return 0
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            result = await conn.fetchval(
                """
                WITH targets AS (
                  SELECT *
                  FROM unnest($2::text[], $3::uuid[]) AS target(object_type, object_id)
                ),
                artifacts AS (
                  UPDATE autoskill.context_artifacts ca
                  SET metadata = ca.metadata || jsonb_build_object(
                    'revoked', true,
                    'revoked_at', now(),
                    'revocation_reason', 'derived_object_revoked'
                  )
                  FROM autoskill.workspaces w, targets t
                  WHERE ca.workspace_id = w.workspace_id
                    AND w.external_key = $1
                    AND (
                      (t.object_type = 'context_artifact'
                        AND ca.context_artifact_id = t.object_id)
                      OR (t.object_type = 'skill_version'
                        AND ca.skill_version_id = t.object_id)
                      OR (t.object_type = 'skill'
                        AND ca.skill_id = t.object_id)
                      OR (t.object_type = 'broker_policy_version'
                        AND ca.broker_policy_version_id = t.object_id)
                      OR (t.object_type = ca.source_object_type
                        AND ca.source_object_id = t.object_id)
                    )
                  RETURNING ca.context_artifact_id
                ),
                ledgers AS (
                  UPDATE autoskill.context_token_ledgers ctl
                  SET metadata = ctl.metadata || jsonb_build_object(
                    'revoked', true,
                    'revoked_at', now(),
                    'revocation_reason', 'derived_object_revoked'
                  )
                  FROM autoskill.workspaces w, targets t
                  WHERE ctl.workspace_id = w.workspace_id
                    AND w.external_key = $1
                    AND (
                      (t.object_type = 'context_artifact'
                        AND ctl.context_artifact_id = t.object_id)
                      OR (t.object_type = 'skill_version'
                        AND ctl.skill_version_id = t.object_id)
                      OR (t.object_type = 'skill'
                        AND ctl.skill_id = t.object_id)
                      OR (t.object_type = 'broker_policy_version'
                        AND ctl.broker_policy_version_id = t.object_id)
                      OR ctl.context_artifact_id IN (
                        SELECT context_artifact_id FROM artifacts
                      )
                    )
                  RETURNING ctl.context_token_ledger_id
                )
                SELECT
                  (SELECT count(*) FROM artifacts)
                  + (SELECT count(*) FROM ledgers) AS invalidated
                """,
                workspace_key,
                [object_type for object_type, _object_id in object_keys],
                [object_id for _object_type, object_id in object_keys],
            )
        return int(result or 0)

    async def record_token_ledger_outcome(
        self,
        *,
        workspace_key: str,
        context_token_ledger_id: UUID,
        outcome: str,
        utility_delta: float = 0.0,
        task_success: bool | None = None,
        token_savings: int | None = None,
        latency_delta_ms: float | None = None,
        tool_call_delta: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TokenLedgerRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            existing = await conn.fetchrow(
                """
                SELECT ctl.*, $3::text AS workspace_key
                FROM autoskill.context_token_ledgers ctl
                WHERE ctl.workspace_id = $1
                  AND ctl.context_token_ledger_id = $2
                FOR UPDATE
                """,
                workspace_id,
                context_token_ledger_id,
                workspace_key,
            )
            if existing is None:
                raise ValueError("context token ledger row not found")
            token_count = int(existing["token_count"])
            value = _marginal_value_score(
                token_count=token_count,
                utility_delta=utility_delta,
                task_success=task_success,
                token_savings=token_savings,
                latency_delta_ms=latency_delta_ms,
                tool_call_delta=tool_call_delta,
            )
            marginal = {
                "utility_delta": utility_delta,
                "task_success": task_success,
                "token_savings": token_savings,
                "latency_delta_ms": latency_delta_ms,
                "tool_call_delta": tool_call_delta,
                "marginal_value": value,
                "context_value_per_token": value / max(token_count, 1),
            }
            merged_metadata = {
                **_json_dict(existing["metadata"]),
                **(metadata or {}),
                "marginal_value": marginal,
            }
            row = await conn.fetchrow(
                """
                UPDATE autoskill.context_token_ledgers
                SET outcome = $3,
                    metadata = $4::jsonb
                WHERE workspace_id = $1
                  AND context_token_ledger_id = $2
                RETURNING *, $5::text AS workspace_key
                """,
                workspace_id,
                context_token_ledger_id,
                outcome,
                _json(merged_metadata),
                workspace_key,
            )
            if existing["context_artifact_id"] is not None:
                await _update_context_artifact_marginal_value(
                    conn,
                    workspace_id=workspace_id,
                    context_artifact_id=existing["context_artifact_id"],
                    outcome=outcome,
                    marginal=marginal,
                )
        return TokenLedgerRecord.from_row(row)

    async def record_compile_run(
        self,
        *,
        workspace_key: str,
        compiler_version: str,
        input_skillir_hash: str,
        output_manifest_hash: str,
        actual_runtime_tokens: int,
        status: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        candidate_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        model_assist_used: bool = False,
        target_runtime_tokens: int | None = None,
        compression_ratio: float | None = None,
        semantic_equivalence_score: float | None = None,
        reject_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextCompileRunRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.context_compile_runs (
                  context_compile_run_id,
                  workspace_id,
                  skill_id,
                  skill_version_id,
                  candidate_id,
                  context_artifact_id,
                  compiler_version,
                  model_assist_used,
                  input_skillir_hash,
                  output_manifest_hash,
                  target_runtime_tokens,
                  actual_runtime_tokens,
                  compression_ratio,
                  semantic_equivalence_score,
                  status,
                  reject_reason,
                  metadata
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                  $11, $12, $13, $14, $15, $16::jsonb
                )
                RETURNING *, $17::text AS workspace_key
                """,
                workspace_id,
                skill_id,
                skill_version_id,
                candidate_id,
                context_artifact_id,
                compiler_version,
                model_assist_used,
                input_skillir_hash,
                output_manifest_hash,
                target_runtime_tokens,
                actual_runtime_tokens,
                compression_ratio,
                semantic_equivalence_score,
                status,
                reject_reason,
                _json(metadata or {}),
                workspace_key,
            )
        return ContextCompileRunRecord.from_row(row)

    async def record_budget_event(
        self,
        *,
        workspace_key: str,
        event_type: str,
        decision: str,
        skill_id: UUID | None = None,
        skill_version_id: UUID | None = None,
        context_artifact_id: UUID | None = None,
        tokens_delta: int | None = None,
        marginal_success_delta: float | None = None,
        false_positive_load_delta: float | None = None,
        ignored_load_delta: float | None = None,
        shadowing_delta: float | None = None,
        evidence: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ContextBudgetEventRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.context_budget_events (
                  context_budget_event_id,
                  workspace_id,
                  skill_id,
                  skill_version_id,
                  context_artifact_id,
                  event_type,
                  tokens_delta,
                  marginal_success_delta,
                  false_positive_load_delta,
                  ignored_load_delta,
                  shadowing_delta,
                  decision,
                  evidence,
                  metadata
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                  $11, $12::jsonb, $13::jsonb
                )
                RETURNING *, $14::text AS workspace_key
                """,
                workspace_id,
                skill_id,
                skill_version_id,
                context_artifact_id,
                event_type,
                tokens_delta,
                marginal_success_delta,
                false_positive_load_delta,
                ignored_load_delta,
                shadowing_delta,
                decision,
                _json(evidence or {}),
                _json(metadata or {}),
                workspace_key,
            )
        return ContextBudgetEventRecord.from_row(row)

    async def record_semantic_compression_trial(
        self,
        *,
        workspace_key: str,
        source_tokens: int,
        candidate_tokens: int,
        preserved_requirements: int,
        lost_requirements: int,
        added_unsupported_requirements: int,
        equivalence_score: float,
        status: str,
        skill_id: UUID | None = None,
        source_revision_id: UUID | None = None,
        candidate_revision_id: UUID | None = None,
        source_context_artifact_id: UUID | None = None,
        candidate_context_artifact_id: UUID | None = None,
        target_probe_pass_rate: float | None = None,
        regression_probe_pass_rate: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticCompressionTrialRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            workspace_id = await ensure_workspace(conn, workspace_key)
            row = await conn.fetchrow(
                """
                INSERT INTO autoskill.semantic_compression_trials (
                  semantic_compression_trial_id,
                  workspace_id,
                  skill_id,
                  source_revision_id,
                  candidate_revision_id,
                  source_context_artifact_id,
                  candidate_context_artifact_id,
                  source_tokens,
                  candidate_tokens,
                  preserved_requirements,
                  lost_requirements,
                  added_unsupported_requirements,
                  equivalence_score,
                  target_probe_pass_rate,
                  regression_probe_pass_rate,
                  status,
                  metadata
                )
                VALUES (
                  gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                  $11, $12, $13, $14, $15, $16::jsonb
                )
                RETURNING *, $17::text AS workspace_key
                """,
                workspace_id,
                skill_id,
                source_revision_id,
                candidate_revision_id,
                source_context_artifact_id,
                candidate_context_artifact_id,
                source_tokens,
                candidate_tokens,
                preserved_requirements,
                lost_requirements,
                added_unsupported_requirements,
                equivalence_score,
                target_probe_pass_rate,
                regression_probe_pass_rate,
                status,
                _json(metadata or {}),
                workspace_key,
            )
        return SemanticCompressionTrialRecord.from_row(row)


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _budget_status(token_count: int, max_tokens: int) -> str:
    return "passed" if token_count <= max_tokens else "over_budget"


def _bounded_recent(
    records: list[Any],
    *,
    workspace_key: str | None,
    limit: int,
) -> list[Any]:
    filtered = [
        record
        for record in records
        if workspace_key is None or record.workspace_key == workspace_key
    ]
    return sorted(
        filtered,
        key=lambda record: record.created_at,
        reverse=True,
    )[: max(1, min(limit, 500))]


def _find_record(
    records: list[Any],
    id_attribute: str,
    record_id: UUID,
    *,
    workspace_key: str | None,
) -> Any | None:
    for record in records:
        if getattr(record, id_attribute) != record_id:
            continue
        if workspace_key is not None and record.workspace_key != workspace_key:
            continue
        return record
    return None


async def _update_context_artifact_marginal_value(
    conn: asyncpg.Connection,
    *,
    workspace_id: UUID,
    context_artifact_id: UUID,
    outcome: str,
    marginal: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE autoskill.context_artifacts
        SET semantic_density_score = $4::double precision,
            metadata = metadata || jsonb_build_object(
              'last_marginal_outcome', $3::text,
              'last_marginal_value', $5::jsonb,
              'last_context_value_per_token', $4::double precision
            )
        WHERE workspace_id = $1
          AND context_artifact_id = $2
        """,
        workspace_id,
        context_artifact_id,
        outcome,
        float(marginal["context_value_per_token"]),
        _json(marginal),
    )


def _marginal_value_score(
    *,
    token_count: int,
    utility_delta: float,
    task_success: bool | None,
    token_savings: int | None,
    latency_delta_ms: float | None,
    tool_call_delta: int | None,
) -> float:
    score = float(utility_delta)
    if task_success is True:
        score += 1.0
    elif task_success is False:
        score -= 1.0
    if token_savings is not None:
        score += min(1.0, max(-1.0, float(token_savings) / max(token_count, 1)))
    if latency_delta_ms is not None:
        score += min(0.5, max(-0.5, float(latency_delta_ms) / 10_000.0))
    if tool_call_delta is not None:
        score += min(0.5, max(-0.5, float(tool_call_delta) * 0.1))
    return score


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_get(row: asyncpg.Record | dict[str, Any], key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except KeyError:
        return None


def _optional_int(row: asyncpg.Record | dict[str, Any], key: str) -> int | None:
    value = _row_get(row, key)
    return int(value) if value is not None else None


def _optional_float(row: asyncpg.Record | dict[str, Any], key: str) -> float | None:
    value = _row_get(row, key)
    return float(value) if value is not None else None


def _object_keys(objects: list[dict[str, str]]) -> list[tuple[str, UUID]]:
    keys: list[tuple[str, UUID]] = []
    for item in objects:
        object_type = str(item.get("object_type") or "")
        object_id = item.get("object_id")
        if not object_type or object_id is None:
            continue
        try:
            keys.append((object_type, UUID(str(object_id))))
        except ValueError:
            continue
    return keys
