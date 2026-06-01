from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autoskill.core.hashing import sha256_text
from autoskill.db.external_skills import ExternalSkillInput, ExternalSkillStore
from autoskill.db.scheduler import SchedulerStore, ScheduleUpsertResult
from autoskill.services.scanner import has_blocking_findings, scan_text

SAFE_SLUG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
DEFAULT_EXTERNAL_SKILL_SCAN_INTERVAL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class ExternalSkillScanResult:
    scanned_roots: int
    discovered: int
    created: int
    updated: int
    skills: list[dict[str, object]]

    def to_json(self) -> dict[str, object]:
        return {
            "scanned_roots": self.scanned_roots,
            "discovered": self.discovered,
            "created": self.created,
            "updated": self.updated,
            "skills": self.skills,
        }


async def scan_external_skill_roots(
    store: ExternalSkillStore,
    *,
    workspace_key: str,
    roots: list[Path],
    source: str = "workspace-skill-root",
    limit: int = 250,
) -> ExternalSkillScanResult:
    """Inventory external skill roots without persisting raw filesystem paths."""

    inputs: list[ExternalSkillInput] = []
    scanned_roots = 0
    for root in roots[: max(0, limit)]:
        scanned_roots += 1
        inputs.extend(_scan_root(root, source=source, remaining=max(0, limit - len(inputs))))
        if len(inputs) >= limit:
            break

    result = await store.upsert_external_skills(
        workspace_key=workspace_key,
        skills=inputs,
    )
    return ExternalSkillScanResult(
        scanned_roots=scanned_roots,
        discovered=len(inputs),
        created=result.created,
        updated=result.updated,
        skills=[skill.to_json() for skill in result.skills],
    )


async def ensure_external_skill_scan_schedule(
    scheduler: SchedulerStore,
    *,
    workspace_key: str,
    external_skill_roots: list[Path],
    interval_seconds: int = DEFAULT_EXTERNAL_SKILL_SCAN_INTERVAL_SECONDS,
    source: str = "workspace-skill-root",
    limit: int = 250,
    enabled: bool = True,
) -> ScheduleUpsertResult | None:
    """Register durable scan cadence without persisting raw external root paths."""

    if not external_skill_roots:
        return None
    return await scheduler.upsert_schedule(
        workspace_key=workspace_key,
        name="external-skills.scan",
        job_kind="external_skills.scan",
        interval_seconds=max(300, interval_seconds),
        next_run_at=datetime.now(UTC),
        payload={
            "workspace_id": workspace_key,
            "source": source,
            "limit": max(1, min(limit, 1000)),
        },
        enabled=enabled,
    )


def _scan_root(root: Path, *, source: str, remaining: int) -> list[ExternalSkillInput]:
    if remaining <= 0:
        return []
    root = root.expanduser()
    if not root.exists() or not root.is_dir():
        return []

    discovered: list[ExternalSkillInput] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        if len(discovered) >= remaining:
            break
        skill_dir = skill_md.parent
        slug = skill_dir.name
        if not SAFE_SLUG.fullmatch(slug):
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        frontmatter = _parse_frontmatter(text)
        findings = scan_text(text)
        blocking = has_blocking_findings(findings)
        discovered.append(
            ExternalSkillInput(
                source=source,
                root_path_hash=sha256_text(skill_dir.resolve().as_posix()),
                slug=slug,
                file_hash=sha256_text(text),
                name=_string_or_none(frontmatter.get("name")) or slug,
                description=_string_or_none(frontmatter.get("description")),
                frontmatter=_public_frontmatter(frontmatter),
                status="quarantined" if blocking else "visible",
                risk_summary={
                    "scanner_status": "blocked" if blocking else "passed",
                    "scanner_codes": [finding.code for finding in findings],
                    "stored_raw_root_path": False,
                },
            )
        )
    return discovered


def _parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    parsed: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"')
        if key in {"name", "description"}:
            parsed[key] = value
    return parsed


def _public_frontmatter(frontmatter: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in frontmatter.items()
        if key in {"name", "description"} and isinstance(value, str)
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
