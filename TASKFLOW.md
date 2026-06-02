# SkillKernel TaskFlow Ledger

Managed durable work item: `skillkernel-autoskill-v1`

Goal: implement SkillKernel / OpenClaw AutoSkill Manager from the v16 coherence-closed implementation handoff until production acceptance criteria are satisfied.

Owner: Claudia front-stage; `codex-worker` may be used for bounded coding/debugging slices.

Canonical path: `/Warehouse/SkillKernel`

Guiding document: `skillkernel-openclaw-autoskill-ultimate-v16-coherence-closed-implementation-handoff.md`

## Current Phase

Phase 10/11 v16 coherence closure and production-hardening buildout.

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
- Retrieval schema support is implemented for body index documents, profile-scoped pgvector embedding records, lexical indexes, a default-dimension HNSW vector index, and retrieval logs.
- Deterministic lexical retrieval API is implemented for evidence/body-index records.
- Real local Postgres retrieval validation passed via compose: migration applied, evidence derived, lexical query found an evidence candidate, and a retrieval log row was written.
- Embedding upsert/search primitives are implemented with finite-value checks, all-zero rejection, stored `embedding_dim`, profile-scoped ownership, dimension-filtered pgvector cosine nearest search, and a default 1536-dimension HNSW index path.
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
- Embedding profile qualification now probes both deterministic hash profiles and
  OpenAI-compatible embedding profiles through the bounded provider embedder path,
  recording dimension, finite-value, non-zero, stability, and negative-pair
  separation checks without persisting API keys or probe text.
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
- Long-running job lease renewal is implemented: `JobStore.renew_job_lease` extends currently held leases, `/v1/jobs/{job_id}/renew-lease` exposes the control surface, and worker handlers periodically renew leases while still running; focused job/worker tests cover API renewal and handler-side renewal.
- Shadowing control materialization is implemented: repeated selected-vs-expected shadowing evidence records medium-risk attribution events, creates a `shadow` skill graph edge, and activates a contrastive `shadowing` probe for broker/evaluator use.
- Proposal-gate intervention replay is implemented: no-skill-control probes with recorded `no_skill` and `skill_visible` replay outcomes deterministically pass or fail instead of staying `needs_intervention`, and passed proposal gates record `intervention_validated` maturity for the skill version and cited evidence.
- Contrastive replay induction is implemented for proposal gates: redacted evidence rows carrying paired `autoskill_replay`/`contrastive_replay` outcomes are clustered by planned no-skill probe evidence IDs, attached to the probe as deterministic `intervention_replay`, persisted with `maturity='contrastive'`, and then evaluated through the existing proposal gate.
- Contrastive replay induction now also accepts normalized attribution, canary, and broker outcome schemas, so `missing_skill`/`skill_helped`, canary pass/fail, and broker no-skill control outcomes can produce deterministic no-skill versus skill-visible intervention replay evidence.
- Phase 9 deterministic drift probes now cover static path existence, bare executable availability, required environment presence, Python package availability, JSON schema loadability, and bounded TCP reachability without arbitrary shell execution.
- Drift checks now create active drift probes for violated contracts, retire contract-scoped drift probes when a contract returns to valid, and attach localized repair-plan metadata to drift events without mutating runtime skills.
- Runtime context cache invalidation is implemented: the in-process broker cache can evict by workspace and skill IDs, exposes a control endpoint, and freeze/critical-canary paths invalidate affected skill hints immediately.
- Promotion/duplicate curation now has evaluator gates: archived promotion and duplicate merge/archive record blocked curation actions unless the latest skill versions have passed evaluator status.
- Phase 8 guarded curation planning is implemented: repeated harmful outcomes and shadowing patterns create planned `plan_improvement`, `plan_disambiguation_repair`, or `plan_split` curation actions instead of directly mutating skill text.
- Mutation-worker apply orchestration is implemented as fail-closed `writer.apply`: the mutation pool can apply a staged manifest through the transaction-aware writer only when the job payload explicitly sets `policy_approved=true`.
- Durable worker entrypoint wiring now includes utility and contract stores, so long-lived maintenance workers can actually execute `curation.run`, `contracts.extract`, and `drift.check` jobs rather than only the in-process API test path.
- External-skill inventory and collision awareness are implemented: external skills can be upserted/listed through control-authenticated APIs, persisted with hashed roots/file hashes/status/risk metadata, surfaced by lexical retrieval as non-runtime `external_skill` candidates, suppressed by the broker instead of injected, and returned by duplicate matching as `external_collision_review` so candidate creation pauses for review instead of mutating external skill roots.
- Real local Postgres contrastive-replay validation passed via compose: a fresh candidate evaluation consumed redacted no-skill failure and skill-visible success evidence, persisted the no-skill probe as `contrastive`, passed the proposal gate, and recorded intervention-validated maturity rows for the skill version plus both evidence items.
- Real local Postgres drift/curation/writer validation passed via compose: one SkillIR env contract was extracted, the missing env var created one drift event and one active drift probe, repeated harmful attribution produced one planned improvement action, attribution/canary contrastive evidence produced a replay, and a policy-approved mutation-worker `writer.apply` job activated a staged autoskill artifact.
- Real local Postgres external-skill validation passed via compose: migration applied, first external inventory upsert created one row, second upsert updated the same row to `changed`, status-filtered listing returned it, lexical retrieval surfaced it as `external_skill`, and compose was cleaned down afterward.
- v14 SkillIR effect signatures are implemented in the typed model: outputs, effects, state delta, side effects, termination, retry/idempotency, unsafe-when, failure modes, support artifact load policy, and compiler scanning of the full SkillIR payload.
- The deterministic compiler now emits runtime-facing `OUTPUTS` and `EFFECTS`, estimates context tokens, and fails compiled artifacts that exceed the configured context budget.
- v14 schema substrate is implemented for trace spans/links, diagnostic momentum, executor profiles, text model profiles, embedding profiles, context artifacts, context token ledgers, SkillGraphIR operation records, usage windows, co-usage edges, and usage clusters.
- Sidecar control surfaces now expose trace-span start/finish/list, diagnostic momentum record/list, executor profile upsert/list, text model profile upsert, embedding profile upsert, context artifact recording, and context token-ledger recording.
- Trace spine propagation has started: plugin event envelopes now include `trace_id`, `span_id`, and `parent_span_id`, Python ingest models accept those fields, and `raw_events` persists them.
- Job queue trace propagation is implemented: job enqueue accepts explicit trace context, new API/scheduled jobs generate missing `trace_id`/`span_id`, existing dev rows are migration-backfilled and constrained non-null for trace/span, and job list/claim/renew/complete responses preserve the trace fields.
- Worker execution trace-span recording is implemented: claimed jobs open content-safe `job` spans under their queued job span, close spans as `ok` or `error`, and include safe job/worker/output-key/error metadata without raw payload capture.
- Retrieval trace propagation is implemented: direct retrieval queries and broker context-hint retrieval now pass trace/span/parent IDs into `retrieval_logs`, and new retrieval logs generate trace/span IDs when callers omit them.
- Evaluator trace propagation is implemented: API-triggered and worker-triggered proposal-gate evaluation runs open content-safe `evaluator` spans, preserve caller/job trace roots, and close spans with safe counts/status/object refs instead of SkillIR or probe payloads.
- Semantic model-call trace propagation is implemented for the typed LLM client: each completion attempt opens a content-safe `llm_call` span under the caller/job span, records the LLM invocation against that span, closes successful calls with safe token/finish metadata, and closes unsupported routes as denied without storing prompt or response text in span attributes.
- Broker context governance recording is implemented: rendered broker hints persist as `broker_hint` context artifacts, and broker decisions write token-ledger rows for `skill_visible`, `skill_hidden`, and `no_skill` visibility states.
- Marginal-value outcome updates are implemented for context token ledgers: observed outcomes can update existing ledger rows with task success, utility delta, token savings, latency/tool-call deltas, derived marginal-value score, and context-value-per-token, while linked context artifacts receive the latest marginal outcome and semantic density score.
- SkillGraphIR validation is implemented for topology operation graphs, including missing-node checks, compose effect-gap blocking, and decompose effect coverage requirements.
- Propose-only topology operation planners are implemented for `improve`, `compose`, and `decompose`: planners validate effect compatibility, emit deterministic SkillGraphIR only when gates pass, produce stable plan hashes/idempotency keys, include rollback-aware transaction metadata, and create planned trial metadata without DB writes or runtime file activation.
- Topology proposal persistence is implemented: `/v1/topology/propose` records propose-only `improve`/`compose`/`decompose` plans into `skill_graph_operations`, starts an idempotent evolution transaction, records rollback-aware transaction items, writes `planned_topology_trials`, and links evidence/transactions/operations/trials through provenance without activating runtime files.
- Embedding profile qualification is wired into embedding generation: `/v1/embeddings/generate` can target an `embedding_profile_key`, requires the profile to be `qualified`, honors the profile's configured dimension, and routes generation through the profile model/provider instead of ad hoc settings.
- Embeddings are now profile-owned, not only model-string-owned: `autoskill.embeddings` stores `embedding_profile_id`, profile-scoped uniqueness prevents collisions between two qualified profiles using the same model string, API upsert/search/recall/generation paths accept or propagate profile IDs, and profile-scoped Postgres smoke validation proved same-object/same-model records remain separate.
- Typed LLM client and invocation audit substrate are implemented: model profiles include thinking-level/fallback policy, `LLMClient` fetches one workspace/profile text profile, routes `openai_compatible` calls through bounded `/chat/completions`, records content-safe `llm_invocations` rows with trace/span/token estimates/status/errors/thinking decisions, and fails the unstable `openclaw` route closed as `unsupported`.
- First-class profile qualification run substrate is implemented: model and embedding qualification runs have dedicated tables, control-authenticated API entry points, deterministic text-profile JSON/evidence/refusal probes through the typed LLM client, deterministic local hash embedding dimension/stability/separation probes, and profile rows are stamped with latest verdict/status.
- Executor-profile compatibility now participates in runtime broker routing: `skill_profile_compatibility` records can be upserted through a control API, runtime context-hint requests can carry `executor_profile_id`, broker cache keys are executor-profile-scoped, and explicit `blocked`/`drifted` skill-version compatibility suppresses otherwise renderable skill hints for that executor.
- Proposal-gate evaluation now updates executor-profile compatibility as deterministic derived state: executor-scoped evaluations stamp matching skill versions as `compatible`, `degraded`, or `blocked` with evaluation IDs, reason codes, and trace/span evidence, so broker routing can consume evaluator results without manual compatibility writes.
- Broker policy artifact primitives are implemented: active `broker_policy_versions` can override bootstrap broker limits/graph policy/max rendered skills, context hint cache keys include the active policy, retrieval/context governance telemetry records `broker_policy_version_id`, and control APIs can upsert, activate, replay, and record canary feedback for policy versions.
- Writer activation gates are now explicit on both queued mutation jobs and the direct writer apply API: when `activation_gate_required=true`, the staged manifest's `skill_version_id` must resolve to a scanner-passed, evaluator-passed, proposal-gate-passed skill version, and any supplied executor profile must be `compatible` before active-root files are exposed.
- Runtime context-loadability gates are now attached to compiled skill artifacts: staged writer manifests include `runtime_skill_body` loadability metadata, scanner/equivalence/token-budget statuses, token counts, and text hashes; writer apply rejects manifests without passed context gates, and candidate persistence records matching `skill_md` context artifacts for inactive candidate versions.
- First-class support artifact writer coverage is implemented for staged runtime
  manifests: declared support files are path-allowlisted, hash-checked, scanned,
  token-budgeted, co-load bundle-scanned, stamped with loadability class and
  content hash metadata, applied/archived/restored with the active skill
  directory, and recorded as `support_artifact` governance/provenance items.
