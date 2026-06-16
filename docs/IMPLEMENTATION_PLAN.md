# SkillKernel Implementation Plan

2026-06-16 update: proposal-gate evaluation results now make executor-profile
scope explicit without breaking callers that do not have a profile. The
deterministic evaluator threads optional `executor_profile_id` through its
fixture, per-probe JSON, evaluator-level `evaluation_scope`, adapter
context/artifacts/trace, and autonomy assurance. The asyncpg evaluation runner
passes the row `executor_profile_id` into the gate and stores the same safe
string scope in the result before preserving existing compatibility recording.
This advances unified Sections 23.6 and 2.14. Validation passed with focused
executor/profile proposal-gate pytest coverage, touched-file Ruff, touched-file
compileall, diff hygiene, parent full `uv run pytest`, and conformance report.
Next: review/commit and CI confirmation.

2026-06-16 update: generated candidate probes now fail closed before they can
become proposal-gate evaluation material. Candidate persistence and fallback
`run_more_probes` expansion both honor `ProbePlan.ok`, skip generated probes
with blocking scanner findings (`error`/`critical`), and record content-safe
probe scan envelopes containing only probe hash, kind, status, reason codes,
and finding codes/severities. Clean generated probes still persist through the
existing inactive probe/evaluation flow. This advances unified Section 23.4
and Part V probe/evaluation assurance. Validation passed with focused probe
tests (`5 passed, 46 deselected`), touched-file Ruff, touched-file compileall,
diff hygiene, parent full `uv run pytest`, and conformance report. Next:
review/commit and CI confirmation.

2026-06-15 update: Observatory `verify_audit_chain` operator actions now check
the audit store before accepting non-dry-run verification requests. The handler
normalizes and clamps caller-provided verification limits, calls
`audit.verify_chain` for the requested workspace, rejects invalid chains with
`audit-chain-verification-failed`, and records a content-safe verification
envelope in the redacted receipt and action audit details without returning raw
audit rows. Focused Observatory API coverage proves success, failure, limit
clamping, policy metrics, and live-event outcomes. This advances unified
Section 28.3 audit hash-chain integrity and Observatory action truthfulness.
Validation passed with the focused Observatory API test slice, touched-file
Ruff, touched-file compileall, diff hygiene, parent full `uv run pytest`,
conformance report, and GitHub Actions run `27578009449` for commit
`f8b3927`. Next: continue the next narrow production-hardening slice under
TaskFlow/`codex-worker` authority.

2026-06-15 update: audit hash-chain persistence now serializes SQL appends per
workspace with a deterministic transaction-level Postgres advisory lock. The
lock is taken in `AsyncpgAuditStore.append_record` immediately after
`ensure_workspace` and before reading the previous audit hash, so the empty
chain case cannot admit concurrent first records with the same `previous_hash`.
Focused fake-asyncpg coverage proves the lock/select/insert ordering without a
live Postgres dependency, while leaving `NullAuditStore` and public audit APIs
unchanged. This advances unified Section 28.3 audit hash-chain integrity.
Validation passed with the focused audit pytest slice, touched-file Ruff,
touched-file compileall, and diff hygiene. Next: parent broader sidecar/full
validation.

2026-06-15 update: topology composition admission now carries the Section
1.5.1 effect-signature contract into composed SkillGraphIR proposals. A narrow
deterministic checker in `services/topology.py` rejects composed outputs that
hide explicit component state deltas, side effects, unsafe conditions, or
termination semantics, while preserving existing valid default-empty contracts
and not treating unknown idempotency as a blocker. Focused topology tests prove
hidden disclosure blockers and the passing disclosed-output case. Next:
touched-file Ruff/compileall, diff hygiene, then parent broader sidecar/full
validation.

2026-06-15 update: Observatory readiness now includes a content-safe
`live_stream_health` field on `/admin/api/v1/health/ready`. The object reports
availability, health, reason codes, snapshot/outbox cursor summaries, and an
explicit no-payload content policy from existing snapshot, live-envelope,
issue, and live-event outbox sequence signals. Outbox read failures now degrade
with `live-event-outbox-unavailable`, while sequence-gap self-health reason
codes surface as degraded stream health without exposing raw event payloads,
secrets, prompts, skill text, or introducing any control-plane authority.
Focused readiness tests, the broader Observatory readiness slice, touched-file
Ruff, touched-file compileall, and diff hygiene passed. Next: parent full
validation.

2026-06-15 update: Observatory admin health now exposes a content-safe
deployment fingerprint for the independently deployed web container. The
existing settings/env primitive for `SKILLKERNEL_BUILD_SHA` and
`SKILLKERNEL_IMAGE_SOURCE` is shared through a small API helper and reported
with service `skillkernel-observatory` on `/admin/api/v1/health/live` and
`/admin/api/v1/health/ready`; `/healthz` remains the compatible plain-text
liveness probe. This advances the unified Observatory health/readiness and
inter-container compatibility assurance requirements by making Observatory's
runtime identity visible without exposing secrets, raw/private content, or
adding a second control plane. Focused validation passed for the new
Observatory fingerprint coverage, touched-file Ruff, touched-file compileall,
and diff hygiene. Next: parent review, full suite, and real
container/deployment confirmation.

2026-06-15 update: runtime deployment fingerprint reporting now extends the
OCI image-label packaging primitive into Core's compatibility and readiness
surfaces. Settings accept `SKILLKERNEL_BUILD_SHA` and
`SKILLKERNEL_IMAGE_SOURCE` with `local` defaults, compose passes those values
through the shared runtime env for rebuilt Core/shared and Observatory
containers, and Core handshake responses now include a content-safe
`deployment_fingerprint` on `/v1/version`, `/v1/capabilities`,
`/v1/read-model-contract`, and `/v1/health/ready`. The object reports service,
build SHA/revision, image source, source, and generation time without exposing
secrets or raw content. This advances the Container health/readiness and
Inter-container API compatibility contracts by making runtime state visible
instead of assuming matching tags. Validation passed with focused compatibility
tests (`7 passed`), `uv run ruff check sidecar`, full `uv run pytest` (`541
passed`), `uv run python -m compileall -q sidecar`, and `git diff --check`.
Next: parent review/commit, then CI/deploy confirmation.

2026-06-15 update: Core and Observatory container build revision traceability
is now part of the deterministic packaging contract. The container Dockerfiles
and root release aliases accept `SKILLKERNEL_BUILD_SHA` and
`SKILLKERNEL_IMAGE_SOURCE` with local-safe defaults and stamp
`org.opencontainers.image.revision` plus `org.opencontainers.image.source`
labels on the runtime images. `docker-compose.yml` threads those args through
the shared Core build anchor and Observatory build, and
`.github/workflows/publish-ghcr.yml` passes `${{ github.sha }}` plus the
repository URL to both local CI image builds and GHCR publish builds. The
conformance packaging check now asserts the Dockerfile, compose, and workflow
contract. This advances first-class repository packaging and deployable image
traceability without runtime behavior changes. Validation passed with the
focused conformance test, compose config, touched-script Ruff, touched-script
compileall, parent `uv run ruff check sidecar scripts/autoskill_conformance.py`,
parent full `uv run pytest` (`540 passed`), parent `uv run python -m
compileall -q sidecar scripts/autoskill_conformance.py`, and diff hygiene.
Next: parent review/commit, then verify pushed GHCR Core and Observatory images
expose the revision label.

2026-06-15 follow-up: the SQL activation gate fixture now uses per-case
compiled text hashes for the missing, below-threshold, and passing context
proof rows, matching the live `autoskill.context_artifacts` uniqueness
contract while keeping the semantic-equivalence and context-value assertions
unchanged. This removes the unrelated fixture collision found by parent full
validation. Focused activation gate validation, packaging conformance, compose
config, touched-test Ruff/compileall, parent full `uv run pytest` (`540
passed`), and diff hygiene passed.

2026-06-14 update: bootstrap migration idempotency is now a shared primitive
for cron/operator SQL entry points. `scripts/migrate.py` executes
`0001_autoskill_schema.sql` statement by statement, preserving quoted strings,
comments, and PostgreSQL dollar blocks while reporting the failing statement
preview. The activation context, deployment readiness, revocation traversal,
topology admission, and Observatory live SQL smokes now reuse that runner
instead of sending the whole migration as one asyncpg query. The migration
schema patch keeps the `schema_migrations` marker as the final success marker,
deduplicates runtime-artifact and historical-import compatibility backfills
before `ON CONFLICT` updates, guards vector conversion, and recreates
historical import sync triggers after backfill. This closes the Dev-01 reapply
failure mode where an already-migrated database could fail with duplicate
`ON CONFLICT` rows or single-query migration execution. Validation passed with
focused migration, readiness, jobs, and operator-script tests (`26 passed`),
touched-script Ruff, compileall for the migration runner/tests,
`git diff --check`, direct `scripts/migrate.py` reapply against the configured
Dev-01 database, and the deployment readiness smoke with `ok=true`.

2026-06-14 update: activation context smoke summaries now carry per-case
effective threshold echoes. Each missing, below-threshold, and passing case
reports the content-safe `effective_min_context_value_per_token` and
`effective_min_semantic_equivalence_score` used for that readiness check, and
`_assert_smoke` rejects summaries where any case diverges from the top-level
run policy. Focused tests prove non-default `0.05` context-value and `0.95`
semantic-equivalence thresholds are echoed and enforced without raw skill text,
evidence, prompt output, runtime skill writes, plugin activation, autonomous
apply, or live OpenClaw mutation. This advances unified Sections 11.12-11.15
and Part V Section 4 threshold-governance assurance. Validation passed with
focused pytest (`20 passed`), touched-file Ruff, touched-file compileall,
`uv run ruff check sidecar`, full `uv run pytest` (`533 passed, 2 skipped`),
`uv run python -m compileall -q sidecar`, `git diff --check`, and the Dev-01
SQL smoke using `--skip-migrate --min-context-value-per-token 0.05
--min-semantic-equivalence-score 0.95`. Next: confirm the pushed GitHub
Actions/GHCR result for this commit, then redeploy only `skillkernel-core` and
`skillkernel-observatory` after green CI.

2026-06-14 update: activation context smoke CI and live-schema cleanup
compatibility landed in recent commits.
`.github/workflows/publish-ghcr.yml` runs
`scripts/autoskill_activation_context_smoke.py` with
`--min-context-value-per-token 0.05` and explicit
`--min-semantic-equivalence-score 0.9`, proving the SQL missing,
below-threshold, and passing cases under a non-default policy instead of only
the default zero threshold. The smoke cleanup now discovers existing
`autoskill` tables, fails closed when core smoke tables are missing, and
deletes optional/later cleanup tables such as `runtime_artifacts`,
`skill_components`, `skill_ir_revisions`, `skill_state_records`, and
`memory_contracts` only when they exist. This addresses parent Dev-01 evidence
where a full migration reapply failed on an already-migrated DB with
`ON CONFLICT DO UPDATE command cannot affect row a second time`, then the safer
`--skip-migrate --min-context-value-per-token 0.05` rerun hit `relation
"autoskill.runtime_artifacts" does not exist` during cleanup. Validation passed
with the focused activation-context tests (`17 passed`), touched-file Ruff,
touched-file compileall, workflow YAML parse, diff hygiene, and the
parent-style Dev-01 `set -a; . ./.env; set +a; uv run python
scripts/autoskill_activation_context_smoke.py --skip-migrate
--min-context-value-per-token 0.05` smoke. This advances unified Sections 1.4
and 11.12-11.15 plus Part V Section 4 threshold-governance assurance. Next:
parent review/commit and confirm the CI `activation-context-smoke` job passes.

2026-06-14 update: activation context smoke threshold fixtures are now
policy-relative. `scripts/autoskill_activation_context_smoke.py` derives the
missing, below-threshold, and passing context-value cases from the accepted
`--min-context-value-per-token` before seeding SQL rows, preserving the default
fixture values where practical while letting positive caller thresholds retain
one below-policy case and one at/above-policy passing case. The summary
assertions remain fail-closed and prove the below and passing cases relative to
policy. Focused tests cover a positive `0.05` threshold. This advances unified
Sections 11.12-11.15 and Part V Section 4 threshold-governance assurance.
Validation passed with the focused activation context smoke tests (`14
passed`). Next: parent SQL smoke with a positive context-value threshold.

2026-06-14 update: activation context smoke caller-provided threshold policy
now fails closed before any Postgres mutation. `scripts/autoskill_activation_context_smoke.py`
validates threshold CLI inputs during argument parsing, rejecting non-finite
values, semantic-equivalence thresholds outside `[0.0, 1.0]`, and negative
context-value-per-token thresholds while preserving the default valid policy.
Focused tests cover invalid threshold rejection without calling `_run` or
requiring Postgres. This advances unified Sections 11.12-11.15 and Part V
Section 4 threshold-governance assurance. Validation passed with the focused
activation context smoke tests (`12 passed`), touched-file Ruff, touched-file
compileall, and `git diff --check`. Next: parent/CI SQL smoke with valid
policy thresholds.

2026-06-14 update: activation context marginal-value readiness now has a
standalone SQL-backed smoke primitive. `scripts/autoskill_activation_context_smoke.py`
uses `--database-url` / `AUTOSKILL_DATABASE_URL`, applies
`0001_autoskill_schema.sql` unless skipped, seeds an isolated workspace with
passed activation prerequisites, `skill_md` context artifacts, passed compile
runs, semantic-equivalence proof, and three marginal-value cases, then calls
`AsyncpgActivationGateStore.check_activation_readiness` to prove missing,
below-threshold, and passing context value per token behavior. The summary
assertions preserve content-safe output and no runtime skill writes, plugin
activation, autonomous apply, deployment, or live OpenClaw mutation.
`.github/workflows/publish-ghcr.yml` now runs the smoke as an independent
pgvector-backed job after deterministic tests and gates local image builds on
it. This advances unified Sections 1.4 and 11.12-11.15. Validation passed with
the focused smoke summary tests (`4 passed`), touched-file Ruff, touched-file
compileall, and workflow YAML parsing. Next: parent/CI run the real SQL smoke
against disposable or Dev-01 Postgres and confirm the emitted JSON.

2026-06-13 update: activation readiness now exposes and optionally enforces
compiled context marginal value per token. `ActivationGateStore` accepts
`require_context_value` and `min_context_value_per_token` without changing
existing default behavior; when activation-grade context compile proof is
required and this policy is enabled, SQL readiness reads
`context_artifacts.metadata.last_context_value_per_token` and emits
content-safe blockers for missing or below-threshold marginal value. The null
gate fails closed under the same required policy because it has no real context
artifact metadata. Focused tests cover blocker behavior, null-store
fail-closed behavior, and SQL-backed missing/below-threshold/passing fixture
paths when a Postgres autoskill schema is available. This advances unified
Sections 11.12-11.15. Validation passed with `uv run pytest
sidecar/autoskill/tests/test_activation_gate.py -q` (`15 passed, 2 skipped`;
SQL-backed smoke cases skipped because local Postgres was unavailable), touched
file Ruff, touched file compileall, and `git diff --check`.

2026-06-13 update: context compiler support-bundle scanning now fails closed
before context-visible support artifacts can pass governance. The compiler
builds the deterministic co-loadable bundle from rendered `SKILL.md` plus
`agent_may_read` and `broker_excerpt_only` support excerpts, runs
`scan_text_bundle`, merges bundle findings into compiled scanner findings, and
persists content-safe scanner codes through context artifact metadata, compile
manifest hash inputs, compile run metadata, budget rejection, and calibration
signals. Focused regression tests prove a cross-artifact secret/upload chain in
support declarations is rejected while a bounded non-sensitive report case
passes. This advances unified Sections 11.10, 11.12-11.17, 24.1, and 24.6.
Validation passed with `uv run pytest
sidecar/autoskill/tests/test_skillir_compiler_scanner.py` (`26 passed`), `uv
run ruff check sidecar/autoskill/services/compiler.py
sidecar/autoskill/tests/test_skillir_compiler_scanner.py`, `uv run python -m
compileall -q sidecar/autoskill/services/compiler.py
sidecar/autoskill/tests/test_skillir_compiler_scanner.py`, and `git diff
--check`. Next: parent broader sidecar gates.

2026-06-13 update: activation semantic-equivalence readiness now has
asyncpg-backed coverage for the real SQL store path. The activation gate test
seeds a throwaway workspace, passed scanner/evaluator/proposal-gate state, a
passed `skill_md` context artifact, and three `context_compile_runs` rows that
exercise missing, below-threshold, and passing
`semantic_equivalence_score` values through `AsyncpgActivationGateStore`.
Cleanup removes the seeded workspace/version/artifact/run rows and derived
trigger records, including default memory-contract rows inserted for the
throwaway workspace. The SQL-backed test also exposed and fixed the asyncpg
activation query's missing `latest_ev.result` lateral select, allowing the
existing autonomy fallback fields to be read from the real store path.
Validation passed with focused activation pytest against disposable Postgres
(`12 passed`), `uv run ruff check sidecar`, `uv run pytest` (`507 passed, 1
skipped`), `uv run python -m compileall -q sidecar`, and `git diff --check`.

2026-06-13 update: activation readiness is now policy-aware for
semantic-equivalence context regression gates. `ActivationReadiness` includes
the context compile run semantic-equivalence score, the SQL activation gate
selects `context_compile_runs.semantic_equivalence_score`, and
`_activation_blockers` fails closed with
`context-semantic-equivalence-missing` or
`context-semantic-equivalence-below-threshold` when activation-grade context
proof is required and configured policy is not met. Filesystem and API writer
apply paths pass the existing `require_semantic_equivalence` and
`min_semantic_equivalence_score` settings into the activation gate, preserving
content-safe blocker reporting and adding no runtime apply authority. This
advances unified Sections 11.12-11.15. Validation covered focused activation
gate regressions, affected worker apply expectations, touched-file Ruff,
touched-file compileall, and `git diff --check`. Follow-up SQL-backed
activation readiness coverage and full parent validation are recorded in the
2026-06-13 update above.

2026-06-13 update: activation readiness now treats null/in-memory gate paths as
fail-closed when deterministic context compile proof is required. The
`NullActivationGateStore` mirrors the SQL activation gate's proof-presence
semantics: missing `context_compile_run_id`, `context_artifact_id`, compiled
text hash, or context output manifest hash returns
`context-compile-proof-missing` and `allowed=false`; complete proof preserves
the supplied run/artifact IDs and passed statuses. Focused regression tests
cover proofless blocking and complete-proof readiness. Validation passed with
`uv run pytest sidecar/autoskill/tests/test_activation_gate.py -q`, `uv run
ruff check sidecar/autoskill/db/activation.py
sidecar/autoskill/tests/test_activation_gate.py`, `uv run python -m compileall
-q sidecar/autoskill/db/activation.py
sidecar/autoskill/tests/test_activation_gate.py`, and `git diff --check`.

2026-06-13 update: dirty-state reconciliation preserves the Dev-01 operational
compose/Postgres and model-fixture alignment before new implementation work.
`docker-compose.yml` defaults now target the Dev-01 Postgres/pgvector endpoint
at `172.16.8.20:5432` and no longer attach SkillKernel services to the
unused `dev01-postgres` external network, while keeping Core, Observatory,
workers, and the data plane as separate service boundaries. The plugin hook
smoke test and sidecar redaction test now reference the live
`llama-cpp-compaction` model artifact
`gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf`, keeping redaction fixtures aligned with
the deployed local model route. The k8s/Postgres backup files remain untracked
operator backups and are not part of the commit. No live OpenClaw gateway
install, runtime skill write, autonomous apply, container redeploy, or runtime
configuration mutation is part of this reconciliation.

2026-06-12 update: the SQL-backed deployment readiness smoke now proves the
executor-profile compatibility contract exposed by `/v1/deployment/readiness`
instead of summarizing `active_executor_profile` as `{status,count}`. Its
content-safe summary carries profile keys, compatible and blocked profile
records, tool/binary/API-contract counts and keys, permission keys, and reason
codes, while `_assert_smoke` rejects count-only or incomplete executor detail.
This closes the immediate smoke-reporting gate for executor-profile-aware
readiness without raw evidence exposure, environment dumps, runtime skill
writes, plugin activation, autonomous apply, or production OpenClaw mutation.
Validation passed with the focused smoke tests, touched-file Ruff,
touched-file compileall, and `git diff --check`. Next: run the real SQL smoke
against Dev-01 readiness/Postgres and confirm the emitted JSON includes the
richer executor-profile contract.

2026-06-12 update: deployment readiness now treats executor profiles as
operator-visible compatibility contracts, not count-only presence. The
`active_executor_profile` check fails closed unless an active profile includes
agent backend, model family, sandbox, OS name, tool surface, binary surface,
and API-contract keys; readiness detail returns content-safe profile keys,
compatibility fields, tool/binary/API-contract summaries, permission keys, and
reason codes for blocked profiles without exposing secrets, prompts, evidence,
or broad environment dumps. This advances executor-profile-aware evaluation and
routing contracts, deployment/readiness fake-health prevention, and the
OpenClaw assurance seam while preserving no runtime skill writes, plugin
activation, autonomous apply, or production OpenClaw mutation. Validation
covered focused admin readiness tests and the deployment-readiness smoke
summary test, touched-file Ruff, touched-file compileall, sidecar Ruff, full
pytest, sidecar compileall, and `git diff --check`. Next: verify the SQL smoke
reports the richer profile detail against Dev-01 readiness.

