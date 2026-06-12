# SkillKernel

**SkillKernel** is the repository for the OpenClaw **AutoSkill Manager** (`autoskill`):
a governed skill-library control plane that observes OpenClaw work, turns repeated
operator patterns into canonical `SkillIR`, compiles safe runtime `SKILL.md`
artifacts, and keeps the library useful through retrieval, evaluation, rollback,
and operator review.

SkillKernel is built for people operating or extending OpenClaw installations
where skills are not just prompt snippets. They are procedural-memory artifacts
with provenance, scanner gates, model/embedding profile constraints, topology
relationships, and rollback requirements.

> **Status:** active production-hardening and Observatory buildout. The
> repository contains substantial sidecar, plugin, database, UI, Docker, and test
> coverage, but broad live rollout remains intentionally gated by replay corpus,
> embedding/profile validation, and operator acceptance evidence.

## What SkillKernel does

SkillKernel separates fast runtime capture from slower governed skill evolution:

- **one OpenClaw plugin** captures typed hook events, redacts locally, spools
  when Core is unavailable, forwards batches to the sidecar, and can inject a
  small fail-soft runtime context hint;
- **one Python sidecar** stores redacted evidence in Postgres, schedules durable
  worker jobs, derives evidence, manages retrieval, evaluates proposals, writes
  staged artifacts, records provenance, and rolls back derived state;
- **SkillIR** is the canonical source of truth for SkillKernel-owned skills;
  generated OpenClaw `SKILL.md` files as runtime artifacts are compiled from
  that canonical form;
- **Observatory** gives operators a web control room for pipeline health,
  issues, traces, skills, topology operations, replay evidence, storage state,
  and guarded admin actions.

The design goal is controlled autonomy: generate less, validate more, compile
tighter, route smarter, attribute causally, and evolve transactionally.

## Current capabilities

The current repository implements the following product surfaces.

| Area | Implemented surfaces |
| --- | --- |
| OpenClaw capture | Runtime plugin package, typed hook registration, local redaction, bounded spool/replay, sidecar forwarding, runtime context-hint hook, optional tool-boundary blocking, hook smoke tests. |
| Data plane | One `autoskill` Postgres schema, pgvector extension, migrations for workspaces, events, evidence, skills, SkillIR revisions, embeddings, scheduler/jobs, traces, governance, topology, Observatory read models, audit, quarantine, and revocation state. |
| Core API | FastAPI `/v1` health, readiness, ingest, raw evidence, memory quarantine, control-flow, runtime context hints, profiles, topology, evidence, candidates, evaluations, writer, rollback, retrieval, embeddings, jobs, schedules, workers, traces, metrics, and audit endpoints. |
| Worker model | Durable worker pools for scheduler, ingest, backfill, embedding, retrieval, analysis, LLM generation, scanner, evaluation, filesystem, and maintenance work. |
| Retrieval and broker | Body index documents, lexical indexes, pgvector embeddings, retrieval logs/events, runtime broker policy versions, context artifacts, token ledgers, compile runs, budget events, and broker replay episodes. |
| Skill governance | SkillIR and SkillGraphIR primitives, deterministic compiler, scanner, evaluator/probes, candidate proposals, topology proposal/trial/apply records, proposal review, lifecycle state, canary/freeze, provenance traversal, revocation, staged writer apply, and rollback. |
| Safety controls | Redaction-before-store/embed defaults, raw-vault access logging, memory quarantine, control-flow events, harmful-capability and prompt-injection scanner classes, action-attribution checks, forbidden hidden markdown, generated skill network/shell defaults off, and admin raw-content defaults off. |
| Historical/bootstrap import | Source discovery, dry-run inventory, historical import tables, chunking, taint/confidence controls, bootstrap candidate generation, lower trust for stale/summary evidence, and stage-only external-skill import review. |
| Model and embedding profiles | Operator-selected OpenAI-compatible text and embedding endpoints, profile records, qualification runs, active embedding selection, profile-qualified queued embedding generation, content-safe embedding traces, and production embedding validation API. |
| Observatory | Split web/API container, React UI, 30-station assembly-line map, subsystem workcells, station cockpit, issue board, search, skills/topology views, gates/autonomy views, trace replay, broker replay corpus, storage diagnostics, live WebSocket/SSE updates, action gateway, CSRF/auth handling, generated API client, and deterministic UI fixture catalog. |
| Operations | Deployment readiness endpoint, backup/restore scripts, acceptance/readiness/conformance/traceability reports, deterministic scanner red-team runner, replay-corpus tooling, and Docker/GHCR packaging workflow. |

