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
- prompt, message, body, completion, and similar conversation-content fields are
  content-stripped by default before forwarding/storage, while an explicit raw
  capture opt-in still runs secret/email redaction and the sidecar applies its
  own storage-time redaction;
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
- worker pools; implemented as explicit scheduler/maintenance/mutation run-once dispatch, bounded loop entrypoints, configured per-pool loop concurrency, persistent worker heartbeats, content-safe single-job progress phases, and worker health summaries.

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

- evidence extractor; implemented for deterministic observed evidence derived from redacted raw events plus recurring evidence clusters when repeated redacted signatures meet support thresholds;
- redacted embeddings; storage/search primitives, deterministic development generation worker, configurable provider routing, profile-scoped embedding ownership, variable-dimension profile storage/search, qualified-profile generation, and deployment-level `AUTOSKILL_EMBEDDING_DIM` configuration are implemented;
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
- OpenAI-compatible embedding profile qualification is implemented through the
  same bounded provider embedder path used by generation, with dimension,
  finite-value, non-zero, stability, and negative-pair separation checks recorded
  without storing API keys or probe text.
- OpenAI-compatible embedding generation honors the configured embedding
  dimension instead of forcing the default 1536-dimensional contract.

## Phase 4.5 - Text Model Access and Invocation Audit

Deliverables:

- typed LLM client for semantic proposal jobs; implemented for one workspace/profile text profile per call;
- model profile thinking-level and fallback policy; implemented on profile storage/API and recorded on invocation audit rows;
- OpenAI-compatible text routes; implemented for `/chat/completions` and
  explicit `/responses` endpoint profiles with bounded timeout and safe
  endpoint/API-key resolution;
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
- OpenAI-compatible text profiles can select `chat_completions` or `responses`
  endpoint semantics, and invocation audit records the chosen endpoint route
  without storing prompts, responses, or API keys.

## Phase 4.75 - Historical Ingestion and Deployment Bootstrap

Deliverables:

- historical source inventory substrate; implemented as first-class
  `historical_import_sources` rows with workspace, source kind/key,
  fingerprint, parser version, redaction policy version, trust, taint,
  metadata, status, and idempotent uniqueness;
- redacted historical chunk substrate; implemented as
  `historical_import_chunks` rows with source lineage, item key, chunk index,
  content hash, token estimate, parser/redaction versions, trust, taint, and
  duplicate skip semantics;
- control-authenticated historical import APIs; implemented for source
  list/upsert, bounded dry-run discovery, source revocation, and chunk
  recording without writing runtime skills or mutating imported OpenClaw roots;
- historical datasource discovery substrate; implemented as read-only,
  configured-root inventory with file/source classification, byte/time/risk
  summaries, path hashing instead of raw path persistence, allow/deny filters,
  max file/byte limits, preview-only mode, durable `historical_import.discover`
  worker registration, and optional inventory-only source upsert;
- historical structured import substrate; implemented as bounded
  `historical_import.parse` control/worker flow with run/checkpoint rows,
  transient in-memory raw paths, source upsert, redacted chunk recording,
  transcript JSONL turn parsing, transcript-corpus metadata/summary/transcript
  parsing, Markdown memory/context/taskflow section parsing, session-store
  metadata parsing, trajectory/diagnostic/observability JSON summary parsing,
  existing-skill read-only section parsing, metadata-only plugin manifest/hook/
  source import, metadata-only media artifact import, max chunk limits, and
  duplicate-safe reruns;
- imported chunk downstream readiness; implemented by existing evidence and
  embedding source discovery paths consuming observed historical chunks only
  after storage-time redaction and taint labeling.

Acceptance:

- every imported source/chunk row records source lineage, fingerprint,
  parser/redaction versions, trust, taint, and hash identity for the substrate
  level;
- repeated source upserts and duplicate chunk records are idempotent;
- chunk storage performs deterministic secret/email redaction at the DB-store
  boundary even when an importer caller mislabels raw text as redacted;
- discovery does not parse sensitive content or store raw paths, and scheduled
  backfill roots are operator-configured rather than inferred as broad read
  permission;
- historical source revocation tombstones source and chunk rows, giving
  provenance traversal a concrete historical root before derived-object
  invalidation;
- historical chunks can become observed evidence and embedding sources, but
  cannot directly activate skills, broker runtime context, or trusted memory;
- historical task-ledger variants now include metadata-only JSON/JSONL parsing
  with safe keys, task-ledger tainting, redacted text storage, and hashed record
  locators;
- imported chunks now carry compact source-item lineage metadata with source
  kind, source key, fingerprint, item key, chunk index, and relative path hash
  while continuing to avoid raw path storage;
- source-item locator lineage is now schema-promoted for chunk rows: chunks
  carry nullable content-safe locator hash, source-item kind, item-key hash,
  line-range hash, and record-index columns, with idempotent migration backfill
  from existing v2 metadata and an index for source-item lookup without raw path
  storage;
- bounded bootstrap consolidation is implemented as a historical-only,
  propose-only consolidation API and maintenance job that filters tainted
  historical observations/recurring clusters, reuses existing active/archive/
  external matching before proposal, and optionally persists inactive candidate
  rows through the normal governance transaction/probe path without writing
  runtime skill files;
- remaining historical ingestion work is sustained validation of richer
  non-file ledgers and live source systems beyond the current hashed
  file/item/chunk locator model.

## Phase 5 - Runtime Context Broker

Deliverables:

- deterministic broker planner;
- set-aware context renderer; implemented as a conservative retrieval-backed first pass with duplicate skill suppression, prerequisite graph expansion, and local-hash vector fusion before compatibility/selection gates;
- rendered context bundle scanner; implemented for broker-selected skill sets
  with cross-artifact secret-exfiltration chain detection and conflict-edge
  fail-closed handling before runtime hints are exposed, plus content-safe
  bundle verdict metadata persisted on retrieval logs/context artifacts by
  bundle hash, scanner status, selected IDs, and finding codes;
- cache-backed context hint endpoint; endpoint is present behind a disabled-by-default config gate with short in-process cache;
- shadowing logs; broker suppression/rendering telemetry is attached to retrieval logs, and outcome/correction-based shadowing detection records attribution events.
- external-skill inventory awareness; implemented as control-authenticated upsert/list APIs, hashed-root/file-hash/status/risk metadata persistence, read-only scanner job wiring, lexical retrieval of visible/changed external skills, broker suppression as non-runtime collisions, and duplicate-match `external_collision_review` decisions that block automatic candidate creation.
- executor-profile compatibility suppression; implemented through `skill_profile_compatibility`, a control upsert API, executor-scoped broker cache keys, and runtime suppression of explicitly `blocked` or `drifted` skill versions for the requesting executor profile.
- usage-derived broker policy proposals; implemented as
  `/v1/broker/policies/propose-from-usage`, which consumes accepted
  context-waste/false-positive usage recommendations carrying `broker_abstain`
  or `tighten_description`, turns them into content-safe operator-review
  actions, and can persist a candidate-only broker policy version without
  activating or changing runtime routing.
- broker policy artifacts; implemented as persisted `broker_policy_versions` with active-version lookup, bounded policy overrides for retrieval/graph/render limits, policy-scoped cache keys, replay evaluation primitives, and canary feedback recording.
- context compiler governance records; implemented as idempotent migration
  tables, asyncpg/null store primitives, and control-authenticated APIs for
  `context_compile_runs`, `context_budget_events`, and
  `semantic_compression_trials`, giving the future deterministic compiler a
  content-safe place to persist token-budget, semantic-equivalence, and
  compression-trial decisions.
- deterministic context compiler gate execution; implemented as
  `/v1/context/compile-skillir`, compiling SkillIR into runtime `SKILL.md`,
  recording a context artifact, compile run, token-budget decision, and
  semantic-compression trial, and failing closed for scanner, description,
  token-budget, or semantic-loss rejections without staging or activating files.

Acceptance:

- hint returns under configured timeout;
- no LLM call runs in the hook path;
- no raw memory/evidence is injected; implemented for evidence-only matches by deferring without hint text.
- rendered skill IDs, suppression reasons, and reason codes are recorded on retrieval logs.
- rendered broker bundles fail closed when individually acceptable candidates
  become unsafe together or include conflict graph edges; implemented with
  focused scanner/broker tests, with verdict metadata persisted for replay and
  revocation traceability.
- external skills are visible to collision analysis but are never injected as runtime hints or selected for autonomous mutation; scanner jobs hash external roots/files and quarantine scanner-blocked external skills without storing raw root paths.
- blocked/drifted executor compatibility suppresses otherwise renderable skills for that profile while leaving unscoped/no-row retrieval unchanged; implemented and validated with focused broker tests plus compose/Postgres smoke coverage.
- active broker policy versions are represented in retrieval/context telemetry and can be replayed against bounded episodes before canary feedback marks a policy passed, failed, or rolled back.
- context compile runs, token-budget governor decisions, and semantic
  compression trials can be recorded without storing compiled text or prompt
  bodies; implemented and validated through focused admin tests plus a real
  compose Postgres smoke.
- SkillIR context-gate execution records those governance rows from the
  deterministic compiler in one control-authenticated API call; implemented and
  validated with focused compiler/admin tests.
- Writer activation gates can require staged manifests to carry matching
  context compile-run proof, and the real activation gate verifies the passed
  compile run plus passed `skill_md` context artifact against the manifest text
  hash before writer apply proceeds.
- opt-in runtime tool-call boundary enforcement is implemented on
  `before_tool_call`, preserving capture-only behavior by default and returning
  terminal OpenClaw block decisions for deterministic high-risk tool patterns
  when `runtimeToolBoundary.enabled=true`.
- plugin-side production canary gates can be toggled from environment fallbacks
  for sidecar URL, runtime context broker, and runtime tool boundary settings
  when no explicit OpenClaw plugin config is supplied.

## Phase 6 - Candidate Generation in Propose-Only Mode

Deliverables:

- opportunity miner;
- duplicate matching before candidate generation; implemented in deterministic opportunity miner;
- contrastive induction;
- typed LLM operation wrappers;
- SkillIR compiler and deterministic propose-only candidate scaffolding from gated opportunities;
- inactive candidate skill/version persistence with body-level indexing; implemented for propose-only candidates without writing runtime files and now anchored to idempotent governance transactions;
- scanner; implemented with deterministic blocking classifications for hidden
  comments, invisible controls, secret-like material, dynamic fetch-exec,
  policy override, credential exfiltration, destructive host commands, and
  sensitive file harvesting;
- probe generator; implemented as deterministic target, no-skill-control, and regression probe plans for persisted candidates;
- evaluator; implemented as deterministic proposal-gate execution that records target, no-skill-control, and regression probe results while requiring intervention replay before activation.
- evaluator trace propagation; implemented for API-triggered and worker-triggered proposal-gate runs with content-safe `evaluator` spans, caller/job trace preservation, and safe count/status/object-ref close metadata.
- contrastive induction; implemented for redacted paired outcome evidence by attaching generated `intervention_replay` inputs to no-skill-control probes, persisting contrastive probe maturity, and evaluating through the existing proposal gate. Induction accepts explicit replay outcomes, attribution outcomes, canary/broker outcomes, and context-token-ledger outcome evidence including usage-window source metadata with marginal-value signals.

Acceptance:

- candidates require grounded evidence; proposal scaffolds carry cited evidence IDs, skip active/archive duplicates, and persist inactive candidate revisions only;
- persisted candidate revisions are stamped with `created_by_transaction_id` and rollback-aware transaction items are recorded for the inactive version and compiled `SKILL.md`;
- self-feedback-only changes fail;
- malicious artifacts are rejected;
- evaluator reports target, regression, and no-skill results; no-skill-control remains `needs_intervention` until recorded or redacted contrastive replay evidence exists.
- proposal-gate evaluation runs are trace-visible without storing SkillIR or probe payloads in trace attributes; implemented and validated with focused tests plus compose/Postgres smoke coverage.
- executor-scoped proposal-gate evaluations update `skill_profile_compatibility` as derived state (`compatible`, `degraded`, or `blocked`) with evaluation IDs, reason codes, and trace/span evidence, so broker routing consumes evaluator compatibility outcomes rather than only manual operator writes.
- proposal-gate acceptance now enforces section 23.2 utility/token policy after
  deterministic probes pass: intervention replay metrics record utility delta
  and token delta, then fail closed when utility is below the configured minimum
  or when additional tokens arrive without utility gain. Validation passed with
  focused evaluator tests plus `uv run ruff check sidecar`, `uv run pytest -q`
  with 303 tests, `uv run python -m compileall -q sidecar`, and `git diff
  --check`.

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
- topology downstream apply trace spans; implemented as content-safe mutation-worker
  `topology.apply_downstream` operation spans that preserve the queued job trace/span
  root and close with bounded lifecycle, graph-edge, governance, provenance, and
  runtime-invalidation counts plus job/operation object refs.

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
- direct and queued writer apply with `activation_gate_required=true` fails
  closed unless the staged manifest's context gate matches a passed persisted
  compile run and passed context artifact for the skill version; implemented and
  validated with focused tests plus a real compose Postgres smoke.
- runtime context hint cache can be invalidated by workspace/skill ID through a control endpoint, and freeze/critical-canary paths evict affected skill hints immediately;
- writer apply/rollback transaction items are discoverable by provenance traversal from their evolution transaction root; implemented and validated with focused writer/governance tests plus compose/Postgres smoke coverage;
- canary critical failures record canary evidence, mark the skill `frozen`, store the freeze reason, record a transaction item, and queue a rollback revocation request when the canary is transaction-scoped; implemented and validated with focused tests plus compose/Postgres smoke coverage;
- mutation-pool `revocations.rollback` jobs claim queued rollback revocation requests, start an idempotent `rollback_skill` transaction, restore the recorded archive manifest through the transaction-aware writer rollback path, complete the revocation request with rollback artifact evidence, and persist a content-safe `rollback` trace span for the worker operation; implemented and validated with focused worker tests plus compose/Postgres smoke coverage;
- mutation-pool `topology.apply_downstream` jobs persist content-safe `topology`
  child spans for lifecycle/graph materialization, preserving trace roots and
  recording only bounded counts and object refs; implemented and validated with
  focused worker tests plus full sidecar validation.
- accepted SkillGraphIR topology operations record deterministic downstream orchestration actions in `trial_summary.downstream_orchestration`, and mutation-pool `topology.apply_downstream` jobs can consume applied operations to materialize graph edges, activate successor/composed skills, archive superseded/decomposed subjects, record applied action results, and invalidate runtime-derived retrieval/context/embedding records where stores expose invalidation hooks;
- valid skill appears under active root;
- invalid paths are rejected;
- rollback restores the previous effective state;
- first-class support artifacts are staged as manifest-bound runtime artifacts:
  writer manifests carry per-file loadability class, load policy, scanner status,
  token budget, content hash metadata, and apply/rollback governance records
  each support file as `support_artifact` provenance instead of hiding it under
  the directory-level compiled skill item;
- support artifact context governance is declaration-only by default:
  activation-grade compilation records scanner-gated `support_excerpt` context
  artifacts for each declared support file, stamps load policy/retrieval
  boundary/capability/hash metadata, and includes support hashes in compile
  manifests without injecting support-file contents into broker/runtime context;
- canary critical failures trigger rollback/freeze; freeze, rollback revocation queueing, archive-backed mutation-worker rollback execution, initial-create active-path deletion rollback, body-index/embedding/retrieval/context/topology/evaluator/attribution/governance invalidation, active broker-cache invalidation, and fail-closed policy-approved mutation-worker writer apply orchestration are implemented.
- long-running job leases renew while handlers are still running; implemented in the job store, worker execution wrapper, and control API with focused tests.
- mutation-worker `writer.apply` and `revocations.rollback` handlers record content-safe child trace spans under their claimed job spans, including bounded success/error metadata and object refs without compiled skill text.

## Phase 8 - Autonomous Improvement and Curation

Deliverables:

- `autonomous_guarded` apply; implemented as fail-closed mutation-worker `writer.apply` orchestration that only applies a staged manifest when the queued job carries explicit `policy_approved=true`;
- repair-proposal execution; implemented as mutation-worker `repair.execute` orchestration that claims planned curation repair proposals and open drift repair candidates, records governance transactions/items/provenance, queues explicit policy-approved staged manifests to `writer.apply`, can generate guarded staged repair manifests from policy-approved bounded proposals with skill-version anchors, and otherwise fail-closes to evaluator or drift recheck jobs with source execution metadata;
- repair materialization context proof; implemented so generated repair
  manifests receive deterministic context artifact, compile-run, budget, and
  semantic-compression proof plus activation-grade routing/regression probe
  evidence before staging, and fail closed when proof cannot be produced;
- improvement engine;
- archive/promote/merge/split; archive, evaluator-gated archived promotion, evaluator-gated explicit duplicate merge/archive, active-bank budget overflow, and planned split/improvement/disambiguation curation actions are implemented as deterministic lifecycle-state or planning actions with structured repair proposal payloads;
- external-skill review actions and import materialization; implemented as a control-authenticated operator decision ledger for reuse/import/ignore/quarantine plus operator-approved stage-only import candidates, with no autonomous mutation of external-owned files;
- utility rollups; implemented as deterministic v1 rollups from attribution events, rendered retrieval counts, shadowing/hurt outcomes, and canary failures;
- context-value utility signals; implemented by folding token-ledger marginal
  value, context-value-per-token, ignored/false-positive load counts, and token
  waste into utility rollups, score computation, and guarded improvement
  planning with an explicit context-value acceptance gate;
- usage/topology evidence aggregation; implemented as the `usage.aggregate`
  maintenance job, which mines content-safe retrieval and attribution rows into
  idempotent usage windows, co-use/sequence edges, and observed usage clusters
  with first-pass compose recommendations for later topology consumers;
- usage/topology recommendation scoring; implemented so `usage.aggregate`
  returns ranked content-safe topology recommendations from observed clusters,
  including support, success/failure, sequence, operation-score, and blocker
  metadata before any propose-only or activation path consumes them;
- usage/topology negative-signal scoring; implemented so single-skill harmful
  attribution and false-positive/ignored context-token outcomes create
  subject-scoped `improve` or `decompose` recommendations with structured
  negative-source metadata and suggested `broker_abstain`/`tighten_description`
  context actions;
- usage/topology negative-signal proposal consumption; implemented so accepted
  single-skill `improve` and `decompose` recommendations can persist
  propose-only SkillGraphIR operations, governance transactions, and target/
  regression/broker/rollback trial plans without staging or activating runtime
  skill files;
- broker-abstain and description-tightening recommendation consumption;
  implemented so context-waste/false-positive usage recommendations also feed
  a candidate-only broker policy review surface with hashed cluster keys,
  subject skill IDs, evidence IDs, reason codes, token-waste metrics, and
  operator-review-required action records;
- usage/topology real-skill hydration for negative-signal proposals; implemented
  so accepted `improve` and `decompose` proposals preserve current SkillIR
  effect signatures, carry contract/body-index/description presence signals,
  preserve side-effect/failure/idempotency metadata, and persist measured
  context-value/token-waste reasons into relevant trial expectations;
- topology operation metrics; implemented as a control-authenticated
  `/v1/topology/metrics` surface that reports create/improve/compose/decompose
  operation counts separately, trial status breakdowns by operation and trial
  kind, and bounded recent operation samples for operator dashboards;
- attribution ledger and action-attribution checks; implemented for attribution events, runtime blocked-tool action checks, and revocation invalidation of derived attribution records.

Acceptance:

- low-utility skills archive; implemented for active skills below a configurable utility threshold with curation action logging;
- archived skills promote when demand recurs; implemented for archived skills with repeated retrieval demand, no harm/canary failures, and latest evaluator pass;
- duplicates merge only after probes pass; implemented for explicit duplicate graph edges as lower-utility duplicate archiving only when both latest skill versions have evaluator pass, with dedicated target/no-skill/regression/collision merge probe plans plus repair/split structured trial/gate proposals now logged for duplicate, harmful, or shadowing patterns;
- active bank budget is enforced; implemented by archiving lowest-utility overflow active skills.
- usage aggregation is deterministic and idempotent across repeated maintenance
  passes; implemented with focused tests and a real Postgres smoke proving
  windows, co-use edge counters, sequence/success counts, and usage clusters.
- usage cluster recommendations fail closed when support, successful outcome,
  sequence, or failure-ratio gates are not met, and remain recommendations only
  rather than autonomous topology proposal/apply actions.
- validation evidence for this slice: `uv run ruff check sidecar`, `uv run
  pytest` with 220 tests, `uv run python -m compileall -q sidecar`, and `git
  diff --check` passed; a compose Postgres smoke seeded retrieval plus
  attribution usage, aggregated 2 windows into one compose cluster, and proved a
  repeated pass left windows and edge counters unchanged.
- validation evidence for recommendation scoring: focused usage/worker tests
  passed, then `uv run ruff check sidecar`, `uv run pytest` with 222 tests, `uv
  run python -m compileall -q sidecar`, and `git diff --check` passed.
- validation evidence for improve/decompose negative-signal recommendations:
  focused usage tests passed, `uv run ruff check sidecar`, `uv run pytest` with
  230 tests, `uv run python -m compileall -q sidecar`, and `git diff --check`
  passed; a real Compose Postgres smoke seeded harmful attribution plus
  false-positive context-token outcomes and produced accepted `improve` and
  `decompose` recommendations without writing runtime skills.
- validation evidence for improve/decompose recommendation proposal
  consumption: focused topology tests passed, `uv run ruff check sidecar`, `uv
  run pytest` with 255 tests, `uv run python -m compileall -q sidecar`, and
  `git diff --check` passed.
- validation evidence for hydrated improve/decompose topology proposal reasons
  and task-ledger historical import lineage: focused topology/history tests
  passed, `uv run ruff check sidecar`, `uv run pytest` with 256 tests, `uv run
  python -m compileall -q sidecar`, `npm test --prefix plugin/autoskill` with
  18 tests, and `git diff --check` passed.
- historical source-item lineage; implemented as v2 content-safe lineage
  metadata on every parsed historical chunk, including source-item locator hash,
  item-key hash, item kind, chunk kind/index, optional record index, and optional
  line-range hash without storing raw filesystem paths.
- external collisions pause candidate creation for review; real external-root scanning,
  import recommendation, operator review actions, and stage-only import
  materialization are implemented without mutating external-owned roots.

## Phase 9 - Drift and Advanced Governance

Deliverables:

- contract extraction; implemented for SkillIR `environment_contracts` into DB-backed environment contract rows;
- drift checks; implemented as a deterministic first pass for static path-existence, bare-command availability, and required-env probes with drift event creation;
- package/schema/service/API drift checks; implemented as deterministic Python package, JSON schema, bounded TCP reachability, and bounded HTTP status probes without arbitrary shell execution or request bodies;
- diagnostic momentum accumulation; implemented so maintenance-worker
  `drift.check` jobs record one content-safe diagnostic signal per drift event
  into the existing momentum store, scoped to skill/version when available and
  keyed by hashed contract/probe identifiers;
