# SkillKernel

SkillKernel is the project home for **OpenClaw AutoSkill Manager**, internal codename `autoskill`.

The closed-design handoff is the controlling source for architecture and implementation priorities:

- `skillkernel-openclaw-autoskill-ultimate-v16-coherence-closed-implementation-handoff.md`

The v1 implementation follows the handoff's fixed architecture:

- one OpenClaw plugin for lightweight capture, redaction, spooling, forwarding, status/control, and optional cached runtime context hints;
- one Python sidecar for durable scheduling, database work, retrieval, scanning, evaluation, deterministic writing, rollback, and governance;
- one Postgres database with one `autoskill` schema and pgvector;
- canonical SkillIR as the source of truth;
- generated OpenClaw `SKILL.md` files as runtime artifacts, never as the internal canonical representation.

## Current Status

This repository is in Phase 10/11 v16 coherence closure and production-hardening buildout.

Implemented now:

- project structure, durable local instructions, and implementation plan tracking;
- sidecar API with health/status, ingest, context hints, retrieval, embeddings, worker, topology, profile, drift, writer, and control endpoints;
- DB-backed idempotent ingest for redacted event envelopes;
- optional bearer-token auth for event ingest;
- optional bearer-token auth for control/job APIs;
- Postgres-backed job enqueue, idempotency, claim, completion, expired-lease recovery, heartbeat, and lease-renewal primitives;
- sidecar-owned scheduler tick primitive and durable worker pools for scheduler, maintenance, and mutation jobs;
- deterministic evidence derivation from redacted raw events with provenance edges and recurring-evidence clusters;
- retrieval schema support for body index documents, pgvector embeddings, lexical indexes, vector fusion, retrieval logs, and broker telemetry;
- profile-owned embedding storage and search with variable-dimension support;
- typed event envelope, SkillIR, SkillGraphIR, scanner, compiler, redaction, audit hash, trace spine, and path-contained writer primitives;
- deterministic first-pass scanner classifications for hidden content,
  secret-like material, dynamic fetch-exec, policy override, credential
  exfiltration, destructive host commands, and sensitive file harvesting;
- staged writer apply/rollback, provenance traversal, revocation invalidation, canary freeze, and mutation-worker rollback paths;
- topology proposal, trial, apply, downstream action, and invalidation primitives;
- topology-specific broker replay/canary trial scoring for compose/decompose apply gates;
- read-only proposal review/status surface for candidate revisions, topology
  operations, and proposal-gate evaluations;
- curation, utility, duplicate-merge probe planning, repair proposal planning, guarded repair materialization, drift probes, false-positive controls, and HTTP-status contract probes;
- external-skill operator review plus stage-only import materialization that never mutates external-owned roots;
- runtime action-attribution check recording for blocked high-risk tool-boundary decisions;
- active embedding-profile selection, profile-qualified queued embedding generation, content-safe embedding generation trace spans, and production embedding validation control API;
- redacted broker replay episode corpus recording plus stored-corpus broker policy replay;
- deployment readiness preflight, operator backup/restore bundle scripts, and a
  deterministic scanner red-team smoke runner;
- runtime context-hint request compatibility for both `user_intent` and `intent`
  payloads;
- deployed Dev-01 plugin policy with fail-soft runtime context hints enabled,
  raw conversation capture disabled, runtime tool-boundary blocking disabled, and
  environment fallback coverage for hook contexts that do not receive explicit
  plugin config;
- OpenClaw plugin/hook package with local redaction, bounded spool, forwarding, replay utilities, and smoke-tested hook loading;
- focused Python, Node, and local Postgres compose smoke validation for deterministic primitives.

Deployment/operator gates still outside repo implementation:

- larger production broker replay corpus population from sustained redacted
  deployment telemetry;
- live production repair/import rollout after replay/embedding validation remains
  green under sustained traffic.

## Development

Python sidecar:

```bash
cd /Warehouse/SkillKernel
uv sync --group dev
uv run pytest
uv run python -m compileall sidecar
```

Run the sidecar locally:

```bash
uv run uvicorn autoskill.main:app --app-dir sidecar --host 127.0.0.1 --port 8765
```

## Docker Deployment

The portable Docker deployment is split into two SkillKernel application
images plus a stock pgvector Postgres container:

- `Dockerfile.core` builds the Python SkillKernel core image. It contains the
  sidecar API, migrations, scripts, and worker entrypoints.