2026-06-12 update: deployment readiness now treats model and embedding profile
qualification as a hard fail-closed gate. `/v1/deployment/readiness` accepts
text profiles only when they carry an autonomous-capable
`qualified_autonomous` qualification verdict/status and accepts embedding
profiles only when they carry a `qualified` verdict/status. Active profiles
with missing, failed, expired, or propose-only qualification no longer satisfy
Core readiness; the check returns only content-safe profile keys, status/verdict
values, checklist keys, and reason codes for blocked profiles. The SQL
deployment-readiness smoke seed was aligned to the autonomous text verdict.
Validation covered focused readiness/profile admin tests, touched-file Ruff,
touched-file compileall, related deployment-readiness smoke tests, and `git
diff --check`.

2026-06-12 update: the SQL-backed Observatory live-stream smoke is now a
repeatable CI/operator gate. `scripts/autoskill_observatory_live_smoke.py`
continues to target a caller-provided Postgres/pgvector DSN, apply the
bootstrap migration by default, seed isolated `observatory-live-smoke-*`
outbox events, and exercise the real `/admin/live-sse` route over the asyncpg
Observatory admin store. Its emitted JSON now includes explicit safe-summary
flags while proving the Section 12.3 live stream envelope and Section 12.6
truth/stability behavior: the initial snapshot carries a cursor that fences
pre-existing outbox rows, and later persisted deltas still arrive with stable
event type, `seq`, `cursor_seq`, and UI-safe payload. The gate also reinforces
Section 13 read-model/outbox consumption and Part V Section 7 Observatory
assurance without raw-vault exposure, runtime skill writes, plugin activation,
autonomous apply, or live OpenClaw mutation. `.github/workflows/publish-ghcr.yml`
now runs `observatory-live-smoke` after deterministic tests with disposable
`pgvector/pgvector:pg17`, and local image-build validation depends on it
alongside the revocation, topology, and deployment readiness SQL smokes.
Validation for this slice: focused unit test, workflow YAML parse, touched-file
Ruff, touched-file compileall, and `git diff --check`. Next: confirm the
pushed GitHub Actions run.

2026-06-12 update: SQL-backed deployment readiness now has a repeatable smoke
primitive and CI gate. `scripts/autoskill_deployment_readiness_smoke.py`
targets a caller-provided `--database-url`, applies the bootstrap migration by
default unless `--skip-migrations` is supplied, seeds only content-safe minimal
readiness records in an isolated workspace, and exercises the real
`/v1/deployment/readiness` route endpoint over asyncpg-backed job/profile/broker
stores. The smoke proves migrated Postgres/pgvector schema visibility,
read-model contract compatibility, scheduler heartbeat visibility, active
executor/text-model/embedding/broker-policy records, telemetry-linked
operator-reviewed replay evidence, and final ready state while explicitly
reporting `raw_evidence_returned=false`, `runtime_skill_writes=false`,
`activation_authority=false`, and `live_openclaw_mutation=false`.
`.github/workflows/publish-ghcr.yml` now runs this as a separate
`deployment-readiness-smoke` job after deterministic tests using a disposable
`pgvector/pgvector:pg17` service, and local image-build validation depends on
it alongside the existing revocation and topology SQL smoke gates. This advances
the Container health/readiness contract, Inter-container API compatibility
contract, and Part V diagnostic/evidence assurance without production runtime
behavior, plugin activation, runtime skill writes, autonomous apply, raw
evidence exposure, or live OpenClaw mutation. Validation passed with the focused
unit test, touched-file Ruff, touched-file compileall, workflow YAML parsing,
and a disposable local pgvector smoke on `127.0.0.1:57031`. Next: confirm the
pushed GitHub Actions run.

2026-06-12 update: the SQL-backed topology admission smoke is now a repeatable
CI/operator gate in `.github/workflows/publish-ghcr.yml`. The new
`topology-admission-smoke` job runs after deterministic Python tests, provisions
a disposable `pgvector/pgvector:pg17` Postgres service, waits for asyncpg
connectivity, and executes `scripts/autoskill_topology_admission_smoke.py`
through `AUTOSKILL_DATABASE_URL`. Local image-build validation now depends on
both SQL-backed smoke gates (`revocation-traversal-smoke` and
`topology-admission-smoke`) alongside plugin and Observatory checks, keeping
GHCR publication downstream of deterministic topology admission assurance for
Sections 13.6-13.8 and Part V evidence-sufficiency/autonomy requirements. The
gate preserves content-safe summaries only and adds no production runtime
behavior, plugin activation, runtime skill writes, autonomous apply, raw
evidence exposure, or live OpenClaw mutation. Validation passed with
`yq '.' .github/workflows/publish-ghcr.yml >/dev/null`,
`uv run ruff check sidecar scripts/autoskill_topology_admission_smoke.py`,
`uv run python -m compileall -q sidecar
scripts/autoskill_topology_admission_smoke.py`, and a disposable local
`pgvector/pgvector:pg17` topology smoke on `127.0.0.1:56999`. Next: confirm
the pushed GitHub Actions run.

2026-06-12 update: the revocation traversal smoke is now a CI gate in
`.github/workflows/publish-ghcr.yml`. The new `revocation-traversal-smoke` job
runs after deterministic Python tests, provisions a disposable
`pgvector/pgvector:pg17` Postgres service, waits for asyncpg connectivity, and
executes `scripts/autoskill_revocation_traversal_smoke.py` against
`AUTOSKILL_DATABASE_URL`. Local image-build validation now depends on the smoke
alongside plugin and Observatory checks, keeping GHCR publication downstream of
the SQL-backed Section 1.2 / 2.26 rollback-complete derived-data revocation
proof. The gate preserves content-safe summaries only and adds no production
runtime behavior, plugin activation, runtime skill writes, or live OpenClaw
mutation. Validation: workflow YAML parsing, `uv run ruff check sidecar`, `uv
run pytest`, `uv run python -m compileall -q sidecar`, `git diff --check`, and
a disposable local `pgvector/pgvector:pg17` revocation smoke passed. Next:
confirm the pushed GitHub Actions run.

2026-06-12 update: SQL-backed rollback-complete derived-data revocation now has
a bounded smoke primitive at `scripts/autoskill_revocation_traversal_smoke.py`.
The smoke uses the real asyncpg governance store against Postgres to create an
isolated workspace, seed content-safe evidence/memory source roots, stage a
compile evolution transaction, record writer transaction items whose `item_id`
values are affected `skill_version` UUIDs, connect source roots via
`source_for_writer_item` provenance edges, preview evidence-root revocation
traversal, queue an operator revocation request, and expand reached
`transaction_item` nodes into `skill_version` impacts. This advances unified
Sections 1.2 and 2.26 by proving the SQL provenance graph can discover derived
writer artifacts without exposing raw evidence, writing runtime skills,
granting activation authority, or mutating live OpenClaw state. Validation:
`uv run python scripts/autoskill_revocation_traversal_smoke.py --database-url
postgresql://autoskill:autoskill-dev@127.0.0.1:55433/autoskill` passed against a
disposable `pgvector/pgvector:pg17` container, and focused Ruff/compileall
passed for the touched script. The follow-up CI gate is now recorded above.

2026-06-11 update: Observatory readiness now reports Core reachability as a
known/not-assumed readiness primitive. `/admin/api/v1/health/ready` and the
shared Observatory snapshot include a content-safe `core_reachability` object
derived from the existing worker-health scheduler heartbeat signal, including
known/reachable state, source, scheduler worker count, ready worker ids, last
Core heartbeat, and disabled-action reasons. Missing or unhealthy scheduler
heartbeat state produces `core_unreachable` in data quality and the issue board
and makes the ready response fail closed without adding outbound Core probes,
guarded action execution, migrations, runtime skill writes, plugin installs, or
new Observatory control-plane authority. This advances the Container
health/readiness contract item requiring Core reachability to be known, not
assumed. Validation: focused readiness tests passed (`3 passed, 66 deselected`)
with `uv run pytest sidecar/autoskill/tests/test_observatory_api.py -q -k
'ready or core'`, touched-file Ruff passed with `uv run ruff check
sidecar/autoskill/api/app.py sidecar/autoskill/services/observatory.py
sidecar/autoskill/tests/test_observatory_api.py`, `uv run python -m compileall
-q sidecar` passed, and `git diff --check` passed. Next: parent-side full gates
and real Dev-01 container verification after dirty-work reconciliation.

2026-06-11 update: deployment readiness now includes an explicit
`read_model_contract_compatible` check. The check derives a content-safe
compatibility state from the live storage/schema probe and the read-model
contract expected for `0001_autoskill_schema`, reporting required Observatory
catalog tables and failing closed with `storage_plane_uninitialized`,
`migration_required`, `read_model_contract_missing`, or
`read_model_contract_incompatible` when the schema/read-model state cannot be
trusted. `/v1/read-model-contract` also advertises the schema migration,
expected contract version, required catalogs, and compatibility reason codes.
This advances the Container health/readiness and Inter-container API
compatibility contracts without adding schema writes, Observatory repair
authority, runtime skill mutation, or activation authority. Validation: focused
readiness/compatibility tests passed (`16 passed, 15 deselected`) with `uv run
pytest sidecar/autoskill/tests/test_admin_surfaces.py
sidecar/autoskill/tests/test_compatibility.py -q -k 'readiness or ready or
compatibility or read_model_contract'`, and touched-file Ruff passed. Required
gates passed with `uv run ruff check sidecar`, `uv run pytest` (`484 passed`),
`uv run python -m compileall -q sidecar`, and `git diff --check`. Next: verify
the reason-code surface against the real Dev-01 Postgres/pgvector deployment
once the unrelated storage/model ops dirty work is reconciled.

2026-06-11 update: deployment readiness now requires observable storage-plane
schema readiness before reporting ready. The new `storage_plane_schema_ready`
check lives in the shared deployment readiness substrate and uses the job-store
storage connection to verify live Postgres reachability, installed pgvector
extension visibility, the `autoskill` schema, required Core/Observatory tables,
and a persisted `autoskill.schema_migrations` marker seeded with
`0001_autoskill_schema`. Missing or mismatched markers fail closed instead of
inferring readiness from table presence. Null and in-memory stores fail closed
with content-safe unavailable details unless tests explicitly provide a ready
storage probe. Because `/v1/health/ready` consumes deployment readiness, Core
readiness now also depends on observable storage/schema/pgvector state.
Validation: touched-file Ruff passed with `uv run ruff check
sidecar/autoskill/db/jobs.py sidecar/autoskill/api/app.py
sidecar/autoskill/services/observatory.py
sidecar/autoskill/tests/test_admin_surfaces.py`, `uv run python -m compileall
-q sidecar` passed, a direct import check confirmed the marker fields, and
parent-side reconciliation validation passed with `uv run pytest` (`483
passed`) plus `git diff --check`. Disposable pgvector smoke validation passed by
applying `scripts/migrate.py` against a fresh `pgvector/pgvector:pg17` container
and confirming the readiness probe returned ready with no missing tables. Next:
deploy after green CI and verify the same readiness check against the Dev-01
SkillKernel application containers.

2026-06-11 update: deployment readiness now requires a visible scheduler worker
heartbeat before reporting ready. The new `scheduler_worker_heartbeat` check
uses the existing job-store heartbeat listing, accepts only recent scheduler
workers with positive concurrency and `running`/`idle` status, and reports only
content-safe worker id, pool, status, concurrency, and last-seen metadata.
Because Core readiness passes through deployment readiness, `/v1/health/ready`
now fails closed when the scheduler lease/worker signal is absent or unhealthy.
Validation: focused readiness tests passed (`8 passed, 20 deselected`) with
`uv run pytest sidecar/autoskill/tests/test_admin_surfaces.py
sidecar/autoskill/tests/test_compatibility.py -q -k 'readiness or ready'`, and
touched-file Ruff passed with `uv run ruff check sidecar/autoskill/api/app.py
sidecar/autoskill/tests/test_admin_surfaces.py`. No migration was required; the
slice reuses existing worker-heartbeat read models.

2026-06-11 update: Core `/v1/health/ready` now gates its protocol-level ready
bit through the existing deployment readiness report for the default `dev-01`
workspace instead of relying on config booleans alone. The response keeps the
Core readiness protocol fields and adds content-safe deployment blockers,
warnings, and check summaries under `checks`; failed readiness-store access now
fails closed without exposing raw payloads or secrets. This advances the
Container health and readiness contract while leaving `/v1/deployment/readiness`
behavior intact and preserving no runtime writes, no live OpenClaw mutation, and
no activation authority. Validation: focused readiness tests passed (`6 passed,
20 deselected`), touched-file Ruff passed, and required gates passed with
`uv run ruff check sidecar`, `uv run pytest` (`479 passed`), `uv run python -m
compileall -q sidecar`, and `git diff --check`. Next: add live
Postgres/pgvector, schema/read-model, and scheduler lease probes to the shared
deployment readiness substrate.

2026-06-11 update: SQL-backed topology admission now has a bounded smoke
primitive at `scripts/autoskill_topology_admission_smoke.py`. The smoke applies
the bootstrap migration to disposable pgvector/Postgres, inserts content-safe
governed evidence rows, resolves evidence fidelity through
`AsyncpgEvidenceStore`, and persists create topology proposals through the
asyncpg topology/governance/autonomy stores. It verifies `hash_only`,
`metadata_only`, and unavailable evidence persist blocked/fail-closed, while
`redacted_derivative` and `declassified_summary` persist as propose-only
candidate operations with planned trials and staged transactions. This advances
topology/evidence-to-skill bridge Sections 13.6-13.8 plus Part V
evidence-sufficiency/autonomy assurance, while preserving no raw-evidence
exposure, no runtime skill writes, no activation authority, and no live
OpenClaw mutation. Validation: `uv run python
scripts/autoskill_topology_admission_smoke.py --database-url
postgresql://autoskill:autoskill-dev@127.0.0.1:55433/autoskill` passed against
a disposable `pgvector/pgvector:pg17` container, and touched-file Ruff
(`uv run ruff check scripts/autoskill_topology_admission_smoke.py`) passed.
Next: wire the smoke into the operator/CI runbook or extend the same
SQL-backed proof to usage-derived topology proposal sources.

2026-06-11 update: topology proposal services now enforce evidence-fidelity
authority even when called below the FastAPI wrapper. The shared service-level
`create`, `improve`, `compose`, and `decompose` paths treat a missing
evidence-fidelity map as `unavailable` and block
`topology_operation_choice`, preventing non-API callers from admitting semantic
topology operations on unresolved evidence authority. This extends the
2026-06-08 API/store-backed evidence-fidelity admission work into the common
proposal primitive while preserving propose-only state, no runtime writes, no
activation authority, and no raw-evidence exposure. Validation: focused
topology tests (`23 passed`), `uv run ruff check sidecar`, `uv run pytest`
(`478 passed`), `uv run python -m compileall -q sidecar`, and `git diff
--check`. No Postgres smoke was run because this is deterministic
service-level admission behavior. Next: add SQL-backed topology admission smoke
when practical and keep closing remaining fidelity-aware candidate-source gaps.

2026-06-08 update: topology proposal admission now consumes governed
 evidence-fidelity state before creating propose-only SkillGraphIR candidates.
 Core resolves cited evidence IDs through the evidence store for direct and
 usage-derived topology proposal APIs, includes the content-safe fidelity map in
 proposal output, transaction metrics, data-to-skill trace content policy, and
 topology calibration components, and blocks `metadata_only`, `hash_only`, or
 unavailable evidence from authorizing `topology_operation_choice`. This closes
 the immediate gap between Observatory evidence-fidelity diagnostics and Core
 topology admission while preserving propose-only state, deterministic authority,
 no raw-evidence reveal, no runtime write, and no activation authority.
 Validation: `uv run pytest sidecar/autoskill/tests/test_topology_services.py
 -q` (`22 passed`), touched-file Ruff, full `uv run ruff check sidecar`, full
 `uv run pytest` (`477 passed`), `uv run python -m compileall -q sidecar`, and
 `git diff --check`. No Postgres smoke was run for this read-only fidelity
 lookup slice. Next: run SQL-backed topology admission smoke when practical and
 continue fidelity-aware admission for remaining semantic candidate sources.

2026-06-08 update: revocation invalidation now follows writer-item source
provenance into compiled artifact invalidation. Governance can expand impacted
`transaction_item` nodes reached through `source_for_writer_item` edges into the
affected `skill_version` objects, and writer apply/rollback item rows now carry
that skill-version UUID for compiled files, support artifacts, manifests,
archive snapshots, and restored rollback artifacts. The filesystem revocation
worker deduplicates the expanded object set before handing it to retrieval,
embedding, context, topology, evaluator, attribution, and governance
invalidators. This closes the immediate Section 1.2 / 2.26 gap between
source-root provenance edges and derived-state invalidation while remaining
content-safe and activation-neutral. Validation: focused worker/governance/writer
tests passed (`3 passed` and `34 passed`), touched-file Ruff passed, and full
required gates passed with `uv run ruff check sidecar`, `uv run pytest` (`475
passed`), `uv run python -m compileall -q sidecar`, and `git diff --check`.
Next: run SQL-backed revocation traversal/invalidation smoke when a bounded
Postgres lane is practical and add any remaining first-class artifact IDs not
covered by skill-version expansion.

2026-06-08 update: writer apply/rollback governance now links transaction source
roots to generated writer transaction items. When a transaction carries
`source_evidence_ids` or `source_memory_ids`, deterministic writer governance
records content-safe `source_for_writer_item` provenance edges from those roots
to compiled-skill, support-artifact, artifact-manifest, archive-snapshot, and
rollback/delete transaction items. This closes part of the provenance-graph gap
for rollback/deletion traversal without exposing raw evidence or adding any
Observatory/live activation authority. Validation: `uv run pytest
sidecar/autoskill/tests/test_audit_writer_events.py::test_writer_records_source_provenance_for_apply_and_rollback_items
-q` (`1 passed`) and `uv run pytest
sidecar/autoskill/tests/test_audit_writer_events.py -q` (`33 passed`). Next
implementation gate: use these writer-item edges in revocation traversal/workers
when revoking evidence or memory-derived compiled artifacts, embeddings,
retrieval records, and broker hints.

2026-06-08 update: Observatory evidence-fidelity status now refreshes from
governed evidence before admin reads. `/admin/api/v1/evidence/fidelity`, raw
vault summary, and evidence-fidelity object microscope paths invoke a
content-safe refresh that aggregates evidence item source kind, decision family,
and canonical fidelity tier, writes/updates `admin_evidence_fidelity_status` for
Postgres-backed stores, and uses deterministic in-memory parity for tests/dev.
`metadata_only` and `hash_only` rows are marked
`evidence_insufficient_for_autonomy`, `redacted_derivative` rows are degraded,
full-fidelity rows are sufficient, and no-evidence workspaces receive explicit
blocked fallback rows rather than an empty/fail-open read model. This advances
Sections 5.5, 5.12-5.14, 17.1, and the Observatory read-only diagnostic
contract without exposing raw evidence or adding operator mutation authority.
Validation: touched-file Ruff; `uv run ruff check sidecar`; `uv run pytest
sidecar/autoskill/tests/test_observatory_api.py -q` (`66 passed`); targeted
evidence-fidelity tests (`2 passed, 64 deselected`); full `uv run pytest` (`472
passed`); `uv run python -m compileall -q sidecar`; `git diff --check`. No
Postgres smoke was run; the SQL-backed refresh is deterministic aggregation over
existing read-model tables and is covered by API/in-memory parity tests. Next
gate: enforce the refreshed fidelity state in autonomy/topology admission and
semantic decision calibration gates so metadata/hash-only evidence can inform
diagnostics but not full autonomous semantic choices.

This plan tracks the unified implementation specification and turns it into
repo-level gates.


2026-06-08 update: scanner policy now performs deterministic harmful-capability
classification in addition to static prompt-injection/text-risk checks. It blocks
hazardous cyber and credential-harvesting workflows, privacy-violating data
collection, fraud/forged-document workflows, and coercive surveillance as
capability risks even when the artifact contains no hidden instructions or
policy-override phrasing. Explicit negative safety boundaries remain allowed,
while boundary inversions that tell the agent not to refuse harmful workflows are
blocked. This advances Sections 2.22, 3.1 scanner/capability boundaries, 5.1,
14.5, 17.1, and Part IV scanner/security capability coverage while preserving
deterministic scanner authority and adding no runtime write, activation, LLM
policy authority, or external mutation path. Focused and required validation
passed as recorded in `TASKFLOW.md`; no migration or Postgres smoke is required
for this scanner-only slice.

2026-06-08 update: context-governance compilation now writes separate
spec-native calibration observations for `context_equivalence` and
`semantic_compression_preservation` instead of recording the combined
`context_budget_semantic_equivalence` family. The deterministic compiler still
owns context artifact, compile-run, budget-event, and semantic-compression
trial persistence, but the autonomy calibration corpus now receives one
content-safe context-equivalence observation and one content-safe
semantic-compression preservation observation per governed compile. Components
include artifact/compile/trial IDs, token budget status, scanner codes,
requirement preservation counts, semantic-equivalence score, probe evidence
state, safe routing/regression summaries, semantic density, and explicit
`llm_authority=none` plus `runtime_write_authority=false`; they omit compiled
skill text, raw SkillIR, prompts, raw evidence, runtime write authority, and
activation authority. This advances Sections 5.5, 5.12, 5.13, 5.14, and
11.12-11.15 plus Part IV semantic decision-family coverage for both context
equivalence and semantic compression preservation. Focused validation passed
with the context compiler/evaluator calibration subsets, touched-file Ruff, and
the required gates recorded in `TASKFLOW.md`; no migration or Postgres smoke is
required because the slice reuses the generic autonomy calibration primitive.

2026-06-07 update: action attribution checks now write pending calibration
observations for the `action_attribution` semantic family. After
`/v1/attribution/action-checks` persists a deterministic risky-action check,
Core records content-safe check/action identifiers, original action risk
labels, verdict, counterfactual kind, contribution counts, broker-policy and
user-intent-hash presence flags, metric key names, numeric metric count, and
explicit `raw_metric_values_returned=false`,
`user_intent_hash_returned=false`, `raw_user_intent_returned=false`,
`runtime_write_authority=false`, and `action_execution_authority=false`.
Blocked or rejected checks record `auto_reject`, allowed checks record
`accept_action_attribution`, and deferred/unknown checks record
`no_op_reschedule`. The calibration payload omits arbitrary metric values,
user-intent hash values, raw user intent, raw evidence, and any action
execution authority. This advances Sections 5.5, 5.12, 5.13, 5.14, and 27
plus Part IV semantic decision-family coverage for action attribution while
preserving deterministic sidecar control and adding no runtime write,
activation, raw-vault reveal, or Observatory mutation authority. Focused
validation passed with `uv run pytest sidecar/autoskill/tests/test_shadowing.py
-q -k "action_attribution_check"` (`2 passed, 4 deselected`) and touched-file
Ruff. Required gates passed with `uv run ruff check sidecar`, `uv run pytest`
(`467 passed`), `uv run python -m compileall -q sidecar`, `docker compose
config --quiet`, and `git diff --check`. A Dev-01 Postgres smoke was attempted
against the existing `dev01-postgres-pgvector` container on
`127.0.0.1:55432`, but the idempotent `scripts/migrate.py` validation path
produced no output within the bounded smoke window and was terminated (`exit
143`); no schema changed, and deterministic in-memory API coverage exercises
the added endpoint/store wiring.

2026-06-07 update: LLM-backed replay intent synthesis now writes pending
calibration observations for the `intent_reconstruction` semantic family. When
`/v1/broker/replay-episodes/synthesize` reconstructs a missing redacted intent
from content-safe retrieval context and deterministic validation passes, Core
records `accept_intent_reconstruction` with T1 risk, source retrieval log ID,
broker decision, profile key, evidence-fidelity tier, redacted-intent source
kind, validation status/check count, context object type counts,
candidate/rendered skill counts, and explicit `raw_prompt_returned=false`,
`redacted_intent_returned=false`, and `runtime_write_authority=false`. The
calibration payload omits the reconstructed intent text and raw prompt content.
This advances Sections 5.5, 5.12, 5.13, and 5.14 plus Part IV semantic
decision-family coverage for intent reconstruction while preserving
sidecar-only deterministic control and adding no runtime write, activation,
raw-vault reveal, or Observatory mutation authority. Focused validation passed
with `uv run pytest sidecar/autoskill/tests/test_broker_policy_api.py -q -k
"synthesizes_missing_intent_from_safe_retrieval_context or
synthesizes_replay_episodes_from_redacted_telemetry"` (`2 passed, 12
deselected`) and touched-file Ruff. Required gates passed with `uv run ruff
check sidecar`, `uv run pytest` (`466 passed`), `uv run python -m compileall -q
sidecar`, `node --test plugin/autoskill/test/hook-smoke.test.js` (`21`
passed), `docker compose config --quiet`, and `git diff --check`. No Postgres
smoke was required because the slice reuses the existing autonomy observation
primitive and is covered through the in-memory broker replay API path without
schema changes.

2026-06-07 update: lifecycle curation actions now write pending calibration
observations for the `lifecycle_curation` semantic family. After `curation.run`
finishes, the worker records one content-safe observation per curation action
through the existing autonomy control store. Applied archive and active-budget
decisions record `archive_low_utility_skill`; archive promotions record
`promote_archived_skill`; duplicate merges record `merge_duplicate_skill`;
split/decomposition repair plans record `stage_lifecycle_decomposition_repair`;
improvement/disambiguation repair plans record
`stage_lifecycle_improvement_repair`; blocked actions record `quarantine`.
Calibration components include action IDs, skill IDs, action/status, safe
reason codes, utility/count/token signals, feature key names, filesystem
archive/promotion status, merge/repair schema names, repair trial kinds,
curation result counts, and explicit `raw_reason_returned=false`,
`raw_skill_text_returned=false`, `runtime_write_completed_by_llm=false`, and
`observatory_direct_mutation_authority=false`. The payload omits raw skill
text, raw curation rationale, and any direct Observatory mutation authority.
This advances Sections 5.5, 5.12, 5.13, 5.14, 21, and 27 plus Part IV/Part V
lifecycle-curation coverage while preserving deterministic worker authority and
adding no autonomous production apply. Focused validation passed with `uv run
pytest sidecar/autoskill/tests/test_worker.py -q -k
"curation_worker_records_lifecycle_calibration_observations or
dispatches_utility_and_curation"` (`2 passed, 43 deselected`) and touched-file
Ruff. Required gates passed with `uv run ruff check sidecar`, `uv run pytest`
(`466 passed`), `uv run python -m compileall -q sidecar`, `docker compose
config --quiet`, and `git diff --check`. No Postgres smoke was required because
the slice reuses existing curation persistence and the existing asyncpg
autonomy observation primitive without schema changes.

2026-06-07 update: administrative escalation events now write pending
calibration observations for the `administrative_escalation` semantic family.
After `record_administrative_escalation` persists the hard-boundary escalation
event and Observatory read-model row, the null and asyncpg autonomy stores
record a content-safe `escalate_admin` observation with T4 risk, deterministic
confidence, escalation/event identifiers, decision family, target kind,
attempted fallback counts/action names, safe key summaries, hard-invariant key
names, source fidelity, and explicit `target_id_returned=false`,
`raw_reason_returned=false`, `raw_content_returned=false`,
`runtime_write_authorized=false`, and `autonomous_apply_authority=false`. The
calibration payload omits raw target IDs, operator reason text, raw content,
raw reveal material, and runtime mutation authority. This advances Sections
5.5, 5.12, 5.13, and 5.14 plus Part IV administrative-escalation semantic
decision-family coverage and Observatory autonomy workcell requirements.
Focused validation passed with `uv run pytest
sidecar/autoskill/tests/test_observatory_api.py -q -k "raw_reveal"` (`2
passed, 63 deselected`) and touched-file Ruff. Required gates passed with `uv
run ruff check sidecar`, `uv run pytest` (`465 passed`), `uv run python -m
compileall -q sidecar`, `docker compose config --quiet`, `node --test
plugin/autoskill/test/hook-smoke.test.js` (`21` passed), and `git diff
--check`. A Dev-01 Postgres smoke inserted a throwaway
`cron-admin-escalation-calibration-smoke-*` workspace through
`AsyncpgAutonomyControlStore`, verified
`family=administrative_escalation`, `action=escalate_admin`,
`risk=T4_external_or_irreversible`, `confidence=1.0`, `sample_count=1`,
`support=empirical_low_support`, no raw target ID in confidence components,
then cleaned up with `cleanup_remaining_workspaces=0`.

2026-06-07 update: model and embedding profile qualification now writes pending
calibration observations for the `model_profile_qualification` and
`embedding_profile_qualification` families. After a text or embedding
qualification run is persisted, the service records a content-safe observation
through the existing autonomy control store. Successful text verdicts record
`accept_model_profile_qualification`; successful embedding verdicts record
`accept_embedding_profile_qualification`; failed verdicts record `auto_reject`.
The calibration payload includes profile IDs/keys, route/provider/model
identifiers, probe-set version, qualification run ID, verdict, check
names/results, pass counts, optional reason code, and explicit
`raw_error_returned=false`, `runtime_write_authority=false`, and
`profile_activation_authority=false`; it omits endpoint refs, raw errors,
prompts, embeddings, and secrets. This advances Sections 3.3, 5.3, 5.4, 5.5,
5.9, 5.12, 5.13, and 5.14 while preserving deterministic qualification
authority and adding no profile activation, runtime skill writes, or autonomous
apply authority. Focused validation passed with `uv run pytest
sidecar/autoskill/tests/test_profile_qualification.py -q` (`6 passed`) and
touched-file Ruff. Required gates passed with `uv run ruff check sidecar`, `uv
run pytest` (`465 passed`), `uv run python -m compileall -q sidecar`, `docker
compose config --quiet`, and `git diff --check`. A Dev-01 Postgres smoke used
`AsyncpgProfileStore`, `AsyncpgProfileQualificationStore`, and
`AsyncpgAutonomyControlStore` to qualify a throwaway
`cron-profile-qualification-calibration-smoke-*` text profile, verified
`family=model_profile_qualification`,
`action=accept_model_profile_qualification`, `risk=T1_internal_record`,
`confidence=1.0`, `sample_count=1`, `support=empirical_low_support`,
`profile_status=qualified`, then cleaned up with
`cleanup_remaining_workspaces=0`.

2026-06-07 update: repair execution triage now writes pending calibration
observations for the `freeze_repair_triage` semantic family. After each
`repair.execute` source finishes completion bookkeeping, the worker records a
content-safe observation that maps evaluator probes to `run_more_probes`, drift
rechecks to `collect_more_evidence`, policy-approved staged writer work to
`stage_repair_artifact`, blocked executions to `quarantine`, and default
reschedules to `no_op_reschedule`. The calibration payload includes source
IDs, proposal schema/key names, memory-influence count, triage status, queued
job references, repair transaction ID, policy-approval booleans, explicit
scanner/evaluator/context-gate preservation, and
`runtime_write_completed=false`; it omits proposal bodies, repair rationale,
memory content, staged skill text, and raw evidence. This advances Sections
5.3, 5.5, 5.6, 5.9, 5.11, 5.12, 5.13, and 5.14 plus Part IV lifecycle
freeze/repair semantic decision-family coverage while preserving trial-only
writer staging, activation-gate requirements, sidecar-only deterministic
control, and no runtime skill writes. Focused validation passed with `uv run
pytest sidecar/autoskill/tests/test_worker.py -q -k "repair_execute"` (`6
passed, 38 deselected`), `uv run pytest
sidecar/autoskill/tests/test_redaction.py -q` (`4 passed`), `node --test
plugin/autoskill/test/hook-smoke.test.js` (`21` tests passed), and
touched-file Ruff. Required gates passed with `uv run ruff check sidecar`, `uv
run pytest` (`463 passed`), `uv run python -m compileall -q sidecar`, `docker
compose config --quiet`, and `git diff --check`. A Dev-01 Postgres smoke
inserted a throwaway `cron-repair-triage-calibration-smoke-*` workspace
through `AsyncpgAutonomyControlStore`, verified
`family=freeze_repair_triage`, `action=run_more_probes`,
`risk=T1_internal_record`, `sample_count=1`,
`support=empirical_low_support`, `runtime_write_completed=false`, then cleaned
up and verified `cleanup_remaining_workspaces=0`.

2026-06-07 update: external-skill review decisions now write pending
calibration observations for the `external_skill_relationship` semantic
family. After `/v1/external-skills/review-actions` successfully records a
reuse/import/ignore/quarantine review decision, Core records a content-safe
observation with the review-action ID, external-skill ID, action, status,
collision risk/score, reason-code constants, metadata key names, and explicit
`external_body_returned=false`, `raw_root_path_returned=false`, and
`external_root_mutated=false`. Reuse decisions record
`suppress_skillkernel_duplicate_for_external_skill`; import decisions record
`stage_external_skill_import_review`; ignore decisions record `inventory_only`;
quarantine/rejected decisions record `quarantine` or `auto_reject`. The
calibration payload omits external skill bodies, raw root paths, operator
rationale, and raw metadata values beyond the bounded collision fields,
preserving the external-owned-root immutability boundary and adding no runtime
skill write, autonomous external mutation, activation, or browser raw-content
authority. This advances Sections 5.5, 5.12, 5.13, and 5.14 plus Part IV
semantic decision-family coverage for external-skill relationships. Focused
validation passed with `uv run pytest
sidecar/autoskill/tests/test_external_skills.py -q -k "review_action"` (`2
passed, 5 deselected`) and touched-file Ruff. Required gates passed with `uv
run ruff check sidecar`, `uv run pytest` (`463 passed`), `uv run python -m
compileall -q sidecar`, and `git diff --check`. A Dev-01 Postgres smoke
inserted a throwaway `cron-external-calibration-smoke-*` workspace through the
external-skill inventory/review API path backed by asyncpg external-skill and
autonomy stores, verified
`metric_family=external_skill_relationship`,
`selected_action=suppress_skillkernel_duplicate_for_external_skill`,
`action_risk_tier=T1_internal_record`, `sample_count=1`, and
`support=empirical_low_support`, confirmed no private rationale or raw root
path leaked into confidence components, then cleaned up and verified
`cleanup_remaining_workspaces=0`.

2026-06-07 update: memory quarantine decisions now write pending calibration
observations for the `memory_declassification` semantic family. After
`/v1/memory/quarantine/{quarantine_id}/decision` successfully approves,
rejects, or expires a quarantined memory candidate, Core records a content-safe
observation with the quarantine ID, source object type, status, proposed-memory
key names, taint/scanner key names, scanner secret count, and
`runtime_loaded=false`. Approved decisions record
`approve_memory_declassification`; rejected decisions record `auto_reject`;
expired decisions record `no_op_reschedule`. The calibration payload omits the
proposed memory content and decision rationale, preserving the quarantine-first
memory governance boundary and adding no runtime memory influence, browser raw
content exposure, activation, or runtime skill write authority. This advances
Sections 5.5, 5.12, 5.13, and 5.14 plus Part IV semantic decision-family
coverage for memory declassification. Focused validation passed with `uv run
pytest sidecar/autoskill/tests/test_admin_surfaces.py -q -k memory_quarantine`
(`1 passed, 18 deselected`) and touched-file Ruff. Required gates passed with
`uv run ruff check sidecar`, `uv run pytest` (`463 passed`), `uv run python -m
compileall -q sidecar`, and `git diff --check`. A Dev-01 Postgres smoke
inserted a throwaway `cron-memory-calibration-smoke-*` workspace through the
memory quarantine decision API path backed by asyncpg memory/autonomy stores,
verified `metric_family=memory_declassification`, `observation_count=1`,
`sample_count=1`, `support=empirical_low_support`, no leaked memory/rationale
text in confidence components, then deleted the smoke workspace and verified
`remaining_workspaces=0`.

2026-06-07 update: broker replay episode synthesis now writes pending
calibration observations for the `replay_episode_promotion` semantic family.
After `/v1/broker/replay-episodes/synthesize` persists a telemetry-derived
replay row, it records a content-safe `promote_replay_episode` observation with
the replay episode/log IDs, evidence fidelity, normalized intent-source kind,
deterministic validation status, expected decision, skill/context counts, and
raw-prompt/operator-plan flags. The calibration components deliberately omit the
redacted replay intent and raw evidence, and stale telemetry replay repairs use
the same observation path. This advances Sections 5.5, 5.12, 5.13, and 5.14;
Part IV semantic decision-family coverage for replay/canary intent synthesis;
and production criteria 31.58/31.63 without adding runtime write authority,
activation, raw-vault reveal, or an Observatory-side mutation path. Focused
validation passed with `uv run pytest
sidecar/autoskill/tests/test_broker_policy_api.py -q -k
"synthesizes_replay_episodes_from_redacted_telemetry or
synthesis_repairs_stale_telemetry_episode_decision"` (`2 passed, 12
deselected`) and touched-file Ruff. Required gates passed with `uv run ruff
check sidecar`, `uv run pytest` (`463 passed`), `uv run python -m compileall -q
sidecar`, and `git diff --check`. A Dev-01 Postgres smoke inserted a throwaway
`cron-replay-calibration-smoke-*` workspace and retrieval log, synthesized one
replay episode through asyncpg retrieval/broker/autonomy stores, verified
`metric_family=replay_episode_promotion`, `sample_count=1`,
`support=empirical_low_support`, then cleaned up and verified
`remaining_workspaces=0`.

2026-06-07 update: context compilation now writes pending calibration
observations for the `context_budget_semantic_equivalence` semantic family.
`compile_skill_with_context_governance` accepts an optional autonomy control
store after persisting the context artifact, compile run, budget event, and
semantic-compression trial, then records content-safe compile status,
budget/scanner state, requirement preservation counts, semantic-equivalence
score, probe-evidence gate state, and IDs for the artifact/compile/trial
records. Passing compiles record `accept_context_artifact`; failed compiles
record reversible `compile_more_conservatively` or deterministic `auto_reject`
evidence. The repair-proposal worker path now passes its existing
proposal-gate autonomy store through when present, keeping compiler/writer
authority deterministic and adding no runtime skill writes, activation, or LLM
file/SQL authority. This advances Sections 5.5, 5.7, 5.9, 5.12, 5.13, 5.14,
11, and 20; Part IV semantic decision-family coverage for context
equivalence/compression; and production criteria 31.58/31.63. Focused
validation passed with `uv run pytest
sidecar/autoskill/tests/test_skillir_compiler_scanner.py -q -k
"context_compiler"` (`8 passed, 12 deselected`) and touched-file Ruff.
Required gates passed with `uv run ruff check sidecar`, `uv run pytest` (`463
passed`), `uv run python -m compileall -q sidecar`, and `git diff --check`. A
Dev-01 Postgres smoke compiled a throwaway
`cron-context-equivalence-calibration-smoke-*` SkillIR through
`AsyncpgContextGovernanceStore` plus `AsyncpgAutonomyControlStore`, verified
`status=passed`, `action=accept_context_artifact`, `sample_count=1`,
`support=empirical_low_support`, then deleted the smoke workspace and verified
`remaining_workspaces=0`.

2026-06-07 update: topology proposal persistence now records pending
calibration observations for the `topology_operation_choice` semantic family.
The propose-only topology persistence path accepts the existing autonomy
control store after staging the operation, transaction, provenance, and planned
trial records, then records content-safe selected action, deterministic
confidence, evidence/trial counts, graph counts, blocker codes, and explicit
propose-only/no-runtime-write flags. Candidate topology choices record
`propose_create`/`propose_improve`/`propose_compose`/`propose_decompose`;
blocked proposals record deterministic `auto_reject` evidence. Core
`/v1/topology/propose` and usage-derived topology proposal routes pass their
existing autonomy store through, keeping scanner/evaluator/trial/rollback
authority unchanged and adding no runtime skill writes or apply-path authority.
This advances Sections 5.5, 5.9, 5.12, 5.13, and 5.14; topology Sections
1.3/13/17; and production criteria 31.29, 31.53, 31.58, and 31.63 by making
topology operation choice part of the calibrated semantic decision-family
surface. Focused validation passed with `uv run pytest
sidecar/autoskill/tests/test_topology_services.py -q -k "calibration or
topology_proposal_persistence_records_operation"` (`3 passed, 17 deselected`),
`uv run pytest sidecar/autoskill/tests/test_admin_surfaces.py -q -k
"topology_proposal_endpoint"` (`4 passed, 15 deselected`), and touched-file
Ruff. Required gates passed with `uv run ruff check sidecar`, `uv run pytest`
(`462 passed`), `uv run python -m compileall -q sidecar`, and `git diff
--check`. A Dev-01 Postgres smoke inserted a throwaway
`cron-topology-calibration-smoke-*` workspace through the topology proposal API
path backed by asyncpg topology/governance/autonomy stores, verified
`status=candidate`, `operation_kind=compose`, `trial_count=5`,
`metric_sample_count=1`, and `metric_support=empirical_low_support`, then
deleted the smoke workspace and verified zero remaining smoke workspaces.

2026-06-07 update: runtime broker decisions now write pending calibration
observations for the `broker_decision_adjudication` semantic family. The broker
context-hint path accepts the existing autonomy control store and records
content-safe selected action, deterministic confidence, broker policy refs,
retrieval-log ref, candidate/rendered/suppressed counts, reason codes, and
bundle-scan status for non-cached persisted broker decisions. The Core
`/v1/runtime/context-hint` route passes its existing autonomy store into the
broker, so this reuses the generic calibration persistence/read-model surface
without adding LLM authority to runtime hooks, changing cache semantics,
exposing raw content, or enabling runtime writes. This advances Sections 5.5,
5.12, 5.13, 5.14, Part IV semantic decision-family broker adjudication
coverage, and production criteria 31.58/31.63. Focused validation passed with
`uv run pytest sidecar/autoskill/tests/test_broker.py -q -k "calibration or
context_broker_renders"` (`2 passed, 22 deselected`) and touched-file Ruff.
Required gates passed with `uv run ruff check sidecar`, `uv run pytest` (`459
passed`), `uv run python -m compileall -q sidecar`, and `git diff --check`.
Report gates passed with core acceptance (`ready=true`, `63` production
criteria, `7` context criteria), Observatory acceptance (`ready=true`, `42`
acceptance criteria, `44` developer checklist items), conformance
(`ready=true`, `23/23`), readiness (`ready=true`, `17` checklist items), and
handoff governance (`35` risks mitigated, `79` satisfied). A Dev-01 Postgres
smoke inserted a throwaway `cron-broker-calibration-smoke-*` workspace through
the broker path backed by `AsyncpgAutonomyControlStore`, verified
`decision=skill_hint`, `sample_count=1`, `coverage_rate=0.0`,
`abstention_rate=0.0`, and `calibration_support=empirical_low_support`, then
deleted the smoke workspace plus calibration rows.