- diagnostic momentum consumption; implemented so mutation-worker
  `repair.execute` jobs can claim ready-for-probe/ready-for-patch momentum
  records as fail-closed repair sources, record governance/provenance metadata,
  and queue drift rechecks or evaluator gates unless a future policy-approved
  staged manifest exists;
- localized repair;
- skill graph maintenance; implemented for accepted topology operations with
  mutation-worker downstream materialization that records transaction items,
  provenance edges, active transaction status, lifecycle updates, graph-edge
  materialization counts, and runtime invalidation evidence after deterministic
  trial gates pass;
- repeated shadowing events materialize deterministic `shadow` skill graph edges plus active contrastive shadowing probes;
- audit and retrieval policy reviews; implemented as a control-authenticated
  broker-policy review surface that reports active policy status, bounded
  replay-corpus coverage, production-tagged replay coverage, latest critical
  policy feedback, and bounded audit-chain verification without mutating
  routing state;
- evidence maturity, action-attribution check, control-flow event, and revocation request storage; implemented as v9 governance schema foundations, with passed recorded or contrastively induced intervention-replay proposal gates recording `intervention_validated` maturity for cited evidence and skill versions.

Acceptance:

- drift violations trigger targeted repair; implemented as drift-event repair-candidate metadata with localized repair plans and active drift probes that retire when contracts return valid or when an operator marks a known-noisy contract false-positive; conservative repair execution now queues drift rechecks or policy-approved staged writer applies rather than inventing broad autonomous mutations from incomplete source data;
- drift violations also accumulate diagnostic momentum before repair execution,
  preserving the spec rule that recurring drift evidence should guide probe or
  patch readiness instead of one-off reflection;
- validation evidence for drift diagnostic momentum: focused worker tests and
  focused ruff checks passed, full `uv run ruff check sidecar scripts`, `uv run
  pytest` with 263 tests, `uv run python -m compileall -q sidecar scripts`,
  plugin tests/check, compose config, and `git diff --check` passed; real
  Compose/Postgres smokes verified migration idempotency, `NULLS NOT DISTINCT`
  diagnostic aggregation for unscoped records, and claim/complete status flow
  through `repairing` -> `repair_queued`;
- curation logs features/actions/outcomes;
- audit integrity verifies, and retrieval-policy review fails closed on missing
  active policy or invalid bounded audit hash-chain verification while warning
  on empty replay evidence.
- accepted topology downstream materialization is tied back to the originating
  evolution transaction through rollback-aware transaction items and provenance
  edges for the operation plus touched skills; focused worker validation proved
  active transaction status, three governance items, six provenance edges,
  runtime invalidation, and lifecycle/edge execution for an `improve` operation;
  full `uv run ruff check sidecar`, `uv run pytest` with 301 tests,
  `uv run python -m compileall -q sidecar`, and `git diff --check` passed, and
  a real compose Postgres smoke persisted the same transaction/provenance
  evidence while archiving the subject skill, activating the successor skill,
  and materializing one `supersedes` edge.

## Phase 9.5 - Memory Quarantine and Control-Flow Integrity

Deliverables:

- DB-side governed memory quarantine; implemented as inactive pending
  `memory_quarantine` rows with proposed memory, taint, scanner findings, and
  explicit approve/reject/expire decisions;
- control-flow integrity logging; implemented as append-only
  `control_flow_events` rows for memory, skill, broker, tool, user, system, and
  external-skill-inventory influence over retrieval, routing, mutation, archive,
  promotion, and rollback decisions;
- control-authenticated operator APIs for recording/listing memory quarantine,
  deciding quarantined memory, and recording/listing control-flow events;
