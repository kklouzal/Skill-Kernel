from __future__ import annotations

from pathlib import Path


class PathContainmentError(ValueError):
    pass


def resolve_contained(root: Path, relative_path: str) -> Path:
    if relative_path.startswith("/") or "\x00" in relative_path:
        raise PathContainmentError("path must be relative and non-null")
    root_resolved = root.resolve()
    target = (root_resolved / relative_path).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise PathContainmentError(f"path escapes root: {relative_path}")
    return target


def stage_text(root: Path, relative_path: str, content: str, *, overwrite: bool = False) -> Path:
    target = resolve_contained(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)
    return target