2026-06-07 update: proposal-gate autonomy adjudication now feeds the current
calibration reliability state back into semantic fallback selection. The
autonomy control store exposes `get_latest_reliability_metric` for both Null and
asyncpg stores, and the proposal-gate Autonomous Decision Orchestrator includes
a content-safe calibration-support packet in the LLM request and persisted
`autonomy_fallback` diagnostics. First-run decisions report `status=none`; when
family metrics exist, the fallback records support status, sample count,
coverage, abstention, false-accept/false-reject, and unnecessary-abstention
rates. This advances Sections 5.2, 5.5, 5.9, 5.12, 5.13, and 5.14 plus
production criteria 31.56, 31.58, and 31.63 by connecting delayed-outcome
reliability metrics to the semantic decision path without authorizing runtime
writes, relaxing hard invariants, or creating a second control plane. Focused
validation passed with `uv run pytest sidecar/autoskill/tests/test_evaluator.py
-q -k "calibration or proposal_gate_autonomy"` (`14 passed, 21 deselected`) and
touched-file Ruff. Required gates passed with `uv run ruff check sidecar`, `uv
run pytest` (`458 passed`), `uv run python -m compileall -q sidecar`, and `git
diff --check`. Report gates passed with core acceptance (`ready=true`, `63`
production criteria, `7` context criteria), Observatory acceptance
(`ready=true`, `42` acceptance criteria, `44` developer checklist items),
conformance (`ready=true`, `23/23`), readiness (`ready=true`, `17` checklist
items), and handoff governance (`35` risks mitigated, `79` satisfied). A Dev-01
Postgres smoke inserted a throwaway `cron-calibration-support-smoke-*`
workspace, verified the asyncpg latest-family reliability lookup returned
`sample_count=1`, `coverage_rate=0.0`, and
`calibration_support=empirical_low_support`, then deleted the smoke workspace
plus calibration rows.

2026-06-07 update: autonomy reliability metrics now count the full
specification-native soft-exit vocabulary as abstention/calibration support
evidence instead of treating only a small internal fallback subset as
abstention. The Core autonomy store uses one shared classifier for the in-memory
and asyncpg reliability paths, covering Section 5.1/5.6 fallback terms such as
`run_additional_retrieval`, `build_ephemeral_candidate`,
`canary_with_smaller_exposure`, `no_skill`, verifier/re-adjudication aliases,
scope-reduction aliases, pending-candidate exits, and canary/ephemeral paths.
This advances Sections 5.1, 5.5, 5.6, 5.9, 5.12, and 5.14 plus production
criteria 31.53, 31.58, and 31.63 by making over-deferral/abstention reliability
metrics reflect the same fallback ladder the Autonomous Decision Orchestrator
advertises, without changing hard invariants, runtime-write authority, or
Observatory mutation boundaries. Focused validation passed with the
calibration/orchestrator evaluator subset (`6 passed, 28 deselected`) and
touched-file Ruff. Required gates passed with `uv run ruff check sidecar`,
`uv run pytest` (`457 passed`), `uv run python -m compileall -q sidecar`, and
`git diff --check`. Report gates passed with core acceptance (`ready=true`, `63`
production criteria, `7` context criteria), Observatory acceptance
(`ready=true`, `42` acceptance criteria, `44` developer checklist items),
conformance (`ready=true`, `23/23`), readiness (`ready=true`, `17` checklist
items), and handoff governance (`35` risks mitigated, `79` satisfied). A
Dev-01 Postgres smoke inserted a throwaway
`cron-calibration-abstention-smoke-*` workspace, recorded four broker-decision
soft-exit calibration observations through `AsyncpgAutonomyControlStore`,
verified latest `sample_count=4` and `abstention_rate=1.0`, and deleted the
smoke workspace plus calibration rows.

2026-06-07 update: autonomy calibration persistence now has a generic
semantic decision-family observation primitive instead of being usable only by
proposal-gate fallback recording. `AutonomyControlStore` exposes
`record_calibration_observation` for any calibrated semantic family with
content-safe family/action/confidence metadata, optional decision/adjudication
links, deterministic confidence bounding, outcome-status normalization, and
fail-closed validation for blank family/action names or unsupported action risk
tiers. The proposal-gate fallback path now reuses the same insert helper, and
delayed outcomes continue to refresh 30-day reliability metrics for the
affected calibration family. This advances Sections 5.5, 5.9, 5.12, 5.13,
5.14, and production criterion 31.58 by making calibration coverage reusable
for broker decision adjudication, context-equivalence, topology choice, and
other semantic decision families without adding runtime-write authority,
autonomous apply, or a second Observatory control plane. Focused validation
passed with `uv run pytest sidecar/autoskill/tests/test_evaluator.py -q -k
"calibration"` (`4 passed, 29 deselected`) and touched-file Ruff. Required
gates passed with `uv run ruff check sidecar`, `uv run pytest` (`456 passed`),
`uv run python -m compileall -q sidecar`, and `git diff --check`. Report gates
passed with core acceptance (`ready=true`, `63` production criteria, `7`
context criteria), Observatory acceptance (`ready=true`, `42` acceptance
criteria, `44` developer checklist items), conformance (`ready=true`, `23/23`),
readiness (`ready=true`, `17` checklist items), and handoff governance (`35`
risks mitigated). A Dev-01 Postgres smoke inserted a throwaway
`cron-generic-calibration-smoke-*` workspace, recorded a generic
`broker_decision_adjudication` calibration observation through
`AsyncpgAutonomyControlStore`, listed/detail-read it and its reliability metric
through `AsyncpgObservatoryAdminStore`, attached delayed outcome `success`, and
deleted the smoke workspace plus calibration rows.

2026-06-07 update: Observatory now exposes autonomy calibration observations
and reliability metrics as content-safe admin read models. The
`ObservatoryAdminStore` contract and asyncpg implementation list/detail
`autonomy_calibration_observations` and `autonomy_reliability_metrics`; the
admin API adds `/admin/api/v1/autonomy/calibration/observations`,
`/admin/api/v1/autonomy/calibration/observations/{observation_id}`,
`/admin/api/v1/autonomy/calibration/metrics`, and
`/admin/api/v1/autonomy/calibration/metrics/{metric_id}`; and generic object
microscope resolution supports both calibration object types. These projections
expose workspace, calibration family, selected action, predicted confidence,
outcome status, aggregate rates, reliability bins, support status, and
over-action/over-deferral diagnostics while omitting raw outcome payloads,
confidence-component payloads, raw semantic verdicts, and raw evidence. This
advances Sections 5.5, 5.9, 5.12, and 5.14 plus Observatory Sections 21.16,
21.23, and 24.auto.1 and production criteria 31.58/31.63 by making delayed
outcomes and reliability metrics operationally inspectable without creating a
second control plane or weakening deterministic hard invariants. Focused
validation passed with the Observatory autonomy route/content-safety regression
(`2 passed, 64 deselected`), touched-file Ruff, and generated OpenAPI client
freshness. Required gates passed with `uv run ruff check sidecar`, `uv run
pytest` (`453 passed`), `uv run python -m compileall -q sidecar`, `git diff
--check`, and `npm run build` in `sidecar/autoskill/observatory`. Report gates
passed with core acceptance (`ready=true`, `63` production criteria, `7`
context criteria), Observatory acceptance (`ready=true`, `42` acceptance
criteria, `44` developer checklist items), conformance (`ready=true`, `23/23`),
readiness (`ready=true`, `17` checklist items), and handoff governance (`35`
risks mitigated). A Dev-01 Postgres smoke inserted a throwaway
`cron-calibration-readmodel-smoke-*` workspace, verified the new asyncpg
observation/metric list and detail methods, and deleted the smoke workspace
plus its calibration rows.

2026-06-07 update: autonomy calibration persistence now attaches real
calibration corpus rows to proposal-gate fallback decisions instead of relying
only on schema/report-level evidence. `record_proposal_gate_fallback` seeds a
pending `autonomy_calibration_observations` row with calibration family,
adjudication/decision IDs, action risk tier, predicted confidence, confidence
components, and selected action, then refreshes a 30-day
`autonomy_reliability_metrics` snapshot with sample count, coverage,
abstention rate, reliability bins, calibration error/Brier-style fields when
delayed outcomes exist, and empirical support status. A new
`record_calibration_outcome` store method records delayed success/failure
outcomes plus false-accept/false-reject/unnecessary-abstention/harm and
utility-per-token inputs, preserving hard-invariant authority and adding no
runtime-write capability. This advances Sections 5.5, 5.9, 5.12, 5.14, and
production criteria 31.56/31.58/31.63 by making semantic decision-family
calibration observations and reliability metrics operational Core state.
Focused validation passed with the proposal-gate autonomy evaluator subset (`9
passed, 21 deselected`) and touched-file Ruff. Required gates passed with `uv
run ruff check sidecar`, `uv run pytest` (`453 passed`), `uv run python -m
compileall -q sidecar`, `git diff --check`, core acceptance (`ready=true`,
`70` implemented, `7` context criteria), Observatory acceptance (`ready=true`,
`86` satisfied), conformance (`ready=true`, `23/23`), readiness (`ready=true`,
`17` checklist items), and handoff governance (`79` satisfied). A
compose/Postgres smoke against the Dev-01 local database inserted a throwaway
proposal-gate fallback, recorded a delayed calibration outcome, verified
`outcome_status='success'`, and then deleted the smoke workspace plus its
metrics/observation/decision/adjudication rows.

2026-06-07 update: proposal-gate autonomy adjudication now exposes the
specification-native soft-exit vocabulary in the LLM request instead of
advertising only the smaller executable internal action set. Section 5.1,
5.6, and 5.10 terms including `run_additional_retrieval`,
`use_raw_vault_context_if_policy_allows`, `run_verifier_adjudication`,
`run_independent_verifier_adjudication`, `build_ephemeral_candidate`,
`record_pending_candidate`, `no_op_with_reschedule`, and `no_skill` are
deterministically normalized to existing governed worker actions while the
requested action remains visible in the content-safe fallback payload. This
advances Sections 5.1, 5.2, 5.6, 5.7, 5.10, and 12.8 without adding runtime
write authority, raw-vault access, or a new control plane. Focused validation
passed with the proposal-gate autonomy evaluator subset (`8 passed, 21
deselected`) and touched-file Ruff. Required gates passed with `uv run ruff
check sidecar`, `uv run pytest` (`452 passed`), `uv run python -m compileall
-q sidecar`, `git diff --check`, core acceptance (`ready=true`, `70`
implemented, `7` context criteria), Observatory acceptance (`ready=true`, `86`
satisfied), conformance (`ready=true`, `23/23`), readiness (`ready=true`, `17`
checklist items), and handoff governance (`79` satisfied). No compose/Postgres
smoke was required because this slice changes in-process adjudication prompt
vocabulary and deterministic normalization only.

2026-06-07 update: threshold-deadlock remediation now persists a deterministic
recommended action derived from the repeated stall context instead of treating
every soft-threshold loop as a generic evidence-collection problem.
`evaluations.remediate_fallbacks` maps token-cost stalls to `narrow_scope`,
low-utility/probe/adjudication stalls to `generate_more_probes`,
profile/provider-unavailable stalls to `no_action`, and missing contrastive
proof to `collect_more_evidence`; both the remediation payload and
`threshold_deadlock_findings.recommended_action` use the existing bounded enum.
This advances Sections 5.10-5.14 and 12.8.2-12.8.3 by making threshold
deadlocks actionable without granting LLM write authority, changing hard
invariants, or adding a policy-schema migration. Focused validation passed
with the fallback-remediation evaluator subset (`4 passed, 19 deselected`) and
touched-file Ruff. Required gates passed with full sidecar Ruff, full pytest
(`446 passed`), compileall, diff-check, core acceptance (`ready=true`, `70`
implemented, `7` context criteria), Observatory acceptance (`ready=true`, `86`
satisfied), and conformance (`ready=true`, `23/23`). No compose/Postgres smoke
was required because the slice uses existing threshold-deadlock persistence
shape and deterministic evaluator/store-unit coverage.

2026-06-07 update: proposal-gate autonomy adjudication now accepts
`auto_accept` as a valid structured Autonomous Decision Orchestrator verdict
for soft-threshold stalls, then deterministically maps it to `stage_canary`
before persistence or activation checks. This aligns the proposal-gate fallback
vocabulary with Section 5.2 while preserving Section 17.6's deterministic
activation boundary: the original LLM verdict remains visible in the
content-safe fallback payload, the selected action is canary-only, runtime
writes remain unauthorized, and the existing writer/topology activation gates
still decide whether anything can apply. Focused validation passed with the proposal-gate
autonomy evaluator regressions (`6 passed, 13 deselected`) and touched-file
Ruff. Required gates passed with full sidecar Ruff, full pytest (`441
passed`), compileall, diff-check, core acceptance (`ready=true`, `70`
implemented, `7` context criteria), Observatory acceptance (`ready=true`, `86`
satisfied), and conformance (`ready=true`, `23/23`). No compose/Postgres smoke
was required because the slice changes deterministic in-memory action
normalization and adds no schema or persistence contract.

2026-06-07 update: proposal-gate `needs_intervention` now stays on the LLM
autonomy path through provider routing, JSON schema handling, and invalid-output
recovery. The LLM client supports an optional OpenAI-compatible JSON
response-format hint, the proposal-gate autonomy request is compact and
JSON-mode by default, invalid/truncated adjudicator output gets one autonomous
retry, and exhausted JSON repair records a governed `run_re_adjudication`
fallback with the LLM invocation attached instead of degrading to
`llm-adjudication-unavailable`. The reference compose and `.env.example`
defaults now point Dev-01 LLM traffic at `http://llama-cpp-compaction:8080/v1`
on the shared Docker network, matching the documented model-service topology.
The live stale-row/schema/profile repair was performed directly on Dev-01 as a
one-time operator action so old rows could be brought up to the current control
plane; no permanent migration/backfill endpoint or background unstick loop was
added to the project.

2026-06-07 update: Observatory proposal-gate diagnostics now have a dedicated
Gates view tied to existing sidecar read models for evaluation reviews and
autonomy decisions. Evaluation summaries persist a sanitized autonomy-fallback
projection, the evaluation microscope links selected fallback action,
admissibility, autonomy decision ID, semantic adjudication ID, and downstream
provenance, and the frontend can navigate from a stalled proposal gate to the
linked autonomy decision detail without giving Observatory independent mutation
authority. The proposal-gate autonomy path also accepts model profiles with a
generic `qualified` status when their latest qualification verdict is
`qualified_autonomous`, matching the profile qualification read model used by
operators. This advances Core Sections 5.1 and 5.10-5.12 plus Observatory
Sections 21.16, 21.22, 21.23, 24.auto.1, and 24.auto.3 by making
soft-threshold remedies visible as deterministic, content-safe control-plane
state. Focused validation passed with the evaluator/Observatory API regression
set (`81 passed`) and the Observatory frontend production build. Required
gates passed with full sidecar Ruff, full pytest (`437 passed`), compileall,
diff-check, core acceptance (`ready=true`, `70` implemented, `7` context
criteria), Observatory acceptance (`ready=true`, `86` satisfied), and
conformance (`ready=true`, `23/23`). No compose/Postgres smoke was required
because this slice uses existing admin read-model APIs and adds no schema
change.

2026-06-06 update: activation readiness now requires the selected Autonomous
Decision Orchestrator action for writer and topology activation checks. The
deterministic gate accepts only `auto_accept` or `stage_canary`; `stage_canary`
can clear the soft proposal-gate `needs_intervention` stall for bounded canary
admission, but hard scanner/evaluator/context/profile failures and missing
autonomy decisions still block activation. This advances Sections 5.1-5.3,
5.10-5.12, and 17.6 by connecting semantic fallback results to activation
authority without granting the LLM direct write authority or mutating live
runtime skills during this implementation slice.

2026-06-06 update: `repair.execute` now fails closed for direct policy-approved
writer-apply repair payloads unless the repair is anchored to a concrete
`skill_version_id` for the affected repair source. Direct drift/curation repair
manifests must carry the same skill-version anchor as the source or proposal
before a `writer.apply` job can be queued; unanchored manifests now fall back to
the deterministic gate/recheck path instead of mutating runtime artifacts. This
advances localized repair under Phase 9 plus Core Sections 13.7-13.8 and
production acceptance criteria 31.14/31.24 by preserving the spec bias toward
targeted repair and rollback-complete activation evidence. Focused validation
passed with the repair-anchor regressions (`2 passed, 41 deselected`) and
touched-file Ruff. Required gates passed with `uv run ruff check sidecar`, `uv
run pytest` (`430 passed`), `uv run python -m compileall -q sidecar`, `git diff
--check`, core acceptance (`ready=true`, `70` implemented, `7` context
criteria), Observatory acceptance (`ready=true`, `86` satisfied), and
conformance (`ready=true`, `23/23`). No compose/Postgres smoke was required
because the slice changes pre-queue deterministic repair admission and is
covered by in-memory worker/governance tests.

2026-06-06 update: Deterministic writer rollback deletion now validates that
the target path is exactly `skills/autoskill/<safe-slug>` before recording
rollback status, transaction items, provenance edges, or touching the
filesystem. This closes a fail-closed path-authority gap where the helper that
deletes newly-created active skills accepted any contained workspace-relative
path; malformed rollback actions now cannot delete arbitrary workspace
content. This advances Core Sections 9.6 and 17.1 plus production acceptance
criteria 31.9 and 31.14 without enabling runtime skill promotion,
autonomous apply, or broader production mutation. Focused validation passed
with the writer rollback path regression and full writer event module (`31
passed`) plus targeted Ruff. Required gates passed with full sidecar Ruff,
full pytest (`427 passed`), compileall, diff-check, core acceptance
(`ready=true`, `70` implemented, `7` context criteria), Observatory acceptance
(`ready=true`, `86` satisfied), and conformance (`ready=true`, `23/23`). No
compose/Postgres smoke was required because this is a deterministic
pre-persistence filesystem path admission change covered by in-memory
governance tests.

2026-06-06 update: Observatory guarded action admission now fails closed unless
the request includes a non-empty audit reason. The shared action recorder
enforces the audit-reason requirement for both `/admin/api/v1/actions` and all
registered guarded-action aliases before recording action audits, attribution
checks, audit-chain rows, or live events. This advances Observatory Sections
12.1, 12.6, and 16.1 plus acceptance criterion 21.29 by making operator action
auditability deterministic without adding UI-local control authority or runtime
apply behavior. Focused validation passed with the guarded-action regression
(`3 passed, 61 deselected`) and targeted Ruff. Required gates passed with full
sidecar Ruff, full pytest (`422 passed`), compileall, diff-check, core
acceptance (`70` implemented), Observatory acceptance (`86` satisfied), and
conformance (`23/23`). No compose/Postgres smoke was required because this is a
pre-persistence route-admission change covered by in-memory action-store tests
that verify no audit/action/live-event rows are written on rejection.

2026-06-06 update: Reference compose/operator access now matches the
split-container Observatory route split. The Observatory service is attached
to the same runtime networks as Core so it can reach the shared Postgres/read
model plane in the Dev-01 topology, and `scripts/autoskill_admin_token.py`
defaults `--check` to the sidecar-hosted Observatory admin API on port `8757`
using `/admin/api/v1/config` instead of Core's old summary endpoint. This
advances the unified implementation specification's deployment model,
Observatory image requirements, and Observatory readiness/operator-access
contract without adding UI-local control authority, runtime skill writes, or
autonomous apply behavior. Focused validation passed with the operator-script
regression (`8 passed`), targeted Ruff, and isolated
`COMPOSE_FILE=docker-compose.yml docker compose config --quiet`. Required
gates passed with full sidecar Ruff, full pytest (`421 passed`), compileall,
diff-check, core acceptance (`70` implemented), Observatory acceptance (`86`
satisfied), and conformance (`23/23`). No Postgres smoke was required because
the slice changes reference service wiring and the operator helper endpoint
target only.

2026-06-06 update: Direct vector control endpoints now require an explicit
`embedding_profile_id` for manual upsert, search, and recall-audit operations.
`/v1/embeddings/upsert`, `/v1/embeddings/search`, and
`/v1/embeddings/recall-audit` reject profileless requests before they can
write, compare, or audit vectors outside a declared embedding profile; the
generated embedding worker/profile-selection path remains unchanged for its
existing explicit degraded/test-mode handling. This advances Core Sections
3.2-3.3 and 10.4-10.5 plus production acceptance criteria 31.6 and 31.36.
Focused validation passed with the embedding API regression (`5 passed`) and
targeted Ruff. Required gates passed with full sidecar Ruff, full pytest (`419
passed`), compileall, diff-check, core acceptance (`70` implemented),
Observatory acceptance (`86` satisfied), and conformance (`23/23`). No
compose/Postgres smoke was needed because the slice changes API admission
behavior and focused in-memory route tests cover the store-bypass prevention.

2026-06-06 update: Raw event capture now carries the spec-aligned event
identity and evidence-fidelity envelope needed for governed autonomy. The
plugin emits SHA-256-prefixed payload hashes, deterministic `source_event_key`
values, agent IDs, evidence-fidelity tiers, raw-vault pointers, and a
content-safe runtime hook registration snapshot on startup; Core validates the
fidelity tier, persists the new raw-event columns idempotently, and exposes the
fields through the content-safe captured-event read model. The migration adds
idempotent raw-event columns, a fidelity check, and a workspace/source/source
event key uniqueness guard without enabling raw-vault storage or live runtime
skill apply. This advances Core Sections 12.1-12.1.2 plus the raw-events DDL
contract in Section 31 and Plugin Sections 7.2-7.4. Focused validation passed
with event-store and readiness regressions (`8 passed`) plus plugin `npm test`
(`28 passed`) and `npm run check`. Required gates passed with full sidecar
Ruff, full pytest (`415 passed`), compileall, diff-check, generated OpenAPI
client freshness check, core acceptance (`70` implemented), Observatory
acceptance (`86` satisfied), and conformance (`14/14`). An isolated pgvector
migration smoke applied `scripts/migrate.py` twice against a fresh temporary
database and verified the new raw-event columns plus
`raw_events_workspace_source_event_key_idx`.

2026-06-06 update: Observatory model invocation audit records now have direct
sidecar-hosted, content-safe collection/detail read models in addition to the
generic object microscope. `LLMInvocationStore` lists recent invocation rows
with workspace, purpose, profile, and status filters; admin routes expose
`/admin/api/v1/model-invocations` and
`/admin/api/v1/model-invocations/{llm_invocation_id}`; and the generated
Observatory route catalog includes both paths. The projection preserves stable
invocation, profile, provider/model, thinking, token, status, and trace
metadata while hashing provider errors/request IDs and withholding prompts,
responses, API keys, endpoint URLs, raw audit payloads, and cost analytics. The
run also stabilized the embedding-provider hardening already present in the
worktree: hash embeddings are explicit degraded/test mode, production
embedding jobs require a configured production-ready profile, degraded
embedding state is surfaced through readiness/capabilities/effective
config/Observatory health, and hash profiles run only under the explicit
test/dev allowance. A deployment smoke caught and the run fixed a readiness
predicate regression where the non-paused production embedding flag incorrectly
made `/v1/health/ready` report `ready=false` even when embeddings were
production-ready. This advances Core Sections 3.2-3.3, 10.4-10.5,
28.1-28.2, and 31.48 plus Observatory Sections 8.18, 12.1, 12.6, 13.1, 16.1,
and acceptance criteria 21.16 and 21.26. Focused validation passed with the
LLM invocation route regression plus embedding fail-closed/profile/worker
regressions (`13` focused tests) and targeted Ruff. Required gates also passed
with full sidecar Ruff, full pytest (`415 passed`), compileall, diff-check,
Observatory frontend build, generated OpenAPI client freshness check, core
acceptance (`70` implemented), Observatory acceptance (`86` satisfied), and
conformance (`14/14`). No compose/Postgres smoke was needed because no schema
changed and the slice only adds bounded reads over existing invocation rows
plus deterministic config/profile policy behavior.

2026-06-06 update: Worker heartbeat summaries now carry content-safe
`progress_plan` metadata for long semantic, topology, repair, historical,
embedding, rollback, and writer jobs. The plan is static job-definition
metadata, not caller payload content: it lists expected phase names, marks
metadata-only content policy, keeps historical bootstrap tainted/propose-only
with runtime writes forbidden, marks writer policy/activation-gate
requirements, marks repair fail-closed routing, and names the canonical
create/improve/compose/decompose topology operation classes. This advances
Core Sections 26.3 and 28.1-28.2 plus Observatory Sections 12.3, 12.6, and
13.1 by making leased worker progress explainable through the existing
heartbeat/read-model surface without adding UI-local control authority.
Focused validation passed with the worker progress regressions (`2 passed, 38
deselected`) and targeted Ruff. Required gates also passed with full sidecar
Ruff, full pytest (`405 passed`), compileall, diff-check, core acceptance
(`70` implemented), Observatory acceptance (`86` satisfied), and conformance
(`14/14`). No compose/Postgres smoke was needed because the change only shapes
existing persisted heartbeat summaries and is covered through the in-memory
job store.

2026-06-06 update: Observatory broker decision collection rows now use a
content-safe read-model projection instead of spreading raw
`RetrievalLog.to_json()` payloads. The projection preserves stable retrieval
log identity, trace/span refs, policy refs, decision state, rendered/candidate
skill IDs, reason codes, validated query identity, and metadata key names while
hashing malformed query identity values, replacing raw session/turn IDs with
SHA-256 hashes, and withholding arbitrary retrieval metadata values such as raw
query text, candidate summaries, or suppression context. This advances Core
Section 11 plus Observatory Sections 7.6, 7.7,
12.6, 13.1, 16.1, and acceptance criteria 21.15, 21.16, and 21.30 by closing
the broker runtime aggregate-to-evidence path without adding UI-local authority
or changing the underlying retrieval log store. Focused validation passed with
the broker-decision and route-matrix Observatory API regressions (`2 passed, 60
deselected`) plus targeted Ruff. Required gates also passed with full sidecar
Ruff, full pytest (`403 passed`), compileall, generated OpenAPI client
freshness check, core acceptance (`70` implemented), Observatory acceptance
(`86` satisfied), and conformance (`14/14`). No compose/Postgres smoke was
needed because the change is a deterministic API projection over existing
retrieval log rows.

2026-06-06 update: Observatory scheduler job records now use a content-safe
read-model projection across collection, direct detail, and generic object
microscope paths. The previous admin job collection returned raw
`JobRecord.to_json()` dictionaries and the detail microscope embedded the raw
job dictionary in diagnostics; the new projection preserves stable
job/workspace/trace/span/status/timing fields, payload key names and payload
SHA-256, attempts, priority, and hashed idempotency/lease-owner references
while withholding raw payload values, raw idempotency keys, and raw lease-owner
strings. This advances Observatory Sections 7.6, 7.7, 12.6, 13.1, 16.1, and
acceptance criteria 21.16 and 24.27 by closing the scheduler/job read-model
content-policy seam without changing the public worker job API. Focused
validation passed with the job-microscope and route-matrix Observatory API
regressions (`2 passed, 60 deselected`) plus targeted Ruff. Required gates
also passed with full sidecar Ruff, full pytest (`403 passed`), compileall,
diff-check, core acceptance (`70` implemented), Observatory acceptance (`86`
satisfied), and conformance (`14/14`). No compose/Postgres smoke was needed
because the change is a deterministic API projection over existing scheduler
job rows.

2026-06-06 update: Observatory baseline comparison and diagnostic bundle
records now use content-safe read-model projections across collection,
create/detail, and generic object microscope paths. Persisted comparison
selectors, comparison summaries, difference lists, diagnostic bundle scopes,
manifests, storage URIs, actor IDs, audit details, and live-event references
are exposed as bounded scalar allowlists, key names, counts, and SHA-256 hashes
instead of raw caller-shaped dictionaries. This advances Observatory Sections
7.6, 7.7, 12.6, 13.1, 16.1, and acceptance criteria 21.35-21.36 by closing a
reverse-project read-model seam without adding UI-local mutation authority or
changing the underlying stores. Focused validation passed with the comparison,
diagnostic-bundle, and route-matrix Observatory API regressions (`3 passed, 59
deselected`) plus targeted Ruff. Required gates also passed with full sidecar
Ruff, full pytest (`403 passed`), compileall, diff-check, core acceptance
(`70` implemented), Observatory acceptance (`86` satisfied), and conformance
(`14/14`). No compose/Postgres smoke was needed because the change is a
deterministic API projection over existing Observatory admin store rows.

2026-06-06 update: Observatory diagnostic momentum records now have
sidecar-hosted, content-safe read-model routes and generic object microscope
coverage. The new `/admin/api/v1/diagnostics/momentum` collection/detail
surfaces use the existing Core diagnostic momentum store and expose stable IDs,
workspace/status/kind, issue signature hashes, evidence/contrastive/counter
counts, momentum/risk scores, timeline state, and skill/version/executor
provenance while withholding raw root-cause hypotheses and suggested repair
directions behind SHA-256 hashes and lengths. This advances Core Section 1.5
plus Observatory Sections 7.6, 7.7, 8.5, 12.6, 13.1, and 16.1 by making
recurring diagnostic evidence drillable without adding UI-local mutation
authority or returning raw correction/repair text. Focused validation passed
with the diagnostic-momentum and route-matrix Observatory API regressions (`2
passed, 59 deselected`) plus targeted Ruff. Required pre-commit gates also
passed with full sidecar Ruff, full pytest (`402 passed`), compileall,
Observatory frontend build, generated OpenAPI client freshness check,
diff-check, core acceptance (`70` implemented), Observatory acceptance (`86`
satisfied), and conformance (`14/14`). A compose/Postgres smoke applied
migrations against an isolated project, recorded one `user_correction`
diagnostic momentum row through `AsyncpgDiagnosticMomentumStore`,
list/detail-read it through the new methods, and removed the temporary compose
project/volume.

2026-06-06 update: Observatory governance transaction records now have direct
sidecar-hosted, content-safe read-model routes for evolution transactions,
deterministic writer transactions, and revocation requests. The new
`/admin/api/v1/evolution/transactions`, `/admin/api/v1/writer/transactions`,
and `/admin/api/v1/revocations/requests` collection/detail surfaces reuse the
existing object microscopes and expose bounded lifecycle state, timelines,
provenance, item summaries, manifest/rollback metadata, activation-defer
metadata, and traversal summaries while withholding raw idempotency keys,
transaction causes, generated skill text, rollback instructions, and raw
traversal payloads. This advances Core Sections 1.2, 9.6, 12.11, 23, 25, and
28.2 plus Observatory Sections 7.6, 7.7, 8.5.4, 12.6, 13.1, and 16.1 by
closing the rollback-complete governance aggregate-to-evidence path without
adding UI mutation authority. Focused validation passed with the writer,
revocation, and route-matrix Observatory API regressions (`3 passed, 57
deselected`) plus targeted Ruff. Required pre-commit gates also passed with
full sidecar Ruff, full pytest (`401 passed`), compileall, Observatory
frontend build, generated OpenAPI client freshness check, the core and
Observatory acceptance reports (`70` implemented, `86` satisfied), and the
conformance report (`14/14` checks, zero validation errors). No compose/Postgres
smoke was needed because no schema changed and the asyncpg path only adds
bounded reads over existing governance tables.

2026-06-06 update: Observatory semantic-autonomy evidence read models now use
content-safe microscopes across direct and generic API paths. Evidence-fidelity
status, semantic-adjudication status, and autonomy-decision status records
preserve their stable IDs and top-level state fields, but now also expose
read-model metadata, timeline, provenance/effects, deterministic admissibility
diagnostics, threshold-deadlock indicators, semantic-fidelity support flags,
and explicit raw-verdict/policy/context denial metadata. This advances Core
Sections 5.12-5.14 and 12.1-12.8 plus Observatory Sections 7.6, 7.7, 12.6, and
16.1 by closing semantic-decision aggregate-to-evidence paths without adding
UI-local authority or returning raw evidence, LLM verdict payloads, policy
payloads, or raw context. Focused validation passed with the autonomy/evidence
read-model and route-matrix Observatory API regressions (`2 passed, 58
deselected`) plus targeted Ruff. No compose/Postgres smoke was needed because
the slice only reshapes existing read-model records covered by the in-memory
Observatory admin store. Required pre-commit gates also passed with full
sidecar Ruff, full pytest (`401 passed`), compileall, Observatory frontend
build, generated OpenAPI client freshness check, diff-check, and the core,
Observatory, and conformance reports (`70` implemented, `86` satisfied,
`14/14` checks, zero validation errors).

2026-06-06 update: Observatory autonomy threshold policies now have a
sidecar-hosted, content-safe read model and object microscope path. The broker
policy store exposes bounded policy-version listing, admin routes expose
`/admin/api/v1/autonomy/policies` and
`/admin/api/v1/autonomy/policies/{policy_id}`, generated Observatory route
metadata includes those paths, and generic object aliases resolve
`threshold_policy`, `calibration_policy`, and broker-policy refs. The read
model exposes lifecycle state, policy version/status, SHA-256 policy identity,
top-level policy keys, bounded numeric/bool scalar thresholds, replay/canary
feedback key names, reason hashes, and explicit hard-invariant non-relaxation
flags while withholding arbitrary policy values, canary reason text, and raw
policy payloads. This advances Core Sections 5.8, 5.10, and 5.14 plus
Observatory Sections 12.1, 12.6, 16.1, and acceptance criterion 21.23 by
making threshold/calibration policy versions inspectable without adding
UI-local mutation authority or weakening deterministic hard gates. Focused
validation passed with the threshold-policy and route-matrix Observatory API
regressions (`2 passed, 58 deselected`) and targeted Ruff. Required
pre-commit gates also passed with full sidecar Ruff, full pytest (`401
passed`), compileall, Observatory frontend build, generated OpenAPI client
freshness check, diff-check, and the core, Observatory, and conformance reports
(`70` implemented, `86` satisfied, `14/14` checks, zero validation errors). No
compose/Postgres smoke was needed because the schema already stores broker
policy versions and this slice adds read/list shaping covered by the in-memory
broker policy store.

2026-06-06 update: Observatory context token ledgers now have a
sidecar-hosted, content-safe read model and object microscope path. The context
governance store exposes bounded list/detail reads for existing
`context_token_ledgers`, admin routes expose `/admin/api/v1/context/token-ledgers`
and `/admin/api/v1/context/token-ledgers/{ledger_id}`, and generic object
aliases resolve token-ledger rows with visibility state, token count, outcome,
artifact/skill/policy refs, marginal-value metrics, metadata key names, and
session/turn SHA-256 hashes while withholding raw session IDs, turn IDs, and
metadata values. This advances Core Sections 11.12-11.14 plus Observatory
Sections 7.6, 7.7, 12.1, 12.6, and acceptance criterion 21.20 by making
context-value-per-token evidence inspectable without UI-local authority or raw
runtime context exposure. Focused validation passed with the context compiler
and route-matrix Observatory API regression (`2 passed, 57 deselected`),
targeted Ruff, and the generated OpenAPI client freshness check. Required
pre-commit gates also passed with full sidecar Ruff, full pytest (`400
passed`), compileall, Observatory frontend build, diff-check, and the core and
Observatory acceptance reports (`70` implemented, `86` satisfied, zero
validation errors). No compose/Postgres smoke was needed because no schema
changed and the API shaping is covered through the in-memory context governance
store.

2026-06-06 update: Observatory live outbox redaction metadata is now
Core-owned. The sanitizer drops caller-supplied `redacted_payload_keys` and
`redacted_payload_hashes` while appending events, preserves stored sanitizer
metadata only after strict key/hash validation during serialization, and keeps
computed hashes/key lists for redacted values. This advances Observatory
Sections 12.3, 16.1, and 17.2 plus acceptance criteria 21.11, 21.30, and
21.31 by closing a reserved-metadata covert channel in WebSocket/SSE payloads
without adding UI-local policy authority. Focused validation passed with the
forged-metadata live-SSE regression (`1 passed, 58 deselected`), the
surrounding live-SSE route tests (`6 passed, 53 deselected`), and targeted
Ruff. Required pre-commit gates also passed with `uv run ruff check sidecar`,
`uv run pytest` (`400 passed`), `uv run python -m compileall -q sidecar`, and
`git diff --check`. No compose/Postgres smoke was needed because the
deterministic sanitizer is shared by the in-memory and asyncpg admin stores.

2026-06-06 update: Observatory live-stream outbox payloads are now sanitized at
the Core store/serialization boundary. `AdminLiveEventRecord.to_json`, the
in-memory admin store, and the asyncpg admin store preserve bounded primitive
status fields and reason codes while replacing nested or sensitive/content
payload fields with per-key SHA-256 hashes, key lists, payload hash identity,
and explicit `content_policy` metadata. This advances Observatory Sections
12.3, 12.6, 16.1, and 17.2 plus acceptance criteria 21.11, 21.30, and 21.31 by
making WebSocket/SSE deltas policy-safe even if a future caller accidentally
passes raw notes, prompts, nested content, or secrets. Focused validation passed
with the live-SSE regression (`6 passed, 53 deselected`) and targeted Ruff.
Required pre-commit gates also passed with full sidecar Ruff, full pytest (`400
passed`), compileall, and diff-check. No compose/Postgres smoke was needed
because the slice only hardens the live-event read boundary and validates it
through the in-memory admin store plus browser-facing SSE route.

2026-06-06 update: Observatory administrative escalations now have a
content-safe object microscope over the Core admin read model. The
administrative-escalation list, direct detail route, and generic
`/admin/api/v1/objects/administrative_escalation/{event_id}` path now return
hard-boundary category, decision family, stable target refs, timeline,
provenance, operator-safe action/status summaries, alternative payload hashes,
alternative key names, and explicit raw-denial metadata while suppressing
arbitrary attempted-alternative reason text and payload content. This advances
Observatory Sections 7.6, 7.7, 8.5.3, 8.21, 12.6, and 16.1 by closing the
administrative-escalation aggregate-to-evidence path without adding mutation
authority or browser-side security assumptions. Focused validation passed with
the autonomy/evidence read-model regression (`1 passed, 57 deselected`) and
targeted Ruff. Required pre-commit gates also passed with full sidecar Ruff,
full pytest (`399 passed`), compileall, and diff-check. No compose/Postgres
smoke was needed because the slice only reshapes an existing admin read model
and validates it through the in-memory Observatory admin store.

2026-06-06 update: Observatory audit records now have a content-safe object
microscope over the Core audit store. `/admin/api/v1/audit` returns bounded
audit metadata instead of arbitrary raw `details`, and generic
`/admin/api/v1/objects/audit_record/{audit_id}` resolves stable audit IDs,
actor hashes and subject refs, hash-chain links, primitive counters/flags, detail key
names, and hashes for non-scalar detail values while suppressing raw operator
notes, request payloads, secrets, and private prompt fragments. This advances
core Sections 28.2-28.3 plus Observatory Sections 8.20, 12.6, 13.1, and 16.1
by closing the audit aggregate-to-evidence path without adding mutation
authority or browser-side security assumptions. Validation passed with focused
audit microscope coverage (`2 passed, 56 deselected`), targeted and full
sidecar ruff, full `uv run pytest` (`398 passed`), compileall, and diff-check
gates. No compose/Postgres smoke was needed because the slice only reshapes the
existing audit read path and validates it through the in-memory audit store.

2026-06-06 update: Observatory station catalog coverage now includes the
Part II autonomy/adjudication workcell as a first-class overview subsystem.
The runtime station map and SQL seed expose raw-vault, evidence-fidelity,
semantic-adjudication, autonomy-orchestrator, replay-corpus, and
administrative-escalation stations, and quality gates now include the replay
corpus station as required by the unified spec. Focused validation passed with
the Observatory summary regression covering 30 stations and 9 subsystems.

2026-06-06 update: Historical bootstrap consolidation now emits propose-only
topology recommendations from historical evidence. Historical payloads can
contribute guarded `improve`, `compose`, and `decompose` recommendations with
support counts, outcome counts, sequence/context-pressure signals, token-waste
metadata, taint/source metadata, and deterministic blockers when support or
topology prerequisites are insufficient. The readout explicitly marks
historical evidence as non-activating and forbids runtime file writes, advancing
Core historical ingestion, topology operations, evidence maturity, and safety
ordering without adding autonomous apply authority. Focused validation passed
with historical bootstrap coverage (`7 passed`), targeted ruff, and diff-check
gates.

2026-06-06 update: Observatory component metrics now have a generic object
microscope alias. `/admin/api/v1/objects/component_metrics/{component}` and
station-metrics aliases reuse the same bounded read model as
`/admin/api/v1/components/{component}/metrics`, exposing signal contracts,
bounded records, component diagnostics, provenance, and raw-content denial
without direct SQL/log inspection or UI-local authority. This advances the
Observatory aggregate-to-evidence drill-down contract for station cockpits and
object microscopes. Validation passed with focused generic-object coverage
(`1 passed, 56 deselected`), targeted ruff, and diff-check gates.

