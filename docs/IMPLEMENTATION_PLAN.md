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
- worker pools.

Acceptance:

- jobs survive restart;
- duplicate ticks do not duplicate jobs; implemented with schedule-run idempotency keys;
- stuck leases recover; implemented for expired leases with remaining attempts.

## Phase 4 - Evidence, Embeddings, Retrieval

Deliverables:

- evidence extractor;
- redacted embeddings;
- lexical + vector + metadata search;
- exact rerank;
- active/archive/duplicate matching.

Acceptance:

- active and archived matches are considered before new skill creation;
- ANN recall audit exists;
- retrieval decisions are logged.

## Phase 5 - Runtime Context Broker

Deliverables:

- deterministic broker planner;
- set-aware context renderer;
- cache-backed context hint endpoint;
- shadowing logs.

Acceptance:

- hint returns under configured timeout;
- no LLM call runs in the hook path;
- no raw memory/evidence is injected.

## Phase 6 - Candidate Generation in Propose-Only Mode

Deliverables:

- opportunity miner;
- contrastive induction;
- typed LLM operation wrappers;
- SkillIR compiler;
- scanner;
- probe generator;
- evaluator.

Acceptance:

- candidates require grounded evidence;
- self-feedback-only changes fail;
- malicious artifacts are rejected;
- evaluator reports target, regression, and no-skill results.

## Phase 7 - Deterministic Writer and Rollback

Deliverables:

- staged writer;
- manifests and hashes;
- atomic apply;
- archive snapshots;
- rollback and canary states.

Acceptance:

- valid skill appears under active root;
- invalid paths are rejected;
- rollback restores the previous effective state;
- canary critical failures trigger rollback/freeze.

## Phase 8 - Autonomous Improvement and Curation

Deliverables:

- `autonomous_guarded` apply;
- improvement engine;
- archive/promote/merge/split;
- utility rollups;
- attribution ledger.

Acceptance:

- low-utility skills archive;
- archived skills promote when demand recurs;
- duplicates merge only after probes pass;
- active bank budget is enforced.

## Phase 9 - Drift and Advanced Governance

Deliverables:

- contract extraction;
- drift checks;
- localized repair;
- skill graph maintenance;
- audit and retrieval policy reviews.

Acceptance:

- drift violations trigger targeted repair;
- curation logs features/actions/outcomes;
- audit integrity verifies.
