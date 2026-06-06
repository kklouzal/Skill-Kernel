#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    role = sys.argv[1] if len(sys.argv) > 1 else "core"
    if role != "core":
        print(f"unsupported healthcheck role: {role}", file=sys.stderr)
        return 2
    port = os.environ.get("SKILLKERNEL_CORE_PORT", "8765")
    url = os.environ.get("SKILLKERNEL_CORE_HEALTH_URL", f"http://127.0.0.1:{port}/v1/health")
    try:
        with urlopen(url, timeout=3) as response:
            if 200 <= response.status < 300:
                return 0
            print(f"unhealthy status: {response.status}", file=sys.stderr)
            return 1
    except (OSError, URLError) as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
