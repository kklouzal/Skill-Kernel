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
HARMFUL_CAPABILITY_RULES: tuple[tuple[FindingSeverity, str, str, re.Pattern[str]], ...] = (
    (
        FindingSeverity.CRITICAL,
        "harmful-cyber-capability",
        "hazardous cyber or malware workflow capability is forbidden",
        re.compile(
            r"(?is)\b("
            r"phish(?:ing)?|credential\s+(?:stuffing|spraying|theft|harvest(?:ing)?)|"
            r"steal\s+(?:session\s+)?cookies?|clone\s+login\s+pages?|"
            r"malware|ransomware|keylogger|reverse\s+shell|privilege\s+escalation|"
            r"exploit\s+(?:chain|kit|payload)|bypass\s+(?:auth(?:entication)?|2fa|mfa)"
            r")\b"
        ),
    ),
    (
        FindingSeverity.CRITICAL,
        "privacy-violating-capability",
        "privacy-violating data collection or credential-harvesting capability is forbidden",
        re.compile(
            r"(?is)\b("
            r"scrape|harvest|dump|exfiltrate|collect|deanonymi[sz]e|reidentify"
            r")\b.{0,80}\b("
            r"pii|personal\s+data|private\s+messages?|browser\s+(?:cookies?|history)|"
            r"contacts?|location\s+history|credentials?|passwords?|tokens?"
            r")\b"
        ),
    ),
    (
        FindingSeverity.ERROR,
        "fraud-capability",
        "fraud, impersonation, or forged-document workflow capability is forbidden",
        re.compile(
            r"(?is)\b("
            r"forge|fake|fabricate|counterfeit|impersonate|spoof|evade"
            r")\b.{0,80}\b("
            r"invoices?|receipts?|identity|kyc|passport|driver'?s?\s+license|"
            r"bank\s+statement|chargeback|tax\s+document|signature"
            r")\b"
        ),
    ),
    (
        FindingSeverity.CRITICAL,
        "coercive-surveillance-capability",
        "coercive surveillance, stalking, blackmail, or harassment capability is forbidden",
        re.compile(
            r"(?is)\b("
            r"stalk|doxx?|blackmail|harass|coerce|covertly\s+(?:track|monitor|record)|"
            r"track\s+location\s+without\s+consent|intercept\s+(?:messages?|calls?)"
            r")\b"
        ),
    ),
)
HARMFUL_CAPABILITY_BOUNDARY = re.compile(
    r"(?is)\b("
    r"never|do\s+not|don't|must\s+not|not\s+for|forbid(?:den)?|avoid|"
    r"reject|block|fail\s+(?:closed|when)|stop\s+(?:if|when)"
    r")\b.{0,120}\b("
    r"phish|credential\s+(?:stuffing|spraying|theft|harvest)|malware|ransomware|"
    r"keylogger|reverse\s+shell|privilege\s+escalation|exploit|bypass\s+(?:auth|2fa|mfa)|"
    r"pii|personal\s+data|private\s+messages?|browser\s+(?:cookies?|history)|"
    r"forge|fake|fabricate|counterfeit|impersonate|spoof|invoice|receipt|identity|"
    r"kyc|passport|driver'?s?\s+license|bank\s+statement|chargeback|tax\s+document|"
    r"stalk|doxx?|blackmail|harass|coerce|covertly\s+(?:track|monitor|record)|"
    r"track\s+location\s+without\s+consent|intercept\s+(?:messages?|calls?)"
    r")\b"
)
UNSAFE_BOUNDARY_INVERSION = re.compile(
    r"(?is)\b(?:never|do\s+not|don't|must\s+not)\b.{0,40}\b(refuse|block|reject|stop)\b"
)
BUNDLE_SAFETY_BOUNDARY = re.compile(
    r"(?is)\b(never|do\s+not|don't|must\s+not|forbid(?:den)?|avoid)\b.{0,100}"
    r"\b(secret|token|password|api[_ -]?key|credential|authorization|ssh[_ -]?key)s?\b"
)
BUNDLE_SENSITIVE_SOURCE = re.compile(
    r"(?is)\b(secret|token|password|api[_ -]?key|credential|authorization|ssh[_ -]?key)s?\b"
)
BUNDLE_EXFIL_ACTION = re.compile(
    r"(?is)\b(upload|send|post|exfiltrate|dump|log|copy|collect)\b"
)


def scan_text(text: str) -> list[ScannerFinding]:
    findings: list[ScannerFinding] = []
    normalized_text = _capability_scan_text(text)
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
    for severity, code, message, pattern in HARMFUL_CAPABILITY_RULES:
        if pattern.search(normalized_text):
            findings.append(ScannerFinding(severity, code, message))
    return _dedupe_findings(findings)


def scan_text_bundle(parts: list[str]) -> list[ScannerFinding]:
    """Scan a co-loadable rendered context bundle, not only each artifact alone."""

    findings: list[ScannerFinding] = []
    for part in parts:
        findings.extend(scan_text(part))
    combined = "\n\n--- autoskill-context-boundary ---\n\n".join(parts)
    findings.extend(scan_text(combined))
    chain_text = BUNDLE_SAFETY_BOUNDARY.sub("", combined)
    if (
        len(parts) > 1
        and BUNDLE_SENSITIVE_SOURCE.search(chain_text)
        and BUNDLE_EXFIL_ACTION.search(chain_text)
    ):
        findings.append(
            ScannerFinding(
                FindingSeverity.CRITICAL,
                "bundle-secret-exfiltration-chain",
                "co-loaded context forms a potential secret exfiltration chain",
            )
        )
    return _dedupe_findings(findings)


def has_blocking_findings(findings: list[ScannerFinding]) -> bool:
    return any(f.severity in {FindingSeverity.ERROR, FindingSeverity.CRITICAL} for f in findings)


def _capability_scan_text(text: str) -> str:
    boundary_stripped = HARMFUL_CAPABILITY_BOUNDARY.sub("", text)
    return UNSAFE_BOUNDARY_INVERSION.sub(
        "unsafe_boundary_inversion",
        boundary_stripped,
    )


def _dedupe_findings(findings: list[ScannerFinding]) -> list[ScannerFinding]:
    seen: set[tuple[FindingSeverity, str, str]] = set()
    deduped: list[ScannerFinding] = []
    for finding in findings:
        key = (finding.severity, finding.code, finding.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped
