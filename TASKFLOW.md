# SkillKernel TaskFlow Ledger

Managed durable work item: `skillkernel-autoskill-v1`

Goal: implement SkillKernel / OpenClaw AutoSkill Manager from the v16 coherence-closed implementation handoff until production acceptance criteria are satisfied.

Owner: Claudia front-stage; `codex-worker` may be used for bounded coding/debugging slices.

Canonical path: `/Warehouse/SkillKernel`

Guiding document: `skillkernel-openclaw-autoskill-ultimate-v16-coherence-closed-implementation-handoff.md`

## Current Phase

Phase 10/11 v16 coherence closure and production-hardening buildout.

## Current State

- 2026-06-06: Exhaustive unified-spec pass continued after pushing
  `8721d71`. CI for the current head is in progress. A bounded
  `codex-worker` slice was launched for Part II/III scheduler, governance,
  admin-action, autonomy, storage/embedding/replay, and control-plane read
  model surfaces:
  `agent:codex-worker:subagent:68442cf1-ca30-4afc-b063-4e36485c0460` / run
  `372e5a53-c74e-4c70-acfd-64c534c0cf95`. Parent continues local,
  non-overlapping coverage/report verification while waiting for the push-based
  child result. Current local reports are green: `uv run python
  scripts/autoskill_conformance.py --json` returned `ready=true` with 13/13
  checks passing, and `uv run python scripts/autoskill_readiness.py --json`
  returned `ready=true` with 52 landscape rows, 17 readiness checklist items,
  and zero validation errors. `uv run python scripts/autoskill_traceability.py
  --json` returned `ready=true` with 100 anchors, 25 traceability rows, and
  zero validation errors. Broader local deterministic gates also passed: `uv
  run ruff check sidecar scripts`, `uv run python -m compileall -q sidecar`,
  and `uv run pytest sidecar/autoskill/tests/test_conformance_report.py
  sidecar/autoskill/tests/test_readiness_report.py
  sidecar/autoskill/tests/test_historical_bootstrap.py
  sidecar/autoskill/tests/test_observatory_acceptance_report.py -q` (`18
  passed`). Acceptance/report drift checks are also green: `uv run python
  scripts/autoskill_acceptance.py --json` returned `ready=true` with 70
  implemented criteria and zero validation errors, `uv run python
  scripts/autoskill_observatory_acceptance.py --json` returned `ready=true`
  with 86 satisfied items and zero validation errors, and `uv run python
  scripts/generate_observatory_openapi_client.py --check` passed.
- 2026-06-06: Core historical bootstrap consolidation now surfaces
  historical-only topology recommendations as propose-only, non-activating
  control-plane evidence. Historical evidence payloads can contribute guarded
  `improve`, `compose`, and `decompose` recommendations with support,
  success/failure, sequence, context-pressure, token-waste, taint, and source
  metadata, while weak support or missing topology prerequisites produce
  blockers and all results explicitly forbid runtime file writes. This advances
  the unified specification's Core topology, historical ingestion,
  evidence-maturity, and safety-ordering requirements without adding autonomous
  apply authority. Committed as `46c645a`. Focused validation passed with `uv
  run pytest sidecar/autoskill/tests/test_historical_bootstrap.py -q` (`7
  passed`), `uv run ruff check
  sidecar/autoskill/services/historical_bootstrap.py
  sidecar/autoskill/tests/test_historical_bootstrap.py`, and `git diff
  --check`.
- 2026-06-06: Observatory component metrics now resolve through the generic
  object microscope path. `/admin/api/v1/objects/component_metrics/{component}`
  and station-metrics aliases reuse the same bounded sidecar read model as
  `/admin/api/v1/components/{component}/metrics`, returning signal contracts,
  bounded records, component diagnostics, provenance, and explicit raw-content
  denial without direct SQL/log inspection or UI-local authority. This advances
  Observatory Sections 7.6, 7.7, 8.x station cockpit drill-down, 12.6, 13.1,
  and 16.1 by closing another aggregate-to-evidence path through the Core-owned
  read-model surface. Committed as `8f8a9ac`. Focused validation passed with
  `uv run pytest sidecar/autoskill/tests/test_observatory_api.py -q -k
  component_metrics_generic_object` (`1 passed, 56 deselected`), `uv run ruff
  check sidecar/autoskill/api/app.py
  sidecar/autoskill/tests/test_observatory_api.py`, and `git diff --check`.
- 2026-06-06: Schwi requested a new exhaustive check/remediate/commit pass
  against the full `unified-implementation-specification.md` after the
  cron/spec update aligned report tooling to the unified document. This pass
  uses a parent-level TaskFlow strategy: extract/track requirement coverage by
  specification region, inspect existing implementation and executable
  acceptance reports first, remediate bounded gaps immediately when found,
  commit each coherent fix before moving on, and preserve child-worker session
  IDs, commands, gates, commits, blockers, and next slices here. Baseline at
  start: `main` clean and aligned with `origin/main` at `0f91e61`. First
  bounded slice targets Part IV/V/VI static conformance and assurance;
  `codex-worker` child `agent:codex-worker:subagent:67688647-18bb-487f-9b71-9c641209e6d3`
  / run `44845b0c-f2e3-4874-b16a-f99070a3b4b4` was launched for that
  slice. Local remediation added the Part V conformance gate/docs/test,
  tightened the production placeholder scanner to catch `NotImplementedError`,
  and replaced a historical-bootstrap filtered-store `NotImplementedError`
  with a deterministic no-op derive result. Focused validation passed:
  `uv run python scripts/autoskill_conformance.py --json`, `uv run pytest
  sidecar/autoskill/tests/test_conformance_report.py
  sidecar/autoskill/tests/test_historical_bootstrap.py -q` (`6 passed`),
  `uv run ruff check scripts/autoskill_conformance.py
  sidecar/autoskill/tests/test_conformance_report.py
  sidecar/autoskill/services/historical_bootstrap.py
  sidecar/autoskill/tests/test_historical_bootstrap.py`, and `uv run python
  scripts/autoskill_readiness.py --json`.
- 2026-06-06: Observatory fixture/readiness audit found Part IV/Part V visual
  fixture coverage drift: the fixture set covered stale telemetry and high-load
  soak, but did not explicitly cover the spec-named `regression` and
  `historical_bootstrap` states, and freeze coverage was encoded only as
  `rollback_freeze`. Remediation normalized the required fixture state set,
  added explicit regression and historical-bootstrap fixtures, renamed the
  freeze fixture to `freeze`, regenerated
  `sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json`, and
  updated the focused acceptance expectation to 13 scenarios. Validation passed:
  `uv run python scripts/autoskill_observatory_fixtures.py --json`,
  `uv run pytest sidecar/autoskill/tests/test_observatory_acceptance_report.py
  -q` (`9 passed`), and `uv run ruff check
  scripts/autoskill_observatory_fixtures.py
  sidecar/autoskill/tests/test_observatory_acceptance_report.py`.
- 2026-06-06: Core capture/evidence/historical-bootstrap audit found Section
  14 historical source coverage drift for generic task/subagent/ACP run
  records: task-flow ledgers were handled, but adjacent task-run records were
  not classified or parsed as first-class metadata-only historical sources.
  Remediation added task-record discovery classification, task ledger taint,
  metadata-only import recommendation, safe metadata extraction for JSON/JSONL
  task records, lineage/source-item typing, and focused discovery/import tests
  proving raw prompts and private email-like content do not persist in the
  redacted chunk text. Validation passed with `uv run pytest
  sidecar/autoskill/tests/test_historical_import.py -q` (`24 passed`), `uv run
  ruff check sidecar/autoskill/services/historical_discovery.py
  sidecar/autoskill/services/historical_import.py
  sidecar/autoskill/tests/test_historical_import.py`, and `git diff --check`.
- 2026-06-06: Observatory opportunity mining now has a sidecar-hosted,
  content-safe admin read model instead of being visible only through the
  control-plane `/v1/opportunities/mine` action. `/admin/api/v1/opportunities`
  derives bounded opportunity candidates through the existing deterministic
  miner, and generic `opportunity`/`candidate_opportunity` object aliases return
  support counts, recommendation, evidence refs, duplicate-search decisions and
  match counts, candidate slug, and description hashes while withholding raw
  evidence, raw match summaries, and the derived candidate description; the
  admin path does not create candidate records, activation side effects, or
  retrieval-log rows. This
  advances core handoff Sections 13.2-13.8 and 18.1-18.5 plus Observatory
  Sections 7.6, 7.7, 8.8, 12.1, 12.6, 13.1, and 16.1 by closing the
  opportunity aggregate-to-evidence path without adding UI-local candidate
  creation, activation, or autonomous apply authority. Validation passed with
  focused opportunity/admin route coverage (`5 passed`, `1 passed`), generated
  Observatory OpenAPI client refresh and `--check`, `uv run ruff check
  sidecar`, `uv run pytest` (`391 passed`), `uv run python -m compileall -q
  sidecar`, `npm run build --prefix sidecar/autoskill/observatory`, `docker
  compose config --quiet`, `git diff --check`, and an isolated compose/Postgres
  smoke on port `59662` that migrated a fresh database, verified non-recording
  lexical opportunity lookup creates no workspace or retrieval-log rows for a
  missing workspace, verified normal recorded lexical retrieval still creates
  one workspace and one retrieval-log row, and removed the temporary compose
  project/volume.
- 2026-06-06: Observatory profile qualification runs now have content-safe
  object microscopes instead of being visible only as profile-embedded
  checklist summaries. `ProfileQualificationStore` exposes workspace-filtered
  detail reads for text-model and embedding qualification runs, and generic
  `/admin/api/v1/objects/model_profile_qualification_run/{id}`,
  `/admin/api/v1/objects/profile_qualification_run/{id}`, and
  `/admin/api/v1/objects/embedding_profile_qualification_run/{id}` aliases
  return deterministic check outcomes, bounded scalar metrics, profile refs,
  LLM invocation refs when present, verdicts, probe-set versions, timestamps,
  and explicit raw-probe/error denial metadata while withholding raw probe
  payloads, endpoint refs, API keys, raw provider errors, and cost analytics.
  This advances core handoff Sections 2.40-2.41 and 3.3 plus Observatory
  Sections 1.5, 1.9, 5.1, 7.3, 8.18, 12.6, 16.1, and 21.16/21.26/21.40 by
  closing the aggregate-to-evidence path for model/embedding qualification
  gates without adding UI-local model authority. Validation passed with focused
  Observatory/profile qualification coverage (`1 passed`, `4 passed`), `uv run
  ruff check sidecar`, `uv run pytest` (`390 passed`), `uv run python -m
  compileall -q sidecar`, `docker compose config --quiet`, `git diff --check`,
  and core and Observatory acceptance reports (`70` implemented, `86`
  satisfied, `0` validation errors). An isolated compose/Postgres smoke on
  port `59647` migrated a fresh database, recorded one text-model and one
  embedding qualification run through `AsyncpgProfileQualificationStore`,
  detail-read both by workspace/run ID, verified a cross-workspace miss, and
  removed the temporary compose project/volume.
- 2026-06-06: Observatory historical import sources now have a content-safe
  source microscope instead of returning raw historical source records directly
  to the admin UI. `/admin/api/v1/historical/imports`,
  `/admin/api/v1/historical/imports/{historical_import_id}`, and generic
  `historical_import`, `historical_import_source`, and `historical_source`
  object aliases expose stable source IDs, source kind, parser/redaction
  versions, trust/status, taint and metadata key names, timestamps, and source
  key/fingerprint hashes while withholding raw source locators, arbitrary
  metadata values, taint values, and raw historical content. This advances
  core handoff Sections 14.1-14.5 and 14.12 plus Observatory Sections 8.2,
  12.1, 12.6, 16.1, 21.16, 21.21, 21.30, and 21.40 by closing the
  historical-ingestion aggregate-to-evidence path without making the frontend
  the security boundary or adding UI-local import authority. Validation passed
  with focused Observatory API coverage (`56 passed`), `uv run ruff check
  sidecar`, `uv run pytest` (`387 passed`), `uv run python -m compileall -q
  sidecar`, `docker compose config --quiet`, `git diff --check`, and core and
  Observatory acceptance reports (`63` production criteria, `7` context
  criteria, `42` Observatory criteria, `44` checklist items, ready=true). No
  compose/Postgres smoke was needed because this slice only reshapes the
  existing historical import read path and validates it through in-memory route
  coverage.
- 2026-06-06: Observatory canary results now have a content-safe lifecycle
  drill-down instead of remaining visible only as aggregate counters or skill
  lifecycle side effects. The lifecycle store exposes bounded asyncpg
  `list_canary_results` and `get_canary_result` reads with workspace filtering;
  `/admin/api/v1/canary/results`,
  `/admin/api/v1/canary/results/{canary_result_id}`, and generic
  `canary_result`/`canary` object aliases return status, criticality, skill,
  skill-version, evolution-transaction refs, metric keys plus numeric/boolean
  values, and reason/metrics hashes while withholding arbitrary metric strings
  and raw reason text. This advances core handoff Sections 1, 1.2, 23, 25,
  and 28.2 plus Observatory Sections 1.5, 7.6, 8.5.4, 8.16, 12.6, 13.1,
  16.1, 21.16, 21.22, 21.23, and 21.40 by closing the canary/freeze
  aggregate-to-evidence path without adding UI-local mutation authority.
  Validation passed with focused canary/route coverage (`2 passed`), generated
  Observatory OpenAPI client refresh and `--check`, `uv run ruff check sidecar`,
  `uv run pytest` (`386 passed`), `uv run python -m compileall -q sidecar`,
  `npm run build --prefix sidecar/autoskill/observatory`, `docker compose
  config --quiet`, `git diff --check`, and core and Observatory acceptance
  reports (`70` implemented, `86` satisfied, `0` validation errors). A real
  isolated compose/Postgres smoke on port `59631` migrated a fresh database,
  seeded the FK-backed skill row, recorded one canary result through
  `AsyncpgLifecycleStore`, listed and detail-read it with workspace filtering,
  verified cross-workspace isolation, and removed the temporary compose
  project/volume.
- 2026-06-05: Observatory skill, skill-version, and candidate drill-downs now
  resolve through the generic object microscope instead of depending only on
  dedicated list/detail routes or falling through to the snapshot placeholder.
  Shared content-safe microscope builders keep `/admin/api/v1/skills/{id}`,
  `/admin/api/v1/skills/{skill_id}/versions/{version_id}`,
  `/admin/api/v1/candidates/{id}`, and generic `skill`, `skill_version`, and
  `candidate` object aliases aligned while exposing only lifecycle,
  scanner/evaluator, manifest-hash, active-version, candidate transaction, and
  provenance metadata; raw SkillIR and compiled runtime text remain explicitly
  unavailable. This advances core handoff Sections 1, 1.2, 1.5, 13, 17, 23,
  and 28.2 plus Observatory Sections 7.6, 7.7, 8.9, 8.10, 9.1-9.3, 12.6,
  13.1, and 21.16 by closing the aggregate-to-evidence path for skill-library
  and candidate-review refs without adding UI-local mutation authority.
  Validation passed with focused skill/candidate/schedule microscope coverage
  (`3 passed`), `uv run ruff check sidecar`, `uv run pytest` (`385 passed`),
  `uv run python -m compileall -q sidecar`, `docker compose config --quiet`,
  `git diff --check`, and core and Observatory acceptance reports (`70`
  implemented, `86` satisfied, `0` validation errors). No compose/Postgres
  smoke was needed because this slice only reuses existing skill/candidate read
  stores and validates them through in-memory route coverage.
- 2026-06-05: Observatory storage/read-model health now has a dedicated
  content-safe storage microscope instead of relying on the generic component
  microscope. `/admin/api/v1/storage` returns the bounded storage object with
  relation counts, table/index/total byte summaries, estimated rows, largest
  relation metadata, read-model freshness, index-health status, explicit
  migration/retention telemetry gaps, and action/invariant links while
  withholding connection details, raw SQL, and arbitrary database content; the
  generic `storage`, `storage_db`, and `db_health_report` object aliases resolve
  the same microscope. This advances core handoff Sections 28.2-28.3 and
  Observatory Sections 7.6, 7.7, 8.19, 12.6, 13.1, and 21.25 by closing the
  storage cockpit aggregate-to-evidence path without adding storage mutation
  authority. Validation passed with focused storage microscope coverage (`2
  passed`), `uv run ruff check sidecar`, `uv run pytest` (`383 passed`), `uv
  run python -m compileall -q sidecar`, `docker compose config --quiet`, `git
  diff --check`, and core and Observatory acceptance reports (`70`
  implemented, `86` satisfied, `0` validation errors). No compose/Postgres
  smoke was needed because this slice only shapes existing operator storage
  metrics and validates them through in-memory snapshot/API coverage.