2026-06-06 update: Observatory opportunity mining now has a sidecar-hosted,
content-safe admin read model. `/admin/api/v1/opportunities` derives bounded
opportunity candidates through the existing deterministic miner, and generic
`opportunity`/`candidate_opportunity` object aliases expose support counts,
recommendation, evidence refs, duplicate-search decisions and match counts,
candidate slug, and description hashes while suppressing raw evidence, raw match
summaries, and the derived candidate description; the admin path does not create
candidate records, activation side effects, or retrieval-log rows. This advances core Sections
13.2-13.8 and 18.1-18.5 plus Observatory Sections 7.6, 7.7, 8.8, 12.1, 12.6,
13.1, and 16.1 by closing the opportunity-mining aggregate-to-evidence path
without adding UI-local candidate creation, activation, or autonomous apply
authority. Validation passed with focused opportunity/admin route coverage,
generated OpenAPI client refresh and `--check`, full sidecar ruff/pytest
(`391 passed`)/compileall gates, Observatory frontend build, compose config,
diff-check, and an isolated compose/Postgres smoke that migrated a fresh
database, verified non-recording lexical opportunity lookup creates no workspace
or retrieval-log rows for a missing workspace, verified normal recorded lexical
retrieval still creates one workspace and one retrieval-log row, and removed the
temporary compose project/volume.

2026-06-06 update: Observatory model/embedding profile qualification runs now
have content-safe object microscopes. `ProfileQualificationStore` can fetch
individual text-model and embedding qualification runs by workspace/run ID, and
generic `model_profile_qualification_run`, `profile_qualification_run`, and
`embedding_profile_qualification_run` object aliases expose deterministic
check outcomes, bounded scalar metrics, profile refs, optional LLM invocation
refs, verdicts, probe-set versions, timestamps, and raw-denial metadata while
suppressing raw probe payloads, endpoint refs, API keys, raw provider errors,
and cost analytics. This advances core Sections 2.40-2.41 and 3.3 plus
Observatory Sections 1.5, 1.9, 5.1, 7.3, 8.18, 12.6, 16.1, and
21.16/21.26/21.40 by making qualification-gate evidence directly traversable
without adding UI-local model authority. Validation passed with focused
Observatory/profile qualification coverage, full sidecar ruff/pytest
(`390 passed`)/compileall gates, compose config, diff-check, core and
Observatory acceptance reports (`70` implemented, `86` satisfied, `0`
validation errors), and an isolated compose/Postgres smoke that migrated a
fresh database, recorded/detail-read one text-model and one embedding
qualification run through `AsyncpgProfileQualificationStore`, verified
workspace isolation, and removed the temporary compose project/volume.

2026-06-06 update: Observatory historical import source records now use a
content-safe source microscope. `/admin/api/v1/historical/imports`,
`/admin/api/v1/historical/imports/{historical_import_id}`, and generic
`historical_import`, `historical_import_source`, and `historical_source`
object aliases expose source IDs, source kind, parser/redaction versions,
trust/status, taint and metadata key names, timestamps, and source
key/fingerprint hashes while suppressing raw source locators, arbitrary
metadata values, taint values, and raw historical content. This advances core
Sections 14.1-14.5 and 14.12 plus Observatory Sections 8.2, 12.1, 12.6, 16.1,
21.16, 21.21, 21.30, and 21.40 by making historical-ingestion evidence
drill-downs policy-safe at the sidecar API boundary. Validation passed with
focused Observatory API coverage, full sidecar ruff/pytest/compileall gates,
compose config, diff-check, and core and Observatory acceptance reports (`63`
production criteria, `7` context criteria, `42` Observatory criteria, `44`
checklist items, ready=true). No compose/Postgres smoke was needed because the
slice only reshapes the existing historical import read path and validates it
through in-memory route coverage.

2026-06-06 update: Observatory canary results now have content-safe lifecycle
read models and drill-down routes. `AsyncpgLifecycleStore` can list and detail
read canary results with workspace filtering, and
`/admin/api/v1/canary/results`,
`/admin/api/v1/canary/results/{canary_result_id}`, plus generic
`canary_result`/`canary` object-microscope aliases expose status, criticality,
skill, skill-version, evolution-transaction refs, metric keys with
numeric/boolean values, and reason/metrics hashes while suppressing raw reason
text and arbitrary metric strings. This advances core Sections 1, 1.2, 23, 25,
and 28.2 plus Observatory Sections 1.5, 7.6, 8.5.4, 8.16, 12.6, 13.1, 16.1,
21.16, 21.22, 21.23, and 21.40 by closing the canary/freeze
aggregate-to-evidence path without adding UI-local mutation authority.
Validation passed with focused canary/route coverage, refreshed/generated
OpenAPI client checks, full sidecar ruff/pytest/compileall gates, Observatory
frontend build, compose config, diff-check, core and Observatory acceptance
reports (`70` implemented, `86` satisfied, `0` validation errors), and an
isolated compose/Postgres smoke that migrated a fresh database, seeded a
FK-backed skill row, recorded/listed/detail-read a canary result through
`AsyncpgLifecycleStore`, verified workspace isolation, and removed the
temporary compose project/volume.

2026-06-05 update: Observatory skill, skill-version, and candidate records now
have generic object-microscope drill-downs backed by the existing skill and
candidate read stores. Shared content-safe payload builders align the dedicated
skill/candidate detail routes with generic `skill`, `skill_version`, and
`candidate` object aliases, expose lifecycle state, scanner/evaluator status,
manifest-hash metadata, active-version links, candidate transaction refs, and
safe provenance, and explicitly withhold raw SkillIR plus compiled runtime text.
This advances core Sections 1, 1.2, 1.5, 13, 17, 23, and 28.2 plus Observatory
Sections 7.6, 7.7, 8.9, 8.10, 9.1-9.3, 12.6, 13.1, and 21.16 by closing the
skill-library/candidate aggregate-to-evidence path without adding UI-local
mutation authority. Validation passed with focused skill/candidate/schedule
microscope coverage, full sidecar ruff/pytest/compileall gates, compose config,
diff-check, and core and Observatory acceptance reports (`70` implemented, `86`
satisfied, `0` validation errors). No compose/Postgres smoke was needed because
the slice only reuses existing read stores and validates them through in-memory
route coverage.

2026-06-05 update: Observatory storage/read-model health now has a dedicated
content-safe storage microscope. `/admin/api/v1/storage` returns a storage
object with relation counts, table/index/total byte summaries, estimated rows,
largest relation metadata, read-model freshness, index-health status, explicit
migration/retention telemetry gaps, and action/invariant links while withholding
connection details, raw SQL, and database content. Generic `storage`,
`storage_db`, and `db_health_report` object aliases resolve the same bounded
storage microscope. This advances core Sections 28.2-28.3 plus Observatory
Sections 7.6, 7.7, 8.19, 12.6, 13.1, and 21.25 by closing the storage cockpit
aggregate-to-evidence path without adding storage mutation authority. Validation
passed with focused storage microscope coverage, full sidecar ruff/pytest/
compileall gates, compose config, diff-check, and core and Observatory
acceptance reports (`70` implemented, `86` satisfied, `0` validation errors).
No compose/Postgres smoke was needed because the slice only shapes existing
operator storage metrics and validates them through in-memory snapshot/API
coverage.

2026-06-05 update: Observatory schedule records now have content-safe
drill-down evidence. `/admin/api/v1/schedules` returns redacted schedule admin
records with stable IDs, cadence, enabled state, misfire policy, payload key
names, and payload hash identity, while withholding raw schedule payloads. The
generic `/admin/api/v1/objects/schedule/{id}` and `scheduler_schedule` alias
resolve the same schedule microscope through the existing scheduler store. This
advances core Sections 26.2-26.4 plus Observatory Sections 7.6, 7.7, 8.17,
12.6, 13.1, and 16.1 by closing the scheduler aggregate-to-evidence path
without adding UI-local scheduler authority or exposing raw job payload content.
Validation passed with focused schedule/job microscope coverage, full sidecar
ruff/pytest/compileall gates, compose config, and core and Observatory
acceptance reports (`70` implemented, `86` satisfied, `0` validation errors).
No compose/Postgres smoke was needed because the slice only reshapes the
existing scheduler read path and validates it through an in-memory scheduler
store.

2026-06-05 update: Observatory generic object microscopes now resolve
sidecar scheduler job refs through the same bounded job read model used by
`/admin/api/v1/jobs/{job_id}`. The generic
`/admin/api/v1/objects/job/{id}` and `scheduler_job` alias now return the
content-policy-safe job microscope with scheduler diagnostics and trace/span
provenance links instead of falling back to the snapshot `read-model-missing`
placeholder. This advances core Sections 26.2-26.3 and 28.2 plus Observatory
Sections 1.9, 21.16, 21.27, and 24.27 by closing the drill-down path from
audited rollback/revocation job refs to scheduler evidence without adding UI
mutation authority. Validation passed with focused job microscope coverage,
`uv run ruff check sidecar`, `uv run pytest` (`380 passed`), `uv run python -m
compileall -q sidecar`, `docker compose config --quiet`, `git diff --check`,
and core and Observatory acceptance reports (`ready=true`, `70` implemented,
`86` satisfied, `0` validation errors). No compose/Postgres smoke was needed
because this slice only aliases an existing scheduler read model and validates
it through an in-memory job store.

2026-06-05 update: Observatory artifact drill-downs now resolve UUID-backed
compiled/context artifacts through the governed context-artifact read model
instead of leaving the broader `/admin/api/v1/artifacts/{id}` and generic
`/admin/api/v1/objects/artifact/{id}` surfaces as dead-end placeholders.
The artifact aliases expose artifact kind, source object refs, token budget
status, safety/equivalence/shadowing status, hashes, and redacted metadata-key
summaries while preserving the existing explicit missing-read-model response
for non-UUID or unsupported artifact records. This advances core Section 1.4
context-management gates plus Observatory Sections 7.6, 7.7, and 8.12 by
closing the aggregate-to-evidence path for context artifact contributors
without returning compiled text or adding UI-local mutation authority.
Validation passed with focused context-compiler read-model coverage, `uv run
ruff check sidecar`, `uv run pytest` (`379 passed`), `uv run python -m
compileall -q sidecar`, `docker compose config --quiet`, `git diff --check`,
and core and Observatory acceptance reports (`ready=true`, `70` implemented,
`7` context criteria, `86` Observatory criteria/checklist items satisfied, `0`
validation errors). No compose/Postgres smoke was needed because the slice
reuses the existing context-governance read path and validates it through the
in-memory context store.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `trace` path backed by the observability store.
`/admin/api/v1/objects/trace/{trace_id}` resolves the same ordered trace detail
as `/admin/api/v1/traces/{trace_id}`, including span timeline, downstream
object refs, operation/status summaries, and raw-span denial metadata. This
advances core Sections 28.2 and 28.3 plus Observatory Sections 7.6, 7.7, 8.20,
12.6, 16.1, and 21.16 by closing the drill-down gap from emitted trace refs to
governed sidecar evidence without replaying work or adding UI-local mutation
authority. Validation passed with focused trace/object microscope coverage,
full sidecar ruff/pytest/compileall gates, compose config, diff-check, and core
and Observatory acceptance reports. No compose/Postgres smoke was needed
because the slice only reuses the existing observability-store read path and
validates it through the in-memory trace store.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `writer_transaction` path backed by governance evolution
transactions. `/admin/api/v1/objects/writer_transaction/{id}` resolves
deterministic writer apply/rollback evidence, including manifest hash, active
relative path, file count, previous snapshot pointer, staged manifest path,
activation deferral/window state, bounded transaction items, rollback operation
names, and audit links. Raw metric payloads, raw activation-window notes, raw
idempotency/cause text, raw generated skill text, and arbitrary rollback
instructions remain unavailable. This advances core Sections 1.2, 25, and 28.2
plus Observatory Sections 7.6, 7.7, 8.15, 12.6, 13.1, and 16.1 by closing the
drill-down gap from deterministic writer transactions to governed sidecar
evidence without adding UI-local mutation authority. Validation passed with
focused writer/evolution microscope coverage, full sidecar ruff/pytest/
compileall gates, compose config, diff-check, and core and Observatory
acceptance reports. No compose/Postgres smoke was needed because the slice only
adds a content-safe read-model alias over existing governance transaction
lookups.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `revocation_request` path backed by the governance store.
`/admin/api/v1/objects/revocation_request/{id}` resolves rollback/revocation
request status, root object, created-by job, bounded impacted objects, bounded
provenance edges, rollback transaction refs, and numeric/boolean invalidation
counters while suppressing raw traversal metadata, raw operator/source text,
raw generated skill text, raw provenance notes, and arbitrary invalidation
strings. This advances core Sections 1.2 and 2.26 plus Observatory Sections
7.6, 7.7, 8.16, 12.6, 13.1, and 16.1 by closing the drill-down gap from
rollback/freeze derived-state revocation to governed sidecar evidence.
Validation passed with focused revocation/evolution microscope coverage,
focused worker/governance revocation coverage, full sidecar ruff/pytest/
compileall gates, compose config, diff-check, core and Observatory acceptance
reports, and an isolated compose/Postgres smoke that migrated a fresh database
and round-tripped a rollback revocation request through the asyncpg governance
lookup with workspace filtering.

2026-06-05 update: Observatory scanner findings now have a dedicated
content-safe detail read model. The scanner station emits a stable
`scanner_finding` object for scanner reject counts, and
`/admin/api/v1/scanner-findings/{finding_id}` plus the generic
`/admin/api/v1/objects/scanner_finding/{id}` microscope expose component
health, reason codes, data quality, bounded gate counts, scanner-gate
provenance, and the downstream `gates-cover-writer-activation` invariant
without raw artifact or skill content. This advances core Section 24
scanner/security diagnostics plus Observatory Sections 7.6, 7.7, 8.13, 12.1,
12.6, 13.1, and 16.1 by closing the scanner-pressure aggregate-to-evidence
drill-down path. Validation passed with focused scanner microscope coverage,
generated OpenAPI client `--check`, full sidecar ruff/pytest/compileall gates,
compose config, diff-check, and core and Observatory acceptance reports. No
compose/Postgres smoke was needed because the slice only shapes the existing
snapshot-backed scanner read model.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `evaluation`/`evaluation_run`/`probe_evaluation` path backed by
the evaluator read model. `/admin/api/v1/objects/evaluation/{id}` resolves the
same evaluation/probe autonomy-assurance detail as
`/admin/api/v1/evaluations/{id}`, including hard-invariant failures,
soft-threshold misses, autonomous fallback actions, policy-blocked actions,
skill-version provenance, and raw-content denial metadata. This advances core
Section 23 evaluator/probe acceptance behavior plus Observatory Sections 7.6,
7.7, 8.14, 12.6, 21.16, and 21.22 by closing the drill-down gap from
evaluation/probe aggregates to governed sidecar evidence. Validation passed
with focused Observatory evaluation microscope coverage, full sidecar
ruff/pytest/compileall gates, compose config, diff-check, and core and
Observatory acceptance reports. No compose/Postgres smoke was needed because
the slice reuses the existing evaluator-store read path and validates it
through the in-memory evaluation store.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `broker_decision`/`retrieval_log` path backed by the retrieval
store. `/admin/api/v1/objects/broker_decision/{id}` resolves the same broker
decision detail as `/admin/api/v1/broker/decisions/{id}`, including decision
timeline, trace link, rendered/candidate skill effects, bounded candidate refs,
safe suppression refs, reason codes, query hash identity, and broker policy
identity. Raw retrieval query text, raw candidate summaries, raw suppression
context, and arbitrary metadata values remain unavailable. This advances core
Sections 7-8 runtime-broker/sidecar requirements plus Observatory Sections 7.6,
7.7, 8.7, 8.20, 12.6, 16.1, and 21.16 by closing the drill-down gap from
broker-quality aggregates and replay-episode provenance refs to retrieval-log
evidence. Validation passed with focused broker-decision microscope coverage,
focused ruff checks, full sidecar ruff/pytest/compileall gates, diff-check,
compose config, and core and Observatory acceptance reports. No compose/Postgres
smoke was needed because the slice reuses the existing retrieval-store read path
and validates it through the in-memory retrieval store.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `action_attribution_check` detail path backed by the attribution
store. `/admin/api/v1/objects/action_attribution_check/{id}` resolves the
deterministic operator-action boundary check behind admin action receipts,
including verdict, risk tier, hashed user intent and idempotency identity,
reason codes, target refs, bounded contributing object refs, broker-policy
refs, and source-presence flags. Raw operator reason text, confirmation text,
metadata values, raw IP/proxy values, and arbitrary metric payloads remain
unavailable. This advances core Sections 1.2, 27, and 28.2 plus Observatory
Sections 7.6, 7.7, 8.20, 8.22, 12.6, 16.1, and 16.3 by closing the drill-down
gap from administrative actions to their deterministic attribution checks.
Validation passed with focused action-attribution microscope coverage, broader
Observatory action/attribution tests, full sidecar ruff/pytest/compileall gates,
compose config, core and Observatory acceptance reports, diff-check, and an
isolated compose/Postgres smoke that migrated a fresh database and round-tripped
an action-attribution check lookup with workspace filtering through the asyncpg
store.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `llm_invocation` detail path backed by the LLM invocation store.
`/admin/api/v1/objects/llm_invocation/{id}` resolves purpose, model/profile
route identity, thinking fallback state, token estimates, status, trace/span
refs, and allowlisted endpoint/finish metadata while hashing provider request
and error identity. Raw provider errors, prompt/response text, API keys,
endpoint URLs, arbitrary audit payloads, and cost analytics remain unavailable.
This advances core Sections 3.2.7, 3.3, 5.12, 13.8.12, and 28.2 plus
Observatory Sections 7.6, 7.7, 8.18, 12.6, 13.1, 16.1, and 16.3 by making
model/embedding profile qualification refs traversable through sidecar-hosted
audit evidence. Validation passed with focused profile/invocation microscope
coverage, broader Observatory/LLM/profile tests, full sidecar
ruff/pytest/compileall gates, compose config, core and Observatory acceptance
reports, diff-check, and an isolated compose/Postgres smoke that migrated a
fresh database and round-tripped an LLM invocation through the asyncpg store
lookup with workspace filtering.

2026-06-05 update: Observatory model and embedding profile-detail
read models now expose content-safe qualification evidence. The profile
qualification store can list recent model/embedding qualification runs by
workspace/profile key, and `/admin/api/v1/model-profile/{profile_key}`,
`/admin/api/v1/embedding-profile/{profile_key}`, plus the generic object
microscope aliases return redacted effective configuration, route/status
metadata, latest verdict pointers, allowlisted checklist outcomes, safe token
and embedding sanity metrics, and LLM invocation refs. Raw endpoint URLs, API
keys, raw probe errors, prompt/response text, provider payloads, and cost
analytics stay unavailable. This advances core Phase 4 profile qualification and
invocation-audit requirements plus Observatory Sections 7.6, 7.7, 8.18, 12.1,
12.6, 13.1, 16.1, and 16.3. Validation passed with focused profile microscope
coverage, broader Observatory/profile tests, generated OpenAPI client `--check`,
full sidecar ruff/pytest/compileall gates, compose config, core and Observatory
acceptance reports, diff-check, and an isolated compose/Postgres smoke that
migrated a fresh database and round-tripped model/embedding qualification run
reads through the asyncpg stores.

2026-06-05 update: Observatory object microscopes now include a dedicated
content-safe `evolution_transaction` detail path backed by the governance
store. `/admin/api/v1/objects/evolution_transaction/{id}` resolves transaction
status, timeline, source evidence/memory refs, downstream transaction items,
rollback-operation names, hashed idempotency identity, policy keys, and
allowlisted topology/data-to-skill metrics without exposing raw cause text, raw
metric payloads, raw evidence, or arbitrary rollback payload text. This advances
core Sections 1.2, 17.1, 28.2, and 28.3 plus Observatory Sections 7.6, 7.7,
11.1, 12.6, 13.1, 16.1, and 16.3 by closing a transaction-level drill-down gap
from topology review links to governance/audit evidence. Validation passed with
focused Observatory API tests, full sidecar ruff/pytest/compileall gates, compose
config, core and Observatory acceptance reports, diff-check, and an isolated
compose/Postgres smoke that migrated a fresh database and round-tripped a
topology transaction plus transaction item through `AsyncpgGovernanceStore`.

2026-06-05 update: topology proposal persistence now stamps a content-safe
data-to-skill trace capsule into the governing `topology_*`
`evolution_transactions.metrics` row. The trace records stage status, reason
codes, bounded object refs, terminal stage, and safe non-skill failure exits for
the candidate-to-trial/transaction portion of the bridge, while keeping raw
evidence, SkillIR/SkillGraphIR bodies, skill text, and operator content out of
metrics. `/admin/api/v1/topology` exposes the trace through an allowlisted
transaction-review read model and strips arbitrary raw fields. This advances
core Sections 1.2, 13.8.10-13.8.12, and 17 plus Observatory Sections 7.6, 7.7,
8.9, 8.10, 12.6, 13.1, and 16.1. Validation passed with focused trace
persistence/read-model tests, full sidecar ruff/pytest/compileall gates,
compose config, core and Observatory acceptance reports, diff-check, and a real
compose/Postgres smoke that persisted a compose proposal through asyncpg stores
and read the trace back through authenticated `/admin/api/v1/topology`.