- `Dockerfile.observatory` builds the Observatory web image. It contains the
  compiled React UI and an nginx reverse proxy for `/admin/api`, `/admin/live`,
  and `/admin/live-sse` back to the core container.
- `postgres` uses `pgvector/pgvector:pg17`. Postgres stores vectors; it does
  not generate embeddings.

SkillKernel expects user-supplied OpenAI-compatible model services:

- `AUTOSKILL_LLM_API_BASE_URL` / `AUTOSKILL_LLM_API_KEY` configure the LLM
  endpoint.
- `AUTOSKILL_EMBEDDING_API_BASE_URL` / `AUTOSKILL_EMBEDDING_API_KEY`,
  `AUTOSKILL_EMBEDDING_MODEL`, and `AUTOSKILL_EMBEDDING_DIM` configure the
  embedding endpoint.

Dev-01 currently points those values at the local `llama-cpp-compaction` and
`llama-cpp-embeddings` containers. Other installs can point them at any
compatible local or hosted provider.

Prepare a local environment file and start the portable stack:

```bash
cp .env.example .env
mkdir -p .skillkernel/workspace .skillkernel/openclaw
docker compose up --build
```

By default, the core API is published on `127.0.0.1:8765` and Observatory is
published on `127.0.0.1:8757/admin/`. Set `SKILLKERNEL_CORE_BIND` or
`SKILLKERNEL_OBSERVATORY_BIND` to expose them on another interface.

The core image never mounts Observatory static files. Development and
production both use the same contract: rebuild/redeploy the split containers so
the nginx Observatory image serves the compiled React app while core serves the
API, live streams, and readiness routes.

Validate the OpenClaw plugin skeleton:

```bash
cd /Warehouse/SkillKernel/plugin/autoskill
npm run check
npm test
```

Create and verify an operator disaster-recovery bundle:

```bash
python scripts/autoskill_backup.py --workspace-root /home/kklouzal/.openclaw/workspace --output-dir /tmp/skillkernel-autoskill-backups --include-staging
python scripts/autoskill_restore.py /path/to/autoskill-backup.tar.gz --workspace-root /home/kklouzal/.openclaw/workspace --dry-run
```

Run the deterministic scanner red-team smoke:

```bash
python scripts/autoskill_red_team.py --output /tmp/autoskill-red-team.json
```

Emit the production acceptance crosswalk:

```bash
python scripts/autoskill_acceptance.py --json
```

Emit the Observatory web/admin acceptance crosswalk:

```bash
python scripts/autoskill_observatory_acceptance.py --json
```

Regenerate the Observatory frontend admin API route client from FastAPI OpenAPI:

```bash
python scripts/generate_observatory_openapi_client.py
```

Validate the deterministic Observatory E2E/load/visual fixture catalog:

```bash
python scripts/autoskill_observatory_fixtures.py --check
```

Emit the Section 32/33 risk and developer handoff crosswalk:

```bash
python scripts/autoskill_handoff.py --json
```

Emit the Section 34 research traceability crosswalk:

```bash
python scripts/autoskill_traceability.py --json
```

Emit the unified landscape and readiness checklist crosswalk:

```bash
python scripts/autoskill_readiness.py --json
```

Run the Part V static implementation conformance gate:

```bash
python scripts/autoskill_conformance.py --json
```

List content-safe broker replay candidates from retrieval telemetry:

```bash
python scripts/autoskill_replay_corpus.py candidates --workspace-id dev-01 --distinct-query-hash
```

Record replay episodes from an operator-supplied JSON plan. The plan must
provide explicit `redacted_user_intent` text; retrieval telemetry stores hashes
and selected skill IDs, not raw prompts.

```bash
python scripts/autoskill_replay_corpus.py record --plan /path/to/replay-plan.json
```

Inspect the installed hook-only plugin runtime surface:

```bash
openclaw plugins inspect autoskill --json --runtime
```

## Non-Negotiables

- No per-skill databases.
- No per-skill schemas in v1.
- No OpenClaw Cron dependency.
- No Skill Workshop dependency.
- No LLM-controlled SQL, paths, file writes, shell commands, scheduler state, policy decisions, or rollback.
- No raw secrets or private user facts in SkillIR, `SKILL.md`, support files, probes, embeddings, or logs.
- Core infrastructure is not autonomously self-rewritten in v1.
