# SkillKernel

SkillKernel is the project home for **OpenClaw AutoSkill Manager**, internal codename `autoskill`.

The closed-design handoff is the controlling source for architecture and implementation priorities:

- `openclaw-autoskill-ultimate-v9-closed-design-handoff.md`

The v1 implementation follows the handoff's fixed architecture:

- one OpenClaw plugin for lightweight capture, redaction, spooling, forwarding, status/control, and optional cached runtime context hints;
- one Python sidecar for durable scheduling, database work, retrieval, scanning, evaluation, deterministic writing, rollback, and governance;
- one Postgres database with one `autoskill` schema and pgvector;
- canonical SkillIR as the source of truth;
- generated OpenClaw `SKILL.md` files as runtime artifacts, never as the internal canonical representation.

## Current Status

This repository is in Phase 0/1 bootstrap.

Implemented now:

- project structure and durable local instructions;
- sidecar API skeleton with health/status/ingest/context-hint endpoints;
- DB-backed idempotent ingest for redacted event envelopes;
- optional bearer-token auth for event ingest;
- optional bearer-token auth for control/job APIs;
- Postgres-backed job enqueue, idempotency, claim, completion, and expired-lease recovery primitives;
- sidecar-owned scheduler tick primitive that creates idempotent jobs from due schedules;
- deterministic evidence derivation from redacted raw events with provenance edges;
- retrieval schema support for body index documents, pgvector embeddings, lexical indexes, and retrieval logs;
- deterministic lexical retrieval API over evidence/body-index records;
- typed event envelope, SkillIR, scanner, compiler, redaction, audit hash, and path-contained writer primitives;
- initial Postgres migration covering the core v9 control-plane tables;
- OpenClaw plugin/hook package skeleton with local redaction, bounded spool, forwarding, and replay utilities;
- OpenClaw plugin diagnostics for sidecar status and spool size;
- hook-package smoke tests that import the actual handlers and verify forwarded redacted envelopes;
- focused Python and Node tests for deterministic primitives.

Not implemented yet:

- full installed-plugin proof against the live OpenClaw gateway;
- embedding generation and pgvector candidate search;
- durable worker dispatch loops;
- LLM proposal operations;
- evaluator/probe execution;
- autonomous apply.

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
