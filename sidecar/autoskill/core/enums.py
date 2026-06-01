from enum import StrEnum


class AutonomyMode(StrEnum):
    OBSERVE_ONLY = "observe_only"
    PROPOSE_ONLY = "propose_only"
    AUTO_ARCHIVE_ONLY = "auto_archive_only"
    AUTONOMOUS_GUARDED = "autonomous_guarded"
    AUTONOMOUS_MAX = "autonomous_max"
    FROZEN = "frozen"


class TrustClass(StrEnum):
    SYSTEM_OWNED = "system_owned"
    OPERATOR_CONFIGURED = "operator_configured"
    AUTOSKILL_GENERATED = "autoskill_generated"
    USER_INSTRUCTION = "user_instruction"
    AGENT_OUTPUT = "agent_output"
    TOOL_OUTPUT = "tool_output"
    EXTERNAL_CONTENT = "external_content"
    THIRD_PARTY_SKILL = "third_party_skill"


class RedactionState(StrEnum):
    RAW = "raw"
    REDACTED = "redacted"


class EvidenceMaturity(StrEnum):
    OBSERVED = "observed"
    RECURRING = "recurring"
    CONTRASTIVE = "contrastive"
    INTERVENTION_VALIDATED = "intervention_validated"
    REGRESSION_VALIDATED = "regression_validated"
    CANARIED = "canaried"
    PRODUCTION_VERIFIED = "production_verified"
    REVOKED = "revoked"


class LifecycleState(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"
    FROZEN = "frozen"
    SUPERSEDED = "superseded"
    DELETED = "deleted"

