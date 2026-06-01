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

CREATE TABLE IF NOT EXISTS autoskill.embeddings (
  embedding_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  object_type text NOT NULL,
  object_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  embedding_model text NOT NULL,
  embedding_dim integer NOT NULL,
  embedding vector(1536) NOT NULL,
  text_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (object_type, object_id, embedding_model)
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
  outcome text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.control_flow_events (
  control_flow_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  influence_kind text NOT NULL,
  influenced_object_type text NOT NULL,
  influenced_object_id uuid,
  source_object_type text,
  source_object_id uuid,
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.revocation_requests (
  revocation_request_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  request_kind text NOT NULL,
  root_object_type text NOT NULL,
  root_object_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  traversal_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_job_id uuid REFERENCES autoskill.jobs(job_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
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

CREATE INDEX IF NOT EXISTS environment_contracts_status_idx
  ON autoskill.environment_contracts(workspace_id, status);

CREATE INDEX IF NOT EXISTS drift_events_workspace_time_idx
  ON autoskill.drift_events(workspace_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS embeddings_hnsw_cosine_idx
  ON autoskill.embeddings
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS embeddings_object_idx
  ON autoskill.embeddings (workspace_id, object_type, skill_id);
