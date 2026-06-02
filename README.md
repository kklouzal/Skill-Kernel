# SkillKernel

SkillKernel is the project home for **OpenClaw AutoSkill Manager**, internal codename `autoskill`.

The closed-design handoff is the controlling source for architecture and implementation priorities:

- `skillkernel-openclaw-autoskill-ultimate-v16-coherence-closed-implementation-handoff.md`
- `openclaw-autoskill-ultimate-v9-closed-design-handoff.md` is retained as an earlier baseline.

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
- staged writer apply/rollback, provenance traversal, revocation invalidation, canary freeze, and mutation-worker rollback paths;
- topology proposal, trial, apply, downstream action, and invalidation primitives;
- curation, utility, duplicate-merge probe planning, repair proposal planning, drift probes, false-positive controls, and HTTP-status contract probes;
- OpenClaw plugin/hook package with local redaction, bounded spool, forwarding, replay utilities, and smoke-tested hook loading;
- focused Python, Node, and local Postgres compose smoke validation for deterministic primitives.

Not implemented yet:

- production plugin policy enablement outside the development profile;
- production embedding provider live validation once credentials and endpoint are configured;
- richer broker replay and canary policy feedback for compose/decompose routing decisions;
- optional operator-approved import materialization for external skills;
- autonomous execution of repair proposals.

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

Validate the OpenClaw plugin skeleton:

```bash
cd /Warehouse/SkillKernel/plugin/autoskill
npm run check
npm test
```

## Non-Negotiables

- No per-skill databases.
- No per-skill schemas in v1.
- No OpenClaw Cron dependency.
- No Skill Workshop dependency.
- No LLM-controlled SQL, paths, file writes, shell commands, scheduler state, policy decisions, or rollback.
- No raw secrets or private user facts in SkillIR, `SKILL.md`, support files, probes, embeddings, or logs.
- Core infrastructure is not autonomously self-rewritten in v1.
