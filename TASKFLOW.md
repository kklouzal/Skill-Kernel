# SkillKernel TaskFlow Ledger

Managed durable work item: `skillkernel-autoskill-v1`

Goal: implement OpenClaw AutoSkill Manager from the v9 closed-design handoff until production acceptance criteria are satisfied.

Owner: Claudia front-stage; `codex-worker` may be used for bounded coding/debugging slices.

Canonical path: `/Warehouse/SkillKernel`

Guiding document: `openclaw-autoskill-ultimate-v9-closed-design-handoff.md`

## Current Phase

Phase 6/7 control-plane buildout.

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
- Durable worker loop primitive is implemented: bounded async concurrency, idle sleep, max-iteration test hook, graceful `SIGINT`/`SIGTERM` shutdown through `autoskill.worker_main`, and `make worker-maintenance` / `make worker-scheduler` entrypoints.
- Real local Postgres worker-loop validation passed via compose: queued `worker-loop:derive` and `worker-loop:embed`, ran the maintenance loop with concurrency 2, and verified both jobs reached `succeeded` with one attempt.
- Embedding provider routing is implemented: deterministic hash provider remains the safe default, OpenAI-compatible `/embeddings` provider is configurable with base URL/API key/model/timeout, and both API and worker generation paths use the configured provider.
- Real local Postgres provider-routing validation passed via compose: configured a non-default hash embedding model, generated one evidence embedding, and verified pgvector search found it under the configured model name.
- Active/archive duplicate matching primitive is implemented: `/v1/skills/match` checks candidate descriptions/runtime text against body-index documents, returns `reuse_active`, `consider_archive_promotion`, or `create_candidate`, and keeps active/archived match lists separate for opportunity-miner gating.
- Real local Postgres duplicate-match validation passed via compose: seeded active and archived body-index matches, matcher returned `reuse_active`, surfaced both active and archived matches, and wrote a retrieval log.
- Deterministic opportunity-miner primitive is implemented: groups repeated observed evidence, builds candidate descriptions with trigger terms, calls duplicate matching before recommending action, exposes `/v1/opportunities/mine`, and adds `opportunities.mine` as a maintenance job kind.
- Real local Postgres opportunity-miner validation passed via compose: two repeated `message_received` evidence records were grouped into one opportunity, an active body-index skill was matched, and the recommendation was `reuse_active` instead of creating a duplicate candidate.
- Worker observability/configured concurrency primitive is implemented: settings now define scheduler/maintenance/mutation pool concurrency, worker loops default to those settings unless overridden, `/v1/status` includes worker health, and `/v1/workers/health` reports pool job kinds plus job counts by status, kind, and pool.
- Propose-only candidate SkillIR scaffolding is implemented: `/v1/candidates/propose` mines repeated opportunities, skips active/archive matches according to opportunity recommendations, and returns scanner-checked SkillIR previews with cited evidence IDs without writing runtime skill files.
- Candidate persistence and deterministic probe planning are implemented: proposal persistence writes inactive candidate skill/version rows, inactive compiled-file metadata, body-index documents, planned target/no-skill/regression probes, provenance-ready evidence links, and a planned proposal-gate evaluation without writing runtime skill files.
- Real local Postgres candidate-persistence validation passed via compose: two redacted repeated events produced one opportunity, one proposal, one persisted candidate version, three planned probes, one planned evaluation, and two body-index documents.
- Deterministic proposal-gate evaluator execution is implemented: `/v1/evaluations/run` and `evaluations.run` maintenance jobs execute planned target/no-skill/regression probes, record per-probe results, and update `skill_versions.evaluator_status` without activating candidates.
- Real local Postgres evaluator validation passed via compose: a persisted candidate produced target/regression pass results, a no-skill-control `needs_intervention` result, and matching `needs_intervention` statuses on the evaluation row and skill version.
- Outcome-based shadowing detection primitive is implemented: `/v1/shadowing/detect` scans recent evidence for explicit `skill_shadowed` outcomes, selected-vs-expected skill mismatches, and correction phrasing, then records medium-risk attribution events without changing routing.
- v9 governance schema/store primitives are implemented: evolution transactions now have idempotency keys, plan hashes, source evidence/memory links, policy snapshots, metrics, transaction item records, evidence maturity records, action-attribution checks, control-flow events, and queued revocation requests.
- Governance control APIs are implemented for starting idempotent evolution transactions, updating transaction status/metrics, recording transaction items with rollback metadata, and queuing revocation requests.
- Real local Postgres governance validation passed via compose: migration applied, an idempotent `create_skill` transaction returned `created=True` then `created=False`, a staged skill-file transaction item was recorded, transaction status advanced to `staged`, and a rollback revocation request was queued.
- Candidate proposal persistence is now anchored to governance transactions: `/v1/candidates/propose` starts or accepts an idempotent `candidate_proposal` transaction, stamps persisted inactive `skill_versions.created_by_transaction_id`, records rollback-aware transaction items for the candidate version and inactive compiled `SKILL.md`, and advances the transaction to `staged`.
- Real local Postgres candidate-transaction validation passed via compose: migration applied, two repeated evidence items produced one proposal, one inactive candidate version was persisted with `created_by_transaction_id`, transaction status advanced to `staged`, source evidence IDs were recorded, and transaction items were written for `skill_version` and `compiled_skill_file`.
- Provenance/revocation traversal primitives are implemented: provenance edges can be recorded idempotently through the governance store/API, the schema now enforces unique provenance edges, `/v1/revocations/preview` returns a bounded derived-object traversal, and queued revocation requests populate an impact summary when none is supplied.
- Real local Postgres provenance traversal validation passed via compose: migration applied, duplicate evidence→skill-version edge recording returned `created=False`, skill-version→embedding derived state was linked, traversal from the root evidence item found three impacted objects/two edges, and a rollback revocation request was queued with traversal summary.
- Deterministic staged writer manifest primitives are implemented: compiled `SKILL.md` artifacts can be staged under a bounded staging root with scanner blocking, slug validation, symlink/path containment checks, support-artifact path allowlisting, writer manifests, and staged file hash verification without activating runtime skill files.
- Deterministic active-root apply and rollback filesystem primitives are implemented: verified writer manifests can replace one `skills/autoskill/<slug>` directory through a temporary same-root directory, previous active versions are snapshotted under `.autoskill/archive` with archive manifests/hashes, rollback restores a verified archive snapshot, and active snapshot symlinks or target path escapes are rejected.
- Writer validation passed locally: focused writer tests covered manifest creation/verification, scanner rejection, support-artifact allowlisting, staging symlink rejection, active apply, archive snapshot verification, rollback restore, manifest target escape rejection, and active snapshot symlink rejection; full Python suite passed with 68 tests.
- Transaction-aware writer apply/rollback service primitives are implemented: staged manifest apply records active compiled-file and archive-snapshot transaction items with rollback actions, rollback restore records a rolled-back compiled-file item, transaction statuses advance through applying/applied and rolling_back/rolled_back, and failed governance recording after filesystem apply restores the previous active snapshot or removes the newly-created active path.
- Writer governance validation passed locally: focused writer tests covered transaction item recording for apply, fail-closed active restore on governance recording failure, and rollback item recording; full Python suite passed with 71 tests.
- Sidecar writer control endpoints are implemented: `/v1/writer/apply` and `/v1/writer/rollback` require control auth, resolve staging/archive roots under the configured workspace root, fail closed unless `active_root` is the pinned `skills/autoskill` root expected by the deterministic writer, and call the transaction-aware apply/rollback wrappers.
- Writer API validation passed locally: focused writer/API tests staged a compiled skill, applied it through the sidecar route, recorded active/archive transaction items, rolled back through the sidecar route, and restored the previous `SKILL.md`.
- Real local Postgres writer endpoint validation passed via compose: migration applied, staged manifest applied through `/v1/writer/apply`, rollback restored the prior active `SKILL.md` through `/v1/writer/rollback`, DB rows showed `compile` status `applied` with two transaction items and `rollback_skill` status `rolled_back` with one transaction item, and compose was cleaned down afterward.
- Writer artifact provenance edges are implemented: transaction-aware apply/rollback now link each recorded active/archive/rollback writer transaction item from its evolution transaction, so revocation traversal can discover filesystem writer artifacts by transaction root.
- Writer provenance validation passed locally: focused writer/governance tests covered apply and rollback provenance edges, and a real local Postgres compose smoke showed apply traversal with three impacted objects/two edges plus rollback traversal with two impacted objects/one edge while restoring the previous active `SKILL.md`.
- Canary/freeze lifecycle primitives are implemented: canary results persist with skill/version/transaction links, critical canary failures set `skills.lifecycle_state='frozen'`, freeze reasons and last canary status are stored, `/v1/control/freeze`, `/v1/control/unfreeze`, and `/v1/canary/results` are control-authenticated, frozen skills are suppressed by the existing broker lifecycle filter, and transaction-scoped critical canaries queue rollback revocation requests.
- Real local Postgres canary/freeze validation passed via compose: migration applied, an active skill received a transaction-scoped critical canary result, the skill moved to `frozen`, the freeze reason was recorded, a `canary_result` transaction item was written with `activation_state='frozen'`, and a rollback revocation request was queued against the originating evolution transaction.
- Mutation-worker rollback revocation execution is implemented: queued rollback `revocation_requests` can be claimed by the mutation pool, mapped back to the originating evolution transaction's active compiled-file rollback action, executed through the transaction-aware deterministic writer rollback path, and completed with rollback transaction/artifact evidence.
- Real local Postgres rollback-revocation validation passed via compose: migration applied, a staged manifest replaced an active `SKILL.md`, a rollback revocation was queued for the apply transaction, `revocations.rollback` ran in the mutation pool, the prior active `SKILL.md` was restored from the archive manifest, and compose was cleaned down afterward.
- Rollback revocation invalidation is implemented for provenance traversal impacted objects: mutation-worker rollback completion now calls retrieval and embedding invalidation hooks, records deletion counts in the revocation summary, and focused worker coverage validates per-object invalidation.
- Operator/admin read surfaces are no longer stubs: `/v1/skills` lists persisted skill/version lifecycle metadata and `/v1/audit/recent` returns recent DB audit records plus bounded hash-chain verification.
- Phase 8 utility/curation primitives are implemented as a deterministic first pass: skill utility rollups combine attribution, retrieval rendering, shadowing, harm, and canary failure features; `curation.run` archives active skills below a configured utility threshold and logs curation actions.
- Real local Postgres utility/curation/audit validation passed via compose: migration applied, a low-utility active skill was archived, archived skill listing found it, an audit record was appended, and the audit chain verified.
- Phase 8 promotion/merge/budget curation is implemented as deterministic lifecycle-state actions: recurring archived skills can promote back to active, explicit duplicate graph edges archive the lower-utility duplicate, and active-bank budget enforcement archives lowest-utility overflow skills.
- Real local Postgres promotion/merge/budget validation passed via compose: a retrieval-recurring archived skill promoted to active, an explicit duplicate edge archived the lower-utility skill, a harmful low-utility active skill archived, active-budget overflow archived, and curation actions recorded `promote_archive`, `merge_duplicate`, `archive`, and `enforce_active_budget`.
- Phase 9 contract/drift primitives are implemented as a deterministic first pass: SkillIR `environment_contracts` persist into DB contract rows, `contracts.extract` and `drift.check` worker jobs/API endpoints are wired, static path-existence probes update contract status, and violated contracts create drift events with repair-candidate metadata.
- Real local Postgres contract/drift validation passed via compose: migration applied, a SkillIR path contract was extracted, the missing path was marked violated, and a drift event was recorded.
- Phase 9 deterministic drift probes now cover static path existence, bare executable availability (`static:which:<command>`), and required environment presence (`static:env:<NAME>`) without executing arbitrary shell commands.
- Real local Postgres command/env drift validation passed via compose: migration applied, three contracts were extracted, command and present-env probes were marked valid, the missing-env probe was marked violated, and one drift event was recorded.
- ANN/vector recall audit is implemented: `/v1/embeddings/recall-audit` compares index-preferred nearest-neighbor results against exact pgvector ordering for a bounded sample and reports min/average recall plus per-sample failures.
- Real local Postgres recall-audit validation passed via compose with two stored embeddings and perfect recall against exact ordering.
- Persistent worker heartbeat records are implemented: worker loops upsert `worker_heartbeats`, `/v1/workers/health` includes recently observed workers, and heartbeat summaries track loop iterations/claimed/succeeded/failed/idle counts.
- Real local Postgres worker heartbeat validation passed via compose: a worker heartbeat was inserted, updated from `running` to `idle`, and listed with preserved `first_seen_at`, refreshed `last_seen_at`, pool/concurrency, and summary metadata.
- Initial-create rollback deletion is implemented: mutation-worker rollback revocations now support `delete_active_path` rollback actions for newly-created active skills with no archive snapshot, record rollback transaction items/provenance, and run retrieval/embedding invalidation.
- OpenClaw simple-plugin validator is not applicable to this hook plugin shape; Phase 0 still needs an installed-plugin smoke test against the live gateway.