- runtime broker memory-influence audit wiring; implemented as bounded
  `memory_influence_ids` on context-hint requests that record memory-to-retrieval
  control-flow events without injecting proposed memory text into runtime hints;
- runtime memory-influence trust gating; implemented so broker requests must
  resolve every cited memory ID to an approved quarantined memory before
  retrieval/cache lookup, while pending/missing memory references fail closed and
  record content-safe blocked influence events;
- mutation memory-influence trust gating; implemented so repair execution and
  writer apply jobs that cite memory influence IDs require approved quarantined
  memory before queueing/applying mutation work, and record content-safe
  mutation control-flow events for approved and blocked cases.

Acceptance:

- quarantined memories do not become runtime-loaded, embedded, or mutation
  inputs merely by being recorded;
- invalid quarantine decisions and invalid control-flow source/influence kinds
  fail before persistence;
- focused admin tests prove pending quarantine, explicit approval, and
  memory-influenced retrieval event recording through the API surface;
- focused broker tests prove approved memory references create content-safe
  retrieval control-flow events while rendered hints remain sourced from scanned
  skill body-index documents, and unapproved memory references block before
  retrieval;
- focused worker tests prove approved memory references can influence guarded
  repair mutation queueing with audit events, while pending memory blocks
  mutation before writer apply is queued.

## Phase 10 - Production Hardening and Operator Readiness

Deliverables:

- operator profile inventory surfaces; implemented as control-authenticated
  bounded `GET /v1/profiles/models` and `GET /v1/profiles/embeddings` routes;
- deterministic deployment readiness reporting; implemented as
  `GET /v1/deployment/readiness`, which reports pass/block/warn state for
  database/auth/redaction, runtime broker config, writer root containment,
  active executor/text/embedding profiles, active broker policy, replay corpus,
  worker concurrency, and workspace-scoped job-queue health;
- operator disaster-recovery bundle export and guarded restore; implemented as
  `scripts/autoskill_backup.py` and `scripts/autoskill_restore.py`, covering a
  verifiable Postgres `autoskill` schema dump plus active/archive/staging runtime
  roots, with restore defaulting to verification and requiring explicit
  destructive confirmation before DB or filesystem overwrite;
- deterministic scanner red-team smoke; implemented as
  `scripts/autoskill_red_team.py`, covering hidden Markdown, bidi/invisible
  controls, dynamic fetch-exec, policy override, credential exfiltration,
  destructive host commands, sensitive-file harvest, cross-artifact bundle
  exfiltration chains, and allowed secret-boundary language;
- content-safe broker replay corpus mining; implemented as
  `scripts/autoskill_replay_corpus.py`, which lists retrieval telemetry
  candidates by log ID/query hash/selected skill metadata and records replay
  episodes only from an explicit operator plan containing redacted intents;
- production preflight remains sidecar-state-only and does not install the
  plugin, write runtime skills, activate autonomous apply, or mutate live
  OpenClaw configuration;
- Dev-01 deployment alignment is implemented separately from the sidecar
  preflight: compose workers, plugin config, and gateway env fallback all target
  `dev-01`, runtime context hints are enabled fail-soft, raw capture remains off,
  runtime broker semantic retrieval uses the active qualified embedding profile
  when present, and runtime tool-boundary blocking remains off.

Acceptance:

- missing production safety/configuration gates produce explicit blockers instead
  of a permissive status;
- persisted executor, qualified text model, active embedding profile, active
  broker policy, and production replay records can make the readiness report pass
  through the real asyncpg stores after compose migrations;
- readiness reporting is an operator preflight; the current Dev-01 deployment
  also passed live gateway capture/hint validation, active-profile semantic
  broker paraphrase validation, stored broker replay, production embedding
  validation, red-team smoke, and backup/restore dry-run.
- telemetry-derived replay episode creation does not persist or reconstruct raw
  prompts; operators must supply redacted replay intent text when promoting a
  retrieval log into the replay corpus.
