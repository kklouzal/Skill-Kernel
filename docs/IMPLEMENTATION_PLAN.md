# SkillKernel Implementation Plan

This plan mirrors section 27 of the v9 handoff and turns it into repo-level gates.

## Phase 0 - Confirm OpenClaw Seams

Deliverables:

- exact hook package shape for the target OpenClaw version;
- manifest keys for plugin-owned hooks;
- hook names and payload shape for session, message, tool, model, prompt/context, compaction, and gateway events;
- active skill root and archive invisibility proof;
- fail-soft context hint proof.

Acceptance:

- an installed local plugin can capture tool and turn events;
- a generated test skill loads from `<workspace>/skills/autoskill/<slug>/SKILL.md`;
- archived skills under `<workspace>/.autoskill/archive` are invisible to OpenClaw skill loading;
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

- sidecar outage does not block OpenClaw;
- only redacted payloads are persisted;
- spool replay is idempotent; implemented as accepted-or-duplicate deletion from bounded JSONL spool.
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
- redacted embeddings; storage/search primitives, deterministic development generation worker, and configurable provider routing are implemented;
- lexical + vector + metadata search; lexical evidence/body-index search and pgvector nearest search are implemented;
- exact rerank; implemented as deterministic broker rerank over lexical score, query overlap, lifecycle, and graph edges;
- active/archive matching; implemented in runtime broker and `/v1/skills/match` so archived matches are promotion candidates rather than injected hints or duplicate new skills;
- duplicate matching;
- ANN recall audit; implemented as `/v1/embeddings/recall-audit`, comparing index-preferred nearest-neighbor results against exact pgvector ordering for a bounded sample.

Acceptance:

- active and archived matches are considered before new skill creation;
- ANN recall audit exists; implemented and validated against local Postgres;
- retrieval decisions are logged.

## Phase 5 - Runtime Context Broker

Deliverables:

- deterministic broker planner;
- set-aware context renderer; implemented as a conservative retrieval-backed first pass with duplicate skill suppression and prerequisite graph expansion;
- cache-backed context hint endpoint; endpoint is present behind a disabled-by-default config gate with short in-process cache;
- shadowing logs; broker suppression/rendering telemetry is attached to retrieval logs, and outcome/correction-based shadowing detection records attribution events.
- external-skill inventory awareness; implemented as control-authenticated upsert/list APIs, hashed-root/file-hash/status/risk metadata persistence, lexical retrieval of visible/changed external skills, broker suppression as non-runtime collisions, and duplicate-match `external_collision_review` decisions that block automatic candidate creation.

Acceptance:

- hint returns under configured timeout;
- no LLM call runs in the hook path;
- no raw memory/evidence is injected; implemented for evidence-only matches by deferring without hint text.
- rendered skill IDs, suppression reasons, and reason codes are recorded on retrieval logs.
- external skills are visible to collision analysis but are never injected as runtime hints or selected for autonomous mutation.

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
- contrastive induction; implemented for redacted paired outcome evidence by attaching generated `intervention_replay` inputs to no-skill-control probes, persisting contrastive probe maturity, and evaluating through the existing proposal gate.

Acceptance:

- candidates require grounded evidence; proposal scaffolds carry cited evidence IDs, skip active/archive duplicates, and persist inactive candidate revisions only;
- persisted candidate revisions are stamped with `created_by_transaction_id` and rollback-aware transaction items are recorded for the inactive version and compiled `SKILL.md`;
- self-feedback-only changes fail;
- malicious artifacts are rejected;
- evaluator reports target, regression, and no-skill results; no-skill-control remains `needs_intervention` until recorded or redacted contrastive replay evidence exists.

## Phase 7 - Deterministic Writer and Rollback

Deliverables:

- v9 transaction/provenance/revocation schema; implemented for idempotent evolution transactions, transaction items, evidence maturity, action-attribution checks, control-flow events, and revocation requests;
- transaction control APIs; implemented for starting idempotent transactions, updating transaction status/metrics, recording rollback-aware transaction items, and queuing revocation requests;
- staged writer; implemented for scanner-gated compiled `SKILL.md` staging under a bounded staging root without active-root mutation;
- manifests and hashes; implemented for writer manifests with staged file hash verification;
- atomic apply; implemented as a deterministic same-root active skill directory replacement from verified writer manifests;
- archive snapshots; implemented as manifest-and-hash verified snapshots of previous active `skills/autoskill/<slug>` directories;
- rollback; implemented as deterministic active-root restore from verified archive snapshots;
- transaction-aware writer service wrappers; implemented for apply/rollback transaction status updates, active compiled-file and archive-snapshot transaction items, rollback metadata, and fail-closed filesystem recovery when governance recording fails after apply;
- sidecar writer control endpoints; implemented for `/v1/writer/apply` and `/v1/writer/rollback` with control auth, workspace-contained staging/archive roots, pinned `skills/autoskill` active-root policy, and transaction-aware writer wrapper calls;
- writer artifact provenance traversal; implemented by linking active/archive/rollback writer transaction items from their evolution transaction during apply/rollback;
- canary states; implemented as canary-result storage plus deterministic freeze/unfreeze
  control APIs that suppress frozen skills through the existing broker lifecycle filter and
  queue rollback revocation requests for transaction-scoped critical canary failures.
- mutation-worker rollback revocation execution; implemented for queued rollback revocation
  requests whose originating transaction recorded an archive-backed compiled-file rollback
  action or an initial-create active-path deletion rollback action.
- rollback-derived invalidation; implemented for traversal-summary impacted objects by deleting
  matching body-index documents and embeddings during mutation-worker rollback completion.

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
- mutation-pool `revocations.rollback` jobs claim queued rollback revocation requests, start an idempotent `rollback_skill` transaction, restore the recorded archive manifest through the transaction-aware writer rollback path, and complete the revocation request with rollback artifact evidence; implemented and validated with focused worker tests plus compose/Postgres smoke coverage;
- valid skill appears under active root;
- invalid paths are rejected;
- rollback restores the previous effective state;
- canary critical failures trigger rollback/freeze; freeze, rollback revocation queueing, archive-backed mutation-worker rollback execution, initial-create active-path deletion rollback, body-index/embedding invalidation, active broker-cache invalidation, and fail-closed policy-approved mutation-worker writer apply orchestration are implemented, while broader per-object revoke handlers remain pending.
- long-running job leases renew while handlers are still running; implemented in the job store, worker execution wrapper, and control API with focused tests.

## Phase 8 - Autonomous Improvement and Curation

Deliverables:

- `autonomous_guarded` apply; implemented as fail-closed mutation-worker `writer.apply` orchestration that only applies a staged manifest when the queued job carries explicit `policy_approved=true`;
- improvement engine;
- archive/promote/merge/split; archive, evaluator-gated archived promotion, evaluator-gated explicit duplicate merge/archive, active-bank budget overflow, and planned split/improvement/disambiguation curation actions are implemented as deterministic lifecycle-state or planning actions;
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
