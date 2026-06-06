-- SkillKernel / autoskill bootstrap schema.
-- v1 uses one database and one autoskill schema. Do not create per-skill schemas.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS autoskill;

CREATE TABLE IF NOT EXISTS autoskill.workspaces (
  workspace_id uuid PRIMARY KEY,
  external_key text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  config jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS autoskill.raw_evidence_records (
  raw_evidence_record_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_event_hash text NOT NULL,
  source_kind text NOT NULL,
  source_id text,
  session_id text,
  turn_id text,
  raw_kind text NOT NULL CHECK (raw_kind IN (
    'user_prompt',
    'agent_message',
    'system_prompt',
    'model_input',
    'model_output',
    'tool_params',
    'tool_result',
    'transcript_window',
    'trajectory_window',
    'memory_file',
    'context_file',
    'diagnostic_raw_stream',
    'other'
  )),
  content_hash text NOT NULL,
  sensitivity_level text NOT NULL CHECK (sensitivity_level IN (
    'public',
    'internal',
    'private',
    'secret_candidate',
    'credential_candidate',
    'unknown'
  )),
  taint text[] NOT NULL DEFAULT '{}',
  retention_until timestamptz NOT NULL,
  encryption_key_id text NOT NULL,
  ciphertext bytea,
  external_ciphertext_ref text,
  compression text NOT NULL DEFAULT 'none',
  capture_policy_id text NOT NULL,
  redaction_policy_id text NOT NULL,
  access_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  UNIQUE (workspace_id, source_event_hash, raw_kind, content_hash),
  CHECK ((ciphertext IS NOT NULL) OR (external_ciphertext_ref IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS raw_evidence_records_workspace_retention_idx
  ON autoskill.raw_evidence_records(workspace_id, retention_until, revoked_at);

CREATE INDEX IF NOT EXISTS raw_evidence_records_workspace_kind_idx
  ON autoskill.raw_evidence_records(workspace_id, raw_kind, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.raw_evidence_access_log (
  raw_access_id uuid PRIMARY KEY,
  raw_evidence_record_id uuid NOT NULL REFERENCES autoskill.raw_evidence_records(raw_evidence_record_id),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  job_id uuid,
  purpose text NOT NULL,
  accessor_kind text NOT NULL CHECK (accessor_kind IN (
    'core_job',
    'llm_profile',
    'operator_ui',
    'retention_job',
    'scanner',
    'evaluator'
  )),
  model_profile_id uuid,
  exposure_level text NOT NULL CHECK (exposure_level IN (
    'metadata',
    'redacted',
    'secret_masked_raw',
    'raw_local_only',
    'raw_allowed_hosted'
  )),
  decision text NOT NULL CHECK (decision IN (
    'allowed',
    'denied',
    'masked',
    'expired',
    'revoked'
  )),
  reason_code text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS raw_evidence_access_log_record_idx
  ON autoskill.raw_evidence_access_log(raw_evidence_record_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.declassification_reports (
  declassification_report_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_raw_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  output_kind text NOT NULL CHECK (output_kind IN (
    'redacted_intent',
    'semantic_summary',
    'operational_fact',
    'memory_candidate',
    'replay_episode',
    'topology_hint',
    'rejected'
  )),
  redaction_policy_id text NOT NULL,
  model_profile_id uuid,
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  privacy_risk numeric NOT NULL CHECK (privacy_risk >= 0 AND privacy_risk <= 1),
  output jsonb NOT NULL,
  scanner_status text NOT NULL CHECK (scanner_status IN (
    'passed',
    'failed',
    'quarantined',
    'not_run'
  )),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS declassification_reports_workspace_created_idx
  ON autoskill.declassification_reports(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.autonomous_adjudications (
  adjudication_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  job_id uuid,
  adjudication_kind text NOT NULL CHECK (adjudication_kind IN (
    'intent_reconstruction',
    'replay_episode_promotion',
    'memory_declassification',
    'external_skill_relationship',
    'topology_operation_choice',
    'policy_safe_action',
    'skill_plan_semantic_adjudication',
    'context_equivalence',
    'quarantine_release',
    'freeze_repair_triage'
  )),
  input_event_ids uuid[] NOT NULL DEFAULT '{}',
  input_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  input_raw_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  model_profile_id uuid,
  llm_verdict jsonb NOT NULL,
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  deterministic_checks jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision text NOT NULL CHECK (decision IN (
    'auto_accept',
    'auto_reject',
    'collect_more_evidence',
    'run_more_probes',
    'run_re_adjudication',
    'run_verifier_adjudication',
    'stage_ephemeral_candidate',
    'stage_canary',
    'reduce_scope',
    'quarantine',
    'freeze',
    'rollback',
    'escalate_admin',
    'no_op_reschedule'
  )),
  escalation_reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS autonomous_adjudications_workspace_kind_idx
  ON autoskill.autonomous_adjudications(workspace_id, adjudication_kind, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.autonomy_policy_versions (
  autonomy_policy_version_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  policy_kind text NOT NULL CHECK (policy_kind IN (
    'decision_orchestrator',
    'candidate_thresholds',
    'acceptance_bands',
    'broker_policy',
    'curation_policy',
    'canary_policy'
  )),
  version_name text NOT NULL,
  policy jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','active','retired','quarantined')),
  activated_at timestamptz,
  retired_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, policy_kind, version_name)
);

CREATE INDEX IF NOT EXISTS autonomy_policy_versions_workspace_kind_idx
  ON autoskill.autonomy_policy_versions(workspace_id, policy_kind, status, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.autonomy_calibration_observations (
  calibration_observation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  calibration_family text NOT NULL,
  autonomy_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  model_profile_id uuid,
  adjudication_id uuid REFERENCES autoskill.autonomous_adjudications(adjudication_id),
  autonomy_decision_id uuid,
  action_risk_tier text NOT NULL CHECK (action_risk_tier IN (
    'T0_observe',
    'T1_internal_record',
    'T2_trial_artifact',
    'T3_owned_runtime_change',
    'T4_external_or_irreversible'
  )),
  predicted_confidence numeric NOT NULL CHECK (predicted_confidence >= 0 AND predicted_confidence <= 1),
  confidence_components jsonb NOT NULL DEFAULT '{}'::jsonb,
  selected_action text NOT NULL,
  outcome_status text NOT NULL CHECK (outcome_status IN (
    'pending',
    'success',
    'failure',
    'mixed',
    'unknown',
    'revoked'
  )),
  outcome_observed_at timestamptz,
  outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
  false_accept boolean,
  false_reject boolean,
  unnecessary_abstention boolean,
  harm_finding boolean,
  utility_score numeric,
  context_token_delta integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS autonomy_calibration_workspace_family_idx
  ON autoskill.autonomy_calibration_observations(workspace_id, calibration_family, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.autonomy_reliability_metrics (
  reliability_metric_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  calibration_family text NOT NULL,
  autonomy_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  executor_profile_id uuid,
  evidence_fidelity text,
  action_risk_tier text,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  sample_count integer NOT NULL DEFAULT 0,
  coverage_rate numeric,
  false_accept_rate numeric,
  false_reject_rate numeric,
  abstention_rate numeric,
  unnecessary_abstention_rate numeric,
  calibration_error numeric,
  brier_like_score numeric,
  canary_failure_rate numeric,
  rollback_rate numeric,
  harm_finding_rate numeric,
  utility_per_context_token numeric,
  reliability_bins jsonb NOT NULL DEFAULT '[]'::jsonb,
  calibration_support text NOT NULL CHECK (
    calibration_support IN ('none','empirical_low_support','empirical_supported','conformal_supported','stale')
  ),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS autonomy_reliability_workspace_family_idx
  ON autoskill.autonomy_reliability_metrics(workspace_id, calibration_family, window_end DESC);

CREATE TABLE IF NOT EXISTS autoskill.autonomy_policy_trials (
  autonomy_policy_trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  policy_kind text NOT NULL,
  candidate_policy jsonb NOT NULL,
  baseline_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  status text NOT NULL CHECK (
    status IN ('draft','replay_backtest','shadow_mode','canary_policy','accepted','rejected','rolled_back')
  ),
  replay_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  shadow_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  canary_result jsonb NOT NULL DEFAULT '{}'::jsonb,
  hard_invariant_impact jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected_unblocked_decisions integer NOT NULL DEFAULT 0,
  expected_risk_delta jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  retired_at timestamptz
);

CREATE INDEX IF NOT EXISTS autonomy_policy_trials_workspace_kind_idx
  ON autoskill.autonomy_policy_trials(workspace_id, policy_kind, status, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.autonomy_decisions (
  autonomy_decision_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  job_id uuid,
  candidate_id uuid,
  skill_id uuid,
  operation_kind text NOT NULL,
  autonomy_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  llm_adjudication_ids uuid[] NOT NULL DEFAULT '{}',
  hard_invariants jsonb NOT NULL DEFAULT '{}'::jsonb,
  soft_thresholds jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence_decomposition jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_band text NOT NULL CHECK (
    decision_band IN ('clear_accept','clear_reject','improve_evidence','narrow_scope','canary_only','quarantine','admin_required')
  ),
  action text NOT NULL CHECK (action IN (
    'auto_accept',
    'auto_reject',
    'collect_more_evidence',
    'run_more_probes',
    'run_re_adjudication',
    'stage_ephemeral_candidate',
    'stage_canary',
    'reduce_scope',
    'quarantine',
    'freeze',
    'rollback',
    'escalate_admin',
    'no_op_reschedule'
  )),
  reason_codes text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS autonomy_decisions_workspace_operation_idx
  ON autoskill.autonomy_decisions(workspace_id, operation_kind, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.administrative_escalation_events (
  escalation_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  autonomy_decision_id uuid REFERENCES autoskill.autonomy_decisions(autonomy_decision_id),
  adjudication_id uuid REFERENCES autoskill.autonomous_adjudications(adjudication_id),
  escalation_kind text NOT NULL CHECK (escalation_kind IN (
    'policy_forbids_needed_raw_access',
    'raw_reveal_requested',
    'external_owned_root_mutation_requested',
    'irreversible_infrastructure_change_requested',
    'required_infrastructure_unavailable',
    'repeated_contradictory_adjudications_after_fallback',
    'predelegated_authority_absent_for_T4_action'
  )),
  evidence_packet_id uuid,
  decision_family text,
  source_fidelity text,
  hard_invariants jsonb NOT NULL DEFAULT '{}'::jsonb,
  attempted_autonomous_alternatives text[] NOT NULL DEFAULT '{}',
  recommended_admin_action text,
  status text NOT NULL CHECK (status IN ('open','resolved','withdrawn','superseded','expired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS administrative_escalation_workspace_status_idx
  ON autoskill.administrative_escalation_events(workspace_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.threshold_deadlock_findings (
  threshold_deadlock_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  policy_kind text NOT NULL,
  stalled_candidate_ids uuid[] NOT NULL DEFAULT '{}',
  stall_reason_codes text[] NOT NULL DEFAULT '{}',
  hard_invariants_passed boolean NOT NULL,
  llm_high_utility_count integer NOT NULL DEFAULT 0,
  recommended_action text NOT NULL CHECK (recommended_action IN (
    'collect_more_evidence',
    'generate_more_probes',
    'relax_soft_threshold',
    'narrow_scope',
    'increase_canary_budget',
    'reject_cohort',
    'no_action'
  )),
  status text NOT NULL CHECK (status IN ('open','trialing_policy','resolved','rejected','quarantined')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS threshold_deadlock_workspace_status_idx
  ON autoskill.threshold_deadlock_findings(workspace_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.intent_interpretations (
  intent_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  source_event_ids uuid[] NOT NULL DEFAULT '{}',
  raw_evidence_record_ids uuid[] NOT NULL DEFAULT '{}',
  declassification_report_id uuid REFERENCES autoskill.declassification_reports(declassification_report_id),
  redacted_user_intent text NOT NULL,
  intent_fingerprint text NOT NULL,
  expected_skill_decision jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  taint text[] NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('candidate','accepted','rejected','quarantined','revoked')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS intent_interpretations_workspace_status_idx
  ON autoskill.intent_interpretations(workspace_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.raw_events (
  event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  trace_id uuid,
  span_id uuid,
  parent_span_id uuid,
  agent_id text,
  session_id text,
  turn_id text,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL,
  source text NOT NULL,
  source_event_key text,
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  redaction_state text NOT NULL,
  evidence_fidelity text NOT NULL DEFAULT 'redacted_derivative' CHECK (evidence_fidelity IN (
    'raw_vault_linked',
    'declassified_summary',
    'redacted_derivative',
    'metadata_only',
    'hash_only'
  )),
  raw_evidence_record_id uuid,
  payload_hash text NOT NULL,
  payload jsonb NOT NULL,
  plugin_version text,
  openclaw_version text,
  inserted_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS agent_id text;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS source_event_key text;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS evidence_fidelity text NOT NULL DEFAULT 'redacted_derivative';

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS raw_evidence_record_id uuid;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'raw_events_evidence_fidelity_check'
      AND connamespace = 'autoskill'::regnamespace
  ) THEN
    ALTER TABLE autoskill.raw_events
      ADD CONSTRAINT raw_events_evidence_fidelity_check
      CHECK (evidence_fidelity IN (
        'raw_vault_linked',
        'declassified_summary',
        'redacted_derivative',
        'metadata_only',
        'hash_only'
      ));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS raw_events_workspace_source_event_key_idx
  ON autoskill.raw_events(workspace_id, source, source_event_key)
  WHERE source_event_key IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'raw_events_raw_evidence_record_fk'
      AND connamespace = 'autoskill'::regnamespace
  ) THEN
    ALTER TABLE autoskill.raw_events
      ADD CONSTRAINT raw_events_raw_evidence_record_fk
      FOREIGN KEY (raw_evidence_record_id)
      REFERENCES autoskill.raw_evidence_records(raw_evidence_record_id)
      DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS autoskill.evidence_items (
  evidence_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_event_id uuid REFERENCES autoskill.raw_events(event_id),
  evidence_hash text NOT NULL,
  kind text NOT NULL,
  maturity text NOT NULL DEFAULT 'observed',
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  summary text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS evidence_items_workspace_hash_idx
  ON autoskill.evidence_items(workspace_id, evidence_hash);

CREATE TABLE IF NOT EXISTS autoskill.evidence (
  evidence_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid,
  source_event_ids uuid[] NOT NULL DEFAULT '{}',
  evidence_type text NOT NULL,
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  summary text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric NOT NULL DEFAULT 1 CHECK (confidence >= 0 AND confidence <= 1),
  utility_hint numeric,
  evidence_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, evidence_hash)
);

CREATE INDEX IF NOT EXISTS evidence_workspace_type_created_idx
  ON autoskill.evidence(workspace_id, evidence_type, created_at DESC);

CREATE OR REPLACE FUNCTION autoskill.sync_evidence_from_items()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.evidence (
    evidence_id,
    workspace_id,
    skill_id,
    source_event_ids,
    evidence_type,
    trust,
    taint,
    summary,
    details,
    confidence,
    utility_hint,
    evidence_hash,
    created_at
  )
  VALUES (
    NEW.evidence_id,
    NEW.workspace_id,
    NULL,
    CASE
      WHEN NEW.source_event_id IS NULL THEN '{}'::uuid[]
      ELSE ARRAY[NEW.source_event_id]
    END,
    NEW.kind,
    NEW.trust,
    NEW.taint,
    NEW.summary,
    NEW.payload,
    CASE
      WHEN (NEW.payload ->> 'confidence') ~ '^(0(\.[0-9]+)?|1(\.0+)?)$'
      THEN (NEW.payload ->> 'confidence')::numeric
      ELSE 1
    END,
    CASE
      WHEN (NEW.payload ->> 'utility_hint') ~ '^-?[0-9]+(\.[0-9]+)?$'
      THEN (NEW.payload ->> 'utility_hint')::numeric
      ELSE NULL
    END,
    NEW.evidence_hash,
    NEW.created_at
  )
  ON CONFLICT (workspace_id, evidence_hash)
  DO UPDATE SET
    source_event_ids = EXCLUDED.source_event_ids,
    evidence_type = EXCLUDED.evidence_type,
    trust = EXCLUDED.trust,
    taint = EXCLUDED.taint,
    summary = EXCLUDED.summary,
    details = EXCLUDED.details,
    confidence = EXCLUDED.confidence,
    utility_hint = EXCLUDED.utility_hint;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS evidence_items_sync_evidence ON autoskill.evidence_items;
CREATE TRIGGER evidence_items_sync_evidence
AFTER INSERT OR UPDATE ON autoskill.evidence_items
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_evidence_from_items();

INSERT INTO autoskill.evidence (
  evidence_id,
  workspace_id,
  skill_id,
  source_event_ids,
  evidence_type,
  trust,
  taint,
  summary,
  details,
  confidence,
  utility_hint,
  evidence_hash,
  created_at
)
SELECT
  evidence_id,
  workspace_id,
  NULL,
  CASE
    WHEN source_event_id IS NULL THEN '{}'::uuid[]
    ELSE ARRAY[source_event_id]
  END,
  kind,
  trust,
  taint,
  summary,
  payload,
  CASE
    WHEN (payload ->> 'confidence') ~ '^(0(\.[0-9]+)?|1(\.0+)?)$'
    THEN (payload ->> 'confidence')::numeric
    ELSE 1
  END,
  CASE
    WHEN (payload ->> 'utility_hint') ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (payload ->> 'utility_hint')::numeric
    ELSE NULL
  END,
  evidence_hash,
  created_at
FROM autoskill.evidence_items
ON CONFLICT (workspace_id, evidence_hash) DO NOTHING;

CREATE TABLE IF NOT EXISTS autoskill.skills (
  skill_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  slug text NOT NULL,
  name text NOT NULL,
  source text NOT NULL DEFAULT 'autoskill',
  lifecycle_state text NOT NULL DEFAULT 'ephemeral_candidate',
  active_version_id uuid,
  last_canary_status text,
  freeze_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  frozen_at timestamptz,
  UNIQUE(workspace_id, slug)
);

ALTER TABLE autoskill.skills
  ADD COLUMN IF NOT EXISTS last_canary_status text;

ALTER TABLE autoskill.skills
  ADD COLUMN IF NOT EXISTS freeze_reason text;

ALTER TABLE autoskill.skills
  ADD COLUMN IF NOT EXISTS frozen_at timestamptz;

ALTER TABLE autoskill.skills
  ALTER COLUMN lifecycle_state SET DEFAULT 'ephemeral_candidate';

ALTER TABLE autoskill.skills
  DROP CONSTRAINT IF EXISTS skills_lifecycle_state_check;
ALTER TABLE autoskill.skills
  ADD CONSTRAINT skills_lifecycle_state_check CHECK (
    lifecycle_state IN (
      'observed_pattern',
      'candidate_cluster',
      'ephemeral_candidate',
      'trial_candidate',
      'validated_candidate',
      'active',
      'canary_active',
      'archived',
      'frozen',
      'revoked',
      'superseded',
      'external_readonly',
      'candidate',
      'quarantined',
      'deleted'
    )
  );

CREATE TABLE IF NOT EXISTS autoskill.skill_versions (
  skill_version_id uuid PRIMARY KEY,
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  version integer NOT NULL,
  skill_ir_schema_version text NOT NULL DEFAULT 'skillir.v1',
  compiler_version text NOT NULL DEFAULT 'autoskill-compiler.v1',
  skill_ir jsonb NOT NULL,
  compiled_sha256 text,
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  scanner_status text NOT NULL DEFAULT 'pending',
  evaluator_status text NOT NULL DEFAULT 'pending',
  created_by_transaction_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  archived_at timestamptz,
  UNIQUE(skill_id, version)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'skills_active_version_fk'
      AND conrelid = 'autoskill.skills'::regclass
  ) THEN
    ALTER TABLE autoskill.skills
      ADD CONSTRAINT skills_active_version_fk
      FOREIGN KEY (active_version_id)
      REFERENCES autoskill.skill_versions(skill_version_id)
      DEFERRABLE INITIALLY DEFERRED;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS autoskill.compiled_files (
  compiled_file_id uuid PRIMARY KEY,
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  path text NOT NULL,
  sha256 text NOT NULL,
  bytes integer NOT NULL,
  renderer_version text NOT NULL,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.support_artifacts (
  support_artifact_id uuid PRIMARY KEY,
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  path text NOT NULL,
  kind text NOT NULL,
  sha256 text NOT NULL,
  capabilities text[] NOT NULL DEFAULT '{}',
  load_policy text NOT NULL DEFAULT 'never_loaded'
    CHECK (
      load_policy IN (
        'never_loaded',
        'agent_may_read',
        'broker_excerpt_only',
        'script_only',
        'probe_only',
        'operator_only'
      )
    ),
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.skill_files (
  skill_file_id uuid PRIMARY KEY,
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  relative_path text NOT NULL,
  file_role text NOT NULL,
  content_hash text NOT NULL,
  byte_size integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, relative_path)
);

CREATE OR REPLACE FUNCTION autoskill.sync_skill_file_from_compiled()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.skill_files (
    skill_file_id,
    skill_version_id,
    relative_path,
    file_role,
    content_hash,
    byte_size,
    created_at
  )
  VALUES (
    NEW.compiled_file_id,
    NEW.skill_version_id,
    NEW.path,
    'compiled_runtime',
    NEW.sha256,
    NEW.bytes,
    NEW.created_at
  )
  ON CONFLICT (skill_version_id, relative_path)
  DO UPDATE SET
    file_role = EXCLUDED.file_role,
    content_hash = EXCLUDED.content_hash,
    byte_size = EXCLUDED.byte_size;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS compiled_files_sync_skill_files ON autoskill.compiled_files;
CREATE TRIGGER compiled_files_sync_skill_files
AFTER INSERT OR UPDATE ON autoskill.compiled_files
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_file_from_compiled();

CREATE OR REPLACE FUNCTION autoskill.sync_skill_file_from_support_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.skill_files (
    skill_file_id,
    skill_version_id,
    relative_path,
    file_role,
    content_hash,
    byte_size,
    created_at
  )
  VALUES (
    NEW.support_artifact_id,
    NEW.skill_version_id,
    NEW.path,
    NEW.kind,
    NEW.sha256,
    CASE
      WHEN (NEW.manifest ->> 'byte_size') ~ '^[0-9]+$'
      THEN (NEW.manifest ->> 'byte_size')::integer
      ELSE 0
    END,
    NEW.created_at
  )
  ON CONFLICT (skill_version_id, relative_path)
  DO UPDATE SET
    file_role = EXCLUDED.file_role,
    content_hash = EXCLUDED.content_hash,
    byte_size = EXCLUDED.byte_size;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS support_artifacts_sync_skill_files ON autoskill.support_artifacts;
CREATE TRIGGER support_artifacts_sync_skill_files
AFTER INSERT OR UPDATE ON autoskill.support_artifacts
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_file_from_support_artifact();

INSERT INTO autoskill.skill_files (
  skill_file_id,
  skill_version_id,
  relative_path,
  file_role,
  content_hash,
  byte_size,
  created_at
)
SELECT
  compiled_file_id,
  skill_version_id,
  path,
  'compiled_runtime',
  sha256,
  bytes,
  created_at
FROM autoskill.compiled_files
ON CONFLICT (skill_version_id, relative_path) DO NOTHING;

INSERT INTO autoskill.skill_files (
  skill_file_id,
  skill_version_id,
  relative_path,
  file_role,
  content_hash,
  byte_size,
  created_at
)
SELECT
  support_artifact_id,
  skill_version_id,
  path,
  kind,
  sha256,
  CASE
    WHEN (manifest ->> 'byte_size') ~ '^[0-9]+$'
    THEN (manifest ->> 'byte_size')::integer
    ELSE 0
  END,
  created_at
FROM autoskill.support_artifacts
ON CONFLICT (skill_version_id, relative_path) DO NOTHING;

CREATE TABLE IF NOT EXISTS autoskill.skill_ir_revisions (
  skill_ir_revision_id uuid PRIMARY KEY,
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  ir_schema_version text NOT NULL DEFAULT 'skillir.v1',
  ir_hash text NOT NULL,
  ir jsonb NOT NULL,
  change_kind text NOT NULL CHECK (change_kind IN (
    'create',
    'improve',
    'compose',
    'decompose',
    'compile',
    'repair',
    'merge',
    'split',
    'archive',
    'promote',
    'rollback',
    'drift_repair'
  )),
  source_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  source_memory_ids uuid[] NOT NULL DEFAULT '{}',
  llm_plan_hash text,
  compiler_version text NOT NULL DEFAULT 'skillkernel-compiler.v1',
  created_by_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_id, ir_hash)
);

CREATE OR REPLACE FUNCTION autoskill.sync_skill_ir_revision_from_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  computed_ir_hash text;
BEGIN
  computed_ir_hash := 'sha256:' || encode(digest(NEW.skill_ir::text, 'sha256'), 'hex');
  INSERT INTO autoskill.skill_ir_revisions (
    skill_ir_revision_id,
    skill_id,
    skill_version_id,
    ir_schema_version,
    ir_hash,
    ir,
    change_kind,
    compiler_version,
    created_at
  )
  VALUES (
    NEW.skill_version_id,
    NEW.skill_id,
    NEW.skill_version_id,
    NEW.skill_ir_schema_version,
    computed_ir_hash,
    NEW.skill_ir,
    CASE
      WHEN NEW.version <= 1 THEN 'create'
      ELSE 'improve'
    END,
    NEW.compiler_version,
    NEW.created_at
  )
  ON CONFLICT (skill_id, ir_hash)
  DO UPDATE SET
    skill_version_id = EXCLUDED.skill_version_id,
    ir_schema_version = EXCLUDED.ir_schema_version,
    ir = EXCLUDED.ir,
    compiler_version = EXCLUDED.compiler_version;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS skill_versions_sync_skill_ir_revisions ON autoskill.skill_versions;
CREATE TRIGGER skill_versions_sync_skill_ir_revisions
AFTER INSERT OR UPDATE ON autoskill.skill_versions
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_ir_revision_from_version();

INSERT INTO autoskill.skill_ir_revisions (
  skill_ir_revision_id,
  skill_id,
  skill_version_id,
  ir_schema_version,
  ir_hash,
  ir,
  change_kind,
  compiler_version,
  created_at
)
SELECT
  skill_version_id,
  skill_id,
  skill_version_id,
  skill_ir_schema_version,
  'sha256:' || encode(digest(skill_ir::text, 'sha256'), 'hex'),
  skill_ir,
  CASE
    WHEN version <= 1 THEN 'create'
    ELSE 'improve'
  END,
  compiler_version,
  created_at
FROM autoskill.skill_versions
ON CONFLICT (skill_id, ir_hash) DO NOTHING;

CREATE TABLE IF NOT EXISTS autoskill.skill_components (
  component_id uuid PRIMARY KEY,
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  component_type text NOT NULL CHECK (component_type IN (
    'planning',
    'functional',
    'atomic',
    'precondition',
    'validator',
    'failure_mode',
    'disambiguator',
    'contract',
    'template',
    'tool_template',
    'runtime_guard',
    'negative_example',
    'quality_gate'
  )),
  title text NOT NULL,
  content text NOT NULL,
  applicability jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, component_type, title)
);

CREATE OR REPLACE FUNCTION autoskill.sync_skill_component_from_version()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  component_kind text;
  component_title text;
  component_content text;
BEGIN
  component_kind := COALESCE(NULLIF(NEW.skill_ir ->> 'granularity', ''), 'functional');
  IF component_kind NOT IN ('planning','functional','atomic') THEN
    component_kind := 'functional';
  END IF;
  component_title := COALESCE(NULLIF(NEW.skill_ir ->> 'name', ''), 'SkillIR component');
  component_content := COALESCE(
    NULLIF(NEW.skill_ir ->> 'description', ''),
    NULLIF(NEW.skill_ir ->> 'summary', ''),
    component_title
  );
  INSERT INTO autoskill.skill_components (
    component_id,
    skill_id,
    skill_version_id,
    component_type,
    title,
    content,
    applicability,
    provenance,
    confidence,
    created_at
  )
  VALUES (
    gen_random_uuid(),
    NEW.skill_id,
    NEW.skill_version_id,
    component_kind,
    component_title,
    component_content,
    jsonb_build_object('source', 'skill_ir', 'granularity', component_kind),
    jsonb_build_object('skill_version_id', NEW.skill_version_id),
    1,
    NEW.created_at
  )
  ON CONFLICT (skill_version_id, component_type, title)
  DO UPDATE SET
    content = EXCLUDED.content,
    applicability = EXCLUDED.applicability,
    provenance = EXCLUDED.provenance,
    confidence = EXCLUDED.confidence;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS skill_versions_sync_skill_components ON autoskill.skill_versions;
CREATE TRIGGER skill_versions_sync_skill_components
AFTER INSERT OR UPDATE ON autoskill.skill_versions
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_component_from_version();

INSERT INTO autoskill.skill_components (
  component_id,
  skill_id,
  skill_version_id,
  component_type,
  title,
  content,
  applicability,
  provenance,
  confidence,
  created_at
)
SELECT
  gen_random_uuid(),
  skill_id,
  skill_version_id,
  CASE
    WHEN COALESCE(NULLIF(skill_ir ->> 'granularity', ''), 'functional') IN ('planning','functional','atomic')
    THEN COALESCE(NULLIF(skill_ir ->> 'granularity', ''), 'functional')
    ELSE 'functional'
  END,
  COALESCE(NULLIF(skill_ir ->> 'name', ''), 'SkillIR component'),
  COALESCE(NULLIF(skill_ir ->> 'description', ''), NULLIF(skill_ir ->> 'summary', ''), COALESCE(NULLIF(skill_ir ->> 'name', ''), 'SkillIR component')),
  jsonb_build_object('source', 'skill_ir', 'granularity', COALESCE(NULLIF(skill_ir ->> 'granularity', ''), 'functional')),
  jsonb_build_object('skill_version_id', skill_version_id),
  1,
  created_at
FROM autoskill.skill_versions
ON CONFLICT (skill_version_id, component_type, title) DO NOTHING;

CREATE TABLE IF NOT EXISTS autoskill.skill_edges (
  edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  from_skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  to_skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  edge_kind text NOT NULL,
  revoked_at timestamptz,
  revocation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(from_skill_id, to_skill_id, edge_kind)
);

ALTER TABLE autoskill.skill_edges
  ADD COLUMN IF NOT EXISTS revoked_at timestamptz;

ALTER TABLE autoskill.skill_edges
  ADD COLUMN IF NOT EXISTS revocation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS autoskill.probes (
  probe_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  probe_hash text NOT NULL,
  kind text NOT NULL,
  maturity text NOT NULL DEFAULT 'observed',
  spec jsonb NOT NULL,
  expected jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  retired_at timestamptz,
  UNIQUE(workspace_id, probe_hash)
);

CREATE TABLE IF NOT EXISTS autoskill.executor_profiles (
  executor_profile_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  profile_key text NOT NULL,
  model_family text,
  agent_backend text,
  sandbox text,
  os_name text,
  available_tools text[] NOT NULL DEFAULT '{}',
  available_binaries text[] NOT NULL DEFAULT '{}',
  permissions jsonb NOT NULL DEFAULT '{}'::jsonb,
  api_contracts jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','inactive','quarantined')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, profile_key)
);

CREATE TABLE IF NOT EXISTS autoskill.model_profiles (
  model_profile_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  profile_key text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  route_kind text NOT NULL CHECK (route_kind IN ('openclaw','openai_compatible')),
  endpoint_ref text,
  endpoint_kind text NOT NULL DEFAULT 'chat_completions'
    CHECK (endpoint_kind IN ('chat_completions','responses')),
  timeout_seconds double precision NOT NULL DEFAULT 60,
  thinking_level text NOT NULL DEFAULT 'off'
    CHECK (thinking_level IN ('off','minimal','low','medium','high','xhigh','adaptive','max')),
  thinking_fallback_policy text NOT NULL DEFAULT 'omit'
    CHECK (thinking_fallback_policy IN ('strict','downgrade','omit')),
  status text NOT NULL DEFAULT 'candidate'
    CHECK (status IN ('candidate','qualified','failed','disabled')),
  qualification jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, profile_key)
);

ALTER TABLE autoskill.model_profiles
  ADD COLUMN IF NOT EXISTS thinking_level text NOT NULL DEFAULT 'off';

ALTER TABLE autoskill.model_profiles
  ADD COLUMN IF NOT EXISTS thinking_fallback_policy text NOT NULL DEFAULT 'omit';

ALTER TABLE autoskill.model_profiles
  ADD COLUMN IF NOT EXISTS endpoint_kind text NOT NULL DEFAULT 'chat_completions';

ALTER TABLE autoskill.model_profiles
  DROP CONSTRAINT IF EXISTS model_profiles_endpoint_kind_check;

ALTER TABLE autoskill.model_profiles
  ADD CONSTRAINT model_profiles_endpoint_kind_check
  CHECK (endpoint_kind IN ('chat_completions','responses'));

ALTER TABLE autoskill.model_profiles
  DROP CONSTRAINT IF EXISTS model_profiles_thinking_level_check;

ALTER TABLE autoskill.model_profiles
  ADD CONSTRAINT model_profiles_thinking_level_check
  CHECK (thinking_level IN ('off','minimal','low','medium','high','xhigh','adaptive','max'));

ALTER TABLE autoskill.model_profiles
  DROP CONSTRAINT IF EXISTS model_profiles_thinking_fallback_policy_check;

ALTER TABLE autoskill.model_profiles
  ADD CONSTRAINT model_profiles_thinking_fallback_policy_check
  CHECK (thinking_fallback_policy IN ('strict','downgrade','omit'));

CREATE TABLE IF NOT EXISTS autoskill.llm_invocations (
  llm_invocation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  trace_id uuid,
  span_id uuid,
  purpose text NOT NULL,
  profile_key text NOT NULL,
  model_profile_id uuid REFERENCES autoskill.model_profiles(model_profile_id),
  route_kind text NOT NULL CHECK (route_kind IN ('openclaw','openai_compatible')),
  provider text NOT NULL,
  model text NOT NULL,
  requested_thinking_level text,
  effective_thinking_level text,
  thinking_fallback_policy text NOT NULL DEFAULT 'omit',
  thinking_downgraded boolean NOT NULL DEFAULT false,
  prompt_token_estimate integer NOT NULL DEFAULT 0,
  output_token_estimate integer NOT NULL DEFAULT 0,
  status text NOT NULL CHECK (status IN ('ok','error','timeout','unsupported')),
  error text,
  audit jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS llm_invocations_workspace_created_idx
  ON autoskill.llm_invocations(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.model_profile_qualification_runs (
  model_profile_qualification_run_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  model_profile_id uuid REFERENCES autoskill.model_profiles(model_profile_id),
  profile_key text NOT NULL,
  route_kind text NOT NULL CHECK (route_kind IN ('openclaw','openai_compatible')),
  provider text NOT NULL,
  model text NOT NULL,
  thinking_level text,
  probe_set_version text NOT NULL,
  verdict text NOT NULL
    CHECK (
      verdict IN (
        'qualified_autonomous',
        'qualified_propose_only',
        'qualified_classify',
        'failed',
        'expired'
      )
    ),
  probe_results jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);

CREATE INDEX IF NOT EXISTS model_profile_qualification_runs_profile_created_idx
  ON autoskill.model_profile_qualification_runs(workspace_id, profile_key, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.embedding_profiles (
  embedding_profile_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  profile_key text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  route_kind text NOT NULL CHECK (route_kind IN ('hash','openclaw','openai_compatible')),
  embedding_dim integer NOT NULL,
  endpoint_ref text,
  timeout_seconds double precision NOT NULL DEFAULT 30,
  status text NOT NULL DEFAULT 'candidate'
    CHECK (status IN ('candidate','qualified','active','failed','disabled')),
  qualification jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, profile_key)
);

ALTER TABLE autoskill.embedding_profiles
  DROP CONSTRAINT IF EXISTS embedding_profiles_status_check;

ALTER TABLE autoskill.embedding_profiles
  ADD CONSTRAINT embedding_profiles_status_check
  CHECK (status IN ('candidate','qualified','active','failed','disabled'));

CREATE TABLE IF NOT EXISTS autoskill.embedding_profile_qualification_runs (
  embedding_profile_qualification_run_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  embedding_profile_id uuid REFERENCES autoskill.embedding_profiles(embedding_profile_id),
  profile_key text NOT NULL,
  route_kind text NOT NULL CHECK (route_kind IN ('hash','openclaw','openai_compatible')),
  provider text NOT NULL,
  model text NOT NULL,
  embedding_dim integer NOT NULL,
  distance_metric text NOT NULL DEFAULT 'cosine',
  probe_set_version text NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('qualified','failed','expired')),
  probe_results jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);

CREATE INDEX IF NOT EXISTS embedding_profile_qualification_runs_profile_created_idx
  ON autoskill.embedding_profile_qualification_runs(workspace_id, profile_key, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.evaluations (
  evaluation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  trace_id uuid,
  span_id uuid,
  parent_span_id uuid,
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  broker_policy_version_id uuid,
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  category text NOT NULL,
  status text NOT NULL,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE autoskill.evaluations
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.evaluations
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.evaluations
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

CREATE TABLE IF NOT EXISTS autoskill.skill_profile_compatibility (
  skill_profile_compatibility_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  executor_profile_id uuid NOT NULL REFERENCES autoskill.executor_profiles(executor_profile_id),
  status text NOT NULL CHECK (status IN ('unknown','compatible','degraded','blocked','drifted')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_checked_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, skill_version_id, executor_profile_id)
);

CREATE TABLE IF NOT EXISTS autoskill.broker_policy_versions (
  broker_policy_version_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  version text NOT NULL,
  policy jsonb NOT NULL,
  status text NOT NULL DEFAULT 'candidate',
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  rolled_back_at timestamptz,
  UNIQUE(workspace_id, version)
);

CREATE OR REPLACE FUNCTION autoskill.stable_uuid_from_text(seed text)
RETURNS uuid
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT (
    substr(md5(coalesce(seed, '')), 1, 8) || '-' ||
    substr(md5(coalesce(seed, '')), 9, 4) || '-' ||
    substr(md5(coalesce(seed, '')), 13, 4) || '-' ||
    substr(md5(coalesce(seed, '')), 17, 4) || '-' ||
    substr(md5(coalesce(seed, '')), 21, 12)
  )::uuid;
$$;

CREATE TABLE IF NOT EXISTS autoskill.retrieval_logs (
  retrieval_log_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  trace_id uuid,
  span_id uuid,
  parent_span_id uuid,
  session_id text,
  turn_id text,
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  decision text NOT NULL,
  candidate_skill_ids uuid[] NOT NULL DEFAULT '{}',
  rendered_skill_ids uuid[] NOT NULL DEFAULT '{}',
  no_skill_control boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE autoskill.retrieval_logs
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.retrieval_logs
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.retrieval_logs
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

CREATE TABLE IF NOT EXISTS autoskill.retrieval_events (
  retrieval_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  query_hash text NOT NULL,
  query_features jsonb NOT NULL DEFAULT '{}'::jsonb,
  candidate_skill_ids uuid[] NOT NULL DEFAULT '{}',
  rendered_skill_ids uuid[] NOT NULL DEFAULT '{}',
  injected boolean NOT NULL DEFAULT false,
  budget_tokens integer NOT NULL DEFAULT 0,
  decision jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION autoskill.sync_retrieval_event_from_log()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.retrieval_events (
    retrieval_event_id,
    workspace_id,
    session_id,
    turn_id,
    query_hash,
    query_features,
    candidate_skill_ids,
    rendered_skill_ids,
    injected,
    budget_tokens,
    decision,
    created_at
  )
  VALUES (
    NEW.retrieval_log_id,
    NEW.workspace_id,
    NEW.session_id,
    NEW.turn_id,
    COALESCE(
      NULLIF(NEW.metadata->>'query_hash', ''),
      'sha256:' || encode(digest(
        coalesce(NEW.metadata->>'query', '') || ':' || NEW.retrieval_log_id::text,
        'sha256'
      ), 'hex')
    ),
    jsonb_strip_nulls(
      jsonb_build_object(
        'source', 'retrieval_logs',
        'trace_id', NEW.trace_id,
        'span_id', NEW.span_id,
        'parent_span_id', NEW.parent_span_id,
        'broker_policy_version_id', NEW.broker_policy_version_id
      )
    ) ||
      CASE
        WHEN jsonb_typeof(NEW.metadata->'query_features') = 'object'
        THEN NEW.metadata->'query_features'
        ELSE '{}'::jsonb
      END,
    NEW.candidate_skill_ids,
    NEW.rendered_skill_ids,
    cardinality(NEW.rendered_skill_ids) > 0,
    CASE
      WHEN NEW.metadata->>'budget_tokens' ~ '^[0-9]+$'
      THEN (NEW.metadata->>'budget_tokens')::integer
      ELSE 0
    END,
    jsonb_strip_nulls(jsonb_build_object(
      'legacy_decision', NEW.decision,
      'no_skill_control', NEW.no_skill_control,
      'metadata', NEW.metadata
    )),
    NEW.created_at
  )
  ON CONFLICT (retrieval_event_id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    session_id = EXCLUDED.session_id,
    turn_id = EXCLUDED.turn_id,
    query_hash = EXCLUDED.query_hash,
    query_features = EXCLUDED.query_features,
    candidate_skill_ids = EXCLUDED.candidate_skill_ids,
    rendered_skill_ids = EXCLUDED.rendered_skill_ids,
    injected = EXCLUDED.injected,
    budget_tokens = EXCLUDED.budget_tokens,
    decision = EXCLUDED.decision,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS retrieval_logs_sync_retrieval_events ON autoskill.retrieval_logs;
CREATE TRIGGER retrieval_logs_sync_retrieval_events
AFTER INSERT OR UPDATE ON autoskill.retrieval_logs
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_retrieval_event_from_log();

INSERT INTO autoskill.retrieval_events (
  retrieval_event_id,
  workspace_id,
  session_id,
  turn_id,
  query_hash,
  query_features,
  candidate_skill_ids,
  rendered_skill_ids,
  injected,
  budget_tokens,
  decision,
  created_at
)
SELECT
  retrieval_log_id,
  workspace_id,
  session_id,
  turn_id,
  COALESCE(
    NULLIF(metadata->>'query_hash', ''),
    'sha256:' || encode(digest(coalesce(metadata->>'query', '') || ':' || retrieval_log_id::text, 'sha256'), 'hex')
  ),
  jsonb_strip_nulls(jsonb_build_object(
    'source', 'retrieval_logs',
    'trace_id', trace_id,
    'span_id', span_id,
    'parent_span_id', parent_span_id,
    'broker_policy_version_id', broker_policy_version_id
  )) ||
    CASE
      WHEN jsonb_typeof(metadata->'query_features') = 'object' THEN metadata->'query_features'
      ELSE '{}'::jsonb
    END,
  candidate_skill_ids,
  rendered_skill_ids,
  cardinality(rendered_skill_ids) > 0,
  CASE
    WHEN metadata->>'budget_tokens' ~ '^[0-9]+$' THEN (metadata->>'budget_tokens')::integer
    ELSE 0
  END,
  jsonb_strip_nulls(jsonb_build_object(
    'legacy_decision', decision,
    'no_skill_control', no_skill_control,
    'metadata', metadata
  )),
  created_at
FROM autoskill.retrieval_logs
ON CONFLICT (retrieval_event_id) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  session_id = EXCLUDED.session_id,
  turn_id = EXCLUDED.turn_id,
  query_hash = EXCLUDED.query_hash,
  query_features = EXCLUDED.query_features,
  candidate_skill_ids = EXCLUDED.candidate_skill_ids,
  rendered_skill_ids = EXCLUDED.rendered_skill_ids,
  injected = EXCLUDED.injected,
  budget_tokens = EXCLUDED.budget_tokens,
  decision = EXCLUDED.decision,
  created_at = EXCLUDED.created_at;

CREATE INDEX IF NOT EXISTS retrieval_events_workspace_created_idx
  ON autoskill.retrieval_events (workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.broker_replay_episodes (
  broker_replay_episode_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_retrieval_log_id uuid REFERENCES autoskill.retrieval_logs(retrieval_log_id),
  episode_key text NOT NULL,
  redacted_user_intent text NOT NULL,
  expected_decision text,
  expected_skill_ids uuid[] NOT NULL DEFAULT '{}',
  tags text[] NOT NULL DEFAULT '{}',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, episode_key)
);

CREATE INDEX IF NOT EXISTS broker_replay_episodes_workspace_created_idx
  ON autoskill.broker_replay_episodes(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.body_index_documents (
  body_index_document_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  document_kind text NOT NULL,
  text_hash text NOT NULL,
  text_content text NOT NULL,
  secret_scan_status text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, skill_version_id, document_kind, text_hash)
);

CREATE TABLE IF NOT EXISTS autoskill.context_artifacts (
  context_artifact_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  artifact_kind text NOT NULL CHECK (artifact_kind IN (
    'skill_md','frontmatter_description','broker_hint','support_excerpt',
    'tool_template','verification_instruction','failure_instruction',
    'component_reference'
  )),
  source_object_type text NOT NULL,
  source_object_id uuid,
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  text_hash text NOT NULL,
  token_count integer NOT NULL,
  max_tokens integer NOT NULL,
  semantic_density_score double precision,
  safety_status text NOT NULL DEFAULT 'pending',
  equivalence_status text NOT NULL DEFAULT 'pending',
  budget_status text NOT NULL DEFAULT 'pending',
  shadowing_status text NOT NULL DEFAULT 'pending',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, artifact_kind, source_object_type, source_object_id, text_hash)
);

CREATE TABLE IF NOT EXISTS autoskill.context_token_ledgers (
  context_token_ledger_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  context_artifact_id uuid REFERENCES autoskill.context_artifacts(context_artifact_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  session_id text,
  turn_id text,
  visibility_state text NOT NULL CHECK (visibility_state IN (
    'no_skill','defer_skill','skill_hidden','skill_visible','sibling_bundle'
  )),
  token_count integer NOT NULL,
  outcome text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.runtime_guard_templates (
  guard_template_id uuid PRIMARY KEY,
  guard_name text UNIQUE NOT NULL,
  guard_kind text NOT NULL CHECK (
    guard_kind IN (
      'preflight',
      'verify_only',
      'warn',
      'block',
      'context_hint',
      'drift_check',
      'capability_check',
      'shadowing_hint'
    )
  ),
  allowed_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  renderer_version text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO autoskill.runtime_guard_templates (
  guard_template_id,
  guard_name,
  guard_kind,
  allowed_parameters,
  renderer_version
)
VALUES
  (
    autoskill.stable_uuid_from_text('runtime_guard_template:preflight_check'),
    'preflight_check',
    'preflight',
    '{"fields":["condition_summary","operator_message","required_capabilities"],"executable_logic_allowed":false}'::jsonb,
    'skillkernel-guard-template.v1'
  ),
  (
    autoskill.stable_uuid_from_text('runtime_guard_template:verify_only_check'),
    'verify_only_check',
    'verify_only',
    '{"fields":["condition_summary","operator_message","required_capabilities"],"executable_logic_allowed":false}'::jsonb,
    'skillkernel-guard-template.v1'
  ),
  (
    autoskill.stable_uuid_from_text('runtime_guard_template:capability_warning'),
    'capability_warning',
    'warn',
    '{"fields":["condition_summary","operator_message","required_capabilities"],"executable_logic_allowed":false}'::jsonb,
    'skillkernel-guard-template.v1'
  ),
  (
    autoskill.stable_uuid_from_text('runtime_guard_template:sibling_disambiguation_hint'),
    'sibling_disambiguation_hint',
    'shadowing_hint',
    '{"fields":["condition_summary","operator_message","required_capabilities"],"executable_logic_allowed":false}'::jsonb,
    'skillkernel-guard-template.v1'
  ),
  (
    autoskill.stable_uuid_from_text('runtime_guard_template:drift_block'),
    'drift_block',
    'drift_check',
    '{"fields":["condition_summary","operator_message","required_capabilities"],"executable_logic_allowed":false}'::jsonb,
    'skillkernel-guard-template.v1'
  )
ON CONFLICT (guard_name) DO UPDATE SET
  guard_kind = EXCLUDED.guard_kind,
  allowed_parameters = EXCLUDED.allowed_parameters,
  renderer_version = EXCLUDED.renderer_version,
  enabled = EXCLUDED.enabled;

CREATE TABLE IF NOT EXISTS autoskill.memory_contracts (
  memory_contract_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  memory_kind text NOT NULL CHECK (
    memory_kind IN (
      'evidence',
      'procedural_lesson',
      'negative_control',
      'environment_fact',
      'user_correction',
      'tool_capability',
      'drift_signal'
    )
  ),
  allowed_sources jsonb NOT NULL DEFAULT '{}'::jsonb,
  ttl_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  declassification_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  validator jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, memory_kind)
);

CREATE OR REPLACE FUNCTION autoskill.sync_default_memory_contracts_for_workspace()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  memory_kind_value text;
BEGIN
  FOREACH memory_kind_value IN ARRAY ARRAY[
    'evidence',
    'procedural_lesson',
    'negative_control',
    'environment_fact',
    'user_correction',
    'tool_capability',
    'drift_signal'
  ]::text[] LOOP
    INSERT INTO autoskill.memory_contracts (
      memory_contract_id,
      workspace_id,
      memory_kind,
      allowed_sources,
      ttl_policy,
      declassification_rules,
      validator
    )
    VALUES (
      autoskill.stable_uuid_from_text('memory_contract:' || NEW.workspace_id::text || ':' || memory_kind_value),
      NEW.workspace_id,
      memory_kind_value,
      jsonb_build_object(
        'required_provenance', true,
        'required_source_event_ids', true,
        'external_content_policy', 'evidence_only'
      ),
      jsonb_build_object(
        'retention_class', 'standard',
        'requires_expiry_for_private_or_secret', true
      ),
      jsonb_build_object(
        'requires_verifier_before_skillir_influence', true,
        'quarantine_imperative_or_policy_language', true,
        'prefer_false_negatives', true
      ),
      jsonb_build_object(
        'required_fields', jsonb_build_array('provenance', 'trust', 'taint', 'source_event_ids'),
        'reject_external_direct_instruction', true,
        'compare_for_contradictions', true
      )
    )
    ON CONFLICT (workspace_id, memory_kind) DO NOTHING;
  END LOOP;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS workspaces_sync_default_memory_contracts ON autoskill.workspaces;
CREATE TRIGGER workspaces_sync_default_memory_contracts
AFTER INSERT ON autoskill.workspaces
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_default_memory_contracts_for_workspace();

INSERT INTO autoskill.memory_contracts (
  memory_contract_id,
  workspace_id,
  memory_kind,
  allowed_sources,
  ttl_policy,
  declassification_rules,
  validator
)
SELECT
  autoskill.stable_uuid_from_text('memory_contract:' || workspace_id::text || ':' || memory_kind_value),
  workspace_id,
  memory_kind_value,
  jsonb_build_object(
    'required_provenance', true,
    'required_source_event_ids', true,
    'external_content_policy', 'evidence_only'
  ),
  jsonb_build_object(
    'retention_class', 'standard',
    'requires_expiry_for_private_or_secret', true
  ),
  jsonb_build_object(
    'requires_verifier_before_skillir_influence', true,
    'quarantine_imperative_or_policy_language', true,
    'prefer_false_negatives', true
  ),
  jsonb_build_object(
    'required_fields', jsonb_build_array('provenance', 'trust', 'taint', 'source_event_ids'),
    'reject_external_direct_instruction', true,
    'compare_for_contradictions', true
  )
FROM autoskill.workspaces
CROSS JOIN unnest(ARRAY[
  'evidence',
  'procedural_lesson',
  'negative_control',
  'environment_fact',
  'user_correction',
  'tool_capability',
  'drift_signal'
]::text[]) AS memory_kind_value
ON CONFLICT (workspace_id, memory_kind) DO NOTHING;

CREATE TABLE IF NOT EXISTS autoskill.runtime_artifacts (
  runtime_artifact_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  artifact_type text NOT NULL CHECK (
    artifact_type IN (
      'skill_md',
      'manifest',
      'contract',
      'script',
      'reference',
      'template',
      'schema',
      'static_data',
      'asset',
      'example',
      'test',
      'probe_fixture',
      'adjunct_request',
      'profile_rendering',
      'broker_hint',
      'context_excerpt'
    )
  ),
  loadability_class text NOT NULL CHECK (
    loadability_class IN (
      'runtime_always_metadata',
      'runtime_on_skill_load',
      'agent_may_read',
      'broker_excerpt_only',
      'script_only',
      'probe_only',
      'operator_only',
      'never_loaded'
    )
  ),
  relative_path text NOT NULL DEFAULT '',
  content_hash text NOT NULL,
  byte_size bigint NOT NULL DEFAULT 0 CHECK (byte_size >= 0),
  context_token_estimate integer NOT NULL DEFAULT 0 CHECK (context_token_estimate >= 0),
  capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  artifact_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  scanner_status text NOT NULL,
  test_status text NOT NULL DEFAULT 'not_applicable',
  source_kind text NOT NULL,
  source_record_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, artifact_type, relative_path)
);

CREATE OR REPLACE FUNCTION autoskill.sync_runtime_artifact_from_compiled_file()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  source_workspace_id uuid;
BEGIN
  SELECT s.workspace_id
  INTO source_workspace_id
  FROM autoskill.skill_versions sv
  JOIN autoskill.skills s ON s.skill_id = sv.skill_id
  WHERE sv.skill_version_id = NEW.skill_version_id;

  IF source_workspace_id IS NULL THEN
    RETURN NEW;
  END IF;

  INSERT INTO autoskill.runtime_artifacts (
    runtime_artifact_id,
    workspace_id,
    skill_version_id,
    artifact_type,
    loadability_class,
    relative_path,
    content_hash,
    byte_size,
    context_token_estimate,
    capabilities,
    artifact_contract,
    scanner_status,
    test_status,
    source_kind,
    source_record_id,
    created_at
  )
  VALUES (
    autoskill.stable_uuid_from_text('runtime_artifact:compiled_file:' || NEW.compiled_file_id::text),
    source_workspace_id,
    NEW.skill_version_id,
    CASE
      WHEN lower(NEW.path) = 'skill.md' OR lower(NEW.path) LIKE '%/skill.md' THEN 'skill_md'
      WHEN lower(NEW.path) LIKE '%.schema.json' THEN 'schema'
      WHEN lower(NEW.path) LIKE '%.json' THEN 'manifest'
      ELSE 'script'
    END,
    CASE WHEN NEW.active THEN 'runtime_on_skill_load' ELSE 'never_loaded' END,
    NEW.path,
    NEW.sha256,
    GREATEST(0, NEW.bytes)::bigint,
    0,
    '{}'::jsonb,
    jsonb_build_object(
      'source', 'compiled_files',
      'renderer_version', NEW.renderer_version,
      'active', NEW.active
    ),
    'not_run',
    'not_applicable',
    'compiled_file',
    NEW.compiled_file_id,
    NEW.created_at
  )
  ON CONFLICT (skill_version_id, artifact_type, relative_path) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    content_hash = EXCLUDED.content_hash,
    byte_size = EXCLUDED.byte_size,
    context_token_estimate = EXCLUDED.context_token_estimate,
    capabilities = EXCLUDED.capabilities,
    artifact_contract = EXCLUDED.artifact_contract,
    scanner_status = EXCLUDED.scanner_status,
    test_status = EXCLUDED.test_status,
    source_kind = EXCLUDED.source_kind,
    source_record_id = EXCLUDED.source_record_id,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION autoskill.sync_runtime_artifact_from_support_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  source_workspace_id uuid;
BEGIN
  SELECT s.workspace_id
  INTO source_workspace_id
  FROM autoskill.skill_versions sv
  JOIN autoskill.skills s ON s.skill_id = sv.skill_id
  WHERE sv.skill_version_id = NEW.skill_version_id;

  IF source_workspace_id IS NULL THEN
    RETURN NEW;
  END IF;

  INSERT INTO autoskill.runtime_artifacts (
    runtime_artifact_id,
    workspace_id,
    skill_version_id,
    artifact_type,
    loadability_class,
    relative_path,
    content_hash,
    byte_size,
    context_token_estimate,
    capabilities,
    artifact_contract,
    scanner_status,
    test_status,
    source_kind,
    source_record_id,
    created_at
  )
  VALUES (
    autoskill.stable_uuid_from_text('runtime_artifact:support_artifact:' || NEW.support_artifact_id::text),
    source_workspace_id,
    NEW.skill_version_id,
    CASE NEW.kind
      WHEN 'script' THEN 'script'
      WHEN 'template' THEN 'template'
      WHEN 'fixture' THEN 'probe_fixture'
      WHEN 'manifest' THEN 'manifest'
      WHEN 'asset' THEN 'asset'
      ELSE 'reference'
    END,
    CASE
      WHEN NEW.load_policy IN (
        'agent_may_read',
        'broker_excerpt_only',
        'script_only',
        'probe_only',
        'operator_only',
        'never_loaded'
      )
      THEN NEW.load_policy
      ELSE 'never_loaded'
    END,
    NEW.path,
    NEW.sha256,
    CASE
      WHEN NEW.manifest->>'byte_size' ~ '^[0-9]+$' THEN (NEW.manifest->>'byte_size')::bigint
      ELSE 0
    END,
    CASE
      WHEN NEW.manifest->>'token_count' ~ '^[0-9]+$' THEN (NEW.manifest->>'token_count')::integer
      ELSE 0
    END,
    to_jsonb(NEW.capabilities),
    jsonb_build_object('source', 'support_artifacts', 'manifest', NEW.manifest, 'active', NEW.active),
    COALESCE(NULLIF(NEW.manifest->>'scanner_status', ''), 'not_run'),
    COALESCE(NULLIF(NEW.manifest->>'test_status', ''), 'not_applicable'),
    'support_artifact',
    NEW.support_artifact_id,
    NEW.created_at
  )
  ON CONFLICT (skill_version_id, artifact_type, relative_path) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    content_hash = EXCLUDED.content_hash,
    byte_size = EXCLUDED.byte_size,
    context_token_estimate = EXCLUDED.context_token_estimate,
    capabilities = EXCLUDED.capabilities,
    artifact_contract = EXCLUDED.artifact_contract,
    scanner_status = EXCLUDED.scanner_status,
    test_status = EXCLUDED.test_status,
    source_kind = EXCLUDED.source_kind,
    source_record_id = EXCLUDED.source_record_id,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION autoskill.sync_runtime_artifact_from_context_artifact()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.skill_version_id IS NULL THEN
    RETURN NEW;
  END IF;

  INSERT INTO autoskill.runtime_artifacts (
    runtime_artifact_id,
    workspace_id,
    skill_version_id,
    artifact_type,
    loadability_class,
    relative_path,
    content_hash,
    byte_size,
    context_token_estimate,
    capabilities,
    artifact_contract,
    scanner_status,
    test_status,
    source_kind,
    source_record_id,
    created_at
  )
  VALUES (
    autoskill.stable_uuid_from_text('runtime_artifact:context_artifact:' || NEW.context_artifact_id::text),
    NEW.workspace_id,
    NEW.skill_version_id,
    CASE NEW.artifact_kind
      WHEN 'skill_md' THEN 'skill_md'
      WHEN 'broker_hint' THEN 'broker_hint'
      WHEN 'tool_template' THEN 'template'
      WHEN 'support_excerpt' THEN 'context_excerpt'
      ELSE 'reference'
    END,
    CASE
      WHEN NEW.metadata->>'loadability_class' IN (
        'runtime_always_metadata',
        'runtime_on_skill_load',
        'agent_may_read',
        'broker_excerpt_only',
        'script_only',
        'probe_only',
        'operator_only',
        'never_loaded'
      )
      THEN NEW.metadata->>'loadability_class'
      ELSE 'broker_excerpt_only'
    END,
    COALESCE(NULLIF(NEW.metadata->>'relative_path', ''), 'context/' || NEW.context_artifact_id::text || '.txt'),
    NEW.text_hash,
    GREATEST(0, NEW.token_count * 4)::bigint,
    GREATEST(0, NEW.token_count),
    CASE
      WHEN jsonb_typeof(NEW.metadata->'capabilities') = 'array' THEN NEW.metadata->'capabilities'
      ELSE '{}'::jsonb
    END,
    jsonb_build_object(
      'source', 'context_artifacts',
      'artifact_kind', NEW.artifact_kind,
      'source_object_type', NEW.source_object_type,
      'source_object_id', NEW.source_object_id,
      'metadata', NEW.metadata
    ),
    NEW.safety_status,
    COALESCE(NULLIF(NEW.equivalence_status, ''), 'not_applicable'),
    'context_artifact',
    NEW.context_artifact_id,
    NEW.created_at
  )
  ON CONFLICT (skill_version_id, artifact_type, relative_path) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    content_hash = EXCLUDED.content_hash,
    byte_size = EXCLUDED.byte_size,
    context_token_estimate = EXCLUDED.context_token_estimate,
    capabilities = EXCLUDED.capabilities,
    artifact_contract = EXCLUDED.artifact_contract,
    scanner_status = EXCLUDED.scanner_status,
    test_status = EXCLUDED.test_status,
    source_kind = EXCLUDED.source_kind,
    source_record_id = EXCLUDED.source_record_id,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS compiled_files_sync_runtime_artifacts ON autoskill.compiled_files;
CREATE TRIGGER compiled_files_sync_runtime_artifacts
AFTER INSERT OR UPDATE ON autoskill.compiled_files
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_runtime_artifact_from_compiled_file();

DROP TRIGGER IF EXISTS support_artifacts_sync_runtime_artifacts ON autoskill.support_artifacts;
CREATE TRIGGER support_artifacts_sync_runtime_artifacts
AFTER INSERT OR UPDATE ON autoskill.support_artifacts
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_runtime_artifact_from_support_artifact();

DROP TRIGGER IF EXISTS context_artifacts_sync_runtime_artifacts ON autoskill.context_artifacts;
CREATE TRIGGER context_artifacts_sync_runtime_artifacts
AFTER INSERT OR UPDATE ON autoskill.context_artifacts
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_runtime_artifact_from_context_artifact();

INSERT INTO autoskill.runtime_artifacts (
  runtime_artifact_id,
  workspace_id,
  skill_version_id,
  artifact_type,
  loadability_class,
  relative_path,
  content_hash,
  byte_size,
  context_token_estimate,
  capabilities,
  artifact_contract,
  scanner_status,
  test_status,
  source_kind,
  source_record_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text('runtime_artifact:compiled_file:' || cf.compiled_file_id::text),
  s.workspace_id,
  cf.skill_version_id,
  CASE
    WHEN lower(cf.path) = 'skill.md' OR lower(cf.path) LIKE '%/skill.md' THEN 'skill_md'
    WHEN lower(cf.path) LIKE '%.schema.json' THEN 'schema'
    WHEN lower(cf.path) LIKE '%.json' THEN 'manifest'
    ELSE 'script'
  END,
  CASE WHEN cf.active THEN 'runtime_on_skill_load' ELSE 'never_loaded' END,
  cf.path,
  cf.sha256,
  GREATEST(0, cf.bytes)::bigint,
  0,
  '{}'::jsonb,
  jsonb_build_object('source', 'compiled_files', 'renderer_version', cf.renderer_version, 'active', cf.active),
  'not_run',
  'not_applicable',
  'compiled_file',
  cf.compiled_file_id,
  cf.created_at
FROM autoskill.compiled_files cf
JOIN autoskill.skill_versions sv ON sv.skill_version_id = cf.skill_version_id
JOIN autoskill.skills s ON s.skill_id = sv.skill_id
ON CONFLICT (skill_version_id, artifact_type, relative_path) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  content_hash = EXCLUDED.content_hash,
  byte_size = EXCLUDED.byte_size,
  context_token_estimate = EXCLUDED.context_token_estimate,
  capabilities = EXCLUDED.capabilities,
  artifact_contract = EXCLUDED.artifact_contract,
  scanner_status = EXCLUDED.scanner_status,
  test_status = EXCLUDED.test_status,
  source_kind = EXCLUDED.source_kind,
  source_record_id = EXCLUDED.source_record_id,
  created_at = EXCLUDED.created_at;

INSERT INTO autoskill.runtime_artifacts (
  runtime_artifact_id,
  workspace_id,
  skill_version_id,
  artifact_type,
  loadability_class,
  relative_path,
  content_hash,
  byte_size,
  context_token_estimate,
  capabilities,
  artifact_contract,
  scanner_status,
  test_status,
  source_kind,
  source_record_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text('runtime_artifact:support_artifact:' || sa.support_artifact_id::text),
  s.workspace_id,
  sa.skill_version_id,
  CASE sa.kind
    WHEN 'script' THEN 'script'
    WHEN 'template' THEN 'template'
    WHEN 'fixture' THEN 'probe_fixture'
    WHEN 'manifest' THEN 'manifest'
    WHEN 'asset' THEN 'asset'
    ELSE 'reference'
  END,
  CASE
    WHEN sa.load_policy IN (
      'agent_may_read',
      'broker_excerpt_only',
      'script_only',
      'probe_only',
      'operator_only',
      'never_loaded'
    )
    THEN sa.load_policy
    ELSE 'never_loaded'
  END,
  sa.path,
  sa.sha256,
  CASE WHEN sa.manifest->>'byte_size' ~ '^[0-9]+$' THEN (sa.manifest->>'byte_size')::bigint ELSE 0 END,
  CASE WHEN sa.manifest->>'token_count' ~ '^[0-9]+$' THEN (sa.manifest->>'token_count')::integer ELSE 0 END,
  to_jsonb(sa.capabilities),
  jsonb_build_object('source', 'support_artifacts', 'manifest', sa.manifest, 'active', sa.active),
  COALESCE(NULLIF(sa.manifest->>'scanner_status', ''), 'not_run'),
  COALESCE(NULLIF(sa.manifest->>'test_status', ''), 'not_applicable'),
  'support_artifact',
  sa.support_artifact_id,
  sa.created_at
FROM autoskill.support_artifacts sa
JOIN autoskill.skill_versions sv ON sv.skill_version_id = sa.skill_version_id
JOIN autoskill.skills s ON s.skill_id = sv.skill_id
ON CONFLICT (skill_version_id, artifact_type, relative_path) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  content_hash = EXCLUDED.content_hash,
  byte_size = EXCLUDED.byte_size,
  context_token_estimate = EXCLUDED.context_token_estimate,
  capabilities = EXCLUDED.capabilities,
  artifact_contract = EXCLUDED.artifact_contract,
  scanner_status = EXCLUDED.scanner_status,
  test_status = EXCLUDED.test_status,
  source_kind = EXCLUDED.source_kind,
  source_record_id = EXCLUDED.source_record_id,
  created_at = EXCLUDED.created_at;

INSERT INTO autoskill.runtime_artifacts (
  runtime_artifact_id,
  workspace_id,
  skill_version_id,
  artifact_type,
  loadability_class,
  relative_path,
  content_hash,
  byte_size,
  context_token_estimate,
  capabilities,
  artifact_contract,
  scanner_status,
  test_status,
  source_kind,
  source_record_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text('runtime_artifact:context_artifact:' || context_artifact_id::text),
  workspace_id,
  skill_version_id,
  CASE artifact_kind
    WHEN 'skill_md' THEN 'skill_md'
    WHEN 'broker_hint' THEN 'broker_hint'
    WHEN 'tool_template' THEN 'template'
    WHEN 'support_excerpt' THEN 'context_excerpt'
    ELSE 'reference'
  END,
  CASE
    WHEN metadata->>'loadability_class' IN (
      'runtime_always_metadata',
      'runtime_on_skill_load',
      'agent_may_read',
      'broker_excerpt_only',
      'script_only',
      'probe_only',
      'operator_only',
      'never_loaded'
    )
    THEN metadata->>'loadability_class'
    ELSE 'broker_excerpt_only'
  END,
  COALESCE(NULLIF(metadata->>'relative_path', ''), 'context/' || context_artifact_id::text || '.txt'),
  text_hash,
  GREATEST(0, token_count * 4)::bigint,
  GREATEST(0, token_count),
  CASE WHEN jsonb_typeof(metadata->'capabilities') = 'array' THEN metadata->'capabilities' ELSE '{}'::jsonb END,
  jsonb_build_object(
    'source', 'context_artifacts',
    'artifact_kind', artifact_kind,
    'source_object_type', source_object_type,
    'source_object_id', source_object_id,
    'metadata', metadata
  ),
  safety_status,
  COALESCE(NULLIF(equivalence_status, ''), 'not_applicable'),
  'context_artifact',
  context_artifact_id,
  created_at
FROM autoskill.context_artifacts
WHERE skill_version_id IS NOT NULL
ON CONFLICT (skill_version_id, artifact_type, relative_path) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  content_hash = EXCLUDED.content_hash,
  byte_size = EXCLUDED.byte_size,
  context_token_estimate = EXCLUDED.context_token_estimate,
  capabilities = EXCLUDED.capabilities,
  artifact_contract = EXCLUDED.artifact_contract,
  scanner_status = EXCLUDED.scanner_status,
  test_status = EXCLUDED.test_status,
  source_kind = EXCLUDED.source_kind,
  source_record_id = EXCLUDED.source_record_id,
  created_at = EXCLUDED.created_at;

CREATE INDEX IF NOT EXISTS runtime_artifacts_skill_version_idx
  ON autoskill.runtime_artifacts (workspace_id, skill_version_id, artifact_type);

CREATE TABLE IF NOT EXISTS autoskill.integration_proposals (
  integration_proposal_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  originating_skill_id uuid REFERENCES autoskill.skills(skill_id),
  originating_skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  proposal_kind text NOT NULL CHECK (
    proposal_kind IN (
      'openclaw_tool',
      'plugin_hook',
      'plugin_service',
      'mcp_server',
      'sidecar_schedule',
      'taskflow_template',
      'persistent_store',
      'capability_policy_change'
    )
  ),
  status text NOT NULL CHECK (
    status IN (
      'draft',
      'administrative_authority_required',
      'authorized',
      'denied',
      'implemented',
      'superseded'
    )
  ),
  reason text NOT NULL,
  proposed_contract jsonb NOT NULL DEFAULT '{}'::jsonb,
  inert_template_artifact_id uuid REFERENCES autoskill.runtime_artifacts(runtime_artifact_id),
  source_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  scanner_findings jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS autoskill.skill_state_records (
  skill_state_record_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id) DEFERRABLE INITIALLY DEFERRED,
  state_key text NOT NULL,
  state_kind text NOT NULL CHECK (
    state_kind IN ('counter','cache','checkpoint','runtime_fact','drift_state','adjunct_state')
  ),
  state_value jsonb NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  taint_state text NOT NULL DEFAULT 'clean',
  retention_class text NOT NULL DEFAULT 'standard',
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, skill_id, state_key)
);

CREATE OR REPLACE FUNCTION autoskill.sync_skill_state_record_from_skill()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.skill_state_records (
    skill_state_record_id,
    workspace_id,
    skill_id,
    skill_version_id,
    state_key,
    state_kind,
    state_value,
    provenance,
    taint_state,
    retention_class,
    created_at,
    updated_at
  )
  VALUES (
    autoskill.stable_uuid_from_text('skill_state_record:skills:' || NEW.skill_id::text || ':lifecycle'),
    NEW.workspace_id,
    NEW.skill_id,
    NEW.active_version_id,
    'lifecycle',
    'runtime_fact',
    jsonb_strip_nulls(jsonb_build_object(
      'slug', NEW.slug,
      'name', NEW.name,
      'source', NEW.source,
      'lifecycle_state', NEW.lifecycle_state,
      'active_version_id', NEW.active_version_id,
      'last_canary_status', NEW.last_canary_status,
      'freeze_reason', NEW.freeze_reason,
      'frozen_at', NEW.frozen_at
    )),
    jsonb_build_object('source', 'skills'),
    CASE
      WHEN NEW.lifecycle_state IN ('quarantined','revoked','deleted') THEN 'tainted'
      ELSE 'clean'
    END,
    CASE
      WHEN NEW.lifecycle_state IN ('deleted','revoked') THEN 'retention_delete'
      ELSE 'standard'
    END,
    NEW.created_at,
    NEW.updated_at
  )
  ON CONFLICT (workspace_id, skill_id, state_key) DO UPDATE SET
    skill_version_id = EXCLUDED.skill_version_id,
    state_kind = EXCLUDED.state_kind,
    state_value = EXCLUDED.state_value,
    provenance = EXCLUDED.provenance,
    taint_state = EXCLUDED.taint_state,
    retention_class = EXCLUDED.retention_class,
    updated_at = EXCLUDED.updated_at;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS skills_sync_skill_state_records ON autoskill.skills;
CREATE TRIGGER skills_sync_skill_state_records
AFTER INSERT OR UPDATE ON autoskill.skills
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_state_record_from_skill();

INSERT INTO autoskill.skill_state_records (
  skill_state_record_id,
  workspace_id,
  skill_id,
  skill_version_id,
  state_key,
  state_kind,
  state_value,
  provenance,
  taint_state,
  retention_class,
  created_at,
  updated_at
)
SELECT
  autoskill.stable_uuid_from_text('skill_state_record:skills:' || skill_id::text || ':lifecycle'),
  workspace_id,
  skill_id,
  active_version_id,
  'lifecycle',
  'runtime_fact',
  jsonb_strip_nulls(jsonb_build_object(
    'slug', slug,
    'name', name,
    'source', source,
    'lifecycle_state', lifecycle_state,
    'active_version_id', active_version_id,
    'last_canary_status', last_canary_status,
    'freeze_reason', freeze_reason,
    'frozen_at', frozen_at
  )),
  jsonb_build_object('source', 'skills'),
  CASE WHEN lifecycle_state IN ('quarantined','revoked','deleted') THEN 'tainted' ELSE 'clean' END,
  CASE WHEN lifecycle_state IN ('deleted','revoked') THEN 'retention_delete' ELSE 'standard' END,
  created_at,
  updated_at
FROM autoskill.skills
ON CONFLICT (workspace_id, skill_id, state_key) DO UPDATE SET
  skill_version_id = EXCLUDED.skill_version_id,
  state_kind = EXCLUDED.state_kind,
  state_value = EXCLUDED.state_value,
  provenance = EXCLUDED.provenance,
  taint_state = EXCLUDED.taint_state,
  retention_class = EXCLUDED.retention_class,
  updated_at = EXCLUDED.updated_at;

CREATE TABLE IF NOT EXISTS autoskill.skill_marginal_value_trials (
  trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  trial_kind text NOT NULL CHECK (
    trial_kind IN (
      'no_skill',
      'old_skill',
      'new_skill',
      'skill_hidden',
      'skill_visible',
      'sibling_bundle',
      'broker_variant'
    )
  ),
  task_fingerprint text NOT NULL,
  outcome jsonb NOT NULL,
  score numeric,
  source_context_token_ledger_id uuid UNIQUE REFERENCES autoskill.context_token_ledgers(context_token_ledger_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION autoskill.sync_skill_marginal_value_trial_from_context_ledger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.skill_marginal_value_trials (
    trial_id,
    workspace_id,
    skill_version_id,
    executor_profile_id,
    trial_kind,
    task_fingerprint,
    outcome,
    score,
    source_context_token_ledger_id,
    created_at
  )
  VALUES (
    autoskill.stable_uuid_from_text('skill_marginal_value_trial:context_token_ledger:' || NEW.context_token_ledger_id::text),
    NEW.workspace_id,
    NEW.skill_version_id,
    NULL,
    CASE NEW.visibility_state
      WHEN 'no_skill' THEN 'no_skill'
      WHEN 'skill_hidden' THEN 'skill_hidden'
      WHEN 'defer_skill' THEN 'skill_hidden'
      WHEN 'skill_visible' THEN 'skill_visible'
      WHEN 'sibling_bundle' THEN 'sibling_bundle'
      ELSE 'broker_variant'
    END,
    COALESCE(
      NULLIF(NEW.metadata->>'task_fingerprint', ''),
      'sha256:' || encode(digest(
        coalesce(NEW.session_id, '') || ':' || coalesce(NEW.turn_id, '') || ':' || NEW.context_token_ledger_id::text,
        'sha256'
      ), 'hex')
    ),
    jsonb_build_object(
      'source', 'context_token_ledgers',
      'context_artifact_id', NEW.context_artifact_id,
      'skill_id', NEW.skill_id,
      'visibility_state', NEW.visibility_state,
      'token_count', NEW.token_count,
      'outcome', NEW.outcome,
      'metadata', NEW.metadata
    ),
    CASE
      WHEN NEW.metadata #>> '{marginal_value,marginal_value}' ~ '^-?[0-9]+(\.[0-9]+)?$'
      THEN (NEW.metadata #>> '{marginal_value,marginal_value}')::numeric
      WHEN NEW.metadata #>> '{source_metadata,marginal_value,marginal_value}' ~ '^-?[0-9]+(\.[0-9]+)?$'
      THEN (NEW.metadata #>> '{source_metadata,marginal_value,marginal_value}')::numeric
      ELSE NULL
    END,
    NEW.context_token_ledger_id,
    NEW.created_at
  )
  ON CONFLICT (source_context_token_ledger_id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    skill_version_id = EXCLUDED.skill_version_id,
    executor_profile_id = EXCLUDED.executor_profile_id,
    trial_kind = EXCLUDED.trial_kind,
    task_fingerprint = EXCLUDED.task_fingerprint,
    outcome = EXCLUDED.outcome,
    score = EXCLUDED.score,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS context_token_ledgers_sync_skill_marginal_value_trials
  ON autoskill.context_token_ledgers;
CREATE TRIGGER context_token_ledgers_sync_skill_marginal_value_trials
AFTER INSERT OR UPDATE ON autoskill.context_token_ledgers
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_marginal_value_trial_from_context_ledger();

INSERT INTO autoskill.skill_marginal_value_trials (
  trial_id,
  workspace_id,
  skill_version_id,
  executor_profile_id,
  trial_kind,
  task_fingerprint,
  outcome,
  score,
  source_context_token_ledger_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text('skill_marginal_value_trial:context_token_ledger:' || context_token_ledger_id::text),
  workspace_id,
  skill_version_id,
  NULL,
  CASE visibility_state
    WHEN 'no_skill' THEN 'no_skill'
    WHEN 'skill_hidden' THEN 'skill_hidden'
    WHEN 'defer_skill' THEN 'skill_hidden'
    WHEN 'skill_visible' THEN 'skill_visible'
    WHEN 'sibling_bundle' THEN 'sibling_bundle'
    ELSE 'broker_variant'
  END,
  COALESCE(
    NULLIF(metadata->>'task_fingerprint', ''),
    'sha256:' || encode(digest(coalesce(session_id, '') || ':' || coalesce(turn_id, '') || ':' || context_token_ledger_id::text, 'sha256'), 'hex')
  ),
  jsonb_build_object(
    'source', 'context_token_ledgers',
    'context_artifact_id', context_artifact_id,
    'skill_id', skill_id,
    'visibility_state', visibility_state,
    'token_count', token_count,
    'outcome', outcome,
    'metadata', metadata
  ),
  CASE
    WHEN metadata #>> '{marginal_value,marginal_value}' ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (metadata #>> '{marginal_value,marginal_value}')::numeric
    WHEN metadata #>> '{source_metadata,marginal_value,marginal_value}' ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (metadata #>> '{source_metadata,marginal_value,marginal_value}')::numeric
    ELSE NULL
  END,
  context_token_ledger_id,
  created_at
FROM autoskill.context_token_ledgers
ON CONFLICT (source_context_token_ledger_id) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  skill_version_id = EXCLUDED.skill_version_id,
  executor_profile_id = EXCLUDED.executor_profile_id,
  trial_kind = EXCLUDED.trial_kind,
  task_fingerprint = EXCLUDED.task_fingerprint,
  outcome = EXCLUDED.outcome,
  score = EXCLUDED.score,
  created_at = EXCLUDED.created_at;

CREATE INDEX IF NOT EXISTS skill_marginal_value_trials_task_idx
  ON autoskill.skill_marginal_value_trials (workspace_id, task_fingerprint, trial_kind, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.context_compile_runs (
  context_compile_run_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  candidate_id uuid,
  context_artifact_id uuid REFERENCES autoskill.context_artifacts(context_artifact_id),
  compiler_version text NOT NULL,
  model_assist_used boolean NOT NULL DEFAULT false,
  input_skillir_hash text NOT NULL,
  output_manifest_hash text NOT NULL,
  target_runtime_tokens integer,
  actual_runtime_tokens integer NOT NULL,
  compression_ratio double precision,
  semantic_equivalence_score double precision,
  status text NOT NULL CHECK (status IN (
    'planned','passed','failed','rejected','needs_probe','over_budget'
  )),
  reject_reason text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.context_budget_events (
  context_budget_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  context_artifact_id uuid REFERENCES autoskill.context_artifacts(context_artifact_id),
  event_type text NOT NULL,
  tokens_delta integer,
  marginal_success_delta double precision,
  false_positive_load_delta double precision,
  ignored_load_delta double precision,
  shadowing_delta double precision,
  decision text NOT NULL CHECK (decision IN (
    'compress_again','split_support_file','decompose_skill',
    'tighten_description','broker_abstain','archive_low_value_skill',
    'reject_change','accept','observe'
  )),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.semantic_compression_trials (
  semantic_compression_trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  source_revision_id uuid,
  candidate_revision_id uuid,
  source_context_artifact_id uuid REFERENCES autoskill.context_artifacts(context_artifact_id),
  candidate_context_artifact_id uuid REFERENCES autoskill.context_artifacts(context_artifact_id),
  source_tokens integer NOT NULL,
  candidate_tokens integer NOT NULL,
  preserved_requirements integer NOT NULL,
  lost_requirements integer NOT NULL,
  added_unsupported_requirements integer NOT NULL,
  equivalence_score double precision NOT NULL,
  target_probe_pass_rate double precision,
  regression_probe_pass_rate double precision,
  status text NOT NULL CHECK (status IN (
    'passed','failed','needs_probe','rejected','planned'
  )),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.external_skill_inventory (
  external_skill_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source text NOT NULL,
  root_path_hash text NOT NULL,
  slug text NOT NULL,
  name text,
  description text,
  frontmatter jsonb NOT NULL DEFAULT '{}'::jsonb,
  file_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('visible','missing','changed','ignored','quarantined')),
  risk_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, source, root_path_hash, slug)
);

CREATE TABLE IF NOT EXISTS autoskill.external_skill_review_actions (
  external_skill_review_action_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  external_skill_id uuid NOT NULL REFERENCES autoskill.external_skill_inventory(external_skill_id),
  action text NOT NULL CHECK (action IN ('reuse','import','ignore','quarantine')),
  status text NOT NULL CHECK (status IN ('requested','approved','rejected','completed')),
  operator_id text,
  rationale text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.embeddings (
  embedding_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  object_type text NOT NULL,
  object_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  embedding_profile_id uuid REFERENCES autoskill.embedding_profiles(embedding_profile_id),
  embedding_model text NOT NULL,
  embedding_dim integer NOT NULL,
  embedding vector NOT NULL,
  text_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE autoskill.embeddings
  ADD COLUMN IF NOT EXISTS embedding_profile_id uuid
  REFERENCES autoskill.embedding_profiles(embedding_profile_id);

DROP INDEX IF EXISTS autoskill.embeddings_hnsw_cosine_idx;

ALTER TABLE autoskill.embeddings
  ALTER COLUMN embedding TYPE vector
  USING embedding::vector;

ALTER TABLE autoskill.embeddings
  DROP CONSTRAINT IF EXISTS embeddings_object_type_object_id_embedding_model_key;

CREATE UNIQUE INDEX IF NOT EXISTS embeddings_object_model_unique_idx
  ON autoskill.embeddings(workspace_id, object_type, object_id, embedding_model)
  WHERE embedding_profile_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS embeddings_object_profile_unique_idx
  ON autoskill.embeddings(workspace_id, object_type, object_id, embedding_profile_id)
  WHERE embedding_profile_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS autoskill.schedules (
  schedule_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  name text NOT NULL,
  job_kind text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  interval_seconds integer NOT NULL,
  next_run_at timestamptz NOT NULL,
  misfire_policy text NOT NULL DEFAULT 'coalesce',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(workspace_id, name)
);

ALTER TABLE autoskill.schedules
  ADD COLUMN IF NOT EXISTS misfire_policy text NOT NULL DEFAULT 'coalesce';

ALTER TABLE autoskill.schedules
  DROP CONSTRAINT IF EXISTS schedules_misfire_policy_check;

ALTER TABLE autoskill.schedules
  ADD CONSTRAINT schedules_misfire_policy_check
  CHECK (misfire_policy IN ('coalesce','catch_up_limited','skip','immediate'));

CREATE TABLE IF NOT EXISTS autoskill.jobs (
  job_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  trace_id uuid NOT NULL DEFAULT gen_random_uuid(),
  span_id uuid NOT NULL DEFAULT gen_random_uuid(),
  parent_span_id uuid,
  job_kind text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  priority integer NOT NULL DEFAULT 100,
  lease_owner text,
  lease_expires_at timestamptz,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  available_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, idempotency_key)
);

ALTER TABLE autoskill.jobs
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.jobs
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.jobs
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

UPDATE autoskill.jobs
SET trace_id = COALESCE(trace_id, gen_random_uuid()),
    span_id = COALESCE(span_id, gen_random_uuid())
WHERE trace_id IS NULL
   OR span_id IS NULL;

ALTER TABLE autoskill.jobs
  ALTER COLUMN trace_id SET DEFAULT gen_random_uuid(),
  ALTER COLUMN trace_id SET NOT NULL,
  ALTER COLUMN span_id SET DEFAULT gen_random_uuid(),
  ALTER COLUMN span_id SET NOT NULL;

CREATE TABLE IF NOT EXISTS autoskill.job_attempts (
  job_attempt_id uuid PRIMARY KEY,
  job_id uuid NOT NULL REFERENCES autoskill.jobs(job_id),
  attempt_number integer NOT NULL,
  worker_id text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status text NOT NULL,
  error text
);

CREATE TABLE IF NOT EXISTS autoskill.worker_heartbeats (
  worker_id text PRIMARY KEY,
  pool text NOT NULL,
  concurrency integer NOT NULL DEFAULT 1,
  status text NOT NULL,
  current_job_id uuid REFERENCES autoskill.jobs(job_id),
  summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS worker_heartbeats_last_seen_idx
  ON autoskill.worker_heartbeats(last_seen_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.evolution_transactions (
  evolution_transaction_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  action text NOT NULL,
  actor text NOT NULL DEFAULT 'autoskill-sidecar',
  status text NOT NULL DEFAULT 'started',
  cause jsonb NOT NULL DEFAULT '{}'::jsonb,
  rollback_of_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  started_at timestamptz NOT NULL DEFAULT now(),
  committed_at timestamptz,
  rolled_back_at timestamptz
);

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS transaction_kind text;

UPDATE autoskill.evolution_transactions
SET transaction_kind = action
WHERE transaction_kind IS NULL;

ALTER TABLE autoskill.evolution_transactions
  ALTER COLUMN transaction_kind SET NOT NULL;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS idempotency_key text;

UPDATE autoskill.evolution_transactions
SET idempotency_key = evolution_transaction_id::text
WHERE idempotency_key IS NULL;

ALTER TABLE autoskill.evolution_transactions
  ALTER COLUMN idempotency_key SET NOT NULL;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS plan_hash text;

UPDATE autoskill.evolution_transactions
SET plan_hash = encode(digest(cause::text, 'sha256'), 'hex')
WHERE plan_hash IS NULL;

ALTER TABLE autoskill.evolution_transactions
  ALTER COLUMN plan_hash SET NOT NULL;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS source_evidence_ids uuid[] NOT NULL DEFAULT '{}';

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS source_memory_ids uuid[] NOT NULL DEFAULT '{}';

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS created_by_job_id uuid REFERENCES autoskill.jobs(job_id);

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS policy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE autoskill.evolution_transactions
  ADD COLUMN IF NOT EXISTS metrics jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS evolution_transactions_workspace_idempotency_idx
  ON autoskill.evolution_transactions(workspace_id, idempotency_key);

CREATE TABLE IF NOT EXISTS autoskill.evolution_transaction_items (
  transaction_item_id uuid PRIMARY KEY,
  evolution_transaction_id uuid NOT NULL REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  item_kind text NOT NULL,
  item_id uuid,
  relative_path text,
  before_hash text,
  after_hash text,
  activation_state text NOT NULL,
  rollback_action jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.canary_results (
  canary_result_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  evolution_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  status text NOT NULL,
  critical boolean NOT NULL DEFAULT false,
  reason text,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS canary_results_skill_observed_idx
  ON autoskill.canary_results(skill_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.transaction_artifacts (
  transaction_artifact_id uuid PRIMARY KEY,
  evolution_transaction_id uuid NOT NULL REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  artifact_kind text NOT NULL,
  artifact_id uuid,
  path text,
  sha256 text,
  state text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.provenance_edges (
  provenance_edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_kind text NOT NULL,
  source_id uuid NOT NULL,
  derived_kind text NOT NULL,
  derived_id uuid NOT NULL,
  relation text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS provenance_source_idx
  ON autoskill.provenance_edges(workspace_id, source_kind, source_id);

CREATE INDEX IF NOT EXISTS provenance_derived_idx
  ON autoskill.provenance_edges(workspace_id, derived_kind, derived_id);

CREATE UNIQUE INDEX IF NOT EXISTS provenance_edges_unique_idx
  ON autoskill.provenance_edges(
    workspace_id,
    source_kind,
    source_id,
    derived_kind,
    derived_id,
    relation
  );

CREATE TABLE IF NOT EXISTS autoskill.evidence_maturity (
  evidence_maturity_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  object_type text NOT NULL,
  object_id uuid NOT NULL,
  maturity text NOT NULL,
  basis jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, object_type, object_id)
);

CREATE TABLE IF NOT EXISTS autoskill.action_attribution_checks (
  action_attribution_check_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  tool_call_id text,
  action_kind text NOT NULL,
  risk_tier text NOT NULL,
  user_intent_hash text,
  contributing_skill_ids uuid[] NOT NULL DEFAULT '{}',
  contributing_memory_ids uuid[] NOT NULL DEFAULT '{}',
  contributing_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  counterfactual_kind text,
  verdict text NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.attribution_events (
  attribution_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  action_kind text NOT NULL,
  risk_level text NOT NULL,
  user_intent_hash text,
  skill_ids uuid[] NOT NULL DEFAULT '{}',
  memory_ids uuid[] NOT NULL DEFAULT '{}',
  retrieved_artifact_ids uuid[] NOT NULL DEFAULT '{}',
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  outcome text CHECK (
    outcome IS NULL OR outcome IN (
      'skill_helped',
      'skill_hurt',
      'skill_ignored',
      'skill_missing',
      'skill_shadowed',
      'agent_solved_independently',
      'tool_failed_independent',
      'environment_drifted',
      'user_correction_changed_requirements',
      'unknown'
    )
  ),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

UPDATE autoskill.attribution_events
SET metadata = metadata || jsonb_build_object('legacy_outcome', outcome),
    outcome = CASE replace(replace(lower(trim(outcome)), '-', '_'), ' ', '_')
      WHEN 'skill_helped' THEN 'skill_helped'
      WHEN 'helped' THEN 'skill_helped'
      WHEN 'success' THEN 'skill_helped'
      WHEN 'succeeded' THEN 'skill_helped'
      WHEN 'useful' THEN 'skill_helped'
      WHEN 'passed' THEN 'skill_helped'
      WHEN 'skill_was_helpful' THEN 'skill_helped'
      WHEN 'skill_was_used' THEN 'skill_helped'
      WHEN 'skill_hurt' THEN 'skill_hurt'
      WHEN 'hurt' THEN 'skill_hurt'
      WHEN 'failed' THEN 'skill_hurt'
      WHEN 'failure' THEN 'skill_hurt'
      WHEN 'harmful' THEN 'skill_hurt'
      WHEN 'skill_was_harmful' THEN 'skill_hurt'
      WHEN 'skill_ignored' THEN 'skill_ignored'
      WHEN 'ignored' THEN 'skill_ignored'
      WHEN 'unused' THEN 'skill_ignored'
      WHEN 'ignored_load' THEN 'skill_ignored'
      WHEN 'false_positive_load' THEN 'skill_ignored'
      WHEN 'skill_was_ignored' THEN 'skill_ignored'
      WHEN 'skill_missing' THEN 'skill_missing'
      WHEN 'missing' THEN 'skill_missing'
      WHEN 'missing_skill' THEN 'skill_missing'
      WHEN 'skill_was_missing' THEN 'skill_missing'
      WHEN 'skill_shadowed' THEN 'skill_shadowed'
      WHEN 'shadowed' THEN 'skill_shadowed'
      WHEN 'wrong_skill' THEN 'skill_shadowed'
      WHEN 'skill_shadowed_another_skill' THEN 'skill_shadowed'
      WHEN 'agent_solved_independently' THEN 'agent_solved_independently'
      WHEN 'agent_solved' THEN 'agent_solved_independently'
      WHEN 'solved_independently' THEN 'agent_solved_independently'
      WHEN 'no_skill_helped' THEN 'agent_solved_independently'
      WHEN 'no_skill_success' THEN 'agent_solved_independently'
      WHEN 'tool_failed_independent' THEN 'tool_failed_independent'
      WHEN 'tool_failed' THEN 'tool_failed_independent'
      WHEN 'tool_failure' THEN 'tool_failed_independent'
      WHEN 'tool_failed_independent_of_skill' THEN 'tool_failed_independent'
      WHEN 'environment_drifted' THEN 'environment_drifted'
      WHEN 'environment_drift' THEN 'environment_drifted'
      WHEN 'env_drifted' THEN 'environment_drifted'
      WHEN 'drift' THEN 'environment_drifted'
      WHEN 'user_correction_changed_requirements' THEN 'user_correction_changed_requirements'
      WHEN 'requirement_changed' THEN 'user_correction_changed_requirements'
      WHEN 'requirements_changed' THEN 'user_correction_changed_requirements'
      WHEN 'user_correction' THEN 'user_correction_changed_requirements'
      WHEN 'user_correction_changed_requirement' THEN 'user_correction_changed_requirements'
      WHEN 'unknown' THEN 'unknown'
      ELSE 'unknown'
    END
WHERE outcome IS NOT NULL
  AND outcome NOT IN (
    'skill_helped',
    'skill_hurt',
    'skill_ignored',
    'skill_missing',
    'skill_shadowed',
    'agent_solved_independently',
    'tool_failed_independent',
    'environment_drifted',
    'user_correction_changed_requirements',
    'unknown'
  );

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'autoskill.attribution_events'::regclass
      AND conname = 'attribution_events_outcome_check'
  ) THEN
    ALTER TABLE autoskill.attribution_events
      ADD CONSTRAINT attribution_events_outcome_check CHECK (
        outcome IS NULL OR outcome IN (
          'skill_helped',
          'skill_hurt',
          'skill_ignored',
          'skill_missing',
          'skill_shadowed',
          'agent_solved_independently',
          'tool_failed_independent',
          'environment_drifted',
          'user_correction_changed_requirements',
          'unknown'
        )
      );
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS autoskill.skill_attributions (
  attribution_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid,
  skill_version_id uuid,
  session_id text,
  turn_id text,
  retrieval_event_id uuid,
  attribution_kind text NOT NULL CHECK (
    attribution_kind IN (
      'helped',
      'hurt',
      'ignored',
      'missing',
      'shadowed',
      'misused',
      'environment_failure',
      'tool_failure',
      'agent_exploration',
      'unknown'
    )
  ),
  confidence numeric NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
  outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  source_kind text NOT NULL,
  source_record_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_kind, source_record_id, skill_id)
);

CREATE OR REPLACE FUNCTION autoskill.sync_skill_attribution_from_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  mapped_kind text;
  source_skill_ids uuid[];
  source_skill_id uuid;
  source_confidence numeric;
  source_skill_version_id uuid;
  source_retrieval_event_id uuid;
BEGIN
  DELETE FROM autoskill.skill_attributions
  WHERE source_kind = 'attribution_event'
    AND source_record_id = NEW.attribution_event_id;

  mapped_kind := CASE NEW.outcome
    WHEN 'skill_helped' THEN 'helped'
    WHEN 'skill_hurt' THEN 'hurt'
    WHEN 'skill_ignored' THEN 'ignored'
    WHEN 'skill_missing' THEN 'missing'
    WHEN 'skill_shadowed' THEN 'shadowed'
    WHEN 'tool_failed_independent' THEN 'tool_failure'
    WHEN 'environment_drifted' THEN 'environment_failure'
    WHEN 'agent_solved_independently' THEN 'agent_exploration'
    ELSE 'unknown'
  END;

  source_skill_ids := CASE
    WHEN cardinality(NEW.skill_ids) > 0 THEN NEW.skill_ids
    ELSE ARRAY[NULL::uuid]
  END;
  source_confidence := CASE
    WHEN NEW.metadata->>'confidence' ~ '^[0-9]+(\.[0-9]+)?$'
    THEN LEAST(1, GREATEST(0, (NEW.metadata->>'confidence')::numeric))
    ELSE 0
  END;
  source_skill_version_id := CASE
    WHEN NEW.metadata->>'skill_version_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (NEW.metadata->>'skill_version_id')::uuid
    ELSE NULL
  END;
  source_retrieval_event_id := CASE
    WHEN NEW.metadata->>'retrieval_event_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (NEW.metadata->>'retrieval_event_id')::uuid
    ELSE NULL
  END;

  FOREACH source_skill_id IN ARRAY source_skill_ids LOOP
    INSERT INTO autoskill.skill_attributions (
      attribution_id,
      workspace_id,
      skill_id,
      skill_version_id,
      session_id,
      turn_id,
      retrieval_event_id,
      attribution_kind,
      confidence,
      outcome,
      evidence_ids,
      source_kind,
      source_record_id,
      created_at
    )
    VALUES (
      autoskill.stable_uuid_from_text(
        'attribution_event:' || NEW.attribution_event_id::text || ':' || coalesce(source_skill_id::text, 'none')
      ),
      NEW.workspace_id,
      source_skill_id,
      source_skill_version_id,
      NEW.session_id,
      NEW.turn_id,
      source_retrieval_event_id,
      mapped_kind,
      source_confidence,
      jsonb_strip_nulls(jsonb_build_object(
        'source', 'attribution_events',
        'action_kind', NEW.action_kind,
        'risk_level', NEW.risk_level,
        'legacy_outcome', NEW.outcome,
        'skill_ids', NEW.skill_ids,
        'memory_ids', NEW.memory_ids,
        'retrieved_artifact_ids', NEW.retrieved_artifact_ids,
        'broker_policy_version_id', NEW.broker_policy_version_id,
        'metadata', NEW.metadata
      )),
      '{}',
      'attribution_event',
      NEW.attribution_event_id,
      NEW.created_at
    )
    ON CONFLICT (attribution_id) DO NOTHING;
  END LOOP;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION autoskill.sync_skill_attribution_from_action_check()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  mapped_kind text;
  source_skill_ids uuid[];
  source_skill_id uuid;
  source_confidence numeric;
  source_skill_version_id uuid;
  source_retrieval_event_id uuid;
BEGIN
  DELETE FROM autoskill.skill_attributions
  WHERE source_kind = 'action_attribution_check'
    AND source_record_id = NEW.action_attribution_check_id;

  mapped_kind := CASE NEW.verdict
    WHEN 'supported' THEN 'helped'
    WHEN 'unsupported' THEN 'hurt'
    ELSE 'unknown'
  END;
  source_skill_ids := CASE
    WHEN cardinality(NEW.contributing_skill_ids) > 0 THEN NEW.contributing_skill_ids
    ELSE ARRAY[NULL::uuid]
  END;
  source_confidence := CASE
    WHEN NEW.metrics->>'confidence' ~ '^[0-9]+(\.[0-9]+)?$'
    THEN LEAST(1, GREATEST(0, (NEW.metrics->>'confidence')::numeric))
    ELSE 0
  END;
  source_skill_version_id := CASE
    WHEN NEW.metrics->>'skill_version_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (NEW.metrics->>'skill_version_id')::uuid
    ELSE NULL
  END;
  source_retrieval_event_id := CASE
    WHEN NEW.metrics->>'retrieval_event_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (NEW.metrics->>'retrieval_event_id')::uuid
    ELSE NULL
  END;

  FOREACH source_skill_id IN ARRAY source_skill_ids LOOP
    INSERT INTO autoskill.skill_attributions (
      attribution_id,
      workspace_id,
      skill_id,
      skill_version_id,
      session_id,
      turn_id,
      retrieval_event_id,
      attribution_kind,
      confidence,
      outcome,
      evidence_ids,
      source_kind,
      source_record_id,
      created_at
    )
    VALUES (
      autoskill.stable_uuid_from_text(
        'action_attribution_check:' || NEW.action_attribution_check_id::text || ':' || coalesce(source_skill_id::text, 'none')
      ),
      NEW.workspace_id,
      source_skill_id,
      source_skill_version_id,
      NEW.session_id,
      NEW.turn_id,
      source_retrieval_event_id,
      mapped_kind,
      source_confidence,
      jsonb_strip_nulls(jsonb_build_object(
        'source', 'action_attribution_checks',
        'tool_call_id', NEW.tool_call_id,
        'action_kind', NEW.action_kind,
        'risk_tier', NEW.risk_tier,
        'user_intent_hash', NEW.user_intent_hash,
        'contributing_skill_ids', NEW.contributing_skill_ids,
        'contributing_memory_ids', NEW.contributing_memory_ids,
        'counterfactual_kind', NEW.counterfactual_kind,
        'verdict', NEW.verdict,
        'metrics', NEW.metrics
      )),
      NEW.contributing_evidence_ids,
      'action_attribution_check',
      NEW.action_attribution_check_id,
      NEW.created_at
    )
    ON CONFLICT (attribution_id) DO NOTHING;
  END LOOP;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS attribution_events_sync_skill_attributions ON autoskill.attribution_events;
CREATE TRIGGER attribution_events_sync_skill_attributions
AFTER INSERT OR UPDATE ON autoskill.attribution_events
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_attribution_from_event();

DROP TRIGGER IF EXISTS action_attribution_checks_sync_skill_attributions ON autoskill.action_attribution_checks;
CREATE TRIGGER action_attribution_checks_sync_skill_attributions
AFTER INSERT OR UPDATE ON autoskill.action_attribution_checks
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_skill_attribution_from_action_check();

INSERT INTO autoskill.skill_attributions (
  attribution_id,
  workspace_id,
  skill_id,
  skill_version_id,
  session_id,
  turn_id,
  retrieval_event_id,
  attribution_kind,
  confidence,
  outcome,
  evidence_ids,
  source_kind,
  source_record_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text(
    'attribution_event:' || attribution_event_id::text || ':' || coalesce(source_skill_id::text, 'none')
  ),
  workspace_id,
  source_skill_id,
  CASE
    WHEN metadata->>'skill_version_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (metadata->>'skill_version_id')::uuid
    ELSE NULL
  END,
  session_id,
  turn_id,
  CASE
    WHEN metadata->>'retrieval_event_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (metadata->>'retrieval_event_id')::uuid
    ELSE NULL
  END,
  CASE outcome
    WHEN 'skill_helped' THEN 'helped'
    WHEN 'skill_hurt' THEN 'hurt'
    WHEN 'skill_ignored' THEN 'ignored'
    WHEN 'skill_missing' THEN 'missing'
    WHEN 'skill_shadowed' THEN 'shadowed'
    WHEN 'tool_failed_independent' THEN 'tool_failure'
    WHEN 'environment_drifted' THEN 'environment_failure'
    WHEN 'agent_solved_independently' THEN 'agent_exploration'
    ELSE 'unknown'
  END,
  CASE
    WHEN metadata->>'confidence' ~ '^[0-9]+(\.[0-9]+)?$'
    THEN LEAST(1, GREATEST(0, (metadata->>'confidence')::numeric))
    ELSE 0
  END,
  jsonb_strip_nulls(jsonb_build_object(
    'source', 'attribution_events',
    'action_kind', action_kind,
    'risk_level', risk_level,
    'legacy_outcome', outcome,
    'skill_ids', skill_ids,
    'memory_ids', memory_ids,
    'retrieved_artifact_ids', retrieved_artifact_ids,
    'broker_policy_version_id', broker_policy_version_id,
    'metadata', metadata
  )),
  '{}',
  'attribution_event',
  attribution_event_id,
  created_at
FROM autoskill.attribution_events
CROSS JOIN LATERAL unnest(
  CASE
    WHEN cardinality(skill_ids) > 0 THEN skill_ids
    ELSE ARRAY[NULL::uuid]
  END
) AS source_skill_id
ON CONFLICT (attribution_id) DO NOTHING;

INSERT INTO autoskill.skill_attributions (
  attribution_id,
  workspace_id,
  skill_id,
  skill_version_id,
  session_id,
  turn_id,
  retrieval_event_id,
  attribution_kind,
  confidence,
  outcome,
  evidence_ids,
  source_kind,
  source_record_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text(
    'action_attribution_check:' || action_attribution_check_id::text || ':' || coalesce(source_skill_id::text, 'none')
  ),
  workspace_id,
  source_skill_id,
  CASE
    WHEN metrics->>'skill_version_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (metrics->>'skill_version_id')::uuid
    ELSE NULL
  END,
  session_id,
  turn_id,
  CASE
    WHEN metrics->>'retrieval_event_id' ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN (metrics->>'retrieval_event_id')::uuid
    ELSE NULL
  END,
  CASE verdict
    WHEN 'supported' THEN 'helped'
    WHEN 'unsupported' THEN 'hurt'
    ELSE 'unknown'
  END,
  CASE
    WHEN metrics->>'confidence' ~ '^[0-9]+(\.[0-9]+)?$'
    THEN LEAST(1, GREATEST(0, (metrics->>'confidence')::numeric))
    ELSE 0
  END,
  jsonb_strip_nulls(jsonb_build_object(
    'source', 'action_attribution_checks',
    'tool_call_id', tool_call_id,
    'action_kind', action_kind,
    'risk_tier', risk_tier,
    'user_intent_hash', user_intent_hash,
    'contributing_skill_ids', contributing_skill_ids,
    'contributing_memory_ids', contributing_memory_ids,
    'counterfactual_kind', counterfactual_kind,
    'verdict', verdict,
    'metrics', metrics
  )),
  contributing_evidence_ids,
  'action_attribution_check',
  action_attribution_check_id,
  created_at
FROM autoskill.action_attribution_checks
CROSS JOIN LATERAL unnest(
  CASE
    WHEN cardinality(contributing_skill_ids) > 0 THEN contributing_skill_ids
    ELSE ARRAY[NULL::uuid]
  END
) AS source_skill_id
ON CONFLICT (attribution_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS skill_attributions_workspace_skill_idx
  ON autoskill.skill_attributions (workspace_id, skill_id, attribution_kind, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.historical_import_sources (
  historical_import_source_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_kind text NOT NULL CHECK (
    source_kind IN (
      'session_store','transcript','transcript_corpus','trajectory','compaction_summary',
      'workspace_memory','workspace_context','task_record','taskflow_record',
      'plugin_hook_manifest','plugin_manifest','plugin_session_state','plugin_source',
      'queued_injection','active_memory',
      'diagnostics_export','media_artifact','observability_export',
      'channel_media','transcription',
      'preprocessing_artifact','existing_skill','other'
    )
  ),
  source_key text NOT NULL,
  fingerprint text NOT NULL,
  parser_version text NOT NULL,
  redaction_policy_version text NOT NULL,
  trust_level text NOT NULL DEFAULT 'tainted'
    CHECK (trust_level IN ('trusted','tainted','untrusted')),
  taint jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'discovered'
    CHECK (status IN ('discovered','inventory_only','imported','revoked')),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  imported_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, source_kind, source_key, fingerprint)
);

CREATE TABLE IF NOT EXISTS autoskill.historical_import_chunks (
  historical_import_chunk_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  historical_import_source_id uuid NOT NULL
    REFERENCES autoskill.historical_import_sources(historical_import_source_id),
  item_key text NOT NULL,
  chunk_index integer NOT NULL CHECK (chunk_index >= 0),
  source_item_locator_hash text,
  source_item_kind text,
  item_key_hash text,
  line_range_hash text,
  record_index integer,
  chunk_kind text NOT NULL DEFAULT 'redacted_text',
  content_hash text NOT NULL,
  redacted_text text NOT NULL,
  token_estimate integer NOT NULL DEFAULT 0 CHECK (token_estimate >= 0),
  parser_version text NOT NULL,
  redaction_policy_version text NOT NULL,
  trust_level text NOT NULL DEFAULT 'tainted'
    CHECK (trust_level IN ('trusted','tainted','untrusted')),
  taint jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'observed'
    CHECK (status IN ('observed','revoked')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, historical_import_source_id, item_key, chunk_index, content_hash)
);

ALTER TABLE autoskill.historical_import_chunks
  ADD COLUMN IF NOT EXISTS source_item_locator_hash text;
ALTER TABLE autoskill.historical_import_chunks
  ADD COLUMN IF NOT EXISTS source_item_kind text;
ALTER TABLE autoskill.historical_import_chunks
  ADD COLUMN IF NOT EXISTS item_key_hash text;
ALTER TABLE autoskill.historical_import_chunks
  ADD COLUMN IF NOT EXISTS line_range_hash text;
ALTER TABLE autoskill.historical_import_chunks
  ADD COLUMN IF NOT EXISTS record_index integer;

UPDATE autoskill.historical_import_chunks
SET source_item_locator_hash = COALESCE(
      source_item_locator_hash,
      metadata #>> '{source_item,locator_hash}',
      metadata #>> '{lineage,source_item_locator_hash}'
    ),
    source_item_kind = COALESCE(
      source_item_kind,
      metadata #>> '{source_item,item_kind}'
    ),
    item_key_hash = COALESCE(
      item_key_hash,
      metadata #>> '{source_item,item_key_hash}',
      metadata #>> '{lineage,item_key_hash}'
    ),
    line_range_hash = COALESCE(
      line_range_hash,
      metadata #>> '{source_item,line_range_hash}'
    ),
    record_index = COALESCE(
      record_index,
      NULLIF(metadata #>> '{source_item,record_index}', '')::integer
    )
WHERE source_item_locator_hash IS NULL
   OR source_item_kind IS NULL
   OR item_key_hash IS NULL
   OR line_range_hash IS NULL
   OR record_index IS NULL;

CREATE INDEX IF NOT EXISTS idx_historical_import_sources_workspace_status
  ON autoskill.historical_import_sources(workspace_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_historical_import_chunks_source_item_locator
  ON autoskill.historical_import_chunks(workspace_id, source_item_locator_hash)
  WHERE source_item_locator_hash IS NOT NULL;

ALTER TABLE autoskill.historical_import_sources
  DROP CONSTRAINT IF EXISTS historical_import_sources_source_kind_check;

ALTER TABLE autoskill.historical_import_sources
  ADD CONSTRAINT historical_import_sources_source_kind_check CHECK (
    source_kind IN (
      'session_store','transcript','transcript_corpus','trajectory','compaction_summary',
      'workspace_memory','workspace_context','task_record','taskflow_record',
      'plugin_hook_manifest','plugin_manifest','plugin_session_state','plugin_source',
      'queued_injection','active_memory',
      'diagnostics_export','media_artifact','observability_export',
      'channel_media','transcription',
      'preprocessing_artifact','existing_skill','other'
    )
  );

CREATE INDEX IF NOT EXISTS idx_historical_import_chunks_source
  ON autoskill.historical_import_chunks(historical_import_source_id, item_key, chunk_index);

CREATE TABLE IF NOT EXISTS autoskill.historical_import_runs (
  historical_import_run_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  run_kind text NOT NULL,
  idempotency_key text NOT NULL,
  status text NOT NULL CHECK (
    status IN ('running','completed','failed','cancelled')
  ),
  checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb,
  stats jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_historical_import_runs_workspace_status
  ON autoskill.historical_import_runs(workspace_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.memory_quarantine (
  quarantine_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_object_type text NOT NULL,
  source_object_id uuid NOT NULL,
  proposed_memory jsonb NOT NULL,
  taint jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','approved','rejected','expired')),
  scanner_findings jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS autoskill.control_flow_events (
  control_flow_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  run_id text,
  source_kind text CHECK (
    source_kind IN (
      'memory','skill','broker','tool','user','system','external_skill_inventory'
    )
  ),
  source_id uuid,
  decision jsonb NOT NULL DEFAULT '{}'::jsonb,
  influence_kind text NOT NULL,
  influenced_object_type text,
  influenced_object_id uuid,
  source_object_type text,
  source_object_id uuid,
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE autoskill.control_flow_events
  ADD COLUMN IF NOT EXISTS run_id text;

ALTER TABLE autoskill.control_flow_events
  ADD COLUMN IF NOT EXISTS source_kind text;

ALTER TABLE autoskill.control_flow_events
  ADD COLUMN IF NOT EXISTS source_id uuid;

ALTER TABLE autoskill.control_flow_events
  ADD COLUMN IF NOT EXISTS decision jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE autoskill.control_flow_events
  ALTER COLUMN influenced_object_type DROP NOT NULL;

CREATE TABLE IF NOT EXISTS autoskill.revocation_requests (
  revocation_request_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  trace_id uuid,
  span_id uuid,
  parent_span_id uuid,
  request_kind text NOT NULL,
  root_object_type text NOT NULL,
  root_object_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  traversal_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_job_id uuid REFERENCES autoskill.jobs(job_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

ALTER TABLE autoskill.revocation_requests
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.revocation_requests
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.revocation_requests
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

CREATE TABLE IF NOT EXISTS autoskill.audit_records (
  audit_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  action text NOT NULL,
  actor text NOT NULL,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  previous_hash text,
  audit_hash text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS autoskill.audit_log (
  audit_id uuid PRIMARY KEY,
  workspace_id uuid REFERENCES autoskill.workspaces(workspace_id),
  actor text NOT NULL,
  action text NOT NULL,
  object_type text NOT NULL,
  object_id uuid,
  before_hash text,
  after_hash text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  prev_audit_hash text,
  audit_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION autoskill.sync_audit_log_from_record()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.audit_log (
    audit_id,
    workspace_id,
    actor,
    action,
    object_type,
    object_id,
    before_hash,
    after_hash,
    payload,
    prev_audit_hash,
    audit_hash,
    created_at
  )
  VALUES (
    NEW.audit_id,
    NEW.workspace_id,
    NEW.actor,
    NEW.action,
    NEW.subject_type,
    CASE
      WHEN NEW.subject_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
      THEN NEW.subject_id::uuid
      ELSE NULL
    END,
    NEW.previous_hash,
    NEW.audit_hash,
    NEW.details || jsonb_build_object('legacy_subject_id', NEW.subject_id),
    NEW.previous_hash,
    NEW.audit_hash,
    NEW.occurred_at
  )
  ON CONFLICT (audit_id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    actor = EXCLUDED.actor,
    action = EXCLUDED.action,
    object_type = EXCLUDED.object_type,
    object_id = EXCLUDED.object_id,
    before_hash = EXCLUDED.before_hash,
    after_hash = EXCLUDED.after_hash,
    payload = EXCLUDED.payload,
    prev_audit_hash = EXCLUDED.prev_audit_hash,
    audit_hash = EXCLUDED.audit_hash,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS audit_records_sync_audit_log ON autoskill.audit_records;
CREATE TRIGGER audit_records_sync_audit_log
AFTER INSERT OR UPDATE ON autoskill.audit_records
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_audit_log_from_record();

INSERT INTO autoskill.audit_log (
  audit_id,
  workspace_id,
  actor,
  action,
  object_type,
  object_id,
  before_hash,
  after_hash,
  payload,
  prev_audit_hash,
  audit_hash,
  created_at
)
SELECT
  audit_id,
  workspace_id,
  actor,
  action,
  subject_type,
  CASE
    WHEN subject_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    THEN subject_id::uuid
    ELSE NULL
  END,
  previous_hash,
  audit_hash,
  details || jsonb_build_object('legacy_subject_id', subject_id),
  previous_hash,
  audit_hash,
  occurred_at
FROM autoskill.audit_records
ON CONFLICT (audit_id) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  actor = EXCLUDED.actor,
  action = EXCLUDED.action,
  object_type = EXCLUDED.object_type,
  object_id = EXCLUDED.object_id,
  before_hash = EXCLUDED.before_hash,
  after_hash = EXCLUDED.after_hash,
  payload = EXCLUDED.payload,
  prev_audit_hash = EXCLUDED.prev_audit_hash,
  audit_hash = EXCLUDED.audit_hash,
  created_at = EXCLUDED.created_at;

CREATE INDEX IF NOT EXISTS audit_log_workspace_created_idx
  ON autoskill.audit_log (workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.skill_utility_rollups (
  skill_utility_rollup_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  helped_count integer NOT NULL DEFAULT 0,
  hurt_count integer NOT NULL DEFAULT 0,
  shadow_count integer NOT NULL DEFAULT 0,
  retrieval_count integer NOT NULL DEFAULT 0,
  canary_failure_count integer NOT NULL DEFAULT 0,
  utility_score numeric NOT NULL DEFAULT 0,
  features jsonb NOT NULL DEFAULT '{}'::jsonb,
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, skill_id)
);

CREATE TABLE IF NOT EXISTS autoskill.curation_actions (
  curation_action_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  action text NOT NULL,
  status text NOT NULL,
  reason text NOT NULL,
  features jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_job_id uuid REFERENCES autoskill.jobs(job_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS skill_utility_rollups_score_idx
  ON autoskill.skill_utility_rollups(workspace_id, utility_score);

CREATE INDEX IF NOT EXISTS curation_actions_workspace_time_idx
  ON autoskill.curation_actions(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.environment_contracts (
  environment_contract_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  contract_type text NOT NULL,
  name text NOT NULL,
  expectation text NOT NULL,
  validation_method text NOT NULL DEFAULT 'manual',
  status text NOT NULL DEFAULT 'unknown',
  severity text NOT NULL DEFAULT 'medium',
  last_checked_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, skill_version_id, name, expectation)
);

CREATE TABLE IF NOT EXISTS autoskill.drift_events (
  drift_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  environment_contract_id uuid NOT NULL REFERENCES autoskill.environment_contracts(environment_contract_id),
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  status text NOT NULL,
  reason text NOT NULL,
  repair_candidate jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.trace_spans (
  trace_id uuid NOT NULL,
  span_id uuid PRIMARY KEY,
  parent_span_id uuid REFERENCES autoskill.trace_spans(span_id),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  operation_name text NOT NULL,
  operation_kind text NOT NULL CHECK (operation_kind IN (
    'plugin_capture','ingest','redaction','evidence','memory','retrieval','broker',
    'llm_call','embedding_call','scanner','evaluator','compiler','writer',
    'scheduler','job','evolution','rollback','archive','promotion','tool_attribution'
  )),
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz,
  status text NOT NULL CHECK (
    status IN ('running','ok','error','timeout','denied','quarantined','rolled_back')
  ),
  safe_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  object_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.trace_span_links (
  from_span_id uuid NOT NULL REFERENCES autoskill.trace_spans(span_id),
  to_span_id uuid NOT NULL REFERENCES autoskill.trace_spans(span_id),
  link_type text NOT NULL CHECK (
    link_type IN ('batch_input','causal','rollback','revocation','trial','counterfactual')
  ),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (from_span_id, to_span_id, link_type)
);

CREATE TABLE IF NOT EXISTS autoskill.admin_live_event_outbox (
  seq bigserial PRIMARY KEY,
  kind text NOT NULL,
  component_id text,
  trace_id text,
  object_type text,
  object_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  redaction_level text NOT NULL DEFAULT 'default',
  created_at timestamptz NOT NULL DEFAULT now(),
  delivered_hint boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS autoskill.admin_component_catalog (
  component_id text PRIMARY KEY,
  display_name text NOT NULL,
  subsystem_ids text[] NOT NULL DEFAULT '{}',
  purpose text NOT NULL,
  object_kinds text[] NOT NULL DEFAULT '{}',
  metric_family text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  seeded_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_subsystem_catalog (
  subsystem_id text PRIMARY KEY,
  display_name text NOT NULL,
  station_ids text[] NOT NULL DEFAULT '{}',
  diagnostic_questions text[] NOT NULL DEFAULT '{}',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  seeded_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO autoskill.admin_component_catalog (
  component_id,
  display_name,
  subsystem_ids,
  purpose,
  object_kinds,
  metric_family
) VALUES
  ('openclaw_live_capture', 'OpenClaw live capture', ARRAY['capture_bootstrap'], 'Plugin hook and SDK-event capture from active OpenClaw sessions.', ARRAY['captured_event', 'hook_matrix', 'session_coverage'], 'ingest'),
  ('historical_ingestion', 'Historical bootstrap', ARRAY['capture_bootstrap'], 'Discovery and ingestion of existing transcripts, trajectories, memory files, task records, and skills.', ARRAY['historical_import_run', 'historical_source', 'parser_finding'], 'historical'),
  ('redaction_taint', 'Redaction + taint', ARRAY['capture_bootstrap'], 'Sensitive-content reduction, taint propagation, confidence, and storage eligibility.', ARRAY['redaction_finding', 'taint_graph', 'revocation_path'], 'redaction'),
  ('raw_evidence_vault', 'Raw-evidence vault', ARRAY['autonomy_adjudication'], 'Governed full-fidelity evidence retention, raw/declassified access policy, raw-access audit, retention, revocation, and derived-data traversal.', ARRAY['raw_vault_record', 'declassification_report', 'access_audit'], 'vault'),
  ('evidence_fidelity', 'Evidence fidelity', ARRAY['learning_memory', 'autonomy_adjudication'], 'Evidence-fidelity tiers, degraded-autonomy states, and supported decision-family matrix.', ARRAY['evidence_fidelity_status', 'source_item', 'unsupported_decision_family'], 'fidelity'),
  ('spool_ingest', 'Spool + ingest', ARRAY['capture_bootstrap'], 'Plugin spool, sidecar ingest API, idempotency, and normalized forwarding.', ARRAY['spool_record', 'ingest_batch', 'normalization_result'], 'spool'),
  ('event_normalization', 'Event normalization', ARRAY['capture_bootstrap'], 'Canonical events, chunks, spans, and evidence inputs.', ARRAY['canonical_event', 'span', 'evidence_input'], 'ingest'),
  ('evidence_memory', 'Evidence + memory', ARRAY['learning_memory'], 'Evidence extraction, memory derivation, provenance, maturity, and poisoning defenses.', ARRAY['evidence_cluster', 'memory_record', 'provenance_path'], 'evidence'),
  ('semantic_adjudication', 'LLM semantic adjudication', ARRAY['learning_memory', 'autonomy_adjudication'], 'Structured LLM verdicts for intent reconstruction, replay intent synthesis, memory declassification, topology choice, context equivalence, broker misses, and ambiguous evidence.', ARRAY['semantic_adjudication', 'llm_verdict', 'deterministic_admissibility'], 'adjudication'),
  ('autonomy_orchestrator', 'Autonomy decision orchestrator', ARRAY['autonomy_adjudication', 'lifecycle_governance'], 'Calibrated selective-trust decisions, soft-threshold policy, fallback ladders, policy trials, threshold-deadlock findings, and selected autonomous actions.', ARRAY['autonomy_decision', 'threshold_policy', 'fallback_ladder'], 'autonomy'),
  ('replay_corpus', 'Replay + canary corpus', ARRAY['autonomy_adjudication', 'quality_gates'], 'Replay episode synthesis, redacted intent, expected decisions, canary eligibility, and corpus evidence coverage.', ARRAY['broker_replay_episode', 'redacted_intent', 'canary_result'], 'replay'),
  ('retrieval_indexing', 'Retrieval + indexing', ARRAY['learning_memory', 'runtime_context'], 'Lexical/vector indexing, pgvector status, re-embedding, exact rerank, and graph expansion indexes.', ARRAY['retrieval_audit', 'embedding_profile', 'rerank_example'], 'retrieval'),
  ('broker_runtime', 'Runtime broker', ARRAY['runtime_context'], 'Skill-context selection, no-skill decisions, shadowing control, and context hint rendering.', ARRAY['broker_decision', 'scoring_waterfall', 'rendered_hint'], 'broker'),
  ('opportunity_mining', 'Opportunity miner', ARRAY['learning_memory', 'topology_design'], 'Candidate discovery from clustered evidence, repeated workflows, failures, corrections, and co-use.', ARRAY['opportunity', 'rejected_candidate', 'candidate_seed'], 'topology'),
  ('topology_operations', 'Topology operations', ARRAY['topology_design'], 'Create, improve, compose, decompose, merge, archive, promote, rollback, and freeze decisions.', ARRAY['topology_operation', 'curation_decision', 'skill_lineage'], 'topology'),
  ('skill_ir_graph_ir', 'SkillIR / SkillGraphIR', ARRAY['topology_design'], 'Canonical skill representation, graph workflows, version state, contracts, and effect signatures.', ARRAY['skill_ir', 'skill_graph_ir', 'effect_signature'], 'skills'),
  ('artifact_planner', 'Skill package planner', ARRAY['topology_design', 'artifact_mutation'], 'Ancillary-file planning and support artifact risk decisions.', ARRAY['artifact_plan', 'manifest', 'support_file_preview'], 'artifact'),
  ('context_compiler', 'Context compiler', ARRAY['runtime_context', 'artifact_mutation'], 'Compiles SkillIR to compact runtime skill text, broker hints, and context excerpts under token budgets.', ARRAY['compiled_skill_md', 'broker_hint', 'token_diff'], 'context'),
  ('scanner_security', 'Scanner + security', ARRAY['quality_gates', 'artifact_mutation'], 'Static, semantic, capability, harmful-skill, injection, artifact, and bundle scanning.', ARRAY['scanner_finding', 'risk_matrix', 'taint_to_artifact_path'], 'scanner'),
  ('evaluator_probes', 'Evaluator + probes', ARRAY['quality_gates', 'artifact_mutation'], 'Target, regression, adversarial, canary, benchmark, and counterfactual trials.', ARRAY['evaluation_run', 'probe_fixture', 'comparison_trial'], 'evaluator'),
  ('deterministic_writer', 'Deterministic writer', ARRAY['artifact_mutation'], 'Path-contained staging, manifest hashing, file writes, activation locks, and transactionality.', ARRAY['writer_transaction', 'file_diff', 'rollback_pointer'], 'writer'),
  ('activation_curation', 'Activation + curation', ARRAY['artifact_mutation', 'lifecycle_governance'], 'Active/archive/promotion lifecycle, active budget, utility rollups, and skill technical debt.', ARRAY['skill_lifecycle', 'curation_decision', 'canary_result'], 'lifecycle'),
  ('canary_rollback', 'Canary + rollback', ARRAY['runtime_context', 'artifact_mutation', 'lifecycle_governance'], 'Runtime canary observation, rollback, freeze, and derived-data revocation.', ARRAY['evolution_transaction', 'revocation_graph', 'post_rollback_validation'], 'rollback'),
  ('administrative_escalation', 'Administrative escalation', ARRAY['autonomy_adjudication', 'lifecycle_governance'], 'Exceptional authority-boundary cases, attempted autonomous alternatives, escalation reason codes, and resolution state.', ARRAY['administrative_escalation', 'policy_boundary', 'safe_next_action'], 'escalation'),
  ('scheduler_jobs', 'Scheduler + jobs', ARRAY['control_storage'], 'Sidecar schedules, jobs, leases, attempts, backoff, and queue pressure.', ARRAY['job', 'schedule', 'lease', 'attempt_timeline'], 'jobs'),
  ('model_embedding', 'Model + embedding profiles', ARRAY['quality_gates', 'control_storage'], 'Text model profile, embedding profile, qualification gates, and invocation health.', ARRAY['profile_qualification', 'structured_output_failure', 'embedding_sanity_probe'], 'profiles'),
  ('storage_db', 'Postgres + pgvector', ARRAY['control_storage'], 'DB health, migrations, index health, read models, partitions, and retention.', ARRAY['db_health_report', 'index_status', 'materialized_view_refresh'], 'storage'),
  ('audit_trace', 'Audit + trace spine', ARRAY['lifecycle_governance', 'control_storage'], 'Correlation across events, jobs, actions, model calls, evaluations, artifacts, and mutations.', ARRAY['trace', 'span_graph', 'action_audit', 'causal_attribution'], 'audit'),
  ('operator_action_gateway', 'Operator action gateway', ARRAY['lifecycle_governance'], 'Role checks, confirmations, idempotency, guarded action dispatch, and action audit links.', ARRAY['admin_action', 'policy_check', 'idempotency_key', 'action_receipt'], 'actions'),
  ('observatory_admin', 'Observatory self-health', ARRAY['control_storage'], 'Admin API, frontend serving, live stream, read-model freshness, browser diagnostics, and dashboard performance.', ARRAY['admin_self_health', 'frontend_error', 'sequence_gap'], 'observatory')
ON CONFLICT (component_id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  subsystem_ids = EXCLUDED.subsystem_ids,
  purpose = EXCLUDED.purpose,
  object_kinds = EXCLUDED.object_kinds,
  metric_family = EXCLUDED.metric_family,
  updated_at = now();

INSERT INTO autoskill.admin_subsystem_catalog (
  subsystem_id,
  display_name,
  station_ids,
  diagnostic_questions
) VALUES
  ('capture_bootstrap', 'Capture + bootstrap workcell', ARRAY['openclaw_live_capture', 'historical_ingestion', 'redaction_taint', 'spool_ingest', 'event_normalization'], ARRAY['Are live and historical inputs arriving?', 'Are source items parsed, skipped, quarantined, or revoked?', 'Is redaction removing too much useful structure?']),
  ('learning_memory', 'Learning + memory workcell', ARRAY['evidence_memory', 'evidence_fidelity', 'semantic_adjudication', 'retrieval_indexing', 'opportunity_mining'], ARRAY['Is evidence maturing into useful memory?', 'Are retrieval indexes fresh?', 'Are useful opportunities being produced?']),
  ('autonomy_adjudication', 'Autonomy + adjudication workcell', ARRAY['raw_evidence_vault', 'evidence_fidelity', 'semantic_adjudication', 'autonomy_orchestrator', 'replay_corpus', 'administrative_escalation', 'model_embedding', 'audit_trace'], ARRAY['Is semantic autonomy supported by sufficient evidence?', 'Are LLM adjudications bounded by deterministic gates?', 'Are replay and escalation states visible?']),
  ('runtime_context', 'Runtime context workcell', ARRAY['retrieval_indexing', 'broker_runtime', 'context_compiler', 'canary_rollback'], ARRAY['Is the broker selecting fewer, better skills?', 'Is context token pressure bounded?', 'Are canaries feeding rollback safely?']),
  ('topology_design', 'Topology design workcell', ARRAY['opportunity_mining', 'topology_operations', 'skill_ir_graph_ir', 'artifact_planner'], ARRAY['Are create/improve/compose/decompose proposals well explained?', 'Are duplicate and external-skill collisions visible?', 'Does every proposal preserve provenance?']),
  ('quality_gates', 'Quality gates workcell', ARRAY['scanner_security', 'evaluator_probes', 'replay_corpus', 'model_embedding'], ARRAY['Which gates accepted or rejected work?', 'Are scanner or evaluator failures concentrated?', 'Are model and embedding profiles qualified?']),
  ('artifact_mutation', 'Artifact mutation workcell', ARRAY['artifact_planner', 'context_compiler', 'scanner_security', 'evaluator_probes', 'deterministic_writer', 'activation_curation', 'canary_rollback'], ARRAY['Can every file mutation be traced to policy and evidence?', 'Are manifests and rollback pointers valid?', 'Are activation gates blocking unsafe changes?']),
  ('lifecycle_governance', 'Lifecycle governance workcell', ARRAY['activation_curation', 'canary_rollback', 'autonomy_orchestrator', 'administrative_escalation', 'audit_trace', 'operator_action_gateway'], ARRAY['Which skills are active, archived, frozen, or revoked?', 'Can changes roll back with derived data revoked?', 'Are operator actions policy checked and audited?']),
  ('control_storage', 'Control + storage workcell', ARRAY['scheduler_jobs', 'model_embedding', 'storage_db', 'audit_trace', 'observatory_admin'], ARRAY['Is the sidecar scheduler moving work?', 'Is storage/index/read-model health trustworthy?', 'Is Observatory telemetry fresh enough to believe?'])
ON CONFLICT (subsystem_id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  station_ids = EXCLUDED.station_ids,
  diagnostic_questions = EXCLUDED.diagnostic_questions,
  updated_at = now();

CREATE TABLE IF NOT EXISTS autoskill.admin_action_audit (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id text NOT NULL,
  actor_roles text[] NOT NULL DEFAULT '{}',
  action_kind text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  idempotency_key text NOT NULL,
  request_payload_redacted jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL,
  result text NOT NULL CHECK (result IN ('accepted','rejected','failed','completed')),
  linked_job_id uuid REFERENCES autoskill.jobs(job_id),
  linked_audit_id uuid REFERENCES autoskill.audit_records(audit_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (actor_id, action_kind, target_type, target_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS autoskill.admin_comparison_runs (
  comparison_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  actor_id text NOT NULL,
  comparison_kind text NOT NULL,
  left_selector jsonb NOT NULL,
  right_selector jsonb NOT NULL,
  result_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_diagnostic_bundles (
  bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  actor_id text NOT NULL,
  scope jsonb NOT NULL,
  redaction_level text NOT NULL,
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  storage_uri text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);

CREATE TABLE IF NOT EXISTS autoskill.admin_evidence_fidelity_status (
  workspace_key text NOT NULL,
  source_kind text NOT NULL,
  decision_family text NOT NULL,
  evidence_fidelity text NOT NULL CHECK (evidence_fidelity IN (
    'raw_vault_linked',
    'declassified_summary',
    'redacted_derivative',
    'metadata_only',
    'hash_only',
    'unavailable'
  )),
  item_count bigint NOT NULL DEFAULT 0 CHECK (item_count >= 0),
  autonomy_support_state text NOT NULL CHECK (autonomy_support_state IN (
    'sufficient',
    'degraded',
    'evidence_insufficient_for_autonomy',
    'policy_disallowed',
    'not_applicable',
    'unknown'
  )),
  dominant_reason_code text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_key, source_kind, decision_family, evidence_fidelity)
);

CREATE INDEX IF NOT EXISTS admin_evidence_fidelity_lookup_idx
ON autoskill.admin_evidence_fidelity_status(workspace_key, decision_family, updated_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_autonomy_decision_status (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_key text NOT NULL,
  decision_family text NOT NULL,
  target_kind text NOT NULL,
  target_id text NOT NULL,
  action_risk_tier text NOT NULL,
  hard_invariant_state text NOT NULL,
  soft_threshold_state text NOT NULL,
  selected_action text NOT NULL,
  confidence_band text NOT NULL,
  evidence_fidelity text NOT NULL,
  autonomy_support_state text NOT NULL,
  dominant_reason_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_autonomy_decision_lookup_idx
ON autoskill.admin_autonomy_decision_status(workspace_key, decision_family, created_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_semantic_adjudication_status (
  adjudication_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_key text NOT NULL,
  decision_family text NOT NULL,
  model_profile_id uuid REFERENCES autoskill.model_profiles(model_profile_id),
  schema_status text NOT NULL,
  confidence_band text NOT NULL,
  evidence_fidelity text NOT NULL,
  verifier_state text NOT NULL,
  raw_vault_exposure_class text NOT NULL,
  dominant_reason_code text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS admin_semantic_adjudication_lookup_idx
ON autoskill.admin_semantic_adjudication_status(workspace_key, decision_family, started_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_administrative_escalation_status (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_key text NOT NULL,
  hard_boundary_kind text NOT NULL,
  decision_family text NOT NULL,
  target_kind text NOT NULL,
  target_id text NOT NULL,
  attempted_autonomous_alternatives jsonb NOT NULL DEFAULT '[]'::jsonb,
  resolution_state text NOT NULL CHECK (
    resolution_state IN ('open','acknowledged','resolved','rejected','expired')
  ),
  dominant_reason_code text NOT NULL,
  opened_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS admin_administrative_escalation_lookup_idx
ON autoskill.admin_administrative_escalation_status(workspace_key, resolution_state, opened_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.diagnostic_momentum (
  diagnostic_momentum_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  issue_signature_hash text NOT NULL,
  diagnostic_kind text NOT NULL CHECK (diagnostic_kind IN (
    'tool_failure','user_correction','probe_failure','drift','retrieval_shadowing',
    'false_positive_load','ignored_load','semantic_loss','context_overhead',
    'composition_gap','decomposition_gap','security_finding','other'
  )),
  root_cause_hypothesis text NOT NULL,
  suggested_change_direction text NOT NULL,
  evidence_count integer NOT NULL DEFAULT 0,
  contrastive_support_count integer NOT NULL DEFAULT 0,
  counterevidence_count integer NOT NULL DEFAULT 0,
  momentum_score double precision NOT NULL DEFAULT 0,
  risk_score double precision NOT NULL DEFAULT 0,
  status text NOT NULL CHECK (
    status IN (
      'accumulating','ready_for_probe','ready_for_patch','repairing',
      'repair_queued','patched','rejected','revoked'
    )
  ),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (
    workspace_id,
    skill_id,
    executor_profile_id,
    issue_signature_hash,
    diagnostic_kind
  )
);

ALTER TABLE autoskill.diagnostic_momentum
  DROP CONSTRAINT IF EXISTS diagnostic_momentum_status_check;
ALTER TABLE autoskill.diagnostic_momentum
  ADD CONSTRAINT diagnostic_momentum_status_check CHECK (
    status IN (
      'accumulating','ready_for_probe','ready_for_patch','repairing',
      'repair_queued','patched','rejected','revoked'
    )
  );
WITH ranked_diagnostic_momentum AS (
  SELECT
    diagnostic_momentum_id,
    first_value(diagnostic_momentum_id) OVER (
      PARTITION BY
        workspace_id,
        skill_id,
        executor_profile_id,
        issue_signature_hash,
        diagnostic_kind
      ORDER BY last_seen_at DESC, diagnostic_momentum_id
    ) AS keep_id,
    workspace_id,
    skill_id,
    executor_profile_id,
    issue_signature_hash,
    diagnostic_kind,
    evidence_count,
    contrastive_support_count,
    counterevidence_count,
    risk_score,
    first_seen_at,
    last_seen_at,
    status
  FROM autoskill.diagnostic_momentum
),
diagnostic_momentum_rollup AS (
  SELECT
    keep_id,
    min(first_seen_at) AS first_seen_at,
    max(last_seen_at) AS last_seen_at,
    sum(evidence_count)::int AS evidence_count,
    sum(contrastive_support_count)::int AS contrastive_support_count,
    sum(counterevidence_count)::int AS counterevidence_count,
    GREATEST(
      sum(evidence_count) + (2 * sum(contrastive_support_count)) - sum(counterevidence_count),
      0
    )::double precision AS momentum_score,
    max(risk_score) AS risk_score,
    bool_or(status = 'revoked') AS has_revoked,
    bool_or(status = 'rejected') AS has_rejected,
    bool_or(status = 'patched') AS has_patched,
    count(*) AS duplicate_count
  FROM ranked_diagnostic_momentum
  GROUP BY keep_id
  HAVING count(*) > 1
),
updated_diagnostic_momentum AS (
  UPDATE autoskill.diagnostic_momentum dm
  SET
    first_seen_at = rollup.first_seen_at,
    last_seen_at = rollup.last_seen_at,
    evidence_count = rollup.evidence_count,
    contrastive_support_count = rollup.contrastive_support_count,
    counterevidence_count = rollup.counterevidence_count,
    momentum_score = rollup.momentum_score,
    risk_score = rollup.risk_score,
    status = CASE
      WHEN rollup.has_revoked THEN 'revoked'
      WHEN rollup.has_rejected THEN 'rejected'
      WHEN rollup.has_patched THEN 'patched'
      WHEN rollup.momentum_score >= 4 THEN 'ready_for_patch'
      WHEN rollup.risk_score >= 0.8 OR rollup.momentum_score >= 2 THEN 'ready_for_probe'
      ELSE 'accumulating'
    END
  FROM diagnostic_momentum_rollup rollup
  WHERE dm.diagnostic_momentum_id = rollup.keep_id
  RETURNING dm.diagnostic_momentum_id
)
DELETE FROM autoskill.diagnostic_momentum dm
USING ranked_diagnostic_momentum ranked
WHERE dm.diagnostic_momentum_id = ranked.diagnostic_momentum_id
  AND ranked.diagnostic_momentum_id <> ranked.keep_id;
ALTER TABLE autoskill.diagnostic_momentum
  DROP CONSTRAINT IF EXISTS diagnostic_momentum_workspace_id_skill_id_executor_profile_id_issue_key;
ALTER TABLE autoskill.diagnostic_momentum
  DROP CONSTRAINT IF EXISTS diagnostic_momentum_workspace_id_skill_id_executor_profile__key;
ALTER TABLE autoskill.diagnostic_momentum
  DROP CONSTRAINT IF EXISTS diagnostic_momentum_scope_unique;
ALTER TABLE autoskill.diagnostic_momentum
  ADD CONSTRAINT diagnostic_momentum_scope_unique UNIQUE NULLS NOT DISTINCT (
    workspace_id,
    skill_id,
    executor_profile_id,
    issue_signature_hash,
    diagnostic_kind
  );

CREATE TABLE IF NOT EXISTS autoskill.skill_graph_operations (
  skill_graph_operation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  operation_kind text NOT NULL CHECK (
    operation_kind IN ('create','improve','compose','decompose','merge','archive','promote')
  ),
  status text NOT NULL DEFAULT 'candidate' CHECK (
    status IN ('candidate','blocked','trial','accepted','rejected','applied','rolled_back')
  ),
  subject_skill_ids uuid[] NOT NULL DEFAULT '{}',
  output_skill_ids uuid[] NOT NULL DEFAULT '{}',
  skill_graph_ir jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  effect_coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
  trial_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  evolution_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.planned_topology_trials (
  planned_topology_trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_graph_operation_id uuid NOT NULL REFERENCES autoskill.skill_graph_operations(skill_graph_operation_id),
  trial_kind text NOT NULL,
  objective text NOT NULL,
  expected jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'planned' CHECK (
    status IN ('planned','running','passed','failed','blocked','retired')
  ),
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  evolution_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.topology_candidates (
  topology_candidate_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  candidate_kind text NOT NULL CHECK (
    candidate_kind IN (
      'create',
      'improve',
      'compose',
      'decompose',
      'archive',
      'promote',
      'merge',
      'description_repair',
      'validator_add',
      'adapter_add',
      'no_op'
    )
  ),
  target_skill_id uuid,
  source_skill_ids uuid[] NOT NULL DEFAULT '{}',
  proposed_skill_ids uuid[] NOT NULL DEFAULT '{}',
  source_cluster_ids uuid[] NOT NULL DEFAULT '{}',
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  maturity text NOT NULL DEFAULT 'observed',
  llm_plan_hash text,
  deterministic_score numeric NOT NULL DEFAULT 0,
  score_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL CHECK (
    status IN (
      'proposed',
      'deduped',
      'rejected',
      'staged',
      'evaluating',
      'accepted',
      'committed',
      'rolled_back',
      'quarantined'
    )
  ),
  rejection_reason text,
  created_by_job_id uuid,
  source_skill_graph_operation_id uuid UNIQUE REFERENCES autoskill.skill_graph_operations(skill_graph_operation_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.topology_operation_trials (
  topology_operation_trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  topology_candidate_id uuid NOT NULL REFERENCES autoskill.topology_candidates(topology_candidate_id),
  trial_kind text NOT NULL CHECK (
    trial_kind IN (
      'no_op',
      'no_skill',
      'current_skill',
      'nearest_active',
      'nearest_archived',
      'old_version',
      'new_version',
      'component_only',
      'composed_skill',
      'decomposed_successors',
      'broker_only',
      'sibling_bundle'
    )
  ),
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  task_fingerprint text NOT NULL,
  probe_ids uuid[] NOT NULL DEFAULT '{}',
  outcome jsonb NOT NULL DEFAULT '{}'::jsonb,
  passed boolean NOT NULL DEFAULT false,
  score numeric,
  source_planned_topology_trial_id uuid UNIQUE REFERENCES autoskill.planned_topology_trials(planned_topology_trial_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.topology_operation_results (
  topology_operation_result_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  topology_candidate_id uuid NOT NULL REFERENCES autoskill.topology_candidates(topology_candidate_id),
  evolution_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  operation_kind text NOT NULL CHECK (
    operation_kind IN ('create','improve','compose','decompose','archive','promote','merge','repair','no_op')
  ),
  affected_skill_ids uuid[] NOT NULL DEFAULT '{}',
  before_state jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_state jsonb NOT NULL DEFAULT '{}'::jsonb,
  activation_decision text NOT NULL CHECK (
    activation_decision IN ('accepted','rejected','rolled_back','canarying','kept','frozen','no_op')
  ),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_skill_graph_operation_id uuid UNIQUE REFERENCES autoskill.skill_graph_operations(skill_graph_operation_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION autoskill.sync_topology_candidate_from_skill_graph_operation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  mapped_candidate_status text;
  mapped_activation_decision text;
  deterministic_score_value numeric;
BEGIN
  mapped_candidate_status := CASE NEW.status
    WHEN 'candidate' THEN 'proposed'
    WHEN 'blocked' THEN 'rejected'
    WHEN 'trial' THEN 'evaluating'
    WHEN 'accepted' THEN 'accepted'
    WHEN 'rejected' THEN 'rejected'
    WHEN 'applied' THEN 'committed'
    WHEN 'rolled_back' THEN 'rolled_back'
    ELSE 'proposed'
  END;
  mapped_activation_decision := CASE NEW.status
    WHEN 'blocked' THEN 'rejected'
    WHEN 'rejected' THEN 'rejected'
    WHEN 'rolled_back' THEN 'rolled_back'
    WHEN 'trial' THEN 'canarying'
    WHEN 'accepted' THEN 'accepted'
    WHEN 'applied' THEN 'accepted'
    WHEN 'candidate' THEN 'kept'
    ELSE 'no_op'
  END;
  deterministic_score_value := CASE
    WHEN NEW.effect_coverage->>'deterministic_score' ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (NEW.effect_coverage->>'deterministic_score')::numeric
    WHEN NEW.trial_summary->>'deterministic_score' ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (NEW.trial_summary->>'deterministic_score')::numeric
    ELSE 0
  END;

  INSERT INTO autoskill.topology_candidates (
    topology_candidate_id,
    workspace_id,
    candidate_kind,
    target_skill_id,
    source_skill_ids,
    proposed_skill_ids,
    source_cluster_ids,
    evidence_ids,
    maturity,
    llm_plan_hash,
    deterministic_score,
    score_breakdown,
    status,
    rejection_reason,
    source_skill_graph_operation_id,
    created_at,
    updated_at
  )
  VALUES (
    NEW.skill_graph_operation_id,
    NEW.workspace_id,
    CASE
      WHEN NEW.operation_kind IN (
        'create',
        'improve',
        'compose',
        'decompose',
        'archive',
        'promote',
        'merge'
      )
      THEN NEW.operation_kind
      ELSE 'no_op'
    END,
    NEW.subject_skill_ids[1],
    NEW.subject_skill_ids,
    NEW.output_skill_ids,
    '{}',
    NEW.evidence_ids,
    COALESCE(NULLIF(NEW.skill_graph_ir->>'maturity', ''), 'observed'),
    COALESCE(NULLIF(NEW.skill_graph_ir->>'plan_hash', ''), NULLIF(NEW.effect_coverage->>'plan_hash', '')),
    deterministic_score_value,
    jsonb_build_object(
      'source', 'skill_graph_operations',
      'skill_graph_ir', NEW.skill_graph_ir,
      'effect_coverage', NEW.effect_coverage,
      'trial_summary', NEW.trial_summary
    ),
    mapped_candidate_status,
    CASE WHEN NEW.status = 'blocked' THEN NEW.trial_summary->>'blocker' ELSE NULL END,
    NEW.skill_graph_operation_id,
    NEW.created_at,
    NEW.updated_at
  )
  ON CONFLICT (source_skill_graph_operation_id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    candidate_kind = EXCLUDED.candidate_kind,
    target_skill_id = EXCLUDED.target_skill_id,
    source_skill_ids = EXCLUDED.source_skill_ids,
    proposed_skill_ids = EXCLUDED.proposed_skill_ids,
    source_cluster_ids = EXCLUDED.source_cluster_ids,
    evidence_ids = EXCLUDED.evidence_ids,
    maturity = EXCLUDED.maturity,
    llm_plan_hash = EXCLUDED.llm_plan_hash,
    deterministic_score = EXCLUDED.deterministic_score,
    score_breakdown = EXCLUDED.score_breakdown,
    status = EXCLUDED.status,
    rejection_reason = EXCLUDED.rejection_reason,
    updated_at = EXCLUDED.updated_at;

  INSERT INTO autoskill.topology_operation_results (
    topology_operation_result_id,
    workspace_id,
    topology_candidate_id,
    evolution_transaction_id,
    operation_kind,
    affected_skill_ids,
    before_state,
    after_state,
    activation_decision,
    metrics,
    source_skill_graph_operation_id,
    created_at
  )
  VALUES (
    autoskill.stable_uuid_from_text('topology_operation_result:skill_graph_operation:' || NEW.skill_graph_operation_id::text),
    NEW.workspace_id,
    NEW.skill_graph_operation_id,
    NEW.evolution_transaction_id,
    CASE
      WHEN NEW.operation_kind IN ('create','improve','compose','decompose','archive','promote','merge')
      THEN NEW.operation_kind
      ELSE 'no_op'
    END,
    array_cat(NEW.subject_skill_ids, NEW.output_skill_ids),
    jsonb_build_object(
      'subject_skill_ids', NEW.subject_skill_ids,
      'skill_graph_ir', NEW.skill_graph_ir
    ),
    jsonb_build_object(
      'output_skill_ids', NEW.output_skill_ids,
      'status', NEW.status
    ),
    mapped_activation_decision,
    jsonb_build_object(
      'source', 'skill_graph_operations',
      'effect_coverage', NEW.effect_coverage,
      'trial_summary', NEW.trial_summary
    ),
    NEW.skill_graph_operation_id,
    NEW.updated_at
  )
  ON CONFLICT (source_skill_graph_operation_id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    topology_candidate_id = EXCLUDED.topology_candidate_id,
    evolution_transaction_id = EXCLUDED.evolution_transaction_id,
    operation_kind = EXCLUDED.operation_kind,
    affected_skill_ids = EXCLUDED.affected_skill_ids,
    before_state = EXCLUDED.before_state,
    after_state = EXCLUDED.after_state,
    activation_decision = EXCLUDED.activation_decision,
    metrics = EXCLUDED.metrics,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION autoskill.sync_topology_operation_trial_from_planned_trial()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO autoskill.topology_operation_trials (
    topology_operation_trial_id,
    workspace_id,
    topology_candidate_id,
    trial_kind,
    executor_profile_id,
    task_fingerprint,
    probe_ids,
    outcome,
    passed,
    score,
    source_planned_topology_trial_id,
    created_at
  )
  VALUES (
    NEW.planned_topology_trial_id,
    NEW.workspace_id,
    NEW.skill_graph_operation_id,
    CASE NEW.trial_kind
      WHEN 'no_skill_control' THEN 'no_skill'
      WHEN 'current_skill_control' THEN 'current_skill'
      WHEN 'original_baseline' THEN 'current_skill'
      WHEN 'nearest_active_collision' THEN 'nearest_active'
      WHEN 'target_creation' THEN 'new_version'
      WHEN 'target_improvement' THEN 'new_version'
      WHEN 'component_baseline' THEN 'component_only'
      WHEN 'composed_workflow' THEN 'composed_skill'
      WHEN 'successor_routing' THEN 'decomposed_successors'
      WHEN 'broker_replay' THEN 'broker_only'
      WHEN 'broker_canary' THEN 'broker_only'
      WHEN 'sibling_bundle' THEN 'sibling_bundle'
      ELSE 'no_op'
    END,
    NULL,
    COALESCE(
      NULLIF(NEW.expected->>'task_fingerprint', ''),
      'sha256:' || encode(digest(
        NEW.objective || ':' || NEW.planned_topology_trial_id::text,
        'sha256'
      ), 'hex')
    ),
    CASE
      WHEN jsonb_typeof(NEW.expected->'probe_ids') = 'array'
      THEN ARRAY(
        SELECT probe_id_text.value::uuid
        FROM jsonb_array_elements_text(NEW.expected->'probe_ids') AS probe_id_text(value)
        WHERE probe_id_text.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
      )
      ELSE '{}'
    END,
    jsonb_build_object(
      'source', 'planned_topology_trials',
      'legacy_trial_kind', NEW.trial_kind,
      'objective', NEW.objective,
      'expected', NEW.expected,
      'status', NEW.status,
      'result', NEW.result
    ),
    NEW.status = 'passed',
    CASE
      WHEN NEW.result->>'score' ~ '^-?[0-9]+(\.[0-9]+)?$' THEN (NEW.result->>'score')::numeric
      ELSE NULL
    END,
    NEW.planned_topology_trial_id,
    NEW.created_at
  )
  ON CONFLICT (source_planned_topology_trial_id) DO UPDATE SET
    workspace_id = EXCLUDED.workspace_id,
    topology_candidate_id = EXCLUDED.topology_candidate_id,
    trial_kind = EXCLUDED.trial_kind,
    executor_profile_id = EXCLUDED.executor_profile_id,
    task_fingerprint = EXCLUDED.task_fingerprint,
    probe_ids = EXCLUDED.probe_ids,
    outcome = EXCLUDED.outcome,
    passed = EXCLUDED.passed,
    score = EXCLUDED.score,
    created_at = EXCLUDED.created_at;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS skill_graph_operations_sync_topology_candidates
  ON autoskill.skill_graph_operations;
CREATE TRIGGER skill_graph_operations_sync_topology_candidates
AFTER INSERT OR UPDATE ON autoskill.skill_graph_operations
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_topology_candidate_from_skill_graph_operation();

DROP TRIGGER IF EXISTS planned_topology_trials_sync_topology_operation_trials
  ON autoskill.planned_topology_trials;
CREATE TRIGGER planned_topology_trials_sync_topology_operation_trials
AFTER INSERT OR UPDATE ON autoskill.planned_topology_trials
FOR EACH ROW EXECUTE FUNCTION autoskill.sync_topology_operation_trial_from_planned_trial();

INSERT INTO autoskill.topology_candidates (
  topology_candidate_id,
  workspace_id,
  candidate_kind,
  target_skill_id,
  source_skill_ids,
  proposed_skill_ids,
  source_cluster_ids,
  evidence_ids,
  maturity,
  llm_plan_hash,
  deterministic_score,
  score_breakdown,
  status,
  rejection_reason,
  source_skill_graph_operation_id,
  created_at,
  updated_at
)
SELECT
  skill_graph_operation_id,
  workspace_id,
  CASE
    WHEN operation_kind IN ('create','improve','compose','decompose','archive','promote','merge')
    THEN operation_kind
    ELSE 'no_op'
  END,
  subject_skill_ids[1],
  subject_skill_ids,
  output_skill_ids,
  '{}',
  evidence_ids,
  COALESCE(NULLIF(skill_graph_ir->>'maturity', ''), 'observed'),
  COALESCE(NULLIF(skill_graph_ir->>'plan_hash', ''), NULLIF(effect_coverage->>'plan_hash', '')),
  CASE
    WHEN effect_coverage->>'deterministic_score' ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (effect_coverage->>'deterministic_score')::numeric
    WHEN trial_summary->>'deterministic_score' ~ '^-?[0-9]+(\.[0-9]+)?$'
    THEN (trial_summary->>'deterministic_score')::numeric
    ELSE 0
  END,
  jsonb_build_object(
    'source', 'skill_graph_operations',
    'skill_graph_ir', skill_graph_ir,
    'effect_coverage', effect_coverage,
    'trial_summary', trial_summary
  ),
  CASE status
    WHEN 'candidate' THEN 'proposed'
    WHEN 'blocked' THEN 'rejected'
    WHEN 'trial' THEN 'evaluating'
    WHEN 'accepted' THEN 'accepted'
    WHEN 'rejected' THEN 'rejected'
    WHEN 'applied' THEN 'committed'
    WHEN 'rolled_back' THEN 'rolled_back'
    ELSE 'proposed'
  END,
  CASE WHEN status = 'blocked' THEN trial_summary->>'blocker' ELSE NULL END,
  skill_graph_operation_id,
  created_at,
  updated_at
FROM autoskill.skill_graph_operations
ON CONFLICT (source_skill_graph_operation_id) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  candidate_kind = EXCLUDED.candidate_kind,
  target_skill_id = EXCLUDED.target_skill_id,
  source_skill_ids = EXCLUDED.source_skill_ids,
  proposed_skill_ids = EXCLUDED.proposed_skill_ids,
  source_cluster_ids = EXCLUDED.source_cluster_ids,
  evidence_ids = EXCLUDED.evidence_ids,
  maturity = EXCLUDED.maturity,
  llm_plan_hash = EXCLUDED.llm_plan_hash,
  deterministic_score = EXCLUDED.deterministic_score,
  score_breakdown = EXCLUDED.score_breakdown,
  status = EXCLUDED.status,
  rejection_reason = EXCLUDED.rejection_reason,
  updated_at = EXCLUDED.updated_at;

INSERT INTO autoskill.topology_operation_results (
  topology_operation_result_id,
  workspace_id,
  topology_candidate_id,
  evolution_transaction_id,
  operation_kind,
  affected_skill_ids,
  before_state,
  after_state,
  activation_decision,
  metrics,
  source_skill_graph_operation_id,
  created_at
)
SELECT
  autoskill.stable_uuid_from_text('topology_operation_result:skill_graph_operation:' || skill_graph_operation_id::text),
  workspace_id,
  skill_graph_operation_id,
  evolution_transaction_id,
  CASE
    WHEN operation_kind IN ('create','improve','compose','decompose','archive','promote','merge')
    THEN operation_kind
    ELSE 'no_op'
  END,
  array_cat(subject_skill_ids, output_skill_ids),
  jsonb_build_object('subject_skill_ids', subject_skill_ids, 'skill_graph_ir', skill_graph_ir),
  jsonb_build_object('output_skill_ids', output_skill_ids, 'status', status),
  CASE status
    WHEN 'blocked' THEN 'rejected'
    WHEN 'rejected' THEN 'rejected'
    WHEN 'rolled_back' THEN 'rolled_back'
    WHEN 'trial' THEN 'canarying'
    WHEN 'accepted' THEN 'accepted'
    WHEN 'applied' THEN 'accepted'
    WHEN 'candidate' THEN 'kept'
    ELSE 'no_op'
  END,
  jsonb_build_object(
    'source', 'skill_graph_operations',
    'effect_coverage', effect_coverage,
    'trial_summary', trial_summary
  ),
  skill_graph_operation_id,
  updated_at
FROM autoskill.skill_graph_operations
ON CONFLICT (source_skill_graph_operation_id) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  topology_candidate_id = EXCLUDED.topology_candidate_id,
  evolution_transaction_id = EXCLUDED.evolution_transaction_id,
  operation_kind = EXCLUDED.operation_kind,
  affected_skill_ids = EXCLUDED.affected_skill_ids,
  before_state = EXCLUDED.before_state,
  after_state = EXCLUDED.after_state,
  activation_decision = EXCLUDED.activation_decision,
  metrics = EXCLUDED.metrics,
  created_at = EXCLUDED.created_at;

INSERT INTO autoskill.topology_operation_trials (
  topology_operation_trial_id,
  workspace_id,
  topology_candidate_id,
  trial_kind,
  executor_profile_id,
  task_fingerprint,
  probe_ids,
  outcome,
  passed,
  score,
  source_planned_topology_trial_id,
  created_at
)
SELECT
  planned_topology_trial_id,
  workspace_id,
  skill_graph_operation_id,
  CASE trial_kind
    WHEN 'no_skill_control' THEN 'no_skill'
    WHEN 'current_skill_control' THEN 'current_skill'
    WHEN 'original_baseline' THEN 'current_skill'
    WHEN 'nearest_active_collision' THEN 'nearest_active'
    WHEN 'target_creation' THEN 'new_version'
    WHEN 'target_improvement' THEN 'new_version'
    WHEN 'component_baseline' THEN 'component_only'
    WHEN 'composed_workflow' THEN 'composed_skill'
    WHEN 'successor_routing' THEN 'decomposed_successors'
    WHEN 'broker_replay' THEN 'broker_only'
    WHEN 'broker_canary' THEN 'broker_only'
    WHEN 'sibling_bundle' THEN 'sibling_bundle'
    ELSE 'no_op'
  END,
  NULL,
  COALESCE(
    NULLIF(expected->>'task_fingerprint', ''),
    'sha256:' || encode(digest(objective || ':' || planned_topology_trial_id::text, 'sha256'), 'hex')
  ),
  CASE
    WHEN jsonb_typeof(expected->'probe_ids') = 'array'
    THEN ARRAY(
      SELECT probe_id_text.value::uuid
      FROM jsonb_array_elements_text(expected->'probe_ids') AS probe_id_text(value)
      WHERE probe_id_text.value ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )
    ELSE '{}'
  END,
  jsonb_build_object(
    'source', 'planned_topology_trials',
    'legacy_trial_kind', trial_kind,
    'objective', objective,
    'expected', expected,
    'status', status,
    'result', result
  ),
  status = 'passed',
  CASE
    WHEN result->>'score' ~ '^-?[0-9]+(\.[0-9]+)?$' THEN (result->>'score')::numeric
    ELSE NULL
  END,
  planned_topology_trial_id,
  created_at
FROM autoskill.planned_topology_trials
ON CONFLICT (source_planned_topology_trial_id) DO UPDATE SET
  workspace_id = EXCLUDED.workspace_id,
  topology_candidate_id = EXCLUDED.topology_candidate_id,
  trial_kind = EXCLUDED.trial_kind,
  executor_profile_id = EXCLUDED.executor_profile_id,
  task_fingerprint = EXCLUDED.task_fingerprint,
  probe_ids = EXCLUDED.probe_ids,
  outcome = EXCLUDED.outcome,
  passed = EXCLUDED.passed,
  score = EXCLUDED.score,
  created_at = EXCLUDED.created_at;

CREATE INDEX IF NOT EXISTS topology_candidates_kind_status_idx
  ON autoskill.topology_candidates (workspace_id, candidate_kind, status, deterministic_score DESC);

CREATE TABLE IF NOT EXISTS autoskill.skill_usage_windows (
  skill_usage_window_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  skill_ids uuid[] NOT NULL DEFAULT '{}',
  sequence_signature_hash text NOT NULL,
  outcome text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.skill_co_usage_edges (
  skill_co_usage_edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  left_skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  right_skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  co_usage_count integer NOT NULL DEFAULT 0,
  success_count integer NOT NULL DEFAULT 0,
  failure_count integer NOT NULL DEFAULT 0,
  sequence_count integer NOT NULL DEFAULT 0,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, left_skill_id, right_skill_id)
);

CREATE TABLE IF NOT EXISTS autoskill.skill_usage_clusters (
  skill_usage_cluster_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  cluster_key text NOT NULL,
  skill_ids uuid[] NOT NULL DEFAULT '{}',
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  support_count integer NOT NULL DEFAULT 0,
  recommended_operation text CHECK (
    recommended_operation IN ('create','improve','compose','decompose','merge','archive','promote')
  ),
  status text NOT NULL DEFAULT 'observed',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, cluster_key)
);

CREATE INDEX IF NOT EXISTS environment_contracts_status_idx
  ON autoskill.environment_contracts(workspace_id, status);

CREATE INDEX IF NOT EXISTS drift_events_workspace_time_idx
  ON autoskill.drift_events(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS trace_spans_trace_idx
  ON autoskill.trace_spans (workspace_id, trace_id, started_at);

CREATE INDEX IF NOT EXISTS admin_live_event_created_idx
  ON autoskill.admin_live_event_outbox(created_at DESC);

CREATE INDEX IF NOT EXISTS admin_live_event_component_idx
  ON autoskill.admin_live_event_outbox(component_id, seq DESC);

CREATE INDEX IF NOT EXISTS admin_component_catalog_metric_family_idx
  ON autoskill.admin_component_catalog(metric_family);

CREATE INDEX IF NOT EXISTS admin_subsystem_catalog_station_ids_idx
  ON autoskill.admin_subsystem_catalog USING gin(station_ids);

CREATE INDEX IF NOT EXISTS admin_comparison_runs_workspace_time_idx
  ON autoskill.admin_comparison_runs(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS admin_diagnostic_bundles_workspace_time_idx
  ON autoskill.admin_diagnostic_bundles(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS diagnostic_momentum_ready_idx
  ON autoskill.diagnostic_momentum (
    workspace_id,
    status,
    momentum_score DESC,
    last_seen_at DESC
  );

CREATE INDEX IF NOT EXISTS context_artifacts_workspace_kind_idx
  ON autoskill.context_artifacts(workspace_id, artifact_kind, created_at DESC);

CREATE INDEX IF NOT EXISTS context_token_ledgers_workspace_visibility_idx
  ON autoskill.context_token_ledgers(workspace_id, visibility_state, created_at DESC);

CREATE INDEX IF NOT EXISTS context_compile_runs_workspace_status_idx
  ON autoskill.context_compile_runs(workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS context_compile_runs_skill_idx
  ON autoskill.context_compile_runs(workspace_id, skill_id, skill_version_id, created_at DESC);

CREATE INDEX IF NOT EXISTS context_budget_events_skill_time_idx
  ON autoskill.context_budget_events(workspace_id, skill_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_compression_trials_skill_idx
  ON autoskill.semantic_compression_trials(workspace_id, skill_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS skill_graph_operations_workspace_status_idx
  ON autoskill.skill_graph_operations(workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS planned_topology_trials_operation_idx
  ON autoskill.planned_topology_trials(skill_graph_operation_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS skill_usage_windows_workspace_time_idx
  ON autoskill.skill_usage_windows(workspace_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS memory_quarantine_workspace_status_idx
  ON autoskill.memory_quarantine(workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS control_flow_events_workspace_time_idx
  ON autoskill.control_flow_events(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS control_flow_events_source_idx
  ON autoskill.control_flow_events(workspace_id, source_kind, influence_kind, created_at DESC);

CREATE INDEX IF NOT EXISTS raw_events_workspace_time_idx
  ON autoskill.raw_events(workspace_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS jobs_ready_idx
  ON autoskill.jobs(status, available_at, priority);

CREATE INDEX IF NOT EXISTS evidence_items_lexical_idx
  ON autoskill.evidence_items
  USING gin (to_tsvector('simple', summary));

CREATE INDEX IF NOT EXISTS body_index_documents_lexical_idx
  ON autoskill.body_index_documents
  USING gin (to_tsvector('simple', text_content));

CREATE INDEX IF NOT EXISTS external_skill_inventory_lexical_idx
  ON autoskill.external_skill_inventory
  USING gin (to_tsvector('simple', COALESCE(name, '') || ' ' || COALESCE(description, '')));

CREATE INDEX IF NOT EXISTS external_skill_inventory_status_idx
  ON autoskill.external_skill_inventory(workspace_id, status, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS external_skill_review_actions_external_idx
  ON autoskill.external_skill_review_actions(external_skill_id, created_at DESC);

CREATE INDEX IF NOT EXISTS embeddings_hnsw_cosine_1536_idx
  ON autoskill.embeddings
  USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
  WHERE embedding_dim = 1536;

CREATE INDEX IF NOT EXISTS embeddings_object_idx
  ON autoskill.embeddings (workspace_id, object_type, skill_id);