- Context-value curation signals now feed utility rollups and improvement
  planning: `context_token_ledgers` marginal value, average context value per
  token, ignored/false-positive load counts, and token waste are folded into
  `SkillUtilityFeatures`, utility scoring, curation action features, and
  deterministic improvement planning with a context-value acceptance gate.
- External-skill scanner job wiring is implemented: read-only skill roots can be passed to the worker entrypoint, `external_skills.scan` inventories `*/SKILL.md` files without storing raw root paths, hashes roots/files, parses public name/description frontmatter, and quarantines scanner-blocked external skills.
- Scanner classification now blocks deterministic first-pass harmful capability and
  policy-override patterns: credential exfiltration, destructive host commands,
  sensitive file harvesting, and policy/approval/sandbox override instructions,
  while preserving explicit secret-boundary language.
- Runtime tool-call boundary enforcement is implemented as an opt-in
  `runtimeToolBoundary.enabled` plugin gate on `before_tool_call`, returning
  OpenClaw's terminal `{ block: true, blockReason }` shape for deterministic
  high-risk patterns while preserving capture-only behavior by default.
- Expanded rollback revocation invalidation now marks retrieval logs and context-governance records in addition to deleting body-index documents and embeddings, so rollback summaries report `retrieval_logs_invalidated` and `context_records_invalidated` derived-state counts.
- Rollback revocation invalidation now also handles topology derived state: mutation workers can retire `planned_topology_trials`, mark `skill_graph_operations` rolled back, and report `topology_records_invalidated` in revocation summaries.
- Rollback revocation invalidation now also handles evaluator-derived state: impacted skill versions, skills, probes, or evaluations retire matching probes and mark proposal-gate evaluations revoked with revocation metadata.
- Rollback revocation invalidation now also handles attribution-derived state: impacted skills, skill versions, evidence, memories, retrieved artifacts, broker policies, attribution events, or action-attribution checks mark matching attribution records revoked and report `attribution_records_invalidated` in revocation summaries.
- Rollback revocation invalidation now also handles governance-derived state: impacted active skill versions mark their owning skills `revoked`, revoke connected `skill_edges`, mark matching `evidence_maturity` rows revoked with previous maturity in the basis, suppress revoked skills from broker injection, and ignore revoked graph edges during graph expansion and duplicate/merge curation.
- Validation passed for the v14 substrate slice: `ruff check sidecar/autoskill`, `.venv/bin/pytest -q sidecar/autoskill/tests` with 108 passing tests, `npm test --prefix plugin/autoskill` with 7 passing tests, and a real compose Postgres migration smoke.
- Validation passed for the job trace propagation slice: `uv run pytest sidecar/autoskill/tests/test_jobs_api.py sidecar/autoskill/tests/test_scheduler_api.py -q` passed 6 tests; `uv run ruff check sidecar/autoskill/db/jobs.py sidecar/autoskill/db/scheduler.py sidecar/autoskill/api/app.py sidecar/autoskill/tests/test_jobs_api.py sidecar/autoskill/tests/test_scheduler_api.py` passed; real compose Postgres smoke proved migration backfill/defaults, duplicate enqueue trace preservation, generated/scheduled job trace IDs, and claim-time trace preservation; final gates `uv run ruff check sidecar`, `uv run pytest`, `uv run python -m compileall -q sidecar`, and `git diff --check` passed.
- Validation passed for the worker/retrieval/context governance slice: focused worker/broker/retrieval tests passed, `uv run ruff check sidecar` passed, and `uv run pytest -q` passed with 111 tests.
- Validation passed for the propose-only topology planner slice: `uv run pytest -q sidecar/autoskill/tests/test_topology_services.py` passed 6 tests, `uv run ruff check sidecar/autoskill/services/topology.py sidecar/autoskill/tests/test_topology_services.py` passed, and `uv run pytest -q` passed with 117 tests.
- Validation passed for embedding profile qualification slice: focused embedding-generation tests passed 7 tests and focused ruff checks passed.
- Validation passed for v16 model/embedding profile ownership slice: focused LLM/profile/embedding tests passed 19 tests, `uv run ruff check sidecar/autoskill` passed, `uv run pytest -q sidecar/autoskill/tests` passed with 131 tests, `uv run python -m compileall -q sidecar/autoskill` passed, `git diff --check` passed, `npm test --prefix plugin/autoskill` passed with 7 tests, and a compose Postgres smoke applied migrations twice, persisted profile-scoped same-model embeddings, and wrote an LLM invocation audit row.
- Validation passed for expanded revocation invalidation slice: focused worker/embedding tests passed 25 tests, `uv run ruff check sidecar` passed, and `uv run pytest -q` passed with 120 tests.
- Validation passed for the topology persistence slice: focused topology/admin tests passed 12 tests, `uv run ruff check sidecar` passed, `uv run pytest -q` passed with 123 tests, `uv run python -m compileall -q sidecar/autoskill` passed, `git diff --check` passed, and a fresh compose Postgres migration plus topology persistence smoke recorded one candidate compose operation with three planned trials.
- Validation passed for topology rollback invalidation wiring: focused worker/topology/admin tests passed 30 tests, focused ruff checks passed, and a fresh compose Postgres smoke invalidated one topology operation plus three planned trials (`operation_status='rolled_back'`, all trial statuses `retired`).
- Validation passed for evaluator trace propagation: focused evaluator/worker tests passed 24 tests, `uv run ruff check sidecar` passed, `uv run pytest` passed with 127 tests, `uv run python -m compileall -q sidecar` passed, `git diff --check` passed, and a fresh compose Postgres smoke persisted a closed `evaluator` trace span with safe count metadata.
- Validation passed for compiled context-loadability gates: focused writer/candidate tests passed 21 tests, focused ruff checks passed, and a fresh compose Postgres smoke persisted a candidate `skill_md` context artifact with `runtime_skill_body`, passed safety/equivalence/budget gates, and `269/1200` token usage.
- Validation passed for external-skill scanner wiring: focused external-skill tests covered root hashing, no raw path persistence, frontmatter extraction, and scanner-blocked quarantine; full `uv run pytest` passed with 127 tests.
- Validation passed for the combined v14 context/evaluator/external inventory smoke: fresh compose Postgres migration persisted a passed context gate, one traced proposal-gate evaluation, one closed evaluator trace span, and one visible external-skill inventory row without raw root path persistence.
- Validation passed for evaluator/probe revocation invalidation: focused evaluator/worker tests passed 25 tests, focused ruff checks passed, and a fresh compose Postgres smoke retired three planned probes plus revoked one proposal-gate evaluation from a skill-version revocation.
- Validation passed for attribution revocation invalidation: focused worker tests passed, focused ruff checks passed, and a fresh compose Postgres smoke invalidated two attribution records from a `skill_version` rollback traversal (`attribution_events.metadata.revoked=true`, `action_attribution_checks.verdict='revoked'`).
- Validation passed for governance revocation invalidation: focused worker/governance/broker tests passed 29 tests, focused ruff checks passed, and a compose Postgres smoke revoked one active skill version into one revoked skill, one revoked graph edge, and two revoked evidence-maturity rows, then proved fresh shadowing evidence reactivated the graph edge.
- Validation passed for profile qualification runs: focused profile/LLM/embedding/admin tests passed 14 tests, focused ruff checks passed, migrations applied idempotently in compose Postgres, and a real asyncpg smoke persisted one model-profile qualification run plus one embedding-profile qualification run while stamping both profile rows `qualified`.
- Validation passed for executor-profile broker compatibility routing: focused broker/compatibility tests passed 12 tests, focused ruff checks passed, migrations applied idempotently in compose Postgres, and a real broker smoke suppressed a blocked skill version for one executor profile while rendering the same skill when no executor profile was supplied.
- Validation passed for evaluator-derived executor compatibility: focused evaluator/broker/compatibility tests passed 19 tests and focused ruff checks passed, proving evaluator completion writes executor compatibility evidence that the broker can later consume.
- Validation passed for writer activation gating: focused worker/writer tests passed 38 tests and focused ruff checks passed, covering allowed activation, fail-closed blocked activation, and API blocking before active files or governance status changes are written.
- Validation passed for marginal-value token-ledger outcome updates: focused admin/context tests passed, focused ruff checks passed, and a real compose Postgres smoke updated one ledger outcome plus linked artifact `semantic_density_score`.
- Validation passed for semantic LLM trace spans: focused LLM/profile/admin tests passed 11 tests, `uv run ruff check sidecar`, `uv run pytest` with 138 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed; a real compose Postgres smoke persisted one LLM invocation joined to a closed `llm_call` span with safe metadata only, then compose was cleaned down.
- Validation passed for external-skill embedding sources: focused embedding/external-skill tests passed 14 tests, focused ruff checks passed, and a real compose Postgres smoke generated one `external_skill` embedding for visible inventory while excluding a quarantined external skill and keeping raw root paths out of embedded text.
- Validation passed for external-skill scan scheduling defaults: focused external-skill/worker tests passed, full sidecar tests passed with 141 tests, plugin tests passed with 7 tests, and a real compose Postgres smoke upserted an `external-skills.scan` schedule plus queued `external_skills.scan` job without persisting raw external root paths.
- Validation passed for external-skill collision recommendations: focused matching/opportunity/candidate tests passed, full sidecar tests passed with 142 tests, plugin tests passed with 7 tests, and a real compose Postgres smoke returned `external_collision_review` with high collision risk plus `review_changed_external_skill_before_candidate_creation` for a changed external skill.
- Validation passed for broker external shadow-risk metadata: focused broker tests passed, full sidecar tests passed with 142 tests, plugin tests passed with 7 tests, and a real compose Postgres smoke deferred a changed external skill while recording high external shadow risk and `review_changed_external_skill_before_runtime_hint` metadata.
- Validation passed for direct writer API trace spans: focused writer/admin tests passed 19 tests, full sidecar tests passed with 142 tests, plugin tests passed with 7 tests, and a real compose Postgres smoke recorded `writer.apply` and `writer.rollback` spans parented under a caller trace root.
- Validation passed for deterministic topology apply semantics: focused topology/admin tests passed 10 tests, full sidecar tests passed with 144 tests, plugin tests passed with 7 tests, and a real compose Postgres smoke blocked apply while trials were planned, then moved the operation to `applied` after all planned topology trials were marked passed.
- Validation passed for the installed OpenClaw runtime-plugin seam: the AutoSkill plugin now uses `openclaw.plugin.json` plus `package.json#openclaw.extensions` instead of a metadata-only `.codex-plugin` bundle, registers typed hooks through `api.on(...)`, and `openclaw --dev plugins inspect autoskill --json --runtime` reports `imported=true`, `hookCount=11`, and no diagnostics when dev-profile `allowConversationAccess` and `allowPromptInjection` are enabled.
- Validation passed for active skill root loading and archive invisibility: a dev-profile fixture under `/home/kklouzal/.openclaw/workspace-dev/skills/autoskill/v16-active-root-smoke/SKILL.md` appeared in `openclaw --dev skills list --json` as `source='openclaw-workspace'`, `eligible=true`, `modelVisible=true`, and `commandVisible=true`; a paired fixture under `/home/kklouzal/.openclaw/workspace-dev/.autoskill/archive/v16-archive-root-smoke/v1/SKILL.md` did not appear in normal or `--eligible` skill discovery, and both fixtures were removed after the smoke.
- Validation passed for runtime hook spool failure/concurrency behavior: plugin tests now prove sidecar outage spools the current event without blocking capture, concurrent failed captures append all events to the bounded spool, and a failed replay of older spooled records no longer re-spools or misreports an already-forwarded current event; `npm test --prefix plugin/autoskill` passed with 11 tests.
- Validation passed for mutation-worker revocation rollback tracing: `revocations.rollback` now starts a content-safe `rollback` operation span for queued rollback work, DB-backed observability tolerates missing caller parent spans without failing the worker, span closure records bounded scanned/completed/failed counts plus job/revocation-request refs, and focused/full worker tests prove trace/span propagation through rollback execution.
- Validation passed for topology apply downstream orchestration planning: accepted topology operations now persist a deterministic `downstream_orchestration` action plan in `trial_summary`, and API/store responses surface the planned actions for activation, supersession/routing, decomposition, and graph-edge materialization instead of marking topology operations applied with no follow-on mutation plan.
- Validation passed for mutation-worker writer apply tracing: queued `writer.apply` jobs now start content-safe child `writer` spans under the claimed job span for both success and error paths, recording policy/gate booleans, relative artifact path, manifest hash, activation-gate outcome, and job/transaction refs without compiled text.
- Validation passed for external-skill operator review actions: external skill reuse/import/ignore/quarantine decisions now persist through a control-authenticated review-action API and DB table, recording operator/rationale/metadata without storing raw roots or mutating external-owned files; approved ignore/quarantine decisions can update inventory status while reuse/import remain explicit operator decisions. Focused external-skill tests passed, full sidecar tests passed with 146 tests, plugin tests passed with 11 tests, and a compose Postgres smoke inserted an approved `reuse` action while leaving inventory status `visible`.
- Validation passed for richer external-skill collision scoring: external matches now expose deterministic `collision_score`, reason-weighted `collision_risk`, slug-family overlap signals, changed-since-review/scanner-blocked risk metadata, and a blocked recommendation for quarantined or scanner-blocked external skills.
- Validation passed for worker-executed topology downstream apply: accepted topology operations can now be consumed by a mutation-worker job that materializes SkillGraphIR edges, activates successor/composed output skills, archives superseded/decomposed subject skills, records applied downstream action results in `trial_summary`, and invalidates runtime-derived retrieval/context/embedding records where stores expose invalidation hooks. Focused topology/worker tests passed, and a real compose Postgres smoke moved an improve operation from planned downstream orchestration to applied state with the subject archived, successor active, and a `supersedes` skill edge materialized.
- Validation passed for variable-dimension profile-scoped embedding storage: `autoskill.embeddings.embedding` now uses unbounded pgvector storage with `embedding_dim`, search/recall filter by dimension before distance comparisons, the default 1536 path keeps an expression HNSW index, and a real compose Postgres smoke stored and searched an 8-dimensional qualified profile embedding.
- Validation passed for conservative broker vector fusion: retrieval now has a semantic pgvector query path that hydrates embedding hits into normal runtime candidates, the broker can merge lexical/vector/graph candidates before compatibility and selection gates, runtime API wiring only enables vector fusion for the local deterministic hash embedder, focused broker/retrieval tests passed, and a real compose Postgres smoke returned a vector-matched body-index skill candidate.
- Validation passed for recurring evidence aggregation: evidence derivation now emits immutable `recurring_evidence_cluster` items once at least three observed redacted events share a stable signature, records support provenance edges, stamps `evidence_maturity`, keeps cluster payloads redacted/support-ID based, and lets opportunity mining propose from a single higher-maturity cluster using its support count; focused evidence/opportunity/candidate tests passed and a real compose Postgres smoke persisted three observed items, one recurring cluster, three support edges, and a recurring maturity row.
- Validation passed for deterministic curation repair proposals: planned split/disambiguation/improvement curation actions now include a structured `repair_proposal` with proposal kind, subject skill, signal counts, objectives, trial categories, acceptance gates, and rollback scope; focused utility/worker tests passed and a real compose Postgres smoke produced a planned improvement with target/regression/no-skill/adversarial trials from repeated harmful attribution.
- Validation passed for drift false-positive lifecycle controls: `/v1/drift/false-positive` and the contract store can mark known-noisy environment contracts `false_positive`, store operator/rationale metadata, retire active drift probes, close open drift events, and make later drift checks count the contract as false-positive instead of reopening repair churn; focused contract tests passed and a real compose Postgres smoke verified violation -> false-positive -> skipped rerun behavior.
- Validation passed for live API contract probes: environment contracts can now declare `static:http-status:<expected>:<http-or-https-url>` checks, which run bounded HEAD requests without request bodies, classify exact status matches as valid, and create drift events for mismatches; focused contract tests passed and a real compose Postgres smoke checked a local HTTP endpoint with one valid and one violated API contract.
- Validation passed for duplicate-merge probe planning: duplicate merge curation actions now carry a structured `merge_probe_plan` with deterministic target, no-skill-control, regression, and collision trial hashes plus rollback gates before or alongside lower-utility duplicate archiving; focused utility tests passed, `uv run ruff check sidecar`, `uv run pytest` with 157 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed. No compose/Postgres smoke was needed because the slice only enriches deterministic curation-action metadata.
- Validation passed for conservative repair-proposal execution: mutation-pool `repair.execute` jobs now claim planned curation repair actions and open drift repair candidates, anchor each proposal in a `repair_proposal_execution` governance transaction with rollback-aware transaction items/provenance, and queue `writer.apply` only when the source proposal already carries an explicit policy-approved staged manifest; otherwise the job fail-closes to queued evaluator or drift recheck work and records execution metadata on the source. Focused worker/utility/admin tests and focused ruff checks passed.
- Validation passed for topology-specific broker trial scoring: compose/decompose proposals now include broker replay and broker canary trial plans with no-skill controls and routing thresholds, `topology.score_broker_trials` can persist pass/fail replay/canary results, and topology apply blocks missing or degraded broker gates before lifecycle/graph activation. Focused topology/worker tests and focused ruff checks passed.
- Validation passed for runtime action-attribution checks: the sidecar now persists `action_attribution_checks`, and the plugin emits a content-safe blocked-tool check when runtime tool-boundary enforcement blocks a high-risk call. Focused shadowing/API tests, plugin tests, and focused ruff checks passed.
- Validation passed for guarded external-skill import materialization: approved `import` review decisions can now become stage-only SkillKernel import candidates through `external_skills.materialize_import`, recording a completed review action without mutating external-owned roots. Focused external-skill/worker tests and focused ruff checks passed.
- Validation passed for guarded repair materialization: policy-approved repair proposals with a skill-version anchor can now generate a scanned staged repair `SKILL.md` manifest and queue `writer.apply`; proposals without explicit approval or sufficient anchors still fail closed to evaluator/drift recheck work. Focused worker tests and focused ruff checks passed.
- Validation passed for activation-grade repair materialization proof and
  explicit text endpoint selection: generated repair manifests now go through
  the deterministic SkillIR context compiler and require routing-equivalence plus
  regression evidence before staging, while OpenAI-compatible text model profiles
  can opt into `/responses` endpoint semantics with content-safe invocation
  audit. Focused LLM/compiler/worker tests passed, `uv run ruff check sidecar`,
  `uv run pytest` with 211 tests, `uv run python -m compileall -q sidecar`, and
  `git diff --check` passed; a rebuilt compose migration smoke applied the DDL,
  then a live asyncpg smoke persisted and read back `endpoint_kind=responses` for
  a qualified model profile.
