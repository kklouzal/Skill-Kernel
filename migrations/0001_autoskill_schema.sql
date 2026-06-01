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

CREATE TABLE IF NOT EXISTS autoskill.raw_events (
  event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL,
  source text NOT NULL,
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  redaction_state text NOT NULL,
  payload_hash text NOT NULL,
  payload jsonb NOT NULL,
  plugin_version text,
  openclaw_version text,
  inserted_at timestamptz NOT NULL DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS autoskill.skills (
  skill_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  slug text NOT NULL,
  name text NOT NULL,
  source text NOT NULL DEFAULT 'autoskill',
  lifecycle_state text NOT NULL DEFAULT 'candidate',
  active_version_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(workspace_id, slug)
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
  manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.skill_edges (
  edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  from_skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  to_skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  edge_kind text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(from_skill_id, to_skill_id, edge_kind)
);

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

CREATE TABLE IF NOT EXISTS autoskill.evaluations (
  evaluation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  broker_policy_version_id uuid,
  executor_profile_id uuid,
  category text NOT NULL,
  status text NOT NULL,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
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

CREATE TABLE IF NOT EXISTS autoskill.retrieval_logs (
  retrieval_log_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
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

CREATE TABLE IF NOT EXISTS autoskill.schedules (
  schedule_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  name text NOT NULL,
  job_kind text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  interval_seconds integer NOT NULL,
  next_run_at timestamptz NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(workspace_id, name)
);

CREATE TABLE IF NOT EXISTS autoskill.jobs (
  job_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
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
  outcome text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

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

CREATE INDEX IF NOT EXISTS raw_events_workspace_time_idx
  ON autoskill.raw_events(workspace_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS jobs_ready_idx
  ON autoskill.jobs(status, available_at, priority);
