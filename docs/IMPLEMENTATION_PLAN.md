# SkillKernel Implementation Plan

This plan tracks the v16 coherence-closed handoff and turns it into repo-level gates.

## Phase 0 - Confirm OpenClaw Seams

Deliverables:

- exact hook package shape for the target OpenClaw version;
- manifest keys for plugin-owned hooks;
- hook names and payload shape for session, message, tool, model, prompt/context, compaction, and gateway events;
- active skill root and archive invisibility proof;
- fail-soft context hint proof.

Acceptance:

- an installed local plugin can capture tool and turn events; implemented for the
  runtime plugin shape with `openclaw --dev plugins inspect autoskill --json
  --runtime` proving `imported=true`, `hookCount=11`, and no diagnostics when
  `allowConversationAccess`/`allowPromptInjection` are enabled;
- a generated test skill loads from `<workspace>/skills/autoskill/<slug>/SKILL.md`;
  implemented with a dev-profile fixture that appeared as `openclaw-workspace`,
  `eligible=true`, and `modelVisible=true`;
- archived skills under `<workspace>/.autoskill/archive` are invisible to
  OpenClaw skill loading; implemented with a paired dev-profile archive fixture
  that stayed absent from normal and `--eligible` skill discovery;
- context hints can be disabled and fail softly.

## Phase 1 - Database, Migrations, Sidecar Skeleton

Deliverables:

- `autoskill` Postgres schema migration;
- pgvector extension enablement;
- FastAPI sidecar with health, status, ingest, context hint, skills, jobs, and audit endpoints;
- event idempotency;
- audit hash chain primitive.

Acceptance:

- events insert idempotently; implemented with `workspaces.external_key` upsert and `raw_events.event_id` conflict handling;
- schema can migrate up/down in dev;
- audit hash chain verifies.

## Phase 2 - Plugin Capture, Redaction, Spool

Deliverables:

- OpenClaw hook handlers;
- local redaction and taint marking;
- bounded append-only spool;
- localhost forwarding with retry;
- plugin status command or diagnostic endpoint.

Acceptance:

- sidecar outage does not block OpenClaw; implemented with hook-level tests that
  spool failed events without throwing;
- only redacted payloads are persisted;
- spool replay is idempotent; implemented as accepted-or-duplicate deletion from
  bounded JSONL spool, with replay failure isolated from the already-forwarded
  current event;
- concurrent capture appends all failed events to the bounded spool;
- actual hook handlers import and forward redacted envelopes in the local smoke fixture.

## Phase 3 - Scheduler and Job Queue

Deliverables:

- sidecar-owned schedules;
- jobs, attempts, leases, idempotency keys;
- job trace context; implemented with enqueue-supplied or generated `trace_id`/`span_id`, non-null persisted job trace/span roots, scheduled-job trace generation, and trace-preserving job JSON responses.
- worker pools; implemented as explicit scheduler/maintenance/mutation run-once dispatch, bounded loop entrypoints, configured per-pool loop concurrency, persistent worker heartbeats, and worker health summaries.

Acceptance:

- jobs survive restart;
- duplicate ticks do not duplicate jobs; implemented with schedule-run idempotency keys;
- stuck leases recover; implemented for expired leases with remaining attempts;
- failed attempts back off and terminally fail at `max_attempts`;
- maintenance worker can claim and complete deterministic evidence/embedding jobs.
- worker loop supports bounded/configured concurrency, persistent heartbeat observation, and graceful process shutdown.
- queued, leased, renewed, completed, API-enqueued, and scheduled jobs carry trace/span context; implemented and validated with focused tests plus compose/Postgres smoke coverage.

## Phase 4 - Evidence, Embeddings, Retrieval

Deliverables:

- evidence extractor; implemented for deterministic observed evidence derived from redacted raw events;
- redacted embeddings; storage/search primitives, deterministic development generation worker, configurable provider routing, profile-scoped embedding ownership, variable-dimension profile storage/search, and qualified-profile generation are implemented;
- lexical + vector + metadata search; lexical evidence/body-index search and pgvector nearest search are implemented;
- exact rerank; implemented as deterministic broker rerank over lexical score, query overlap, lifecycle, and graph edges;
- active/archive matching; implemented in runtime broker and `/v1/skills/match` so archived matches are promotion candidates rather than injected hints or duplicate new skills;
- duplicate matching;
- ANN recall audit; implemented as `/v1/embeddings/recall-audit`, comparing index-preferred nearest-neighbor results against exact pgvector ordering for a bounded sample.

Acceptance:

- active and archived matches are considered before new skill creation;
- ANN recall audit exists; implemented and validated against local Postgres;
- retrieval decisions are logged.
- same-object/same-model embeddings from different qualified profiles remain separate; implemented with `embedding_profile_id` storage, profile-scoped uniqueness, API propagation, and local Postgres smoke validation.
- non-default embedding dimensions can be qualified, stored, and searched under profile ownership; implemented with unbounded pgvector storage, persisted `embedding_dim`, dimension-filtered search/recall queries, and a retained expression HNSW index for the default 1536-dimensional path.
- model/embedding qualification run tables and profile status stamping are implemented for auditable qualification gates.

## Phase 4.5 - Text Model Access and Invocation Audit

Deliverables:

- typed LLM client for semantic proposal jobs; implemented for one workspace/profile text profile per call;
- model profile thinking-level and fallback policy; implemented on profile storage/API and recorded on invocation audit rows;
- OpenAI-compatible `/chat/completions` route; implemented with bounded timeout and safe endpoint/API-key resolution;
- OpenClaw text route; intentionally fail-closed as `unsupported` until a stable seam is available;
- LLM invocation audit and trace spans; implemented as content-safe `llm_invocations` rows with purpose, model/profile, route, trace/span, token estimates, status, error, and non-secret audit metadata, plus `llm_call` trace spans that preserve caller/job trace roots without storing prompt or response text in span attributes;
- text-model qualification runs; implemented as control-authenticated probes through the typed LLM client, with dedicated run records and latest-verdict profile status stamping.

Acceptance:

- LLM calls are proposal-engine calls only, with deterministic code owning policy/application;
- unsupported OpenClaw text routing is audited and blocked instead of silently falling through;
- API keys are never persisted in invocation audit metadata;
- focused LLM client tests pass, full sidecar tests pass, and local Postgres smoke can persist an invocation audit row;
- typed LLM calls record first-class `llm_call` spans for successful OpenAI-compatible calls and denied unsupported routes, with invocation audit rows attached to the model-call span;
- model and embedding qualification runs persist dedicated audit rows and stamp the latest verdict onto profile records.

## Phase 5 - Runtime Context Broker

Deliverables:

- deterministic broker planner;
- set-aware context renderer; implemented as a conservative retrieval-backed first pass with duplicate skill suppression and prerequisite graph expansion;
- cache-backed context hint endpoint; endpoint is present behind a disabled-by-default config gate with short in-process cache;
- shadowing logs; broker suppression/rendering telemetry is attached to retrieval logs, and outcome/correction-based shadowing detection records attribution events.
- external-skill inventory awareness; implemented as control-authenticated upsert/list APIs, hashed-root/file-hash/status/risk metadata persistence, read-only scanner job wiring, lexical retrieval of visible/changed external skills, broker suppression as non-runtime collisions, and duplicate-match `external_collision_review` decisions that block automatic candidate creation.
- executor-profile compatibility suppression; implemented through `skill_profile_compatibility`, a control upsert API, executor-scoped broker cache keys, and runtime suppression of explicitly `blocked` or `drifted` skill versions for the requesting executor profile.

Acceptance:

