from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|credential|authorization|cookie|session)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b"),
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
REDACTED = "[REDACTED]"


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    return redacted


def redact_payload(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        out: MutableMapping[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_RE.search(key_text):
                out[key_text] = REDACTED
            else:
                out[key_text] = redact_payload(item)
        return dict(out)
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [redact_payload(item) for item in value]
    return value

