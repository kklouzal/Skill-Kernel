from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autoskill.core.redaction import redact_text
from autoskill.db.historical import (
    HistoricalChunkInput,
    HistoricalChunkRecordResult,
    HistoricalImportRunRecord,
    HistoricalImportStore,
)
from autoskill.services.historical_discovery import (
    HistoricalDiscoveryInventory,
    HistoricalDiscoveryItem,
    discover_historical_sources,
)

HISTORICAL_CHUNKING_VERSION = "historical-chunking.v1"


@dataclass(frozen=True)
class HistoricalImportResult:
    discovery: HistoricalDiscoveryInventory
    run: HistoricalImportRunRecord
    chunks: HistoricalChunkRecordResult
    parsed_sources: int
    skipped_sources: int
    parse_errors: list[dict[str, object]]

    def to_json(self) -> dict[str, object]:
        return {
            "discovery": self.discovery.to_json(),
            "run": self.run.to_json(),
            "chunks": self.chunks.to_json(),
            "parsed_sources": self.parsed_sources,
            "skipped_sources": self.skipped_sources,
            "parse_errors": self.parse_errors,
        }


async def import_historical_sources(
    store: HistoricalImportStore,
    *,
    workspace_key: str,
    roots: list[Path],
    source_allowlist: set[str] | None = None,
    source_denylist: set[str] | None = None,
    max_files: int = 500,
    max_bytes: int = 25_000_000,
    max_chunks: int = 1000,
    idempotency_key: str = "historical-import:manual",
) -> HistoricalImportResult:
    """Parse authorized historical files into redacted, structure-preserving chunks."""

    await store.record_import_run(
        workspace_key=workspace_key,
        run_kind="historical_import",
        idempotency_key=idempotency_key,
        status="running",
        checkpoint={"phase": "discover"},
        stats={},
    )
    discovery = await discover_historical_sources(
        store,
        workspace_key=workspace_key,
        roots=roots,
        source_allowlist=source_allowlist,
        source_denylist=source_denylist,
        max_files=max_files,
        max_bytes=max_bytes,
        preview_only=True,
    )
    parsed_inputs: list[HistoricalChunkInput] = []
    imported_sources = []
    inventory_sources = []
    parse_errors: list[dict[str, object]] = []
    for item in discovery.items:
        if len(parsed_inputs) >= max_chunks:
            inventory_sources.append(item.to_source_input(status="inventory_only"))
            continue
        try:
            item_chunks = _parse_item(item, remaining=max_chunks - len(parsed_inputs))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            parse_errors.append(
                {
                    "source_key": item.source_key,
                    "source_kind": item.source_kind,
                    "error": type(error).__name__,
                }
            )
            inventory_sources.append(
                item.to_source_input(
                    status="inventory_only",
                )
            )
            continue
        if item_chunks:
            parsed_inputs.extend(item_chunks)
            imported_sources.append(item.to_source_input(status="imported"))
        else:
            inventory_sources.append(item.to_source_input(status="inventory_only"))

    if imported_sources or inventory_sources:
        await store.upsert_sources(
            workspace_key=workspace_key,
            sources=[*imported_sources, *inventory_sources],
        )
    chunks = await store.record_chunks(workspace_key=workspace_key, chunks=parsed_inputs)
    run = await store.record_import_run(
        workspace_key=workspace_key,
        run_kind="historical_import",
        idempotency_key=idempotency_key,
        status="completed",
        checkpoint={
            "phase": "completed",
            "scanned_files": discovery.scanned_files,
            "parsed_sources": len(imported_sources),
            "chunks_seen": len(parsed_inputs),
        },
        stats={
            "created_chunks": chunks.created,
            "duplicate_chunks": chunks.skipped,
            "skipped_sources": len(inventory_sources),
            "parse_errors": len(parse_errors),
        },
    )
    return HistoricalImportResult(
        discovery=discovery,
        run=run,
        chunks=chunks,
        parsed_sources=len(imported_sources),
        skipped_sources=len(inventory_sources),
        parse_errors=parse_errors,
    )


