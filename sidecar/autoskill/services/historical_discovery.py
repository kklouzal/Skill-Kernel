from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoskill.core.hashing import sha256_json, sha256_text
from autoskill.db.historical import (
    HistoricalImportStore,
    HistoricalSourceInput,
    HistoricalSourceUpsertResult,
)
from autoskill.db.scheduler import SchedulerStore, ScheduleUpsertResult

HISTORICAL_DISCOVERY_VERSION = "historical-discovery.v1"
HISTORICAL_PARSER_VERSION = "historical-import.v1"
HISTORICAL_REDACTION_VERSION = "redaction.v1"
DEFAULT_HISTORICAL_DISCOVERY_INTERVAL_SECONDS = 12 * 60 * 60

WORKSPACE_CONTEXT_FILES = {
    "AGENTS.md",
    "SOUL.md",
    "TOOLS.md",
    "IDENTITY.md",
    "USER.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "BOOT.md",
}
WORKSPACE_MEMORY_FILES = {"MEMORY.md", "DREAMS.md"}
TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".txt", ".yaml", ".yml"}


@dataclass(frozen=True)
class HistoricalDiscoveryItem:
    source_kind: str
    source_key: str
    fingerprint: str
    bytes_estimate: int
    parser_version: str
    redaction_policy_version: str
    trust_level: str
    taint: dict[str, Any]
    metadata: dict[str, Any]
    path: Path | None = None

    def to_source_input(self, *, status: str = "inventory_only") -> HistoricalSourceInput:
        return HistoricalSourceInput(
            source_kind=self.source_kind,
            source_key=self.source_key,
            fingerprint=self.fingerprint,
            parser_version=self.parser_version,
            redaction_policy_version=self.redaction_policy_version,
            trust_level=self.trust_level,
            taint=self.taint,
            metadata=self.metadata,
            status=status,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "source_key": self.source_key,
            "fingerprint": self.fingerprint,
            "bytes_estimate": self.bytes_estimate,
            "parser_version": self.parser_version,
            "redaction_policy_version": self.redaction_policy_version,
            "trust_level": self.trust_level,
            "taint": self.taint,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class HistoricalDiscoveryInventory:
    scanned_roots: int
    scanned_files: int
    skipped_files: int
    estimated_bytes: int
    oldest_mtime: str | None
    newest_mtime: str | None
    risk_classes: dict[str, int]
    source_counts: dict[str, int]
    items: list[HistoricalDiscoveryItem]
    upsert: HistoricalSourceUpsertResult | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "scanned_roots": self.scanned_roots,
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "estimated_bytes": self.estimated_bytes,
            "oldest_mtime": self.oldest_mtime,
            "newest_mtime": self.newest_mtime,
            "risk_classes": self.risk_classes,
            "source_counts": self.source_counts,
            "items": [item.to_json() for item in self.items],
            "upsert": self.upsert.to_json() if self.upsert is not None else None,
        }