2026-06-05 update: Observatory topology review now consumes the topology
transaction capsule persisted on `evolution_transactions.metrics`.
`/admin/api/v1/topology` combines operation/trial metrics from the topology
store with a bounded `topology_*` transaction-review section from the
governance store. The response exposes only transaction IDs, status, plan hash,
operation/status, evidence and trial counts, graph shape, effect coverage,
rollback readiness, write-target metadata, and the trial-before-apply invariant;
raw plan text, evidence text, skill bodies, and operator content remain
unavailable. This advances core Sections 1.2, 1.3, 9.6, 9.7, 13.7-13.8, and 17
plus Observatory Sections 7.7, 8.9, 12.1, 12.6, 13.1, and 16.1.

2026-06-05 update: topology proposal persistence now stamps a content-safe
transaction review capsule onto the governing evolution transaction. The
metrics summarize operation kind/status, plan hash, evidence count, planned
trial kinds, graph node/edge shape, effect coverage, rollback readiness, write
targets, and the trial-before-apply invariant without copying evidence text,
skill bodies, or raw operator-facing content into transaction metrics. This
deepens the core Sections 13.7-13.8 and 17 topology-operation bridge and gives
the Observatory topology cockpit a transaction-scoped control-plane summary for
candidate/trial review.

2026-06-05 update: Observatory administrative actions now create a deterministic
action-attribution boundary check before the normal audit/action receipt. The
admin action route stores only content-safe causality metadata: request id, risk
tier, policy verdict, reason codes, source identity, target identity, and hashed
intent/idempotency values. Receipts and action microscopes expose the resulting
`action_attribution_check` link, and `/admin/api/v1/actions/summary` reports
attribution-check coverage plus blocked-check counts. This advances the core
Section 1.2 action-attribution gate and Observatory Sections 1.9/16.3 without
adding a UI-local control plane or exposing raw reason, confirmation, or content
payloads.

2026-06-05 update: Observatory administrative action gateway summaries are now
first-class sidecar read models. `/admin/api/v1/actions/summary` derives a
content-safe cockpit aggregate from bounded `admin_action_audit` receipts,
including accepted/rejected counts by action kind, linked audit/job counts,
confirmation failures, role-policy failures, raw-content reveal outcomes,
high-impact action history, and explicit data-quality limits. New receipts
persist redacted `reason_codes` and confirmation-required metadata so the
summary can explain policy blocks without storing confirmation text or raw
content. This advances Observatory Sections 4.3, 8.22, 12.1, 12.6, 13.1, and
16.3 without adding action authority outside the audited sidecar gateway.

2026-06-05 update: Observatory guarded action idempotency now replays existing
content-safe action receipts before writing new action-audit or live-event side
effects. The admin action route stores a redacted request fingerprint, looks up
existing `admin_action_audit` rows by actor/action/target/idempotency key, and
reports `idempotency-replay` plus `idempotency-collision` metadata for divergent
retries without exposing confirmation text or raw content. This tightens the
Observatory administrative action gateway for Sections 4.3, 8.22, 16.3, and
16.4 while preserving sidecar-hosted policy/audit authority.

2026-06-05 update: Observatory split-container serving is now first-class in the implementation ledger and runtime contract. The Core FastAPI container owns internal `/v1` APIs only in the reference deployment; the separate Observatory FastAPI container owns the compiled React app, `/admin` browser entrypoint, `/admin/api`, `/admin/live`, and `/admin/live-sse` surfaces. The legacy core static mount and `sidecar` local-development static-serving mode were removed so development and production both validate UI changes through the same rebuild/redeploy path.

2026-06-04 update: the authoritative main and Observatory specs were refreshed. Acceptance crosswalks were expanded to the current main criteria (`31.1`-`31.63` plus context criteria) and Observatory criteria/checklist (`21.1`-`21.42`, `24.auto.1`-`24.auto.6`, `24.1`-`24.38`). The newly exposed replay-corpus gap is closed by `/v1/broker/replay-episodes/synthesize`: it records pre-adjudicated redacted telemetry, can synthesize a redacted intent through the configured text LLM from content-safe retrieval context, repairs stale telemetry-derived episode expectations from source retrieval logs, stores deterministic validation/provenance, and returns explicit hash-only/metadata-only/no-safe-context skip reasons instead of treating degraded evidence as full-autonomy replay support. Live Dev-01 validation synthesized/repaired telemetry-derived episodes and replayed the stored corpus at 19/19 matches.

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
  bounded self-validating JSONL spool records, with replay failure isolated from
  the already-forwarded current event;
- normal spool records carry checksum/idempotency metadata, raw retry records are
  encrypted with short-retention metadata when raw capture is configured, and
  tampered/expired wrapped records are tombstoned;
- concurrent capture appends all failed events to the bounded spool;
- actual hook handlers import and forward redacted envelopes in the local smoke fixture.

## Phase 3 - Scheduler and Job Queue

Deliverables:

- sidecar-owned schedules;
- jobs, attempts, leases, idempotency keys;
- job trace context; implemented with enqueue-supplied or generated `trace_id`/`span_id`, non-null persisted job trace/span roots, scheduled-job trace generation, and trace-preserving job JSON responses.
- worker pools; implemented as explicit scheduler, ingest, backfill, embedding, retrieval, analysis, LLM-generation, scanner, evaluation, filesystem, and maintenance run-once dispatch, bounded loop entrypoints, configured per-pool loop concurrency, persistent worker heartbeats, content-safe single-job progress phases, and worker health summaries.

Acceptance:

- jobs survive restart;
- duplicate ticks do not duplicate jobs; implemented with schedule-run idempotency keys;
- stuck leases recover; implemented for expired leases with remaining attempts;
- failed attempts back off and terminally fail at `max_attempts`;
- maintenance worker can claim and complete deterministic evidence/embedding jobs.
- worker loop supports bounded/configured concurrency, persistent heartbeat observation, and graceful process shutdown.
- queued, leased, renewed, completed, API-enqueued, and scheduled jobs carry trace/span context; implemented and validated with focused tests plus compose/Postgres smoke coverage.
- job health summaries are workspace-scoped where the caller supplies a
  workspace and ignore stale failed rows once a later job with the same
  workspace/job kind has succeeded, preserving current failures without leaving
  recovered backlog runs as false blocked signals.

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
- deployment bootstrap root resolution; implemented so worker startup resolves
  explicit historical roots first, otherwise falls back to existing bounded
  OpenClaw state subroots plus the configured workspace root, and the local
  compose path mounts OpenClaw state read-only instead of treating `/workspace`
  as the import universe.

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
- worker default discovery/import scheduling now uses bounded deployment-level
  limits for historical bootstrap over mounted OpenClaw state roots, with
  recurring evidence, embedding, parse, and consolidation payloads sized for
  aggressive Dev-01 backlog processing while preserving explicit root overrides
  and avoiding raw path persistence;
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
- activation gate; implemented for queued filesystem-worker apply and direct writer apply when requested, requiring the staged manifest skill version to have passed scanner/evaluator/proposal-gate checks and requiring any supplied executor profile to be compatible before active-root exposure;
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
- filesystem-worker rollback revocation execution; implemented for queued rollback revocation
  requests whose originating transaction recorded an archive-backed compiled-file rollback
  action or an initial-create active-path deletion rollback action.
- rollback revocation trace spans; implemented as content-safe filesystem-worker `rollback`
  operation spans that close with bounded counts and job/revocation-request refs, while
  DB-backed observability tolerates missing caller parent spans instead of failing rollback
  workers.
- rollback-derived invalidation; implemented for traversal-summary impacted objects by deleting
  matching body-index documents and embeddings, marking retrieval/context/topology/evaluator
  derived state revoked or rolled back, revoking matching attribution records, marking
  impacted active skills `revoked`, revoking connected skill graph edges, and revoking
  matching evidence-maturity rows during filesystem-worker rollback completion.
- topology downstream apply trace spans; implemented as content-safe filesystem-worker
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
- filesystem-pool `revocations.rollback` jobs claim queued rollback revocation requests, start an idempotent `rollback_skill` transaction, restore the recorded archive manifest through the transaction-aware writer rollback path, complete the revocation request with rollback artifact evidence, and persist a content-safe `rollback` trace span for the worker operation; implemented and validated with focused worker tests plus compose/Postgres smoke coverage;
- filesystem-pool `topology.apply_downstream` jobs persist content-safe `topology`
  child spans for lifecycle/graph materialization, preserving trace roots and
  recording only bounded counts and object refs; implemented and validated with
  focused worker tests plus full sidecar validation.
- accepted SkillGraphIR topology operations record deterministic downstream orchestration actions in `trial_summary.downstream_orchestration`, and filesystem-pool `topology.apply_downstream` jobs can consume applied operations to materialize graph edges, activate successor/composed skills, archive superseded/decomposed subjects, record applied action results, and invalidate runtime-derived retrieval/context/embedding records where stores expose invalidation hooks;
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
- canary critical failures trigger rollback/freeze; freeze, rollback revocation queueing, archive-backed filesystem-worker rollback execution, initial-create active-path deletion rollback, body-index/embedding/retrieval/context/topology/evaluator/attribution/governance invalidation, active broker-cache invalidation, and fail-closed policy-approved filesystem-worker writer apply orchestration are implemented.
- long-running job leases renew while handlers are still running; implemented in the job store, worker execution wrapper, and control API with focused tests.
- filesystem-worker `writer.apply` and `revocations.rollback` handlers record content-safe child trace spans under their claimed job spans, including bounded success/error metadata and object refs without compiled skill text.

## Phase 8 - Autonomous Improvement and Curation

Deliverables:

- `autonomous_guarded` apply; implemented as fail-closed filesystem-worker `writer.apply` orchestration that only applies a staged manifest when the queued job carries explicit `policy_approved=true`;
- repair-proposal execution; implemented as llm-generation-worker `repair.execute` orchestration that claims planned curation repair proposals and open drift repair candidates, records governance transactions/items/provenance, queues explicit policy-approved staged manifests to `writer.apply`, can generate guarded staged repair manifests from policy-approved bounded proposals with skill-version anchors, and otherwise fail-closes to evaluator or drift recheck jobs with source execution metadata;
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
  waste into utility rollups, score computation, guarded improvement planning,
  and decomposition-grade context-waste planning with explicit context-value
  acceptance gates;
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
- topology operation drill-down; implemented as a content-safe Observatory
  operation microscope over persisted SkillGraphIR operations and planned trials,
  exposing evidence, transaction, subject/output skill, effect-coverage, and
  trial-status refs through `/admin/api/v1/topology/operations/{operation_id}`,
  the generic object microscope resolver, and the Skills/Topology Operation
  Evidence panel without adding mutation authority;
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
- validation evidence for decomposition-grade context-waste repair planning:
  focused utility tests passed with `7 passed`, focused ruff checks passed, and
  the final validation ladder for the committed slice recorded the exact full
  gate results in `TASKFLOW.md`.
- validation evidence for topology operation drill-down visibility: focused
  Observatory API/frontend source assertions passed with `2 passed`; generated
  OpenAPI client check, focused ruff, `npm run build --prefix
  sidecar/autoskill/observatory`, full `uv run ruff check sidecar`, full
  `uv run pytest` with `354 passed`, `uv run python -m compileall -q sidecar`,
  `docker compose config --quiet`, and `git diff --check` passed; a real
  compose/Postgres smoke inserted one topology operation plus one planned trial,
  read it back through `AsyncpgTopologyStore.get_operation_detail`, verified
  `trial_count=1`, and cleaned the smoke rows.
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
- diagnostic momentum accumulation; implemented so scanner-worker
  `drift.check` jobs record one content-safe diagnostic signal per drift event
  into the existing momentum store, scoped to skill/version when available and
  keyed by hashed contract/probe identifiers;
- diagnostic momentum consumption; implemented so llm-generation-worker
  `repair.execute` jobs can claim ready-for-probe/ready-for-patch momentum
  records as fail-closed repair sources, record governance/provenance metadata,
  and queue drift rechecks or evaluator gates unless a future policy-approved
  staged manifest exists;
- localized repair; implemented so repair execution consumes drift, diagnostic,
  and curation repair proposals through a fail-closed worker path, queues
  gate/recheck jobs when source data is insufficient, and now requires direct
  policy-approved writer-apply repair manifests to be anchored to the affected
  skill version before runtime artifact mutation can be queued;
- skill graph maintenance; implemented for accepted topology operations with
  filesystem-worker downstream materialization that records transaction items,
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
  operator-reviewed/source-linked production replay coverage, worker
  concurrency, and workspace-scoped job-queue health;
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
  episodes from explicit operator redacted-intent plans, pre-adjudicated redacted
  telemetry, or LLM-synthesized redacted intent derived only from content-safe
  retrieval context;
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
  broker policy, and operator-reviewed production replay records can make the
  readiness report pass through the real asyncpg stores after compose
  migrations, while source-linked replay coverage is surfaced as an explicit
  warning gate for sustained replay/canary growth;
- readiness reporting is an operator preflight; the current Dev-01 deployment
  also passed live gateway capture/hint validation, active-profile semantic
  broker paraphrase validation, stored broker replay, production embedding
  validation, red-team smoke, and backup/restore dry-run.
- telemetry-derived replay episode creation does not persist or reconstruct raw
  prompts; missing intents can be synthesized only from content-safe retrieval
  context, and degraded hash-only/metadata-only/no-safe-context cases return
  explicit skip reasons instead of entering the full-autonomy replay corpus.
