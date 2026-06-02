from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ScannerFinding:
    severity: FindingSeverity
    code: str
    message: str


BIDI_CLASSES = {"RLO", "LRO", "RLE", "LRE", "PDF", "RLI", "LRI", "FSI", "PDI"}
SECRET_LIKE = re.compile(
    r"(?i)("
    r"(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*[A-Za-z0-9._~+/=-]{8,}"
    r"|bearer\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|sk-[A-Za-z0-9_-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9_]{20,}"
    r")"
)
FETCH_EXEC = re.compile(
    r"(?is)(curl|wget|fetch|Invoke-WebRequest).{0,120}(\|\s*(sh|bash|python)|eval|exec)"
)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
POLICY_OVERRIDE = re.compile(
    r"(?is)\b(ignore|bypass|override|discard)\b.{0,80}"
    r"\b(system|developer|safety|policy|instruction|guardrail|approval|sandbox)\b"
)
CREDENTIAL_EXFILTRATION = re.compile(
    r"(?is)\b(print|dump|exfiltrate|send|upload|post|log|copy|collect)\b.{0,100}"
    r"\b(secret|token|password|api[_ -]?key|credential|authorization|ssh[_ -]?key)\b"
)
DESTRUCTIVE_HOST_COMMAND = re.compile(
    r"(?is)(\brm\s+-rf\s+/(?:\s|$)|\bmkfs(?:\.\w+)?\b|"
    r"\bdd\s+if=.{0,80}\s+of=/dev/|\bchmod\s+-R\s+777\s+/|\bchown\s+-R\b.{0,80}\s+/)"
)
SENSITIVE_FILE_HARVEST = re.compile(
    r"(?is)\b(read|cat|open|scan|index|embed|upload|copy)\b.{0,100}"
    r"(~?/\.ssh\b|/etc/shadow\b|/etc/passwd\b|\.env\b|credentials?\.(json|yaml|yml)\b)"
)


def scan_text(text: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    if HTML_COMMENT.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.ERROR,
                "hidden-markdown-comment",
                "hidden Markdown comments are forbidden in generated artifacts",
            )
        )
    if any(unicodedata.bidirectional(ch) in BIDI_CLASSES for ch in text):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "bidi-control",
                "bidirectional control characters are forbidden",
            )
        )
    if any(unicodedata.category(ch) == "Cf" for ch in text):
        findings.append(
            ScannerFinding(
                FindingSeverity.ERROR,
                "invisible-format-control",
                "invisible Unicode format controls are forbidden",
            )
        )
    if SECRET_LIKE.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "secret-like-material",
                "secret-like material is forbidden in generated artifacts",
            )
        )
    if FETCH_EXEC.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "dynamic-fetch-exec",
                "dynamic fetch-exec patterns are forbidden",
            )
        )
    if POLICY_OVERRIDE.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "policy-override-instruction",
                "policy, approval, sandbox, or instruction override language is forbidden",
            )
        )
    if CREDENTIAL_EXFILTRATION.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "credential-exfiltration",
                "credential or secret exfiltration instructions are forbidden",
            )
        )
    if DESTRUCTIVE_HOST_COMMAND.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "destructive-host-command",
                "destructive host-level command patterns are forbidden",
            )
        )
    if SENSITIVE_FILE_HARVEST.search(text):
        findings.append(
            ScannerFinding(
                FindingSeverity.ERROR,
                "sensitive-file-harvest",
                "sensitive file harvesting instructions are forbidden",
            )
        )
    return findings


def has_blocking_findings(findings: list[ScannerFinding]) -> bool:
    return any(f.severity in {FindingSeverity.ERROR, FindingSeverity.CRITICAL} for f in findings)