- Validation passed for active/profile-qualified embedding generation controls: direct API and queued worker `embeddings.generate` paths now resolve explicit or active qualified embedding profiles, preserve profile IDs through embedding storage, and record content-safe `embedding_call` spans without embedding text/source bodies. Focused embedding/worker tests passed.
- Validation passed for production embedding validation and stored broker replay corpus controls: `/v1/profiles/embeddings/validate-production` can qualify the configured endpoint/profile and optionally exercise generation, while broker policy replay can consume persisted redacted replay episodes by tag instead of requiring caller-supplied episodes only. Focused profile/broker tests passed.
- Validation passed for content-safe worker progress metadata: `run_worker_once` now records persistent worker heartbeat progress for claimed jobs, lease renewals, success, and failure, including bounded payload controls and output keys/counts without raw evidence, skill text, or body content. Focused worker tests passed, and full `make test`, `make lint`, `make compile`, `make plugin-check`, and `git diff --check` passed with 181 tests.
- Validation passed for operator-configurable deployment fallbacks: the plugin now reads sidecar URL, runtime context broker, and runtime tool-boundary gates from `AUTOSKILL_*` environment fallbacks when explicit plugin config is absent; the sidecar can configure non-default OpenAI-compatible embedding dimensions through `AUTOSKILL_EMBEDDING_DIM`; and sidecar tests ignore repo-local `.env` by default to keep deployment settings from leaking into deterministic test fixtures. Full validation passed: `uv run ruff check sidecar`, `uv run pytest` with 183 tests, `uv run python -m compileall -q sidecar`, `git diff --check`, `npm test --prefix plugin/autoskill` with 17 tests, and `docker compose config`.
- Validation passed for operator deployment readiness reporting: control-authenticated `/v1/deployment/readiness` now reports fail-closed blockers for database/auth/redaction/runtime broker/writer-root/profile/broker replay readiness, `/v1/profiles/models` and `/v1/profiles/embeddings` expose bounded profile inventory, focused admin tests passed, full `uv run ruff check sidecar`, `uv run pytest` with 186 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed, and a real compose Postgres smoke proved the readiness route can pass with persisted executor, qualified text model, active embedding profile, active broker policy, and production-tagged broker replay evidence.
- Memory quarantine and control-flow integrity primitives are implemented: `autoskill.memory_quarantine` stores derived memory candidates as inactive `pending` rows until an explicit approve/reject/expire decision, `autoskill.control_flow_events` records append-only memory/skill/broker/tool/external-inventory influence decisions, and control-authenticated API surfaces expose record/list/decision paths without embedding or activating quarantined memory.
- Validation passed for memory governance surface wiring: focused admin/API tests passed with 9 tests and focused ruff checks passed for the new memory store, API wiring, and admin tests.
- Runtime broker memory-influence audit wiring is implemented: `/v1/runtime/context-hint` and `build_context_hint` accept bounded `memory_influence_ids`, record append-only memory-to-retrieval control-flow events through the memory governance store, and keep the rendered runtime hint sourced only from scanned skill body-index candidates rather than memory text.
- Validation passed for broker memory control-flow wiring: focused broker tests passed with 16 tests, `uv run ruff check sidecar`, `uv run pytest` with 188 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed, and a real compose Postgres smoke persisted one memory-to-retrieval control-flow event through the runtime context-hint API path without injecting proposed memory text.
- Runtime broker memory-influence trust gating is implemented: cited memory IDs are resolved through memory quarantine state before retrieval/cache lookup, only approved memory can influence the broker audit path, and pending/missing/governance-unavailable references fail closed without loading runtime hints.
- Validation passed for memory-influence trust gating: focused broker tests passed with 18 tests, `uv run ruff check sidecar`, `uv run pytest` with 190 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed, and a real compose Postgres smoke proved a pending quarantined memory produced `memory-influence-blocked`, wrote one blocked control-flow event, and made zero retrieval calls.
- Context compiler governance persistence is implemented for v16 context-budget gates: `context_compile_runs`, `context_budget_events`, and `semantic_compression_trials` now migrate idempotently, have asyncpg/null store primitives, and are exposed through control-authenticated context admin APIs without storing compiled text or prompt bodies.
- Validation passed for context compiler governance records: focused admin tests passed with 9 tests, `uv run ruff check sidecar`, `uv run pytest` with 190 tests, `uv run python -m compileall -q sidecar`, and a real compose Postgres smoke persisted one compile run, one token-budget event, and one semantic compression trial after a rebuilt migration image applied the new DDL.
- Deterministic context compiler gate execution is implemented: SkillIR can be compiled through a control-authenticated `/v1/context/compile-skillir` route that records the context artifact, compile run, token-budget decision, and semantic-compression trial with hashes/counts/statuses only, rejecting scanner, description-budget, token-budget, or semantic-loss failures without staging or activating runtime files.
- Validation passed for deterministic context compiler gate execution: focused compiler/admin tests passed with 20 tests, `uv run ruff check sidecar`, `uv run pytest` with 194 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed; a rebuilt compose sidecar/Postgres smoke called `/v1/context/compile-skillir` with control auth and verified exactly one context artifact, compile run, budget event, and semantic compression trial persisted for the smoke workspace, then compose was cleaned down without removing the persistent volume.
- Writer activation compile-proof gating is implemented: staged writer manifests can carry context compile-run/artifact/output-manifest proof, and direct/queued writer apply with `activation_gate_required=true` fails closed unless the real activation gate can match a passed `context_compile_run` and passed `skill_md` context artifact to the staged manifest text hash.
- Validation passed for writer activation compile-proof gating: focused worker writer-apply tests passed, focused audit/topology activation tests passed, `uv run ruff check sidecar`, `uv run pytest` with 195 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed; a real compose Postgres smoke blocked missing proof with `context-compile-proof-missing`, allowed matching passed compile/artifact proof, and blocked mismatched output-manifest proof with `context-compile-run-not-found`.
- Rendered context bundle scanning is implemented for broker-selected skill sets:
  `scan_text_bundle` checks co-loadable context across artifact boundaries,
  detects cross-skill secret-exfiltration chains, and broker rendering now fails
  closed on bundle scanner findings or conflict graph edges before a runtime hint
  is exposed.