- 2026-06-05: Observatory schedules now have content-safe drill-down evidence
  instead of remaining list-only scheduler cockpit records. The sidecar
  schedule collection shapes schedules through a redacted admin record with
  stable schedule IDs, cadence, enabled state, misfire policy, payload key
  names, and payload hash identity while withholding raw schedule payloads; the
  generic `/admin/api/v1/objects/schedule/{id}` and `scheduler_schedule` alias
  resolve the same redacted schedule microscope through the existing scheduler
  store. This advances core handoff Sections 26.2-26.4 and Observatory
  Sections 7.6, 7.7, 8.17, 12.6, 13.1, and 16.1 by closing the schedule
  aggregate-to-evidence path without adding scheduler mutation authority or
  exposing raw job payload content. Validation passed with focused schedule/job
  microscope coverage (`2 passed`), `uv run ruff check sidecar`, `uv run
  pytest` (`381 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, and core and Observatory acceptance reports (`70`
  implemented, `86` satisfied, `0` validation errors). No compose/Postgres
  smoke was needed because this slice only reshapes the existing scheduler read
  path and validates it through an in-memory scheduler store.
- 2026-06-05: Observatory generic object microscopes now resolve
  `job`/`scheduler_job` links through the existing sidecar scheduler job
  read model instead of falling through to the snapshot placeholder. The
  shared job microscope keeps `/admin/api/v1/jobs/{job_id}` and
  `/admin/api/v1/objects/job/{id}` behavior aligned, exposes trace/span
  downstream refs for job provenance, and preserves the redacted/no-raw-content
  object policy without adding scheduler mutation authority. This advances
  core handoff Sections 26.2-26.3 and 28.2 plus Observatory Sections 1.9,
  21.16, 21.27, and 24.27 by closing the drill-down path from audited
  revocation/provenance job refs to scheduler job evidence. Validation passed
  with focused job object microscope coverage (`1 passed`), `uv run ruff check
  sidecar`, `uv run pytest` (`380 passed`), `uv run python -m compileall -q
  sidecar`, `docker compose config --quiet`, `git diff --check`, and core and
  Observatory acceptance reports (`ready=true`, `70` implemented and `86`
  satisfied, `0` validation errors). No compose/Postgres smoke was needed
  because this slice only aliases an existing scheduler read model and
  validates it through an in-memory job store.
- 2026-06-05: Observatory artifact drill-downs now resolve UUID-backed
  `artifact`/`compiled_artifact` aliases through the existing content-safe
  context-artifact read model instead of dead-ending at the placeholder
  artifact microscope. The dedicated `/admin/api/v1/artifacts/{id}` route
  opportunistically returns governed context artifact detail for UUID context
  artifact IDs, and `/admin/api/v1/objects/artifact/{id}` plus
  `/admin/api/v1/objects/compiled_artifact/{id}` reuse the same context
  governance lookup while preserving the explicit missing-read-model payload
  for unsupported artifact records. This advances core Section 1.4 and
  Observatory Sections 7.6, 7.7, and 8.12 by closing the context-artifact
  aggregate-to-evidence path without exposing compiled text or adding UI-local
  mutation authority. Validation passed with focused context-compiler
  Observatory coverage (`1 passed`), `uv run ruff check sidecar`, `uv run
  pytest` (`379 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, `git diff --check`, and core and Observatory
  acceptance reports (`ready=true`, `70` implemented, `7` context criteria,
  `86` Observatory criteria/checklist items satisfied, `0` validation errors).
  No compose/Postgres smoke was needed because this slice only reuses the
  existing context-governance read path and in-memory test store.
- 2026-06-05: Observatory object microscopes now resolve `trace` refs through
  the observability store instead of falling through to the generic snapshot
  placeholder. The shared trace-detail microscope exposes the ordered
  content-safe span timeline, downstream object refs, operation/status
  summaries, and explicit raw-span denial metadata, and the dedicated
  `/admin/api/v1/traces/{trace_id}` route now reuses the same payload builder.
  This advances core handoff Sections 28.2 and 28.3 plus Observatory Sections
  7.6, 7.7, 8.20, 12.6, 16.1, and 21.16 by making trace refs emitted by model,
  broker, writer, event, and replay microscopes directly traversable through
  the canonical object route without re-executing work or adding mutation
  authority. Validation passed with focused trace/object microscope coverage
  (`1 passed`), focused ruff checks, `uv run ruff check sidecar`, `uv run
  pytest` (`379 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, `git diff --check`, and core and Observatory
  acceptance reports (`ready=true`, `70` implemented and `86` satisfied, `0`
  validation errors). No compose/Postgres smoke was needed because the slice
  only reuses the existing observability-store read path and validates it
  through the in-memory trace store.
- 2026-06-05: Observatory object microscopes now resolve deterministic
  `writer_transaction` links through governance-backed evolution transaction
  rows instead of forcing operators to infer writer state from generic
  transaction detail or trace replay alone. The new microscope exposes
  content-safe writer metadata including manifest hash, active relative path,
  file count, previous snapshot pointer, staged manifest path, activation
  deferral/window status, bounded transaction items, rollback operation names,
  and audit links while withholding raw metric payloads, raw activation-window
  notes, raw idempotency/cause text, raw generated skill text, and arbitrary
  rollback instructions. This advances core handoff Sections 1.2, 25, and
  28.2 plus Observatory Sections 7.6, 7.7, 8.15, 12.6, 13.1, and 16.1 by
  making deterministic writer apply/rollback evidence traversable through the
  sidecar object microscope without adding any runtime mutation authority.
  Validation passed with focused writer/evolution microscope coverage (`2
  passed`), focused ruff checks, `uv run ruff check sidecar`, `uv run pytest`
  (`379 passed`), `uv run python -m compileall -q sidecar`, `docker compose
  config --quiet`, `git diff --check`, and core and Observatory acceptance
  reports (`ready=true`, `70` implemented and `86` satisfied, `0` validation
  errors). No compose/Postgres smoke was needed because the slice only adds a
  content-safe read-model alias over existing governance transaction lookups.
- 2026-06-05: Observatory object microscopes now resolve
  `revocation_request` links to content-safe rollback/revocation request
  detail backed by the governance store instead of falling through to the
  generic snapshot object. The governance store exposes a workspace-filtered
  `get_revocation_request` lookup; the object route returns request kind/status,
  root object, created-by job, timeline, bounded impacted object refs, bounded
  provenance edges, rollback transaction refs, and numeric/boolean invalidation
  counters while withholding raw traversal metadata, raw operator/source text,
  raw generated skill text, raw edge notes, and arbitrary invalidation strings.
  This advances core handoff Sections 1.2 and 2.26 rollback/derived-data
  revocation requirements plus Observatory Sections 7.6, 7.7, 8.16, 12.6,
  13.1, and 16.1 by making derived-state revocation status traversable through
  the sidecar object microscope without adding any runtime mutation authority.
  Validation passed with focused governance/rollback Observatory coverage (`3
  passed`) and worker/governance revocation coverage (`3 passed`), `uv run ruff
  check sidecar`, `uv run pytest` (`378 passed`), `uv run python -m compileall
  -q sidecar`, `docker compose config --quiet`, `git diff --check`, core and
  Observatory acceptance reports (`ready=true`, `70` implemented and `86`
  satisfied, `0` validation errors), and an isolated compose/Postgres smoke on
  port `59621` that migrated a fresh database, queued one rollback revocation
  request through `AsyncpgGovernanceStore`, fetched it by workspace/request ID,
  verified workspace isolation, completed it, refetched completed status, and
  removed the temporary compose project/volume.
- 2026-06-05: Observatory scanner findings now have a content-safe detail
  microscope instead of remaining list-only scanner cockpit records. The
  scanner station record is normalized as a stable `scanner_finding` object,
  `/admin/api/v1/scanner-findings/{finding_id}` returns the same object
  microscope shape as the generic `/admin/api/v1/objects/scanner_finding/{id}`
  path, and the payload exposes scanner component health, reason codes, data
  quality, bounded scanner-reject counts, upstream scanner-gate provenance, and
  the downstream `gates-cover-writer-activation` invariant without raw artifact
  or skill content. This advances core handoff Section 24 scanner/security
  diagnostics plus Observatory Sections 7.6, 7.7, 8.13, 12.1, 12.6, 13.1, and
  16.1 by closing the drill-down path from scanner pressure aggregates to
  governed sidecar evidence. Validation passed with focused scanner microscope
  coverage (`2 passed`), generated Observatory OpenAPI client `--check`, `uv
  run ruff check sidecar`, `uv run pytest` (`377 passed`), `uv run python -m
  compileall -q sidecar`, `docker compose config --quiet`, `git diff --check`,
  and core and Observatory acceptance reports (`ready=true`, `70` implemented
  and `86` satisfied, `0` validation errors). No compose/Postgres smoke was
  needed because the slice only shapes an existing snapshot-backed scanner read
  model and does not touch persistence.
- 2026-06-05: Observatory object microscopes now resolve `evaluation`,
  `evaluation_run`, and `probe_evaluation` links through the existing
  evaluator read model instead of falling through to the generic snapshot
  fallback. The generic object route reuses the content-safe evaluation
  microscope behind `/admin/api/v1/evaluations/{evaluation_id}`, preserving
  autonomy-assurance diagnostics, hard-invariant failures, soft-threshold
  misses, fallback actions, skill-version provenance refs, and raw-content
  denial metadata without adding any UI-local evaluator authority. This
  advances core handoff Section 23 evaluator/probe acceptance behavior plus
  Observatory Sections 7.6, 7.7, 8.14, 12.6, and 21.16/21.22 by making
  aggregate evaluation/probe refs drill into the governed sidecar record.
  Validation passed with focused Observatory evaluation microscope coverage
  (`1 passed`), `uv run ruff check sidecar`, `uv run pytest` (`376 passed`),
  `uv run python -m compileall -q sidecar`, `docker compose config --quiet`,
  `git diff --check`, and core and Observatory acceptance reports
  (`ready=true`, `70` implemented and `86` satisfied, `0` validation errors).
  No compose/Postgres smoke was needed because the slice only reuses the
  existing evaluator-store list/read path and in-memory route coverage.
- 2026-06-05: Observatory object microscopes now resolve
  `broker_decision`/`retrieval_log` links to the same content-safe retrieval-log
  detail used by `/admin/api/v1/broker/decisions/{id}` instead of falling
  through to a generic snapshot object. Broker decision detail construction is
  shared across both routes and now allowlists candidate/suppression refs plus
  scalar diagnostic identity while withholding raw retrieval queries, raw
  candidate summaries, raw suppression context, and arbitrary metadata values.
  This advances core handoff Sections 7-8 runtime-broker/sidecar requirements
  plus Observatory Sections 7.6, 7.7, 8.7, 8.20, 12.6, 16.1, and 21.16 by
  making broker-quality aggregates and replay-episode provenance links
  traversable through the sidecar object microscope without adding UI-local
  authority. Validation passed with focused broker-decision microscope coverage
  (`1 passed`), focused ruff checks, `uv run ruff check sidecar`, `uv run
  pytest` (`376 passed`), `uv run python -m compileall -q sidecar`, `git diff
  --check`, `docker compose config --quiet`, and core and Observatory
  acceptance reports (`ready=true`, `70` implemented and `86` satisfied, `0`
  validation errors). No compose/Postgres smoke was needed because this slice
  reuses existing retrieval-store read paths and exercises them through the
  in-memory retrieval store.
- 2026-06-05: Observatory object microscopes now resolve
  `action_attribution_check` links from admin action receipts to content-safe
  deterministic boundary-check detail instead of falling through to a generic
  snapshot object. The attribution store exposes a workspace-filtered lookup by
  action-attribution check ID; the admin object route returns verdict, risk
  tier, hashed user intent/idempotency identity, bounded contributing
  skill/memory/evidence and broker-policy refs, reason codes, target refs, and
  source-presence flags while withholding raw operator reason text,
  confirmation text, metadata values, raw IP/proxy values, and arbitrary metric
  payloads. This advances core handoff Sections 1.2, 27, and 28.2 plus
  Observatory Sections 7.6, 7.7, 8.20, 8.22, 12.6, 16.1, and 16.3 by making
  administrative action attribution checks traversable through the sidecar
  object microscope without adding UI-local authority. Validation passed with
  focused action-attribution microscope coverage (`1 passed`), broader
  Observatory action/attribution coverage (`9 passed`), focused ruff checks,
  `uv run ruff check sidecar`, `uv run pytest` (`376 passed`), `uv run python
  -m compileall -q sidecar`, `docker compose config --quiet`, `git diff
  --check`, core and Observatory acceptance reports (`ready=true`, `70`
  implemented and `86` satisfied, `0` validation errors), and an isolated
  compose/Postgres smoke on port `59489` that migrated a fresh database, wrote
  one action-attribution check through `AsyncpgAttributionStore`, fetched it by
  workspace/check ID, verified workspace isolation, and removed the temporary
  compose project/volume.
- 2026-06-05: Observatory object microscopes now resolve
  `llm_invocation` links to content-safe model-call audit detail instead of
  falling through to a generic snapshot object. The LLM invocation store exposes
  a bounded lookup by workspace and invocation ID; the admin object route returns
  purpose, model/profile route identity, thinking fallback state, token
  estimates, status, trace/span refs, allowlisted endpoint/finish metadata, and
  hashed provider request/error identity while withholding raw provider errors,
  prompt/response text, API keys, endpoint URLs, arbitrary audit payloads, and
  cost analytics. This advances core handoff Sections 3.2.7, 3.3, 5.12,
  13.8.12, and 28.2 plus Observatory Sections 7.6, 7.7, 8.18, 12.6, 13.1,
  16.1, and 16.3 by making the model/embedding profile qualification refs
  traversable through sidecar-hosted audit evidence. Validation passed with
  focused profile/invocation microscope coverage (`2 passed`), broader
  Observatory/LLM/profile coverage (`53 passed`), focused ruff checks, `uv run
  ruff check sidecar`, `uv run pytest` (`376 passed`), `uv run python -m
  compileall -q sidecar`, `docker compose config --quiet`, `git diff --check`,
  core and Observatory acceptance reports (`ready=true`, `70` implemented and
  `86` satisfied, `0` validation errors), and an isolated compose/Postgres smoke
  on port `56547` that migrated a fresh database, wrote one LLM invocation
  through `AsyncpgLLMInvocationStore`, fetched it by workspace/invocation ID,
  verified workspace isolation, and removed the temporary compose project/volume.
- 2026-06-05: Observatory model/embedding profile cockpits now have
  content-safe detail microscopes instead of list-only profile visibility.
  The profile qualification store exposes bounded recent run reads by
  workspace/profile key; `/admin/api/v1/model-profile/{profile_key}`,
  `/admin/api/v1/embedding-profile/{profile_key}`, and generic
  `model_profile`/`embedding_profile` object microscope aliases return
  redacted effective profile configuration, route/status metadata, latest
  qualification verdict pointers, allowlisted checklist outcomes, safe metrics
  such as token estimates and embedding similarity probes, and LLM invocation
  object refs without raw endpoint URLs, API keys, raw probe errors, raw prompt
  or response text, cost analytics, or provider payloads. This advances core
  handoff Phase 4 text/embedding profile qualification and invocation-audit
  acceptance plus Observatory Sections 7.6, 7.7, 8.18, 12.1, 12.6, 13.1,
  16.1, and 16.3. Validation passed with focused profile microscope coverage
  (`2 passed`), broader Observatory/profile coverage (`57 passed`), generated
  Observatory OpenAPI client `--check`, `uv run ruff check sidecar`, `uv run
  pytest` (`375 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, `git diff --check`, core and Observatory acceptance
  reports (`ready=true`, `70` implemented and `86` satisfied, `0` validation
  errors), and an isolated compose/Postgres smoke on port `56533` that migrated
  a fresh database, wrote model and embedding profiles plus qualification runs
  through the asyncpg stores, read both run families through the new bounded
  list methods (`1`, `1`), and removed the temporary compose project/volume.
- 2026-06-05: Observatory object microscopes now resolve
  `evolution_transaction` links to content-safe governance transaction detail
  instead of falling through to a generic snapshot object. The governance store
  exposes a bounded transaction lookup by workspace and transaction ID; the
  admin object route returns transaction status/timeline, source evidence/memory
  refs, downstream transaction items, rollback-operation names, hashed
  idempotency identity, policy keys, and allowlisted topology/data-to-skill
  metrics while withholding raw cause text, raw metric payloads, raw evidence,
  and arbitrary rollback payload text. This advances core handoff Sections 1.2,
  17.1, 28.2, and 28.3 plus Observatory Sections 7.6, 7.7, 11.1, 12.6, 13.1,
  16.1, and 16.3 by making transaction-level why/provenance drill-down a real
  sidecar read model. Validation passed with focused evolution-transaction
  microscope coverage (`1 passed`), focused topology read-model coverage (`2
  passed`), Observatory acceptance-report tests (`9 passed`), focused ruff
  checks, `uv run ruff check sidecar`, `uv run pytest` (`374 passed`), `uv run
  python -m compileall -q sidecar`, `docker compose config --quiet`, core and
  Observatory acceptance reports (`ready=true`, `70` implemented and `86`
  satisfied, `0` validation errors), and an isolated compose/Postgres smoke on
  port `56521` that migrated a fresh database, wrote/read a
  `topology_compose` transaction and transaction item through
  `AsyncpgGovernanceStore`, verified the fetched workspace/metrics/item, and
  removed the temporary compose project/volume.
- 2026-06-05: Topology proposal persistence now records a content-safe
  data-to-skill trace capsule inside the governing `topology_*`
  `evolution_transactions.metrics` record. The trace exposes stage names,
  statuses, reason codes, bounded object refs, terminal stage, and non-skill
  failure exit for source/evidence packet, operation candidate/plan,
  SkillGraphIR revision, artifact-plan, evaluation/trial, transaction, and
  propose-only activation/broker-outcome phases without storing raw evidence,
  SkillIR/SkillGraphIR bodies, skill text, or operator content. The
  Observatory topology transaction-review read model now allowlists the trace
  into `/admin/api/v1/topology` while stripping arbitrary raw fields from
  transaction metrics. This advances core handoff Sections 1.2, 13.8.10,
  13.8.11, 13.8.12, and 17.1-17.9 plus Observatory Sections 7.6, 7.7, 8.9,
  8.10, 12.6, 13.1, and 16.1. Validation passed with topology
  persistence/read-model tests (`2 passed`), focused ruff checks, `uv run ruff
  check sidecar`, `uv run pytest` (`373 passed`), `uv run python -m compileall
  -q sidecar`, `docker compose config --quiet`, `git diff --check`, `uv run
  python scripts/autoskill_acceptance.py --json` (`ready=true`, `70`
  implemented, `0` validation errors), `uv run python
  scripts/autoskill_observatory_acceptance.py --json` (`ready=true`, `86`
  satisfied, `0` validation errors), and a real compose/Postgres smoke on port
  `56509` that migrated a fresh database, persisted a `topology_compose`
  proposal through `AsyncpgTopologyStore`/`AsyncpgGovernanceStore`, read the
  stored trace back through authenticated `/admin/api/v1/topology`, verified
  the operation/trial refs (`5` trials, `11` trace stages), and removed the
  temporary compose project/volume.
- 2026-06-05: Observatory topology cockpit now includes a content-safe
  transaction-review read model derived from `evolution_transactions.metrics`.
  The governance store exposes bounded recent transaction listing by workspace
  and transaction-kind prefix; `/admin/api/v1/topology` now joins topology
  operation metrics with recent `topology_*` transaction capsules showing
  transaction status, plan hash, operation/status, evidence and trial counts,
  trial kinds, SkillGraphIR node/edge counts, effect coverage, rollback
  readiness, write targets, and the trial-before-apply invariant without
  echoing raw plan text, evidence text, skill bodies, confirmation text, or
  raw operator content. This advances core handoff Sections 1.2, 1.3, 9.6,
  9.7, 13.7-13.8, and 17.1-17.9 plus Observatory Sections 7.7, 8.9, 12.1,
  12.6, 13.1, and 16.1 by making topology proposal review visible through
  the sidecar control-plane read model rather than a UI-local interpretation.
  Validation passed with focused topology Observatory API coverage (`1
  passed`), focused ruff checks, `uv run ruff check sidecar`, `uv run pytest`
  (`373 passed`), `uv run python -m compileall -q sidecar`, `docker compose
  config --quiet`, `git diff --check`, `uv run python
  scripts/autoskill_acceptance.py --json` (`ready=true`, `70` implemented,
  `0` validation errors), `uv run python
  scripts/autoskill_observatory_acceptance.py --json` (`ready=true`, `86`
  satisfied, `0` validation errors), and an isolated compose/Postgres smoke on
  port `56452` that migrated a fresh database, wrote a staged
  `topology_compose` transaction with metrics through `AsyncpgGovernanceStore`,
  read it back via the new bounded transaction query, and removed the temporary
  compose project/volume.
- 2026-06-05: Topology proposal persistence now records a content-safe
  transaction review capsule on the governing evolution transaction. Persisted
  create/improve/compose/decompose proposals stamp operation kind/status, plan
  hash, evidence count, planned trial kinds, graph node/edge counts, node-role
  and edge-kind counts, effect coverage count, rollback-blocker/action counts,
  write targets, and the trial-before-apply invariant without storing evidence
  text, skill bodies, or raw SkillGraphIR-only details in transaction metrics.
  This advances core handoff Sections 13.7-13.8 and 17.1-17.9 by making
  topology decisions more inspectable as transaction-scoped control-plane state,
  and supports the Observatory Section 8.9 topology cockpit/read-model contract.
  Validation passed with focused topology tests (`18 passed`), focused ruff
  checks, `uv run ruff check sidecar`, `uv run pytest` (`373 passed`), `uv run
  python -m compileall -q sidecar`, `docker compose config --quiet`, `git diff
  --check`, and an isolated compose/Postgres smoke on port `56432` that migrated
  a fresh database, persisted a compose topology proposal through the real
  asyncpg topology/governance stores, verified the JSONB transaction metrics
  (`operation=compose`, `graph_node_count=3`, `graph_edge_count=2`), and removed
  the temporary compose project/volume.
- 2026-06-05: Observatory administrative actions now write a deterministic
  action-attribution boundary check before the normal audit/action receipt.
  `/admin/api/v1/actions` records a content-safe `action_attribution_checks`
  row with request id, risk tier, policy verdict, hashed intent/idempotency
  values, reason codes, target identity, and source identity metadata without
  storing raw reason text, confirmation text, raw content, or browser payloads.
  Fresh and idempotency-replayed receipts expose only a bounded attribution-check
  link, action-audit microscopes include the check as upstream causality, and
  `/admin/api/v1/actions/summary` reports attribution-check coverage and blocked
  check counts. This advances core handoff Section 1.2 action-attribution gate
  requirements plus Observatory Sections 1.9 and 16.3 by making guarded operator
  actions causally inspectable through the same sidecar audit path. Validation
  passed with focused Observatory action tests (`5 passed`), focused ruff
  checks, `uv run ruff check sidecar`, `uv run pytest` (`373 passed`), `uv run
  python -m compileall -q sidecar`, `git diff --check`, and an alternate-port
  compose/Postgres smoke that applied migrations, recorded one admin action,
  joined `admin_action_audit` to `action_attribution_checks` by the persisted
  safe receipt link (`verdict=allowed`, `risk_tier=low`,
  `raw_content_included=false`), deleted the smoke rows, and removed the
  temporary compose Postgres container.
- 2026-06-05: Observatory administrative action gateway now exposes a
  content-safe aggregate read model at `/admin/api/v1/actions/summary`.
  The summary is derived from bounded `admin_action_audit` receipts and reports
  accepted/rejected counts by action kind, linked audit/job coverage,
  confirmation and role-policy failures, raw-content reveal outcomes,
  high-impact action history, and explicit data-quality limits without exposing
  confirmation text, raw content, or adding mutation authority. New action
  receipts persist redacted `reason_codes` and confirmation-required metadata so
  the cockpit can distinguish policy blocks. This advances Observatory Sections
  4.3, 8.22, 12.1, 12.6, 13.1, and 16.3 while preserving the existing sidecar
  action gateway and audit chain. Validation passed with focused Observatory
  action tests (`4 passed`), Observatory acceptance-report tests (`9 passed`),
  generated OpenAPI client `--check`, `uv run ruff check sidecar`, `uv run
  pytest` (`373 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, `uv run python scripts/autoskill_observatory_acceptance.py
  --json` (`ready=true`, `86` satisfied, `0` validation errors), `uv run python
  scripts/autoskill_acceptance.py --json` (`ready=true`, `70` implemented,
  `0` validation errors), `npm run build --prefix sidecar/autoskill/observatory`,
  and `git diff --check`. No compose/Postgres smoke was needed because this
  slice adds a derived API read model over the existing action-audit store and
  exercises it through the in-memory store.
- 2026-06-05: Observatory guarded action idempotency now returns existing
  content-safe action receipts instead of creating duplicate audit/live-event
  side effects. `/admin/api/v1/actions` fingerprints the redacted request
  shape, checks `admin_action_audit` by actor/action/target/idempotency key
  before appending new records, reports `idempotency-replay` and
  `idempotency-collision` metadata when a retried payload diverges, and keeps
  confirmation text/raw content out of receipts. This advances core handoff
  Sections 5.2-5.3 and 5.12 plus Observatory Sections 4.3, 8.22, 12.6,
  16.3, and 16.4. Validation passed with focused Observatory action tests
  (`5 passed`), focused ruff checks, `uv run ruff check sidecar`,
  `uv run pytest` (`372 passed`), `uv run python -m compileall -q sidecar`,
  `docker compose config --quiet`, `git diff --check`, the Observatory
  acceptance report (`ready=true`, `86` satisfied, `0` validation errors), and
  a compose/Postgres smoke proving async action-audit idempotency lookup/upsert
  replays the same action id and cleans the smoke row.
- 2026-06-05: Deployment readiness and broker-policy review now distinguish
  mere production replay presence from operator-reviewed/source-linked replay
  evidence. `/v1/deployment/readiness` samples the production replay corpus,
  blocks readiness when no `operator-reviewed` replay episode is present, and
  warns when sampled production replay has no source-linked telemetry. Broker
  policy review now exposes the same operator-reviewed/source-linked/telemetry
  counts without replay intent text. This advances the Phase 10 sustained
  replay/canary gate and Observatory replay/canary visibility rules while
  preserving sidecar-state-only, read-only preflight behavior. Validation
  passed with focused deployment-readiness tests (`3 passed`), focused broker
  policy review tests (`2 passed`), `uv run ruff check sidecar`, `uv run
  pytest` (`371 passed`), `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, and `git diff --check`.
- 2026-06-05: Portable Observatory deployment is now modeled as split-container
  from first principles: the core container owns FastAPI admin APIs/live streams
  and reports Observatory frontend serving as owned by the Observatory nginx
  container. That container owns the compiled React static app and proxies
  `/admin/api`, `/admin/live`, and `/admin/live-sse` to core. The legacy core
  static mount and local-development serving mode were removed so development
  changes are validated through normal container rebuild/redeploy behavior.
- 2026-06-04: Implementation and Observatory specs were refreshed, revealing acceptance-crosswalk drift. The executable reports now cover the current main production criteria (`31.1`-`31.63`, plus seven context criteria) and Observatory criteria/checklist (`21.1`-`21.42`, `24.auto.1`-`24.auto.6`, `24.1`-`24.38`). Added automatic broker replay episode synthesis through `/v1/broker/replay-episodes/synthesize`: it records pre-adjudicated redacted telemetry, can synthesize missing redacted intent through the configured text LLM from content-safe retrieval context, repairs stale telemetry-derived episode expectations from source retrieval logs, stores deterministic validation/provenance, and returns explicit hash-only/metadata-only/no-safe-context skip reasons without raw prompt exposure. Live Dev-01 replay validation now matches the stored telemetry-derived corpus at 19/19 after synthesis/repair.
- 2026-06-04: Observatory context compiler cockpit read models now use the persisted context-governance store instead of snapshot placeholder records. The context store exposes bounded list/detail reads for context artifacts, context compile runs, context budget events, and semantic compression trials; `/admin/api/v1/context/artifacts`, `/context/compile-runs`, `/context/budget-events`, `/context/compression-trials`, their detail routes, and generic object-microscope aliases return hashes, statuses, token metrics, evidence/metadata key summaries, and provenance refs without compiled text, raw SkillIR, prompt bodies, raw evidence, or artifact text. This advances core handoff Sections 11.12-11.15 and Observatory Sections 8.12, 12.1, 12.6, and 13.1 while preserving sidecar-hosted read-only authority. Validation passed with focused context/route tests (`2 passed`), generated Observatory OpenAPI client `--check`, focused Observatory API tests (`39 passed`), `uv run ruff check sidecar`, `uv run pytest` (`369 passed`), `uv run python -m compileall -q sidecar`, `npm run build --prefix sidecar/autoskill/observatory`, `docker compose config --quiet`, `git diff --check`, the Observatory acceptance report (`86` satisfied, `0` validation errors), and a real compose/Postgres smoke that applied migrations, recorded/listed/detail-read all four context-governance record families through `AsyncpgContextGovernanceStore`, and stopped the Postgres service afterward.
- 2026-06-04: Observatory threshold-deadlock findings now have a dedicated detail/read-model route at `/admin/api/v1/autonomy/threshold-deadlocks/{decision_id}` plus generic `threshold_deadlock` object-microscope support. The payload is derived from `admin_autonomy_decision_status`, preserves the underlying autonomy-decision reference, exposes a content-safe safe-next-action and provenance path, and keeps raw content unavailable. This advances Observatory Sections 7.6, 7.7, 8.5.3, 12.1, and 12.6 without adding mutation authority or a second control plane. Validation passed with focused Observatory API tests (`38 passed`), generated Observatory OpenAPI client `--check`, `uv run ruff check sidecar`, `uv run pytest` (`368 passed`), `uv run python -m compileall -q sidecar`, `npm run build --prefix sidecar/autoskill/observatory`, `docker compose config --quiet`, `git diff --check`, and the Observatory acceptance report (`86` satisfied, `0` validation errors).
- 2026-06-04: Observatory live-stream fallback envelopes now match the Section 12.3 stream-envelope contract more closely: snapshot and heartbeat events include additive `kind` and `sent_at` fields, aligning them with persisted outbox deltas without changing existing `event_type`, `seq`, `cursor_seq`, or payload behavior. This advances Observatory Sections 12.3, 17.2, and acceptance criterion 11 by keeping WebSocket/SSE fallback reconciliation timestamped and schema-consistent while remaining sidecar-hosted and non-blocking. Validation passed with focused live fallback/SSE tests (`6 passed`), `uv run ruff check sidecar`, `uv run pytest` (`365 passed`), `uv run python -m compileall -q sidecar`, and `docker compose config --quiet`.
- 2026-06-04: Observatory autonomy/evidence read-model primitives are now durable and route-visible: the migration adds status-only `admin_evidence_fidelity_status`, `admin_autonomy_decision_status`, `admin_semantic_adjudication_status`, and `admin_administrative_escalation_status` tables plus bounded lookup indexes; the admin store exposes content-safe list/detail accessors; `/admin/api/v1/evidence/fidelity`, `/raw-vault/summary`, `/adjudications`, `/autonomy/decisions`, `/autonomy/threshold-deadlocks`, and `/escalations` expose those rows without raw evidence, LLM verdict payloads, or mutation authority. This advances Observatory Sections 8.5.1-8.5.3, 12.1, 12.6, 13.3.1, and acceptance items `21.23`, `21.24`, `21.40`, `24.auto.1`, `24.auto.3`, and `24.auto.6`. Validation passed with focused Observatory API tests (`37 passed`), generated OpenAPI client `--check`, `uv run ruff check sidecar`, `uv run pytest` (`367 passed`), `uv run python -m compileall -q sidecar`, `npm run build --prefix sidecar/autoskill/observatory`, `docker compose config --quiet`, `git diff --check`, and a real compose/Postgres smoke that applied migrations, inserted/listed/detail-read the four read-model families, and deleted smoke rows.
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
- Contrastive replay induction now also accepts normalized attribution, canary, broker, and context-token-ledger outcome schemas, so `missing_skill`/`skill_helped`, canary pass/fail, broker no-skill control outcomes, and context-ledger marginal-value evidence can produce deterministic no-skill versus skill-visible intervention replay evidence.
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
- Support artifact context-governance registration is implemented: the
  activation-grade compiler records deterministic declaration-only
  `support_excerpt` context artifacts for each SkillIR support artifact,
  scanner-gates those excerpts, stamps loadability/retrieval-boundary metadata,
  and includes support hashes in the compile manifest/run metadata without
  rendering support-file contents into runtime context by default.
- Usage/topology evidence aggregation is implemented as a maintenance job:
  `usage.aggregate` consumes content-safe retrieval and attribution rows into
  idempotent `skill_usage_windows`, pair/sequence `skill_co_usage_edges`, and
  observed `skill_usage_clusters` with first-pass `compose` recommendations for
  topology consumers.
- Validation passed for usage/topology aggregation and support-artifact context
  registration: focused usage/worker/compiler tests passed, `uv run ruff check
  sidecar`, `uv run pytest` with 220 tests, `uv run python -m compileall -q
  sidecar`, and `git diff --check` passed; a real compose Postgres smoke seeded
  retrieval plus attribution co-use, created 2 usage windows, updated the pair
  edge to `co_usage_count=2`/`success_count=1`/`sequence_count=2`, created 1
  compose usage cluster, and proved the second aggregation pass did not
  increment windows or edge counters.
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
- Validation passed for transaction-audited topology downstream apply: mutation-worker downstream materialization now records rollback-aware transaction items, provenance edges from the originating evolution transaction to the operation/items/touched skills, active transaction status/metrics, and runtime invalidation evidence after lifecycle/edge effects are applied. Focused worker validation proved 3 governance items, 6 provenance edges, transaction status `active`, 2 lifecycle updates, and 1 materialized edge for an `improve` operation; final gates `uv run ruff check sidecar`, `uv run pytest` with 301 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed; a real compose Postgres smoke ran the mutation worker once and persisted 3 transaction items/6 provenance edges while archiving the subject skill, activating the successor skill, and materializing one `supersedes` edge.
- Validation passed for topology downstream apply trace spans: mutation-worker `topology.apply_downstream` jobs now start a content-safe child `topology` span under the queued job trace/span, record job and skill-graph-operation object refs, and close with bounded lifecycle, graph-edge, governance, provenance, and runtime-invalidation counts. Focused worker validation passed, and final gates `uv run ruff check sidecar`, `uv run pytest` with 301 tests, `uv run python -m compileall -q sidecar`, and `git diff --check` passed.
- Validation passed for variable-dimension profile-scoped embedding storage: `autoskill.embeddings.embedding` now uses unbounded pgvector storage with `embedding_dim`, search/recall filter by dimension before distance comparisons, the default 1536 path keeps an expression HNSW index, and a real compose Postgres smoke stored and searched an 8-dimensional qualified profile embedding.
- Validation passed for conservative broker vector fusion: retrieval now has a semantic pgvector query path that hydrates embedding hits into normal runtime candidates, the broker can merge lexical/vector/graph candidates before compatibility and selection gates, runtime API wiring resolves the active qualified embedding profile when present and falls back to local deterministic hash embeddings otherwise, focused broker/retrieval tests passed, and real compose/Postgres smokes returned vector-matched body-index skill candidates.
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
- Validation passed for active-profile semantic broker routing: `/v1/runtime/context-hint` and broker policy replay now pass the active qualified embedding profile and profile ID into semantic retrieval, allowing the live Qwen profile to recover natural paraphrases that strict lexical matching misses. Focused broker regression passed, full validation passed with `uv run ruff check sidecar scripts`, `uv run pytest -q` with 301 tests, `uv run python -m compileall -q sidecar scripts`, `npm test --prefix plugin/autoskill` with 18 tests, `docker compose config --quiet`, and `git diff --check`; the rebuilt Dev-01 sidecar returned `skill_hint` with `vector-fused` for `fix unreadable labels in a generated diagram`, while broker replay remained 6/6 with no degradation and Qwen recall audit sampled 10 with `avg_recall=1.0`.
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
- Usage/topology cluster recommendation scoring is implemented: `usage.aggregate`
  now returns ranked content-safe topology recommendations from observed
  `skill_usage_clusters`, with fail-closed blockers for insufficient support,
  missing successful outcomes, high failure ratio, weak sequence evidence, and
  unsupported topology operations. Focused usage/worker tests passed, and full
  validation passed with `uv run ruff check sidecar`, `uv run pytest` (222
  tests), `uv run python -m compileall -q sidecar`, and `git diff --check`.
- Usage/topology recommendation consumption is implemented for propose-only
  compose planning: control-authenticated `/v1/topology/propose-from-usage`
  reads ranked usage recommendations, converts accepted recurring co-usage
  clusters into existing topology proposal/persistence records, and returns
  blocked or unsupported improve/decompose signals as explicit skipped records
  until their upstream recommendations carry enough subject/successor structure.
  Validation passed with focused topology/usage tests, full sidecar tests,
  ruff, compileall, plugin check/tests, compose config, and diff hygiene.
- Usage/topology recommendations now carry deterministic improve/decompose
  signals from single-skill negative evidence and context-waste outcomes:
  `usage.aggregate` ingests `context_token_ledgers` as content-safe usage
  windows, emits subject-scoped `improve` clusters for repeated harmful
  outcomes, emits subject-scoped `decompose` clusters for false-positive or
  ignored context loads, and records `broker_abstain`/`tighten_description` as
  suggested context actions without adding any autonomous mutation path.
  Validation passed with focused usage tests, `uv run ruff check sidecar`,
  `uv run pytest` (230 tests), `uv run python -m compileall -q sidecar`,
  `git diff --check`, and a real Compose Postgres smoke that created 6 windows,
  2 clusters, and accepted `improve` plus `decompose` recommendations.
- Runtime guard-template SkillIR support is implemented as declarative,
  preapproved controls only: generated skills can declare fixed guard templates
  such as capability warnings, verify-only checks, sibling-disambiguation hints,
  and drift blocks; the compiler renders them into runtime skill text and records
  guard metadata in context-governance artifacts without accepting arbitrary
  executable guard code.
- Dev-01 deployment was refreshed at commit `219ffad`: `docker compose up
  --build -d` rebuilt/recreated the sidecar and worker stack while preserving the
  compose Postgres volume, the OpenClaw gateway was restarted, live plugin
  inspection with `--runtime` reported `status=loaded`, `imported=true`,
  `hookCount=11`, and no diagnostics, and sidecar logs showed fresh
  `/v1/ingest/events` plus `/v1/runtime/context-hint` 200s after restart.
  Operational validation passed with `uv run ruff check sidecar scripts`,
  `uv run pytest -q` (227 tests), `uv run python -m compileall -q sidecar
  scripts`, `npm test --prefix plugin/autoskill` (18 tests), `npm run check
  --prefix plugin/autoskill`, `docker compose config --quiet`, and `git diff
  --check`. Live Dev-01 readiness returned `ready=true`, stored broker replay
  matched 6/6 under `dev-01-canary.v1`, production embedding validation qualified
  `llama-cpp-embeddings-nomic` and generated one embedding, red-team scanning
  passed 9/9, a corrected UUID/trust-shaped ingest smoke accepted one
  `operator_smoke` event, the runtime context-hint smoke returned `no_skill`
  fail-closed for an empty candidate set, the local spool was empty, and backup
  plus restore dry-run verified `autoskill-backup-20260602T195700Z`.
- Dev-01 writer deployment remediation and first runtime activation proof passed:
  the sidecar service now mounts `/home/kklouzal/.openclaw/workspace` at
  `/workspace` and runs with `working_dir: /workspace`, matching the worker root
  and preventing writer apply from targeting the container image filesystem. The
  first SkillKernel-owned runtime smoke skill,
  `autoskill-first-runtime-smoke`, was compiled through
  `/v1/context/compile-skillir`, staged with context-governance proof, applied
  as v1, applied as v2 to force an archive snapshot, and rolled back to v1 from
  `.autoskill/archive`; the active file is now
  `skills/autoskill/autoskill-first-runtime-smoke/SKILL.md`, and `openclaw
  skills list --json` reports it eligible/model-visible from the
  `openclaw-workspace` source. A fresh backup with active/archive/staging roots
  present was verified by restore dry-run as
  `autoskill-backup-20260602T201150Z`. Post-remediation validation passed with
  `uv run ruff check sidecar scripts`, `uv run pytest -q` (227 tests), `uv run
  python -m compileall -q sidecar scripts`, `npm test --prefix plugin/autoskill`
  (18 tests), `npm run check --prefix plugin/autoskill`, `docker compose config
  --quiet`, and `git diff --check`. Live checks after the mount fix showed
  readiness `ready=true`, plugin `typedHookCount=11` with no diagnostics, empty
  spool, no recent sidecar errors, stored broker replay matched 9/9 with no
  degradation, red-team scanning passed 9/9, and
  `llama-cpp-embeddings-nomic` remained qualified while generating one
  embedding.
- Historical import/bootstrap substrate is implemented for the requested
  `unified-implementation-specification.md` Phase 5 gap: the schema now has
  first-class `historical_import_sources` and `historical_import_chunks` rows
  with source kind, source key, fingerprint, parser version, redaction policy,
  trust/taint, status, content hash, token estimate, and idempotent uniqueness;
  the sidecar exposes control-authenticated
  `/v1/historical-import/sources` list/upsert and
  `/v1/historical-import/chunks` record endpoints; and the asyncpg store
  supports source inventory, idempotent update, storage-time text redaction,
  content-hash verification, redacted chunk recording, and duplicate skip
  semantics. Validation passed with focused tests, full `uv run ruff check
  sidecar scripts`, `uv run pytest` (235 tests), `uv run python -m compileall
  -q sidecar scripts`, `npm test --prefix plugin/autoskill` (18 tests), `npm
  run check --prefix plugin/autoskill`, `docker compose config --quiet`, `git
  diff --check`, idempotent compose Postgres migration, and a DB-backed smoke
  proving source create/update, storage-time secret/email redaction plus hash
  identity, chunk create, duplicate skip, and imported-source listing.
- Historical chunks now feed the governed evidence/retrieval substrate instead
  of remaining inert inventory: `evidence.derive` derives tainted
  `historical_chunk_observation` evidence from observed historical chunks,
  records provenance from `historical_import_chunk` to `evidence_item`, includes
  historical observations in recurring-evidence clustering, and embedding source
  discovery exposes observed historical chunks as `historical_import_chunk`
  sources under the normal profile-scoped embedding path. Validation passed with
  focused evidence/embedding tests, full `uv run ruff check sidecar scripts`,
  `uv run pytest -q` (235 tests), `uv run python -m compileall -q sidecar
  scripts`, `npm test --prefix plugin/autoskill` (18 tests), `npm run check
  --prefix plugin/autoskill`, `docker compose config --quiet`, `git diff
  --check`, and a compose Postgres smoke proving historical chunk evidence
  derivation plus pending historical embedding-source discovery.
- Historical import discovery and source revocation are now implemented as the
  next Phase 5/14 layer: `historical_import.discover` performs bounded,
  read-only inventory over operator-configured roots; classifies session stores,
  transcripts, trajectories, memory/context files, taskflow records, diagnostics,
  and existing skills; records byte/time/risk/source-count summaries; hashes
  paths instead of persisting raw paths; supports preview-only, allow/deny,
  max-file, and max-byte controls; can upsert inventory-only source rows; and
  exposes both API and worker/CLI scheduling surfaces. Historical source
  revocation now tombstones the source and its chunks. Focused validation passed
  with historical discovery/revocation API, service, schedule, and worker tests;
  full validation passed with `uv run ruff check sidecar scripts`, `uv run
  pytest -q` (242 tests), `uv run python -m compileall -q sidecar scripts`,
  `npm test --prefix plugin/autoskill` (18 tests), `npm run check --prefix
  plugin/autoskill`, `docker compose config --quiet`, `git diff --check`,
  idempotent compose Postgres migration, and a DB-backed smoke proving discovery
  upsert, chunk redaction, and source/chunk revocation.
- Historical structured import parsing and checkpointing now exists as the next
  Phase 5/14 layer: `historical_import.parse` runs through the control API or
  maintenance worker, carries raw file paths only transiently during authorized
  configured-root scans, records `historical_import_runs` checkpoint/stat rows,
  upserts imported sources, records redacted chunks, and supports duplicate-safe
  reruns. The first parser set covers transcript JSONL turns, Markdown memory,
  workspace-context, taskflow sections, session-store metadata, trajectory or
  diagnostic JSON summaries, and existing-skill sections as read-only external
  skill evidence. Focused validation passed with parser/service/API/worker
  tests; full validation passed with `uv run ruff check sidecar scripts`, `uv
  run pytest -q` (246 tests), `uv run python -m compileall -q sidecar scripts`,
  `npm test --prefix plugin/autoskill` (18 tests), `npm run check --prefix
  plugin/autoskill`, `docker compose config --quiet`, `git diff --check`,
  idempotent compose Postgres migration, and a DB-backed smoke proving
  transcript/memory parse, run checkpoint completion, redaction, and
  duplicate-safe rerun behavior.
- Historical transcript-corpus export parsing is implemented as a distinct
  Phase 5/14 datasource slice: discovery classifies `metadata.json`,
  `summary.md`, and `transcript.jsonl` corpus files as `transcript_corpus`,
  the migration/store validator accepts that source kind, metadata chunks keep
  only safe keys, summary chunks are marked lossy/derived, and transcript turns
  preserve direct-turn evidence while redacting storage text and never storing
  raw paths.
- Historical source revocation now propagates into the provenance-backed
  revocation system instead of only tombstoning import rows: chunk recording
  writes `historical_import_source` -> `historical_import_chunk` provenance
  edges, the revoke API previews traversal, queues an `operator_revoke`
  revocation request plus `revocations.invalidate` mutation job, and the generic
  invalidation worker completes non-rollback revocations without requiring
  writer archive roots. Focused tests and a real Postgres smoke passed with a
  source -> chunk -> evidence traversal of 3 impacted objects and one completed
  invalidation request.
- Historical datasource coverage now includes metadata-only plugin and media
  import surfaces: discovery classifies plugin package manifests, hook
  manifests, plugin source files, media artifacts, and observability exports;
  parsing stores only safe metadata chunks for plugin/source/media files,
  taints plugin/control-plane and body-not-imported surfaces, redacts manifest
  metadata, and continues to avoid raw path storage.
- `create` is now a first-class propose-only topology operation alongside
  improve/compose/decompose: `CreateTopologyRequest` produces SkillGraphIR,
  rollback actions, target/no-skill/collision/rollback trial plans, governance
  transaction metadata, and `/v1/topology/propose` persistence through the
  existing topology operation/trial path. Focused topology/admin tests passed.
- Topology operations now have the separate operator metrics surface required
  by the handoff spec: `/v1/topology/metrics` reports create/improve/compose/
  decompose operation counts independently, includes planned-trial status
  breakdowns by operation kind and trial kind, and returns bounded recent
  operation samples without activating or mutating topology state.
- Bounded audit integrity checks now verify partial recent windows as anchored
  hash-chain segments instead of incorrectly requiring the oldest returned row
  to be the genesis record; full-chain verification semantics remain available
  by using a genesis-anchored record list.
- Accepted single-skill usage recommendations now feed propose-only topology
  planning for `improve` and `decompose` as well as `compose`: repeated
  negative-outcome clusters become improvement successors with deterministic
  target/regression/rollback trials, context-waste/false-positive clusters
  become two-successor decomposition proposals with broker replay/canary trials,
  and persistence still writes only topology/governance/trial records without
  staging or activating runtime files. Focused topology tests passed, then `uv
  run ruff check sidecar`, `uv run pytest` (255 tests), `uv run python -m
  compileall -q sidecar`, and `git diff --check` passed.
- Usage-derived improve/decompose proposals now hydrate current SkillIR effect
  signatures instead of placeholder-only nodes, preserve failure/idempotency
  metadata, and persist contract/body-index/description presence plus measured
  context-value/token-waste signals into deterministic trial expectations.
- Historical import now records compact per-chunk source-item lineage metadata
  and parses TaskFlow JSON/JSONL ledgers as metadata-only, redacted, tainted
  task records with hashed record locators instead of Markdown-like blobs.
  Validation passed with `uv run ruff check sidecar`, `uv run pytest` (256
  tests), `uv run python -m compileall -q sidecar`, `npm test --prefix
  plugin/autoskill` (18 tests), and `git diff --check`.
- Broker policy/audit review is now implemented as the remaining Phase 9
  operator review surface: `/v1/broker/policies/review` summarizes active
  policy state, replay-corpus coverage, production-tagged replay coverage,
  latest critical feedback, and bounded audit-chain verification without
  mutating retrieval or runtime context state. Focused validation passed with
  broker-policy API tests and focused ruff checks.
- Historical bootstrap consolidation is now implemented for the Phase 4.75/Next
  Gate 3 gap: `/v1/historical-bootstrap/consolidate` and maintenance job
  `historical_bootstrap.consolidate` filter to historical chunk observations and
  historical-tainted recurring clusters, run existing active/archive/external
  duplicate matching before candidate proposal, return propose-only candidates
  with cited historical evidence IDs, and optionally persist inactive candidate
  rows through the existing governance/candidate/probe path without writing
  runtime skill files.
- Historical source-item lineage now has a v2 content-safe locator layer:
  parsed historical chunks carry stable source-item locator hashes, item-key
  hashes, item kind, chunk kind/index, optional record index, and optional
  line-range hashes while preserving the no-raw-path storage rule.

## Latest Validated Increment

- Phase 9 drift-governance hardening now includes diagnostic momentum
  consumption: `drift.check` worker jobs record content-safe diagnostic
  momentum, unscoped diagnostic records now aggregate correctly with a
  `NULLS NOT DISTINCT` uniqueness constraint, and mutation-worker
  `repair.execute` jobs can claim ready-for-probe/ready-for-patch diagnostic
  momentum as fail-closed repair sources. Claimed diagnostics record a
  governance transaction/provenance item and queue a drift recheck for drift
  diagnostics or an evaluator gate for other diagnostics unless a future
  policy-approved staged manifest exists. Validation passed with focused worker
  tests and ruff checks, full `uv run ruff check sidecar scripts`, `uv run
  pytest` with 263 tests, `uv run python -m compileall -q sidecar scripts`,
  `npm test --prefix plugin/autoskill` with 18 tests, `npm run check --prefix
  plugin/autoskill`, `docker compose config --quiet`, and `git diff --check`.
  Real Compose/Postgres smokes verified migration idempotency, the diagnostic
  status/unique constraints, unscoped diagnostic aggregation, and
  ready-record claim/complete flow to `repair_queued`.
- SkillGraphIR compose precondition attribution is now corrected for
  multi-component workflows: required-effect edges point to the nearest previous
  component that actually produced each required effect instead of defaulting to
  the first component. Validation passed with focused topology tests, focused
  ruff checks, full `uv run ruff check sidecar`, `uv run pytest -q` with 264
  tests, `uv run python -m compileall -q sidecar`, and `git diff --check`.
- Create/improve topology proposals now carry the required broker/routing gates
  for broker-visible or active-routing changes: both operation classes plan
  broker replay plus broker canary trials in addition to target/regression and
  rollback checks, and topology plan hashes now include trial and rollback
  shapes so changed gates cannot reuse stale idempotency keys. Validation passed
  with focused topology/admin tests, focused ruff checks, full `uv run ruff
  check sidecar`, `uv run pytest -q` with 264 tests, `uv run python -m
  compileall -q sidecar`, `git diff --check`, `npm test --prefix
  plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Description minimization is now enforced as an activation-grade context gate:
  context-governed SkillIR compilation rejects broad descriptions that lack the
  required action, `use when`, and `not for` clauses, records deterministic
  style metadata on context artifacts/compile runs/compression trials, and the
  candidate and repair fallback generators now emit compliant compact
  descriptions. Validation passed with focused compiler/candidate/admin/worker
  tests, focused ruff checks, full `uv run ruff check sidecar`, `uv run pytest
  -q` with 265 tests, `uv run python -m compileall -q sidecar`, `git diff
  --check`, `npm test --prefix plugin/autoskill` with 18 tests, and `npm run
  check --prefix plugin/autoskill`.
- External import materialization now emits canonical SkillIR candidates instead
  of ad-hoc manifest dictionaries: imported external skills get deterministic
  `external-*` slugs/names, compliant bounded descriptions, complete SkillIR
  sections, read-only/no-activation boundaries, evidence links, and separate
  content-safe external-source metadata. Validation passed with focused external
  import/worker tests, focused ruff checks, full `uv run ruff check sidecar`,
  `uv run pytest -q` with 265 tests, `uv run python -m compileall -q sidecar`,
  `git diff --check`, `npm test --prefix plugin/autoskill` with 18 tests, and
  `npm run check --prefix plugin/autoskill`.
- SkillIR migration now has an executable guarded proposal path: the new
  migration planner validates existing SkillIR payloads, rejects invalid
  runtime descriptions fail-closed, preserves semantic fields exactly, records
  source revision/compiler/reason/rollback metadata, recompiles into a new
  inactive candidate revision, and exposes `/v1/skillir/migrations/propose`
  through the same transaction, probe, evaluation, and rollback persistence
  path used by other candidate revisions. Validation passed with focused
  migration/candidate tests, focused ruff checks, full `uv run ruff check
  sidecar`, `uv run pytest -q` with 268 tests, `uv run python -m compileall -q
  sidecar`, `git diff --check`, `npm test --prefix plugin/autoskill` with 18
  tests, and `npm run check --prefix plugin/autoskill`.
- Utility curation archive/promotion now keeps filesystem state aligned with DB
  lifecycle: archive, active-budget archive, and duplicate-merge archive actions
  snapshot active skill directories into `.autoskill/archive` and remove them
  from `skills/autoskill`, promotion restores the latest archive manifest before
  moving DB state back to active, and curation records filesystem archive or
  restore metadata on each action for rollback evidence. Validation passed with
  focused utility/writer/worker/admin tests, focused ruff checks, full `uv run
  ruff check sidecar`, `uv run pytest -q` with 270 tests, `uv run python -m
  compileall -q sidecar`, `git diff --check`, `npm test --prefix
  plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Active-bank curation now performs drift preflight through the contract store
  before curation runs from the API or worker, surfaces the preflight result in
  curation output, and blocks archived promotion when the latest SkillIR
  contracts are stale or not valid/false-positive. Validation passed with
  focused utility/worker/admin/contracts tests, focused ruff checks, full `uv
  run ruff check sidecar`, `uv run pytest -q` with 271 tests, `uv run python -m
  compileall -q sidecar`, `git diff --check`, `npm test --prefix
  plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Proposal probe generation and deterministic acceptance now include an
  adversarial probe gate: candidate and migration proposals plan adversarial
  probes, the evaluator fails closed on critical scanner findings or explicit
  policy-bypass/exfiltration phrases, and proposal-gate results record the
  section 23.2 acceptance policy and metrics. Validation passed with focused
  evaluator/candidate/migration/external tests, focused ruff checks, full `uv
  run ruff check sidecar`, `uv run pytest -q` with 272 tests, `uv run python -m
  compileall -q sidecar`, `git diff --check`, `npm test --prefix
  plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Activated SkillKernel runtime artifacts now get an active
  `.autoskill-manifest.json` provenance manifest as required by section 24.8:
  writer governance apply emits the manifest with artifact hashes, generator
  metadata, SkillIR/version/transaction identifiers, gate statuses,
  loadability/capability fields, token-budget slot, and rollback pointer, then
  verifies schema, file presence, hashes, rollback archive hash, and absence of
  unmanifested active files before recording governance items. The manifest is
  recorded as its own active `artifact_manifest` transaction item. Validation
  passed with focused writer/worker/admin tests, focused ruff checks, full `uv
  run ruff check sidecar`, `uv run pytest -q` with 273 tests, `uv run python -m
  compileall -q sidecar`, `git diff --check`, `npm test --prefix
  plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Writer activation now has the section 25.2 safe-window gate on both direct
  API apply and queued mutation-worker apply: an optional activation-window
  store can block active-root mutation when the target skill package is unsafe
  to rewrite, leaving the evolution transaction staged with defer metadata and
  returning a conflict/deferred result without writing active files or
  governance items. Validation passed with focused writer/worker/admin tests,
  focused ruff checks, full `uv run ruff check sidecar`, `uv run pytest -q`
  with 275 tests, `uv run python -m compileall -q sidecar`, `git diff
  --check`, `npm test --prefix plugin/autoskill` with 18 tests, and `npm run
  check --prefix plugin/autoskill`.
- Writer path containment now matches the section 25.4 allowlist: support
  artifacts can use the approved scripts/references/templates/schemas/data/
  assets/examples/tests/probes/adjunct_requests directories with
  directory-specific suffix checks, `.autoskill-contract.json` is accepted as a
  root active artifact, and staged, active-snapshot, archive-verify, and
  rollback source files reject hardlinks as well as symlinks/path escapes.
  Validation passed with focused writer/worker/admin tests, focused ruff
  checks, full `uv run ruff check sidecar`, `uv run pytest -q` with 277 tests,
  `uv run python -m compileall -q sidecar`, `git diff --check`, `npm test
  --prefix plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Scheduler ticks now implement the section 26.2/26.5 scheduler hardening:
  schedule records carry a validated `misfire_policy`, API and worker tick
  responses report skipped/coalesced/lock-acquired metadata, asyncpg ticks take
  a transaction-scoped advisory lock before processing due schedules, and
  interval misfires can coalesce, catch up one interval at a time, skip stale
  expensive work, or run immediately. Validation passed with focused scheduler/
  worker tests, focused ruff checks, full `uv run ruff check sidecar`, `uv run
  pytest -q` with 278 tests, `uv run python -m compileall -q sidecar`, `git
  diff --check`, `npm test --prefix plugin/autoskill` with 18 tests, `npm run
  check --prefix plugin/autoskill`, `docker compose config --quiet`, and a
  compose Postgres migration smoke verifying the `misfire_policy` column and
  check constraint.
- Scheduler startup now registers handler-backed section 26.4 core defaults
  through a centralized default-schedule service: evidence derivation,
  embedding generation, opportunity mining, usage aggregation, utility rollup,
  curation, contract extraction, drift checks, historical parsing, historical
  bootstrap consolidation, evaluator gates, and guarded repair execution get
  deterministic intervals, workspace-scoped payloads, and section 26.5 misfire
  policies. Validation passed with focused scheduler/worker tests, focused
  ruff checks, full `uv run ruff check sidecar`, `uv run pytest -q` with 279
  tests, `uv run python -m compileall -q sidecar`, `git diff --check`, `npm
  test --prefix plugin/autoskill` with 18 tests, and `npm run check --prefix
  plugin/autoskill`.
- Attribution outcomes now implement the section 27 taxonomy at the store and
  schema boundary: attribution events normalize legacy/spoken aliases into the
  canonical helped/hurt/ignored/missing/shadowed/independent-tool-drift/
  user-correction/unknown slugs, reject unsupported strings, preserve raw
  legacy outcomes in metadata, and enforce the canonical vocabulary with an
  idempotent Postgres check constraint. Usage and utility consumers now score
  normalized attribution outcomes. Validation passed with focused attribution/
  shadowing/usage/utility tests, focused ruff checks, full `uv run ruff check
  sidecar`, `uv run pytest -q` with 283 tests, `uv run python -m compileall -q
  sidecar`, `git diff --check`, `npm test --prefix plugin/autoskill` with 18
  tests, `npm run check --prefix plugin/autoskill`, `docker compose config
  --quiet`, and a compose Postgres migration smoke verifying the
  `attribution_events_outcome_check` constraint plus invalid-outcome rejection.
- Section 28 operator observability now has a read-only
  `/v1/observability/metrics` control endpoint backed by an asyncpg
  observability snapshot: it reports ingest rate, redaction counts, trace-based
  sidecar latency, explicit plugin-diagnostics-required spool status, job queue
  depth and success/failure by type, embedding backlog, retrieval/context hint
  counts and token cost, skill creation/improvement counts, scanner/evaluator
  failure counts, active/archive/promote/rollback/freeze/drift/utility metrics,
  audit counts plus chain verification, and bounded Postgres table/index size
  rows. The response also materializes the ten minimum dashboard views from
  section 28.2. Validation passed with focused observability/admin tests,
  focused ruff checks, full `uv run ruff check sidecar`, `uv run pytest -q`
  with 284 tests, `uv run python -m compileall -q sidecar`, `git diff
  --check`, `npm test --prefix plugin/autoskill` with 18 tests, `npm run check
  --prefix plugin/autoskill`, `docker compose config --quiet`, and a live
  compose route smoke showing 24 metric keys, 10 dashboard views, valid audit
  chain, five storage rows, and explicit `plugin_diagnostics_required` spool
  status.
- Section 28.3 daily audit-chain verification is now a handler-backed
  maintenance job: `audit.verify` verifies the bounded audit hash chain,
  returns fail-closed job output on success, raises on invalid chains so worker
  completion records a failed job, and is registered in core schedules on a
  daily cadence with a 1000-record verification limit. API single-worker runs
  and `worker_main` now thread the audit store into worker execution.
  Validation passed with focused scheduler/worker tests, focused ruff checks,
  full `uv run ruff check sidecar`, `uv run pytest -q` with 286 tests, `uv
  run python -m compileall -q sidecar`, `git diff --check`, `npm test --prefix
  plugin/autoskill` with 18 tests, `npm run check --prefix plugin/autoskill`,
  `docker compose config --quiet`, and a live compose worker smoke proving the
  default `audit.verify` schedule, enqueued job, and maintenance worker result
  `chain_valid=true`.
- Section 29 effective configuration is now a first-class control surface:
  settings support the spec-named `SKILLKERNEL_*` deployment/provider/token env
  variables while preserving the existing `AUTOSKILL_*` compatibility names,
  and `/v1/config/effective` returns a secret-free `skillkernel` config shape
  with deployment, paths, historical-ingestion, plugin, database, LLM,
  embedding, budget, compiler, gate, security, and scheduler blocks. The route
  requires control auth and reports env variable names/compat aliases instead
  of secret values. Validation passed with focused config/admin tests, focused
  ruff checks, full `uv run ruff check sidecar`, `uv run pytest -q` with 287
  tests, `uv run python -m compileall -q sidecar`, `git diff --check`, `npm
  test --prefix plugin/autoskill` with 18 tests, `npm run check --prefix
  plugin/autoskill`, `docker compose config --quiet`, and an HTTP smoke against
  a temporary local sidecar showing the expected block list, `dsn_env=
  SKILLKERNEL_DATABASE_URL`, configured database/LLM flags, embedding dimension
  768, and sidecar URL projection.
- Section 30 Phase 12 now has the required proposal reviewer/status control
  surface: `/v1/proposals/review` returns bounded, read-only candidate revision
  summaries, topology operation summaries, proposal-gate evaluation statuses,
  and status counts for operator review without exposing SkillIR/runtime text
  bodies. Validation passed with focused candidate/evaluation/topology/admin
  tests, focused ruff checks, full `uv run ruff check sidecar`, `uv run
  pytest -q` with 288 tests, `uv run python -m compileall -q sidecar`, `git
  diff --check`, `npm test --prefix plugin/autoskill` with 18 tests, `npm run
  check --prefix plugin/autoskill`, `docker compose config --quiet`, and a
  compose Postgres smoke proving the review route reads one real candidate
  revision, one topology proposal, and one planned proposal-gate evaluation.
- Section 31 production acceptance criteria now have an executable crosswalk:
  `scripts/autoskill_acceptance.py --json` emits a deterministic acceptance
  report mapping every concrete production bullet from the duplicated-number
  criteria list plus the seven context-management criteria to repo evidence,
  validation commands, tests, or control surfaces. The report fails closed if a
  criterion has missing evidence, duplicate IDs, empty text, or placeholder
  evidence, and its focused test locks the current 44 production criteria plus
  seven context criteria. Validation passed with focused acceptance-report
  tests, focused ruff checks, `python scripts/autoskill_acceptance.py --json`
  reporting `ready=true`, full `uv run ruff check sidecar scripts`, `uv run
  pytest -q` with 289 tests, `uv run python -m compileall -q sidecar scripts`,
  `git diff --check`, `npm test --prefix plugin/autoskill` with 18 tests, `npm
  run check --prefix plugin/autoskill`, and `docker compose config --quiet`.
- Sections 32/33 now have an executable governance crosswalk:
  `scripts/autoskill_handoff.py --json` emits a deterministic risk-register and
  developer-handoff report mapping all 31 risk rows, 23 before-coding checklist
  items, 18 during-implementation checklist items, and the final autonomous
  apply ship gate to concrete repo evidence. The report fails closed on missing
  evidence, missing mitigation, duplicate IDs, non-ready statuses, empty text,
  or placeholder text, and its focused test locks the 73-item count.
  Validation passed with focused handoff-report tests, focused ruff checks,
  `python scripts/autoskill_handoff.py --json` reporting `ready=true`, full `uv
  run ruff check sidecar scripts`, `uv run pytest -q` with 290 tests, `uv run
  python -m compileall -q sidecar scripts`, `git diff --check`, `npm test
  --prefix plugin/autoskill` with 18 tests, `npm run check --prefix
  plugin/autoskill`, and `docker compose config --quiet`.
- Section 34 research and design traceability now has an executable crosswalk:
  `scripts/autoskill_traceability.py --json` parses the controlling handoff
  spec's Section 34, validates the six anchor subsections, all 88 research
  anchors, the 79 URL-backed anchors, and all 25 research-to-design matrix rows,
  and maps every matrix row to concrete repo evidence. The report fails closed
  on missing sections, anchor-count drift, missing evidence mappings, duplicate
  findings, empty fields, or placeholder text. Validation passed with focused
  traceability-report tests, focused ruff checks, `python
  scripts/autoskill_traceability.py --json` reporting `ready=true`, full `uv
  run ruff check sidecar scripts`, `uv run pytest -q` with 291 tests, `uv run
  python -m compileall -q sidecar scripts`, `git diff --check`, `npm test
  --prefix plugin/autoskill` with 18 tests, `npm run check --prefix
  plugin/autoskill`, and `docker compose config --quiet`.
- Sections 35/36 landscape assimilation and implementation readiness now have
  an executable crosswalk: `scripts/autoskill_readiness.py --json` parses the
  controlling handoff spec's landscape matrix, adopted stance, architecture
  list, product operation definition, and implementation-order ladder. It
  validates all 52 landscape rows, the eight stance lines, 28 architecture
  items, four topology operations, 29 implementation-order steps, and the two
  sequencing gates requiring control-plane-first implementation and concrete
  failure-mode justification for future design changes. Every landscape row,
  architecture item, and implementation-order step carries repo evidence.
  Validation passed with focused readiness-report tests, focused ruff checks,
  `python scripts/autoskill_readiness.py --json` reporting `ready=true`, full
  `uv run ruff check sidecar scripts`, `uv run pytest -q` with 292 tests, `uv
  run python -m compileall -q sidecar scripts`, `git diff --check`, `npm test
  --prefix plugin/autoskill` with 18 tests, `npm run check --prefix
  plugin/autoskill`, and `docker compose config --quiet`.
- 2026-06-03 interrupted-turn deployment continuation is closed: the sidecar
  embedding request path now sends the configured embedding dimension to
  OpenAI-compatible providers, the Dev-01 compose defaults now point at the
  live qualified `Qwen3-Embedding-4B-Q8_0.gguf` 1536-dimensional profile, and
  the refreshed `docker compose up -d --build` deployment recreated sidecar plus
  worker containers while preserving the Postgres volume. The running sidecar
  reports effective embedding config `model=Qwen3-Embedding-4B-Q8_0.gguf` and
  `dimensions=1536`; live profile qualification run
  `7dbc0f69-46ef-49d0-9d3e-8fb170246e6b` passed route, dimension, finite,
  non-zero, stability, and negative-pair separation checks; deployment
  readiness for `workspace_id=dev-01&replay_tag=production` reports
  `ready=true` with no blockers or warnings and active embedding dimensions
  `[1536]`. Validation passed with acceptance/readiness/handoff/traceability
  reports all `ready=true`, red-team 9/9, focused operator/report/profile tests,
  `uv run ruff check sidecar scripts`, `npm test --prefix plugin/autoskill`
  with 18 tests, `uv run python -m compileall -q sidecar scripts`, `git diff
  --check`, `docker compose config --quiet`, and full `uv run pytest -q` with
  294 tests.
- Usage-derived broker policy proposal consumption is implemented for the
  previously stale broker-abstain gap: accepted context-waste/false-positive
  usage recommendations carrying `broker_abstain` or `tighten_description` now
  feed `/v1/broker/policies/propose-from-usage`, returning content-safe
  operator-review action records and optionally persisting a candidate-only
  broker policy version without activating it or changing runtime routing.
  Validation passed with focused broker-policy/topology tests, `uv run ruff
  check sidecar/autoskill/api/app.py
  sidecar/autoskill/tests/test_broker_policy_api.py`, full `uv run ruff check
  sidecar scripts`, full `uv run pytest -q` with 296 tests, `uv run python -m
  compileall -q sidecar scripts`, `npm test --prefix plugin/autoskill` with 18
  tests, `npm run check --prefix plugin/autoskill`, `docker compose config
  --quiet`, `git diff --check`, and acceptance/readiness/handoff/traceability
  reports all `ready=true`.
- Historical source-item locator lineage is now schema-backed instead of
  metadata-only: `historical_import_chunks` stores content-safe
  `source_item_locator_hash`, `source_item_kind`, `item_key_hash`,
  `line_range_hash`, and `record_index` columns, idempotent migration backfill
  hydrates them from existing v2 metadata, and chunk records/API JSON expose the
  fields without storing raw paths or raw item keys. Focused validation passed
  with `uv run pytest -q sidecar/autoskill/tests/test_historical_import.py` and
  `uv run ruff check sidecar/autoskill/db/historical.py
  sidecar/autoskill/tests/test_historical_import.py`; full validation passed
  with `uv run ruff check sidecar scripts`, `uv run pytest -q` with 296 tests,
  `uv run python -m compileall -q sidecar scripts`, `npm test --prefix
  plugin/autoskill` with 18 tests, `npm run check --prefix plugin/autoskill`,
  `docker compose config --quiet`, `git diff --check`, all four executable
  crosswalk reports returning `ready=true`, and an idempotent compose Postgres
  migration smoke verifying all five locator columns exist.
- Context-token-ledger contrastive evidence mining is implemented: contrastive
  replay induction now accepts explicit context ledger outcomes plus
  usage/source-metadata-shaped context ledger evidence, derives success from
  known outcome labels, `task_success`, or marginal-value scores, and maps
  `no_skill`/`skill_hidden` versus `skill_visible` visibility states into
  deterministic intervention replay pairs. Focused validation passed with `uv
  run pytest -q sidecar/autoskill/tests/test_contrastive.py` and `uv run ruff
  check sidecar/autoskill/services/contrastive.py
  sidecar/autoskill/tests/test_contrastive.py`; full validation passed with
  `uv run pytest -q` with 298 tests, `uv run ruff check sidecar scripts`, `uv
  run python -m compileall -q sidecar scripts`, `npm test --prefix
  plugin/autoskill` with 18 tests, `npm run check --prefix plugin/autoskill`,
  `docker compose config --quiet`, `git diff --check`, and all four executable
  crosswalk reports returning `ready=true`.
- Proposal-gate acceptance now enforces the section 23.2 utility/token policy:
  no-skill intervention replay metrics are folded into acceptance metrics as
  `utility_delta` and `token_delta`, and a candidate fails closed after otherwise
  passed deterministic probes when utility is below the configured threshold or
  token growth has no utility gain. Focused validation passed with `uv run
  pytest -q sidecar/autoskill/tests/test_evaluator.py` and `uv run ruff check
  sidecar/autoskill/services/evaluator.py
  sidecar/autoskill/tests/test_evaluator.py`; full validation passed with `uv
  run ruff check sidecar`, `uv run pytest -q` with 303 tests, `uv run python -m
  compileall -q sidecar`, and `git diff --check`.
- Observatory implementation slice landed from
  `unified-implementation-specification.md`: web-admin config,
  role-aware admin auth, `/admin/api/v1/*` summary/pipeline/subsystem/component
  issue/search/object/replay/action endpoints, `/admin/live` WebSocket,
  `/admin/live-sse`, web-container static serving, station/subsystem/read-model
  aggregation, issue/reason-code generation, content-safe object microscope
  payloads, audited operator action receipts, and legacy route-inspection
  compatibility for existing tests.
- Observatory React/Vite frontend landed under
  `sidecar/autoskill/observatory`: React Flow assembly-line map, lazy ELK
  layout, ECharts health/queue charts, PixiJS live-flow overlay, Monaco
  read-only JSON inspector, TanStack Query server-state polling, token/workspace
  controls, global search, issue board, workcell lens, station cockpit,
  skill/topology lens, trace/object inspector, admin action gateway, reduced
  motion support, and Docker/Compose/Makefile build wiring.
- Observatory validation passed: `uv run ruff check sidecar`, `uv run pytest -q`
  with 307 passing tests, `uv run python -m compileall -q sidecar`,
  `npm test --prefix plugin/autoskill` with 18 passing tests,
  `npm run build` and `npm audit --omit=dev` in
  `sidecar/autoskill/observatory`, `docker compose config`, and
  `git diff --check`.
- Local Observatory preview is running at `http://127.0.0.1:8757/admin/` from
  PID file `/tmp/skillkernel-observatory-8757.pid`; verified `/v1/health`,
  `/admin/api/v1/summary?workspace_id=dev-01`, and `/admin/` all return 200.
- Observatory route-map expansion and cockpit stabilization are implemented:
  `/admin/api/v1` now exposes bounded collection/detail/readiness surfaces for
  components, reason codes, playbooks, jobs, schedules, skills, candidates,
  evaluations, scanner findings, historical imports, broker decisions, context
  artifacts, model/embedding profiles, storage, audit, comparisons, diagnostic
  bundles, trace detail, and trace replay without raw content exposure. Guarded
  operator action aliases record audit receipts and fail closed on high-impact
  actions without confirmation. The React app now preserves deep-link state,
  falls back from WebSocket to SSE live updates, and adds cockpit tabs for
  records, metrics, traces, artifacts, config, audit, and help.
- Observatory expansion validation passed on the final tree: focused
  Observatory tests passed `8 passed`; `uv run ruff check sidecar scripts`,
  `uv run pytest -q` with 311 passing tests, `uv run python -m compileall -q
  sidecar scripts`, `npm test --prefix plugin/autoskill` with 18 passing tests,
  `npm run build --prefix sidecar/autoskill/observatory`, `docker compose
  config --quiet`, and `git diff --check` passed.
- Observatory broker-decision drill-down now reads directly from the
  content-safe `retrieval_logs` read model: `/admin/api/v1/broker/decisions`
  lists recent retrieval/broker decisions, and
  `/admin/api/v1/broker/decisions/{decision_id}` exposes query hashes,
  candidate object IDs, rendered skill IDs, trace/span links, reason codes, and
  suppression metadata without raw query text. This advances the Observatory
  aggregate-to-evidence/object-microscope contract for runtime broker
  diagnostics.
- Validation passed for the Observatory broker-decision read model: focused
  Observatory API tests passed `9 passed`, `uv run ruff check sidecar`, `uv run
  pytest` passed with 312 tests, `uv run python -m compileall -q sidecar`, `git
  diff --check`, and `docker compose config --quiet` passed; a compose
  Postgres smoke migrated the schema, inserted a redacted retrieval-log row,
  read it through the admin collection/detail routes with bearer auth, verified
  `raw_query_stored=false`, deleted the smoke rows, and stopped Postgres without
  removing the persistent volume.
- Observatory placeholder read-model remediation is implemented for the next
  spec slice: `/admin/api/v1/events` now lists bounded redacted `raw_events`
  metadata from the event store; `/admin/api/v1/traces` now lists bounded trace
  summaries from `trace_spans`; `/admin/api/v1/comparisons/query` persists
  read-only baseline comparison records; `/admin/api/v1/comparisons` lists
  saved comparisons; and diagnostic bundle creation/retrieval now persists
  redacted bundle descriptors instead of returning a missing-read-model
  placeholder.
- Focused validation passed for the Observatory event/trace/comparison/bundle
  read models: `uv run pytest -q sidecar/autoskill/tests/test_observatory_api.py`
  passed with `11 passed`, and focused `uv run ruff check` passed for the edited
  API, DB, and Observatory test files.
- Observatory object-microscope remediation is implemented for the generic
  `/admin/api/v1/objects/{object_type}/{object_id}` route: captured events,
  saved baseline comparisons, and diagnostic bundles now resolve from persisted
  read-model stores before falling back to snapshot-derived placeholder
  diagnostics.
- Validation passed for the Observatory object-microscope remediation:
  focused Observatory API tests passed `11 passed`, focused ruff passed for the
  edited API/DB/test files, `uv run ruff check sidecar scripts`, `uv run
  pytest -q` with 314 passing tests, `uv run python -m compileall -q sidecar
  scripts`, `npm test --prefix plugin/autoskill` with 18 passing tests,
  `npm run build --prefix sidecar/autoskill/observatory`, `docker compose
  config --quiet`, and `git diff --check` passed. A compose/Postgres smoke
  migrated the schema, inserted a redacted event, created a saved comparison and
  diagnostic bundle, verified all three through `/admin/api/v1/objects/...`,
  confirmed `raw_available=false`, deleted the smoke workspace, and stopped
  Postgres without removing the persistent volume.
- Observatory additive response-envelope remediation is implemented for the
  remaining Phase 1/12.2 API-envelope gap: admin response models now include
  `ok`, `data`, and `meta` with request IDs, generation timestamps, redaction
  level, and warning slots while preserving existing `snapshot`, `collection`,
  `object`, `receipt`, and search payload fields for current clients. Focused
  validation passed with Observatory API tests `11 passed`, focused ruff, and
  the Observatory frontend build. Final-tree validation also passed with `uv run
  ruff check sidecar scripts`, `uv run pytest -q` with 314 passing tests, `uv
  run python -m compileall -q sidecar scripts`, `npm test --prefix
  plugin/autoskill` with 18 passing tests, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and `git
  diff --check`.
- Observatory browser-hardening remediation is implemented for the Phase 16/23
  security-header gap: `/admin` responses now receive scoped content security,
  frame denial, referrer, MIME sniffing, and opener-isolation headers while
  ordinary `/v1` sidecar routes are left unchanged. Focused validation passed
  with Observatory API tests `12 passed`, including a direct ASGI middleware
  check, and focused ruff. Final-tree validation also passed with `uv run ruff
  check sidecar scripts`, `uv run pytest -q` with 315 passing tests, `uv run
  python -m compileall -q sidecar scripts`, `npm test --prefix plugin/autoskill`
  with 18 passing tests, `npm run build --prefix sidecar/autoskill/observatory`,
  `docker compose config --quiet`, and `git diff --check`.
- Observatory dedicated operator-action audit persistence is implemented for
  the Phase 4.3/12.1/16.3 action-audit gap: accepted and rejected admin actions
  now write the existing `autoskill.admin_action_audit` table with actor roles,
  target identity, idempotency key, linked generic audit-chain record, result,
  request ID, metadata-key summary, and confirmation hash without storing raw
  confirmation text. Focused Observatory API tests passed `12 passed`; final
  validation passed with `uv run ruff check sidecar`, `uv run pytest` with 315
  tests, `uv run python -m compileall -q sidecar`, `npm test --prefix
  plugin/autoskill` with 18 tests, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and `git diff
  --check`. A compose/Postgres smoke migrated the schema, recorded one
  `verify_audit_chain` action through the admin API into
  `admin_action_audit`, verified the linked `audit_records` row and redacted
  payload shape, deleted the smoke rows, and stopped Postgres without removing
  the persistent volume.
- Observatory cursor/security/live-outbox remediation is implemented for the
  Phase 2/12.4/16.4 gaps: admin collection envelopes now expose bounded cursor,
  next-cursor, and pagination metadata while rejecting malformed/stale cursors;
  browser-originated POST actions require `X-SkillKernel-CSRF`, while API-token
  clients remain usable; per-actor in-memory rate limits protect operator
  actions and raw-reveal attempts; and accepted/rejected admin actions,
  comparison creation, and diagnostic bundle creation now append UI-safe
  `admin_live_event_outbox` rows. `/admin/live` and `/admin/live-sse` drain the
  persisted outbox before falling back to snapshot/heartbeat events, preserving
  the existing nonblank live dashboard behavior. Final validation passed with
  `uv run ruff check sidecar scripts`, `uv run pytest -q` with 317 passing
  tests, `uv run python -m compileall -q sidecar scripts`, `npm test --prefix
  plugin/autoskill` with 18 passing tests, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and a
  compose/Postgres smoke that applied migrations, recorded one
  `refresh_read_models` action, verified the `read_model_invalidated`
  `admin_live_event_outbox` row plus linked `admin_action_audit` and
  `audit_records` rows, deleted the smoke rows, and stopped Postgres without
  removing the persistent volume.
- Observatory raw-content reveal grant enforcement is implemented for the Phase
  4.3/16.1/16.3 guarded-action gap: `reveal_raw_content` is now a config-gated,
  admin-only, confirmation-required action that returns a short-lived token only
  in the accepted response while persisting just the token hash, target,
  confirmation hash, and content-safe metadata in `admin_action_audit` and the
  generic audit chain. The action still returns no raw event, prompt, skill,
  support-file, or memory content. Validation passed with focused Observatory
  API tests `16 passed`, `uv run ruff check sidecar`, `uv run pytest` with 319
  tests, `uv run python -m compileall -q sidecar`, `docker compose
  config --quiet`, `git diff --check`, and a compose/Postgres smoke that
  migrated the schema, accepted one admin raw-reveal grant, verified DB audit
  hash-only persistence, deleted the smoke rows, and stopped compose without
  removing the persistent volume.
- Observatory operator-action audit read models are implemented for the Phase
  12.1/16.3 aggregate-to-evidence gap: `/admin/api/v1/actions/audit` lists
  bounded content-safe `admin_action_audit` receipts with workspace/actor/action/
  result filters, `/admin/api/v1/actions/audit/{action_id}` returns one receipt,
  and the generic object microscope resolves `admin_action` objects with linked
  audit/job provenance, request ID, source identity, metadata-key summary,
  confirmation-hash presence, and `raw_available=false` policy metadata.
  Validation passed with focused Observatory API tests `17 passed`, `uv run
  ruff check sidecar`, `uv run pytest -q` with 320 tests, `uv run python -m
  compileall -q sidecar`, `npm test --prefix plugin/autoskill` with 18 tests,
  `npm run build --prefix sidecar/autoskill/observatory`, `docker compose
  config --quiet`, and `git diff --check`; a real compose/Postgres smoke
  applied migrations idempotently, recorded one smoke `admin_action_audit` row,
  verified workspace-filtered list/detail reads through the new asyncpg store
  methods, deleted the smoke row, and left the pre-existing Postgres container
  running.
- Observatory missing-signal diagnostics are remediated across the sidecar and
  frontend: zero-valued but present metric read models no longer produce
  `missing-required-signal`, stations now expose `data_quality.missing_signal_keys`
  for genuinely absent metric fields, missing admin object/read-model fallbacks
  use the more specific `read-model-missing` reason code, and the station cockpit
  renders explicit missing-signal chips only when such signals are actually
  present. Validation passed with focused Observatory API tests `19 passed`, full
  `uv run pytest -q` with 322 tests, `uv run ruff check` for the edited sidecar
  files, `uv run python -m compileall -q sidecar`, `npm test --prefix
  plugin/autoskill` with 18 tests, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and `git diff
  --check`. The live Dev-01 Observatory sidecar on `:8758` was restarted with the
  patch and reported no `missing-required-signal` stations, no missing signal
  keys, 24 rendered graph labels, 24 stations, 24 edges, all `/admin/assets`
  returning 200, and the remaining visible issue limited to
  `embedding-backlog-present`.
- Historical deployment bootstrap root resolution is implemented for Phase 4.75
  and Observatory historical-ingestion readiness: worker startup now resolves
  explicit historical import roots first, otherwise falls back to existing
  bounded OpenClaw state subroots plus the configured workspace root; local
  compose mounts OpenClaw state read-only and no longer schedules broad
  `/workspace` import as the only default root. Scheduler defaults now carry
  bounded but aggressive bootstrap limits for discovery, parse, evidence,
  embedding, and historical consolidation. Validation passed with focused historical
  import/scheduler tests `23 passed`, `uv run ruff check sidecar`, full `uv run
  pytest` with 324 tests, `uv run python -m compileall -q sidecar`, `docker
  compose config --quiet`, and `git diff --check`. A compose/Postgres smoke
  reran migrations, resolved eight existing bounded OpenClaw roots from
  `OPENCLAW_STATE_DIR`, registered expected historical discovery/parse schedule
  payloads, then deleted the smoke workspace and schedules from the persistent
  dev DB.
- Live Dev-01 broad historical import is running over the bounded OpenClaw
  roots rather than a single agent root: the first broad discovery/parse run
  imported 10,005 historical sources and 20,005 redacted chunks, derived 20,003
  historical evidence rows, completed 40 evidence derivation jobs, completed 40
  initial embedding jobs, completed one persisted historical bootstrap
  consolidation job, and queued 100 additional `embeddings.generate` jobs to
  drain the remaining evidence/historical chunk embedding backlog with the
  maintenance worker active.
- Observatory live stream fallback continuity is implemented for Phase 2:
  WebSocket and SSE snapshot fallbacks now use the real snapshot sequence from
  the read model, advance the local cursor after fallback delivery, and emit
  heartbeat payloads once the client is caught up instead of repeatedly
  replaying full snapshots. The frontend inspector remains the spec-required
  read-only Monaco surface while handling missing detail payloads explicitly.
  Validation passed with focused `uv run pytest
  sidecar/autoskill/tests/test_observatory_api.py -q` (`22 passed`),
  `npm run build --prefix sidecar/autoskill/observatory`, `uv run ruff check
  sidecar`, full `uv run pytest` (`327 passed`), `uv run python -m compileall
  -q sidecar`, and `git diff --check`.
- Observatory job-health scoping is implemented for the control/storage
  workcell: `/admin/api/v1/summary` now resolves an effective workspace from
  the query, `AUTOSKILL_WORKSPACE_ID`, then the `dev-01` deployment default,
  passes that workspace through job counts, worker-health summaries,
  operator metrics, and audit verification, and suppresses stale failed job
  rows when the same workspace/job kind later succeeded. This prevents
  recovered backlog runs from remaining as false `failed-jobs-present`
  indicators while preserving newer failures and other-workspace failures.
  Validation passed with `uv run pytest
  sidecar/autoskill/tests/test_jobs_api.py::test_job_summary_ignores_failed_kind_after_later_success
  sidecar/autoskill/tests/test_observatory_api.py::test_observatory_summary_defaults_to_effective_workspace
  -q` (`2 passed`), `uv run ruff check sidecar`, `uv run pytest`
  (`334 passed`), `uv run python -m compileall -q sidecar`,
  `docker compose config --quiet`, and `git diff --check`. A real
  compose/Postgres smoke applied migrations, inserted an isolated terminal
  failed job followed by a same-workspace/job-kind success through
  `AsyncpgJobStore`, verified the job summary and Observatory
  `operator_metrics.job_queue_depth` returned only `{"succeeded": 1}`, then
  deleted the smoke workspace rows.
- Observatory live-stream delta/outbox continuity is implemented for the Phase
  2/12.3 stream contract: WebSocket and SSE now keep the timestamp-derived
  snapshot freshness sequence separate from the persisted
  `admin_live_event_outbox` cursor, expose `cursor_seq` for reconnect-safe
  frontend resume, fence pre-existing outbox rows for first snapshots, and
  replay later persisted deltas even when their outbox sequence is lower than
  the snapshot timestamp sequence. Snapshot-style reconnect cursors that are
  larger than the current outbox sequence are clamped to the newest persisted
  outbox row so legacy/spec-shaped `last_seq` values cannot suppress future
  deltas. Validation passed with focused `uv run pytest
  sidecar/autoskill/tests/test_observatory_api.py -q` (`30 passed`), `uv run
  ruff check sidecar scripts`, `uv run pytest` (`340 passed`), `uv run python
  -m compileall -q sidecar scripts`, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and `git
  diff --check`. A real Postgres smoke through `uv run python
  scripts/autoskill_observatory_live_smoke.py` proved
  `snapshot_seq=1780550603438`, `snapshot_cursor_seq=11`,
  `stale_outbox_seq=11`, and `live_outbox_seq=12` before deleting the smoke rows.
- Observatory trace replay frontend remediation is implemented for Section 11:
  the React Trace view now consumes `/admin/api/v1/traces` and
  `/admin/api/v1/replay/traces/{trace_id}`, preserves a deep-linkable
  `trace=` URL parameter, lists trace summaries, highlights touched pipeline
  stations, exposes a span scrubber/waterfall, shows policy/gate badges,
  object refs, diff metadata panels, and read-only replay safety flags without
  adding a second control path. Validation passed with focused
  `uv run pytest
  sidecar/autoskill/tests/test_observatory_api.py::test_observatory_event_and_trace_read_models_are_bounded_and_content_safe
  -q`, full focused Observatory API tests (`30 passed`), `uv run ruff check
  sidecar/autoskill/tests/test_observatory_api.py`, `npm run build --prefix
  sidecar/autoskill/observatory`, and `git diff --check`.
- Observatory skill/topology frontend remediation is implemented for Sections
  9 and 21: the React Skills view now consumes `/admin/api/v1/skills`,
  `/admin/api/v1/skills/{skill_id}`, `/admin/api/v1/topology`, and
  `/admin/api/v1/context/artifacts`, preserves a deep-linkable `skill=` URL
  parameter, lists SkillKernel-owned skills, shows lifecycle/scanner/evaluator
  badges, exposes SkillIR/version diagnostics, context-artifact budget evidence,
  topology read-model detail, and routing stations without relying on static
  station tiles as the whole surface. Validation passed with `npm run build
  --prefix sidecar/autoskill/observatory`, focused Observatory API tests
  (`30 passed`), `uv run ruff check
  sidecar/autoskill/tests/test_observatory_api.py`, and `git diff --check`.
- Observatory operator action frontend remediation is implemented for Sections
  4.3/16.3/21: the React Admin view now exposes multiple dry-run operator
  actions through the existing `/admin/api/v1/actions` policy/audit gateway,
  refreshes `/admin/api/v1/actions/audit` after accepted receipts, and shows
  persisted action audit rows beside command-palette navigation and receipt
  inspection. Validation passed with `npm run build --prefix
  sidecar/autoskill/observatory`, focused Observatory API tests (`30 passed`),
  and `git diff --check`.
- Observatory Section 21/24 acceptance now has an executable crosswalk:
  `scripts/autoskill_observatory_acceptance.py --json` emits a deterministic
  Observatory web/admin acceptance and developer-checklist report covering 40
  acceptance criteria plus 38 checklist items, with explicit evidence pointers
  and implemented-equivalent markers where the repo intentionally uses an
  equivalent pattern. Validation passed with
  `uv run pytest -q sidecar/autoskill/tests/test_observatory_acceptance_report.py`
  (`1 passed`) and `uv run python scripts/autoskill_observatory_acceptance.py
  --json` reporting `ready=true`, `satisfied=78`, and no validation errors.
- Observatory catalog seed remediation is implemented for Section 24.4:
  `migrations/0001_autoskill_schema.sql` now creates and idempotently seeds
  `autoskill.admin_component_catalog` and
  `autoskill.admin_subsystem_catalog` from the runtime station/subsystem map,
  with focused regression coverage tying all 24 station IDs and 8 subsystem
  IDs back to the SQL seed. Validation passed with the Observatory acceptance
  report showing `implemented_equivalent=5`, focused pytest (`2 passed`),
  ruff, `docker compose config --quiet`, and `git diff --check`.
- Observatory OpenAPI client remediation is implemented for Section 24.14:
  `scripts/generate_observatory_openapi_client.py` exports the FastAPI
  `/admin/api/v1` OpenAPI route surface into the checked-in TypeScript client
  at `sidecar/autoskill/observatory/src/generated/observatoryClient.ts`, and
  `api.ts` consumes the generated route helper for every direct admin API call.
  Validation passed with generator `--check`, focused pytest (`3 passed`),
  ruff, `npm run build --prefix sidecar/autoskill/observatory`, and the
  Observatory acceptance report showing `implemented_equivalent=4`.
- Observatory render/mount diagnostics remediation is implemented for Section
  24.18: the React app now tracks app render count, session-persisted mount
  count, live snapshot applications, duplicate snapshot suppressions, summary
  seeds, and sequence-gap snapshot reloads, and exposes those counters in the
  Admin view. Validation passed with focused pytest (`4 passed`), ruff,
  `npm run build --prefix sidecar/autoskill/observatory`, `git diff --check`,
  and the Observatory acceptance report showing `implemented_equivalent=3`.
- Observatory guarded action dialog remediation is implemented for Section
  24.31: Admin action buttons now open an explicit modal confirmation with an
  operator reason before submitting any dry-run action to the audited action
  gateway. Validation passed with focused pytest (`5 passed`), ruff,
  `npm run build --prefix sidecar/autoskill/observatory`, `git diff --check`,
  and the Observatory acceptance report showing `implemented_equivalent=2`.
- Observatory E2E/load/visual fixture remediation is implemented for Sections
  21.7, 21.40, 24.36, and 24.37: `scripts/autoskill_observatory_fixtures.py`
  now generates and checks
  `sidecar/autoskill/observatory/fixtures/visual-regression-fixtures.json`,
  covering healthy/degraded/blocked/security/context-pressure/rollback/stale
  telemetry/reduced-motion/low-power/WebGL-fallback/high-load-soak scenarios.
  Validation passed with fixture `--check`, npm `fixtures:check`, focused
  pytest (`6 passed`), ruff, `npm run build --prefix
  sidecar/autoskill/observatory`, `git diff --check`, and the Observatory
  acceptance report showing `implemented_equivalent=0`.
- Observatory broker replay corpus visibility is implemented for the replay/
  canary readiness gate: `/admin/api/v1/broker/replay-episodes` lists bounded
  content-safe stored replay episodes with tag filtering and cursor pagination,
  `/admin/api/v1/broker/replay-episodes/{episode_id}` returns an object
  microscope payload with source broker-decision provenance, expected skill
  links, redacted intent hash, metadata-key summary, and explicit
  `raw_prompt_stored=false` policy metadata, and the generic object microscope
  resolves `broker_replay_episode` objects through the broker policy store.
  Validation passed with focused Observatory API tests (`2 passed`), generated
  Observatory OpenAPI client `--check`, `uv run ruff check sidecar`,
  `uv run pytest` (`347 passed`), `uv run python -m compileall -q sidecar`,
  `npm run build --prefix sidecar/autoskill/observatory`, and a real
  compose/Postgres smoke that migrated the schema, inserted one production-
  tagged replay episode through `AsyncpgBrokerPolicyStore`, read it through the
  new admin list/detail routes with bearer auth, verified `raw_prompt_stored=false`,
  and deleted the smoke rows.
- Observatory broker replay corpus frontend visibility is implemented for
  Sections 1.4, 1.9, 8.7, and 12.6: the React app now has a dedicated Replay
  tab backed by the generated `/admin/api/v1/broker/replay-episodes` routes,
  production-tag filtering, episode selection, expected routing/provenance
  panels, and explicit raw-prompt/content-policy badges without exposing raw
  prompt text by default. Validation passed with focused frontend source
  assertions (`7 passed`), `npm run build --prefix
  sidecar/autoskill/observatory`, `uv run ruff check sidecar`, `uv run pytest
  -q` (`348 passed`), `uv run python -m compileall -q sidecar`, and `git diff
  --check`.
- Observatory memory/control-flow read-model visibility is implemented for
  Sections 8.5, 12.6, and 16.1/16.3: `/admin/api/v1/memory/quarantine` and
  `/admin/api/v1/control-flow/events` now expose bounded list/detail surfaces
  plus generic object-microscope resolution over existing memory-governance
  stores, returning memory hashes/keys, taint/status, provenance, and
  content-safe decision metadata without returning proposed memory content or
  creating a second mutation path. Validation passed with focused Observatory
  API tests (`2 passed`), generated client `--check`, `uv run ruff check
  sidecar`, `uv run pytest` (`349 passed`), `uv run python -m compileall -q
  sidecar`, `npm test --prefix plugin/autoskill` (`18 passed`), `npm run build
  --prefix sidecar/autoskill/observatory`, `docker compose config --quiet`, and
  `git diff --check`.
- Observatory trace replay backend enrichment is implemented for Section 11:
  `/admin/api/v1/replay/traces/{trace_id}` now returns a content-safe replay
  object with ordered span timeline entries, span waterfall rows, station
  highlights, policy/gate badges, diff/hash metadata panels, detail-drawer
  object refs, deduplicated downstream provenance, and a redacted export bundle
  descriptor while preserving the persisted-state-only/no-reexecution safety
  contract. Validation passed with focused Observatory API tests (`32 passed`),
  `uv run ruff check sidecar`, `uv run pytest` (`349 passed`), `uv run python
  -m compileall -q sidecar`, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and `git
  diff --check`. No compose/Postgres smoke was needed because the slice only
  reshapes already-covered trace-span read data and adds no schema or
  asyncpg-store behavior.
- Observatory trace replay frontend enrichment is implemented for Section 11
  and Sections 1.4/1.8 causal-investigation journeys: the Trace tab now
  renders the backend replay read model's span waterfall, station highlights,
  policy/gate badges, detail-drawer object refs, safe diff/hash panels,
  redacted export bundle descriptor, and downstream provenance instead of
  deriving those views only from the selected raw timeline span. Validation
  passed with focused Observatory acceptance source assertions (`8 passed`),
  `npm run build --prefix sidecar/autoskill/observatory`, `uv run ruff check
  sidecar`, `uv run pytest` (`350 passed`), `uv run python -m compileall -q
  sidecar`, `npm test --prefix plugin/autoskill` (`18 passed`), `docker compose
  config --quiet`, and `git diff --check`. No compose/Postgres smoke was needed
  because this is a frontend/read-model consumption change over the already
  validated trace replay API.

- Deterministic context-waste repair planning now distinguishes moderate
  low-value context from decomposition-grade context bloat: curation still
  plans guarded `improve` for repairable token waste, but repeated ignored/
  false-positive context loads or materially negative context value with high
  token waste now plan a propose-only `decompose` repair with sibling and
  context-value trials. This advances core handoff Sections 11.13-11.15,
  19.1-19.4, and 21.8 without writing runtime skills or bypassing evaluator,
  scanner, context, or rollback gates. Focused validation passed with `uv run
  pytest -q sidecar/autoskill/tests/test_utility.py` (`7 passed`) and `uv run
  ruff check sidecar/autoskill/db/utility.py
  sidecar/autoskill/tests/test_utility.py`; full validation passed with `uv run
  ruff check sidecar`, `uv run pytest` (`351 passed`), `uv run python -m
  compileall -q sidecar`, `docker compose config --quiet`, and `git diff
  --check`.
- Observatory topology metrics cockpit visibility is implemented for Sections
  8.9, 9.3, 12.6, and 13.1: `/admin/api/v1/topology` now includes the existing
  sidecar `topology_store.metrics` read model with create/improve/compose/
  decompose operation counts, trial status matrices, recent SkillGraphIR
  operations, data-quality/read-model metadata, and raw-content-disabled policy;
  the React Skills/Topology view renders those operation and trial signals
  before the JSON inspector without adding any mutation path. Focused validation
  passed with the Observatory API/source assertions (`2 passed`), focused ruff,
  and `npm run build --prefix sidecar/autoskill/observatory`; full validation
  passed with `uv run ruff check sidecar`, `uv run pytest` (`353 passed`),
  `uv run python -m compileall -q sidecar`, `npm run build --prefix
  sidecar/autoskill/observatory`, `docker compose config --quiet`, and
  `git diff --check`. No compose/Postgres smoke was needed because this is a
  read-model shaping and frontend consumption change over the already-validated
  topology store metrics surface.
- Observatory topology operation microscope visibility is implemented for
  Sections 1.9, 7.7, 8.9, 9.3, 12.6, and 21.38: recent topology operation
  aggregates now drill into a content-safe operation object with trial rows,
  evidence/transaction/subject/output provenance refs, effect coverage,
  trial-summary metadata, and raw-content-disabled policy through
  `/admin/api/v1/topology/operations/{operation_id}` and the generic object
  microscope resolver. The React Skills/Topology view exposes selectable recent
  operations plus an Operation Evidence inspector without adding mutation
  authority. Focused validation passed with Observatory API/frontend source
  assertions (`2 passed`), generated OpenAPI client check, focused ruff, and
  `npm run build --prefix sidecar/autoskill/observatory`; full validation
  passed with `uv run ruff check sidecar`, `uv run pytest` (`354 passed`),
  `uv run python -m compileall -q sidecar`, `docker compose config --quiet`,
  `git diff --check`, and a real compose/Postgres smoke that migrated the
  schema, inserted one topology operation plus one planned trial through
  `AsyncpgTopologyStore`, read it back through the new detail method, verified
  `trial_count=1`, and cleaned the smoke rows.
- Observatory required-signal issue evidence is implemented for Sections 5.5,
  7.7, 12.6, and acceptance criterion 31: `missing-required-signal` issue-board
  rows now carry exact missing signal classes, missing metric keys, component
  evidence refs, and a specific safe next action; the generic issue microscope
  exposes the same content-safe evidence path instead of leaving operators with
  only a generic label. Validation passed with the focused Observatory API
  regression (`3 passed`), focused ruff checks, full `uv run ruff check
  sidecar`, full `uv run pytest` (`355 passed`), `uv run python -m compileall
  -q sidecar`, and `git diff --check`.
- Observatory guided diagnostic playbooks now expose the Section 7.5 current
  signal-state contract: `/admin/api/v1/playbooks/{id}` and the generic object
  microscope return severity, confidence, first checks, next views, supporting
  issue/component records, missing telemetry warnings, affected objects,
  content-safe next diagnostic actions, and explicit policy-blocked actions.
  The catalog now includes the required operator journeys for candidate drought,
  rejected improvements, context pressure, harmful activation, historical
  bootstrap yield, broker misses, read-model staleness, and stalled LLM
  maintenance without adding mutation authority or raw-content access.
  Validation passed with focused Observatory API tests (`35 passed`), focused
  ruff, full `uv run ruff check sidecar`, full `uv run pytest` (`356 passed`),
  `uv run python -m compileall -q sidecar`, `docker compose config --quiet`,
  and `git diff --check`. No compose/Postgres smoke was needed because this is
  a deterministic snapshot/read-model shaping slice over existing in-memory
  Observatory snapshot data.
- Observatory object microscope read-model fallbacks now keep missing telemetry
  and missing read models distinct for Sections 7.6, 7.7, and 12.6: unsupported
  object types return `read-model-missing` with `observatory_admin` as the
  supporting component instead of incorrectly reporting
  `missing-required-signal`. This preserves the required signal contract while
  giving operators a truthful dead-end explanation without raw-content access.
  Focused validation passed with the Observatory API regression (`2 passed`);
  final validation evidence is recorded in the implementation plan entry for
  this slice.
- Proposal-gate autonomy assurance is implemented for the replacement handoff
  autonomy-policy tranche: deterministic evaluator results now classify hard
  invariant failures separately from calibrated soft-threshold misses, attach
  non-admin autonomous fallback ladders, flag repeated soft-stall
  threshold-deadlock candidates, and expose the bounded assurance summary
  through evaluation review read models without relaxing scanner, regression,
  activation, rollback, or proposal-gate requirements. This advances core
  handoff Sections 5.1, 5.4-5.6, 5.10, 12.8-12.10, and production acceptance
  criteria 53-55 and 62-63. Focused validation passed with `uv run pytest -q
  sidecar/autoskill/tests/test_evaluator.py` (`11 passed`) and `uv run ruff
  check sidecar/autoskill/services/evaluator.py
  sidecar/autoskill/db/evaluations.py
  sidecar/autoskill/tests/test_evaluator.py`; full validation passed with
  `uv run ruff check sidecar scripts`, `uv run pytest` (`357 passed`),
  `uv run python -m compileall -q sidecar scripts`, `docker compose config
  --quiet`, and `git diff --check`.
- Observatory evaluation microscopes now expose proposal-gate autonomy assurance
  as content-safe operator evidence: `/admin/api/v1/evaluations/{id}` expands
  hard invariant failures, soft threshold misses, threshold-deadlock state,
  deterministic fallback actions, policy-blocked actions, and typed provenance
  refs for evaluated skill versions and threshold/invariant signals without raw
  probe payload access. This advances core handoff Sections 5.1, 5.6, 5.10,
  12.8-12.10 and Observatory Sections 7.6, 7.7, 8.14, 12.6, and 16.1/16.3.
  Focused validation passed with `uv run pytest -q
  sidecar/autoskill/tests/test_observatory_api.py` (`36 passed`) and `uv run
  ruff check sidecar/autoskill/api/app.py
  sidecar/autoskill/tests/test_observatory_api.py`; final validation passed
  with `uv run ruff check sidecar`, `uv run pytest` (`358 passed`), `uv run
  python -m compileall -q sidecar`, `docker compose config --quiet`, and
  `git diff --check`. No compose/Postgres smoke was needed because the slice
  reshapes an existing content-safe evaluation review read model without
  changing schema or worker persistence.

## Next Gates

1. Continue collecting sustained Dev-01 telemetry and add only distinct,
   operator-reviewed replay episodes from real usage, then run replay/canary
   tuning on the enlarged corpus.
2. Promote or replace the operator smoke runtime skill with the first genuinely
   useful SkillKernel-owned runtime skill once replay/probe evidence supports a
   non-smoke activation target.
3. Keep historical bootstrap consolidation tainted, propose-only, and subject
   to normal evidence/evaluator gates while collecting enough imported-history
   signal to validate the schema-backed v2 source-item locator layer under
   non-file ledgers and live source systems.
4. Roll out live repair/import execution only after production replay/embedding validation remains green under sustained traffic.

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
- Evidence derivation now creates observed event evidence plus deterministic recurring evidence clusters, and `usage.aggregate` now mines retrieval/attribution/co-use/context-token-ledger windows into topology evidence tables. Accepted recurring co-use clusters can now become propose-only compose topology operations; structured improve/decompose and broker-abstain consumption now exist, and contrastive induction consumes context-token-ledger outcomes plus marginal-value source metadata. Remaining work is sustained replay/canary validation under real traffic.
- Memory quarantine/control-flow tables and operator APIs now exist, the runtime broker can record approved memory-influenced retrieval decisions without injecting memory text while blocking unapproved memory references before retrieval, and repair/writer mutation paths now gate and log approved or blocked memory influence.
- Historical import now has durable source/chunk inventory, bounded discovery,
  parser checkpoint workers, redacted chunk storage, evidence derivation,
  provenance, embedding-source discovery, transcript-corpus export parsing, and
  source-rooted revocation traversal/invalidation. Plugin manifests/hooks/source
  files, media artifacts, and observability exports now have metadata-only
  source/chunk coverage. Historical chunks now also carry schema-backed v2
  source-item locator hashes beyond file/section/line references; worker
  bootstrap resolves bounded mounted OpenClaw state subroots when explicit roots
  are absent; historical imports still cannot activate candidates without the
  normal gates.
- Embedding generation defaults to deterministic local hash embeddings unless an active qualified embedding profile is configured; storage now supports profile-scoped variable dimensions, with the default 1536-dimensional path retaining the indexed HNSW fast path.
- Runtime context broker is still conservative: vector fusion is available through the active qualified embedding profile when present, with deterministic hash fallback for local tests; policy artifact replay/canary primitives exist, and stored redacted replay episodes can drive policy replay. Production replay quality still depends on deployment telemetry being populated and operator-reviewed replay episodes staying representative.
- Deployment readiness is a deterministic sidecar/state preflight, not a
  substitute for sustained telemetry review; the one-shot live gateway
  capture/hint smoke has passed for the current Dev-01 deployment.
- The first active SkillKernel-owned runtime skill is an operator-controlled
  smoke artifact with narrow applicability and no declared mutation capability;
  it proves writer apply/archive/rollback and backup coverage, but it should be
  replaced by a real utility-bearing skill after replay/probe evidence supports
  promotion.
- Repair execution remains guarded and fail-closed: explicit staged manifests still pass through activation-gated `writer.apply`, and policy-approved repair materialization can generate staged manifests from bounded repair proposals only when a skill-version anchor exists and deterministic context-governance proof with routing-equivalence and regression evidence can be recorded for the staged runtime artifact.
- External-skill awareness now includes read-only root scanning plus inventory/retrieval/matching, scan scheduling defaults, embedding generation for external descriptions, richer collision risk scoring, explicit operator review-action recording, and operator-approved stage-only import materialization.
- v16 trace/profile/context APIs and schema exist; event/job/retrieval/evaluator/context-broker paths now propagate trace or context artifacts, LLM calls now have content-safe invocation audit rows, direct writer apply/rollback APIs record content-safe writer spans, mutation-worker writer apply, revocation rollback, and topology downstream apply record content-safe child spans, embedding generation records content-safe `embedding_call` spans, and worker heartbeat summaries expose content-safe claimed/renewed/succeeded/failed job progress. Longer semantic jobs may still add specialized counters as their multi-phase internals mature.
- SkillGraphIR now has planner/API/store persistence with transactions, planned trials, first-class create/improve/compose/decompose proposal operations, revocation invalidation for operation/trial state, deterministic apply state transitions after passed trials, broker replay/canary scoring gates for compose/decompose routing, stored downstream action plans, and mutation-worker lifecycle/graph/runtime invalidation execution after accepted topology operations with transaction items/provenance edges tied to the originating evolution transaction.
- Operator visibility for SkillGraphIR topology now includes separate
  create/improve/compose/decompose metrics through `/v1/topology/metrics`;
  richer UI dashboards can build on this read-only sidecar surface.
- Operator visibility for retrieval policy now includes a read-only
  `/v1/broker/policies/review` endpoint that fails closed on missing active
  policy or invalid audit-chain verification and warns on missing replay
  evidence.
- Candidate evaluator execution is deterministic and conservative; no-skill-control probes can now pass/fail with recorded or induced redacted intervention replay from explicit replay, attribution, canary, or broker outcome evidence.
- Candidate proposal persistence is transaction-anchored, and staged writer apply/rollback plus canary freeze now have sidecar control endpoints; mutation-worker apply exists but fails closed unless the queued job is explicitly policy-approved.
- Revocation traversal now previews impacted derived artifacts, staged writer artifacts have provenance edges, and critical canary failures can freeze skills plus queue rollback revocation requests. Mutation-worker rollback execution is implemented for archive-backed rollbacks and initial-create active-path deletion, invalidates body-index/embedding/context/retrieval/topology/evaluator/attribution/governance objects from traversal summaries, and freeze/critical-canary paths evict affected broker cache entries.
- Utility rollups are deterministic v1 scoring, not full intervention scoring yet; curation now handles archived promotion, explicit duplicate merge/archive, low-utility archive, active-bank budget overflow, context-value/token-waste features, evaluator blocking, duplicate merge probe planning, and planned split/improvement/disambiguation actions with structured repair proposals. Conservative repair execution now claims planned repairs, records governance/provenance, queues evaluator or policy-approved writer work, and can generate guarded staged repair manifests from policy-approved bounded proposals.
- Context-value/token ledgers feed utility rollups, repair planning, and
  usage/topology consumers for improve, decompose, tighten-description, and
  broker-abstain recommendations; remaining work is sustained production
  replay/canary validation of those actions under real traffic.
- Support artifacts now have SkillIR/schema representation, writer-manifest
  scan/token/provenance coverage, apply/archive/rollback handling, and
  declaration-only context-governance excerpt registration. Runtime guard
  templates now have fixed declarative SkillIR representation and compiler
  projection. Remaining support work is sustained operational validation of
  retrieval policy boundaries.
- Contract/drift checks are deterministic v1 path/command/env/package/schema/TCP/HTTP-status probes only; drift probe creation/retirement, localized repair metadata, live API status probes, operator false-positive suppression, and conservative repair execution/recheck queueing are implemented.
- Diagnostic momentum now feeds conservative repair execution as an additional
  fail-closed source; it still queues normal drift/evaluator gates unless a
  policy-approved staged manifest with scanner/evaluator/context proof exists.
