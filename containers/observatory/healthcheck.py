#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from http.client import HTTPConnection, HTTPSConnection
from ipaddress import ip_address
from urllib.parse import urlsplit


def _is_loopback_host(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


def _healthcheck_headers(hostname: str, path: str) -> dict[str, str]:
    explicit_token = os.environ.get("SKILLKERNEL_OBSERVATORY_HEALTH_BEARER_TOKEN")
    if explicit_token:
        return {"Authorization": f"Bearer {explicit_token}"}

    if not path.startswith("/admin/api/v1/health/ready") or not _is_loopback_host(hostname):
        return {}

    admin_token = os.environ.get("SKILLKERNEL_ADMIN_TOKEN") or os.environ.get(
        "AUTOSKILL_WEB_ADMIN_TOKEN"
    )
    if not admin_token:
        return {}
    return {"Authorization": f"Bearer {admin_token}"}


def main() -> int:
    role = sys.argv[1] if len(sys.argv) > 1 else "observatory"
    if role != "observatory":
        print(f"unsupported healthcheck role: {role}", file=sys.stderr)
        return 2
    port = os.environ.get("SKILLKERNEL_OBSERVATORY_PORT", "8757")
    url = os.environ.get("SKILLKERNEL_OBSERVATORY_HEALTH_URL", f"http://127.0.0.1:{port}/healthz")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print(f"unsupported healthcheck URL: {url}", file=sys.stderr)
        return 2
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    connection_cls = HTTPSConnection if parsed.scheme == "https" else HTTPConnection
    connection: HTTPConnection | HTTPSConnection | None = None
    try:
        connection = connection_cls(parsed.hostname, parsed.port, timeout=3)
        connection.request("GET", path, headers=_healthcheck_headers(parsed.hostname, path))
        response = connection.getresponse()
        if 200 <= response.status < 300:
            return 0
        print(f"unhealthy status: {response.status}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