- Validation passed for context bundle scanning: focused scanner/compiler/broker
  tests passed with 32 tests; full `uv run ruff check sidecar`,
  `uv run pytest` with 199 tests, `uv run python -m compileall -q sidecar`,
  and `git diff --check` passed.
- Broker bundle scan verdicts are now persisted as content-safe metadata on
  retrieval logs, context artifacts, and token ledgers, including bundle hash,
  selected IDs, scanner status, finding counts, and finding codes without
  storing raw bundle text.
- Repair materialization now records deterministic context-governance proof
  before staging generated repair manifests, embeds the compile-run/artifact
  proof into the writer manifest context gate, and fail-closes back to
  evaluator/drift recheck when proof cannot be produced.
- Memory-influenced mutation jobs now fail closed unless every cited memory ID is
  approved in memory quarantine governance; approved repair/writer mutations and
  blocked pending/missing memory references record content-safe
  `control_flow_events` with influence kind `mutation`.
- Focused validation passed for broker bundle metadata and mutation memory CFI:
  `uv run ruff check sidecar` and broker/worker tests passed with 51 tests.
- Prompt/body capture redaction is hardened across plugin and sidecar paths:
  conversation-like fields (`systemPrompt`, `messages[*].content`, `body`,
  `completion`, `response`, etc.) are content-stripped by default before event
  forwarding/storage, raw capture remains an explicit plugin opt-in that still
  secret-redacts, and the sidecar keeps storage-time redaction fail-closed.
