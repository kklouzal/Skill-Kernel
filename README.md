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
- curation, utility, duplicate-merge probe planning, repair proposal planning, guarded repair materialization, drift probes, false-positive controls, and HTTP-status contract probes;
- external-skill operator review plus stage-only import materialization that never mutates external-owned roots;
- runtime action-attribution check recording for blocked high-risk tool-boundary decisions;
- active embedding-profile selection, profile-qualified queued embedding generation, content-safe embedding generation trace spans, and production embedding validation control API;
- redacted broker replay episode corpus recording plus stored-corpus broker policy replay;
- deployment readiness preflight, operator backup/restore bundle scripts, and a
  deterministic scanner red-team smoke runner;
- runtime context-hint request compatibility for both `user_intent` and `intent`
  payloads;
- OpenClaw plugin/hook package with local redaction, bounded spool, forwarding, replay utilities, and smoke-tested hook loading;
- focused Python, Node, and local Postgres compose smoke validation for deterministic primitives.

Deployment/operator gates still outside repo implementation:

- production plugin policy enablement outside the development profile;
- production embedding provider validation against the real deployment endpoint and
  credentials using the validation API;
- production broker replay corpus population from redacted deployment telemetry;
- live production repair/import rollout after operator config enables the plugin
  outside the development profile.

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

Create and verify an operator disaster-recovery bundle:

```bash
python scripts/autoskill_backup.py --workspace-root /home/kklouzal/.openclaw/workspace --output-dir /tmp/skillkernel-autoskill-backups --include-staging
python scripts/autoskill_restore.py /path/to/autoskill-backup.tar.gz --workspace-root /home/kklouzal/.openclaw/workspace --dry-run
```

Run the deterministic scanner red-team smoke:

```bash
python scripts/autoskill_red_team.py --output /tmp/autoskill-red-team.json
```

## Non-Negotiables

- No per-skill databases.
- No per-skill schemas in v1.
- No OpenClaw Cron dependency.
- No Skill Workshop dependency.
- No LLM-controlled SQL, paths, file writes, shell commands, scheduler state, policy decisions, or rollback.
- No raw secrets or private user facts in SkillIR, `SKILL.md`, support files, probes, embeddings, or logs.
- Core infrastructure is not autonomously self-rewritten in v1.