## Next Gates

1. Confirm exact OpenClaw hook event names and return contracts with an installed-plugin smoke test.
2. Add production embedding provider live validation once credentials/provider endpoint are configured.
3. Add lease renewal for long-running jobs once job handlers start exceeding one lease interval.
4. Add contrastive induction and future intervention replay so no-skill-control probes can graduate from `needs_intervention` to pass/fail.
5. Add shadow-edge/probe generation from repeated attribution events after deduplication policy is defined.
6. Add active-cache invalidation and expanded derived-state revoke handlers for frozen skills and non-body-index transaction-derived artifacts.
7. Add mutation-worker apply orchestration only after autonomous apply policy and intervention replay gates are ready.
8. Extend Phase 8 beyond deterministic promotion/archive/merge/budget curation: split support, guarded improvement planning, promotion evaluator gates, and active-bank optimization beyond utility ordering.
9. Expand Phase 9 beyond static path/command/env checks: package/API/schema/service probes, false-positive controls, drift probe lifecycle, and localized repair proposal generation.

## Known Risks

- Hook event names are currently scaffolded from local code inspection and must be confirmed with an installed plugin smoke test before relying on capture coverage.
- Spool replay is best-effort from capture hooks and still needs a live gateway smoke test under actual hook concurrency.
- Message hook event aliases remain intentionally broad until live OpenClaw installed-plugin validation confirms current names.
- The dev compose Postgres volume is persistent; rerun migrations are intended to be idempotent.
- Worker health now includes persistent heartbeat records; lease renewal is still pending for future handlers that exceed one lease interval.
- Evidence derivation currently creates one observed item per captured event; higher-maturity recurring/contrastive/intervention evidence still needs aggregation logic.
- Embedding generation defaults to deterministic local hash embeddings until production provider settings are configured and live-validated.
- Runtime context broker is still conservative: lexical retrieval-backed and scanned body docs only; vector fusion and shadow-edge/probe generation from attribution events are still pending.
- Candidate evaluator execution is deterministic and conservative; no-skill-control probes remain `needs_intervention` until real intervention/counterfactual replay exists, and this must pass before any staged writer/activation path is added.
- Candidate proposal persistence is transaction-anchored, and staged writer apply/rollback plus canary freeze now have sidecar control endpoints, but mutation-worker orchestration still needs end-to-end caller wiring before autonomous apply is allowed.
- Revocation traversal now previews impacted derived artifacts, staged writer artifacts have provenance edges, and critical canary failures can freeze skills plus queue rollback revocation requests. Mutation-worker rollback execution is implemented for archive-backed rollbacks and initial-create active-path deletion, and invalidates body-index/embedding objects from traversal summaries; broader revoke handlers are still pending.
- Utility rollups are deterministic v1 scoring, not full marginal-value/intervention scoring yet; curation now handles archived promotion, explicit duplicate merge/archive, low-utility archive, and active-budget overflow, while split support, promotion evaluator gates, and guarded improvement planning remain pending.
- Contract/drift checks are deterministic v1 path/command/env probes only; package/API/schema/service probes and repair execution remain pending.