- hint returns under configured timeout;
- no LLM call runs in the hook path;
- no raw memory/evidence is injected; implemented for evidence-only matches by deferring without hint text.
- rendered skill IDs, suppression reasons, and reason codes are recorded on retrieval logs.
- external skills are visible to collision analysis but are never injected as runtime hints or selected for autonomous mutation; scanner jobs hash external roots/files and quarantine scanner-blocked external skills without storing raw root paths.
- blocked/drifted executor compatibility suppresses otherwise renderable skills for that profile while leaving unscoped/no-row retrieval unchanged; implemented and validated with focused broker tests plus compose/Postgres smoke coverage.

## Phase 6 - Candidate Generation in Propose-Only Mode

Deliverables:

- opportunity miner;
- duplicate matching before candidate generation; implemented in deterministic opportunity miner;
- contrastive induction;
- typed LLM operation wrappers;
- SkillIR compiler and deterministic propose-only candidate scaffolding from gated opportunities;
- inactive candidate skill/version persistence with body-level indexing; implemented for propose-only candidates without writing runtime files and now anchored to idempotent governance transactions;
- scanner;
- probe generator; implemented as deterministic target, no-skill-control, and regression probe plans for persisted candidates;
- evaluator; implemented as deterministic proposal-gate execution that records target, no-skill-control, and regression probe results while requiring intervention replay before activation.
- evaluator trace propagation; implemented for API-triggered and worker-triggered proposal-gate runs with content-safe `evaluator` spans, caller/job trace preservation, and safe count/status/object-ref close metadata.
- contrastive induction; implemented for redacted paired outcome evidence by attaching generated `intervention_replay` inputs to no-skill-control probes, persisting contrastive probe maturity, and evaluating through the existing proposal gate.

Acceptance:

- candidates require grounded evidence; proposal scaffolds carry cited evidence IDs, skip active/archive duplicates, and persist inactive candidate revisions only;
- persisted candidate revisions are stamped with `created_by_transaction_id` and rollback-aware transaction items are recorded for the inactive version and compiled `SKILL.md`;
- self-feedback-only changes fail;
- malicious artifacts are rejected;
- evaluator reports target, regression, and no-skill results; no-skill-control remains `needs_intervention` until recorded or redacted contrastive replay evidence exists.
- proposal-gate evaluation runs are trace-visible without storing SkillIR or probe payloads in trace attributes; implemented and validated with focused tests plus compose/Postgres smoke coverage.
- executor-scoped proposal-gate evaluations update `skill_profile_compatibility` as derived state (`compatible`, `degraded`, or `blocked`) with evaluation IDs, reason codes, and trace/span evidence, so broker routing consumes evaluator compatibility outcomes rather than only manual operator writes.

## Phase 7 - Deterministic Writer and Rollback

Deliverables:

- v9 transaction/provenance/revocation schema; implemented for idempotent evolution transactions, transaction items, evidence maturity, action-attribution checks, control-flow events, and revocation requests;
- transaction control APIs; implemented for starting idempotent transactions, updating transaction status/metrics, recording rollback-aware transaction items, and queuing revocation requests;
- staged writer; implemented for scanner-gated compiled `SKILL.md` staging under a bounded staging root without active-root mutation;
- manifests and hashes; implemented for writer manifests with staged file hash verification;
- atomic apply; implemented as a deterministic same-root active skill directory replacement from verified writer manifests;
- activation gate; implemented for queued mutation-worker apply and direct writer apply when requested, requiring the staged manifest skill version to have passed scanner/evaluator/proposal-gate checks and requiring any supplied executor profile to be compatible before active-root exposure;
- archive snapshots; implemented as manifest-and-hash verified snapshots of previous active `skills/autoskill/<slug>` directories;
- rollback; implemented as deterministic active-root restore from verified archive snapshots;
- transaction-aware writer service wrappers; implemented for apply/rollback transaction status updates, active compiled-file and archive-snapshot transaction items, rollback metadata, and fail-closed filesystem recovery when governance recording fails after apply;
- sidecar writer control endpoints; implemented for `/v1/writer/apply` and `/v1/writer/rollback` with control auth, workspace-contained staging/archive roots, pinned `skills/autoskill` active-root policy, and transaction-aware writer wrapper calls;
- writer artifact provenance traversal; implemented by linking active/archive/rollback writer transaction items from their evolution transaction during apply/rollback;
- canary states; implemented as canary-result storage plus deterministic freeze/unfreeze
  control APIs that suppress frozen skills through the existing broker lifecycle filter and
  queue rollback revocation requests for transaction-scoped critical canary failures.