def _parse_item(item: HistoricalDiscoveryItem, *, remaining: int) -> list[HistoricalChunkInput]:
    if remaining <= 0 or item.path is None:
        return []
    if item.source_kind == "transcript":
        return _parse_jsonl_transcript(item, remaining=remaining)
    if item.source_kind == "transcript_corpus":
        return _parse_transcript_corpus(item, remaining=remaining)
    if item.source_kind in {"workspace_memory", "workspace_context", "taskflow_record"}:
        return _parse_markdown_sections(item, remaining=remaining)
    if item.source_kind == "existing_skill":
        return _parse_skill_sections(item, remaining=remaining)
    if item.source_kind == "session_store":
        return _parse_session_store(item)
    if item.source_kind in {"trajectory", "diagnostics_export"}:
        return _parse_json_or_jsonl_summary(item, remaining=remaining)
    return []


def _parse_jsonl_transcript(
    item: HistoricalDiscoveryItem,
    *,
    remaining: int,
) -> list[HistoricalChunkInput]:
    assert item.path is not None
    chunks: list[HistoricalChunkInput] = []
    lines = item.path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_index, line in enumerate(lines):
        if len(chunks) >= remaining:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            payload = {"malformed": True, "text": line}
        role = _string(payload.get("role") or payload.get("type") or payload.get("event_type"))
        content = _extract_content(payload)
        if not content:
            continue
        chunks.append(
            _chunk(
                item,
                item_key=f"{item.metadata['relative_path_hash']}#line-{line_index + 1}",
                chunk_index=line_index,
                text=f"{role or 'transcript'}: {content}",
                chunk_kind="transcript_turn",
                taint_extra={"raw_transcript": True, "compaction_summary": _is_summary(payload)},
                metadata={
                    "line_start": line_index + 1,
                    "line_end": line_index + 1,
                    "record_type": role or "unknown",
                    "chunking_version": HISTORICAL_CHUNKING_VERSION,
                    "lossy": bool(payload.get("summary") or payload.get("compaction")),
                },
            )
        )
    return chunks


def _parse_markdown_sections(
    item: HistoricalDiscoveryItem,
    *,
    remaining: int,
) -> list[HistoricalChunkInput]:
    assert item.path is not None
    text = item.path.read_text(encoding="utf-8", errors="replace")
    sections = _markdown_sections(text)
    chunks: list[HistoricalChunkInput] = []
    for index, (heading, body, start_line, end_line) in enumerate(sections[:remaining]):
        if not body.strip():
            continue
        chunks.append(
            _chunk(
                item,
                item_key=f"{item.metadata['relative_path_hash']}#section-{index}",
                chunk_index=index,
                text=f"{heading}\n{body}".strip(),
                chunk_kind=f"{item.source_kind}_section",
                taint_extra=_section_taint(item, body),
                metadata={
                    "heading": heading,
                    "line_start": start_line,
                    "line_end": end_line,
                    "chunking_version": HISTORICAL_CHUNKING_VERSION,
                    "lossy": False,
                },
            )
        )
    return chunks


def _parse_skill_sections(
    item: HistoricalDiscoveryItem,
    *,
    remaining: int,
) -> list[HistoricalChunkInput]:
    chunks = _parse_markdown_sections(item, remaining=remaining)
    return [
        HistoricalChunkInput(
            source_kind=chunk.source_kind,
            source_key=chunk.source_key,
            fingerprint=chunk.fingerprint,
            item_key=chunk.item_key,
            chunk_index=chunk.chunk_index,
            redacted_text=chunk.redacted_text,
            parser_version=chunk.parser_version,
            redaction_policy_version=chunk.redaction_policy_version,
            chunk_kind="existing_skill_section",
            token_estimate=chunk.token_estimate,
            trust_level=chunk.trust_level,
            taint={**(chunk.taint or {}), "third_party_skill": True},
            metadata={**(chunk.metadata or {}), "external_skill_read_only": True},
        )
        for chunk in chunks
    ]


