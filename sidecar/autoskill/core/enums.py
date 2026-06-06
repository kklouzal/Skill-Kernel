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
    OBSERVED_PATTERN = "observed_pattern"
    CANDIDATE_CLUSTER = "candidate_cluster"
    EPHEMERAL_CANDIDATE = "ephemeral_candidate"
    TRIAL_CANDIDATE = "trial_candidate"
    VALIDATED_CANDIDATE = "validated_candidate"
    ACTIVE = "active"
    CANARY_ACTIVE = "canary_active"
    ARCHIVED = "archived"
    FROZEN = "frozen"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    EXTERNAL_READONLY = "external_readonly"
    CANDIDATE = "candidate"
    LEGACY_CANDIDATE = "candidate"
    QUARANTINED = "quarantined"
    DELETED = "deleted"


SPEC_LIFECYCLE_STATES = tuple(
    state.value
    for state in (
        LifecycleState.OBSERVED_PATTERN,
        LifecycleState.CANDIDATE_CLUSTER,
        LifecycleState.EPHEMERAL_CANDIDATE,
        LifecycleState.TRIAL_CANDIDATE,
        LifecycleState.VALIDATED_CANDIDATE,
        LifecycleState.ACTIVE,
        LifecycleState.CANARY_ACTIVE,
        LifecycleState.ARCHIVED,
        LifecycleState.FROZEN,
        LifecycleState.REVOKED,
        LifecycleState.SUPERSEDED,
        LifecycleState.EXTERNAL_READONLY,
    )
)

LEGACY_LIFECYCLE_STATES = tuple(
    state.value
    for state in (
        LifecycleState.LEGACY_CANDIDATE,
        LifecycleState.QUARANTINED,
        LifecycleState.DELETED,
    )
)

CANDIDATE_REVIEW_LIFECYCLE_STATES = tuple(
    state.value
    for state in (
        LifecycleState.OBSERVED_PATTERN,
        LifecycleState.CANDIDATE_CLUSTER,
        LifecycleState.EPHEMERAL_CANDIDATE,
        LifecycleState.TRIAL_CANDIDATE,
        LifecycleState.VALIDATED_CANDIDATE,
        LifecycleState.LEGACY_CANDIDATE,
    )
)

PROPOSAL_GATE_LIFECYCLE_STATES = tuple(
    state.value
    for state in (
        LifecycleState.EPHEMERAL_CANDIDATE,
        LifecycleState.TRIAL_CANDIDATE,
        LifecycleState.VALIDATED_CANDIDATE,
        LifecycleState.LEGACY_CANDIDATE,
    )
)

RUNTIME_VISIBLE_LIFECYCLE_STATES = tuple(
    state.value
    for state in (
        LifecycleState.ACTIVE,
        LifecycleState.CANARY_ACTIVE,
    )
)
