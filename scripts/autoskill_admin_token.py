from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TOKEN_KEYS = (
    "SKILLKERNEL_ADMIN_TOKEN",
    "AUTOSKILL_WEB_ADMIN_TOKEN",
    "AUTOSKILL_CONTROL_TOKEN",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show or verify the SkillKernel Observatory admin token.",
    )
    parser.add_argument("--show", action="store_true", help="print the full token")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the selected token against the local sidecar",
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8765/admin/api/v1",
        help="admin API base URL used by --check",
    )
    args = parser.parse_args(argv)

    token, source = resolve_token(Path.cwd())
    if not token:
        print("No admin token found in the live core container, environment, or .env.")
        return 1

    if args.check and not verify_token(args.api_base, token):
        print(f"token_source={source}")
        print("status=rejected")
        return 2

    print(f"token_source={source}")
    print(f"token={token if args.show else mask_token(token)}")
    if args.check:
        print("status=accepted")
    return 0


def resolve_token(repo_root: Path) -> tuple[str | None, str]:
    token = _token_from_container(repo_root)
    if token:
        return token, "compose:core"
    token = _token_from_environ(os.environ)
    if token:
        return token, "environment"
    dotenv = repo_root / ".env"
    token = _token_from_dotenv(dotenv)
    if token:
        return token, str(dotenv)
    return None, "missing"


def mask_token(token: str) -> str:
    if len(token) <= 12:
        return "*" * len(token)
    return f"{token[:6]}...{token[-6:]} ({len(token)} chars)"


def verify_token(api_base: str, token: str) -> bool:
    url = f"{api_base.rstrip('/')}/summary?workspace_id=dev-01&window_minutes=5"
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def _token_from_container(repo_root: Path) -> str | None:
    code = (
        "from autoskill.core.config import get_settings;"
        "s=get_settings();"
        "print(s.web_admin_token or s.control_token or '')"
    )
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "core", "python", "-c", code],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _token_from_environ(environ: os._Environ[str] | dict[str, str]) -> str | None:
    for key in TOKEN_KEYS:
        value = environ.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _token_from_dotenv(path: Path) -> str | None:
    if not path.exists():
        return None
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = _parse_dotenv_line(line)
        if key:
            values[key] = value
    return _token_from_environ(values)


def _parse_dotenv_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None, ""
    key, value = stripped.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key.strip(), value.strip()


if __name__ == "__main__":
    sys.exit(main())