- Dev-01 deployment readiness now passes end-to-end with the real local text and
  embedding endpoints, active executor/text/embedding profiles, an active broker
  policy, and a redacted production replay corpus. A readiness bug where
  unrelated historical failed jobs blocked deployment was fixed by scoping the
  job-queue check to the requested workspace.
- Operator disaster-recovery tooling is implemented: `scripts/autoskill_backup.py`
  exports a verifiable bundle containing a custom-format Postgres dump for the
  `autoskill` schema plus active/archive/staging filesystem roots, and
  `scripts/autoskill_restore.py` verifies the bundle by default and requires an
  explicit destructive confirmation before restoring DB or runtime files.
- Deterministic red-team scanner smoke is implemented:
  `scripts/autoskill_red_team.py` runs the blocking scanner cases for hidden
  Markdown, bidi/invisible controls, fetch-exec, policy override, credential
  exfiltration, destructive commands, sensitive-file harvest, cross-artifact
  exfiltration chains, and allowed secret-boundary language.
- Runtime context-hint requests now accept `intent` as a compatibility alias for
  `user_intent`, preventing an otherwise valid broker smoke or caller from
  silently dropping the intent and receiving an empty-intent `no_skill`
  decision.
- Dev-01 production plugin policy is now enabled outside the dev profile:
  OpenClaw `autoskill` plugin config and gateway env fallback both target
  `dev-01`, runtime context hints are enabled with a 150 ms fail-soft timeout and
  800 token cap, raw conversation capture remains disabled, and runtime
  tool-boundary blocking remains disabled.
