# SkillKernel TaskFlow Ledger

Managed durable work item: `skillkernel-autoskill-v1`

Goal: implement OpenClaw AutoSkill Manager from the v9 closed-design handoff until production acceptance criteria are satisfied.

Owner: Claudia front-stage; `codex-worker` may be used for bounded coding/debugging slices.

Canonical path: `/Warehouse/SkillKernel`

Guiding document: `openclaw-autoskill-ultimate-v9-closed-design-handoff.md`

## Current Phase

Phase 0/1 bootstrap.

## Current State

- Project directory created.
- Handoff saved and checksum-verified.
- Project-local `AGENTS.md` added.
- Initial sidecar, migration, plugin skeleton, and deterministic primitive tests are created and committed.
- Python tests pass.
- Python compile check passes.
- Plugin JavaScript syntax and Node spool tests pass.
- DB-backed event ingest is implemented with workspace upsert and `raw_events.event_id` idempotency.
- Sidecar ingest supports optional bearer-token auth.
- OpenClaw plugin spool replay and byte-bound compaction are implemented.
- Hook-package smoke tests import actual handlers, verify OpenClaw event metadata, and prove redacted envelope forwarding.
- Real local Postgres validation passed via compose: migration applied, first ingest accepted, duplicate ingest deduped, payload stored redacted.
- Plugin diagnostics report sidecar reachability/status and spool file/byte counts.
- Sidecar job queue primitives are implemented: idempotent enqueue, lease claim, completion, status counts, and expired-lease recovery.
- Real local Postgres job validation passed via compose: duplicate enqueue returned existing job, claim leased a job, completion marked success, expired lease was recovered and reclaimed.
- Sidecar scheduler tick primitive is implemented: due schedules enqueue idempotent jobs and advance `next_run_at`.
- Real local Postgres scheduler validation passed via compose: first tick enqueued one due job, second tick produced no duplicate, and the schedule advanced.
- Sidecar evidence derivation primitive is implemented: redacted raw events become observed `event_observation` evidence items with source-event provenance.
- Real local Postgres evidence validation passed via compose: first event ingest accepted, duplicate ingest deduped, first derive created one observed item, second derive produced no duplicate, and the evidence payload remained redacted.
- Retrieval schema support is implemented for body index documents, `vector(1536)` embedding records, lexical indexes, HNSW vector index, and retrieval logs.
- Deterministic lexical retrieval API is implemented for evidence/body-index records.
- Real local Postgres retrieval validation passed via compose: migration applied, evidence derived, lexical query found an evidence candidate, and a retrieval log row was written.
- Embedding upsert/search primitives are implemented with fixed `vector(1536)` dimension validation, finite-value checks, all-zero rejection, and pgvector cosine nearest search.
- Real local Postgres embedding validation passed via compose: migration applied, two non-zero embeddings inserted, nearest search returned both, and cosine ordering was correct.
- Embedding generation primitive is implemented: evidence/body-index text source discovery, deterministic hash embedder, `/v1/embeddings/generate` control endpoint, and idempotent skip of already-current embeddings.
- Real local Postgres embedding-generation validation passed via compose: migration applied, raw event ingested, evidence derived, one pending evidence source embedded, second generation pass skipped it, and pgvector search found the stored evidence embedding.
- Runtime context broker primitive is implemented: disabled-by-default config gate, retrieval-backed hint building, first-class abstain/defer decisions, scanned body-document filtering, duplicate skill suppression, composed-context scan, and compact set-aware hints.
- Real local Postgres broker validation passed via compose: seeded a scanned body-index document, broker retrieval logged the decision, and a bounded `skill_hint` returned for the matching intent.
- Sidecar worker dispatch primitive is implemented: explicit `scheduler`, `maintenance`, and `mutation` pools, `/v1/workers/run-once`, deterministic handlers for `scheduler.tick`, `evidence.derive`, and `embeddings.generate`, plus unsupported-job failure handling.
- Real local Postgres worker validation passed via compose: enqueued `evidence.derive` and `embeddings.generate` jobs, worker claimed them from the maintenance pool, derived one evidence item, generated one embedding, and completed both jobs successfully.
- Job retry backoff and terminal failure policy are implemented: failed attempts requeue with exponential backoff until `max_attempts`, and max-attempt failures become terminal `failed`; expired max-attempt leases are recovered to terminal failure instead of staying leased.
- Real local Postgres retry validation passed via compose: first isolated failed attempt requeued with future `available_at`, immediate reclaim skipped it, forced second attempt failed terminally at `max_attempts=2`.
- Broker exact-rerank, active/archive filtering, and graph expansion primitives are implemented: body candidates carry skill lifecycle metadata, archived matches become promotion candidates instead of runtime hints, and prerequisite/conflict/shadow/supersession edges can hydrate related body documents before set-aware rendering.
- Real local Postgres broker graph validation passed via compose: seeded active, archived, and prerequisite-linked skills; matching intent returned the active skill and prerequisite hint, suppressed the archived skill as a promotion candidate, and logged exact-rerank/graph-expanded reason codes.
- Runtime context hint cache and broker telemetry are implemented: enabled broker calls use a short in-process cache, rendered skill IDs/no-skill controls/suppression reasons/reason codes are attached back to retrieval logs, and cache hits avoid duplicate retrieval.
- Real local Postgres broker telemetry validation passed via compose: rendered hint updated `retrieval_logs.rendered_skill_ids`, `decision`, `no_skill_control`, and metadata reason fields; repeated request hit the broker cache.
- OpenClaw simple-plugin validator is not applicable to this hook plugin shape; Phase 0 still needs an installed-plugin smoke test against the live gateway.

## Next Gates

1. Confirm exact OpenClaw hook event names and return contracts with an installed-plugin smoke test.
2. Add durable daemon loop, pool concurrency limits, and graceful shutdown for workers.
3. Replace the deterministic development embedder with the configured production embedding provider when provider routing is wired.
4. Add active/archive duplicate matching and opportunity-miner integration before new skill creation.
5. Add explicit shadowing event detection from outcomes/corrections, beyond current broker suppression telemetry.

## Known Risks

- Hook event names are currently scaffolded from local code inspection and must be confirmed with an installed plugin smoke test before relying on capture coverage.
- Spool replay is best-effort from capture hooks and still needs a live gateway smoke test under actual hook concurrency.
- Message hook event aliases remain intentionally broad until live OpenClaw installed-plugin validation confirms current names.
- The dev compose Postgres volume is persistent; rerun migrations are intended to be idempotent.
- Worker dispatch is run-once only; durable daemon loop, pool concurrency limits, and graceful shutdown are still pending.
- Evidence derivation currently creates one observed item per captured event; higher-maturity recurring/contrastive/intervention evidence still needs aggregation logic.
- Embedding generation currently uses a deterministic local hash embedder as a development-safe provider stand-in; production embedding provider routing is still pending.
- Runtime context broker is still conservative: lexical retrieval-backed and scanned body docs only; vector fusion and explicit outcome-based shadowing detection are still pending.