- validation evidence for the replay-corpus readiness tightening passed on the
  final tree: focused deployment-readiness tests (`3 passed`), focused broker
  policy review tests (`2 passed`), `uv run ruff check sidecar`, `uv run
  pytest` (`371 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, and `git diff --check`. No compose/Postgres smoke was
  needed because the slice only changes existing read-only readiness/review
  shaping over already persisted replay records.

## Phase 11 - Observatory Web Administration and Diagnostics

Deliverables:

- split-container web-admin shell; implemented as a React/Vite Observatory under
  `sidecar/autoskill/observatory`, built into the `Dockerfile.observatory`
  FastAPI image and served from `/admin`, with `/admin/api`, `/admin/live`, and
  `/admin/live-sse` owned by the Observatory container and Core kept to internal
  `/v1` routes in the reference deployment;
- role-aware admin configuration and content-safe API envelopes; implemented for
  `/admin/api/v1/config`, `/summary`, `/pipeline`, `/subsystems`, `/components`,
  `/issues`, `/search`, `/objects`, `/health/live`, and `/health/ready`.
  Observatory response models now expose additive `ok`, `data`, and `meta`
  fields with request IDs, generation timestamps, redaction level, and warning
  slots while preserving existing top-level payload keys for current clients;
- bounded drill-down/read-model surfaces; implemented for components, reason
  codes, playbooks, jobs, schedules, skills, candidates, evaluations, scanner
  findings, historical imports, broker decisions, context artifacts,
  model/embedding profiles, storage, audit, comparisons, diagnostic bundles,
  trace search/detail, event history, and trace replay. Broker-decision
  collection/detail now reads `retrieval_logs` directly and exposes content-safe
  query hashes, candidate object IDs, rendered skill IDs, trace/span links,
  reason codes, and suppression metadata without raw query text. Event history
  now reads bounded redacted `raw_events` metadata, trace search reads bounded
  `trace_spans` summaries, saved comparisons persist in
  `admin_comparison_runs`, and diagnostic bundles persist redacted descriptors
  in `admin_diagnostic_bundles`. Operator action audit receipts now have
  workspace-filtered bounded collection/detail read models over
  `admin_action_audit`. The generic object microscope route now resolves
  captured events, saved baseline
  comparisons, diagnostic bundles, and operator action receipts from those
  stores instead of falling back to placeholder snapshot objects. Broker replay
  corpus visibility is implemented with bounded admin list/detail routes over
  stored replay episodes plus generic `broker_replay_episode` object microscope
  support, exposing only operator-redacted replay intent text, hashes, expected
  skill IDs, source broker-decision links, metadata-key summaries, and explicit
  `raw_prompt_stored=false` policy metadata. Memory quarantine and control-flow
  integrity visibility is implemented with bounded admin list/detail routes over
  existing memory-governance stores plus generic object-microscope support,
  exposing memory hashes/keys, taint/status, provenance links, and
  content-safe decision metadata without returning proposed memory text or
  bypassing the governed `/v1/memory/*` mutation surfaces;
- live updates; implemented with `/admin/live` WebSocket and `/admin/live-sse`
  fallback, frontend fallback logic, snapshot reload handling, and persisted
  `admin_live_event_outbox` events for audited operator actions, diagnostic
  bundles, and read-model invalidation signals;
- operator action gateway; implemented as audited, policy-checked action
  receipts plus guarded aliases for retry/cancel jobs, pause/resume schedules,
  historical import actions, candidate quarantine, freeze/unfreeze/rollback,
  evaluator/scanner/broker/profile/storage/audit/Observatory actions, and source
  revocation. High-impact actions fail closed without explicit confirmation.
  Action receipts now also persist dedicated `admin_action_audit` rows linked to
  the generic audit hash-chain record, preserving actor roles, target identity,
  idempotency key, result, request ID, metadata-key summary, and confirmation
  hashes without storing raw confirmation text. Action-gateway summary reads now
  expose bounded accepted/rejected counts, confirmation/role-policy failures,
  raw-content reveal outcomes, high-impact action history, linked audit/job
  coverage, and data-quality caveats from those persisted receipts without
  creating a second control plane. The raw-content reveal action is implemented
  as an admin-only, config-gated grant primitive that returns a short-lived token
  only in the accepted response and persists only token hashes and content-safe
  request metadata;
- collection pagination and browser action protection; implemented as bounded
  cursor metadata on Observatory collection envelopes, malformed/stale cursor
  rejection, browser-session CSRF header enforcement for POST actions, and
  in-process per-actor rate limits for operator actions and raw reveal attempts;
- frontend overview and cockpits; implemented with assembly-line/workcell
  views, issue board, global search, object inspector, admin actions,
  deep-link state, reduced-motion support, and station cockpit tabs for records,
  metrics, traces, artifacts, config, audit, and help.
- browser hardening; implemented as scoped `/admin` response headers for content
  security policy, frame denial, referrer suppression, MIME sniffing prevention,
  and same-origin opener isolation without applying those headers to ordinary
  `/v1` sidecar routes.

Acceptance:

- Observatory does not expose raw event, prompt, skill, support-file, or memory
  content by default; collection/detail envelopes carry explicit raw-content
  policy metadata;
- Observatory admin routes use existing sidecar stores, snapshots, audit chain,
  trace spine, worker/job surfaces, and governance controls instead of bypassing
  deterministic policy/application layers;
- focused Observatory API tests cover summary/search, bounded collection
  envelopes, readiness, admin auth, audited action receipts, and
  confirmation-required high-impact denial, plus event/trace read models,
  persisted comparisons, persisted diagnostic bundle retrieval, and generic
  object microscope routing for persisted captured-event/comparison/bundle
  records. Operator action audit receipt tests cover bounded filtering, detail
  retrieval, content-policy metadata, linked audit references, and generic
  object microscope routing for `admin_action` objects. Operator action summary
  tests cover accepted/rejected counts, confirmation and role-policy failures,
  raw-content reveal outcomes, high-impact history, linked audit coverage, and
  data-quality metadata;
- validation evidence for the broker-decision drill-down slice passed on the
  final tree: focused Observatory tests `9 passed`, `uv run ruff check sidecar`,
  `uv run pytest` with 312 tests, `uv run python -m compileall -q sidecar`, a
  compose/Postgres smoke of `/admin/api/v1/broker/decisions`, `docker compose
  config --quiet`, and `git diff --check`.
- validation evidence for the persisted object-microscope slice passed on the
  final tree: focused Observatory tests `11 passed`, `uv run ruff check sidecar
  scripts`, `uv run pytest -q` with 314 tests, `uv run python -m compileall -q
  sidecar scripts`, `npm test --prefix plugin/autoskill` with 18 tests,
  `npm run build --prefix sidecar/autoskill/observatory`, a compose/Postgres
  smoke of persisted captured-event/comparison/bundle object routes, `docker
  compose config --quiet`, and `git diff --check`.
- validation evidence for the additive Observatory envelope slice passed on the
  final tree: Observatory API tests `11 passed`, focused `uv run ruff check`
  passed for the edited API/test files, `uv run ruff check sidecar scripts`,
  `uv run pytest -q` with 314 tests, `uv run python -m compileall -q sidecar
  scripts`, `npm test --prefix plugin/autoskill` with 18 tests,
  `npm run build --prefix sidecar/autoskill/observatory`, `docker compose
  config --quiet`, and `git diff --check` passed.
- validation evidence for the scoped admin browser-hardening slice passed on the
  final tree: Observatory API tests `12 passed`, including a dependency-free
  ASGI check that `/admin/api/v1/config` receives the security headers and
  `/v1/health` does not, focused `uv run ruff check` passed for the edited
  API/test files, `uv run ruff check sidecar scripts`, `uv run pytest -q` with
  315 tests, `uv run python -m compileall -q sidecar scripts`, `npm test
  --prefix plugin/autoskill` with 18 tests,
  `npm run build --prefix sidecar/autoskill/observatory`, `docker compose
  config --quiet`, and `git diff --check` passed.
- validation evidence for the dedicated Observatory action-audit slice passed on
  the final tree: Observatory API tests `12 passed`, `uv run ruff check sidecar`
  passed, `uv run pytest` passed with 315 tests, `uv run python -m compileall -q
  sidecar` passed, `npm test --prefix plugin/autoskill` passed with 18 tests,
  `npm run build --prefix sidecar/autoskill/observatory` passed,
  `docker compose config --quiet` passed, and `git diff --check` passed. A
  compose/Postgres smoke applied migrations, recorded one
  `verify_audit_chain` action through the admin API, verified the
  `admin_action_audit` row links to `audit_records` and contains only redacted
  request metadata, deleted the smoke rows, and stopped Postgres while
  preserving the dev volume.
- validation evidence for the Observatory operator-action audit read-model
  slice passed on the final tree: Observatory API tests `17 passed`, `uv run
  ruff check sidecar` passed, `uv run pytest -q` passed with 320 tests, `uv run
  python -m compileall -q sidecar` passed, `npm test --prefix plugin/autoskill`
  passed with 18 tests, `npm run build --prefix
  sidecar/autoskill/observatory` passed, `docker compose config --quiet` passed,
  and `git diff --check` passed. A compose/Postgres smoke applied migrations
  idempotently, inserted one `admin_action_audit` receipt, verified
  workspace-filtered list/detail asyncpg reads, deleted the smoke row, and left
  the pre-existing Postgres container running.
- validation evidence for the cursor/security/live-outbox slice passed on the
  final tree: Observatory API tests `14 passed`, `uv run ruff check sidecar
  scripts` passed, `uv run pytest -q` passed with 317 tests,
  `uv run python -m compileall -q sidecar scripts` passed,
  `npm test --prefix plugin/autoskill` passed with 18 tests,
  `npm run build --prefix sidecar/autoskill/observatory` passed,
  `docker compose config --quiet` passed, and a compose/Postgres smoke applied
  migrations, recorded one `refresh_read_models` admin action, verified its
  `read_model_invalidated` row in `admin_live_event_outbox`, verified linked
  `admin_action_audit` and `audit_records` rows, deleted the smoke rows, and
  stopped Postgres while preserving the dev volume.
- validation evidence for the raw-content reveal grant slice passed on the final
  tree: focused Observatory API tests `16 passed`, `uv run ruff check sidecar`
  passed, `uv run pytest` passed with 319 tests, `uv run python -m compileall -q
  sidecar` passed, `docker compose config --quiet` passed, and `git diff
  --check` passed. A compose/Postgres smoke applied migrations, accepted one
  admin `reveal_raw_content` grant with raw content enabled, verified
  `admin_action_audit` and `audit_records` persisted only the token hash and
  content-safe request metadata, deleted the smoke rows, and stopped compose
  while preserving the dev volume.
- validation evidence for the Observatory missing-signal remediation passed on
  the final tree: focused Observatory API tests `19 passed`, `uv run ruff check`
  passed for the edited sidecar files, `uv run pytest -q` passed with 322 tests,
  `uv run python -m compileall -q sidecar` passed, `npm test --prefix
  plugin/autoskill` passed with 18 tests, `npm run build --prefix
  sidecar/autoskill/observatory` passed, `docker compose config --quiet` passed,
  and `git diff --check` passed. The sidecar now distinguishes absent metric
  fields from present zero-valued read models, exposes
  `data_quality.missing_signal_keys`, uses `read-model-missing` for absent
  bounded admin object/read-model fallbacks, and the Observatory cockpit renders
  missing-signal chips only when a station actually reports missing signals. A
  live Dev-01 validation against `/admin/api/v1/summary?workspace_id=dev-01`
  reported zero stations with `missing-required-signal` and one remaining real
  issue, `embedding-backlog-present`.
- validation evidence for the Observatory live-stream fallback continuity slice
  passed on the final tree: focused Observatory API tests `30 passed`, `npm run
  build --prefix sidecar/autoskill/observatory` passed, `uv run ruff check
  sidecar scripts` passed, `uv run pytest` passed with 340 tests, `uv run
  python -m compileall -q sidecar scripts` passed, `docker compose config --quiet`
  passed, and `git diff --check` passed. WebSocket and SSE fallback snapshots
  now preserve the read-model `snapshot_seq`, advance reconnects with a
  separate persisted outbox `cursor_seq`, clamp snapshot-style `last_seq`
  values to the newest outbox cursor, and emit heartbeat payloads once the
  client is caught up. A real Postgres smoke through `uv run python
  scripts/autoskill_observatory_live_smoke.py` proved
  `snapshot_seq=1780550603438`, `snapshot_cursor_seq=11`,
  `stale_outbox_seq=11`, and `live_outbox_seq=12` before deleting smoke rows.
- validation evidence for the Observatory live-stream envelope contract
  hardening passed on the final tree: snapshot and heartbeat fallback envelopes
  now include additive `kind` and `sent_at` fields like persisted live-outbox
  deltas, preserving existing reconciliation fields while satisfying the
  Section 12.3 timestamped live-envelope shape. Focused live fallback/SSE tests
  passed with `6 passed`; final validation passed with `uv run ruff check
  sidecar`, `uv run pytest` (`365 passed`), `uv run python -m compileall -q
  sidecar`, `docker compose config --quiet`, and `git diff --check`.
- validation evidence for the Observatory job-health scoping slice passed on
  the final tree: focused job/Observatory tests passed with `2 passed`,
  `uv run ruff check sidecar` passed, `uv run pytest` passed with 334 tests,
  `uv run python -m compileall -q sidecar` passed,
  `docker compose config --quiet` passed, and `git diff --check` passed. A
  compose/Postgres smoke applied migrations, inserted an isolated terminal
  failed job followed by a same-workspace/job-kind success through the asyncpg
  store, verified both the job summary and Observatory
  `operator_metrics.job_queue_depth` returned only `{"succeeded": 1}`, and
  deleted the smoke rows. The admin summary now uses one effective workspace for
  job counts, worker-health summaries, operator metrics, and audit
  verification, and job summaries no longer treat old failed rows as active
  failures after a later same-workspace/job-kind success.
- validation evidence for the executable Observatory acceptance crosswalk passed
  on the final tree: `scripts/autoskill_observatory_acceptance.py --json`
  covers the Section 21 acceptance criteria and Section 24 developer checklist
  as a deterministic report with evidence pointers and implemented-equivalent
  markers where the implementation intentionally satisfies the spec through an
  equivalent repo pattern. Focused validation passed with `uv run pytest -q
  sidecar/autoskill/tests/test_observatory_acceptance_report.py` (`1 passed`)
  and the report command returned `ready=true`, `satisfied=78`, and no
  validation errors.
- validation evidence for the proposal-gate autonomy-assurance slice passed on
  the final tree: proposal-gate evaluation results now separate hard invariant
  failures from calibrated soft-threshold misses, attach autonomous fallback
  ladders, mark repeated soft-stall threshold-deadlock candidates, and expose
  the content-safe summary through evaluation review read models. This advances
  core handoff Sections 5.1, 5.4-5.6, 5.10, 12.8-12.10, and production
  acceptance criteria 53-55 and 62-63 without weakening scanner, regression,
  rollback, activation, or evaluator gates. Focused validation passed with
  `uv run pytest -q sidecar/autoskill/tests/test_evaluator.py` (`11 passed`)
  and focused ruff checks; full validation passed with `uv run ruff check
  sidecar scripts`, `uv run pytest` (`357 passed`), `uv run python -m
  compileall -q sidecar scripts`, `docker compose config --quiet`, and `git
  diff --check`.
- validation evidence for the Observatory broker replay corpus read model passed
  on the final tree: focused Observatory API tests covered admin list/detail and
  generic object-microscope lookup for a stored replay episode, generated
  Observatory OpenAPI client `--check` passed, `uv run ruff check sidecar`
  passed, `uv run pytest` passed with 347 tests, `uv run python -m compileall
  -q sidecar` passed, and `npm run build --prefix
  sidecar/autoskill/observatory` passed. A real compose/Postgres smoke applied
  migrations, inserted one production-tagged replay episode through
  `AsyncpgBrokerPolicyStore`, read it through the new admin routes with bearer
  auth, verified `raw_prompt_stored=false`, and deleted the smoke rows.
- validation evidence for the Observatory broker replay corpus frontend slice
  passed on the final tree: the React Observatory now exposes a dedicated Replay
  tab wired through generated `/admin/api/v1/broker/replay-episodes` paths,
  production-tag filtering, episode selection, expected routing/provenance
  panels, and explicit raw-prompt/content-policy badges. Focused frontend source
  assertions passed with `7 passed`, `npm run build --prefix
  sidecar/autoskill/observatory` passed, `uv run ruff check sidecar` passed,
  `uv run pytest -q` passed with `348 passed`, `uv run python -m compileall -q
  sidecar` passed, and `git diff --check` passed.
- validation evidence for the Observatory memory/control-flow read-model slice
  passed on the final tree: focused Observatory API tests proved route-matrix
  coverage, list/detail routes, generic object-microscope lookup, filter
  handling, and content-safe shaping that returns proposed-memory hash/keys
  without proposed memory content. Validation passed with focused tests
  (`2 passed`), generated client `--check`, `uv run ruff check sidecar`,
  `uv run pytest` (`349 passed`), `uv run python -m compileall -q sidecar`,
  `npm test --prefix plugin/autoskill` (`18 passed`), `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and
  `git diff --check`.
- validation evidence for the Observatory trace replay backend enrichment slice
  passed on the final tree: `/admin/api/v1/replay/traces/{trace_id}` now derives
  station highlights, a span waterfall, policy/gate badges, safe diff/hash
  metadata panels, detail-drawer refs, deduplicated downstream provenance, and a
  redacted export bundle descriptor from existing `trace_spans` rows without
  exposing raw content or re-executing work. Focused Observatory API tests
  passed with `32 passed`, `uv run ruff check sidecar` passed, `uv run pytest`
  passed with 349 tests, `uv run python -m compileall -q sidecar` passed,
  `npm run build --prefix sidecar/autoskill/observatory` passed,
  `docker compose config --quiet` passed, and `git diff --check` passed. No
  compose/Postgres smoke was needed because this is a read-model shaping change
  over already-tested trace store data.
- validation evidence for the Observatory trace replay frontend enrichment
  slice passed on the final tree: the Trace tab now consumes the enriched
  replay read model directly, rendering span waterfall rows, station
  highlights, policy/gate badges, detail-drawer object refs, safe diff/hash
  panels, the redacted export-bundle descriptor, and downstream provenance from
  the sidecar-hosted API without exposing raw content or adding a second control
  plane. Focused Observatory acceptance assertions passed with `8 passed`,
  `npm run build --prefix sidecar/autoskill/observatory` passed,
  `uv run ruff check sidecar` passed, `uv run pytest` passed with 350 tests,
  `uv run python -m compileall -q sidecar` passed, `npm test --prefix
  plugin/autoskill` passed with 18 tests, `docker compose config --quiet`
  passed, and `git diff --check` passed. No compose/Postgres smoke was needed
  because this is a frontend/read-model consumption change over the already
  validated Trace Replay API.
- validation evidence for the Observatory topology metrics read-model slice
  passed on the final tree: `/admin/api/v1/topology` now includes content-safe
  `topology_store.metrics` output for create/improve/compose/decompose
  operation states, trial status matrices, and recent SkillGraphIR operations,
  and the React Skills/Topology view renders those cockpit signals before the
  raw inspector payload. This advances Observatory Sections 8.9, 9.3, 12.6, and
  13.1 without adding any mutation path or exposing raw skill/evidence content.
  Focused validation passed with the Observatory API/source assertions, `uv run
  ruff check` on edited Python files, and the Observatory frontend build; final
  validation evidence is recorded in `TASKFLOW.md`.
- validation evidence for the Observatory required-signal issue-evidence slice
  passed on the final tree: `missing-required-signal` issue-board records now
  include exact missing signal classes, missing metric keys, component evidence
  refs, and a dedicated safe next action, and the generic issue microscope
  exposes the same content-safe evidence path. This advances Observatory
  Sections 5.5, 7.7, 12.6, and acceptance criterion 31 without adding mutation
  authority or raw-content access. Validation passed with the focused
  Observatory API regression (`3 passed`), focused ruff, full sidecar ruff, full
  pytest (`355 passed`), compileall, and diff-check gates.
- validation evidence for the Observatory guided-playbook signal-state slice
  passed on the final tree: `/admin/api/v1/playbooks/{id}` and the generic
  object microscope now expose severity, confidence, first checks, next views,
  supporting issue/component records, missing telemetry warnings, affected
  objects, content-safe next diagnostic actions, and explicit blocked-policy
  actions for built-in playbooks. The playbook catalog now covers the required
  Section 7.5 journeys for candidate drought, rejected improvements, context
  pressure, harmful activation, historical bootstrap yield, broker misses,
  read-model staleness, and stalled LLM maintenance. This advances Observatory
  Sections 7.5, 7.7, 12.1, 12.6, and 16.1/16.3 without adding mutation
  authority or raw-content access. Focused Observatory API tests passed
  (`35 passed`); final validation passed with `uv run ruff check sidecar`,
  `uv run pytest` (`356 passed`), `uv run python -m compileall -q sidecar`,
  `docker compose config --quiet`, and `git diff --check`.
- validation evidence for the Observatory object microscope read-model fallback
  slice passed on the final tree: unsupported `/admin/api/v1/objects/{type}/{id}`
  lookups now return `read-model-missing` with `observatory_admin` support
  metadata instead of conflating absent bounded read models with
  `missing-required-signal` telemetry-contract failures. This advances
  Observatory Sections 7.6, 7.7, 12.6, and acceptance criterion 31 without
  adding mutation authority or raw-content access. Focused Observatory API
  regression passed (`2 passed`); final validation passed with `uv run ruff
  check sidecar`, `uv run pytest`, `uv run python -m compileall -q sidecar`,
  `docker compose config --quiet`, and `git diff --check`.
- validation evidence for the Observatory evaluator autonomy-assurance
  microscope slice passed on the final tree: `/admin/api/v1/evaluations/{id}`
  now expands content-safe proposal-gate assurance into hard-invariant failures,
  calibrated soft-threshold misses, threshold-deadlock state, deterministic
  fallback actions, explicit policy-blocked actions, and typed provenance refs
  for evaluated skill versions plus threshold/invariant signals. This advances
  core handoff Sections 5.1, 5.6, 5.10, and 12.8-12.10 plus Observatory
  Sections 7.6, 7.7, 8.14, 12.6, and 16.1/16.3 without exposing raw probe
  payloads or adding mutation authority. Focused Observatory API tests passed
  (`36 passed`); final validation passed with `uv run ruff check sidecar`, `uv
  run pytest` (`358 passed`), `uv run python -m compileall -q sidecar`,
  `docker compose config --quiet`, and `git diff --check`.
- validation evidence for the Observatory autonomy/evidence read-model slice
  passed on the final tree: the durable schema now includes status-only
  `admin_evidence_fidelity_status`, `admin_autonomy_decision_status`,
  `admin_semantic_adjudication_status`, and
  `admin_administrative_escalation_status`; the admin store and generated route
  client expose bounded list/detail surfaces for `/admin/api/v1/evidence/fidelity`,
  `/raw-vault/summary`, `/adjudications`, `/autonomy/decisions`,
  `/autonomy/threshold-deadlocks`, and `/escalations`. This advances
  Observatory Sections 8.5.1-8.5.3, 12.1, 12.6, 13.3.1 and acceptance items
  `21.23`, `21.24`, `21.40`, `24.auto.1`, `24.auto.3`, and `24.auto.6`
  without exposing raw evidence, raw-vault records, or LLM verdict payloads and
  without adding mutation authority. Focused validation passed with
  Observatory API tests (`37 passed`), generated OpenAPI client `--check`,
  `uv run ruff check sidecar`, `uv run pytest` (`367 passed`), `uv run python
  -m compileall -q sidecar`, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, `git diff
  --check`, and a real compose/Postgres smoke that applied migrations,
  inserted/listed/detail-read the four read-model families, and deleted smoke
  rows.
- validation evidence for the Observatory threshold-deadlock detail slice
  passed on the final tree: `/admin/api/v1/autonomy/threshold-deadlocks/{decision_id}`
  now exposes a first-class content-safe threshold-deadlock object derived from
  `admin_autonomy_decision_status`, and the generic object microscope resolves
  `threshold_deadlock` aliases to the same payload with autonomy-decision
  provenance, safe-next-action diagnostics, and raw-content-disabled policy.
  This advances Observatory Sections 7.6, 7.7, 8.5.3, 12.1, and 12.6 without
  mutation authority. Focused validation passed with Observatory API tests
  (`38 passed`), generated OpenAPI client `--check`, `uv run ruff check
  sidecar`, `uv run pytest` (`368 passed`), `uv run python -m compileall -q
  sidecar`, `npm run build --prefix sidecar/autoskill/observatory`, `docker
  compose config --quiet`, `git diff --check`, and the Observatory acceptance
  report (`86` satisfied, `0` validation errors).
- validation evidence for the Observatory context compiler read-model slice
  passed on the final tree: persisted context-governance records now have
  bounded list/detail store methods and sidecar-hosted admin routes for
  context artifacts, context compile runs, context budget events, and semantic
  compression trials. `/admin/api/v1/context/artifacts`,
  `/context/compile-runs`, `/context/budget-events`, `/context/compression-trials`,
  their detail routes, and generic object-microscope aliases expose hashes,
  gate statuses, token counts, semantic-equivalence/compression metrics,
  evidence/metadata key summaries, and provenance refs without returning
  compiled text, raw SkillIR, prompt bodies, raw evidence, or artifact text.
  This advances core handoff Sections 11.12-11.15 and Observatory Sections
  8.12, 12.1, 12.6, and 13.1 without adding mutation authority or a second
  control plane. Focused context/route validation passed with `2 passed`;
  focused Observatory API validation passed with `39 passed`; generated
  OpenAPI client `--check`, `uv run ruff check sidecar`, `uv run pytest`
  (`369 passed`), `uv run python -m compileall -q sidecar`,
  `npm run build --prefix sidecar/autoskill/observatory`, and
  `docker compose config --quiet` passed. A real compose/Postgres smoke applied
  migrations, recorded/listed/detail-read all four context-governance record
  families through `AsyncpgContextGovernanceStore`, and stopped the Postgres
  service afterward.
- the Observatory subsystem/component catalog is now present in durable schema,
  not only in runtime Python constants: `migrations/0001_autoskill_schema.sql`
  creates and idempotently seeds `admin_component_catalog` and
  `admin_subsystem_catalog`, and focused tests verify every runtime station and
  subsystem ID appears in that seed.
- the Observatory frontend API surface now has a generated route client:
  `scripts/generate_observatory_openapi_client.py` derives the checked-in
  `observatoryClient.ts` route map from FastAPI OpenAPI, frontend wrappers
  consume generated admin route paths, and focused tests fail if the generated
  file drifts from the current app schema.
- the Observatory Admin surface now exposes frontend render/live-update
  diagnostics: render count, session mount count, live snapshot application
  count, duplicate snapshot suppression count, summary seed count, and
  sequence-gap reload count are visible beside the operator action/audit tools.
- guarded Observatory operator actions now require an explicit confirmation
  dialog and reason before the frontend submits the dry-run action request to
  the audited action gateway.
- deterministic Observatory E2E/load/visual fixtures now live in
  `sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json` and
  are generated by `scripts/autoskill_observatory_fixtures.py`; the catalog
  covers required visual states plus a high-load soak profile and is checked by
  focused tests and npm `fixtures:check`.
- validation evidence for the Section 8 worker-pool taxonomy passed on the
  final tree: job definitions are split across scheduler, ingest, backfill,
  embedding, retrieval, analysis, LLM generation, scanner, evaluation,
  filesystem, and maintenance pools; `/v1/status` and `/v1/workers/health`
  report canonical pool health/concurrency; root compose launches the separate
  resource-class workers; and legacy `mutation` is retained only as an
  explicit compatibility alias for filesystem work. Focused validation passed
  with worker/backfill/report tests (`68 passed`); full `uv run pytest -q`
  passed (`416 passed`); `uv run ruff check ...`, `uv run python -m compileall
  -q sidecar scripts`, `docker compose -f docker-compose.yml config --quiet`,
  acceptance/readiness/conformance scripts, and `git diff --check` passed.
- validation evidence for the Part V Section 4 threshold-deadlock Observatory
  diagnostics slice passed on the focused tree: threshold-deadlock collection,
  detail, and generic object microscope payloads now include content-safe
  attempted autonomous remedies, remediation status, fallback linkage,
  calibration-support linkage, reason codes, and safest next action derived
  from the linked sanitized evaluation read-model where available. The
  diagnostic remains read-only and suppresses raw fallback, remediation,
  replay/probe, and calibration payloads. Focused validation passed with
  `uv run pytest sidecar/autoskill/tests/test_observatory_api.py -q -k
  'autonomy_evidence_read_models_are_content_safe'` (`1 passed, 70
  deselected`), `uv run ruff check sidecar/autoskill/api/app.py
  sidecar/autoskill/db/evaluations.py
  sidecar/autoskill/tests/test_observatory_api.py`, and `uv run python -m
  compileall -q sidecar/autoskill/api/app.py
  sidecar/autoskill/db/evaluations.py
  sidecar/autoskill/tests/test_observatory_api.py`. Next gate: broader
  Observatory/API suite plus acceptance/conformance reports.