- Live gateway capture/hint smoke passed after remediation: sidecar logs showed
  fresh `/v1/ingest/events` and `/v1/runtime/context-hint` 200s after gateway
  restart, fresh DB rows landed under `workspaces.external_key='dev-01'` instead
  of `auto`, local spool remained empty, and gateway logs no longer showed the
  synchronous `tool_result_persist` Promise warning.
- Final Dev-01 operational validation passed after the deployment fixes:
  `uv run pytest -q` passed with 206 tests; `uv run ruff check sidecar scripts`,
  `uv run python -m compileall -q sidecar scripts`, `npm run check --prefix
  plugin/autoskill`, `npm test --prefix plugin/autoskill`, `docker compose config
  --quiet`, and `git diff --check` passed; live readiness returned
  `ready=true`; stored production broker replay matched 3/3 with no degradation;
  production embedding validation qualified `llama-cpp-embeddings-nomic`; runtime
  context hint returned the active diagram-accessibility skill with bundle scan
  passed; `scripts/autoskill_red_team.py` passed 9/9; and backup plus restore
  dry-run verified `autoskill-backup-20260602T163525Z`.
- Broker replay corpus growth workflow is implemented:
  `scripts/autoskill_replay_corpus.py candidates` lists content-safe retrieval
  telemetry candidates by retrieval log ID, query hash, decision, and selected
  skill IDs/slugs without storing or reconstructing prompt text;
  `record --plan` creates replay episodes only from an operator-supplied
  redacted intent plan. The first telemetry-derived Dev-01 pass added
  `telemetry-unreadable-labels`,
  `telemetry-diagrams-unreadable-labels`, and
  `telemetry-repair-accessibility-annotations`, expanding the production replay
  corpus from 3 to 6 episodes; stored replay then matched 6/6 with no
  degradation.
