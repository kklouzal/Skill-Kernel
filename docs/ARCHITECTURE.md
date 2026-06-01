# Architecture

SkillKernel is split into a thin OpenClaw plugin and a durable sidecar.

## OpenClaw Plugin

The plugin is allowed to:

- register in-process OpenClaw hooks;
- construct typed event envelopes;
- redact and taint before persistence or forwarding;
- spool locally when the sidecar is unavailable;
- forward batches to the localhost sidecar;
- expose status/control/diagnostic surfaces;
- verify active/archive roots;
- optionally inject a tiny cached runtime context hint.

The plugin is not allowed to:

- run slow LLM analysis;
- schedule autonomous maintenance;
- mutate generated skills;
- write arbitrary files;
- make final scanner/evaluator/policy decisions.

## Python Sidecar

The sidecar owns:

- authenticated ingest/control/runtime APIs;
- Postgres migrations and data access;
- durable scheduler and job queue;
- evidence extraction and governed memory;
- hybrid retrieval and body-aware routing;
- SkillIR validation, compilation, scanner, evaluator, and deterministic writer;
- evolution transactions, audit, rollback, quarantine, freeze, and derived-data revocation.

## Source of Truth

`SkillIR` is the canonical representation. Generated `SKILL.md` files are compiled OpenClaw-facing runtime artifacts.

The compiler is deterministic and enforces:

- required SkillIR fields;
- fixed runtime sections;
- OpenClaw skill name and frontmatter constraints;
- token/length budgets;
- scanner pass before activation;
- hashes and manifests for every emitted artifact.

## Transaction Boundary

Every autonomous mutation must be represented as one evolution transaction spanning:

- database rows;
- SkillIR revisions;
- compiled files;
- manifests and hashes;
- embeddings and retrieval caches;
- broker cache invalidations;
- probe additions;
- lifecycle state;
- audit records.

Rollback is graph-aware. It must revoke downstream derived state, not only replace one file.