## Architecture at a glance

```text
OpenClaw runtime
   │
   │ typed hooks, redaction, spool, replay, context-hint requests
   ▼
OpenClaw AutoSkill plugin (`plugin/autoskill`)
   │
   │ redacted event envelopes / control requests
   ▼
SkillKernel Core (`sidecar/autoskill` FastAPI + workers)
   │
   ├─ Postgres + pgvector (`autoskill` schema)
   ├─ evidence, memory, retrieval, profiles, jobs, traces
   ├─ candidate generation, evaluation, scanner, topology governance
   ├─ deterministic SkillIR → `SKILL.md` compiler/writer
   └─ provenance-aware rollback, quarantine, freeze, audit
   │
   ▼
OpenClaw workspace skill root
`skills/autoskill/<slug>/SKILL.md`

Observatory (`/admin`) reads the same governance plane and exposes operator
status, drill-downs, live updates, and guarded admin actions.
```

See also:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the component boundary;
- [`docs/OPENCLAW_SEAMS.md`](docs/OPENCLAW_SEAMS.md) for grounded OpenClaw hook
  seams and plugin constraints;
- [`unified-implementation-specification.md`](unified-implementation-specification.md)
  for the controlling architecture and acceptance specification;
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) for phase-level
  implementation tracking.

## Repository layout

```text
.
├── plugin/autoskill/                 # OpenClaw runtime hook plugin
├── sidecar/autoskill/                # Core API, services, DB access, workers, Observatory backend
├── sidecar/autoskill/observatory/    # React/Vite Observatory UI
├── migrations/                       # Single autoskill schema migration set
├── scripts/                          # acceptance, readiness, backup/restore, replay, red-team utilities
├── compose/                          # portable split-container reference topology
├── containers/                       # split Core and Observatory container entrypoints/health checks
├── Dockerfile.core                   # Core image built by CI/GHCR workflow
├── Dockerfile.observatory            # Observatory image built by CI/GHCR workflow
├── docker-compose.yml                # local/site-oriented development topology
├── pyproject.toml                    # Python project, pytest, Ruff config
└── .github/workflows/publish-ghcr.yml # lint/test/build/publish workflow
```

## Quick start for development

Prerequisites:

- Python 3.12 or newer;
- [`uv`](https://github.com/astral-sh/uv) for Python dependency management;
- Node.js 24 for the plugin and Observatory UI;
- Docker if you want Postgres/pgvector or the split-container topology;
- OpenAI-compatible LLM and embedding endpoints for generation/embedding paths
  that require models.

Install Python development dependencies and run the deterministic Python tests:

```bash
git clone https://github.com/kklouzal/Skill-Kernel.git
cd Skill-Kernel
uv sync --group dev
uv run pytest
```

Run Core locally:

```bash
uv run uvicorn autoskill.main:app --app-dir sidecar --host 127.0.0.1 --port 8765
```

Validate the OpenClaw plugin package:

```bash
cd plugin/autoskill
npm run check
npm test
```

Build the Observatory UI:

```bash
cd sidecar/autoskill/observatory
npm ci
npm run build
```

## Portable Docker topology

The portable reference deployment is the split-container topology in
[`compose/`](compose/):

- `postgres` uses `pgvector/pgvector:pg17` for storage and vector indexes;
- `core` runs the SkillKernel API, migrations, scripts, and worker entrypoints;
- `observatory` serves the compiled React UI plus the Observatory API surface;
- secrets are mounted through `*_FILE` variables rather than inline environment
  values;
- default ports bind to loopback (`127.0.0.1`) unless you deliberately change
  the bind variables.

Create local secret files and validate the Compose model:

```bash
mkdir -p compose/secrets .skillkernel/workspace .skillkernel/openclaw
printf '%s\n' 'change-me' > compose/secrets/postgres_password.txt
printf '%s\n' 'postgresql://skillkernel:change-me@postgres:5432/skillkernel' > compose/secrets/database_url.txt
printf '%s\n' 'replace-with-plugin-shared-secret' > compose/secrets/plugin_shared_secret.txt
printf '%s\n' 'replace-with-control-token' > compose/secrets/control_token.txt
printf '%s\n' 'replace-with-admin-token' > compose/secrets/admin_token.txt

docker compose -f compose/compose.example.yml config --quiet
```

Then start the reference stack:

```bash
docker compose -f compose/compose.example.yml up --build
```

Core defaults to `127.0.0.1:8765`. Observatory defaults to
`127.0.0.1:8757/admin/`.

For LLM-backed candidate generation, evaluation support, and embedding
generation, configure operator-supplied OpenAI-compatible endpoints with:

```text
AUTOSKILL_LLM_API_BASE_URL
AUTOSKILL_LLM_API_KEY
AUTOSKILL_EMBEDDING_API_BASE_URL
AUTOSKILL_EMBEDDING_API_KEY
AUTOSKILL_EMBEDDING_MODEL
AUTOSKILL_EMBEDDING_DIM
```

Postgres stores vectors; it does not generate embeddings.

## Configuration model

SkillKernel accepts the historical `AUTOSKILL_*` environment names and newer
`SKILLKERNEL_*` aliases for deployment secrets. The most important settings are:

| Setting | Purpose |
| --- | --- |
| `SKILLKERNEL_DATABASE_URL` / `AUTOSKILL_DATABASE_URL` | Postgres DSN for Core, workers, and Observatory read models. |
| `SKILLKERNEL_SIDECAR_TOKEN` / `AUTOSKILL_INGEST_TOKEN` | Shared token for plugin-to-Core ingest. Set this before exposing ingest beyond localhost. |
| `SKILLKERNEL_CONTROL_TOKEN` / `AUTOSKILL_CONTROL_TOKEN` | Token for control/job/admin-like Core APIs. |
| `SKILLKERNEL_ADMIN_TOKEN` / `AUTOSKILL_WEB_ADMIN_TOKEN` | Bearer token for Observatory non-liveness endpoints. |
| `AUTOSKILL_WORKSPACE_ID` | Workspace partition key used in records, reports, and replay tooling. |
| `AUTOSKILL_ACTIVE_ROOT` | Runtime skill root, defaulting to `skills/autoskill`. |
| `AUTOSKILL_ARCHIVE_ROOT` | Archive root for inactive artifacts and rollback material. |
| `AUTOSKILL_STAGING_ROOT` | Staging root for proposed/generated artifacts before activation. |
| `AUTOSKILL_RUNTIME_CONTEXT_BROKER_ENABLED` | Enables runtime context-hint requests from the plugin. Defaults off. |
| `AUTOSKILL_PLUGIN_CAPTURE_RAW_CONVERSATION` | Enables raw capture handshake paths. Defaults off. |
| `AUTOSKILL_WEB_ADMIN_RAW_CONTENT_ENABLED` | Enables raw-content reveal paths in admin surfaces. Defaults off. |
| `AUTOSKILL_ALLOW_NETWORK_IN_GENERATED_SKILLS` | Allows generated skills to include network capability. Defaults false. |
| `AUTOSKILL_ALLOW_SHELL_IN_GENERATED_SKILLS` | Allows generated skills to include shell capability. Defaults false. |

Use `/v1/config/effective` or `/admin/api/v1/config/effective` to inspect the
non-secret effective configuration.

## Operator workflows

SkillKernel is designed around explicit gates and reviewable evidence. Common
operator workflows include:

### 1. Capture and ingest redacted runtime evidence

Install and enable the OpenClaw plugin, configure the sidecar URL/token, and let
it forward redacted hook envelopes. If Core is unavailable, the plugin uses a
bounded local spool and replays when forwarding succeeds again.

### 2. Mine evidence and propose skills

Core derives evidence from redacted events, historical imports, external skill
inventory, body indexes, and retrieval telemetry. Candidate generation remains
proposal-gated; generated runtime artifacts are staged until scanner,
evaluator/probe, semantic-equivalence, token-budget, and writer manifest checks
pass.

### 3. Review Observatory health and issues

Open Observatory at `/admin/` with an admin token. The UI exposes a pipeline map,
subsystem lenses, station cockpit views, issue board, search, skills/topology,
gates/autonomy, traces, replay corpus, storage/read-model status, and audited
action gateway.

### 4. Validate broker and topology behavior

Use broker replay episodes, topology operation trials, canary results, and
retrieval logs to decide whether skills should be created, improved, composed,
decomposed, archived, or left alone.

### 5. Back up, restore, and roll back

Use the operator scripts to create disaster-recovery bundles and verify restore
plans before changing a live workspace. Writer rollback is provenance-aware: it
invalidates downstream derived state instead of only replacing a file.

```bash
uv run python scripts/autoskill_backup.py \
  --workspace-root /path/to/openclaw/workspace \
  --output-dir /tmp/skillkernel-autoskill-backups \
  --include-staging

uv run python scripts/autoskill_restore.py \
  /path/to/autoskill-backup.tar.gz \
  --workspace-root /path/to/openclaw/workspace \
  --dry-run
```

## Validation and acceptance checks

The smallest useful local checks are:

```bash
uv run ruff check .
uv run pytest
uv run python -m compileall sidecar

cd plugin/autoskill
npm run check
npm test
```

Observatory-specific checks:

```bash
cd sidecar/autoskill/observatory
npm ci
npm run build
npm run fixtures:check
```

Static/product acceptance reports:

```bash
uv run python scripts/autoskill_acceptance.py --json
uv run python scripts/autoskill_observatory_acceptance.py --json
uv run python scripts/autoskill_handoff.py --json
uv run python scripts/autoskill_traceability.py --json
uv run python scripts/autoskill_readiness.py --json
uv run python scripts/autoskill_conformance.py --json
uv run python scripts/autoskill_red_team.py --output /tmp/autoskill-red-team.json
```

CI currently runs Ruff, deterministic Python tests, the SQL-backed revocation
traversal smoke against disposable `pgvector/pgvector:pg17`, plugin
syntax/tests, Observatory build, Docker image build tests, and GHCR publication
for the split Core and Observatory images on configured refs.

## Security and privacy posture

SkillKernel treats memory, retrieval, and generated skills as control-plane
inputs, not passive logs.

Important defaults and caveats:

- redaction-before-store and redaction-before-embed are enabled by default;
- raw conversation capture is disabled by default;
- raw-content display in Observatory is disabled by default;
- generated skill network and shell capabilities default to false;
- hidden markdown, secret-like content, dynamic fetch-exec patterns,
  credential exfiltration, destructive host commands, and sensitive file
  harvesting are scanner concerns;
- LLMs do not own SQL, paths, file writes, shell commands, scheduler state,
  policy decisions, or rollback;
- admin/control endpoints should not be exposed publicly without tokens, TLS,
  and an operator-owned reverse proxy/access policy;
- local model and embedding providers must be qualified by operators; SkillKernel
  records profile validation rather than assuming a provider is safe;
- historical imports and summary-derived evidence are lower trust than live typed
  capture and are capped by taint/confidence policy.

These controls reduce risk but are not a compliance certification, formal
security audit, or guarantee that generated skills are safe in every OpenClaw
deployment. Treat activation as an operator decision backed by evidence.

## Limitations and rollout gates

Known limits in the current repository state:

- the project is still in active production-hardening/Observatory closure, not a
  finished one-command appliance;
- live production repair/import rollout remains gated on sustained green replay,
  embedding/profile validation, and operator acceptance evidence;
- model-backed behavior depends on the quality and availability of
  operator-supplied OpenAI-compatible LLM and embedding services;
- Docker examples are reference topologies; operators still need to manage TLS,
  backups, secret rotation, network exposure, and OpenClaw installation policy;
- no standalone `LICENSE` file is present in this repository yet, so licensing
  should be clarified before broad redistribution;
- no public funding file or support contract path is committed in this repository
  yet.

## Contributing

Good contributions are evidence-grounded and preserve the separation of powers:

- do not make the plugin run slow analysis or mutate skills;
- do not let LLM output directly control SQL, paths, scheduler state, policy,
  shell commands, or rollback;
- keep `SkillIR` canonical and generated `SKILL.md` deterministic;
- add tests or acceptance-report coverage for new governance behavior;
- prefer stage/propose/review flows over direct activation;
- keep private topology, secrets, and local operator infrastructure out of public
  examples.

Before opening a change, run the smallest checks relevant to the files touched.
For broad sidecar changes, run Ruff and the deterministic Python suite. For
plugin changes, run `npm run check` and `npm test` under `plugin/autoskill`. For
Observatory changes, run `npm run build` and fixture validation.

## Support and sustainability

SkillKernel is an operator-heavy project: sustaining it means maintaining test
coverage, replay corpora, model/profile qualification, security scanning,
Observatory polish, deployment documentation, and careful OpenClaw compatibility
work.

There is not yet a funding link committed in this repository. If SkillKernel is
useful to your OpenClaw work today, the highest-value support paths are:

- test it against non-private OpenClaw workspaces and report reproducible issues;
- contribute docs, fixtures, replay cases, scanner examples, and validation
  improvements;
- review deployment and security documentation for real operator gaps;
- sponsor future work once an official funding path is published.

## Non-negotiables

- No per-skill databases.
- No per-skill schemas in v1.
- No OpenClaw Cron dependency.
- No Skill Workshop dependency.
- No LLM-controlled SQL, paths, file writes, shell commands, scheduler state,
  policy decisions, or rollback.
- No raw secrets or private user facts in SkillIR, `SKILL.md`, support files,
  probes, embeddings, or logs.
- Core infrastructure is not autonomously self-rewritten in v1.