- OpenClaw plugin inspection visibility is resolved operationally: hook-only
  runtime details require `openclaw plugins inspect autoskill --json --runtime`;
  that command now reports `imported=true`, `hookCount=11`, all 11 typed hooks,
  and no diagnostics for the live installed plugin.
- Direct OpenAI-compatible text profiles now persist an explicit
  `endpoint_kind` (`chat_completions` or `responses`) and the LLM client routes
  to `/v1/chat/completions` or `/v1/responses` accordingly, with content-safe
  invocation audit metadata.
- Activation-grade context compilation can now require content-safe routing,
  information-preservation, and regression probe evidence; missing or failed
  evidence causes `needs_probe_evidence` instead of a false equivalence pass.
- Policy-approved repair materialization no longer stages ad hoc Markdown.
  Repair proposals must become SkillIR, pass the normal context compiler, carry
  routing/regression proof summaries, and then stage compiler-rendered `SKILL.md`
  with the full typed runtime sections.

## Next Gates

1. Continue collecting sustained Dev-01 telemetry and add only distinct,
   operator-reviewed replay episodes from real usage, then run replay/canary
   tuning on the enlarged corpus.
2. Run `scripts/autoskill_backup.py` to an operator-approved backup location after the production roots contain activated SkillKernel-owned skills, then verify with `scripts/autoskill_restore.py --dry-run`.
3. Roll out live repair/import execution only after production replay/embedding validation remains green under sustained traffic.