async def discover_historical_sources(
    store: HistoricalImportStore,
    *,
    workspace_key: str,
    roots: list[Path],
    source_allowlist: set[str] | None = None,
    source_denylist: set[str] | None = None,
    max_files: int = 500,
    max_bytes: int = 25_000_000,
    preview_only: bool = True,
) -> HistoricalDiscoveryInventory:
    """Read-only historical source inventory without storing raw paths or content."""

    inventory = _discover_roots(
        roots=roots,
        source_allowlist=source_allowlist,
        source_denylist=source_denylist,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    if preview_only or not inventory.items:
        return inventory
    upsert = await store.upsert_sources(
        workspace_key=workspace_key,
        sources=[item.to_source_input() for item in inventory.items],
    )
    return HistoricalDiscoveryInventory(
        scanned_roots=inventory.scanned_roots,
        scanned_files=inventory.scanned_files,
        skipped_files=inventory.skipped_files,
        estimated_bytes=inventory.estimated_bytes,
        oldest_mtime=inventory.oldest_mtime,
        newest_mtime=inventory.newest_mtime,
        risk_classes=inventory.risk_classes,
        source_counts=inventory.source_counts,
        items=inventory.items,
        upsert=upsert,
    )


async def ensure_historical_discovery_schedule(
    scheduler: SchedulerStore,
    *,
    workspace_key: str,
    roots: list[Path],
    interval_seconds: int = DEFAULT_HISTORICAL_DISCOVERY_INTERVAL_SECONDS,
    max_files: int = 500,
    max_bytes: int = 25_000_000,
    enabled: bool = True,
) -> ScheduleUpsertResult | None:
    """Register a bounded low-priority historical discovery cadence."""

    if not roots:
        return None
    return await scheduler.upsert_schedule(
        workspace_key=workspace_key,
        name="historical_import.discover",
        job_kind="historical_import.discover",
        interval_seconds=max(900, interval_seconds),
        next_run_at=datetime.now(UTC),
        payload={
            "workspace_id": workspace_key,
            "max_files": max(1, min(max_files, 10_000)),
            "max_bytes": max(1, min(max_bytes, 1_000_000_000)),
        },
        enabled=enabled,
    )


def _discover_roots(
    *,
    roots: list[Path],
    source_allowlist: set[str] | None,
    source_denylist: set[str] | None,
    max_files: int,
    max_bytes: int,
) -> HistoricalDiscoveryInventory:
    items: list[HistoricalDiscoveryItem] = []
    scanned_roots = 0
    scanned_files = 0
    skipped_files = 0
    estimated_bytes = 0
    mtimes: list[float] = []
    risk_classes: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    max_files = max(1, min(max_files, 10_000))
    max_bytes = max(1, min(max_bytes, 1_000_000_000))

    for root in roots:
        root = root.expanduser()
        if not root.exists() or not root.is_dir():
            skipped_files += 1
            continue
        scanned_roots += 1
        resolved_root = root.resolve()
        for path in sorted(resolved_root.rglob("*")):
            if len(items) >= max_files or estimated_bytes >= max_bytes:
                break
            if not path.is_file() or path.is_symlink():
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(resolved_root)
            except ValueError:
                skipped_files += 1
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                skipped_files += 1
                continue
            stat = path.stat()
            if stat.st_size <= 0:
                skipped_files += 1
                continue
            if estimated_bytes + stat.st_size > max_bytes:
                skipped_files += 1
                break
            source_kind = _source_kind(path)
            if source_allowlist is not None and source_kind not in source_allowlist:
                skipped_files += 1
                continue
            if source_denylist is not None and source_kind in source_denylist:
                skipped_files += 1
                continue
            scanned_files += 1
            estimated_bytes += stat.st_size
            mtimes.append(stat.st_mtime)
            item = _discovery_item(resolved_root, resolved, stat.st_size, stat.st_mtime)
            items.append(item)
            risk = str(item.metadata["risk_class"])
            risk_classes[risk] = risk_classes.get(risk, 0) + 1
            source_counts[item.source_kind] = source_counts.get(item.source_kind, 0) + 1

    oldest = _mtime(min(mtimes)) if mtimes else None
    newest = _mtime(max(mtimes)) if mtimes else None
    return HistoricalDiscoveryInventory(
        scanned_roots=scanned_roots,
        scanned_files=scanned_files,
        skipped_files=skipped_files,
        estimated_bytes=estimated_bytes,
        oldest_mtime=oldest,
        newest_mtime=newest,
        risk_classes=risk_classes,
        source_counts=source_counts,
        items=items,
    )


def _discovery_item(
    root: Path,
    path: Path,
    size: int,
    mtime: float,
) -> HistoricalDiscoveryItem:
    relative = path.relative_to(root).as_posix()
    source_kind = _source_kind(path)
    risk_class = _risk_class(source_kind)
    source_key = f"path-sha256:{sha256_text(path.as_posix())}"
    fingerprint = sha256_json(
        {
            "root": sha256_text(root.as_posix()),
            "relative": relative,
            "size": size,
            "mtime_ns_bucket": int(mtime),
            "discovery_version": HISTORICAL_DISCOVERY_VERSION,
        }
    )
    return HistoricalDiscoveryItem(
        source_kind=source_kind,
        source_key=source_key,
        fingerprint=fingerprint,
        bytes_estimate=size,
        parser_version=HISTORICAL_PARSER_VERSION,
        redaction_policy_version=HISTORICAL_REDACTION_VERSION,
        trust_level="tainted",
        taint=_taint(source_kind),
        metadata={
            "discovery_version": HISTORICAL_DISCOVERY_VERSION,
            "stored_raw_path": False,
            "root_path_hash": sha256_text(root.as_posix()),
            "relative_path_hash": sha256_text(relative),
            "file_name": path.name,
            "suffix": path.suffix.lower(),
            "bytes_estimate": size,
            "mtime": _mtime(mtime),
            "risk_class": risk_class,
            "import_recommendation": _recommendation(source_kind),
        },
        path=path,
    )


def _source_kind(path: Path) -> str:
    name = path.name
    relative = path.as_posix()
    if name == "sessions.json":
        return "session_store"
    if path.suffix == ".jsonl" and "/sessions/" in relative:
        return "transcript"
    if path.suffix == ".jsonl" and "transcript" in relative.lower():
        return "transcript"
    if "trajectory" in relative.lower() and path.suffix.lower() in {".json", ".jsonl"}:
        return "trajectory"
    if name in WORKSPACE_MEMORY_FILES or "/memory/" in relative:
        return "workspace_memory"
    if name in WORKSPACE_CONTEXT_FILES:
        return "workspace_context"
    if name == "TASKFLOW.md" or "taskflow" in relative.lower():
        return "taskflow_record"
    if name == "SKILL.md":
        return "existing_skill"
    if "diagnostic" in relative.lower() or "otel" in relative.lower():
        return "diagnostics_export"
    return "other"


def _risk_class(source_kind: str) -> str:
    if source_kind in {"transcript", "trajectory", "workspace_memory"}:
        return "sensitive"
    if source_kind in {"workspace_context", "plugin_session_state", "queued_injection"}:
        return "policy_sensitive"
    if source_kind in {"diagnostics_export", "session_store"}:
        return "metadata"
    return "mixed"


def _recommendation(source_kind: str) -> str:
    if source_kind in {"transcript", "trajectory", "workspace_memory"}:
        return "parse_with_redaction_and_taint"
    if source_kind == "workspace_context":
        return "inventory_policy_context_only"
    if source_kind == "existing_skill":
        return "inventory_read_only_external_skill"
    return "inventory_first"


def _taint(source_kind: str) -> dict[str, Any]:
    taint: dict[str, Any] = {"historical": True}
    if source_kind in {"transcript", "trajectory"}:
        taint["raw_transcript"] = True
    if source_kind == "workspace_memory":
        taint["memory_poisoning_suspected"] = True
    if source_kind == "workspace_context":
        taint["policy_sensitive"] = True
        taint["external_instruction"] = True
    if source_kind == "existing_skill":
        taint["third_party_skill"] = True
    return taint


def _mtime(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()
