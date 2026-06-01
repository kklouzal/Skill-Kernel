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
- Initial sidecar, migration, plugin skeleton, and deterministic primitive tests are being created.

## Next Gates

1. Confirm exact OpenClaw hook event names and return contracts against the local OpenClaw checkout.
2. Run Python tests and compile checks.
3. Validate plugin manifest/hook package shape with OpenClaw plugin tooling or a local fixture.
4. Add real DB migration runner and idempotent ingest writes.
5. Add sidecar auth and spool replay.

## Known Risks

- Hook event names are currently scaffolded from local code inspection and must be confirmed with an installed plugin smoke test before relying on capture coverage.
- The sidecar ingest endpoint currently validates/redacts/acknowledges events but does not write to Postgres yet.
- The OpenClaw plugin currently spools on sidecar failure but does not yet implement replay or bounded spool compaction.