## Known Risks

- Installed-plugin runtime loading is now smoke-tested under the dev profile and
  live Dev-01 capture is working. Use `openclaw plugins inspect autoskill --json
  --runtime` for hook-only runtime details; plain inspect reports static
  capability inventory and does not load hook registrations.
- Runtime tool boundary blocking is available but disabled by default
  until explicitly enabled by operator config.
- Spool replay is best-effort from capture hooks and covered by plugin-level
  outage, replay-failure, and concurrent-capture tests. The live Dev-01 smoke
  observed an empty spool while sidecar ingest was healthy; a forced sidecar
  outage drill can be run later if the operator wants destructive/noisy failure
  testing.
- The dev compose Postgres volume is persistent; rerun migrations are intended to be idempotent.
- Worker health now includes persistent heartbeat records, long-running handlers renew job leases, and single-job worker runs emit content-safe progress phases through heartbeat summaries. Future lengthy semantic handlers may still add deeper domain-specific counters when their internal phases mature.
- Evidence derivation now creates observed event evidence plus deterministic recurring evidence clusters; richer cross-session semantic aggregation and additional contrastive evidence mining beyond evaluator replay maturity remain pending.
- Memory quarantine/control-flow tables and operator APIs now exist, the runtime broker can record approved memory-influenced retrieval decisions without injecting memory text while blocking unapproved memory references before retrieval, and repair/writer mutation paths now gate and log approved or blocked memory influence.
- Embedding generation defaults to deterministic local hash embeddings unless an active qualified embedding profile is configured; storage now supports profile-scoped variable dimensions, with the default 1536-dimensional path retaining the indexed HNSW fast path.
- Runtime context broker is still conservative: vector fusion is available for local deterministic hash embeddings, policy artifact replay/canary primitives exist, and stored redacted replay episodes can drive policy replay; production replay quality still depends on deployment telemetry being populated.
- Deployment readiness is a deterministic sidecar/state preflight, not a
  substitute for sustained telemetry review; the one-shot live gateway
  capture/hint smoke has passed for the current Dev-01 deployment.
- Dev-01 readiness is green for the current canary, but the active/archive/staging
  runtime roots were absent during backup smoke because no SkillKernel-owned
  runtime skill has been activated into those roots yet. The backup bundle still
  contains the database dump and records missing roots explicitly; rerun the
  backup after the first live activation to prove filesystem restore coverage.
- Repair execution remains guarded and fail-closed: explicit staged manifests still pass through activation-gated `writer.apply`, and policy-approved repair materialization can generate staged manifests from bounded repair proposals only when a skill-version anchor exists and deterministic context-governance proof with routing-equivalence and regression evidence can be recorded for the staged runtime artifact.
- External-skill awareness now includes read-only root scanning plus inventory/retrieval/matching, scan scheduling defaults, embedding generation for external descriptions, richer collision risk scoring, explicit operator review-action recording, and operator-approved stage-only import materialization.
- v16 trace/profile/context APIs and schema exist; event/job/retrieval/evaluator/context-broker paths now propagate trace or context artifacts, LLM calls now have content-safe invocation audit rows, direct writer apply/rollback APIs record content-safe writer spans, mutation-worker writer apply plus revocation rollback record content-safe child spans, embedding generation records content-safe `embedding_call` spans, and worker heartbeat summaries expose content-safe claimed/renewed/succeeded/failed job progress. Longer semantic jobs may still add specialized counters as their multi-phase internals mature.
- SkillGraphIR now has planner/API/store persistence with transactions, planned trials, revocation invalidation for operation/trial state, deterministic apply state transitions after passed trials, broker replay/canary scoring gates for compose/decompose routing, stored downstream action plans, and mutation-worker lifecycle/graph/runtime invalidation execution after accepted topology operations.
- Candidate evaluator execution is deterministic and conservative; no-skill-control probes can now pass/fail with recorded or induced redacted intervention replay from explicit replay, attribution, canary, or broker outcome evidence.
- Candidate proposal persistence is transaction-anchored, and staged writer apply/rollback plus canary freeze now have sidecar control endpoints; mutation-worker apply exists but fails closed unless the queued job is explicitly policy-approved.
- Revocation traversal now previews impacted derived artifacts, staged writer artifacts have provenance edges, and critical canary failures can freeze skills plus queue rollback revocation requests. Mutation-worker rollback execution is implemented for archive-backed rollbacks and initial-create active-path deletion, invalidates body-index/embedding/context/retrieval/topology/evaluator/attribution/governance objects from traversal summaries, and freeze/critical-canary paths evict affected broker cache entries.
- Utility rollups are deterministic v1 scoring, not full marginal-value/intervention scoring yet; curation now handles archived promotion, explicit duplicate merge/archive, low-utility archive, active-bank budget overflow, evaluator blocking, duplicate merge probe planning, and planned split/improvement/disambiguation actions with structured repair proposals. Conservative repair execution now claims planned repairs, records governance/provenance, queues evaluator or policy-approved writer work, and can generate guarded staged repair manifests from policy-approved bounded proposals.
- Context-value/token ledgers exist and activation-grade compiler proof can now
  require routing/regression evidence, but utility rollups still need to consume
  context-value-per-token and token-waste outcomes before they fully drive
  archive, compose, decompose, tighten-description, or broker-abstain actions.
- Support artifacts remain represented in SkillIR and schema but are not yet
  full writer-manifest artifacts with independent scan/token/provenance records.
- Contract/drift checks are deterministic v1 path/command/env/package/schema/TCP/HTTP-status probes only; drift probe creation/retirement, localized repair metadata, live API status probes, operator false-positive suppression, and conservative repair execution/recheck queueing are implemented.