- marginal context value updates; implemented for context token ledgers by updating observed
  outcomes with utility delta, task success, token savings, latency/tool-call deltas, derived
  marginal value, and context-value-per-token, and by stamping linked context artifacts with the
  latest marginal outcome plus semantic density score.
- mutation-worker rollback revocation execution; implemented for queued rollback revocation
  requests whose originating transaction recorded an archive-backed compiled-file rollback
  action or an initial-create active-path deletion rollback action.
- rollback revocation trace spans; implemented as content-safe mutation-worker `rollback`
  operation spans that close with bounded counts and job/revocation-request refs, while
  DB-backed observability tolerates missing caller parent spans instead of failing rollback
  workers.
- rollback-derived invalidation; implemented for traversal-summary impacted objects by deleting
  matching body-index documents and embeddings, marking retrieval/context/topology/evaluator
  derived state revoked or rolled back, revoking matching attribution records, marking
  impacted active skills `revoked`, revoking connected skill graph edges, and revoking
  matching evidence-maturity rows during mutation-worker rollback completion.

Acceptance:

- transaction start is idempotent by workspace/idempotency key; implemented and validated against local Postgres;
- rollback-relevant transaction items can be recorded with activation state and rollback metadata; implemented and validated against local Postgres;
- revocation requests can be queued for rollback/traversal roots; implemented and validated against local Postgres;
- candidate proposal persistence creates or accepts a `candidate_proposal` transaction, records source evidence IDs, stamps the inactive version, writes transaction items, and advances the transaction to `staged`; implemented and validated against local Postgres;
- provenance edges can be recorded idempotently and revocation roots can be previewed through a bounded derived-object traversal; implemented and validated against local Postgres;
- compiled runtime `SKILL.md` artifacts can be staged with deterministic manifests, slug/path/symlink checks, support-artifact allowlisting, scanner blocking, and staged hash verification; implemented and validated with focused writer tests;
- verified staged manifests can atomically replace one active autoskill directory, snapshot the previous active directory into `.autoskill/archive`, reject active snapshot symlinks and manifest target escapes, and restore the previous active directory from a verified archive snapshot; implemented and validated with focused writer tests;
- active-root apply/rollback service wrappers record governance transaction items/statuses and restore the previous active state if post-apply governance recording fails; implemented and validated with focused writer tests;
- sidecar writer endpoints apply and roll back verified manifests through the transaction-aware writer service; implemented and validated with focused writer/API tests and compose/Postgres smoke coverage;
- runtime context hint cache can be invalidated by workspace/skill ID through a control endpoint, and freeze/critical-canary paths evict affected skill hints immediately;
- writer apply/rollback transaction items are discoverable by provenance traversal from their evolution transaction root; implemented and validated with focused writer/governance tests plus compose/Postgres smoke coverage;
- canary critical failures record canary evidence, mark the skill `frozen`, store the freeze reason, record a transaction item, and queue a rollback revocation request when the canary is transaction-scoped; implemented and validated with focused tests plus compose/Postgres smoke coverage;
- mutation-pool `revocations.rollback` jobs claim queued rollback revocation requests, start an idempotent `rollback_skill` transaction, restore the recorded archive manifest through the transaction-aware writer rollback path, complete the revocation request with rollback artifact evidence, and persist a content-safe `rollback` trace span for the worker operation; implemented and validated with focused worker tests plus compose/Postgres smoke coverage;
- accepted SkillGraphIR topology operations record deterministic downstream orchestration actions in `trial_summary.downstream_orchestration`, and mutation-pool `topology.apply_downstream` jobs can consume applied operations to materialize graph edges, activate successor/composed skills, archive superseded/decomposed subjects, record applied action results, and invalidate runtime-derived retrieval/context/embedding records where stores expose invalidation hooks;
- valid skill appears under active root;
- invalid paths are rejected;
- rollback restores the previous effective state;
- canary critical failures trigger rollback/freeze; freeze, rollback revocation queueing, archive-backed mutation-worker rollback execution, initial-create active-path deletion rollback, body-index/embedding/retrieval/context/topology/evaluator/attribution/governance invalidation, active broker-cache invalidation, and fail-closed policy-approved mutation-worker writer apply orchestration are implemented.
- long-running job leases renew while handlers are still running; implemented in the job store, worker execution wrapper, and control API with focused tests.
- mutation-worker `writer.apply` and `revocations.rollback` handlers record content-safe child trace spans under their claimed job spans, including bounded success/error metadata and object refs without compiled skill text.