def _parse_session_store(item: HistoricalDiscoveryItem) -> list[HistoricalChunkInput]:
    assert item.path is not None
    data = json.loads(item.path.read_text(encoding="utf-8", errors="replace"))
    sessions = data.get("sessions") if isinstance(data, dict) else None
    count = len(sessions) if isinstance(sessions, list) else 0
    return [
        _chunk(
            item,
            item_key=f"{item.metadata['relative_path_hash']}#metadata",
            chunk_index=0,
            text=f"Session metadata store discovered with {count} session records.",
            chunk_kind="session_metadata",
            taint_extra={},
            metadata={
                "session_count": count,
                "chunking_version": HISTORICAL_CHUNKING_VERSION,
                "metadata_only": True,
            },
        )
    ]


def _parse_json_or_jsonl_summary(
    item: HistoricalDiscoveryItem,
    *,
    remaining: int,
) -> list[HistoricalChunkInput]:
    assert item.path is not None
    text = item.path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    chunks: list[HistoricalChunkInput] = []
    for index, payload in enumerate(_json_payloads(text, lines)):
        if len(chunks) >= remaining:
            break
        content = _extract_content(payload) or _json_summary(payload)
        if not content:
            continue
        chunks.append(
            _chunk(
                item,
                item_key=f"{item.metadata['relative_path_hash']}#record-{index}",
                chunk_index=index,
                text=content,
                chunk_kind=f"{item.source_kind}_record",
                taint_extra={"tool_result": item.source_kind == "trajectory"},
                metadata={
                    "record_index": index,
                    "chunking_version": HISTORICAL_CHUNKING_VERSION,
                    "lossy": False,
                },
            )
        )
    return chunks


