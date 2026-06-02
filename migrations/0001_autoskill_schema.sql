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
  trace_id uuid,
  span_id uuid,
  parent_span_id uuid,
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

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS trace_id uuid;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS span_id uuid;

ALTER TABLE autoskill.raw_events
  ADD COLUMN IF NOT EXISTS parent_span_id uuid;

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
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE(workspace_id, name)
);

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
  outcome text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.historical_import_sources (
  historical_import_source_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_kind text NOT NULL CHECK (
    source_kind IN (
      'session_store','transcript','trajectory','compaction_summary',
      'workspace_memory','workspace_context','task_record','taskflow_record',
      'plugin_session_state','queued_injection','active_memory',
      'diagnostics_export','channel_media','transcription',
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

CREATE INDEX IF NOT EXISTS idx_historical_import_sources_workspace_status
  ON autoskill.historical_import_sources(workspace_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_historical_import_chunks_source
  ON autoskill.historical_import_chunks(historical_import_source_id, item_key, chunk_index);

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
    status IN ('accumulating','ready_for_probe','ready_for_patch','patched','rejected','revoked')
  ),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (
    workspace_id,
    skill_id,
    executor_profile_id,
    issue_signature_hash,
    diagnostic_kind
  )
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