## Phase 8 - Autonomous Improvement and Curation

Deliverables:

- `autonomous_guarded` apply; implemented as fail-closed mutation-worker `writer.apply` orchestration that only applies a staged manifest when the queued job carries explicit `policy_approved=true`;
- improvement engine;
- archive/promote/merge/split; archive, evaluator-gated archived promotion, evaluator-gated explicit duplicate merge/archive, active-bank budget overflow, and planned split/improvement/disambiguation curation actions are implemented as deterministic lifecycle-state or planning actions;
- external-skill review actions; implemented as a control-authenticated operator decision ledger for reuse/import/ignore/quarantine, with no autonomous mutation of external-owned files;
- utility rollups; implemented as deterministic v1 rollups from attribution events, rendered retrieval counts, shadowing/hurt outcomes, and canary failures;
- attribution ledger.

Acceptance:

- low-utility skills archive; implemented for active skills below a configurable utility threshold with curation action logging;
- archived skills promote when demand recurs; implemented for archived skills with repeated retrieval demand, no harm/canary failures, and latest evaluator pass;
- duplicates merge only after probes pass; implemented for explicit duplicate graph edges as lower-utility duplicate archiving only when both latest skill versions have evaluator pass, with repair/split planning now logged for harmful or shadowing patterns and dedicated merge probe planning still pending;
- active bank budget is enforced; implemented by archiving lowest-utility overflow active skills.
- external collisions pause candidate creation for review; real external-root scanning/import recommendation flows remain pending.

## Phase 9 - Drift and Advanced Governance

Deliverables:

- contract extraction; implemented for SkillIR `environment_contracts` into DB-backed environment contract rows;
- drift checks; implemented as a deterministic first pass for static path-existence, bare-command availability, and required-env probes with drift event creation;
- package/schema/service drift checks; implemented as deterministic Python package, JSON schema, and bounded TCP reachability probes without arbitrary shell execution;
- localized repair;
- skill graph maintenance;
- repeated shadowing events materialize deterministic `shadow` skill graph edges plus active contrastive shadowing probes;
- audit and retrieval policy reviews;
- evidence maturity, action-attribution check, control-flow event, and revocation request storage; implemented as v9 governance schema foundations, with passed recorded or contrastively induced intervention-replay proposal gates recording `intervention_validated` maturity for cited evidence and skill versions.

Acceptance:

- drift violations trigger targeted repair; implemented as drift-event repair-candidate metadata with localized repair plans and active drift probes that retire when contracts return valid, with actual repair proposal execution and false-positive lifecycle still pending;
- curation logs features/actions/outcomes;
- audit integrity verifies.