def _parse_transcript_corpus(
    item: HistoricalDiscoveryItem,
    *,
    remaining: int,
) -> list[HistoricalChunkInput]:
    assert item.path is not None
    name = item.path.name
    if name == "transcript.jsonl":
        chunks = _parse_jsonl_transcript(item, remaining=remaining)
        return [
            HistoricalChunkInput(
                source_kind=chunk.source_kind,
                source_key=chunk.source_key,
                fingerprint=chunk.fingerprint,
                item_key=chunk.item_key,
                chunk_index=chunk.chunk_index,
                redacted_text=chunk.redacted_text,
                parser_version=chunk.parser_version,
                redaction_policy_version=chunk.redaction_policy_version,
                chunk_kind="transcript_corpus_turn",
                token_estimate=chunk.token_estimate,
                trust_level=chunk.trust_level,
                taint={**(chunk.taint or {}), "transcript_corpus": True},
                metadata={
                    **(chunk.metadata or {}),
                    "transcript_corpus_file": "transcript.jsonl",
                    "confidence": "direct_transcript",
                },
            )
            for chunk in chunks
        ]
    if name == "summary.md":
        chunks = _parse_markdown_sections(item, remaining=remaining)
        return [
            HistoricalChunkInput(
                source_kind=chunk.source_kind,
                source_key=chunk.source_key,
                fingerprint=chunk.fingerprint,
                item_key=chunk.item_key,
                chunk_index=chunk.chunk_index,
                redacted_text=chunk.redacted_text,
                parser_version=chunk.parser_version,
                redaction_policy_version=chunk.redaction_policy_version,
                chunk_kind="transcript_corpus_summary",
                token_estimate=chunk.token_estimate,
                trust_level=chunk.trust_level,
                taint={
                    **(chunk.taint or {}),
                    "transcript_corpus": True,
                    "compaction_summary": True,
                },
                metadata={
                    **(chunk.metadata or {}),
                    "transcript_corpus_file": "summary.md",
                    "confidence": "derived_summary",
                    "lossy": True,
                },
            )
            for chunk in chunks
        ]
    if name == "metadata.json":
        payload = json.loads(item.path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(payload, dict):
            return []
        summary = _transcript_corpus_metadata_summary(payload)
        if not summary:
            return []
        return [
            _chunk(
                item,
                item_key=f"{item.metadata['relative_path_hash']}#metadata",
                chunk_index=0,
                text=summary,
                chunk_kind="transcript_corpus_metadata",
                taint_extra={"transcript_corpus": True},
                metadata={
                    "chunking_version": HISTORICAL_CHUNKING_VERSION,
                    "metadata_only": True,
                    "transcript_corpus_file": "metadata.json",
                    "confidence": "metadata_only",
                    "lossy": True,
                    "safe_keys": sorted(_transcript_corpus_metadata(payload)),
                },
            )
        ]
    return []


def _transcript_corpus_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    safe_keys = {
        "selector",
        "date",
        "source",
        "title",
        "session_id",
        "session_key",
        "agent_id",
        "start_time",
        "stop_time",
        "started_at",
        "ended_at",
        "transcript_path",
        "summary_path",
    }
    return {key: value for key, value in payload.items() if key in safe_keys and value}


def _transcript_corpus_metadata_summary(payload: dict[str, Any]) -> str:
    metadata = _transcript_corpus_metadata(payload)
    if not metadata:
        return ""
    return "Transcript corpus metadata: " + json.dumps(metadata, sort_keys=True)


def _chunk(
    item: HistoricalDiscoveryItem,
    *,
    item_key: str,
    chunk_index: int,
    text: str,
    chunk_kind: str,
    taint_extra: dict[str, Any],
    metadata: dict[str, Any],
) -> HistoricalChunkInput:
    redacted = redact_text(text)
    return HistoricalChunkInput(
        source_kind=item.source_kind,
        source_key=item.source_key,
        fingerprint=item.fingerprint,
        item_key=item_key,
        chunk_index=chunk_index,
        redacted_text=redacted,
        parser_version=item.parser_version,
        redaction_policy_version=item.redaction_policy_version,
        chunk_kind=chunk_kind,
        token_estimate=max(1, (len(redacted) + 3) // 4),
        trust_level=item.trust_level,
        taint={**item.taint, **taint_extra},
        metadata={**metadata, "source_path_stored": False},
    )


def _markdown_sections(text: str) -> list[tuple[str, str, int, int]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str], int]] = []
    current_heading = "document"
    current_lines: list[str] = []
    current_start = 1
    for line_no, line in enumerate(lines, start=1):
        if line.startswith("#"):
            if current_lines:
                sections.append((current_heading, current_lines, current_start))
            current_heading = line.strip("# ").strip() or "section"
            current_lines = []
            current_start = line_no
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, current_lines, current_start))
    if not sections and text.strip():
        sections.append(("document", lines, 1))
    return [
        (heading, "\n".join(body).strip(), start, start + len(body))
        for heading, body, start in sections
    ]


def _json_payloads(text: str, lines: list[str]) -> Iterable[dict[str, Any]]:
    if not text.strip():
        return []
    if len(lines) > 1:
        payloads = []
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
        if payloads:
            return payloads
    payload = json.loads(text)
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _extract_content(payload: dict[str, Any]) -> str:
    for key in ("content", "message", "text", "summary", "body", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _json_summary(payload)


def _json_summary(payload: dict[str, Any]) -> str:
    safe_keys = {
        key: value
        for key, value in payload.items()
        if key in {"event_type", "type", "role", "status", "name", "model", "error_class"}
    }
    return json.dumps(safe_keys, sort_keys=True) if safe_keys else ""


def _section_taint(item: HistoricalDiscoveryItem, body: str) -> dict[str, Any]:
    taint: dict[str, Any] = {}
    lowered = body.lower()
    if item.source_kind in {"workspace_memory", "workspace_context"} and any(
        marker in lowered
        for marker in ("always ", "never ", "must ", "ignore previous", "system prompt")
    ):
        taint["external_instruction"] = True
        taint["memory_poisoning_suspected"] = True
    return taint


def _is_summary(payload: dict[str, Any]) -> bool:
    return bool(payload.get("summary") or payload.get("compaction"))


def _string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
