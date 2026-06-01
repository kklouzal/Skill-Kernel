# SkillKernel — Ultimate Final Coherence-Closed Implementation Handoff

**Version:** v16 final implementation handoff — coherence-closed consolidation of all prior research, topology, context, model-access, governance, security, storage, evaluation, and implementation decisions
**Date:** 2026-06-01
**Status:** final implementation handoff for development decomposition; pre-implementation conceptual design closed
**Project:** SkillKernel, an OpenClaw plugin + autonomous sidecar container for evidence-driven skill creation, improvement, composition, decomposition, curation, AI-facing context compilation, operator-configurable LLM/embedding access, runtime skill-context control, token-budget governance, and reversible skill-library governance.
**Final architecture:** one OpenClaw plugin, one Python sidecar, one Postgres database, one `autoskill` schema, pgvector, logical skill ownership by `skill_id`, canonical SkillIR as source of truth, deterministic context compiler/renderers that emit token-budgeted OpenClaw `SKILL.md`, SkillIR effect signatures, diagnostic-momentum improvement store, trace-spine observability, operator-configurable text-model access profile, operator-configurable embedding access profile, model/embedding profile qualification gates, SkillGraphIR for composed/decomposed workflow topology, SLSA-style artifact provenance manifests, no direct cost-tracker/analyzer, no per-operation model-routing matrix in v1, no per-skill databases, no per-skill schemas in v1, no OpenClaw Cron dependency, no Skill Workshop dependency.

---

## 0. Final implementation decision

Build **SkillKernel** as an autonomous skill operating system for OpenClaw. The implementation may keep `autoskill` as the internal database/schema namespace, but the project-level concept is SkillKernel.

The system continuously captures OpenClaw usage, extracts durable procedural evidence, converts repeated workflows/failures/corrections into evaluated skills, improves SkillKernel-owned skills from grounded usage data, compiles skill text into compact AI-facing runtime interfaces, controls which skills are visible or emphasized, archives low-value skills, promotes archived skills when demand recurs, merges duplicates, detects drift, and rolls back degraded changes.

The final system is autonomous by default but not uncontrolled. Human approval is not part of the normal maintenance loop. Control comes from deterministic policy, redaction, taint tracking, scanner gates, evaluator gates, regression budgets, skill-context budgets, audit trails, canarying, rollback, quarantine, and freeze semantics.

The end-to-end loop is:

```text
OpenClaw event
→ plugin hook capture
→ redaction + tainting
→ local spool or sidecar ingest
→ event normalization
→ immutable evidence extraction
→ governed memory derivation
→ active/archived skill matching
→ context-loadability classification
→ runtime skill-context calibration
→ action selection:
     no-op | create | improve | compose | decompose | compile | repair | merge | archive | promote | rollback | freeze
→ structured SkillIR change plan
→ SkillIR validation + static + semantic + capability scan
→ target + regression + adversarial evaluation
→ deterministic context compile + token-budget gate + staged file write
→ atomic activation/archive/promotion
→ canary observation
→ keep | repair again | roll back | freeze
→ utility, attribution, memory, retrieval, drift, and audit updates
```

The simplified model-access decision closes the model-routing design: SkillKernel has one configured text LLM profile and one configured embedding profile. It supports either OpenClaw-routed calls or direct OpenAI-compatible `/v1` calls. It does not implement a direct dollar-cost tracker/analyzer or a per-operation model-routing matrix in v1.

The final architecture is:

```text
OpenClaw runtime
  └─ SkillKernel plugin, TypeScript
       ├─ registers in-process OpenClaw hooks
       ├─ captures typed event envelopes
       ├─ redacts and taints before persistence or forwarding
       ├─ spools locally when the sidecar is unavailable
       ├─ forwards batches to localhost sidecar
       ├─ exposes status/control/diagnostic commands
       ├─ optionally contributes a small runtime skill-context hint from sidecar cache
       ├─ verifies active/archive roots
       └─ never runs slow LLM analysis, schedules maintenance, or writes arbitrary files

SkillKernel sidecar, Python
  ├─ authenticated ingest/control API
  ├─ durable Postgres-backed scheduler
  ├─ durable Postgres-backed job queue with leases and idempotency
  ├─ event normalizer and evidence extractor
  ├─ governed memory builder
  ├─ hybrid retrieval engine: lexical + vector + metadata + graph + exact rerank
  ├─ runtime skill-context broker: planner + renderer + shadowing control
  ├─ context compiler and token budget governor for every context-loadable artifact
  ├─ opportunity miner and duplicate matcher
  ├─ active/archived skill matcher and promotion engine
  ├─ skill creator, improver, composer, decomposer, compiler, merger, archiver, promoter, rollbacker
  ├─ contract/drift monitor
  ├─ outcome attribution and credit ledger
  ├─ diagnostic momentum store for recurring improvement evidence
  ├─ trace-spine correlation for jobs, events, model calls, evaluations, and mutations
  ├─ static, semantic, and capability scanner
  ├─ regression-aware evaluator and probe-bank manager
  ├─ deterministic path-contained filesystem writer
  ├─ canary monitor and freeze engine
  └─ observability, retention, audit, and policy enforcement

Postgres + pgvector
  └─ one database, one autoskill schema
       ├─ append-only event, evidence, and audit records
       ├─ derived memory clusters and memory links
       ├─ skills, versions, SkillIR revisions, compiled files, manifests, contracts, capabilities
       ├─ skill components, dependency edges, probes, evaluations, failures
       ├─ retrieval/context construction logs
       ├─ context artifact classifications, token ledgers, compression trials, semantic-equivalence results
       ├─ usage, attribution, corrections, outcomes, and utility rollups
       ├─ diagnostic momentum records and trace spans/links
       ├─ active/archive lifecycle state
       ├─ schedules, jobs, attempts, leases, and idempotency keys
       ├─ embeddings for events, evidence, memories, skills, probes, candidates
       ├─ lexical search vectors and metadata filters
       └─ scanner findings, policy decisions, canary results, rollback records
```

---

## 1. Final changes from the final research pass

The prior architecture was sound. The final research pass does not require a top-level component change. It does require one important internal inversion and several hardening refinements. These are integrated into this v16 document.

| Area | Final change | Implementation consequence |
|---|---|---|
| Source of truth | Add **canonical SkillIR** as the internal source of truth. | `SKILL.md` is no longer the internal canonical representation. It is a generated OpenClaw runtime artifact. All creation, improvement, curation, drift, retrieval, evaluation, and rollback operate over SkillIR revisions. |
| Skill compiler | Add deterministic **SkillIR → OpenClaw renderer** and optional renderers for broker hints, probes, manifests, and support-file manifests. | LLMs may propose SkillIR changes. Deterministic code validates, normalizes, scans, renders, token-budgets, hashes, stages, and rolls back outputs. |
| Skill text | Use **typed contracts and pseudocode-like runtime interfaces**. | Runtime instructions use fixed fields: `WHEN`, `INPUTS`, `PRECONDITIONS`, `DO`, `OUTPUTS`, `EFFECTS`, `TOOL TEMPLATES`, `VERIFY`, `FAIL`, `DO NOT USE WHEN`, and `NEVER`. Free-form prose is discouraged. |
| Runtime controls | Add **guard-template support**, not arbitrary generated programs. | Skills may select from deterministic preapproved runtime guard templates such as preflight check, verify-only check, capability warning, sibling-disambiguation hint, or drift-block. LLMs cannot write executable guard logic. |
| Retrieval | Upgrade the broker into **hybrid retrieval + graph expansion + context compilation**. | Retrieve candidate skills, expand prerequisite/conflict/supersession/shadow edges, hydrate the minimal useful subunits, render a set-aware context under budget, and track shadowing outcomes. |
| Skill creation | Require **contrastive and intervention evidence**. | New skills are accepted only when success/failure contrasts and with/without-skill probes show net benefit inside regression limits. |
| Skill improvement | Keep **evidence-gated, regression-aware updates**. | LLM self-feedback alone cannot mutate a skill. Patches need grounded evidence, target probes, regression probes, shadowing checks, scanner pass, and canary pass. |
| Memory | Add **memory-contract and poisoning defenses**. | Long-term evidence/memory is typed, provenance-scored, taint-aware, TTL-governed, and declassified only through verifier-backed transformations. External imperatives never become runtime instructions directly. |
| Security | Strengthen **skill supply-chain scanning**. | Ban hidden comments, invisible Unicode, bidi controls, dynamic fetch-exec patterns, secret exfiltration patterns, unexpected shell/network access, and LLM-controlled paths. Treat every generated artifact as untrusted until scanned and hashed. |
| Schemas | Keep **one `autoskill` schema in v1**. | Per-skill schemas are acceptable in theory, but they add dynamic DDL, migration, index, and permission complexity without improving global retrieval, curation, attribution, or promotion. Use logical `skill_id` ownership and partitioning/indexes when scale demands it. |

The final implementation posture is: **LLM as semantic proposal engine; deterministic infrastructure as authority; SkillIR as source of truth; `SKILL.md` as compiled OpenClaw-facing artifact; skill topology as the optimized product surface.**

---

### 1.1 Final last-pass additions before implementation

The last research pass does not change the top-level architecture. It adds implementation requirements that prevent long-run failure modes once the skill bank grows, once memories accumulate, and once skills are used under different agents, sandboxes, models, or tool profiles.

| Area | Final requirement | Why it matters |
|---|---|---|
| Runtime broker | Treat broker policy as a versioned, evaluated, rollbackable artifact. | Retrieval quality and context construction are independent failure modes. A static broker will decay as the skill bank grows. |
| Skill value | Measure marginal value with `skill-hidden`, `skill-visible`, and `no-skill` controls. | Usage count is not evidence of utility; a frequently loaded skill can be ignored, harmful, or shadowing a better skill. |
| Executor profiles | Evaluate and route skills against explicit executor profiles: model family, agent backend, sandbox, OS, available tools, binaries, API contracts, and permissions. | A skill that works under one harness can fail under another because tool semantics, context policy, or filesystem/shell behavior differs. |
| External skills | Inventory non-SkillKernel skills for collision, shadowing, and risk, but never mutate them autonomously. | The broker cannot avoid collisions if it only sees SkillKernel-owned skills. Autonomy must still respect ownership boundaries. |
| Memory | Add quarantine, delayed activation, provenance gates, and control-flow integrity auditing for memories that can affect retrieval, tool choice, or skill mutation. | Memory poisoning can steer future tool selection or skill edits without looking like a direct instruction. |
| Skill composition security | Scan not only individual skill files but also co-loaded skill sets and rendered broker context. | Individually benign skills can become harmful together through shared context, shadowing, or puppet-style redirection. |
| Runtime security | Add deterministic tool-call boundary enforcement hooks where available. | Model-level resistance is not enough for skill-file and tool-semantic attacks; runtime checks must constrain action boundaries. |
| Support artifacts | Allow helper scripts/templates/contracts only as deterministic, manifest-bound artifacts with declared capabilities, tests, and hashes. | Some procedures are better represented as small deterministic adapters than as prompt text, but executable artifacts need a tighter trust model. |
| Compiler verifier | Require coverage, binding, replacement, and risk checks before rendering `SKILL.md`. | Generated runtime text must cover required SkillIR fields, bind to evidence/contracts, avoid vague replacements, and preserve security boundaries. |
| Batch consolidation | Periodically run holistic batch consolidation across recent candidates, not only incremental per-event updates. | Trace-level work shows that transferable skills often require cross-episode comparison and conflict resolution. |
| Dynamic probes | Generate artifact-grounded probes from real failures, contracts, and drift events, then retire stale probes. | Static tests miss environment drift and overfit; probes must follow the actual operating surface. |
| Per-skill schemas | Keep the v1 decision: no per-skill databases and no per-skill schemas. | Per-skill schemas remain acceptable only as a later strict-isolation migration if measured constraints justify them. They do not improve v1’s core mechanisms. |

These additions create one final principle: **the skill library, the broker, the memory layer, and the evaluator are all versioned systems. Skills are not the only artifacts that can improve or regress.**

### 1.2 Last-push closure additions

The final research pass found no reason to change the top-level architecture. It did expose several implementation details that must be explicit before development starts. These are now part of the handoff and should be treated as first-release requirements, not optional polish.

| Area | Final closure requirement | Implementation consequence |
|---|---|---|
| Evolution transaction | Every autonomous mutation is a single **evolution transaction** spanning DB rows, SkillIR revision, compiled files, manifests, embeddings, retrieval caches, broker cache invalidation, probe additions, lifecycle state, and audit entries. | Rollback must restore the whole effective state, not only the filesystem artifact. No orphan embeddings, stale broker hints, active compiled text, or unrevoked derived memories may survive a rollback. |
| Ephemeral trial workspace | Candidate skill versions, broker-policy versions, and support artifacts are evaluated in an isolated trial workspace/profile before activation. | Evaluation cannot mutate the real active skill root, scheduler state, production embeddings, or production memory. Candidate artifacts are promoted only after scanner, trial replay, regression probes, and activation checks pass. |
| Action attribution gate | Risky tool calls and state mutations influenced by skills, memories, broker context, or retrieved artifacts require deterministic attribution logging and, where feasible, counterfactual/attenuated replay. | A skill/memory/broker hint that materially causes an action unsupported by the user goal is marked harmful, triggers rollback/freeze, and becomes negative evidence. |
| Body-aware routing | Retrieval and reranking must have access to the full SkillIR, compiled runtime text, support-file manifests, and significant non-secret support-file content. | Names and descriptions are insufficient routing signals. The model-facing runtime context remains compact, but the broker/reranker must index and inspect the full body-level skill representation. |
| No-skill as policy action | The broker must be able to select `no_skill`, `defer_skill`, or `skill_hidden` explicitly. | Loading a skill is not always beneficial. The system must measure when not loading a skill improves outcome, latency, safety, or token cost. |
| Evidence maturity ladder | Evidence gets a maturity state: `observed`, `recurring`, `contrastive`, `intervention_validated`, `regression_validated`, `canaried`, `production_verified`, or `revoked`. | Recurrence alone can propose a candidate; intervention/regression maturity is required for activation; production/canary maturity is required for broad applicability and high active priority. |
| Harmful-capability classifier | Generated and external skills are classified for harmful capability, dual-use risk, unsafe implicit intent, sensitive-data access, credential exposure, and policy-override behavior. | A skill that improves task success but creates harmful capability amplification is quarantined or restricted by capability policy. |
| Core infrastructure immutability | SkillKernel may mutate SkillKernel-owned skills and support artifacts. It must not autonomously rewrite the plugin, sidecar, migrations, scheduler, scanner, evaluator, compiler, or policy engine in v1. | Infrastructure improvement evidence can be logged as operator-review backlog only. Self-modification of the control plane is out of scope for v1. |
| Derived-data revocation | Retention, deletion, rollback, and quarantine must propagate to derived artifacts: memories, embeddings, evidence links, skill versions, broker logs, compiled files, and cached context hints. | Privacy and rollback are graph operations, not row-level deletes. The system must track provenance edges strongly enough to revoke downstream artifacts. |
| Secret reference discipline | Skills may refer to capability names or environment contract keys, but never raw secrets, credentials, tokens, personal identifiers, or private user facts. | Redaction happens before storage and embedding; scanner blocks secret-like material in SkillIR, `SKILL.md`, support files, probes, and logs. |
| Final closure criterion | Any future proposed design change must identify a concrete failure mode not already covered by redaction, provenance, evidence maturity, transactionality, scanner, evaluator, broker, rollback, canary, or freeze. | As of this pass, the document is ready for implementation decomposition. Further iteration should happen as implementation issues or production telemetry, not pre-implementation conceptual expansion. |

This creates the final principle for development: **autonomous mutation is allowed only as a rollback-complete transaction whose causal inputs, evidence maturity, compiled artifacts, runtime exposure, and downstream derived state are all versioned and auditable.**


---


### 1.3 Topology-operations closure additions

The final user requirement reframes the system correctly: the project is not merely an automatic skill writer. It is an **evidence-driven skill-library topology optimizer**. The four primary autonomous operations are now first-class implementation primitives:

```text
create      = add a missing useful skill
improve     = modify an existing useful skill
compose     = build a higher-order workflow skill from repeatedly co-used smaller skills
decompose   = split a broad/clunky skill into sharper reusable skills
```

This is now a non-negotiable product requirement. Creation and improvement operate on individual skill nodes. Composition and decomposition operate on the topology of the skill graph. Curation, archiving, promotion, merge, split, recompile, repair, freeze, and rollback remain supporting operations, but they are not substitutes for the four core topology operations.

| Topology addition | Implementation consequence |
|---|---|
| SkillKernel optimizes topology, not only files. | The planner must reason over skill nodes, components, co-usage edges, sequence edges, supersession edges, component relationships, and active-bank budget as one graph. |
| Compose/decompose are first-class, not cleanup. | Add dedicated candidates, transactions, evidence thresholds, probes, DDL, broker behavior, metrics, and rollback semantics. |
| Rich evidence collection is part of the product, not telemetry afterthought. | The event pipeline must record retrieval, injection, use, ignore, co-use, order, error, correction, cost, outcome, and counterfactual/control data because topology decisions require causal-ish evidence. |
| Skill granularity is adaptive. | A stable system must support atomic, functional, planning, and composed workflow skills simultaneously rather than forcing every skill to the same size. |
| Compose is not merge. | Merge removes duplicate or near-duplicate skills. Compose creates a new higher-order orchestration skill while possibly retaining component skills. |
| Decompose is not merely shortening. | Decompose creates successor skills from separable usage clusters and usually supersedes/archives the original broad skill after validation. |
| Operation choice is an evaluated intervention. | For every candidate, compare against no-op, no-skill, current skill, nearest active skill, nearest archived skill, composed candidate, decomposed candidates, and broker-only description repair where applicable. |
| Topology operations affect runtime routing. | The broker must understand `component_of`, `composes_with`, `composed_by`, `decomposes_to`, `specializes`, `generalizes`, `supersedes`, `shadows`, `requires`, and `conflicts_with`. |
| Active-bank size and shape are product variables. | Bank-level optimization must decide when fewer larger workflow skills outperform many small skills, and when smaller specialized skills outperform broad workflow skills. |

The final conceptual model is:

```text
robust data capture
→ evidence extraction and maturity scoring
→ skill/component/body/graph retrieval
→ topology candidate generation
→ operation selection: create | improve | compose | decompose | no-op | supporting action
→ intervention and regression evaluation
→ transactional SkillIR mutation
→ deterministic compile/write
→ broker-aware activation
→ canary and attribution
→ keep | repair | roll back | freeze | archive
```

This topology-operations closure does not introduce a new service or database. It tightens the existing architecture around the four topology operations and adds the missing tables, policies, and acceptance gates needed to implement them deliberately.


---

### 1.4 Context-management closure additions

The final missing requirement is not a new external service. It is a hard invariant that changes how every skill artifact is authored, evaluated, stored, routed, and activated:

```text
Anything that can enter the running agent's context is a compiled AI-facing runtime artifact.
It is not documentation, not a transcript summary, and not human-oriented prose.
```

This requirement is now first-class because context is the scarcest runtime resource in the system. A skill that improves task success but consumes excessive context, triggers false-positive loading, shadows a narrower skill, distracts the model, or injects verbose rationale is not a successful skill. Runtime text must be scrutinized token by token.

| Context-management addition | Implementation consequence |
|---|---|
| Context-loadable artifacts are compiled artifacts. | `SKILL.md`, skill frontmatter descriptions, broker hints, support-file excerpts, tool templates, verification instructions, failure instructions, and component references must pass the same token, semantic-density, safety, and regression gates. |
| SkillIR/Postgres is the full-fidelity source of truth. | Evidence, rationale, long examples, raw traces, failures, alternatives, and improvement history remain in Postgres/SkillIR. They do not leak into runtime prompt text unless a compiler proves they are operationally necessary. |
| `SKILL.md` is an executable prompt interface, not documentation. | Use terse typed sections such as `WHEN`, `INPUTS`, `DO`, `OUTPUTS`, `EFFECTS`, `VERIFY`, `FAIL`, `NEVER`; ban explanations, historical notes, implementation commentary, and human-readable onboarding prose unless measured useful. |
| Every context-visible word must justify itself. | The compiler computes marginal utility per token, token delta per version, false-positive load cost, ignored-skill token waste, shadowing cost, and composed/decomposed token tradeoffs. |
| Progressive disclosure is allowed but governed. | Support files are not context-free; classify every support artifact as `never_loaded`, `agent_may_read`, `broker_excerpt_only`, `script_only`, `probe_only`, or `operator_only`. Any `agent_may_read` artifact must pass compression and scanner gates. |
| Compression is semantic compilation, not summarization. | LLMs may propose compact wording and detect semantic redundancy. Deterministic code enforces format, budget, forbidden text, required fields, hashing, scanning, and acceptance. |
| Context budget affects topology operations. | Composition is accepted only if the composed workflow beats component-only alternatives after token cost. Decomposition is favored when a broad skill causes partial-use loading, false positives, or high unused-token overhead. |
| Context regression is a failure. | A new skill version can be rejected solely for worse token efficiency, increased shadowing, lower retrieval precision, or reduced semantic equivalence, even when target probes improve. |

The runtime design is therefore:

```text
SkillIR / Postgres / evidence store = full-fidelity source of truth
OpenClaw SKILL.md / broker hint / context excerpt = minimized compiled projection
```

Development rule:

```text
No context-loadable artifact ships unless it passes token-budget, semantic-equivalence,
retrieval/shadowing, safety, regression, and marginal-value gates.
```


This closes the remaining conceptual gap. SkillKernel is not only a skill lifecycle system and topology optimizer; it is a context-budget governor for autonomous skill libraries.


---

### 1.5 Prior v14 research-closure additions retained through v16

The final online research pass found no top-level architecture reversal. It did identify three implementation requirements that should be explicit before development starts because they reduce long-run failure modes in autonomous skill evolution.

| Final addition | Requirement | Why it matters |
|---|---|---|
| **SkillIR effect signatures** | Every SkillIR revision and graph edge must expose compact typed `OUTPUTS`, `EFFECTS`, `STATE DELTA`, `SIDE EFFECTS`, `TERMINATION`, and `IDEMPOTENCY` fields where applicable. | Graph-composition research shows that reliable composition depends on precondition-effect edges, not only semantic similarity. The broker and evaluator need to know what a skill changes, produces, requires, and terminates. |
| **Diagnostic momentum store** | Repeated failures, corrections, drift events, and probe losses must accumulate into a persistent diagnostic-momentum record before skill patches are accepted. One-off incidents may create probes or evidence, but should not normally rewrite a production skill. | Skill-improvement research indicates that recurring diagnostic patterns and contrastive losses stabilize skill updates better than heuristic reflection from a single trajectory. |
| **Trace spine** | Every captured event, sidecar job, model call, embedding call, retrieval decision, broker decision, evaluator run, file mutation, rollback, and high-risk tool-action attribution must carry `trace_id`, `span_id`, optional `parent_span_id`, and safe attributes. | Distributed tracing makes multi-service autonomous behavior debuggable and causally inspectable. It also supports rollback-complete evolution transactions and action-attribution gates. |

These are not new services. They are data-plane and control-plane refinements inside the existing plugin, sidecar, and Postgres architecture.

#### 1.5.1 SkillIR effect signatures

SkillIR must not represent a skill only as name, description, and prose steps. Each version requires an operational contract that supports retrieval, composition, decomposition, evaluation, and runtime guarding.

Minimum effect contract fields:

```json
{
  "inputs": [],
  "preconditions": [],
  "outputs": [],
  "effects": [],
  "state_delta": [],
  "side_effects": [],
  "termination": [],
  "idempotency": "idempotent | retry_safe | not_retry_safe | unknown",
  "unsafe_when": [],
  "verification": [],
  "failure_modes": []
}
```

Renderer rule: `OUTPUTS` and `EFFECTS` appear in `SKILL.md` only when they improve execution, routing, or verification enough to justify their tokens. They always remain in SkillIR for indexing, evaluation, and graph reasoning.

Composition rule: a composed skill is valid only when component effects can be ordered without unresolved precondition gaps, conflicting state deltas, hidden unsafe side effects, or ambiguous termination.

Decomposition rule: successor skills must preserve the effect coverage of the original skill for the validated usage clusters they claim to replace. Uncovered effects become either sibling skills, explicit non-goals, or rollback blockers.

#### 1.5.2 Diagnostic momentum store

Skill improvement must be governed by accumulated evidence, not episodic reflection. The sidecar stores recurring diagnostic patterns as an optimization memory overlay.

Diagnostic momentum inputs:

```text
probe failures
user corrections
tool errors
schema/API/package drift
repeated fallback paths
skill-hidden vs skill-visible regressions
context-compile semantic-loss failures
retrieval shadowing events
ignored skill loads
false-positive loads
successful repairs that recur across sessions
```

A diagnostic momentum record contains:

```text
skill_id
skill_version_id
executor_profile_id
issue_signature_hash
diagnostic_kind
root_cause_hypothesis
suggested_change_direction
evidence_count
contrastive_support_count
counterevidence_count
last_seen_at
momentum_score
risk_score
status
```

Patch rule: a production skill patch may be proposed by an LLM, but acceptance requires deterministic evidence thresholds over diagnostic momentum plus normal scanner, semantic-equivalence, regression, shadowing, context-budget, and canary gates.

One-off rule: a single severe event can trigger freeze/quarantine/rollback immediately, but it should not create a normal forward patch without corroborating evidence or targeted probes.

#### 1.5.3 Trace spine and observability discipline

The plugin and sidecar must propagate a trace spine through the whole system. This is not a user-facing cost tracker and not raw transcript logging. It is a minimal correlation substrate for debugging, attribution, rollback, and evaluation.

Trace requirements:

```text
trace_id: one logical user/session/job/evolution flow
span_id: one operation within that flow
parent_span_id: causal parent when present
span_links: batched or cross-trace causal links
operation_name: stable internal operation enum
status: ok | error | timeout | denied | quarantined | rolled_back
safe_attributes: redacted structured metadata only
object_refs: event/evidence/job/skill/version/probe/evolution IDs
```

Rules:

```text
Do not export raw conversation text as trace attributes.
Do not export secrets, file contents, or prompt bodies as trace attributes.
Do not require external observability infrastructure.
Store trace rows in Postgres by default.
Allow optional OpenTelemetry export with content-safe attributes only.
Use trace links for batch jobs that consume many events.
Use trace links for evolution transactions caused by multiple evidence clusters.
Use trace links for rollback/revocation chains.
```

This trace spine strengthens, but does not replace, the audit hash chain. Audit proves what changed. Trace shows why the system changed it and which operations contributed.

#### 1.5.4 Additional DDL for retained v14 additions

```sql
CREATE TABLE autoskill.trace_spans (
  trace_id uuid NOT NULL,
  span_id uuid PRIMARY KEY,
  parent_span_id uuid NULL,
  workspace_id uuid NOT NULL,
  operation_name text NOT NULL,
  operation_kind text NOT NULL CHECK (operation_kind IN (
    'plugin_capture','ingest','redaction','evidence','memory','retrieval','broker',
    'llm_call','embedding_call','scanner','evaluator','compiler','writer',
    'scheduler','job','evolution','rollback','archive','promotion','tool_attribution'
  )),
  started_at timestamptz NOT NULL DEFAULT now(),
  ended_at timestamptz NULL,
  status text NOT NULL CHECK (status IN ('running','ok','error','timeout','denied','quarantined','rolled_back')),
  safe_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  object_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX trace_spans_trace_idx
  ON autoskill.trace_spans (workspace_id, trace_id, started_at);

CREATE TABLE autoskill.trace_span_links (
  from_span_id uuid NOT NULL REFERENCES autoskill.trace_spans(span_id),
  to_span_id uuid NOT NULL REFERENCES autoskill.trace_spans(span_id),
  link_type text NOT NULL CHECK (link_type IN ('batch_input','causal','rollback','revocation','trial','counterfactual')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (from_span_id, to_span_id, link_type)
);

CREATE TABLE autoskill.diagnostic_momentum (
  diagnostic_momentum_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid NULL REFERENCES autoskill.skill_versions(skill_version_id),
  executor_profile_id uuid NULL REFERENCES autoskill.executor_profiles(executor_profile_id),
  issue_signature_hash text NOT NULL,
  diagnostic_kind text NOT NULL CHECK (diagnostic_kind IN (
    'tool_failure','user_correction','probe_failure','drift','retrieval_shadowing',
    'false_positive_load','ignored_load','semantic_loss','context_overhead',
    'composition_gap','decomposition_gap','security_finding','other'
  )),
  root_cause_hypothesis text NOT NULL,
  suggested_change_direction text NOT NULL,
  evidence_count integer NOT NULL DEFAULT 0,
  contrastive_support_count integer NOT NULL DEFAULT 0,
  counterevidence_count integer NOT NULL DEFAULT 0,
  momentum_score double precision NOT NULL DEFAULT 0,
  risk_score double precision NOT NULL DEFAULT 0,
  status text NOT NULL CHECK (status IN ('accumulating','ready_for_probe','ready_for_patch','patched','rejected','revoked')),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, skill_id, executor_profile_id, issue_signature_hash, diagnostic_kind)
);

CREATE INDEX diagnostic_momentum_ready_idx
  ON autoskill.diagnostic_momentum (workspace_id, status, momentum_score DESC, last_seen_at DESC);
```



---

### 1.6 Final v16 landscape-assimilation closure additions

A separate landscape pass was performed across direct projects, narrow research slices, benchmark systems, security audits, validation tools, open Agent Skills standards, and production ecosystem guidance. The pass did not invalidate the architecture. It strengthened the implementation stance: SkillKernel must be a governed skill operating system, not a generator that occasionally writes `SKILL.md`.

The retained landscape additions are first-release requirements unless explicitly marked as future-facing telemetry.

| Landscape-derived requirement | Adopted design rule | Implementation consequence |
|---|---|---|
| Batch evidence before durable mutation | Persistent skill creation/improvement normally requires clustered evidence windows, not one isolated trajectory. | Single events may create `ephemeral_candidate`, probes, negative evidence, rollback, or freeze. They should not normally produce a production `SKILL.md` unless the user gave explicit instruction or the event is severe enough to justify safety rollback. |
| Ephemeral candidate lane | Add candidate state `ephemeral_candidate` before normal persisted activation. | Temporary skill-like hints may be tested in trial workspaces and broker experiments without entering active OpenClaw skill roots. Promotion requires evidence maturity, scanner pass, regression pass, context-budget pass, and silent-bypass audit. |
| Silent-bypass audit | A skill receives positive credit only when it was retrieved, rendered or loaded, visible to the agent, temporally relevant, and causally plausible. | Outcome attribution must distinguish helped, hurt, ignored, missing, bypassed, environment-derived, agent-exploration-derived, and inconclusive. Presence in the candidate set is not usage. |
| Runtime immutability lock | Active skill packages are immutable for any session that may use them. | All changes stage a new version in a trial root, compile and hash artifacts, then activate by atomic pointer/symlink/snapshot swap at a safe boundary. Never rewrite an active `SKILL.md` in place mid-session. |
| External benchmark and validator adapter seam | Evaluator output must be adapter-friendly. | Support SkillsBench/SWE-Skills-Bench/OpenSkillEval/skillgrade/skill-validator-style adapters later without changing core schema. V1 need not bundle those tools, but evaluator records must support deterministic verifiers, gym-style tasks, pinned repos, and external grader artifacts. |
| Genericity and bloat rejection | Reject generic, broad, vague, human-prose-heavy, or redundant skills even if they look polished. | The scanner/compiler must flag weak triggers, marketing language, non-actionable prose, overbroad descriptions, body bloat, repeated constraints, unbounded examples, and token-heavy support files. |
| Co-evolved verifier lane | Skill generation/improvement and verifier/probe generation are separate roles. | A surrogate verifier can propose dense diagnostic checks, but it cannot alone approve a skill. Its probes must themselves pass scanner, coverage, risk, and known-case sanity gates. |
| Granularity labels | SkillIR must record skill granularity: `atomic`, `functional`, `workflow`, `planning`, `meta`, or `external`. | Compose/decompose decisions become explicit level transitions. Broad workflow skills must not shadow narrow atomic/functional skills unless intervention tests show net benefit. |
| Scope labels | SkillIR must record scope: `workspace_local`, `project_local`, `domain`, `global_general`, `external_readonly`, or `archived`. | Prevents a broad generalized skill from polluting narrow tasks and supports future opt-in federation without leaking private evidence. |
| Graph-aware retrieval expansion | Hybrid retrieval seeds candidates, then graph expansion adds required prerequisites, conflicts, supersessions, sibling alternatives, and composed/decomposed relationships under context budget. | The broker should support dependency expansion, reverse prerequisite traversal, co-use expansion, exact rerank, and context-budgeted hydration. Semantic similarity alone is insufficient. |
| SkillGraphIR orchestration | Composition produces graph structure, not pasted prose. | Composed skills need ordered components, precondition/effect links, verifier nodes, fallback nodes, and local repair options. Decomposition must preserve effect coverage of validated usage clusters. |
| Meta-evolution telemetry | Collect data for future improvement of the evolver policy itself, but do not self-rewrite control-plane code in v1. | Log threshold decisions, rejected candidates, broker alternatives, probe usefulness, rollback causes, and delayed outcomes so later versions can learn curation/evolution policies. V1 may only mutate versioned policy artifacts through the same gates, never scheduler/scanner/evaluator/compiler code. |
| Collective-evolution seam | Multi-user or cross-workspace skill evolution is future-facing and must be opt-in. | Schema should retain `workspace_id`, `tenant_id`, provenance, privacy class, and export/import fields. No cross-user evidence sharing or global skill update occurs by default. |
| Multi-file package discipline | Multi-file skills are allowed only when they reduce token burden or improve deterministic reliability. | Support files, scripts, templates, and fixtures require loadability class, capability manifest, hashes, tests, path containment, and no hidden/dynamic remote behavior. |
| Progressive disclosure discipline | Support files are not a loophole around context budgets. | Anything the agent may read is context-loadable and must be compressed/scanned. `script_only`, `probe_only`, and `operator_only` files are not rendered into the agent context. |
| Executor-profile portability | Skill value is executor-specific. | Evaluation records include model, agent harness, sandbox, OS, tools, binaries, package versions, permissions, token budget, and OpenClaw version. A skill can be active for one executor profile and quarantined for another. |
| Open-standard compatibility without dependency lock-in | Emit normal OpenClaw/Agent Skills artifacts, but keep SkillIR as canonical. | SkillKernel can interoperate with `SKILL.md` ecosystems, GitHub skill tooling, and validators while avoiding dependence on third-party project internals. |
| Security by composition | Scan individual artifacts, bundles, broker-rendered context, and composed skill graphs. | A set of individually acceptable skills can become unsafe when co-loaded. Bundle scans must check conflicting instructions, exfiltration chains, unsafe delegated actions, and hidden capability amplification. |

#### 1.6.1 State-machine additions

Add or explicitly preserve these lifecycle states:

```text
observed_pattern
candidate_cluster
ephemeral_candidate
trial_candidate
validated_candidate
active
canary_active
archived
frozen
revoked
superseded
external_readonly
```

`ephemeral_candidate` is not visible to OpenClaw as a normal skill. It exists for temporary broker trials, probe generation, and evidence gathering. Promotion from `ephemeral_candidate` to `trial_candidate` requires clustered evidence or explicit user/operator intent. Promotion to `active` requires normal maturity, scanner, evaluator, context, provenance, and rollback gates.

#### 1.6.2 Topology labels to add to SkillIR

SkillIR should include:

```json
{
  "granularity": "atomic | functional | workflow | planning | meta | external",
  "scope": "workspace_local | project_local | domain | global_general | external_readonly | archived",
  "topology_role": "standalone | component | composition | decomposition_successor | superseded_parent | sibling | prerequisite | alternative",
  "component_policy": "retain_components | prefer_composed | prefer_components | broker_decides",
  "runtime_visibility_policy": "metadata_only | broker_hint_only | full_skill_allowed | hidden_by_default | no_runtime_visibility"
}
```

These labels prevent two common long-run failures: black-hole general skills that match everything, and excessive atomization where the broker must load many tiny skills to perform one recurring workflow.

#### 1.6.3 Verifier/probe co-evolution without verifier capture

The skill generator and verifier/probe generator may both use the configured text LLM profile, but they must run under different prompts, different structured-output schemas, and different evidence access modes. The verifier lane should see enough evidence to generate useful tests but not enough to simply mirror the candidate skill text as truth.

Rules:

- a candidate skill cannot be accepted by probes generated only from the same candidate text;
- verifier-generated probes are treated as untrusted artifacts until scanned;
- probes must cover target behavior, regression cases, sibling-shadow cases, no-skill baselines, and context-budget failure modes;
- failed or flaky probes are themselves evidence for evaluator repair, not automatic rejection of the skill;
- a verifier that repeatedly produces low-signal probes is downranked for future generation.

#### 1.6.4 Runtime immutability and activation semantics

Active artifacts are immutable within a session boundary. A mutation creates:

```text
SkillIR revision
compiled runtime artifacts
support artifacts
manifest
embedding rows
probe rows
broker cache invalidation record
activation candidate pointer
```

Only after gates pass does the sidecar perform an atomic activation. OpenClaw-visible active roots should contain either versioned directories or a deterministic pointer/symlink/snapshot layout such that rollback is an atomic pointer move rather than an in-place file edit.

#### 1.6.5 Benchmark/validator adapter interface

The evaluator must expose a stable adapter interface:

```text
prepare_fixture()
render_candidate_context()
run_baseline_no_skill()
run_baseline_current_skill()
run_candidate_skill()
run_component_only()
run_composed_or_decomposed()
collect_artifacts()
verify_deterministically()
score_outcome()
record_trace()
```

This supports future integration with external benchmark styles without coupling v1 to any one project. Adapters must be sandboxed, versioned, and deterministic where possible. LLM-as-judge may assist diagnosis but cannot be the sole acceptance authority for production activation.

#### 1.6.6 Collective learning boundary

SkillClaw-style collective evolution is directionally relevant, but v1 should not default to shared cross-user skill updates. SkillKernel should store enough provenance for future opt-in federation:

```text
tenant_id
workspace_id
privacy_class
evidence_origin
export_allowed
redaction_version
license/source class
skill ownership
external import status
```

Any future shared-skill federation must require explicit opt-in, privacy-preserving evidence export, source/license tracking, harmful-capability scanning, and compatibility gates. The v1 default remains local/workspace-governed evolution.

#### 1.6.7 Final v16 design answer

After assimilating the broader landscape, there is no top-level architecture change. The final implementation should not add per-skill databases, per-skill schemas, OpenClaw Cron dependency, Skill Workshop dependency, direct cost tracking, or a per-operation model-routing matrix.

The only v16 changes are control-plane clarifications that make the existing architecture safer and more capable:

```text
batch before durable mutation
ephemeral candidate lane
silent-bypass audit
runtime immutability lock
external benchmark/validator adapter seam
genericity and bloat rejection
co-evolved verifier/probe lane
granularity/scope/topology labels
graph-aware retrieval expansion
future opt-in collective-learning seam
```

These changes preserve the core final architecture while closing practical failure modes found across the research and project landscape.

### 1.7 Final v16 coherence closure additions

This pass does not add a new subsystem. It removes ambiguity that accumulated during earlier iterations and makes the implementation document internally coherent. These edits are authoritative wherever older wording conflicts.

| Coherence area | Final v16 rule | Implementation consequence |
|---|---|---|
| Project name | The project is **SkillKernel**. `autoskill` remains only the internal schema/path namespace. | Code, docs, status output, manifests, and plugin UI should say SkillKernel unless referring to the internal `autoskill` schema/path or the external ECNU AutoSkill project. |
| LLM access | One active text LLM profile in v1. | No per-operation model matrix. Typed LLM purposes all use the configured active text profile and are allowed only if that profile passes qualification gates. |
| Embeddings | One active embedding profile in v1. | pgvector stores vectors; embedding generation is performed by the configured embedding route. Profile/dimension are part of the vector contract. |
| Cost | No direct dollar-cost tracker/analyzer. | Record invocation metadata and token counts when returned for audit/debugging, but do not calculate prices, optimize by price, or expose cost analytics. |
| Context | Runtime-loaded skill artifacts are compiled AI-facing prompt artifacts. | `SKILL.md`, broker hints, runtime snippets, and any loadable support excerpts must pass semantic-density, token-budget, scanner, equivalence, and regression gates. |
| Topology | Create, improve, compose, and decompose are first-class lifecycle operations. | Merge/deduplicate, archive, promote, repair, compile, rollback, and freeze are supporting operations. They do not replace composition/decomposition. |
| Source of truth | SkillIR and SkillGraphIR are canonical. | `SKILL.md` is generated output. The LLM proposes structured IR changes; deterministic code validates, renders, stages, hashes, activates, and rolls back. |
| Active artifacts | Active packages are immutable during sessions. | Mutations stage new versions and activate by atomic pointer/snapshot swap only after all gates pass. |
| External skills | External/non-SkillKernel skills are inventoried and considered for collision/shadowing but never mutated autonomously. | Import requires explicit operator action and full scan/provenance conversion. |
| Control plane | Plugin, sidecar, scheduler, migrations, scanner, evaluator, compiler, deterministic writer, and policy engine are not autonomously rewritten in v1. | Self-improvement is limited to SkillKernel-owned skill artifacts, broker policies, probes, manifests, support artifacts, lifecycle state, and derived memories under transaction/rollback controls. |

The final document should be read with this precedence order:

```text
v16 coherence closure
→ non-negotiable final decisions
→ OpenClaw compatibility constraints
→ autonomy policy
→ storage/retrieval/security/evaluation/compiler sections
→ research traceability
```

If an older phrase implies operation-level model routing, human-facing skill prose, direct cost analytics, per-skill databases/schemas in v1, OpenClaw Cron usage, Skill Workshop dependency, synchronous hook-path LLM calls, or direct LLM file mutation, that older implication is superseded by the v16 rules above.



## 2. Research synthesis translated into design requirements

This section is intentionally implementation-facing. It does not summarize papers for their own sake. It translates the literature into concrete engineering decisions.

### 2.1 Skills are procedural memory, not transcript memory

Modern skill work frames skills as reusable procedural capabilities: compact instructions, code, constraints, applicability conditions, termination criteria, and validation checks. That maps directly onto SkillKernel’s goal. The system must not store raw transcript snippets as `SKILL.md`. It must extract procedural invariants from traces, compile them into a stable runtime interface, and preserve raw/derived evidence separately.

**Requirement:** raw events, evidence, memories, skill components, and runtime skill text are distinct objects with distinct trust levels.

### 2.2 Lifelong learning needs controlled external memory

Voyager, Reflexion, ExpeL, Agent Workflow Memory, Memento-Skills, and related work show that frozen models can improve through externalized memory/skills without model weight updates. The recurring successful pattern is not “let the model remember everything”; it is “store reusable experience, retrieve it under constraints, and update it based on feedback.”

**Requirement:** SkillKernel is an external learning layer around OpenClaw. It improves behavior by controlling skills, memories, probes, context, and files, not by fine-tuning the model.

### 2.3 Self-generated skills are useful only with governance

SkillsBench and SkillLearnBench show that curated skills help, while self-generated skills can be unstable, task-dependent, or neutral. SkillLearnBench further reports that self-feedback alone can induce recursive drift.

**Requirement:** skill creation and improvement must be evidence-gated, externally grounded, and regression-aware. Self-reflection can propose hypotheses; it cannot be the only acceptance signal.

### 2.4 Skill update quality depends on lifecycle management

MUSE-Autoskill, SkillsVote, GRASP, Ratchet, SkillOps, SkillOS, SkillBrew, and related systems point to the same conclusion: the library manager matters as much as the skill author. Append-only accumulation creates redundancy, context pollution, and stale procedures.

**Requirement:** SkillKernel must own the full lifecycle: create, evaluate, register, use, attribute, refine, compile, merge, archive, promote, repair, and retire. Addition is only one of many actions.

### 2.5 Retrieval is not enough; context construction is a separate subsystem

SkillRet, Skill Retrieval Augmentation, Graph-of-Skills, More Skills/Worse Agents, and SkillsInjector all indicate that skill selection, dependency recovery, active budget, description rendering, and skill shadowing are separate bottlenecks. A high-similarity result can be wrong, insufficient, or harmful. A useful skill can be buried by sibling descriptions.

**Requirement:** SkillKernel needs a runtime skill-context broker. It should not expose a growing flat list and hope OpenClaw selects correctly. It should calibrate active visibility, retrieve dependency-complete bundles, render concise turn-specific hints, and detect shadowing.

### 2.6 Skill text should be compiled from canonical SkillIR

SkillSmith, Skill-as-Pseudocode, SkillCompiler/SkillIR-style work, and Formal Skill-style runtime contracts point in the same direction: free-form Markdown is too ambiguous to be the system of record. It is useful as the final model-facing artifact, but the manager needs a typed internal representation with explicit applicability, inputs, preconditions, operational steps, tool templates, verification, failure handling, boundaries, dependencies, risks, and environment contracts.

**Requirement:** `SKILL.md` is a compiled OpenClaw runtime interface, not the internal source of truth. The source of truth is versioned SkillIR. Runtime text uses stable sections: `WHEN`, `INPUTS`, `PRECONDITIONS`, `DO`, `OUTPUTS`, `EFFECTS`, `TOOL TEMPLATES`, `VERIFY`, `FAIL`, `DO NOT USE WHEN`, and `NEVER`.

### 2.7 Skill creation should use contrastive evidence

SkillGen-style approaches compare successful and failed trajectories to extract the behavior present in success but absent in failure. This is stronger than generic summarization because it grounds the skill in a causal-looking delta.

**Requirement:** candidate generation should cluster failures, cluster successes, retrieve nearest successful neighbors for failures, and synthesize corrections from local contrasts.

### 2.8 Skill drift is contract violation

Skill drift work shows that skills decay when APIs, packages, file formats, permissions, services, and environment assumptions change. Monitoring incidental values is noisy; monitoring role-bearing operational contracts is actionable.

**Requirement:** every skill version has extracted environment contracts. Drift checks target contracts and produce localized repair plans.

### 2.9 Memory and retrieval are attack surfaces

Memory poisoning, tool-selection poisoning, and sleeper-memory work show that long-term memory can carry delayed attacks. Skills can also be a persistence vector for prompt injection, exfiltration, or hidden directives.

**Requirement:** untrusted content is tainted at ingestion. Memory promotion and skill compilation require provenance, trust, and scanner gates. Skills are treated as untrusted inputs to the model unless they are SkillKernel-generated, scanned, versioned, and policy-approved.

### 2.10 Skills are software supply-chain artifacts

Large-scale security studies of agent skills report vulnerabilities across prompt injection, data exfiltration, privilege escalation, and supply-chain abuse. Hidden-comment injection shows that Markdown can conceal instructions from human reviewers while remaining visible to models.

**Requirement:** SkillKernel-generated artifacts require manifests, capability declarations, file hashes, hidden-content bans, static and semantic scans, deterministic writes, restricted helper scripts, and rollback.

### 2.11 pgvector is useful, but vector-only retrieval is insufficient

pgvector provides exact search, approximate search, HNSW/IVFFlat indexes, half precision, binary quantization, filtering, iterative scans, and hybrid search with PostgreSQL full-text search. But approximate vector indexes can miss filtered results, and semantic similarity does not guarantee functional sufficiency.

**Requirement:** use pgvector as a candidate generator. Final retrieval combines lexical search, vector search, metadata filters, graph expansion, exact reranking, calibration, and recall audits.

### 2.12 Skill context construction must be governed like skill writing

The broker should be handled as a first-class policy artifact with versions, metrics, canaries, rollback, and regression tests. It decides not only which skills are retrieved, but which are exposed, how many are exposed, how dependencies/conflicts are resolved, and how descriptions are rendered relative to siblings. A bad broker can make a good skill library perform badly.

**Requirement:** store `broker_policy_versions`, run offline replay against historical episodes, run canary policies on bounded traffic where possible, and roll back broker versions that increase ignored/harmful/shadowed-skill rates.

### 2.13 Marginal utility is stronger than usage telemetry

Skill usage telemetry is necessary but insufficient. A skill can be frequently loaded because its description is broad, because it shadows other skills, or because the broker keeps retrieving it. Utility must be estimated by comparing outcomes under controlled visibility states.

**Requirement:** maintain marginal-value trials for important skill versions: no-skill, old-skill, new-skill, skill-hidden, skill-visible, and sibling-bundle variants. Archive and promotion decisions use marginal value, not raw usage count alone.

### 2.14 Skills must be executor-profile-aware

OpenClaw can run through different agent backends, sandboxes, hosts, models, token budgets, tools, filesystem permissions, and binary availability. A skill validated in one executor profile may be unsafe or ineffective in another.

**Requirement:** every evaluation, activation, drift check, and runtime broker decision is scoped to an executor profile. Compatibility is explicit, not assumed.

### 2.15 External skills are part of the visible ecosystem

Even though SkillKernel only mutates SkillKernel-owned skills, OpenClaw may load workspace, project-agent, personal-agent, managed, bundled, extra-directory, or plugin-provided skills. Non-SkillKernel skills can collide with SkillKernel skills by name, description, semantics, or capability scope.

**Requirement:** inventory external skills, hash their visible artifacts, embed their descriptions for collision/shadow analysis, mark their ownership as external, and treat them as read-only unless an operator explicitly imports them into SkillKernel ownership.

### 2.16 Memory is control input, not passive storage

Memories, evidence summaries, and retrieval notes can steer future tool choice, skill choice, and skill mutation. They therefore need the same trust logic as skill files, even when they are not directly rendered into `SKILL.md`.

**Requirement:** quarantine newly derived memory by default when it contains imperative language, user-specific data, external instructions, tool-choice claims, security-sensitive claims, or low-provenance content. Promote only after deterministic and semantic checks. Log control-flow events whenever memory influences retrieval, mutation, or tool routing.

### 2.17 Individual skill scanning is insufficient

Per-file scanning misses cross-skill and audit-runtime gaps. Two individually safe skills can jointly produce unsafe context; a skill can pass review and later be modified; a mutable reference can change after approval; a broker-rendered bundle can change the meaning of a skill description.

**Requirement:** bind scanner verdicts to exact bytes/hashes, scan rendered skill bundles and broker hints, maintain co-load risk checks, and invalidate prior approvals if bytes, metadata, dependencies, or renderer version changes.

### 2.18 Deterministic micro-executors are allowed but constrained

Some reusable procedures are better represented as deterministic scripts, adapters, validators, or templates than as model instructions. This should be used sparingly because executable artifacts increase supply-chain risk.

**Requirement:** support artifacts require a manifest, declared capabilities, file hashes, explicit interpreter/runtime, unit tests, no dynamic fetch-exec, no secret access unless explicitly declared, and scanner/evaluator approval. The LLM proposes the artifact plan; deterministic code writes, scans, tests, and activates it.

### 2.19 Evolution must be transactional across artifacts

Self-evolving agent work reinforces that useful improvement loops are anchored to concrete production-failure evidence and promoted only after deterministic stage ordering, replay, health checks, and rollback. For SkillKernel, the mutated object is not only a skill file. A change can affect SkillIR, compiled Markdown, support artifacts, embeddings, retrieval scores, broker decisions, memories, probes, lifecycle state, and caches.

**Requirement:** introduce `evolution_transactions`. Every create/improve/merge/archive/promote/rollback/broker-policy update must be committed or rolled back as one logical transaction. Filesystem writes remain staged and atomic; database state uses row-level transactions; external effects such as caches and embeddings use transaction-bound activation flags and invalidation records.

### 2.20 Action attribution is required for risky runtime effects

Indirect prompt-injection and memory-poisoning research shows that unsafe behavior can be caused by retrieved memories, tool outputs, skill text, or broker-rendered context without any obvious malicious phrase. Runtime safety should ask not only "is this text suspicious?" but also "why is this action being taken?"

**Requirement:** for high-risk tool calls, state mutation, shell execution, credential-adjacent access, network access, or file writes, log the contributing user intent, skill IDs, memory IDs, broker policy version, retrieved artifacts, and tool-output sources. Where feasible, run counterfactual or attenuated replay to determine whether the action survives without untrusted context. Failed attribution becomes negative evidence and can trigger rollback/freeze.

### 2.21 Skill routing needs body-level access, not metadata alone

Routing work shows that names and short descriptions are often insufficient in overlapping skill libraries. The broker must inspect full procedural content, constraints, support manifests, contracts, examples, and negative-use boundaries to choose correctly.

**Requirement:** maintain separate searchable representations for name, description, frontmatter, SkillIR fields, compiled runtime text, support-file summaries, contracts, and probes. The broker/reranker can use all of them. The OpenClaw prompt still receives only the compact compiled runtime interface.

### 2.22 Harmful capability is different from prompt injection

A skill can be harmful even if it contains no prompt-injection payload. It can normalize, accelerate, or conceal unsafe actions by presenting them as reusable procedures. This is separate from whether the skill file is syntactically safe.

**Requirement:** scanner policy must classify capability risk, not only text risk. Generated skills that encode hazardous cyber, fraud, privacy-violating, credential-harvesting, surveillance, coercive, or illegal workflows are rejected or restricted regardless of measured utility.

### 2.23 Marginal skill utility must be proven in realistic contexts

Empirical benchmark work shows many skills provide little or no marginal benefit, some increase token cost substantially, and some degrade performance through version-mismatched or context-incompatible guidance.

**Requirement:** acceptance and active-priority policy must require marginal-value evidence for important skills: with/without skill, old/new version, hidden/visible, sibling bundle, and broker variant trials. A skill may remain archived even if semantically relevant when measured marginal value is low or negative.

### 2.24 Dynamic evaluation is part of maintenance, not a one-time gate

Static probes age. User workflows, file formats, APIs, OpenClaw behavior, model behavior, and artifacts change. Evaluation systems that synthesize fresh tests from real artifacts better match evolving usage.

**Requirement:** generate and retire probes continuously from failures, drift signals, canary results, artifact samples, and executor-profile changes. Probe banks are versioned. Stale probes are preserved for history but not allowed to dominate current decisions.

### 2.25 Core infrastructure self-modification is out of scope for v1

Source-level self-rewriting can address failures unreachable from skill text, but it also increases blast radius. SkillKernel's v1 safety case depends on deterministic control-plane components being stable enough to govern generated skills.

**Requirement:** the plugin, sidecar, scheduler, migrations, scanner, evaluator, compiler, policy engine, and deterministic writer are not autonomously rewritten. SkillKernel may log infrastructure-defect evidence and generate operator-review proposals, but v1 autonomous mutation is limited to SkillKernel-owned skills, manifests, support artifacts, broker policy versions, probes, and lifecycle state.

### 2.26 Rollback and deletion are provenance-graph operations

A rolled-back skill can leave downstream state behind: embeddings, memory summaries, broker hints, cached retrieval scores, attribution records, or derived probes. A deleted private fact can survive inside a skill or embedding if provenance is incomplete.

**Requirement:** every derived object stores provenance edges to source events, evidence, memories, skills, versions, transactions, and compiler/rendering policies. Rollback, quarantine, and deletion jobs traverse those edges and revoke, re-embed, recompile, or mark derived artifacts inactive.

### 2.27 The broker must be allowed to abstain

The right answer is sometimes not to load any skill. A skill can be semantically close but harmful, stale, redundant, token-wasteful, or likely to shadow a better low-level skill.

**Requirement:** `no_skill`, `defer_skill`, `use_builtin_only`, and `skill_hidden_control` are first-class broker decisions and logged outcomes. Curation policy should learn from cases where abstention produced better results.


### 2.28A Skill libraries must be optimized as topology, not append-only collections

The newest skill-bank and skill-scaling literature reinforces a single point: a growing library is not automatically better. Libraries become useful when their shape is governed: diverse enough to cover demand, compact enough to route accurately, decomposed enough to avoid black-hole skills, and composed enough to avoid repeating multi-skill workflows by hand.

**Requirement:** represent the skill library as a graph of skills, components, relationships, evidence clusters, and operation history. Bank-level curation must optimize topology, not only individual skill scores.

### 2.28B Skill granularity must be adaptive

Recent multi-granularity skill work argues against treating every skill as a flat, single-resolution prompt block. Useful libraries contain planning skills, functional skills, atomic execution skills, validators, adapters, and higher-order composed workflows.

**Requirement:** SkillIR must support nested components and relationship edges. The compiler can emit a compact `SKILL.md` for OpenClaw, but the internal representation must preserve multi-level structure for routing, composition, decomposition, and evaluation.

### 2.28C Composition and decomposition require causal-ish evidence, not aesthetic preference

The system should not compose skills because they look related, nor decompose skills because they look long. Composition requires evidence that a set of skills repeatedly participates in the same user-level goal and that a composed workflow improves utility, cost, reliability, or verification. Decomposition requires evidence that one broad skill contains separable usage clusters, routing false positives, partial-use patterns, or unrelated failure modes.

**Requirement:** compose/decompose operations require co-usage or partial-use evidence, operation-specific probes, and counterfactual/marginal-value trials. Cosmetic refactoring is not enough.

### 2.28D Routing and topology co-evolve

Skill composition and decomposition change retrieval behavior. A composed skill can shadow its components; a decomposed successor can reduce false positives but increase missing-prerequisite errors. Therefore topology operations must be broker-aware.

**Requirement:** every compose/decompose transaction includes broker replay, shadowing probes, component/successor routing tests, and no-skill/old-skill controls. Activation updates broker edges and context-rendering policy atomically.

### 2.28E Evidence quality determines autonomous decision quality

The value of autonomous skill operations depends on whether collected data can answer the right questions: what task was attempted, which skills were retrieved, which were visible, which were actually used, which were ignored, what tool calls followed, what failed, what the user corrected, what outcome was achieved, and what it cost.

**Requirement:** data capture must be designed from the start to support operation selection. “Usage count” is insufficient. Store co-retrieval, co-injection, co-use, sequence, partial-use, shadowing, missing-skill, no-skill, and intervention-trial events.



### 2.29 Context is finite, lossy, and distracting

Long-context capability does not remove the need for disciplined context construction. The system must assume that larger runtime context can increase cost, latency, distraction, false retrieval, and reasoning degradation even when the context window is not full.

**Requirement:** all skill-bank decisions must optimize net utility under an effective context budget, not merely nominal model context length.

### 2.30 Progressive disclosure is necessary but insufficient

Skill systems commonly use metadata-first loading and full-instruction loading only when needed. SkillKernel must go further: metadata, full instructions, support-file references, support-file excerpts, broker hints, and composed-skill bundles must all be classified, token-budgeted, and evaluated.

**Requirement:** progressive disclosure is implemented through context-loadability classes, not by assuming non-`SKILL.md` files are harmless.

### 2.31 Prompt compression must preserve operational semantics

Compression that deletes tokens without preserving operational contracts is unsafe. SkillKernel must compile SkillIR into compact runtime text through a measured semantic-density pipeline: compress, render, verify required fields, run equivalence probes, test target behavior, test regressions, and reject drift.

**Requirement:** runtime text compression is an evaluated compiler pass with semantic-equivalence tests, not a free-form summarization step.

### 2.32 AI-facing text differs from human-facing documentation

SkillKernel-generated skills are intended for model consumption. Human readability is secondary to correctness, compactness, unambiguous triggers, execution fidelity, and safety. The full human/debug explanation belongs in Postgres audit records and optional operator reports, not in context-loaded files.

**Requirement:** context-loadable language should be terse, structured, repetitive only where repetition improves model compliance, and free of human-oriented rationale.

### 2.33 Context pressure is a topology signal

Over-broad skills, overly general descriptions, verbose workflow skills, and frequently ignored skill bundles waste context and can harm routing. These are not only compression defects; they are evidence for decomposition, description tightening, archiving, or broker abstention. Conversely, repeated co-use can justify a composed skill only when it reduces total context and execution overhead.

**Requirement:** context telemetry is an input to create/improve/compose/decompose decisions.



### 2.34 Orchestration, not only availability, is the scaling bottleneck

The skill bank should not optimize for raw skill count. As the library grows, the limiting factor becomes selecting, sequencing, and composing the right minimal subset under context budget. Graph-composition research supports treating skills as nodes with preconditions, effects, dependencies, conflicts, and repair scopes rather than independent Markdown fragments.

**Requirement:** composed/decomposed workflows use SkillGraphIR when multiple component skills, ordered effects, verifier nodes, fallback branches, or local repairs are involved.

### 2.35 Formal contracts improve reliability, but OpenClaw output remains `SKILL.md`

Research on formal skill representations, typed pseudocode, and structured skill languages supports typed contracts, schema validation, executability constraints, deterministic quality checks, and explicit side-effect declarations. SkillKernel should adopt those internally without requiring OpenClaw to load a custom runtime format.

**Requirement:** SkillIR and SkillGraphIR are canonical internal contracts; OpenClaw `SKILL.md` remains the compiled, token-budgeted runtime artifact.

### 2.36 Local/operator-selected models require qualification, not blind trust

The simplified v1 model-access design is correct: one text model profile and one embedding profile. The missing hardening is qualification. A local or hosted model may fail JSON adherence, lose evidence IDs, hallucinate paths, compress away constraints, ignore refusal policy, mishandle long context, or produce unstable outputs. An embedding model may have the wrong dimension, poor query/document behavior, or unstable batches.

**Requirement:** active text and embedding profiles must pass lightweight qualification probes before autonomous apply. Failed profiles may still be usable for propose-only or classification tasks if explicitly allowed, but cannot be treated as production-autonomous reasoning backends.

### 2.37 Embedding profiles are retrieval contracts

pgvector stores and indexes vectors, but the embedding model defines the geometry. Vectors from different models, dimensions, query/document modes, or distance metrics are not interchangeable. Re-embedding campaigns are migration work, not transparent updates.

**Requirement:** every vector records embedding profile, dimension, metric, input mode, and source object. Retrieval never compares vectors across incompatible embedding profiles. Profile changes trigger controlled re-embedding and recall calibration.

### 2.38 Generated skills are supply-chain artifacts

Auto-generated skills, support scripts, manifests, probes, broker policies, and compiled snippets are artifacts that can be tampered with, partially rolled back, or activated without their dependencies if provenance is weak.

**Requirement:** each activated skill artifact set has a provenance manifest with artifact hashes, generator metadata, source SkillIR revision, scanner/evaluator gate IDs, capability declarations, and rollback pointer. Activation verifies the manifest before exposing the artifact.

### 2.39 Final research boundary

The latest research does not suggest replacing the existing architecture. It reinforces the existing design: a deterministic control plane, a governed evidence store, compact AI-facing compiled artifacts, profile-qualified LLM/embedding access, graph-aware composition, regression-aware evaluation, supply-chain manifests, and rollback-complete transactions.

**Requirement:** future conceptual changes should be admitted only when they identify a concrete failure mode not already covered by redaction, provenance, evidence maturity, profile qualification, SkillIR/SkillGraphIR contracts, transactionality, scanner, evaluator, broker, rollback, canary, or freeze.

### 2.40 Design closure condition

The remaining risk is no longer missing architecture. It is implementation discipline. The document now covers capture, redaction, provenance, storage, scheduling, retrieval, body-aware routing, SkillIR, compilation, LLM/deterministic boundaries, scanner, evaluator, transactionality, rollback, memory governance, broker governance, autonomous topology operations, creation, improvement, composition, decomposition, curation, archiving, promotion, external-skill inventory, harmful-capability controls, executor profiles, observability, retention, and implementation order.

**Requirement:** development should now proceed. New design changes should be admitted only when implementation discovers a concrete failure mode not covered by the current control surfaces.


---

## 3. Non-negotiable final decisions

Add this invariant to every implementation review:

```text
Context-loadable artifacts are compiled, budgeted, AI-facing runtime interfaces.
Full-fidelity evidence and rationale live in SkillIR/Postgres, not in the prompt.
```

| Area | Decision | Rationale |
|---|---|---|
| Physical database per skill | **No.** | Fragments retrieval, pooling, migrations, backup, and global analytics. |
| Per-skill schemas | **No in v1.** | Acceptable in theory for strict isolation, but unnecessary for the default design. They complicate migrations and do not improve topology, retrieval, curation, or broker algorithms. |
| Database layout | **One Postgres database, one `autoskill` schema.** | Best balance of global retrieval, lifecycle analytics, durability, and operational simplicity. |
| Skill isolation | **Logical ownership by `workspace_id`, `skill_id`, version, and source.** | Provides isolation without dynamic schema sprawl. |
| Scaling | **Indexes, partitions, rollups, and retention before schema fragmentation.** | Keeps query planning predictable. |
| OpenClaw Cron | **Do not use.** | It is user/Gateway-facing automation, not SkillKernel’s internal maintenance substrate. |
| Skill Workshop | **Do not depend on it.** | It is experimental and can change. Use only as conceptual prior art. |
| Plugin role | **Capture, redact, spool, forward, status/control, optional fast context hint.** | Hooks are in-process and must remain lightweight. |
| Sidecar role | **All analysis, scheduling, DB work, LLM calls, mutation, curation, evaluation, rollback.** | Slow autonomous work belongs outside OpenClaw runtime. |
| Scheduler | **Sidecar-owned durable scheduler in Postgres.** | Independent, replayable, observable, leased, crash-safe. |
| Queue | **Postgres jobs table with leases and idempotency.** | Preserves transactional coupling and avoids an additional broker in v1. |
| Evolution transaction | **Every autonomous mutation is transaction-scoped.** | Rollback must cover DB state, files, embeddings, caches, broker exposure, probes, lifecycle, and audit. |
| Generated skills | **Normal OpenClaw skill directories with `SKILL.md`.** | Maintains compatibility and portability. |
| Active skill root | **`<workspace>/skills/autoskill/<slug>/`** | Clear ownership under a normal skill root. |
| Archive root | **`<workspace>/.autoskill/archive/<skill-id>/v<version>/`** | Outside OpenClaw skill roots; searchable only through SkillKernel. |
| Mutation scope | **Only SkillKernel-owned skills mutate automatically.** | Third-party/user-authored skills are separate trust boundaries. |
| Core infrastructure mutation | **No autonomous rewriting of the plugin, sidecar, scheduler, scanner, evaluator, compiler, migrations, or policy engine in v1.** | The control plane must remain deterministic and governable. |
| External skill adoption | **Explicit operator action only.** | Not autonomous v1. |
| Creation priority | **Improve active → promote archived → merge/supersede → create new.** | Prevents duplicate bloat. |
| Runtime context | **Bounded skill-context broker.** | Prevents skill shadowing and token waste. |
| Broker abstention | **`no_skill` is a valid broker decision.** | Skill injection can hurt; abstention must be measured and rewarded when useful. |
| File writes | **LLM emits structured plans; deterministic writer applies.** | Prevents arbitrary paths and shell behavior. |
| Evaluation | **Hard safety gate + hard regression gate + multi-objective ranking.** | Reliability before optimization. |
| Trial evaluation | **Evaluate candidate artifacts in isolated trial workspaces/executor profiles before activation.** | Prevents candidate side effects from contaminating production state. |
| Risky action attribution | **Log causal contributors for high-risk actions and run counterfactual/attenuated checks where feasible.** | Runtime security depends on intent-to-execution integrity, not only text scanning. |
| Skill text | **Compiled runtime interface.** | Minimizes prompt overhead and ambiguity. |
| Memory | **DB-side governed memory.** | Avoids context bloat and memory poisoning. |
| Raw secrets | **Never store, embed, or compile.** | Redact before persistence and embedding. |
| User-specific data | **Never compile into general skills.** | Skills encode reusable procedure, not private facts. |
| Backfill | **Optional importer.** | Live plugin capture is primary. |
| Default autonomy | **`autonomous_guarded`.** | Applies safe changes automatically; rejects unsafe changes automatically. |

---


## 3.1 LLM and deterministic execution boundary

SkillKernel uses an LLM only where semantic judgment, abstraction, synthesis, or natural-language reasoning is required. It uses deterministic programmatic code everywhere a bounded algorithm can produce the correct result more safely, cheaply, repeatably, and audibly.

This is a non-negotiable implementation boundary, not an optimization suggestion.

### 3.1.1 Core rule

```text
Use deterministic code for control, persistence, security, scheduling, IO, scoring, policy, validation, writing, rollback, and accounting.
Use LLM calls for semantic interpretation, reusable-procedure induction, structured plan generation, repair hypotheses, compression decisions, and ambiguous evidence classification.
Never let an LLM directly control paths, SQL, shell commands, scheduler state, policy decisions, file writes, archive/promotion state, or rollback behavior.
```

The LLM is a proposal engine. Deterministic services are the authority.

### 3.1.2 Required LLM uses

LLM calls are appropriate for these jobs because deterministic code cannot reliably infer the required procedural abstractions from messy real-world traces:

| Job | Why the LLM is used | Output contract |
|---|---|---|
| candidate skill discovery from transcript/evidence clusters | identify repeated latent workflows, missing procedures, user corrections, and recurring task intent | candidate classification plus cited evidence IDs |
| contrastive success/failure analysis | infer what successful trajectories did differently from failed ones | reusable behavioral delta with cited traces |
| skill creation planning | synthesize a new procedural capability from multiple evidence items | structured candidate plan JSON only |
| skill improvement planning | infer repair hypotheses from failures, corrections, regressions, and drift | structured patch plan JSON only |
| semantic compilation decisions | choose which components become runtime text and which remain DB-side memory | structured component selection and runtime-section draft |
| description and applicability refinement | write compact frontmatter descriptions, aliases, `WHEN`, and `DO NOT USE WHEN` boundaries | bounded text fields validated by deterministic checks |
| ambiguous outcome attribution support | help classify hard cases where a skill may have helped, hurt, been ignored, or been shadowed | suggested attribution, never final ledger write without rule checks |
| semantic scanner support | detect prompt-injection-like intent or unsafe instruction semantics beyond regex/static checks | scanner finding with severity and rationale |
| probe generation | generate natural-language or tool-use regression probes from evidence | probe specification, expected behavior, and pass/fail conditions |
| topology reasoning | decide whether skills should be deduplicated, composed into a workflow skill, or decomposed into sharper skills | structured topology proposal with evidence |

Every LLM output must be schema-validated, evidence-linked, scanned, and either accepted by deterministic gates or discarded.

### 3.1.3 Deterministic-only responsibilities

The following must never depend on LLM judgment as the final authority:

| Responsibility | Deterministic implementation |
|---|---|
| event capture, redaction, taint marking, and spooling | plugin code with explicit rules and allowlists |
| authentication, authorization, and control API access | fixed policy and credentials/mTLS/token validation |
| scheduling and job execution | Postgres schedules/jobs, leases, idempotency keys, advisory locks |
| SQL generation and migrations | static migrations and parameterized queries only |
| embedding writes and retrieval queries | fixed query builders, indexes, thresholds, exact rerank |
| scoring and threshold decisions | configured formulas and calibrated policy tables |
| active/archive/promote/freeze/rollback state transitions | explicit finite-state machine |
| scanner hard denylists | static/path/Markdown/script/capability scanners |
| capability enforcement | manifests, allowlists, and workspace policy |
| filesystem writes | deterministic path-contained writer using staged directories |
| rollback | manifest hashes, version records, atomic replace/restore |
| token counting and context budgets | deterministic tokenizer estimate and hard caps |
| probe execution | evaluator harness with fixed pass/fail collection |
| regression acceptance | deterministic gate over scanner results, probe outcomes, budgets, and policy |
| audit logging | append-only records and hash chaining |
| retention and deletion | policy-driven jobs with audit records |
| canary/freeze behavior | configured failure thresholds and automatic state transitions |

The LLM can recommend an action in these areas, but deterministic code decides whether the action is legal, safe, useful, and applied.

### 3.1.4 Token-use and LLM-call control

LLM use is limited at the job level. SkillKernel does **not** implement a direct dollar-cost tracker, price analyzer, or model-price optimizer. Cost mitigation is achieved by operator-selected provider/model configuration, local-model support, deterministic prefiltering, concurrency limits, timeout limits, maximum prompt/output token limits, and queue policy.

The runtime broker must not call an LLM synchronously during OpenClaw hook execution. Maintenance jobs may call an LLM only when cheaper deterministic filters have already narrowed the work.

Required call-minimization order:

```text
hard filters
→ lexical search
→ vector candidate search
→ exact rerank
→ deterministic clustering/scoring
→ LLM only for the reduced ambiguous set
→ deterministic validation and application
```

Examples:

- Do not ask an LLM whether every event is a skill candidate. First aggregate events into clusters and only send recurring/high-signal clusters.
- Do not ask an LLM to retrieve skills. Retrieve with hybrid search, then optionally use the LLM only for hard disambiguation cases outside the synchronous path.
- Do not ask an LLM to count runtime context tokens or enforce budgets. Count and enforce deterministically.
- Do not ask an LLM to decide whether a patch is accepted. The LLM proposes; scanner/evaluator/policy gates decide.

### 3.1.5 Execution modes

LLM calls have three execution modes:

| Mode | Allowed latency | Uses | Notes |
|---|---:|---|---|
| synchronous hook path | none | no LLM calls | only cached context hints and deterministic lookup |
| asynchronous maintenance path | normal worker latency | creation, improvement, compilation, probes, semantic scans | budgeted and retryable through job queue |
| emergency repair path | bounded worker latency | rollback explanation, repair proposal after canary failure | cannot bypass scanner/evaluator gates |

This prevents skill management from degrading the interactive OpenClaw session.

### 3.1.6 LLM client abstraction under one active text profile

The sidecar exposes an internal `LLMClient` abstraction with typed purposes rather than raw ad hoc prompt calls. This abstraction is **not** a per-operation model-routing matrix. Every typed purpose uses the single operator-selected active text model profile from Section 3.2 unless a job is disabled because the active profile is not qualified for that purpose.

Typed purposes:

```text
classify_candidate_cluster
analyze_success_failure_delta
generate_skill_plan
propose_skill_patch
generate_composition_plan
generate_decomposition_plan
generate_probe_specs
compile_runtime_sections
semantic_scan_artifact
suggest_merge_or_deduplicate
explain_policy_rejection
```

Each typed purpose has:

- a JSON schema;
- required evidence inputs;
- maximum input tokens;
- maximum output tokens;
- timeout;
- retry policy;
- priority class;
- redaction requirement;
- audit record;
- deterministic validator;
- fallback behavior.

No component calls a generic chat-completion function directly. No component selects a different model per operation in v1. The only active text LLM choice is the configured text model profile.

### 3.1.7 Single-profile capability policy

SkillKernel uses one active text profile in v1. The profile is qualified into capability levels by fixed probes:

| Qualification | Allowed use |
|---|---|
| `qualified_autonomous` | May propose create/improve/compose/decompose plans that can proceed to deterministic gates. |
| `qualified_propose_only` | May draft proposals, but autonomous apply is blocked. |
| `qualified_classify` | May classify evidence, labels, and low-risk semantic fields only. |
| `failed` | Not used by SkillKernel jobs. |

High-impact actions such as creating a skill, expanding capability, composing workflow skills, decomposing broad skills, or accepting a broad patch require `qualified_autonomous`. If the active profile is only `qualified_propose_only`, the sidecar may store proposals and evaluator results but must not activate changes automatically. If the active profile is only `qualified_classify`, semantic mutation jobs are skipped.

This preserves user/operator control, avoids hidden provider/model selection, avoids cost-optimization machinery, and keeps v1 implementation simple while still preventing weak local models from driving autonomous mutations.

### 3.1.8 Fallback behavior

If the LLM provider is unavailable:

- event capture continues;
- redaction, tainting, storage, retrieval logs, usage tracking, curation rollups, archive scoring, canary monitoring, and rollback continue;
- no new skill creation or semantic improvement is applied;
- no composition or decomposition proposal is activated;
- deterministic archival may continue only for clearly inactive SkillKernel-owned skills if policy allows;
- promotion may continue only when an archived skill exactly matches a deterministic recurrence rule and passes scanner/evaluator gates;
- all LLM-dependent jobs remain queued or fail with retryable status according to job policy;
- the plugin never blocks interactive OpenClaw work because maintenance LLM access is unavailable.

If deterministic infrastructure is unavailable, SkillKernel fails closed. It must not ask an LLM to bypass missing scheduler, scanner, evaluator, writer, rollback, token-budget, or database controls.

## 3.2 Operator-configurable LLM and embedding access profiles

### 3.2.1 Final requirement

SkillKernel must support operator-controlled LLM and embedding access, but v1 must keep the configuration deliberately simple.

The final simplified model-access decision is:

```text
one text LLM access profile
one embedding access profile
no operation-level model-routing matrix in v1
no direct dollar-cost tracker/analyzer
no model-price optimizer
```

The operator chooses the provider/model route. SkillKernel does not hardcode a hosted model, local model, embedding model, thinking level, token cap, timeout, or endpoint.

The two supported route types are:

| Route type | Purpose |
|---|---|
| `openclaw` | Send SkillKernel service-model requests through a supported OpenClaw provider/model capability or secured OpenClaw-compatible service seam. |
| `openai_compatible` | Send SkillKernel service-model requests directly to an OpenAI-compatible `/v1` endpoint, especially local or self-hosted llama.cpp, Ollama, LM Studio, vLLM, SGLang, or LiteLLM deployments. |

This is intentionally less granular than the earlier model-router variant. The previous per-operation routing matrix was powerful but unnecessary for v1 and increased configuration burden, test matrix size, failure modes, and support complexity. Deterministic prefiltering, batching, token limits, and operator model choice provide the needed cost/privacy controls without per-operation model routing.

### 3.2.2 Text LLM access profile

All semantic LLM work in v1 uses the single configured text profile:

```text
candidate-cluster interpretation
success/failure contrast
skill creation planning
skill improvement planning
skill composition planning
skill decomposition planning
context compilation
semantic equivalence support
semantic scanner support
probe generation
ambiguous attribution assistance
operator-facing explanation generation
```

This does **not** mean every job calls the LLM. It means any job that reaches the LLM uses the same configured text profile. Deterministic filters decide whether a call is needed.

The text profile must define:

```text
route_type: openclaw | openai_compatible
provider/model or endpoint model id
thinking level, if supported
thinking fallback behavior
base URL and API-key env vars for direct OpenAI-compatible route
temperature
max input tokens
max output tokens
timeout
retry policy
concurrency limit
hosted/local policy
```

The active OpenClaw chat/session model is not implicitly reused. SkillKernel has its own service model profile so normal user-facing model changes do not silently alter autonomous maintenance behavior.

### 3.2.3 OpenClaw-routed text profile

When `route_type: openclaw`, SkillKernel should use a stable supported OpenClaw provider/model capability if one exists for the target OpenClaw version.

Rules:

1. Use canonical OpenClaw-style `provider/model` references.
2. Validate that the configured provider/model exists and supports the required text-generation capability.
3. Validate the requested thinking/reasoning level when the provider exposes that capability.
4. Do not drive the normal interactive user session.
5. Do not inherit user session tools, memory, approvals, or transient context.
6. Do not scrape OpenClaw internals.
7. If the only available route is OpenClaw's OpenAI-compatible Gateway surface, require explicit opt-in, local/private network exposure, authentication, rate limiting, and a no-tools service profile.

The OpenClaw-routed profile is the best default when the operator wants SkillKernel to follow OpenClaw's configured provider/model ecosystem.

### 3.2.4 Direct OpenAI-compatible text profile

When `route_type: openai_compatible`, SkillKernel calls a configured `/v1` endpoint directly.

This is the required v1 escape hatch for local-first, private, offline, self-hosted, or low-cost deployments.

Required behavior:

1. Support `/v1/chat/completions` as the baseline endpoint.
2. Support `/v1/responses` only if explicitly configured and the target server supports it.
3. Do not require provider-specific adapters for Ollama, llama.cpp, LM Studio, vLLM, SGLang, or LiteLLM in v1 if their OpenAI-compatible routes work.
4. Require `base_url_env` and `api_key_env`; allow dummy API keys for local servers that require the header shape but do not validate it.
5. Disable tools/function-calling for SkillKernel maintenance prompts unless a future audited feature explicitly requires it.
6. Treat the direct route as untrusted infrastructure: validate schema outputs, enforce timeouts, and never allow model output to control paths, SQL, shell, or policy.

### 3.2.5 Thinking/reasoning-level policy

Use a provider-neutral logical field:

```text
thinking: off | minimal | low | medium | high | xhigh | adaptive | max
```

The adapter maps this to the configured route when supported.

Required behavior:

- `strict`: fail the job if the configured model does not support the requested thinking level;
- `downgrade`: use the nearest supported lower/equivalent level and audit the downgrade;
- `omit`: do not send a thinking field for providers that do not expose one.

For direct local OpenAI-compatible endpoints, `omit` is often the practical default because many local servers ignore or reject provider-specific reasoning fields.

### 3.2.6 Token, concurrency, and outage controls

SkillKernel does not implement direct dollar-cost tracking.

The access layer enforces only operational controls:

- maximum input tokens;
- maximum output tokens;
- timeout;
- retry policy;
- maximum concurrent LLM calls;
- local-only mode;
- hosted-disabled mode;
- sensitive-field-to-hosted-model policy;
- provider outage behavior.

If the text model route is unavailable, LLM-dependent maintenance jobs pause or retry. Deterministic capture, storage, redaction, retrieval logging, rollback, scanner hard checks, curation rollups, archive scoring, and canary monitoring continue.

### 3.2.7 Invocation audit, not cost ledger

SkillKernel records LLM invocations for reproducibility, debugging, safety audit, and rollback reasoning. It does not compute dollar cost, estimate price, enforce currency-denominated caps, rank models by price, or produce cost analytics.

The invocation audit may record:

```text
job id
purpose class
route type
provider/model or endpoint model id
requested/effective thinking setting
input/output token counts if returned by provider
latency
prompt hash
response hash
schema-validation result
downstream acceptance result
error code
```

The audit must not store raw prompts or raw responses unless a separate redacted retention policy explicitly allows it.

### 3.2.8 Embedding access profile

pgvector stores and searches vectors. It does not create embeddings. SkillKernel therefore needs a separately configured embedding profile.

The embedding profile uses the same two route types:

| Route type | Purpose |
|---|---|
| `openclaw` | Use a supported OpenClaw embedding provider/capability or secured OpenClaw-compatible embedding endpoint. |
| `openai_compatible` | Call a configured `/v1/embeddings` endpoint directly. |

The embedding profile must declare:

```text
route_type
provider/model or endpoint model id
base URL/API-key env vars when direct
dimensions
distance metric
batch size
timeout
local/hosted policy
```

Rules:

1. Never silently use a hosted default embedding model.
2. Never compare vectors generated by different embedding profiles as if they live in the same embedding space.
3. Store `embedding_profile_id`, provider/model, dimension, distance metric, text hash, object type, object ID, and provenance for every vector.
4. Changing the embedding profile creates a re-embedding campaign, not an in-place rewrite.
5. During migration, retrieval may query old and new profiles separately, exact-rerank, and log disagreements until the new profile passes recall audits.

### 3.2.9 Embedding table shape

Use an unconstrained `vector` column plus `embedding_dim` and profile-specific partial expression indexes. Do not use a single hardcoded `vector(1536)` table in v1.

This preserves operator freedom to use OpenAI, local, Ollama, Gemini, Voyage, Mistral, OpenAI-compatible, or other embedding models with different vector dimensions.

Example profile-specific HNSW index:

```sql
CREATE INDEX embeddings_hnsw_profile_1536_cosine
ON autoskill.embeddings
USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE embedding_profile_id = '<profile_uuid>' AND embedding_dim = 1536;
```

Queries must cast to the profile dimension and filter by `embedding_profile_id`:

```sql
SELECT *
FROM autoskill.embeddings
WHERE workspace_id = $1
  AND embedding_profile_id = $2
ORDER BY embedding::vector(1536) <=> $3::vector(1536)
LIMIT $4;
```

### 3.2.10 Required model/embedding control-plane tables

```sql
CREATE TABLE autoskill.text_model_profiles (
  text_model_profile_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  name text NOT NULL,
  route_type text NOT NULL CHECK (route_type IN ('openclaw','openai_compatible')),
  provider text,
  model text NOT NULL,
  base_url_env text,
  api_key_env text,
  endpoint_kind text NOT NULL DEFAULT 'chat_completions' CHECK (endpoint_kind IN ('chat_completions','responses')),
  thinking_level text NOT NULL DEFAULT 'off',
  thinking_fallback_policy text NOT NULL DEFAULT 'omit' CHECK (thinking_fallback_policy IN ('strict','downgrade','omit')),
  temperature numeric(4,3) NOT NULL DEFAULT 0,
  max_input_tokens integer NOT NULL,
  max_output_tokens integer NOT NULL,
  timeout_ms integer NOT NULL DEFAULT 120000,
  max_concurrent integer NOT NULL DEFAULT 1,
  hosted_allowed boolean NOT NULL DEFAULT true,
  local_only boolean NOT NULL DEFAULT false,
  enabled boolean NOT NULL DEFAULT true,
  config jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, name)
);

CREATE TABLE autoskill.llm_invocations (
  llm_invocation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  job_id uuid,
  purpose_class text NOT NULL,
  text_model_profile_id uuid REFERENCES autoskill.text_model_profiles(text_model_profile_id),
  route_type text NOT NULL,
  provider text,
  model text NOT NULL,
  requested_thinking_level text,
  effective_thinking_level text,
  thinking_downgraded boolean NOT NULL DEFAULT false,
  input_tokens integer,
  output_tokens integer,
  latency_ms integer,
  prompt_hash text NOT NULL,
  response_hash text,
  schema_valid boolean,
  accepted_downstream boolean,
  status text NOT NULL CHECK (status IN ('succeeded','failed','rejected','cancelled','unavailable','rate_limited')),
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.embedding_profiles (
  embedding_profile_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  name text NOT NULL,
  route_type text NOT NULL CHECK (route_type IN ('openclaw','openai_compatible')),
  provider text,
  model text NOT NULL,
  base_url_env text,
  api_key_env text,
  dimensions integer NOT NULL,
  distance_metric text NOT NULL DEFAULT 'cosine' CHECK (distance_metric IN ('cosine','l2','inner_product')),
  batch_size integer NOT NULL DEFAULT 128,
  timeout_ms integer NOT NULL DEFAULT 60000,
  hosted_allowed boolean NOT NULL DEFAULT true,
  local_only boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','warming','retiring','retired','failed')),
  config jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, name)
);
```

There is no `operation_model_routes` table in v1 and no cost-estimate column in the invocation audit.

### 3.2.11 Configuration example

OpenClaw-routed text model plus direct local OpenAI-compatible embeddings:

```yaml
autoskill:
  llm:
    active_profile: service_reasoner
    profiles:
      service_reasoner:
        route_type: openclaw
        provider: configured-openclaw-provider
        model: provider/model
        thinking: high
        thinking_fallback_policy: strict
        temperature: 0
        max_input_tokens: 80000
        max_output_tokens: 8000
        timeout_ms: 180000
        max_concurrent: 1
        hosted_allowed: true
        local_only: false

  embeddings:
    active_profile: local_embeddings
    profiles:
      local_embeddings:
        route_type: openai_compatible
        provider: local-embedding
        model: embedding-model-id
        base_url_env: AUTOSKILL_EMBEDDING_BASE_URL
        api_key_env: AUTOSKILL_EMBEDDING_API_KEY
        dimensions: 1536
        distance_metric: cosine
        batch_size: 128
        timeout_ms: 60000
        hosted_allowed: false
        local_only: true
```

Direct local OpenAI-compatible text model plus direct local embeddings:

```yaml
autoskill:
  llm:
    active_profile: local_reasoner
    profiles:
      local_reasoner:
        route_type: openai_compatible
        provider: local-llm
        model: local-model-id
        base_url_env: AUTOSKILL_LOCAL_LLM_BASE_URL
        api_key_env: AUTOSKILL_LOCAL_LLM_API_KEY
        endpoint_kind: chat_completions
        thinking: omit
        thinking_fallback_policy: omit
        temperature: 0
        max_input_tokens: 32000
        max_output_tokens: 4000
        timeout_ms: 180000
        max_concurrent: 1
        hosted_allowed: false
        local_only: true

  embeddings:
    active_profile: local_embeddings
    profiles:
      local_embeddings:
        route_type: openai_compatible
        provider: local-embedding
        model: embedding-model-id
        base_url_env: AUTOSKILL_EMBEDDING_BASE_URL
        api_key_env: AUTOSKILL_EMBEDDING_API_KEY
        dimensions: 768
        distance_metric: cosine
        batch_size: 64
        timeout_ms: 60000
        hosted_allowed: false
        local_only: true
```

### 3.2.12 Development acceptance criteria

Before autonomous skill mutation is enabled:

1. Operator can configure one active text model profile.
2. Operator can configure one active embedding profile.
3. Text profile supports `openclaw` and `openai_compatible` route types.
4. Embedding profile supports `openclaw` and `openai_compatible` route types.
5. Operator can force local-only mode.
6. Operator can disable hosted models.
7. Operator can set one thinking/reasoning level for the active text profile.
8. Unsupported thinking levels fail, downgrade, or omit according to explicit policy.
9. LLM invocations are audited without dollar-cost accounting.
10. Every vector records its embedding profile.
11. Re-embedding campaign works when the embedding profile changes.
12. Runtime hooks perform no synchronous LLM calls.
13. LLM provider outage pauses semantic jobs but does not block event capture, rollback, or deterministic curation.
14. pgvector indexes are profile/dimension-specific when multiple dimensions are supported.


## 3.3 Model and embedding profile qualification gates

The operator controls the text model and embedding model. SkillKernel must not assume those choices are safe, sufficiently capable, or semantically compatible with autonomous mutation. Qualification is a deterministic gate over model behavior, not a cost optimizer and not a multi-model routing system.

### 3.3.1 Text model qualification

A text profile is qualified by running fixed probe suites through the configured `openclaw` or `openai_compatible` route. The probes are versioned artifacts and must cover:

```text
schema/JSON adherence
evidence-ID preservation
path-control refusal
secret handling
prompt-injection resistance
structured SkillIR patch-plan generation
semantic compression fidelity
semantic-equivalence judgment on known cases
bounded output behavior under token limits
thinking-level support or explicit omit/downgrade behavior
```

Qualification verdicts:

```text
qualified_autonomous   = may be used for autonomous create/improve/compose/decompose proposals
qualified_propose_only = may draft proposals, but autonomous apply is blocked
qualified_classify     = may classify evidence or labels only
failed                 = not used by SkillKernel jobs
expired                = must requalify before autonomous use
```

The evaluator, scanner, compiler, token governor, writer, and rollback system remain deterministic authorities. A qualified model can propose; it cannot accept, write, schedule, archive, promote, or roll back.

### 3.3.2 Embedding profile qualification

An embedding profile is qualified separately from the text model. Required checks:

```text
reported dimension equals configured dimension
batch and single embeddings are stable enough for retrieval
known-neighbor semantic sanity tests pass
negative-pair separation is above threshold
query/document input modes behave as configured
vector distance metric matches index/operator class
profile-specific recall calibration succeeds
```

Embedding qualification failure disables trusted vector retrieval for that profile. Lexical retrieval and metadata filters may continue. Re-embedding campaigns are explicit jobs and never silently mix incompatible vector spaces.

### 3.3.3 Control-plane tables

```sql
CREATE TABLE autoskill.model_profile_qualification_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_name text NOT NULL,
  route_type text NOT NULL CHECK (route_type IN ('openclaw','openai_compatible')),
  provider text,
  model text NOT NULL,
  thinking text,
  probe_set_version text NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('qualified_autonomous','qualified_propose_only','qualified_classify','failed','expired')),
  probe_results jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);

CREATE TABLE autoskill.embedding_profile_qualification_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_name text NOT NULL,
  route_type text NOT NULL CHECK (route_type IN ('openclaw','openai_compatible')),
  provider text,
  model text NOT NULL,
  dimensions integer NOT NULL,
  distance_metric text NOT NULL,
  probe_set_version text NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('qualified','failed','expired')),
  probe_results jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);
```

### 3.3.4 Operational rules

```text
profile changed          → requalify
prompt/schema changed    → requalify text profile
embedding model changed   → requalify and start re-embedding campaign
qualification expired     → autonomous LLM-dependent apply pauses or downgrades
evaluator pass            → cannot override failed model qualification
operator override         → may enable propose-only, not unsafe autonomous apply
```

## 4. OpenClaw compatibility constraints

SkillKernel emits ordinary OpenClaw skills.

OpenClaw skills are directories containing a `SKILL.md` file with YAML frontmatter and Markdown instructions. Required frontmatter includes `name` and `description`. The active skill path is:

```text
<workspace>/skills/autoskill/<slug>/SKILL.md
```

Archived versions are not placed under an OpenClaw skill root:

```text
<workspace>/.autoskill/archive/<skill-id>/v<version>/
```

SkillKernel must preserve the following OpenClaw constraints:

1. `name` is lowercase letters, digits, and hyphens.
2. `description` is one line, compact, and routing-relevant.
3. `SKILL.md` must parse cleanly as Markdown with YAML frontmatter.
4. Long examples, diagnostics, evidence, and raw traces do not belong in runtime `SKILL.md`.
5. Supporting scripts/assets are allowed only when needed and must be declared in the manifest.
6. Skills should be organized under the SkillKernel subfolder so ownership is obvious.
7. Archive directories stay outside OpenClaw-visible roots so archived skills cannot be selected accidentally.

OpenClaw plugin hooks are the capture seam. Hook handlers should not run slow analysis or file mutation. They normalize, redact, enqueue, and return. The only optional prompt-adjacent behavior is a short, cached, sidecar-supplied runtime skill-context hint with a strict timeout and fail-soft behavior.

OpenClaw Cron is not used.

Skill Workshop is not used.

---

## 5. Autonomy policy

The production default is:

```yaml
autonomy_mode: autonomous_guarded
```

Autonomy modes:

| Mode | Behavior |
|---|---|
| `observe_only` | Capture, store, analyze. No proposals, no writes. |
| `propose_only` | Generate candidates and evaluations. No filesystem writes. |
| `auto_archive_only` | Can archive/demote SkillKernel-owned low-utility skills. No creation/improvement writes. |
| `autonomous_guarded` | Can create, improve, compile, archive, promote, merge, repair, and roll back SkillKernel-owned skills inside policy gates. |
| `autonomous_max` | Same as guarded but with lower thresholds, more exploration, and larger probe budgets. Still scanner/evaluator/rollback gated. |
| `frozen` | Emergency stop. Capture may continue; mutation and context hints stop. |

Default action rules:

1. If evidence is weak, do nothing.
2. If a matching active skill exists, improve or recompile it rather than create a new one.
3. If a matching archived skill exists, promote or repair it rather than create a new one.
4. If sibling skills conflict, merge/split/clarify before creating.
5. If a change fails scanner, reject or quarantine.
6. If a change fails target evaluation, reject.
7. If a change fails regression budget, reject.
8. If canary fails after activation, roll back.
9. If repeated failures occur, freeze the skill and require explicit operator action.

Quarantine is not the normal workflow. It is an exception bucket for potentially useful but unsafe/ambiguous artifacts.

---

## 6. Workspace, tenant, and trust model

Every record is scoped by:

```text
workspace_id
agent_id, nullable
session_id, nullable
skill_id, nullable
source_kind
source_trust
source_taint
```

Trust classes:

| Trust class | Examples | Can compile into skill? |
|---|---|---|
| `system_owned` | SkillKernel compiler templates, scanner rules, deterministic writer config | Yes |
| `operator_configured` | explicit operator policies, allowed paths, skill budget | Yes, if not secret |
| `autoskill_generated` | previously generated skill version that passed gates | Yes |
| `user_instruction` | user corrections and preferences | Only procedural, non-private, recurring instructions |
| `agent_output` | model reflections, plans, summaries | No direct compile; evidence only |
| `tool_output` | errors, logs, file reads, web results | No direct compile unless sanitized and operationally relevant |
| `external_content` | web pages, docs, repos, third-party files | No direct compile; tainted by default |
| `third_party_skill` | imported skills | Never auto-mutate; explicit adoption required |

Taint propagation rules:

1. Any raw external content is tainted.
2. Any memory derived from tainted content remains tainted unless a verifier declassifies a narrow operational fact.
3. Tainted content cannot enter `SKILL.md` as instruction text.
4. Tainted content can produce probes or negative tests.
5. User-specific private facts cannot compile into general skills.
6. Secrets and credentials are redacted before storage and embedding.

---

## 7. Plugin design

### 7.1 Responsibilities

The plugin is intentionally thin.

It performs:

- hook registration;
- event envelope construction;
- local redaction;
- taint labeling;
- batching;
- local spool writes;
- sidecar forwarding;
- status/control commands;
- active/archive root verification;
- optional fast runtime skill-context hint injection.

It does not perform:

- long LLM calls;
- candidate mining;
- scheduling;
- database maintenance;
- scanner evaluation beyond local hard denylists;
- arbitrary filesystem mutation;
- skill generation;
- skill improvement;
- skill archiving/promotion logic.

### 7.2 Hook surfaces to capture

Capture typed events where available:

| Event area | Purpose |
|---|---|
| session start/end | session boundaries, environment metadata |
| agent turn prepare/end | user intent, outcome, model, duration |
| model input/output hooks | optional raw content when explicitly permitted |
| tool before/after | tool parameters, errors, return class, latency |
| message received/sent | external delivery metadata and corrections |
| compaction/trajectory hooks | evidence preservation before context loss |
| install/update hooks | environment and dependency changes |
| gateway start/stop | sidecar health and root verification |

Raw conversation capture requires explicit configuration. If unavailable, SkillKernel still operates on tool events, summaries, corrections, and trajectory metadata but has lower recall.

### 7.3 Event envelope

All plugin events share this shape:

```json
{
  "event_id": "uuid",
  "schema_version": 1,
  "workspace_id": "uuid-or-hash",
  "agent_id": "string-or-null",
  "session_id": "string-or-null",
  "turn_id": "string-or-null",
  "event_type": "tool_call_end",
  "occurred_at": "2026-06-01T12:00:00Z",
  "source": "openclaw-plugin",
  "trust": "tool_output",
  "taint": ["runtime", "untrusted_output"],
  "redaction_state": "redacted",
  "payload_hash": "sha256",
  "payload": {},
  "plugin_version": "x.y.z",
  "openclaw_version": "observed-version-or-null"
}
```

### 7.4 Local spool

The plugin writes a local append-only spool when the sidecar is unavailable.

Requirements:

- bounded disk usage;
- event checksums;
- idempotency keys;
- retry with exponential backoff;
- oldest-safe compaction after retention threshold;
- no secrets in spool;
- no blocking OpenClaw if sidecar is down.

### 7.5 Runtime skill-context hint path

The plugin may register a prompt/context hook that asks the sidecar for a tiny per-turn context hint.

Constraints:

1. It is disabled unless `runtimeContextBroker.enabled = true`.
2. It has a strict timeout, e.g. 100–250 ms.
3. It uses only cached sidecar retrieval results or fast indexed lookup.
4. It never calls an LLM synchronously inside the hook.
5. It never injects raw memory, raw evidence, or untrusted external content.
6. It injects at most a small bounded block, for example 250–800 tokens.
7. It can fail silently without affecting the turn.
8. It logs whether the hint was requested, returned, injected, ignored, or associated with a later skill outcome.

Example injected block:

```text
SkillKernel routing hint:
- Most likely relevant skill: autoskill-pdf-table-repair.
- Use when: task involves extracting structured tables from PDFs after normal parse fails.
- Do not use when: task is only summarizing text or editing a PDF layout.
- Related prerequisite: autoskill-pdf-screenshot-inspection, only if visual table lines are missing.
```

This is not a replacement for OpenClaw skills. It is a routing aid to reduce shadowing and improve skill incorporation.

---

## 8. Sidecar design

### 8.1 Main services

The sidecar exposes:

| Service | Purpose |
|---|---|
| ingest API | receive plugin batches and spool replays |
| control API | status, mode changes, freeze/unfreeze, diagnostics |
| runtime broker API | fast skill-context hints |
| scheduler | durable periodic and event-triggered jobs |
| job worker pool | leased execution of analysis/mutation jobs |
| embedding worker | async embedding and re-embedding campaigns |
| retrieval service | hybrid search and exact reranking |
| mining service | candidate discovery and duplicate matching |
| generation service | structured plan generation |
| scanner service | static/semantic/capability checks |
| evaluator service | probe execution and regression checks |
| writer service | deterministic staged file writes |
| curation service | archive/promote/merge/prune decisions |
| drift service | contract validation and repair triggers |
| observability service | metrics, traces, audit integrity |

### 8.2 Sidecar API sketch

```http
POST /v1/ingest/events
POST /v1/ingest/replay
GET  /v1/health
GET  /v1/status
POST /v1/control/mode
POST /v1/control/freeze
POST /v1/control/unfreeze
POST /v1/runtime/context-hint
GET  /v1/skills
GET  /v1/skills/{skill_id}
GET  /v1/jobs
GET  /v1/audit/recent
```

All endpoints require localhost binding or mTLS/token authentication. The control API should be unavailable to remote callers by default.

### 8.3 Worker pools

Separate worker pools by risk and cost:

| Pool | Jobs |
|---|---|
| `ingest` | normalize events, extract evidence |
| `embedding` | embeddings, re-embedding, clustering |
| `retrieval` | index audits, duplicate matching |
| `analysis` | opportunity mining, attribution, curation |
| `llm_generation` | skill plans, repairs, compiler passes |
| `scanner` | static and semantic scanning |
| `evaluation` | probes, regression, canary analysis |
| `filesystem` | staged writes, archive, rollback |
| `maintenance` | vacuum hints, rollups, retention, audit checks |

No pool can call another recursively without creating a job. This avoids runaway loops.

---

## 9. Postgres design

### 9.1 One schema only

Use:

```sql
CREATE SCHEMA IF NOT EXISTS autoskill;
```

Do not create physical databases per skill. Do not create per-skill schemas in v1.

Per-skill schemas are acceptable only as a future enterprise isolation mode if a deployment proves it needs schema-level permission boundaries and can absorb the migration/operations cost. They are not the default and are not part of v1.

Why no per-skill schemas in v1:

1. Cross-skill retrieval is central.
2. Archived promotion needs global matching.
3. Curation is bank-level.
4. Skill shadowing requires sibling analysis.
5. Migrations across many schemas are fragile.
6. Connection pooling and permissions are simpler with one schema.
7. `skill_id` scoping plus indexes/partitions gives the needed isolation.
8. SkillIR revisions, broker logs, and graph edges need global analysis.
9. Per-skill schemas would increase DDL churn for little benefit in the normal product path.

### 9.2 Core identifiers

Use UUIDs for durable entities:

```text
workspace_id
session_id
turn_id
event_id
evidence_id
memory_id
skill_id
skill_version_id
candidate_id
probe_id
evaluation_id
job_id
audit_id
```

Use stable hashes for idempotency:

```text
source_event_hash
payload_hash
evidence_hash
file_content_hash
plan_hash
probe_hash
idempotency_key
```

### 9.3 Essential tables

Core tables:

```sql
CREATE TABLE autoskill.workspaces (
  workspace_id uuid PRIMARY KEY,
  external_key text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  config jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE autoskill.raw_events (
  event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL,
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  redaction_state text NOT NULL,
  payload_hash text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, payload_hash)
);

CREATE TABLE autoskill.evidence (
  evidence_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid,
  source_event_ids uuid[] NOT NULL,
  evidence_type text NOT NULL,
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  summary text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}',
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  utility_hint numeric,
  evidence_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, evidence_hash)
);

CREATE TABLE autoskill.skills (
  skill_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  slug text NOT NULL,
  name text NOT NULL,
  status text NOT NULL CHECK (status IN (
    'candidate','active','archived','quarantined','frozen','superseded','deleted_by_retention'
  )),
  owner text NOT NULL DEFAULT 'autoskill',
  active_version_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, slug)
);

CREATE TABLE autoskill.skill_versions (
  skill_version_id uuid PRIMARY KEY,
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  version_num integer NOT NULL,
  status text NOT NULL CHECK (status IN (
    'draft','staged','active','archived','rejected','rolled_back','quarantined'
  )),
  frontmatter jsonb NOT NULL,
  skill_ir jsonb NOT NULL,
  skill_ir_schema_version text NOT NULL DEFAULT 'skillir.v1',
  compiler_version text NOT NULL DEFAULT 'autoskill-compiler.v1',
  compiled_runtime_text text NOT NULL,
  manifest jsonb NOT NULL,
  source_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  parent_version_id uuid,
  created_by_job_id uuid,
  token_estimate integer NOT NULL DEFAULT 0,
  risk_score numeric NOT NULL DEFAULT 0,
  utility_score numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_id, version_num)
);

CREATE TABLE autoskill.skill_files (
  skill_file_id uuid PRIMARY KEY,
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  relative_path text NOT NULL,
  file_role text NOT NULL,
  content_hash text NOT NULL,
  byte_size integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, relative_path)
);

CREATE TABLE autoskill.skill_ir_revisions (
  skill_ir_revision_id uuid PRIMARY KEY,
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  ir_schema_version text NOT NULL DEFAULT 'skillir.v1',
  ir_hash text NOT NULL,
  ir jsonb NOT NULL,
  change_kind text NOT NULL CHECK (change_kind IN (
    'create','improve','compose','decompose','compile','repair','merge','split','archive','promote','rollback','drift_repair'
  )),
  source_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  source_memory_ids uuid[] NOT NULL DEFAULT '{}',
  llm_plan_hash text,
  compiler_version text NOT NULL DEFAULT 'autoskill-compiler.v1',
  created_by_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_id, ir_hash)
);
```

Scheduler tables:

```sql
CREATE TABLE autoskill.schedules (
  schedule_id uuid PRIMARY KEY,
  workspace_id uuid,
  job_type text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  schedule_kind text NOT NULL CHECK (schedule_kind IN ('interval','cron','event','manual')),
  schedule_spec jsonb NOT NULL,
  next_run_at timestamptz,
  last_run_at timestamptz,
  misfire_policy text NOT NULL DEFAULT 'coalesce',
  max_concurrency integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.jobs (
  job_id uuid PRIMARY KEY,
  workspace_id uuid,
  schedule_id uuid REFERENCES autoskill.schedules(schedule_id),
  job_type text NOT NULL,
  status text NOT NULL CHECK (status IN (
    'queued','leased','running','succeeded','failed','cancelled','dead','blocked'
  )),
  priority integer NOT NULL DEFAULT 100,
  run_after timestamptz NOT NULL DEFAULT now(),
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  lease_owner text,
  lease_expires_at timestamptz,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_type, idempotency_key)
);
```

Embeddings:

```sql
CREATE TABLE autoskill.embeddings (
  embedding_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  object_type text NOT NULL,
  object_id uuid NOT NULL,
  skill_id uuid,
  embedding_profile_id uuid NOT NULL REFERENCES autoskill.embedding_profiles(embedding_profile_id),
  embedding_provider text NOT NULL,
  embedding_model text NOT NULL,
  embedding_dim integer NOT NULL,
  distance_metric text NOT NULL DEFAULT 'cosine',
  embedding vector NOT NULL,
  text_hash text NOT NULL,
  source_provenance jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (vector_dims(embedding) = embedding_dim),
  UNIQUE (object_type, object_id, embedding_profile_id)
);
```

Use profile-specific partial expression indexes for active embedding profiles. Do not compare vectors across different embedding profiles. A model/provider/dimension change creates a new profile and a re-embedding campaign.

Skill components:

```sql
CREATE TABLE autoskill.skill_components (
  component_id uuid PRIMARY KEY,
  skill_id uuid NOT NULL,
  skill_version_id uuid,
  component_type text NOT NULL CHECK (component_type IN (
    'planning','functional','atomic','precondition','validator','failure_mode','disambiguator','contract','template','tool_template','runtime_guard','negative_example','quality_gate'
  )),
  title text NOT NULL,
  content text NOT NULL,
  applicability jsonb NOT NULL DEFAULT '{}',
  provenance jsonb NOT NULL DEFAULT '{}',
  confidence numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.skill_edges (
  edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  from_skill_id uuid NOT NULL,
  to_skill_id uuid NOT NULL,
  edge_type text NOT NULL CHECK (edge_type IN (
    'requires','conflicts_with','supersedes','similar_to','composes_with','composed_by','component_of','decomposes_to','specializes','generalizes','shadows','shadowed_by','adapter_for','validator_for','same_domain_as','depends_on_contract','violates_contract'
  )),
  confidence numeric NOT NULL DEFAULT 0,
  evidence jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (from_skill_id, to_skill_id, edge_type)
);
```

Retrieval/context logs:

```sql
CREATE TABLE autoskill.retrieval_events (
  retrieval_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  session_id text,
  turn_id text,
  query_hash text NOT NULL,
  query_features jsonb NOT NULL DEFAULT '{}',
  candidate_skill_ids uuid[] NOT NULL DEFAULT '{}',
  rendered_skill_ids uuid[] NOT NULL DEFAULT '{}',
  injected boolean NOT NULL DEFAULT false,
  budget_tokens integer NOT NULL DEFAULT 0,
  decision jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.skill_attributions (
  attribution_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid,
  skill_version_id uuid,
  session_id text,
  turn_id text,
  retrieval_event_id uuid,
  attribution_kind text NOT NULL CHECK (attribution_kind IN (
    'helped','hurt','ignored','missing','shadowed','misused','environment_failure','tool_failure','agent_exploration','unknown'
  )),
  confidence numeric NOT NULL DEFAULT 0,
  outcome jsonb NOT NULL DEFAULT '{}',
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Probes/evaluations:

```sql
CREATE TABLE autoskill.probes (
  probe_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid,
  probe_type text NOT NULL CHECK (probe_type IN (
    'target','regression','adversarial','drift','canary','shadowing','no_skill_control','intervention','memory_poisoning','quality_gate','contract'
  )),
  prompt text NOT NULL,
  setup jsonb NOT NULL DEFAULT '{}',
  verifier jsonb NOT NULL DEFAULT '{}',
  expected_outcome jsonb NOT NULL DEFAULT '{}',
  provenance jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.evaluations (
  evaluation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid,
  skill_version_id uuid,
  candidate_id uuid,
  eval_kind text NOT NULL,
  status text NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}',
  passed boolean NOT NULL DEFAULT false,
  regression_budget_used numeric NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.runtime_guard_templates (
  guard_template_id uuid PRIMARY KEY,
  guard_name text UNIQUE NOT NULL,
  guard_kind text NOT NULL CHECK (guard_kind IN (
    'preflight','verify_only','warn','block','context_hint','drift_check','capability_check','shadowing_hint'
  )),
  allowed_parameters jsonb NOT NULL DEFAULT '{}',
  renderer_version text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.memory_contracts (
  memory_contract_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  memory_kind text NOT NULL CHECK (memory_kind IN (
    'evidence','procedural_lesson','negative_control','environment_fact','user_correction','tool_capability','drift_signal'
  )),
  allowed_sources jsonb NOT NULL DEFAULT '{}',
  ttl_policy jsonb NOT NULL DEFAULT '{}',
  declassification_rules jsonb NOT NULL DEFAULT '{}',
  validator jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Audit:

```sql
CREATE TABLE autoskill.audit_log (
  audit_id uuid PRIMARY KEY,
  workspace_id uuid,
  actor text NOT NULL,
  action text NOT NULL,
  object_type text NOT NULL,
  object_id uuid,
  before_hash text,
  after_hash text,
  payload jsonb NOT NULL DEFAULT '{}',
  prev_audit_hash text,
  audit_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

### 9.4 Index strategy

Create indexes for:

- `(workspace_id, occurred_at)` on raw events;
- `(workspace_id, event_type, occurred_at)` on raw events;
- `(workspace_id, skill_id, evidence_type, created_at)` on evidence;
- `(workspace_id, status)` on skills;
- `(skill_id, version_num)` on skill versions;
- GIN indexes on important JSONB fields;
- GIN full-text indexes on searchable text;
- HNSW vector indexes on embeddings;
- B-tree filter indexes used before vector search;
- partial indexes for common statuses such as active skills and queued jobs.

Recommended vector indexes:

```sql
-- Created once for ordinary filtering.
CREATE INDEX embeddings_object_idx
ON autoskill.embeddings (workspace_id, object_type, skill_id, embedding_profile_id);

-- Created per active embedding profile/dimension. Example only; the profile UUID and dimension
-- are generated from autoskill.embedding_profiles.
CREATE INDEX embeddings_hnsw_profile_1536_cosine
ON autoskill.embeddings
USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE embedding_profile_id = '<profile_uuid>' AND embedding_dim = 1536;
```

For very high volume, partition first by time for raw events and jobs, then by object type/status for embeddings if needed. Only use hash partitioning by `skill_id` after query plans show a need.

### 9.8 Final control-plane tables

The following tables are part of the implementation target. They keep the broker, memory, executor profile, external-skill inventory, runtime artifacts, and marginal-utility measurements auditable.

```sql
CREATE TABLE autoskill.executor_profiles (
  executor_profile_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  profile_hash text NOT NULL,
  model_provider text,
  model_name text,
  agent_backend text,
  host_os text,
  sandbox_kind text,
  toolset jsonb NOT NULL DEFAULT '{}',
  binaries jsonb NOT NULL DEFAULT '{}',
  permissions jsonb NOT NULL DEFAULT '{}',
  token_budget integer,
  observed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, profile_hash)
);

CREATE TABLE autoskill.skill_profile_compatibility (
  skill_profile_compatibility_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  executor_profile_id uuid NOT NULL REFERENCES autoskill.executor_profiles(executor_profile_id),
  status text NOT NULL CHECK (status IN ('unknown','compatible','degraded','blocked','drifted')),
  evidence jsonb NOT NULL DEFAULT '{}',
  last_checked_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, executor_profile_id)
);

CREATE TABLE autoskill.broker_policy_versions (
  broker_policy_version_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  policy_name text NOT NULL,
  policy_config jsonb NOT NULL,
  renderer_config jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('draft','staged','active','rolled_back','rejected')),
  metrics jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz
);

CREATE TABLE autoskill.skill_marginal_value_trials (
  trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  trial_kind text NOT NULL CHECK (trial_kind IN ('no_skill','old_skill','new_skill','skill_hidden','skill_visible','sibling_bundle','broker_variant')),
  task_fingerprint text NOT NULL,
  outcome jsonb NOT NULL,
  score numeric,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.external_skill_inventory (
  external_skill_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  source text NOT NULL,
  root_path_hash text NOT NULL,
  slug text NOT NULL,
  name text,
  description text,
  frontmatter jsonb NOT NULL DEFAULT '{}',
  file_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('visible','missing','changed','ignored','quarantined')),
  risk_summary jsonb NOT NULL DEFAULT '{}',
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, source, root_path_hash, slug)
);

CREATE TABLE autoskill.memory_quarantine (
  quarantine_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  source_object_type text NOT NULL,
  source_object_id uuid NOT NULL,
  proposed_memory jsonb NOT NULL,
  taint jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('pending','approved','rejected','expired')),
  scanner_findings jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE autoskill.control_flow_events (
  control_flow_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  run_id text,
  source_kind text NOT NULL CHECK (source_kind IN ('memory','skill','broker','tool','user','system')),
  source_id uuid,
  influence_kind text NOT NULL CHECK (influence_kind IN ('retrieval','tool_selection','skill_selection','mutation','archive','promotion','rollback')),
  decision jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.runtime_artifacts (
  runtime_artifact_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_version_id uuid NOT NULL REFERENCES autoskill.skill_versions(skill_version_id),
  artifact_type text NOT NULL CHECK (artifact_type IN ('manifest','contract','template','script','reference','profile_rendering','probe_fixture')),
  relative_path text NOT NULL DEFAULT '',
  content_hash text NOT NULL,
  capabilities jsonb NOT NULL DEFAULT '{}',
  scanner_status text NOT NULL,
  test_status text NOT NULL DEFAULT 'not_applicable',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, artifact_type, relative_path)
);
```

These tables do not create per-skill schemas. They preserve global analysis while allowing strict logical ownership and profile-aware evaluation.

---


### 9.9 Final transaction, attribution, and revocation tables

These tables close the last implementation gap: autonomous updates must be rollback-complete across all derived state, not merely reversible at the file level.

```sql
CREATE TABLE autoskill.evolution_transactions (
  evolution_transaction_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  transaction_kind text NOT NULL CHECK (transaction_kind IN (
    'create_skill','improve_skill','compose_skill_cluster','decompose_skill','compile_skill','merge_skills','split_skill',
    'archive_skill','promote_skill','rollback_skill','freeze_skill','broker_policy_update',
    'probe_update','memory_declassification','support_artifact_update','retention_revocation'
  )),
  status text NOT NULL CHECK (status IN (
    'planned','staged','trial_running','trial_passed','committing','active','rolled_back','failed','quarantined','revoked'
  )),
  idempotency_key text NOT NULL,
  plan_hash text NOT NULL,
  actor text NOT NULL DEFAULT 'autoskill-sidecar',
  source_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  source_memory_ids uuid[] NOT NULL DEFAULT '{}',
  created_by_job_id uuid,
  started_at timestamptz NOT NULL DEFAULT now(),
  committed_at timestamptz,
  rolled_back_at timestamptz,
  rollback_of_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  policy_snapshot jsonb NOT NULL DEFAULT '{}',
  metrics jsonb NOT NULL DEFAULT '{}',
  UNIQUE (workspace_id, idempotency_key)
);

CREATE TABLE autoskill.evolution_transaction_items (
  transaction_item_id uuid PRIMARY KEY,
  evolution_transaction_id uuid NOT NULL REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  item_kind text NOT NULL CHECK (item_kind IN (
    'skill','skill_version','skill_ir_revision','skill_file','runtime_artifact','embedding',
    'memory','evidence','probe','evaluation','broker_policy','retrieval_cache','context_hint',
    'skill_edge','external_skill_inventory','audit_log','filesystem_path','compiled_bundle'
  )),
  item_id uuid,
  relative_path text,
  before_hash text,
  after_hash text,
  activation_state text NOT NULL CHECK (activation_state IN ('planned','staged','active','inactive','revoked','rolled_back')),
  rollback_action jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.provenance_edges (
  provenance_edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  from_object_type text NOT NULL,
  from_object_id uuid NOT NULL,
  to_object_type text NOT NULL,
  to_object_id uuid NOT NULL,
  edge_type text NOT NULL CHECK (edge_type IN (
    'derived_from','compiled_from','embedded_from','evaluated_by','rendered_by','influenced_by',
    'declassified_from','tainted_by','superseded_by','revoked_by','rolled_back_by'
  )),
  strength numeric NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (from_object_type, from_object_id, to_object_type, to_object_id, edge_type)
);

CREATE TABLE autoskill.evidence_maturity (
  evidence_maturity_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  object_type text NOT NULL,
  object_id uuid NOT NULL,
  maturity text NOT NULL CHECK (maturity IN (
    'observed','recurring','contrastive','intervention_validated','regression_validated',
    'canaried','production_verified','revoked'
  )),
  basis jsonb NOT NULL DEFAULT '{}',
  updated_by_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, object_type, object_id)
);

CREATE TABLE autoskill.action_attribution_checks (
  action_attribution_check_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  session_id text,
  turn_id text,
  tool_call_id text,
  action_kind text NOT NULL,
  risk_tier text NOT NULL CHECK (risk_tier IN ('low','medium','high','critical')),
  user_intent_hash text,
  contributing_skill_ids uuid[] NOT NULL DEFAULT '{}',
  contributing_memory_ids uuid[] NOT NULL DEFAULT '{}',
  contributing_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  broker_policy_version_id uuid REFERENCES autoskill.broker_policy_versions(broker_policy_version_id),
  counterfactual_kind text CHECK (counterfactual_kind IN ('none','skill_removed','memory_removed','untrusted_context_attenuated','broker_hint_removed','full_shadow_replay')),
  verdict text NOT NULL CHECK (verdict IN ('supported','unsupported','ambiguous','blocked','not_checked')),
  metrics jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.revocation_requests (
  revocation_request_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  request_kind text NOT NULL CHECK (request_kind IN ('rollback','retention_delete','privacy_delete','quarantine','scanner_revoke','operator_revoke')),
  root_object_type text NOT NULL,
  root_object_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','partial')),
  traversal_summary jsonb NOT NULL DEFAULT '{}',
  created_by_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE autoskill.body_index_documents (
  body_index_document_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid,
  skill_version_id uuid,
  document_kind text NOT NULL CHECK (document_kind IN (
    'frontmatter','description','skill_ir','compiled_runtime','support_manifest','support_summary',
    'contract','probe','negative_example','external_skill_body'
  )),
  text_hash text NOT NULL,
  text_content text NOT NULL,
  secret_scan_status text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, skill_version_id, document_kind, text_hash)
);
```

The `body_index_documents` table gives the retrieval and reranking layer body-level evidence without placing full bodies in the OpenClaw prompt. Embeddings should reference these rows through `autoskill.embeddings(object_type='body_index_document', object_id=body_index_document_id)`.

The `provenance_edges` and `revocation_requests` tables are required for rollback-complete behavior. Any object that contributes to a skill, memory, embedding, probe, compiled artifact, broker decision, or runtime hint must have enough provenance to be revoked or invalidated when the source is rolled back, quarantined, deleted by retention, or found malicious.

---


### 9.10 Topology-operation tables

These tables make create, improve, compose, and decompose first-class autonomous operations rather than informal patch types.

```sql
CREATE TABLE autoskill.skill_usage_windows (
  usage_window_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  session_id text,
  turn_id text,
  task_fingerprint text NOT NULL,
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  retrieved_skill_ids uuid[] NOT NULL DEFAULT '{}',
  rendered_skill_ids uuid[] NOT NULL DEFAULT '{}',
  inferred_used_skill_ids uuid[] NOT NULL DEFAULT '{}',
  explicit_invoked_skill_ids uuid[] NOT NULL DEFAULT '{}',
  ignored_skill_ids uuid[] NOT NULL DEFAULT '{}',
  tool_sequence jsonb NOT NULL DEFAULT '[]',
  skill_sequence jsonb NOT NULL DEFAULT '[]',
  outcome jsonb NOT NULL DEFAULT '{}',
  token_cost integer NOT NULL DEFAULT 0,
  tool_cost numeric NOT NULL DEFAULT 0,
  latency_ms integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.skill_co_usage_edges (
  co_usage_edge_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_a_id uuid NOT NULL,
  skill_b_id uuid NOT NULL,
  window_count integer NOT NULL DEFAULT 0,
  distinct_session_count integer NOT NULL DEFAULT 0,
  co_retrieved_count integer NOT NULL DEFAULT 0,
  co_rendered_count integer NOT NULL DEFAULT 0,
  co_used_count integer NOT NULL DEFAULT 0,
  ordered_transition_count integer NOT NULL DEFAULT 0,
  avg_outcome_score numeric,
  avg_token_cost integer,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  CHECK (skill_a_id <> skill_b_id),
  UNIQUE (workspace_id, skill_a_id, skill_b_id)
);

CREATE TABLE autoskill.skill_usage_clusters (
  skill_usage_cluster_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  cluster_kind text NOT NULL CHECK (cluster_kind IN (
    'missing_skill','improvement','composition','decomposition','shadowing','drift','archive','promotion'
  )),
  target_skill_id uuid,
  member_skill_ids uuid[] NOT NULL DEFAULT '{}',
  task_fingerprints text[] NOT NULL DEFAULT '{}',
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  centroid_embedding_id uuid,
  summary text NOT NULL,
  stats jsonb NOT NULL DEFAULT '{}',
  maturity text NOT NULL DEFAULT 'observed',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.topology_candidates (
  topology_candidate_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  candidate_kind text NOT NULL CHECK (candidate_kind IN (
    'create','improve','compose','decompose','archive','promote','merge','description_repair','validator_add','adapter_add','no_op'
  )),
  target_skill_id uuid,
  source_skill_ids uuid[] NOT NULL DEFAULT '{}',
  proposed_skill_ids uuid[] NOT NULL DEFAULT '{}',
  source_cluster_ids uuid[] NOT NULL DEFAULT '{}',
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  maturity text NOT NULL DEFAULT 'observed',
  llm_plan_hash text,
  deterministic_score numeric NOT NULL DEFAULT 0,
  score_breakdown jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN (
    'proposed','deduped','rejected','staged','evaluating','accepted','committed','rolled_back','quarantined'
  )),
  rejection_reason text,
  created_by_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.topology_operation_trials (
  topology_operation_trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  topology_candidate_id uuid NOT NULL REFERENCES autoskill.topology_candidates(topology_candidate_id),
  trial_kind text NOT NULL CHECK (trial_kind IN (
    'no_op','no_skill','current_skill','nearest_active','nearest_archived','old_version',
    'new_version','component_only','composed_skill','decomposed_successors','broker_only','sibling_bundle'
  )),
  executor_profile_id uuid REFERENCES autoskill.executor_profiles(executor_profile_id),
  task_fingerprint text NOT NULL,
  probe_ids uuid[] NOT NULL DEFAULT '{}',
  outcome jsonb NOT NULL DEFAULT '{}',
  passed boolean NOT NULL DEFAULT false,
  score numeric,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.topology_operation_results (
  topology_operation_result_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  topology_candidate_id uuid NOT NULL REFERENCES autoskill.topology_candidates(topology_candidate_id),
  evolution_transaction_id uuid REFERENCES autoskill.evolution_transactions(evolution_transaction_id),
  operation_kind text NOT NULL CHECK (operation_kind IN ('create','improve','compose','decompose','archive','promote','merge','repair','no_op')),
  affected_skill_ids uuid[] NOT NULL DEFAULT '{}',
  before_state jsonb NOT NULL DEFAULT '{}',
  after_state jsonb NOT NULL DEFAULT '{}',
  activation_decision text NOT NULL CHECK (activation_decision IN ('accepted','rejected','rolled_back','canarying','kept','frozen','no_op')),
  metrics jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Index requirements:

```sql
CREATE INDEX skill_usage_windows_workspace_task_idx
  ON autoskill.skill_usage_windows (workspace_id, task_fingerprint, created_at DESC);

CREATE INDEX skill_usage_windows_skill_arrays_gin
  ON autoskill.skill_usage_windows USING gin (inferred_used_skill_ids);

CREATE INDEX skill_co_usage_workspace_pair_idx
  ON autoskill.skill_co_usage_edges (workspace_id, skill_a_id, skill_b_id);

CREATE INDEX skill_usage_clusters_kind_maturity_idx
  ON autoskill.skill_usage_clusters (workspace_id, cluster_kind, maturity, updated_at DESC);

CREATE INDEX topology_candidates_kind_status_idx
  ON autoskill.topology_candidates (workspace_id, candidate_kind, status, deterministic_score DESC);
```

`skill_usage_windows` is the bridge from raw event telemetry to topology decisions. `skill_co_usage_edges` identifies repeated skill pairs and sequences. `skill_usage_clusters` groups evidence into operation-shaped clusters. `topology_candidates` stores possible actions before mutation. `topology_operation_trials` stores counterfactual and intervention comparisons. `topology_operation_results` closes the loop for future attribution and curator learning.



### 9.11 Context compiler and token-budget tables

Context management needs durable state because token pressure, ignored loads, false-positive routing, and semantic-loss regressions are lifecycle evidence.

```sql
CREATE TABLE autoskill.context_artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(id),
  artifact_type text NOT NULL,
  loadability_class text NOT NULL,
  relative_path text,
  section_key text,
  content_hash text NOT NULL,
  token_count integer NOT NULL,
  tokenizer_profile text NOT NULL,
  source_skillir_revision_id uuid,
  taint_state text NOT NULL DEFAULT 'clean',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.context_compile_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(id),
  candidate_id uuid,
  compiler_version text NOT NULL,
  model_assist_used boolean NOT NULL DEFAULT false,
  input_skillir_hash text NOT NULL,
  output_manifest_hash text NOT NULL,
  target_runtime_tokens integer,
  actual_runtime_tokens integer NOT NULL,
  compression_ratio numeric,
  semantic_equivalence_score numeric,
  status text NOT NULL,
  reject_reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.context_budget_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(id),
  event_type text NOT NULL,
  tokens_delta integer,
  marginal_success_delta numeric,
  false_positive_load_delta numeric,
  ignored_load_delta numeric,
  shadowing_delta numeric,
  decision text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.semantic_compression_trials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(id),
  source_revision_id uuid,
  candidate_revision_id uuid,
  source_tokens integer NOT NULL,
  candidate_tokens integer NOT NULL,
  preserved_requirements integer NOT NULL,
  lost_requirements integer NOT NULL,
  added_unsupported_requirements integer NOT NULL,
  equivalence_score numeric NOT NULL,
  target_probe_pass_rate numeric,
  regression_probe_pass_rate numeric,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Required indexes:

```sql
CREATE INDEX context_artifacts_skill_idx
  ON autoskill.context_artifacts(workspace_id, skill_id, skill_version_id, loadability_class);

CREATE INDEX context_budget_events_skill_time_idx
  ON autoskill.context_budget_events(workspace_id, skill_id, created_at DESC);

CREATE INDEX semantic_compression_trials_skill_idx
  ON autoskill.semantic_compression_trials(workspace_id, skill_id, status, created_at DESC);
```


## 10. pgvector and retrieval strategy

### 10.1 Retrieval is hybrid

Vector similarity alone is insufficient.

The retrieval pipeline is:

```text
query features
→ lexical candidates from PostgreSQL full-text search
→ vector candidates from pgvector HNSW
→ metadata candidates from skill status/capability/contracts
→ graph expansion for prerequisites/conflicts/shadow siblings
→ exact vector rerank on expanded candidate set
→ lexical/semantic/utility fusion
→ policy filters
→ context planner
→ set-aware renderer
→ logging
```

### 10.2 HNSW defaults

Use HNSW for online retrieval because it has better speed/recall tradeoff than IVFFlat in most dynamic settings.

Use exact search for:

- small filtered sets;
- evaluation/reranking;
- recall audits;
- high-risk promotion decisions;
- duplicate detection near final threshold.

Use IVFFlat only for large, relatively static partitions where build time and memory make HNSW unattractive.

### 10.3 Filtered ANN safeguards

Approximate indexes can lose recall when filters are applied after index scans. Use:

- B-tree filter indexes;
- HNSW iterative scans;
- higher `hnsw.ef_search` for important queries;
- partial HNSW indexes for common low-cardinality filters;
- partitioning for high-cardinality domains if needed;
- exact fallback when filtered candidate count is small;
- periodic ANN-vs-exact recall audits.

### 10.4 Embedding objects

Embed:

- evidence summaries;
- failure summaries;
- success summaries;
- contrastive observations;
- memory clusters;
- skill descriptions;
- compiled runtime text;
- skill components;
- probes;
- candidate summaries;
- archived skills.

Do not embed:

- secrets;
- raw credentials;
- unredacted user data;
- full raw logs;
- arbitrary external content without redaction and taint labeling.

### 10.5 Retrieval calibration metrics

Track:

- retrieved skills;
- rendered/injected skills;
- skills selected by the agent;
- skills ignored by the agent;
- useful retrieved skills;
- harmful retrieved skills;
- missing skills discovered later;
- shadowing events;
- no-skill successes;
- no-skill failures;
- token/latency cost of context hint;
- downstream outcome.

These logs form the dataset for future learned routing/curation, but v1 uses deterministic policies plus calibrated thresholds.

---

## 11. Runtime skill-context broker, context compiler, and token budget governor

The active skill library is not enough. Large skill sets can degrade performance through context overhead, wrong-skill selection, skill shadowing, and distractor effects. SkillKernel must optimize the runtime skill context as aggressively as it optimizes skill content.

The broker decides what may be exposed; the context compiler decides how compactly and safely it is expressed; the token budget governor decides whether the marginal value justifies the context cost.

### 11.1 Broker goals

The broker decides:

1. which active skills are likely relevant;
2. whether the task needs zero, one, or multiple skills;
3. whether prerequisites should be included;
4. whether sibling skills need disambiguation;
5. whether an archived skill should be promoted before future runs;
6. how to phrase a small routing hint;
7. when to inject nothing.

### 11.2 Broker inputs

Inputs:

- current user turn summary or redacted message;
- recent tool failure/error class;
- active skill metadata;
- active skill components;
- skill graph edges;
- archived skill nearest neighbors;
- skill utility/cost/risk scores;
- recent retrieval and shadowing logs;
- model/context budget;
- workspace policy.

### 11.3 Broker output

Output:

```json
{
  "decision": "inject_hint|no_hint",
  "selected_skill_ids": ["uuid"],
  "prerequisite_skill_ids": ["uuid"],
  "negative_skill_ids": ["uuid"],
  "archive_promotion_candidates": ["uuid"],
  "token_budget": 500,
  "rendered_hint": "...",
  "confidence": 0.82,
  "reason_codes": ["lexical_match", "utility_positive", "sibling_disambiguation"]
}
```

### 11.4 Planner

The planner scores each candidate on:

- query semantic similarity;
- lexical overlap;
- metadata match;
- observed utility;
- recent success/failure trend;
- contract validity;
- drift risk;
- token cost;
- shadowing risk;
- prerequisite completeness;
- status: active/archived/frozen/quarantined.

Selection formula should be explicit and inspectable in v1:

```text
score =
  + semantic_weight * semantic_score
  + lexical_weight * lexical_score
  + utility_weight * utility_score
  + recency_weight * recency_score
  + contract_weight * contract_validity
  + prerequisite_weight * dependency_completeness
  - risk_weight * risk_score
  - drift_weight * drift_risk
  - token_weight * token_cost
  - shadow_weight * shadowing_risk
```

Do not use a learned planner in v1. Log enough data to train one later.

### 11.5 Renderer

The renderer creates short hints and frontmatter descriptions. It is set-aware: it should mention sibling boundaries when confusion is likely.

Description format:

```text
<capability>; use for <specific trigger>; not for <sibling boundary>.
```

Runtime hint format:

```text
SkillKernel routing hint:
- Use <skill> when <conditions>.
- Verify <checks>.
- Do not use <confusable-skill> when <boundary>.
```

The renderer cannot include raw untrusted content. It cannot include hidden comments. It cannot mention secrets. It cannot add new behavioral policy beyond known skill contracts.

### 11.6 Shadowing detection

Shadowing event definition:

```text
A task had a known-helpful or likely-helpful skill A, but skill B was retrieved/injected/used instead, and the outcome was worse or required correction.
```

Signals:

- wrong skill explicitly invoked;
- agent used a skill whose `DO NOT USE WHEN` matched the task;
- a skill appeared in context and a better skill was ignored;
- user corrected the selected procedure;
- tool failure matches another skill’s known fix;
- archived skill nearest neighbor had higher expected utility.

Actions:

- improve description of A or B;
- add disambiguator component;
- add `DO NOT USE WHEN` boundary;
- lower B’s routing score;
- create edge `B shadows A`;
- add shadowing probe;
- merge/split skills if boundaries are unstable;
- archive B if it repeatedly shadows and underperforms.

### 11.7 Broker policy versioning

The runtime broker is not a fixed helper function. It is a policy artifact with its own lifecycle:

```text
draft → staged → replay-evaluated → active → canaried → kept | rolled_back
```

A broker policy version includes candidate limits, graph expansion depth, conflict/shadow penalties, token budgets, renderer rules, external-skill handling, risk penalties, and fallback behavior. A new policy cannot activate unless historical replay shows no increase in harmful, ignored, shadowed, over-budget, or missing-skill outcomes beyond configured thresholds.

### 11.8 Set-aware context rendering

The renderer must account for co-injected skills. If two skills have overlapping names, applicability, or tool scopes, the broker emits disambiguation hints or suppresses one skill. The rendered context must state why each skill is present and when not to use it.

### 11.9 External-skill awareness

The broker includes external skill inventory in collision and shadowing analysis but never routes automatic mutations into external skill directories. If an external skill is consistently superior, SkillKernel may recommend explicit import or keep SkillKernel-owned duplicates archived.

### 11.10 Context-bundle security scan

Before broker hints or skill bundles are exposed, scan the composed context, not just individual skills. Reject bundles containing conflicting tool directives, hidden instruction channels, suspicious sibling interactions, or combined exfiltration paths.


### 11.11 Context-loadability classes

Every artifact in every SkillKernel-owned skill directory must be classified before activation:

| Class | Meaning | Runtime handling |
|---|---|---|
| `runtime_always_metadata` | `name`, `description`, and OpenClaw-visible metadata. | Always budgeted; strictest wording and character limits. |
| `runtime_on_skill_load` | Main `SKILL.md` body. | Terse typed interface; mandatory semantic-density gates. |
| `agent_may_read` | Reference file the agent may open during skill execution. | Must be compressed, scanned, linked from SkillIR, and token-accounted when read. |
| `broker_excerpt_only` | Material the broker may summarize or excerpt into context. | Broker renders only a bounded excerpt; raw file is not directly loaded. |
| `script_only` | Executed helper script, not prompt text. | Capability-scanned; never used as prompt content except path/contract references. |
| `probe_only` | Evaluation fixture or test case. | Not visible in normal runtime. |
| `operator_only` | Audit/debug/human review notes. | Never loaded into agent context. |
| `never_loaded` | Raw evidence, examples, transcripts, logs. | Stored in Postgres; not placed in skill directory unless needed for offline evaluation. |

Default policy: generated skill directories should contain only `SKILL.md`, minimal verified support scripts, minimal reference files that are actually used, and manifests. No README, changelog, rationale, history, raw examples, or duplicated notes should exist inside a skill directory unless the context compiler classifies them as operationally necessary.

### 11.12 Context compiler responsibilities

The context compiler owns every context-visible artifact:

```text
SkillIR component selection
→ taint/privacy exclusion
→ context-loadability classification
→ semantic density rewrite
→ typed-section rendering
→ description minimization
→ support-reference minimization
→ token counting by target tokenizer profile
→ semantic-equivalence probes
→ scanner pass
→ retrieval/shadowing simulation
→ marginal-value-per-token calculation
→ artifact hash + manifest
```

The compiler must reject text that is correct but verbose. It must also reject text that is short but semantically lossy.

### 11.13 Token budget governor

The token budget governor applies both local and global budgets:

| Budget | Default v1 policy |
|---|---|
| Frontmatter description | Prefer <= 160 characters; hard fail above configured max unless explicit exception. |
| `SKILL.md` body target | Prefer <= 350 tokens. |
| `SKILL.md` body hard max | 900 tokens without explicit split/decompose exception. |
| Broker hint | <= configured `runtime_context_broker.max_tokens`; default 600. |
| Support reference excerpt | <= 120 tokens per excerpt unless a probe proves more is needed. |
| Active-bank metadata overhead | Enforced through active-skill budget and description length controls. |
| Context bundle | Broker must leave room for user task, tool results, current reasoning, and safety instructions. |

Budget failures trigger one of these deterministic actions:

```text
compress_again | split_support_file | decompose_skill | tighten_description | broker_abstain | archive_low_value_skill | reject_change
```

### 11.14 Semantic-density metric

For every compiled artifact, store:

```text
runtime_tokens
frontmatter_tokens
body_tokens
support_excerpt_tokens
compression_ratio_from_previous
compression_ratio_from_skillir_notes
required_field_coverage
semantic_equivalence_score
probe_pass_rate_per_1k_tokens
marginal_success_per_1k_tokens
false_positive_load_cost
ignored_skill_token_waste
shadowing_cost
```

A lower token count is not enough. The accepted artifact must preserve operational semantics and improve marginal value per token.

### 11.15 Context regression definitions

A candidate version has a context regression if it causes any of these beyond policy threshold:

- higher total runtime tokens without measured utility gain;
- lower retrieval precision due to broader description wording;
- higher false-positive load rate;
- higher ignored-skill rate;
- higher sibling shadowing risk;
- lower semantic-equivalence score;
- loss of required verification/failure information;
- more agent turns spent rereading or rediscovering steps;
- worse composed-vs-component token tradeoff;
- worse decomposed-vs-original routing tradeoff.

Context regression is sufficient to reject, roll back, or decompose a skill even if some target probes pass.

### 11.16 AI-facing style rules

Runtime text must prefer compact command language over prose:

```text
Use: imperative fragments, explicit conditions, typed variables, short failure branches.
Avoid: background, justification, narrative, human explanations, repeated synonyms, apologies, speculation.
```

Accepted pattern:

```text
WHEN: task requires X and input has Y.
INPUTS: y_path, target_format.
DO: validate y_path -> run tool Z -> inspect output -> emit result.
VERIFY: output exists; schema valid; no secret tokens.
FAIL: stop; report missing precondition or tool error.
NEVER: run network fetch; overwrite user files; use for sibling case Q.
```

Rejected pattern:

```text
This skill is designed to help the agent work with X. It is important to first understand...
```

### 11.17 Support-file progressive disclosure policy

Support files are permitted only when they reduce net context cost or improve reliability. The compiler must decide whether a detail belongs in:

```text
SKILL.md compact body
broker hint
support reference file
support script
Postgres-only evidence
probe fixture
operator-only audit record
```

Rules:

1. If the agent always needs it, compress it into `SKILL.md`.
2. If the agent rarely needs it but can decide when to read it, place a terse reference in `SKILL.md` and classify the file as `agent_may_read`.
3. If the agent should not inspect it directly, classify it as `broker_excerpt_only`, `script_only`, `probe_only`, `operator_only`, or `never_loaded`.
4. If it is rationale, history, raw evidence, or improvement notes, keep it in Postgres.
5. If it is long and partially useful, split into anchored sections with compact headings so the agent can read only the relevant part.


---

## 12. Evidence and memory pipeline

### 12.1 Raw events are immutable

Raw events are append-only after redaction. Derived records point back to raw event IDs.

No job can mutate raw event payloads except retention/deletion jobs governed by policy. Deletion requires audit entries.

### 12.2 Evidence extraction

Evidence types:

| Evidence type | Meaning |
|---|---|
| `explicit_user_correction` | user says how future behavior should change |
| `recurring_workflow_success` | same workflow succeeds repeatedly |
| `recurring_workflow_failure` | same failure recurs |
| `tool_error_pattern` | tool failure pattern with fix |
| `environment_drift_signal` | API/package/path/schema/service changed |
| `skill_helped` | attribution indicates skill improved outcome |
| `skill_hurt` | attribution indicates skill degraded outcome |
| `skill_shadowed` | wrong skill displaced better skill |
| `missing_skill` | task needed a skill absent from active library |
| `archived_skill_needed` | archived skill matched recent need |
| `user_requested_skill` | user directly asked to save/create/update a skill |

### 12.3 Memory levels

Use adaptive compression:

| Level | Object | Stored where | Loaded into prompt? |
|---|---|---|---|
| L0 | raw event/trace | Postgres raw events | never directly |
| L1 | episodic evidence | `evidence` | rarely, only for analysis jobs |
| L2 | procedural memory/component | `skill_components`, `memory_clusters` | compiled only when stable |
| L3 | declarative rule/validator | `skill_components`, probes | compiled only if broadly useful |

The system should not force all experience into a skill. Some evidence remains evidence. Some becomes memory. Some becomes a validator. Some becomes a skill. Some becomes a negative example.

### 12.4 Memory promotion gates

A memory candidate is promoted only if:

- redacted;
- provenance is known;
- not secret or private fact;
- taint is acceptable for the target use;
- contradiction check passes;
- recurrence or severity threshold passes;
- projected utility exceeds cost;
- no existing memory/skill already covers it.

### 12.5 Memory poisoning controls

Controls:

- taint all external content;
- store provenance and source trust;
- keep direct instructions from external content out of compiled skills;
- use external content only as evidence of environment facts after verification;
- require user/operator-origin for preference-like rules;
- periodically audit memories for suspicious imperative language;
- suppress memories that later produce harmful retrieval outcomes;
- version derived memories and support rollback.


### 12.6 Memory contracts and poisoning resistance

Persistent memory is a benefit and an attack surface. SkillKernel therefore treats memory writes as governed transformations, not as append-only notes.

Rules:

- classify every memory as one of: `evidence`, `procedural_lesson`, `negative_control`, `environment_fact`, `user_correction`, `tool_capability`, or `drift_signal`;
- require provenance, trust score, taint, source event IDs, and TTL policy;
- store external content as evidence only, never as direct runtime instruction;
- require verifier-backed declassification before evidence can influence SkillIR;
- maintain negative-control memories that describe known bad patterns and poisoned examples;
- compare new memories against related memories for contradiction, suspicious imperative phrasing, and delayed-trigger patterns;
- suppress or quarantine memories that correlate with harmful retrieval outcomes;
- keep memory rollback independent from skill rollback.

The memory pipeline must prefer false negatives over persistent compromise. A useful memory can be rediscovered; a poisoned memory can compromise future autonomous changes.

### 12.7 Memory quarantine

Derived memories that can influence future behavior enter quarantine when they include:

- imperative or policy-like language;
- tool-selection claims;
- external instructions;
- credentials, secrets, private user facts, or sensitive identifiers;
- low-provenance summaries;
- content from untrusted webpages, files, tool outputs, or user-controlled artifacts;
- claims that modify skill applicability, risk, or execution order.

Quarantined memory is not embedded for runtime retrieval and cannot become skill text. Approval requires provenance checks, scanner pass, and a deterministic transformation into a non-imperative evidence record.

### 12.8 Control-flow integrity logging

Whenever memory, skills, broker policy, or external-skill inventory materially influences retrieval, mutation, tool selection, archive, promotion, or rollback, SkillKernel writes a `control_flow_events` row. This supports audits and poisoning detection.

---


## 12A. Rich data contract for autonomous topology operations

The success of SkillKernel depends on two coupled systems:

```text
A. collect rich, trustworthy, operation-relevant evidence
B. use that evidence to choose the correct autonomous operation
```

If A is weak, the system will make plausible but wrong skill changes. If B is weak, the system will store useful data without improving the skill bank. Both are implementation requirements, not optional analytics.

### 12A.1 Required per-turn observability

For each user turn and agent turn, capture or derive the following when available:

| Field | Why it matters |
|---|---|
| task fingerprint | Groups repeated workflows and supports create/compose/decompose candidates. |
| user intent summary | Distinguishes user-supported actions from skill/memory-induced actions. |
| active skill inventory snapshot | Determines what the agent could have used. |
| broker candidates | Shows what the sidecar thought was relevant. |
| broker selected/rendered skills | Measures runtime context construction. |
| OpenClaw-visible skills | Captures what the model actually saw. |
| explicitly invoked skill | Supports direct user demand and routing analysis. |
| inferred skill use | Supports attribution when no explicit invocation exists. |
| ignored visible skills | Identifies poor retrieval, poor descriptions, or irrelevant injection. |
| co-retrieved skill set | Supports composition and shadowing analysis. |
| co-injected skill set | Measures context-bundle effects. |
| co-used skill set | Strong composition signal. |
| skill sequence | Identifies recurring workflows and prerequisite chains. |
| tool-call sequence | Extracts procedural structure and failure locations. |
| tool errors and retries | Drives improvement, drift repair, and validators. |
| user corrections | Highest-quality improvement/create evidence. |
| verification checks | Supports skill usefulness and regression probes. |
| final outcome | Needed for utility and attribution. |
| token/tool/time cost | Needed for compose/decompose and curation. |
| executor profile | Skill behavior depends on model/harness/tool/sandbox context. |
| taint/provenance of evidence | Prevents external content from becoming durable instructions. |

### 12A.2 Data needed for creation

Creation needs evidence of missing durable procedure:

- repeated manual workflow;
- repeated user instruction or correction;
- repeated tool sequence with stable outcome;
- repeated failure fixed by the same intervention;
- high-cost task with reusable steps;
- archived skill match that is stale, missing, or not active;
- no active skill/component adequately covers the task.

Creation does **not** require co-use of existing skills. It requires a missing capability/workflow whose expected future value exceeds maintenance, context, and risk cost.

### 12A.3 Data needed for improvement

Improvement needs evidence tied to a target skill version:

- skill was retrieved/visible/used;
- outcome improved, degraded, or required correction;
- exact failure, omission, or inefficiency is known;
- a reproducible probe can be generated;
- patch can be localized to SkillIR, description, validator, contract, support artifact, or broker boundary;
- regression set exists for current behavior.

A model saying “this could be better” is not evidence. The LLM may propose a patch; deterministic gates decide whether it is accepted.

### 12A.4 Data needed for composition

Composition needs evidence that several smaller skills form a recurring higher-order workflow:

- skills are co-retrieved, co-injected, or co-used repeatedly;
- co-use occurs across distinct sessions or task instances;
- the sequence/order is stable enough to compile;
- users describe the combined task as a single goal;
- combined workflow has repeated cost, error, or verification overhead;
- component skills have compatible contracts and capabilities;
- a composed workflow would reduce tokens, steps, latency, errors, or ambiguity;
- no existing composed or archived skill already covers the workflow.

The composed skill should normally be an orchestration skill, not a pasted concatenation. Component skills can remain active if they retain standalone utility.

### 12A.5 Data needed for decomposition

Decomposition needs evidence that a broad skill is too large or semantically overloaded:

- only one section/component is usually relevant;
- different usage clusters rarely overlap;
- the skill is retrieved for wrong tasks because its description is broad;
- token cost is high relative to used content;
- parts of the skill drift or fail independently;
- one component causes regressions while others remain useful;
- sibling skills are shadowed by the broad skill;
- broker suppression/disambiguation repeatedly tries to route around the broad skill.

Decomposition creates successor skills with provenance and usually archives/supersedes the original after canary success.

### 12A.6 Evidence maturity ladder for topology operations

Use the same maturity ladder for all operation classes:

```text
observed
→ recurring
→ contrastive
→ intervention_validated
→ regression_validated
→ canaried
→ production_verified
→ revoked
```

Minimum activation maturity:

| Operation | Minimum maturity for activation |
|---|---|
| create | intervention_validated + regression_validated |
| improve | intervention_validated + regression_validated |
| compose | intervention_validated + regression_validated + shadowing check |
| decompose | intervention_validated + regression_validated + rollback plan |
| archive | recurring negative/low-utility evidence or supersession proof |
| promote | recurring demand + drift/scanner/eval pass |

### 12A.7 Operation-decision loop

The operation planner runs this deterministic outer loop:

```text
collect evidence windows
→ build task/evidence clusters
→ search active skills, archived skills, components, and rejected candidates
→ produce operation candidates: create, improve, compose, decompose, supporting actions
→ reject duplicates and low-maturity candidates
→ ask LLM only for semantic induction/planning on high-signal candidates
→ normalize to structured operation plans
→ score with deterministic policy
→ run intervention/counterfactual probes
→ choose operation or no-op
→ apply only through an evolution transaction
```

The default decision bias is:

```text
repair/improve existing skill
→ promote archived skill
→ add disambiguator/description fix
→ compose/decompose if topology evidence is strong
→ create new skill
→ no-op
```

This bias prevents append-only growth while still allowing genuinely missing skills to be created.


## 13. Skill representation

### 13.1 Source of truth: SkillIR, not `SKILL.md`

The internal source of truth is **SkillIR**: a typed, versioned JSON object stored in Postgres. `SKILL.md` is the OpenClaw-facing compiled artifact generated from SkillIR.

This design prevents free-form Markdown from becoming an unstructured control plane. It also enables deterministic validation, diffing, migration, compression, evaluation, rendering, rollback, and platform-specific output generation.

### 13.2 SkillIR v1 shape

SkillIR v1 must contain these fields:

```json
{
  "schema": "skillir.v1",
  "identity": {
    "name": "autoskill-example",
    "slug": "autoskill-example",
    "description": "Short routing trigger with boundary",
    "aliases": [],
    "domain_tags": []
  },
  "applicability": {
    "when": [],
    "do_not_use_when": [],
    "confusable_with": [],
    "shadowing_boundaries": []
  },
  "interface": {
    "inputs": [],
    "preconditions": [],
    "outputs": [],
    "tool_templates": []
  },
  "procedure": {
    "steps": [],
    "runtime_guards": [],
    "failure_handling": [],
    "never": []
  },
  "verification": {
    "checks": [],
    "deterministic_verifiers": [],
    "expected_artifacts": []
  },
  "contracts": {
    "environment": [],
    "dependencies": [],
    "capabilities": [],
    "permissions": []
  },
  "relations": {
    "requires": [],
    "conflicts_with": [],
    "supersedes": [],
    "composes_with": [],
    "composed_by": [],
    "component_of": [],
    "decomposes_to": [],
    "specializes": [],
    "generalizes": [],
    "adapter_for": [],
    "validator_for": []
  },
  "evidence": {
    "source_evidence_ids": [],
    "source_memory_ids": [],
    "negative_controls": [],
    "confidence": 0.0
  },
  "risk": {
    "capability_risk": 0.0,
    "privacy_risk": 0.0,
    "shadowing_risk": 0.0,
    "drift_risk": 0.0,
    "taint": []
  },
  "compiler": {
    "target": "openclaw-skill-md",
    "compiler_version": "autoskill-compiler.v1",
    "token_budget": 900
  }
}
```

### 13.3 Compiled OpenClaw `SKILL.md` format

The renderer emits a normal OpenClaw skill directory containing `SKILL.md` and any allowed support files. The `SKILL.md` must follow this canonical structure:

```markdown
---
name: autoskill-example
description: Short routing trigger; use for specific recurring workflow; not for sibling boundary.
version: 1.0.0
metadata:
  autoskill: true
  skill_id: "..."
  skill_version_id: "..."
  skill_ir_hash: "..."
  compiler_version: "autoskill-compiler.v1"
  capabilities:
    - "filesystem-read"
  generated_at: "2026-06-01T00:00:00Z"
---

# autoskill-example

## WHEN
Use when all are true:
- ...

## INPUTS
Expected inputs:
- ...

## PRECONDITIONS
Before applying:
- ...

## DO
1. ...
2. ...

## TOOL TEMPLATES
Use only when matching the requested task:
- ...

## VERIFY
- ...

## FAIL
If verification fails:
- ...

## DO NOT USE WHEN
- ...

## NEVER
- Never ...
```

### 13.4 Runtime text rules

Hard invariant: runtime text is AI-facing compiled code-like instruction, not human documentation. Prefer dense operational fragments over readable explanations. A sentence is allowed only when it improves trigger precision, action fidelity, verification, safety, or failure recovery.

Runtime text must be:

- model-facing;
- terse;
- imperative;
- scoped;
- typed enough that the model does not have to infer inputs or invocation syntax;
- testable;
- dependency-aware;
- sibling-disambiguated when shadowing risk exists;
- free of secrets;
- free of hidden comments;
- free of invisible Unicode control tricks;
- free of raw transcript language;
- free of speculative rationale;
- free of unverified external instructions;
- under the configured token budget.

### 13.5 Component model

Internally, a skill can have components:

| Component | Purpose |
|---|---|
| planning | high-level order of operations |
| functional | reusable tool/API/file procedure |
| atomic | small action or constraint |
| precondition | condition that must hold before use |
| validator | deterministic check or expected condition |
| failure_mode | recurring pitfall and correction |
| disambiguator | boundary against confusable skills |
| contract | environment/API/tool/package assumption |
| template | concrete command/path/action template |
| tool_template | parameterized safe tool invocation shape |
| runtime_guard | reference to a preapproved deterministic guard template |
| negative_example | concise non-use example |
| quality_gate | evaluation or compiler acceptance rule |

The compiler chooses which components enter `SKILL.md`; it may keep other components only in Postgres for evaluation, retrieval, drift monitoring, or curation.

### 13.6 Runtime guard templates

Runtime guards are **not arbitrary generated code**. They are deterministic templates selected by SkillIR and parameterized through allowlisted fields.

Allowed guard categories:

| Guard | Purpose |
|---|---|
| preflight | Check required files, tools, env vars, or permissions before skill use. |
| verify_only | Run or describe a deterministic verification after the procedure. |
| warn | Emit a compact caution when risk is bounded but nonzero. |
| block | Suppress skill use when a hard condition fails. |
| context_hint | Add a short broker-rendered hint without exposing full skill text. |
| drift_check | Check environment contract freshness. |
| capability_check | Confirm declared capabilities match actual requested actions. |
| shadowing_hint | Disambiguate against sibling skills. |

LLMs may propose guard-template selection. They cannot author executable guard logic, filesystem paths, shell commands, SQL, or capability expansion.

### 13.7 Description management

Frontmatter `description` is a routing artifact, not a summary paragraph. It must be optimized and versioned.

Description should contain:

1. compact capability phrase;
2. primary trigger condition;
3. strongest non-use boundary when shadowing risk exists.

Example:

```yaml
description: Convert OpenClaw transcript patterns into evaluated SkillKernel candidates; not for runtime skill selection.
```

Description changes require retrieval evaluation because they can improve or degrade skill selection.

---


### 13.8 SkillGraphIR for composed and decomposed workflows

SkillGraphIR is required when a candidate operation involves multiple component skills, ordered subprocedures, state transitions, fallback branches, verifier nodes, or localized repair. It is not rendered wholesale into agent context. It is an internal graph contract used by the broker, evaluator, compiler, and rollback system.

Minimum shape:

```json
{
  "skill_graph_ir_version": "1.0",
  "graph_kind": "composition | decomposition | broker_plan | repair_plan",
  "root_skill_id": "uuid-or-null",
  "nodes": [
    {
      "node_id": "n1",
      "skill_id": "uuid-or-null",
      "skill_version_id": "uuid-or-null",
      "node_kind": "skill | verifier | adapter | decision | fallback | terminal",
      "preconditions": [],
      "inputs": [],
      "outputs": [],
      "effects": [],
      "state_delta": [],
      "side_effects": [],
      "verify": [],
      "failure_modes": []
    }
  ],
  "edges": [
    {
      "from": "n1",
      "to": "n2",
      "edge_kind": "order | data | requires | conflicts | fallback | repair_scope | supersedes",
      "condition": "compact condition",
      "evidence_ids": []
    }
  ],
  "global_invariants": [],
  "unsafe_when": [],
  "repair_policy": "none | local_node | local_subgraph | rollback_candidate",
  "compiler_hints": {
    "runtime_summary_budget_tokens": 120,
    "prefer_component_refs": true,
    "omit_internal_rationale": true
  }
}
```

Rules:

```text
1. Graph must be acyclic unless a loop has a deterministic bounded iteration contract.
2. Every nonterminal node has explicit success and failure exits.
3. Component effects must satisfy downstream preconditions.
4. Conflicting state deltas block composition unless an adapter/verifier resolves them.
5. Every composed workflow has component-only and composed-skill trials.
6. Every decomposition preserves effect coverage for the validated cluster it claims.
7. Broker context receives only the minimal graph summary needed for execution.
```

### 13.9 Skill granularity classes

Each SkillIR revision declares a granularity class. This supports composition, decomposition, broker abstention, and active-bank budgeting.

| Class | Meaning | Typical runtime treatment |
|---|---|---|
| `atomic` | one narrow operation or check | loaded only for precise matches or as component |
| `functional` | reusable subroutine with inputs/outputs | loaded when task directly matches or as workflow node |
| `workflow` | ordered multi-step procedure | loaded for user-level task family |
| `orchestration` | chooses/coordinates component skills | loaded only when full workflow is needed |
| `adapter` | normalizes external tool/API/file behavior | usually support artifact or verifier-bound context |
| `validator` | checks output or environment contract | may be support artifact, probe, or compact VERIFY section |

Granularity is not cosmetic. It participates in retrieval scoring, active-bank budgets, shadowing analysis, compose/decompose proposals, and token-budget decisions.

## 14. Skill lifecycle state machine

Skill statuses:

```text
candidate
active
archived
quarantined
frozen
superseded
deleted_by_retention
```

Version statuses:

```text
draft
staged
active
archived
rejected
rolled_back
quarantined
```

Transitions:

```text
candidate → staged → active
candidate → rejected
candidate → quarantined
active → archived
active → frozen
active → superseded
active vN → active vN+1
active vN+1 → rolled_back, active vN restored
archived → staged → active
frozen → staged repair → active
frozen → archived
```

Transition requirements:

| Transition | Required gates |
|---|---|
| candidate → staged | evidence threshold, duplicate check, scanner pass |
| staged → active | target eval pass, regression eval pass, manifest complete |
| active → archived | utility/cost threshold or drift/risk policy |
| archived → active | recurrence, archived match, scanner re-pass, drift check, eval pass |
| active → frozen | repeated canary failure, scanner discovery, operator command, critical drift |
| active → superseded | replacement passes combined probes and migration plan |
| rollback | previous version snapshot exists and manifest verifies |

---


## 14A. Autonomous skill topology operations

This section is the core product behavior. SkillKernel continuously optimizes the skill library topology through four primary autonomous operations:

```text
create
improve
compose
decompose
```

Supporting operations include compile/recompile, repair, add validator, add adapter, add disambiguator, archive, promote, merge duplicates, split support files, freeze, rollback, and no-op. Supporting operations exist to make the four primary operations safer and more effective.

### 14A.1 Shared invariants for all topology operations

Every topology operation must satisfy these invariants:

1. It is represented as an `evolution_transaction`.
2. It cites source evidence and maturity state.
3. It has a structured LLM proposal only where semantic reasoning is required.
4. It is normalized into deterministic SkillIR or lifecycle changes.
5. It passes scanner, policy, capability, token, and taint gates.
6. It has target probes and regression probes.
7. It has broker/routing replay when it changes description, relationships, visibility, composition, decomposition, or active status.
8. It can be rolled back across files, DB state, embeddings, broker caches, probes, context hints, and derived memories.
9. It writes only SkillKernel-owned active/archive roots.
10. It records attribution and utility outcomes after activation.

### 14A.2 Operation 1 — create

**Purpose:** add a missing reusable skill that does not already exist as an active skill, archived skill, component, or repairable candidate.

**Primary evidence:** repeated missing-skill events, repeated manual workflows, recurring user corrections, recurring failure/fix pairs, high-value explicit user request, or archived-but-stale skill demand.

**LLM role:** infer the reusable procedure, applicability boundary, negative boundary, verification checks, failure handling, and candidate SkillIR from evidence clusters.

**Deterministic role:** active/archived duplicate search, evidence thresholding, schema validation, scanner/evaluator, token budgeting, file writing, activation, rollback, and utility tracking.

**Acceptance tests:**

- no adequate active skill exists;
- no archived skill can be promoted/repaired more cheaply;
- target probes pass;
- no-skill/current-nearest-skill controls show positive marginal value;
- regression probes pass;
- security scanner passes;
- runtime description does not shadow stronger skills.

**Rollback:** archive or remove the created skill from active root, revoke embeddings/context hints/probes derived from it, and mark candidate/transaction rolled back.

### 14A.3 Operation 2 — improve

**Purpose:** increase the utility, reliability, safety, concision, portability, or routing precision of an existing skill.

**Primary evidence:** skill helped but was inefficient, skill failed, tool/API drift, user correction, repeated verification failure, shadowing, misleading description, high token cost, stale support artifact, or evaluator/canary failure.

**LLM role:** propose localized SkillIR changes, repair hypotheses, clearer boundaries, validators, failure modes, contract updates, or compression plans.

**Deterministic role:** identify target version, generate diff, validate capability deltas, run regression probes, compare token/risk/utility, stage files, atomically activate or roll back.

**Acceptance tests:**

- patch is localized and evidence-linked;
- target failure improves;
- prior passing behavior remains inside regression budget;
- token/risk/capability deltas are justified;
- broker replay does not increase shadowing;
- canary monitoring confirms no production degradation.

**Rollback:** restore previous active version and revoke all derived state from the rejected version.

### 14A.4 Operation 3 — compose

**Purpose:** create a higher-order workflow skill when smaller skills repeatedly function as one combined user-level procedure.

Composition is different from merge:

```text
merge      = remove duplicate or near-duplicate skills
compose    = create an orchestration skill over distinct component skills
```

**Primary evidence:** recurring co-use, stable skill sequence, repeated co-retrieval/co-injection, repeated multi-skill workflow errors, user-level goal spanning multiple skills, or measured reduction in steps/tokens/errors from a composed workflow.

**LLM role:** infer the combined workflow boundary, ordering, input handoff, verification strategy, failure recovery, and when the composed skill should defer to components.

**Deterministic role:** compute co-usage and sequence statistics, validate component compatibility, build graph edges, run component-vs-composed intervention trials, ensure the composed skill does not shadow components incorrectly, and apply/rollback transactionally.

**Composition candidate requirements:**

- at least two component skills or components;
- component contracts are compatible;
- repeated evidence across distinct sessions/tasks unless explicit high-value user request exists;
- projected marginal value exceeds component-only baseline;
- composed runtime text is shorter or more reliable than loading components ad hoc;
- composed skill has clear `DO NOT USE WHEN` boundaries;
- component skills retain or lose active status based on measured standalone utility.

**Accepted outputs:**

- a new composed workflow skill;
- edges: `component_of`, `composes_with`, `composed_by`, `requires`, and possibly `supersedes`;
- probes for composed workflow and individual components;
- broker policy updates so the composed skill is used for end-to-end tasks and components are used for narrow tasks.

**Reject composition when:**

- co-use is incidental;
- component order is unstable;
- contracts conflict;
- composition inflates token cost;
- composed skill shadows useful component skills;
- a description/disambiguator improvement solves the problem more cheaply;
- existing archived composed skill can be promoted/repaired.

**Rollback:** deactivate/archive the composed skill, restore prior component visibility/routing weights, revoke derived embeddings/probes/context hints, and retain negative evidence explaining why composition failed.

### 14A.5 Operation 4 — decompose

**Purpose:** split a broad/clunky skill into smaller, more precise skills when evidence shows separate workflows, partial usage, poor routing precision, or high token cost.

Decomposition is different from shortening:

```text
shorten       = reduce text while preserving one skill
decompose     = create successor skills for separable procedures
```

**Primary evidence:** separable usage clusters, partial-use patterns, false-positive retrieval, black-hole/generalist skill behavior, independent drift/failure modes, repeated suppression by broker, high token cost relative to used sections, or component-level utility divergence.

**LLM role:** infer separable skill boundaries, successor responsibilities, shared prerequisites, migration notes, disambiguators, and original-skill deprecation plan.

**Deterministic role:** cluster evidence by subprocedure, test successor coverage, run original-vs-successor/broker-subset trials, update graph edges, archive/supersede original only after successor canaries pass, and preserve rollback.

**Decomposition candidate requirements:**

- broad skill has at least two separable high-confidence usage clusters;
- successor skills have clear non-overlapping or explicitly hierarchical boundaries;
- successor set covers original high-value behavior;
- total expected token/context cost decreases or routing precision increases;
- regression probes for original behavior pass under successor/broker bundle;
- original skill can be restored if successors underperform.

**Accepted outputs:**

- two or more successor skills or components;
- original skill marked `superseded` or `archived` after canary, not deleted;
- edges: `decomposes_to`, `generalizes`, `specializes`, `supersedes`, and `shadows` where relevant;
- broker rules to select narrow successors over broad predecessor;
- rollback plan restoring original active version and hiding successors if needed.

**Reject decomposition when:**

- the skill is merely verbose but semantically unified;
- split boundaries are unstable;
- successor set increases shadowing;
- decomposed skills require frequent co-loading and would be better as one composed workflow;
- original skill has strong positive utility and low false-positive retrieval.

### 14A.6 Topology operation scoring

All operation candidates receive an inspectable score:

```text
operation_score =
  + expected_success_delta
  + expected_error_reduction
  + expected_token_reduction
  + expected_latency_reduction
  + evidence_maturity_bonus
  + recurrence_bonus
  + user_correction_bonus
  + drift_repair_bonus
  - regression_risk
  - security_risk
  - privacy_risk
  - shadowing_risk
  - maintenance_cost
  - active_bank_cost
  - uncertainty_penalty
```

Activation requires `operation_score > threshold` and all hard gates passing. Hard gates override score.

### 14A.7 Operation selection precedence

When multiple candidates compete, prefer the least invasive operation that solves the measured problem:

```text
no-op if evidence is weak
→ description/disambiguator repair
→ improve existing active skill
→ promote/repair archived skill
→ compose if repeated workflow cluster is strong
→ decompose if broad-skill false-positive/partial-use evidence is strong
→ create new skill if no reusable existing/archived/component path exists
→ archive/freeze if risk or negative utility dominates
```

This ordering prevents append-only skill growth while still allowing the library to become more capable.

### 14A.8 Broker behavior for composed and decomposed skills

The runtime broker must understand granularity:

- use composed workflow skill when the user task matches the end-to-end workflow;
- use component skills when the user task matches only a subprocedure;
- suppress broad predecessor when a successor has better precision;
- include prerequisite components only when necessary;
- avoid loading both composed skill and all components unless verification requires it;
- log whether the composed/decomposed topology improved outcome.

### 14A.9 Metrics for the four operations

Track separately:

| Operation | Primary metrics |
|---|---|
| create | missing-skill reduction, future reuse, target-pass delta, duplicate avoidance, token cost. |
| improve | failure reduction, regression rate, token delta, utility delta, drift recovery. |
| compose | co-use workflow success, component-vs-composed delta, step/token reduction, shadowing delta. |
| decompose | retrieval precision, false-positive reduction, token reduction, successor coverage, rollback rate. |

A release is not acceptable if it reports only aggregate “skills created” counts. The topology operations must have separate dashboards and acceptance criteria.


## 15. Skill creation algorithm

### 15.1 Creation priority

Before creating a new skill:

1. Search active skills.
2. Search archived skills.
3. Search skill components.
4. Search rejected/quarantined candidates for previous similar attempts.
5. Check duplicate/merge potential.
6. Check whether an existing skill only needs description/disambiguator improvement.

Only then create.

### 15.2 Candidate triggers

Trigger a candidate when one or more are true:

- explicit user request to create/save a skill;
- repeated successful workflow with reusable procedure;
- repeated failure with stable fix;
- user correction recurs;
- tool failure pattern recurs;
- high-value task required repeated manual reasoning;
- archived skill demand recurs but archived skill is stale and repairable;
- active skill repeatedly shadows or gets shadowed and needs split/merge.

### 15.3 Candidate thresholds

Default thresholds:

```yaml
min_recurrence_count: 3
min_distinct_sessions: 2
min_evidence_confidence: 0.72
min_projected_utility: 0.15
max_risk_score: 0.35
max_token_cost_for_new_skill: 900
explicit_user_request_override: true
high_severity_failure_override: true
```

Explicit user requests can lower recurrence requirements, but they do not bypass scanner/evaluator gates.

### 15.4 Contrastive induction

For each candidate domain:

1. Cluster failures.
2. Cluster successes.
3. Retrieve nearest success for each failure.
4. Compare failed and successful trajectories.
5. Extract the behavior present in success and missing in failure.
6. Convert the delta into candidate components.
7. Generate probes for both failure repair and success preservation.

### 15.5 Candidate plan schema

The LLM emits only a structured plan:

```json
{
  "candidate_kind": "new_skill|improvement|compose|decompose|merge|promotion|description_repair|archive",
  "target_skill_id": null,
  "slug": "autoskill-example",
  "frontmatter": {
    "name": "autoskill-example",
    "description": "..."
  },
  "components": [
    {
      "type": "functional",
      "title": "...",
      "content": "...",
      "evidence_ids": ["..."]
    }
  ],
  "runtime_sections": {
    "WHEN": [],
    "INPUTS": [],
    "DO": [],
    "VERIFY": [],
    "FAIL": [],
    "DO_NOT_USE_WHEN": [],
    "NEVER": []
  },
  "support_files": [],
  "capabilities": [],
  "environment_contracts": [],
  "probes": [],
  "expected_benefit": "...",
  "known_risks": []
}
```

The deterministic compiler/writer validates and renders the plan.

---

## 16. Skill improvement algorithm

### 16.1 Improvement triggers

Improve an active skill when:

- it was used and helped but verification was inefficient;
- it was used and failed;
- it was retrieved but ignored;
- it was shadowed by a sibling;
- it shadowed a better skill;
- user corrected the procedure;
- tool/API/package drift occurred;
- canary shows degradation;
- token cost exceeds utility;
- support file or contract is stale;
- description is misleading.

### 16.2 Improvement actions

Actions:

| Action | Use when |
|---|---|
| recompile | runtime text too verbose or unclear |
| add validator | failure came from missing verification |
| add failure mode | recurring pitfall |
| add disambiguator | sibling confusion/shadowing |
| repair contract | environment changed |
| add adapter | new API/package/schema variant |
| prune section | token overhead with low utility |
| decompose skill | skill covers unrelated procedures or shows partial-use clusters |
| compose skills | recurring skill cluster behaves like one higher-order workflow |
| split skill | low-level mechanical split when a file/section boundary is too broad |
| merge skills | duplicate or near-duplicate procedures |
| archive | low utility or high risk |
| freeze | unsafe or repeated regression |

### 16.3 Evidence requirements

An improvement must cite evidence IDs. It cannot be based only on model preference.

Minimum evidence for normal improvement:

- one explicit user correction, or
- two similar failures, or
- one severe failure with reproducible probe, or
- three retrieval/usage logs showing confusion, or
- one verified drift contract violation.

### 16.4 Regression-aware acceptance

Every improvement evaluates:

- target probes related to the change;
- existing passing probes for that skill;
- sibling probes when disambiguation changes;
- no-skill controls where relevant;
- adversarial probes if security-relevant;
- drift probes if environment contracts changed.

Reject if:

- scanner critical finding exists;
- target probes fail;
- regression budget exceeded;
- token cost increases without utility increase;
- capability set expands without policy allowance;
- skill shadowing risk increases beyond threshold.

---

## 17. SkillIR compiler and renderers

### 17.1 Purpose

The compiler transforms SkillIR into compact runtime artifacts. It is not summarization. It is structured compilation with deterministic validation, token budgeting, policy checks, and artifact hashing.

The primary renderer target is OpenClaw `SKILL.md`. Additional renderers may produce:

- broker context hints;
- probe definitions;
- environment contract checks;
- manifest files;
- support-file manifests;
- audit summaries.

### 17.2 Compiler stages

```text
load SkillIR
→ validate JSON schema
→ validate identity/name/slug/frontmatter constraints
→ validate capability manifest
→ validate dependency and conflict edges
→ validate evidence provenance and taint state
→ select runtime-visible components
→ remove tainted/private/unstable material
→ normalize terminology
→ compile typed contracts and tool templates
→ add sibling disambiguators and negative boundaries
→ add deterministic guard-template references
→ add validators and failure handling
→ enforce token and description budgets
→ render SKILL.md and support manifests
→ parse YAML/Markdown round-trip
→ scan hidden/invisible content and security patterns
→ estimate tokens
→ generate hashes and manifest
→ stage files for evaluator and deterministic writer
```

### 17.3 Compiler quality gates

A compiled skill version must pass:

| Gate | Requirement |
|---|---|
| schema | SkillIR matches current schema and no unknown dangerous fields exist. |
| coverage | All required triggers, inputs, preconditions, procedure, verification, and failure sections exist. |
| binding | Tool templates and variables bind to declared inputs only. |
| replacement | Runtime text preserves intended SkillIR meaning without adding unsupported behavior. |
| risk | Capabilities, taint, privacy, network, filesystem, and shadowing risk remain within policy. |
| token | Description and runtime text fit configured budgets. |
| scan | No hidden content, injection language, unsafe code, or capability drift. |
| eval | Target/intervention probes improve; regression/adversarial/shadowing probes stay within budget. |

### 17.4 Compression principles

Keep:

- triggers;
- explicit inputs;
- preconditions;
- concrete procedure;
- safe tool templates;
- required environment contracts;
- verification checks;
- failure handling;
- non-use boundaries;
- sibling disambiguators;
- safety constraints.

Remove:

- explanatory prose;
- history;
- raw examples unless essential;
- duplicate instructions;
- uncertain observations;
- private facts;
- secrets;
- untrusted external imperatives;
- irrelevant tool logs;
- rationale better stored in Postgres.

### 17.5 Token budget

Default budgets:

```yaml
frontmatter_description_max_chars: 160
runtime_skill_target_tokens: 350
runtime_skill_max_tokens: 900
context_hint_max_tokens: 800
support_file_reference_max_tokens: 120
```

If a skill requires more, split it, move details into support files loaded only when needed, or keep evidence in Postgres rather than prompt context.


### 17.6 Context-loadable artifact audit

Before activation, the compiler must produce an artifact audit:

```json
{
  "skill_id": "uuid",
  "skill_version_id": "uuid",
  "tokenizer_profile": "model-or-estimator",
  "artifacts": [
    {
      "path": "SKILL.md",
      "class": "runtime_on_skill_load",
      "tokens": 342,
      "hash": "sha256:...",
      "sections": ["WHEN", "INPUTS", "DO", "VERIFY", "FAIL", "NEVER"],
      "semantic_equivalence_score": 0.94,
      "scanner_status": "pass"
    }
  ],
  "budget_status": "pass",
  "marginal_value_status": "pass"
}
```

The deterministic writer may not apply files unless the audit exists, is internally consistent, and is tied to the evolution transaction.

### 17.7 Semantic compression acceptance

A compressed candidate is accepted only when all are true:

- every required SkillIR requirement is represented or intentionally excluded with a reason;
- no unsupported behavior is introduced;
- target probes pass;
- regression probes remain inside budget;
- safety scanner passes;
- retrieval precision does not degrade beyond threshold;
- shadowing risk does not rise beyond threshold;
- marginal utility per token is non-negative and preferably improved;
- the compiler can reconstruct a mapping from runtime clauses back to SkillIR requirements.

### 17.8 Compression failure actions

When compression fails, do not ship a verbose skill. Choose one:

```text
retry_compilation_with_stronger_model
split_support_file
create_support_script
add_broker_excerpt
compose_with_components
request_decomposition
archive_or_freeze_candidate
keep_previous_version
```

### 17.9 Context-aware examples policy

Examples are expensive. They may enter runtime text only if probe data shows the agent fails without them. Prefer one minimal counterexample or one terse template over full demonstrations. Store full examples in Postgres or probe fixtures, not `SKILL.md`.

### 17.10 Description minimization

OpenClaw injects skill metadata into the prompt for eligible skills, so the description itself is runtime context. Description writing is a compiler task.

Required description style:

```text
<verb capability>; use when <narrow trigger>; not for <sibling boundary>.
```

Reject descriptions that are generic, marketing-like, or broad enough to cause false-positive loading.


### 17.11 SkillIR migration

SkillIR is versioned. Migrations must be deterministic and reversible where possible.

Rules:

- never mutate historical SkillIR rows in place;
- create a new `skill_ir_revisions` row for migrated versions;
- record compiler version and migration reason;
- run scanner/evaluator gates after migration;
- keep old rendered artifacts available for rollback;
- fail closed if migration cannot preserve meaning.

---

## 18. Curation, archive, promotion, and merge

### 18.1 Active bank budget

The active bank is bounded.

Suggested defaults:

```yaml
max_active_skills: 80
max_active_skill_description_tokens_total: 4000
max_active_autoskill_runtime_tokens_total_soft: 20000
max_new_skills_per_day: 8
max_improvements_per_skill_per_day: 3
max_archive_promotions_per_day: 10
```

The exact values should be configurable.

### 18.2 Utility score

Compute skill utility from:

- successful uses;
- failed uses;
- missing-skill events;
- shadowing events;
- retrieval precision;
- retrieval recall;
- user corrections;
- target/regression eval results;
- token cost;
- latency cost;
- risk score;
- drift score;
- maintenance cost;
- age and recency.

Example:

```text
utility =
  + helped_weight * helped_count
  + repair_weight * fixed_failure_count
  + promotion_weight * archived_need_count
  - hurt_weight * hurt_count
  - shadow_weight * shadowing_count
  - token_weight * token_cost
  - risk_weight * risk_score
  - drift_weight * drift_risk
  - stale_weight * stale_days
```

### 18.3 Bank-level optimization

Do not curate only per skill. Optimize the active bank:

Objectives:

- maximize expected task success;
- maximize coverage of recent workload;
- maximize diversity across distinct workflows;
- minimize token cost;
- minimize latency;
- minimize risk;
- minimize drift sensitivity;
- minimize redundancy;
- minimize shadowing.

Actions are evaluated as a set:

```text
keep
archive
promote
merge
split
compose
decompose
repair
recompile description
add disambiguator
add validator
```

### 18.4 Archive policy

Archive when:

- utility below threshold for sustained period;
- no recent relevant retrievals;
- repeatedly harmful;
- repeatedly shadowing better skills;
- drifted and repair not worthwhile;
- superseded by another skill;
- token/risk cost exceeds benefit.

Archive never deletes history. It moves active files out of OpenClaw skill roots and updates DB status.

### 18.5 Promotion policy

Promote archived skill when:

- recent evidence matches archived skill;
- archived skill is better match than active skills;
- drift contracts still pass or repair passes;
- scanner passes current version;
- target/regression probes pass;
- active bank budget can accommodate it or another skill is archived.

### 18.6 Merge policy

Merge when:

- duplicate or overlapping skills repeatedly match same tasks;
- shadowing cannot be solved by descriptions;
- combined skill is shorter than separate skills;
- combined probes pass;
- no lost capability from merged boundaries.

If a merge increases context bloat or ambiguity, do not merge. Add disambiguators instead.

---


### 18.7 Composition policy

Compose when repeated smaller-skill usage behaves as one stable workflow and the composed skill is expected to improve at least one of: success rate, verification reliability, token cost, latency, step count, or user correction rate.

Composition gates:

1. Co-use evidence crosses recurrence and distinct-session thresholds.
2. Component contracts are compatible.
3. Component ordering or orchestration is stable enough to compile.
4. Composed workflow has a clear trigger and clear non-use boundary.
5. Component-only and composed-skill trials show positive marginal value.
6. Shadowing probes show the composed skill will not steal narrow component tasks.
7. Active-bank policy has budget for the composed skill or archives/demotes another skill.

Post-composition states:

- component skills may remain active if standalone utility is positive;
- component skills may be demoted if all meaningful demand is covered by the composed workflow;
- the composed skill has `component_of` and `composed_by` graph edges;
- broker policy knows when to choose composed vs component skills;
- rollback restores prior component routing and active statuses.

### 18.8 Decomposition policy

Decompose when a skill’s evidence shows separable workflows, broad false-positive retrieval, partial-use clusters, independently drifting sections, or token cost materially above used content.

Decomposition gates:

1. At least two separable usage clusters exist.
2. Successor skills have stable triggers and non-overlapping or hierarchical boundaries.
3. Successor set covers original high-value probes.
4. Original-vs-successor trials show better routing precision, lower cost, or lower regression risk.
5. Broker replay shows the decomposition does not create missing-prerequisite failures.
6. Original skill remains restorable until successor canaries are production-verified.

Post-decomposition states:

- original skill becomes `superseded` or `archived`, never deleted;
- successor skills receive `specializes`, `generalizes`, and `decomposes_to` edges;
- broker prefers successor skills for narrow tasks;
- original skill can be promoted back if successors regress.

### 18.9 Merge/split remain supporting operations

Merge and split still exist, but they are narrower than compose/decompose:

| Operation | Meaning |
|---|---|
| merge | collapse duplicates or near-duplicates into one skill. |
| split | divide a file/component mechanically without creating an autonomous topology strategy. |
| compose | create a higher-order workflow skill from distinct reusable skills. |
| decompose | replace a broad skill with successor skills based on separable usage evidence. |

Do not use merge as a substitute for composition. Do not use split as a substitute for decomposition.


## 19. Contract and drift monitoring

### 19.1 Contract types

Extract contracts for:

- CLI availability;
- tool names;
- tool schemas;
- API endpoints;
- authentication assumptions;
- package versions;
- file paths;
- file formats;
- database schemas;
- environment variables;
- permissions;
- output formats;
- external service behavior.

### 19.2 Contract record

```json
{
  "contract_type": "cli|api|package|path|schema|permission|format|service",
  "role": "operational_precondition|verification|output_assumption",
  "value": "...",
  "validation_method": "probe|tool_check|static|manual",
  "severity": "low|medium|high|critical",
  "last_checked_at": "...",
  "status": "valid|violated|unknown"
}
```

### 19.3 Drift jobs

Run drift checks:

- on schedule;
- after tool failures;
- after OpenClaw/plugin updates;
- after dependency/package updates;
- before archived promotion;
- before active bank curation if contracts are stale.

### 19.4 Drift actions

If drift is detected:

1. mark contract violated;
2. generate targeted repair candidate;
3. add drift probe;
4. evaluate repair;
5. activate repair if gates pass;
6. archive/freeze if repair fails or risk is high.

---

## 20. Evaluation and probe-bank design

### 20.1 Evaluation categories

| Category | Purpose |
|---|---|
| target probes | confirm intended improvement |
| regression probes | preserve prior correct behavior |
| sibling probes | prevent shadowing and misuse |
| no-skill controls | measure intervention effect |
| adversarial probes | detect prompt injection and unsafe actions |
| drift probes | check environment contracts |
| canary probes | monitor production outcomes after activation |

### 20.2 Acceptance gate

A candidate passes only if:

```text
scanner_pass = true
AND target_probe_pass_rate >= threshold
AND regression_failures <= hard_budget
AND adversarial_findings = none_critical
AND capability_expansion_allowed = true
AND token_delta_allowed = true
AND utility_delta_positive = true
```

Suggested defaults:

```yaml
target_probe_min_pass_rate: 0.85
regression_failure_hard_budget: 0
adversarial_critical_budget: 0
max_token_delta_without_utility_gain: 0
min_utility_delta: 0.03
```

For noisy tasks, allow statistical confidence intervals, but never allow critical scanner failures.

### 20.3 Intervention testing

For candidate skill S:

1. Run probes without S.
2. Run probes with S.
3. Compare fixes, new failures, token cost, latency, and tool errors.
4. Accept only if net improvement is positive under regression budget.

### 20.4 Probe generation

Probes are generated from:

- explicit user correction examples;
- failure clusters;
- success clusters;
- contrastive success/failure pairs;
- contracts;
- sibling confusion cases;
- prior passing production cases;
- adversarial templates.

Generated probes must themselves be scanned. A malicious trace cannot become a malicious probe that trains the system to do harmful behavior.

### 20.5 Canarying

After activation:

- monitor a small number of relevant future uses;
- compare against expected utility;
- track user corrections;
- track tool failures;
- detect shadowing;
- roll back if failure threshold triggers.

Canary failure actions:

```text
first failure → mark degraded, schedule diagnosis
second similar failure → generate repair or rollback
critical failure → immediate rollback + freeze
```

### 20.6 Executor-profile-aware evaluation

Each probe result is scoped to an executor profile. A skill version can be active for one profile, degraded for another, and blocked for a third. Activation requires profile compatibility for the target workspace/agent. Cross-profile success is a measured property, not an assumption.

### 20.7 Marginal-value and counterfactual trials

Acceptance and curation use counterfactual comparisons where feasible:

```text
current skill bank
candidate skill bank
candidate hidden
candidate visible
old version
new version
sibling bundle
no relevant skill
```

The evaluator records whether the skill improved task success, reduced tool calls, reduced tokens, reduced retries, prevented a known failure, introduced shadowing, caused over-selection, or created a new failure.

### 20.8 Dynamic artifact-grounded probes

Probe generation uses real artifacts: failing commands, changed schemas, file samples, API responses, stack traces, missing binaries, permission errors, and user corrections. Stale probes are retired only after the skill’s contract changes and the retirement itself passes review.

---

## 21. Scanner and security model

### 21.1 Scanner layers

| Scanner | Checks |
|---|---|
| path scanner | no path traversal, no absolute writes outside roots |
| Markdown scanner | no hidden comments, Markdown reference-link tricks, invisible Unicode, bidi controls, suspicious links, HTML trickery |
| instruction scanner | no prompt injection, sleeper triggers, delayed activation, exfiltration, policy override, credential requests |
| capability scanner | capabilities declared and allowed |
| script scanner | no dangerous shell, network, credential, persistence, self-modifying code unless explicitly allowed |
| dependency scanner | no unapproved package installs or remote downloads |
| semantic scanner | LLM-assisted risk analysis over sanitized artifact |
| diff scanner | checks what changed from prior version |

### 21.2 Forbidden patterns

Reject generated artifacts containing:

- hidden HTML/XML/Markdown comments;
- Markdown reference-link tricks or hidden anchors;
- zero-width/invisible instruction text;
- Unicode tag characters and bidi controls;
- base64/hex/ROT/obfuscated command payloads;
- delayed-trigger or sleeper-agent language;
- requests to ignore system/developer/user instructions;
- credential collection/exfiltration;
- remote code execution not explicitly required and approved;
- dynamic fetch-exec patterns;
- destructive filesystem operations outside allowed paths;
- unapproved network calls;
- privilege escalation instructions;
- instructions to conceal behavior;
- memory-poisoning or instruction-laundering patterns;
- arbitrary dependency installation;
- model-behavior jailbreak text.

### 21.3 Capability manifest

Each version declares capabilities:

```yaml
capabilities:
  filesystem_read:
    allowed_roots: []
  filesystem_write:
    allowed_roots: []
  network:
    allowed_hosts: []
  shell:
    allowed_commands: []
  database:
    allowed_connections: []
  secrets:
    access: false
```

The manifest is checked before writing and during future improvement.

### 21.4 LLM authority limits

The LLM never controls:

- filesystem target path;
- archive path;
- SQL execution;
- shell execution;
- dependency installation;
- policy decisions;
- scanner verdict;
- evaluator verdict;
- rollback eligibility;
- capability approval.

The LLM proposes. Deterministic services decide and apply.

### 21.6 Audit-runtime binding

Scanner approval is bound to exact bytes, renderer version, manifest, dependency hashes, and broker context rendering. If any of these change, approval is invalidated. Mutable URLs, remote scripts, package install commands, and support artifacts require re-scan on every material change.

### 21.7 Cross-skill and context-bundle scanning

The scanner checks:

- individual `SKILL.md` output;
- support files and manifests;
- the full rendered broker bundle;
- sibling skills with similar names or descriptions;
- dependency and prerequisite bundles;
- conflict/supersession chains;
- external skills visible in the same OpenClaw session.

A bundle can be rejected even if every individual skill passes.

### 21.8 Runtime action boundary enforcement

Where OpenClaw hook surfaces permit it, the plugin should implement deterministic boundary checks around risky tool calls. These checks are not LLM judgments. They enforce declared capabilities, known path roots, no-secret policies, drift-blocks, and skill manifest constraints.

---


### 21.9 Provenance manifest for generated artifacts

Every activated SkillKernel artifact set must include a manifest that lets the sidecar verify what was generated, from what source, under which gates, and how to roll it back. This is modeled after supply-chain provenance principles, but kept lightweight for v1.

Required file:

```text
<active-skill-root>/<slug>/.autoskill-manifest.json
```

Required shape:

```json
{
  "schema": "autoskill-artifact-manifest.v1",
  "skill_id": "uuid",
  "skill_version_id": "uuid",
  "skill_ir_revision_id": "uuid",
  "evolution_transaction_id": "uuid",
  "generator": {
    "skillkernel_version": "semver-or-git-sha",
    "compiler_version": "semver-or-git-sha",
    "model_profile": "profile-name-or-null",
    "model_qualification_run_id": "uuid-or-null",
    "embedding_profile": "profile-name-or-null"
  },
  "artifacts": [
    {"path": "SKILL.md", "sha256": "hex", "context_loadable": true},
    {"path": "support/tool.py", "sha256": "hex", "context_loadable": false}
  ],
  "capabilities": [],
  "scanner_run_ids": [],
  "evaluation_run_ids": [],
  "token_budget_record_id": "uuid",
  "rollback_pointer": {
    "previous_skill_version_id": "uuid-or-null",
    "archive_path": "relative/path"
  },
  "created_at": "iso-8601"
}
```

Activation verifies:

```text
manifest schema valid
all files present
all hashes match
capability manifest compatible
scanner/evaluator/token/equivalence gates passed
model/embedding qualification references current enough when applicable
rollback pointer valid
no unmanifested context-loadable file exists
```

A missing or invalid manifest freezes the skill and removes it from the active SkillKernel-owned lineup until repair or rollback succeeds.

## 22. Filesystem writer

### 22.1 Active and archive roots

Active:

```text
<workspace>/skills/autoskill/<slug>/
```

Archive:

```text
<workspace>/.autoskill/archive/<skill-id>/v<version>/
```

Staging:

```text
<workspace>/.autoskill/staging/<job-id>/
```

### 22.2 Write flow

```text
validate structured plan
→ render files in staging
→ parse SKILL.md
→ scan files
→ compute hashes
→ run evaluations
→ fsync staging files
→ snapshot previous active version
→ atomic rename/copy into active root
→ verify final hashes
→ update DB transaction
→ append audit record
→ enqueue canary monitor
```

### 22.3 Rollback flow

```text
identify previous active version
→ verify archive hashes
→ stage rollback files
→ atomic replace active root
→ update DB status
→ append audit record
→ mark failed version rolled_back
→ freeze if critical
```

### 22.4 Path containment

All write paths are derived from `workspace_id`, `skill_id`, version, and sanitized slug. The LLM cannot supply a path. Relative support-file paths are checked against an allowlist:

```text
SKILL.md
scripts/<safe-name>.py
scripts/<safe-name>.sh
references/<safe-name>.md
assets/<safe-name>.<allowed-ext>
```

No symlinks. No hardlinks. No parent traversal. No absolute paths.

---

## 23. Scheduler and job queue

### 23.1 No external scheduler dependency

Do not use:

- OpenClaw Cron;
- system cron;
- Kubernetes CronJob;
- Celery beat;
- pg_cron.

Use sidecar-owned schedules and jobs in Postgres.

### 23.2 Scheduler loop

```text
every scheduler_tick:
  acquire advisory lock
  find due schedules
  coalesce misfires according to policy
  insert jobs with idempotency keys
  update next_run_at
  release lock
```

### 23.3 Worker lease loop

```text
BEGIN;
SELECT job
FROM autoskill.jobs
WHERE status='queued' AND run_after <= now()
ORDER BY priority, run_after
FOR UPDATE SKIP LOCKED
LIMIT 1;
UPDATE job SET status='leased', lease_owner=?, lease_expires_at=?;
COMMIT;
```

Workers heartbeat leases. Expired leases return to queue if attempts remain.

### 23.4 Core schedules

Recommended defaults:

| Job | Frequency |
|---|---|
| event normalization | continuous/queued |
| evidence extraction | every 5–15 min or event-triggered |
| embedding | queued |
| opportunity mining | every 1–6 hours |
| skill improvement scan | every 6–24 hours |
| runtime broker calibration | daily |
| active bank curation | daily |
| archive promotion scan | daily or event-triggered |
| drift check | daily/weekly depending skill contracts |
| probe refresh | weekly |
| retrieval recall audit | weekly |
| audit hash verification | daily |
| retention/rollups | daily |

### 23.5 Misfire policy

Use:

- `coalesce` for routine scans;
- `catch_up_limited` for retention/audit;
- `skip` for expensive non-critical analysis;
- `immediate` only for safety/rollback jobs.

---

## 24. Outcome attribution and credit ledger

### 24.1 Why attribution exists

Skill updates should not happen just because a skill appeared in a session. The system needs credit assignment.

Classify outcomes as:

- skill helped;
- skill hurt;
- skill was ignored;
- skill was missing;
- skill shadowed another skill;
- agent solved independently;
- tool failed independent of skill;
- environment drifted;
- user correction changed requirements;
- unknown.

### 24.2 Attribution signals

Signals:

- retrieval event;
- runtime hint injection;
- explicit skill invocation if observable;
- tool sequence matching skill procedure;
- verifier outcome;
- user correction;
- repeated failure mode;
- before/after skill intervention probes;
- canary outcomes.

### 24.3 Credit events

Credit events feed:

- utility score;
- curation;
- improvement triggers;
- archive/promote decisions;
- retrieval calibration;
- learned curator dataset.

---

## 25. Observability

### 25.1 Metrics

Capture:

- ingest event rate;
- redaction counts;
- sidecar latency;
- spool backlog;
- job queue depth;
- job success/failure by type;
- embedding backlog;
- retrieval recall audit score;
- context hint injection count;
- context hint token cost;
- skill creation/improvement counts;
- scanner reject counts;
- evaluation pass/fail counts;
- active skill count;
- archive/promote counts;
- rollback/freeze counts;
- drift violation counts;
- utility deltas;
- Postgres table/index growth.

### 25.2 Dashboards

Minimum operator views:

1. system health;
2. recent autonomous changes;
3. active skills and utility;
4. archived skills and promotion candidates;
5. scanner/evaluator failures;
6. retrieval/context broker performance;
7. drift violations;
8. rollback/freeze events;
9. storage growth;
10. audit integrity.

### 25.3 Audit hash chain

Every mutation appends an audit record with previous audit hash and current hash. Audit verification runs daily and before release/export.

---

## 26. Configuration

Example config:

```yaml
autoskill:
  mode: autonomous_guarded
  workspace_id: auto
  active_root: "<workspace>/skills/autoskill"
  archive_root: "<workspace>/.autoskill/archive"
  staging_root: "<workspace>/.autoskill/staging"

  plugin:
    capture_raw_conversation: false
    capture_tool_events: true
    capture_messages: true
    local_spool_max_mb: 256
    sidecar_url: "http://127.0.0.1:8765"
    runtime_context_broker:
      enabled: true
      timeout_ms: 150
      max_tokens: 600
      fail_soft: true

  database:
    dsn_env: "AUTOSKILL_DATABASE_URL"
    schema: "autoskill"
    statement_timeout_ms: 30000

  llm:
    active_profile: service_reasoner
    profiles:
      service_reasoner:
        route_type: openclaw          # or openai_compatible
        provider: configured-openclaw-provider
        model: provider/model
        # For route_type: openai_compatible, set:
        # base_url_env: AUTOSKILL_LOCAL_LLM_BASE_URL
        # api_key_env: AUTOSKILL_LOCAL_LLM_API_KEY
        # endpoint_kind: chat_completions
        thinking: high
        thinking_fallback_policy: strict  # strict | downgrade | omit
        temperature: 0
        max_input_tokens: 80000
        max_output_tokens: 8000
        timeout_ms: 180000
        max_concurrent: 1
        hosted_allowed: true
        local_only: false

  embeddings:
    active_profile: default_embedding
    profiles:
      default_embedding:
        route_type: openai_compatible   # or openclaw
        provider: configured-embedding-provider
        model: embedding-model-id
        base_url_env: AUTOSKILL_EMBEDDING_BASE_URL
        api_key_env: AUTOSKILL_EMBEDDING_API_KEY
        dimensions: 1536
        distance_metric: cosine
        batch_size: 128
        hosted_allowed: true
        local_only: false

  skill_budget:
    max_active_skills: 80
    max_runtime_skill_tokens: 900
    target_runtime_skill_tokens: 350
    max_frontmatter_description_chars: 160
    max_context_hint_tokens: 800
    max_support_excerpt_tokens: 120
    min_marginal_success_per_1k_tokens: 0.0
    max_false_positive_load_delta: 0.02
    max_shadowing_delta: 0.01
    max_new_skills_per_day: 8

  context_compiler:
    enabled: true
    tokenizer_profile: "model-specific-or-estimated"
    reject_human_prose: true
    require_semantic_equivalence: true
    min_semantic_equivalence_score: 0.90
    allow_examples_in_runtime_text: false
    allow_support_files: true
    support_files_require_loadability_class: true

  gates:
    min_recurrence_count: 3
    min_evidence_confidence: 0.72
    target_probe_min_pass_rate: 0.85
    regression_failure_hard_budget: 0
    adversarial_critical_budget: 0

  security:
    allow_support_scripts: true
    allow_network_in_generated_skills: false
    allow_shell_in_generated_skills: false
    forbid_hidden_markdown: true
    redact_before_store: true
    redact_before_embed: true

  scheduler:
    tick_seconds: 30
    worker_count: 4
    max_llm_jobs_concurrent: 2
```

---

## 27. Phased implementation plan

The implementation order is part of the safety design. Do not build autonomous skill writing before the control plane exists.

### Phase 0 — Confirm OpenClaw seams

Deliver:

- exact hook names and payloads for the target OpenClaw version;
- plugin permission requirements;
- active skill root behavior;
- watcher/snapshot behavior;
- prompt/context hook behavior;
- skill invocation observability;
- available stable text-inference seams, if any;
- available stable embedding-provider seams, if any;
- confirmation that OpenClaw Cron and Skill Workshop are not required.

Acceptance:

- plugin can capture turn, message, and tool events without blocking sessions;
- generated test skill loads from the active SkillKernel root;
- archive root is invisible to OpenClaw;
- runtime context hint can be disabled and fails soft;
- SkillKernel can operate with direct provider adapters even if OpenClaw inference/embedding seams are unavailable or unsafe.

### Phase 1 — Database, migrations, and sidecar skeleton

Deliver:

- one Postgres database;
- one `autoskill` schema;
- pgvector extension;
- model profile tables;
- embedding profile tables;
- event/evidence/provenance tables;
- job/schedule tables;
- audit table;
- sidecar API;
- auth and health endpoints.

Acceptance:

- events insert idempotently;
- migrations can run up/down in development;
- audit hash chain works;
- model and embedding profiles are stored independently of OpenClaw agent defaults;
- embeddings can store multiple dimensions through profile-scoped vector records.

### Phase 2 — Plugin capture, redaction, tainting, and spool

Deliver:

- plugin hooks;
- redaction;
- taint propagation;
- local spool;
- sidecar forwarding;
- status/control command surface.

Acceptance:

- sidecar outage does not block OpenClaw;
- redacted payloads only are persisted;
- spool replays idempotently;
- raw conversation capture remains explicit opt-in.

### Phase 3 — Sidecar scheduler and job queue

Deliver:

- durable schedules;
- durable jobs;
- leases;
- retries;
- idempotency keys;
- worker pools;
- misfire handling;
- advisory locks.

Acceptance:

- jobs survive restart;
- duplicate ticks do not duplicate work;
- stuck leases recover;
- no OpenClaw Cron dependency exists.

### Phase 4 — Simplified LLM and embedding access layer

Deliver:

- text model profile config loader;
- embedding profile config loader;
- `openclaw` text route when the target OpenClaw version exposes a stable supported seam;
- `openai_compatible` text route for direct `/v1/chat/completions` and optional `/v1/responses`;
- `openclaw` embedding route when the target OpenClaw version exposes a stable supported seam;
- `openai_compatible` embedding route for direct `/v1/embeddings`;
- thinking-level validation and explicit strict/downgrade/omit behavior;
- LLM invocation audit without dollar-cost accounting;
- embedding profile ledger;
- token, timeout, retry, concurrency, local-only, and hosted-disabled controls;
- provider smoke tests;
- text-model qualification probe set;
- embedding-profile qualification probe set.

Acceptance:

- all LLM-needed semantic jobs use the single configured text profile;
- unsupported thinking levels fail, downgrade, or omit according to explicit policy;
- every LLM invocation is audited without cost estimation;
- active text profile has a current qualification verdict before autonomous LLM-dependent apply;
- failed or expired text-profile qualification downgrades LLM-dependent autonomous jobs to propose-only or paused;
- every vector records its embedding profile;
- switching embedding profile creates a re-embedding campaign;
- embedding qualification validates dimension, determinism, query/document input behavior, and calibration before vector retrieval is trusted;
- runtime hooks perform no synchronous LLM calls.

### Phase 5 — Evidence, memory, provenance, and revocation pipeline

Deliver:

- evidence extractor;
- governed memory derivation;
- provenance edges;
- maturity ladder;
- derived-data revocation;
- retention/deletion traversal.

Acceptance:

- no evidence becomes runtime text directly;
- rollback/quarantine/deletion invalidates derived memories, embeddings, compiled artifacts, probes, broker hints, and caches;
- evidence maturity gates are enforced.

### Phase 6 — Retrieval, body-aware indexes, and external-skill inventory

Deliver:

- lexical search;
- vector search;
- exact rerank;
- archived skill matching;
- duplicate/overlap matching;
- body index documents;
- external skill inventory;
- co-use graph and topology evidence tables.

Acceptance:

- active/archived matches precede new creation;
- ANN recall audits work;
- retrieval decisions are logged;
- external skills are inventoried but not autonomously mutated;
- body-aware routing improves broker decisions without injecting full bodies into context.

### Phase 7 — SkillIR, Context Compiler, and Token Budget Governor

Deliver:

- SkillIR schema and validator;
- SkillGraphIR schema and validator;
- context-loadability classification;
- tokenizer abstraction;
- description/frontmatter compiler;
- `SKILL.md` typed-section renderer;
- support-snippet compiler;
- broker-hint compiler;
- SkillGraphIR renderer into minimal broker-context summaries;
- semantic-compression trials;
- artifact token ledger;
- no-human-prose scanner;
- semantic-equivalence gate;
- context-value scoring.

Acceptance:

- no context-loadable artifact activates without token count, budget, hash, scanner status, and coverage record;
- runtime artifacts are AI-facing compiled outputs, not human documentation;
- composed and decomposed workflows have SkillGraphIR when multiple skills or component steps are involved;
- verbose/rationale-heavy runtime text is rejected;
- compression preserves required SkillIR facts and regression probes;
- over-budget artifacts fail closed.

### Phase 8 — Scanner, evaluator, probes, and regression gates

Deliver:

- static scanner;
- semantic scanner support path;
- capability scanner;
- harmful-capability classifier;
- composed-bundle scanner;
- probe generator;
- probe executor;
- no-skill/current-skill/old-skill/new-skill comparison harness;
- SkillGraphIR verifier and local-repair probes;
- regression/adversarial/shadowing gates.

Acceptance:

- scanner rejects malicious artifacts;
- self-feedback-only changes fail;
- target improvements do not regress protected probes;
- composed bundles are scanned as bundles, not only individual files;
- model-profile qualification failure cannot be bypassed by evaluator success.

### Phase 9 — Deterministic writer, evolution transactions, and rollback

Deliver:

- staged deterministic writer;
- capability manifests, provenance manifests, and file hashes;
- atomic apply;
- active/archive file movement;
- evolution transaction manager;
- rollback across DB, files, embeddings, broker caches, context hints, probes, lifecycle state, and derived memories.

Acceptance:

- LLM never controls paths or writes files;
- each activated artifact contains and verifies `.autoskill-manifest.json`;
- partial activation cannot occur;
- rollback restores the effective runtime state, not only `SKILL.md`.

### Phase 10 — Runtime Skill-Context Broker and shadowing control

Deliver:

- broker API;
- deterministic set-aware planner;
- no-skill decision;
- shadowing risk model;
- external-skill collision handling;
- compact context-hint renderer;
- broker policy versioning;
- broker canaries.

Acceptance:

- broker hint returns under timeout;
- no LLM call in hook;
- no raw evidence/memory is injected;
- no-skill is a valid decision;
- shadowing cases are logged and influence curation.

### Phase 11 — Creation, improvement, composition, and decomposition in propose-only mode

Deliver:

- opportunity miner;
- contrastive induction;
- create/improve/compose/decompose candidate planners;
- topology candidate tables;
- component/co-use graph analysis;
- operation-specific trial generation;
- reviewer/status UI for proposals.

Acceptance:

- candidates require evidence;
- compose proposals beat component-only baselines before activation;
- decompose proposals beat original-skill baselines before activation;
- broad/clunky/black-hole skill detection works in dry-run reports.

### Phase 12 — Autonomous guarded apply, canarying, curation, and archive/promotion

Deliver:

- autonomous guarded policy;
- canary activation;
- freeze-after-failure;
- archive/demote policy;
- archived-skill promotion;
- merge/dedupe policy;
- utility/token-time/risk scoring;
- rollback automation.

Acceptance:

- autonomous create/improve/compose/decompose applies only after scanner, evaluator, regression, token-budget, profile-qualification, provenance-manifest, and broker gates pass;
- low-value skills archive without deletion;
- archived skills can be promoted when evidence recurs;
- canary failures freeze or roll back automatically.

### Phase 13 — Advanced governance and production hardening

Deliver:

- drift contracts;
- executor profiles;
- marginal-value trials;
- action attribution gate;
- curator-learning data capture;
- observability dashboards;
- audit verification;
- backup/restore/export/import;
- red-team suite.

Acceptance:

- skill effectiveness is profile-aware;
- high-risk actions have causal attribution;
- cost and context waste are observable;
- the system can be restored after disaster without orphan active artifacts.

## 28. Production acceptance criteria

The release is production-ready only if all are true:

1. no dependency on OpenClaw Cron;
2. no dependency on Skill Workshop;
3. no per-skill databases;
4. no per-skill schemas;
5. all events are redacted before persistence;
6. all embeddings are created from redacted text;
7. sidecar outage does not block normal OpenClaw usage;
8. scheduler survives restart and resumes safely;
9. job leases prevent duplicate mutation;
10. skill operation selection considers improve, promote, compose, decompose, merge, and archive before creating duplicates;
11. every created skill is a normal OpenClaw skill with valid `SKILL.md`;
12. every mutation has manifest, hashes, scanner result, evaluator result, and rollback pointer;
13. hidden comments and invisible Markdown are rejected;
14. scanner blocks known malicious skill patterns;
15. regression gate blocks local fixes that break prior probes;
16. no-skill controls or equivalent intervention checks exist for accepted skills;
17. active skill budget is enforced;
18. runtime context broker is bounded and fail-soft;
19. archived skills are invisible to OpenClaw but searchable through SkillKernel;
20. archived promotion works;
21. rollback works under canary failure;
22. drift checks detect simple broken environment contracts;
23. retrieval logs track retrieved/rendered/injected/used/outcome;
24. shadowing logs and remediation exist;
25. audit hash chain validates;
26. all core invariants are automated tests;
27. create, improve, compose, and decompose are implemented as separate operation classes with separate evidence, evaluation, and metrics;
28. composition requires co-use/sequence evidence and component-vs-composed trials;
29. decomposition requires partial-use/false-positive/separable-cluster evidence and original-vs-successor trials;
30. topology operations are rollback-complete across graph edges, broker policy, embeddings, probes, and active files.
31. every context-loadable artifact has a registry row, token count, budget, content hash, compiler version, scanner status, and provenance;
32. every compressed description passes positive/negative routing-equivalence tests;
33. every compressed body passes information-preservation and regression gates;
34. every support snippet has classification, budget, scan result, and retrieval boundary;
35. context-value-per-token is measured and can drive archive, compose, decompose, or no-skill decisions.


Additional context-management acceptance criteria:

- no SkillKernel-owned context-loadable artifact lacks a loadability class;
- no `SKILL.md` version can activate without token count, semantic-equivalence result, scanner pass, and artifact hash;
- generated descriptions stay within configured character budget unless explicitly excepted by policy;
- runtime skill bodies meet target token budget or produce a deterministic split/decompose decision;
- support files are never assumed safe merely because they are outside `SKILL.md`;
- no raw transcript, rationale, history, or improvement note appears in runtime context unless explicitly promoted through SkillIR and compiler gates;
- context regressions trigger reject, rollback, decompose, description tighten, or broker abstention.


---

## 29. Risk register

| Risk | Mitigation |
|---|---|
| Skill bloat degrades context | Active budget, context broker, compiler, curation, archive. |
| Over-compression drops rare critical constraints | Coverage map, information-preservation gate, semantic-equivalence probes, regression bank, rollback. |
| Verbose support files bypass SKILL.md compression | Support-file classification, snippet budgets, progressive-disclosure gates, scanner and token governor. |
| Description compression breaks routing | Positive/negative routing-equivalence tests and delta-debugging rollback. |
| Context budget policy drifts by model/backend | Executor-profile-specific token policies and artifact variants only when evaluated. |
| Over-composition creates broad black-hole skills | Co-use thresholds, component-vs-composed trials, shadowing probes, no-skill controls, canary rollback. |
| Over-decomposition creates fragmented skill clutter | Successor coverage tests, broker replay, active-bank budget, composition reconsideration, rollback. |
| Composition hides useful components | Component standalone utility tracking and broker rules for composed vs component selection. |
| Decomposition loses original behavior | Original probe preservation, successor-bundle regression tests, restore original on canary failure. |
| Skill shadowing | Sibling disambiguators, shadow edges, runtime hints, bank-level curation. |
| Self-generated bad skills | Evidence gate, contrastive induction, scanner, evaluator, canary, rollback. |
| Self-feedback drift | No self-feedback-only acceptance. Require grounded evidence. |
| Local fix causes regression | Hard regression gate and probe bank. |
| Duplicate skills accumulate | Active/archived matching, merge, supersede, no-create-before-search policy. |
| Archived skill should have been used | Archived retrieval and promotion jobs. |
| Memory poisoning | Taint, provenance, write-path filtering, no direct memory-to-skill compilation. |
| Skill prompt injection | Scanner, no hidden comments, capability manifest, adversarial probes. |
| Malicious support script | Script scanner, capability policy, no unapproved shell/network. |
| LLM writes dangerous file | Structured plan only, deterministic path-contained writer. |
| pgvector recall loss | Hybrid retrieval, exact rerank, iterative scans, recall audits. |
| Drift from changing tools/APIs | Environment contracts and drift jobs. |
| Scheduler duplicate jobs | Idempotency keys, row locks, advisory locks. |
| Postgres growth | Partitioning, rollups, retention, vacuum/index maintenance. |
| User-facing dependency changes | No Cron/Skill Workshop dependency; narrow skill/hook compatibility surface. |
| Evaluation too expensive | Tiered probes, cached evals, canary sampling, multi-objective budget. |
| Autonomy incident | Freeze, quarantine, rollback, audit, operator controls. |

---

## 30. Developer handoff checklist

Before coding:

- [ ] Confirm OpenClaw hook names and payloads.
- [ ] Confirm plugin permissions for raw conversation and prompt/context contribution.
- [ ] Confirm workspace skill root and watcher behavior.
- [ ] Confirm whether skill invocation can be observed directly.
- [ ] Define redaction policy.
- [ ] Select embedding model and vector dimension.
- [ ] Choose evaluation sandbox strategy.
- [ ] Define scanner rule pack.
- [ ] Define active skill budget.
- [ ] Define context hint budget.
- [ ] Define context-loadable artifact classes and budgets: description, body, broker hint, support snippet, support manifest, external-skill summary, probe prompt.
- [ ] Choose tokenizer/token counting implementation per executor profile.
- [ ] Define semantic-density, information-preservation, and context-value thresholds.
- [ ] Define no-human-prose and no-raw-transcript gates for runtime artifacts.
- [ ] Define sidecar authentication.
- [ ] Define backup, retention, revocation, and derived-data deletion policy.
- [ ] Define evolution transaction semantics and rollback-complete invariants.
- [ ] Define action-attribution risk tiers and which tool calls require counterfactual checks.
- [ ] Define harmful-capability and dual-use skill classifier policy.
- [ ] Define topology operation thresholds for create, improve, compose, and decompose.
- [ ] Define co-use, sequence, partial-use, and false-positive retrieval metrics.

During implementation:

- [ ] Build migrations before logic.
- [ ] Build redaction before ingest.
- [ ] Build scheduler before analysis jobs.
- [ ] Build scanner/evaluator before writer.
- [ ] Build rollback before autonomous apply.
- [ ] Build evolution transaction tables before autonomous apply.
- [ ] Build provenance/revocation traversal before autonomous apply.
- [ ] Build retrieval logs before retrieval tuning.
- [ ] Build context broker logs before enabling hints.
- [ ] Build body-level indexing before retrieval tuning.
- [ ] Build context artifact registry before any compiler output activates.
- [ ] Build token-budget, routing-equivalence, and information-preservation gates before autonomous apply.
- [ ] Build action-attribution logs before high-risk runtime enforcement.
- [ ] Build archive before promotion.
- [ ] Build topology operation logs before enabling compose/decompose.
- [ ] Build composition/decomposition evaluators before autonomous topology changes.
- [ ] Build audit before mutation.

Do not ship autonomous apply until scanner, evaluator, deterministic writer, rollback, evolution transactions, provenance/revocation traversal, action attribution, and audit are all operational.

---

## 31. Final references and research traceability

The implementation team should treat this section as the research/design crosswalk, not as optional background. The architecture is intentionally constrained by the platform facts, agent-skill research, context-management research, database behavior, and security findings listed below.

### 31.1 Platform and runtime anchors

- **OpenClaw Skills documentation**: OpenClaw skills are ordinary directories containing `SKILL.md`; skill metadata and Markdown body are loaded from defined roots and injected into the agent context. SkillKernel must therefore emit standard skill artifacts rather than a custom-only runtime format. URL: https://docs.openclaw.ai/tools/skills
- **OpenClaw skill creation documentation**: generated skill directories must contain valid `SKILL.md` frontmatter and body. URL: https://docs.openclaw.ai/tools/creating-skills
- **OpenClaw Plugin/Hooks documentation**: hooks are in-process extension points and should remain lightweight; the sidecar owns slow scheduling, LLM analysis, evaluation, mutation, and rollback. URL: https://docs.openclaw.ai/plugins/hooks
- **OpenClaw Scheduled Tasks/Cron documentation**: Cron is Gateway/user-facing automation; SkillKernel must not use it as the internal autonomous maintenance substrate. URL: https://docs.openclaw.ai/automation/cron-jobs
- **OpenClaw Skill Workshop documentation**: useful prior art for proposal/scanner/quarantine ideas, but excluded as a dependency because SkillKernel must own its lifecycle pipeline end-to-end.

### 31.2 Database and retrieval anchors

- **pgvector documentation**: supports exact search, HNSW/IVFFlat approximate search, hybrid lexical/vector retrieval, filtered-search caveats, iterative scans, partial indexes, partitioning, and reranking. SkillKernel uses pgvector as a candidate generator, never as the final authority. URL: https://github.com/pgvector/pgvector
- **PostgreSQL full-text search**: use for lexical retrieval and hybrid reranking alongside vector search. URL: https://www.postgresql.org/docs/current/textsearch.html
- **PostgreSQL transactional primitives**: use ordinary SQL transactions, constraints, advisory locks, row-level/logical scoping, partitioning when measured, and durable job queues for the control plane.
- **OpenTelemetry trace concepts/specification**: spans, span context, span links, attributes, and context propagation provide a mature model for correlating multi-service work. SkillKernel implements a local Postgres trace spine and optional content-safe OpenTelemetry export. URL: https://opentelemetry.io/docs/concepts/signals/traces/

### 31.3 Agent-skill lifecycle, acquisition, retrieval, and topology anchors

- **A Comprehensive Survey on Agent Skills**: skill systems should be understood through representation, acquisition, retrieval, and evolution. This supports SkillIR plus create/improve/compose/decompose lifecycle operations. URL: https://arxiv.org/html/2605.07358v3
- **Agent Skills for Large Language Models**: skill packaging, acquisition, progressive disclosure, and security shape the implementation surface. URL: https://arxiv.org/html/2602.12430v1
- **MUSE-Autoskill**: creation, memory management, skill management, evaluation, and refinement should be handled as a single lifecycle, not as isolated generators. URL: https://arxiv.org/abs/2605.27366
- **SkillLearnBench**: continual skill learning needs grounded evaluation; self-feedback-only skill mutation can drift. URL: https://arxiv.org/abs/2604.20087
- **SkillsBench**: curated skills can improve average performance, but generated or overbroad skills can hurt individual tasks. SkillKernel therefore requires intervention and regression gates. URL: https://arxiv.org/abs/2602.12670
- **SkillMaster**: trajectory-informed skill review supports evidence-linked create/refine/select cycles. URL: https://arxiv.org/html/2605.08693v1
- **SkillRet**: large-scale skill retrieval is hard enough to require dedicated logging, calibration, reranking, and recall audits. URL: https://arxiv.org/abs/2605.05726
- **Skill Retrieval Augmentation**: retrieval, incorporation, and end-task execution are separate failure points. The runtime broker must log and optimize all three. URL: https://arxiv.org/html/2604.24594v2
- **More Skills, Worse Agents?**: larger skill libraries can degrade performance through skill shadowing; the broker must be set-aware, budgeted, and allowed to abstain. URL: https://arxiv.org/html/2605.24050v1
- **Graph-of-Skills**: dependency-aware graph expansion and budgeted hydration are required for large repositories. URL: https://arxiv.org/abs/2604.05333
- **SkillRAE**: selected skill evidence must be compiled into compact, grounded, immediately usable runtime context; retrieval alone is insufficient. URL: https://arxiv.org/abs/2605.10114
- **CODESKILL**: coding-agent trajectories can be distilled into multi-granularity skills while maintaining a compact bank; this supports SkillKernel's evidence-driven topology optimizer and stable active-bank budget. URL: https://arxiv.org/abs/2605.25430
- **SkillGrad**: recurring trajectory-loss diagnostics and a persistent momentum overlay improve skill updates; SkillKernel implements this as the diagnostic momentum store. URL: https://arxiv.org/abs/2605.27760
- **EffiSkill**: reusable operator/meta skills can capture recurring transformation mechanisms and higher-order strategies; SkillKernel therefore tracks skill granularity and effect signatures rather than only prose. URL: https://arxiv.org/abs/2603.27850
- **GraSP**: graph-structured compositions with typed DAGs, node checks, and localized repair support first-class composition operations. URL: https://arxiv.org/abs/2604.17870
- **SkillOps / SkillOS / SkillBrew / SkillsVote-style work**: long-horizon library health, attribution, retirement, merge/split, and bank-level curation must be explicit data-backed actions rather than manual cleanup.
- **SkillX / SkillLens / SkillNet-style work**: multi-level, multi-granularity, and relational skill libraries support composition/decomposition rather than flat append-only skill accumulation.

### 31.4 Skill representation and compiler anchors

- **SkillSmith**: skills should compile into boundary-first minimal executable runtime interfaces rather than verbose human documentation. URL: https://arxiv.org/html/2605.15215v1
- **Skill-as-Pseudocode / Formal Skill / SkillIR-style work**: typed contracts, structured procedures, deterministic validators, and backend emission reduce ambiguity and support portability. URL: https://arxiv.org/abs/2605.27955
- **SkillRouter**: names and descriptions are insufficient for routing; body-aware indexing over SkillIR, compiled runtime text, contracts, probes, and support summaries is required.
- **SkVM / SkillRT / OpenSkillEval-style work**: skill effectiveness depends on executor profile, harness, runtime environment, tool availability, permissions, and artifact state; compiler-style environment binding can improve portability and reduce token consumption. URL: https://arxiv.org/abs/2604.03088
- **SWE-Skills-Bench-style findings**: skills must be evaluated by marginal value, not existence; token overhead and version-mismatched guidance can make otherwise plausible skills harmful.

### 31.5 Context-management and compression anchors

- **Anthropic effective context engineering**: context is a finite resource with diminishing returns; agents need curated context, not indiscriminate loading. URL: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **Anthropic Agent Skills overview and best practices**: staged/progressive disclosure and bounded `SKILL.md` contents support a compiler/token-governor architecture. URL: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- **Lost in the Middle**: long context is not used uniformly; relevant information can be missed depending on position. Runtime skill text must be short, positioned, and salient. URL: https://aclanthology.org/2024.tacl-1.9/
- **RULER**: advertised context windows can exceed effective context windows on complex long-context tasks. URL: https://arxiv.org/abs/2404.06654
- **Context Rot**: increasing input length and distractor content can degrade performance. SkillKernel must measure token cost, false-positive loads, and context-value per token. URL: https://www.trychroma.com/research/context-rot
- **Prompt Compression and Semantic Prompt Compression work**: compression must preserve semantics and task performance; lossy summaries are insufficient for runtime skill artifacts. URLs: https://arxiv.org/abs/2410.12388 and https://arxiv.org/html/2605.04426v1
- **LLMLingua / LongLLMLingua**: prompt compression can reduce token burden while preserving or improving task performance when key information is preserved and positioned well. URL: https://arxiv.org/abs/2310.06839
- **Lossless dictionary-encoding prompt compression**: repetitive structures can be compressed through dictionaries if savings exceed dictionary overhead and equivalence is validated; SkillKernel can use this only for internal analysis prompts or broker hints where the dictionary itself is budget-positive. URL: https://arxiv.org/abs/2604.13066
- **Active Context Compression**: long-running agents require autonomous context/memory management. SkillKernel treats context-loaded artifacts as compiled projections from full-fidelity SkillIR and evidence stores. URL: https://arxiv.org/html/2601.07190v1

### 31.6 Drift, security, and memory-poisoning anchors

- **OWASP Top 10 for LLM Applications**: prompt injection, insecure output handling, supply-chain vulnerabilities, sensitive information disclosure, excessive agency, and insecure plugin design are first-order system risks. URL: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **Skill-Inject**: skill files can serve as persistent prompt-injection carriers; context-aware authorization and scanner gates are required. URL: https://arxiv.org/abs/2602.20156
- **SkillJect**: payloads can be hidden in `SKILL.md` and auxiliary artifacts; scanner, trace, and deterministic writer gates are non-optional. URL: https://arxiv.org/html/2602.14211v2
- **Malicious Agent Skills / ToxicSkills / harmful-skill analyses**: skills can be dangerous through capability amplification, local privilege, dynamic fetch/execute, or credential exposure even without obvious prompt injection.
- **ToolHijacker**: attacks can target tool retrieval and selection; runtime broker and tool-call boundary checks must be monitored. URL: https://www.ndss-symposium.org/ndss-paper/prompt-injection-attack-to-tool-selection-in-llm-agents/
- **MemSkill**: memory extraction, consolidation, and pruning can themselves be skill-like routines that evolve; SkillKernel keeps memory-building governed, typed, and versioned rather than static summarization. URL: https://arxiv.org/abs/2602.02474
- **MemMorph / eTAMP / memory-poisoning work**: persistent memories can steer tool selection and future reasoning across sessions; memory quarantine, provenance, declassification, revocation traversal, and negative controls are required. URLs: https://arxiv.org/html/2605.26154v1 and https://arxiv.org/html/2604.02623v2
- **AttriGuard / CausalArmor / AgentSentry / intent-to-execution integrity work**: high-risk actions should record causal attribution and verify that user intent, not poisoned context, caused the action.
- **MOSS / runtime-governance / self-evolving-agent work**: evolution must be evidence-batched, staged, verified, versioned, and rollbackable. V1 must not autonomously rewrite the plugin, scheduler, scanner, evaluator, compiler, migrations, or policy engine.

### 31.7 Research-to-design traceability matrix

| Research or platform finding | Final design response |
|---|---|
| OpenClaw skills are context-loaded `SKILL.md` artifacts. | SkillKernel emits normal OpenClaw skills; SkillIR remains canonical; `SKILL.md` is compiled runtime output. |
| OpenClaw hooks are in-process and timeout-sensitive. | Plugin is thin; sidecar owns slow autonomous work. |
| OpenClaw Cron is user/Gateway-facing automation. | Sidecar-owned Postgres scheduler; no OpenClaw Cron dependency. |
| Skill Workshop is useful but unstable as a dependency. | Treat as prior art only; SkillKernel owns proposal, scanner, evaluator, writer, archive, and promotion. |
| Self-generated skills can be neutral or harmful. | Evidence maturity ladder, intervention tests, regression gates, and canary monitoring. |
| Skill libraries degrade as they grow. | Active-bank budgets, runtime broker, no-skill decision, shadowing checks, graph expansion, and marginal-value curation. |
| Names/descriptions are insufficient for routing. | Body-aware indexing over SkillIR, compiled text, contracts, probes, and support summaries. |
| Retrieval, incorporation, and execution fail separately. | Broker logs retrieved/loaded/ignored/used/missing/harmful/useful outcomes independently. |
| Co-used skills may represent higher-order workflows. | First-class composition candidates, co-usage edges, sequence mining, and composed-vs-component trials. |
| Broad skills can become black-hole routers. | First-class decomposition candidates, partial-use clustering, false-positive load metrics, and split-vs-original trials. |
| Free-form Markdown is ambiguous and verbose. | SkillIR, deterministic compiler, required runtime sections, and AI-facing compressed style. |
| Context is finite and long context degrades. | Context Compiler + Token Budget Governor; every context-loaded token must justify marginal value. |
| Compression can lose task-critical meaning. | Semantic-equivalence probes, information-preservation checks, and rollback on compression regressions. |
| Tool/API/package behavior drifts. | Executor profiles, environment contracts, drift probes, and localized repair operations. |
| Skill files and support artifacts are supply-chain inputs. | Capability manifests, static/dynamic scanners, hash manifests, taint propagation, deterministic writer, quarantine, rollback. |
| Memory can be poisoned and persist. | Memory quarantine, provenance, declassification, revocation traversal, and negative controls. |
| Unsafe actions can be caused indirectly. | Action-attribution logs and high-risk boundary checks. |
| Rollback can leave derived state behind. | Evolution transactions covering DB state, files, embeddings, caches, memories, broker hints, probes, and derived artifacts. |
| LLM reasoning is useful but nondeterministic. | LLM proposes structured plans; deterministic infrastructure validates, decides, writes, schedules, archives, and rolls back. |
| Context-loaded skill docs are AI-facing, not human-facing. | No-human-prose gate; compact runtime interface; full details remain in SkillIR/Postgres. |
| Reliable composition requires precondition-effect structure. | SkillIR effect signatures, typed graph edges, component compatibility checks, node-level verification, and localized repair. |
| One-off reflection can overfit. | Diagnostic momentum store, contrastive support counts, counterevidence, targeted probes, and patch thresholds. |
| Autonomous control-plane behavior must be explainable across services. | Trace spine with `trace_id`, `span_id`, span links, safe attributes, audit linkage, and optional OpenTelemetry export. |

---


---

## 31A. Comprehensive landscape assimilation matrix

This appendix records the final source-by-source ingestion pass. SkillKernel does not depend on these projects or papers. They inform design pressure, failure modes, and implementation requirements.

| Source | Useful finding | SkillKernel adoption | Not adopted / reason |
|---|---|---|---|
| AutoSkill — Experience-Driven Lifelong Learning via Skill Self-Evolution, ECNU-ICALK | Real interactions and OpenClaw trajectories can be converted into reusable skills; similar-skill search and `discard/improve/merge/create` decisions are practical. | Keep transcript/trajectory evidence mining, active/archived matching, duplicate prevention, and create/improve/merge decisions. | Do not depend on AutoSkill runtime; SkillKernel needs its own sidecar scheduler, Postgres governance, scanner, broker, context compiler, and rollback. URL: https://github.com/ECNU-ICALK/AutoSkill |
| AutoSkill paper, arXiv:2603.01145 | Repeated interaction experience should become explicit maintainable skills, not only memory. | Confirms SkillKernel’s evidence-to-SkillIR path. | AutoSkill’s human-readable/editable stance is weaker than SkillKernel’s AI-facing compiled artifact stance. URL: https://arxiv.org/abs/2603.01145 |
| SkillOpt | Natural-language skill documents can be optimized through rollouts, reflection, bounded edits, rejected-edit buffers, and held-out validation. | Adopt bounded edit budgets, patch rejection memory, held-out validation, and strict improvement gates. | Do not collapse SkillKernel into a single `best_skill.md` optimizer; SkillKernel manages a full library topology and runtime broker. URL: https://github.com/microsoft/SkillOpt |
| SkillOpt paper, arXiv:2605.23904 | Text-space optimization can be stable when edits are bounded and accepted only after validation improvement. | Add bounded deltas and validation gate discipline to skill improvement. | Do not add per-operation model routing or training-like cost optimizer. URL: https://arxiv.org/abs/2605.23904 |
| MUSE-Autoskill | Skills should be long-lived assets with creation, memory, management, evaluation, and refinement. | Confirms full lifecycle and per-skill memory/evidence stores. | Do not depend on MUSE code; SkillKernel uses Postgres/pgvector/OpenClaw sidecar architecture. URL: https://arxiv.org/abs/2605.27366 |
| SkillX | Multi-level skill libraries distinguish planning, functional, and atomic skills; expansion and refinement improve transfer. | Add granularity labels and compose/decompose across levels. | Do not proactively expand skills without evidence maturity and scanner/evaluator gates. URL: https://arxiv.org/abs/2604.04804 |
| SkillRL | Successful trajectories and failed trajectories can become hierarchical skill banks with general and task-specific guidance. | Add scope labels and contrastive success/failure evidence. | Do not use RL training in v1; only log future curator-learning data. URL: https://github.com/aiming-lab/SkillRL |
| EvoSkill | Failed trajectories are rich sources for reusable coding-agent skills. | Weight failure clusters and repeated tool failures as discovery evidence. | Failure alone does not activate skills; require intervention/regression validation. URL: https://github.com/sentient-agi/EvoSkill |
| EvoSkills / CoEvoSkills | Multi-file skills need iterative generation plus a separately evolving surrogate verifier. | Add co-evolved verifier/probe lane and multi-file package discipline. | Do not allow verifier-generated probes to become sole acceptance authority. URL: https://arxiv.org/abs/2604.01687 |
| SkillClaw | Cross-user interaction streams can drive collective skill evolution. | Preserve tenant/workspace provenance and future opt-in federation seam. | No default cross-user/global sharing in v1 due to privacy, poisoning, and license risk. URL: https://arxiv.org/abs/2604.08377 |
| HiSME | The skill-evolving procedure itself can be improved from execution traces. | Collect meta-evolution telemetry; broker policy artifacts may be versioned/canaried. | No autonomous rewriting of sidecar/plugin/scheduler/scanner/evaluator/compiler code in v1. URL: https://arxiv.org/abs/2605.28390 |
| SkillRouter | Metadata-only routing loses critical body details; routing systems need full body access. | Broker indexes SkillIR, compiled body, contracts, probes, manifests, and support summaries. | Runtime context remains compressed; full body is for broker/ranker, not automatic prompt injection. URL: https://arxiv.org/abs/2603.22455 |
| SkillsInjector | Skill injection is dynamic context construction: which skills, how many, and how they are rendered all matter. | Confirms runtime skill-context broker, adaptive budget, set-aware rendering, shadowing control. | Do not add learned planner dependency in v1; start with deterministic scoring plus logged data. URL: https://arxiv.org/abs/2605.29794 |
| Graph of Skills | Offline graph construction plus hybrid semantic/lexical seeding and graph rerank retrieves small dependency-aware bundles. | Add graph-aware retrieval expansion and context-budgeted hydration. | Do not require MCP dependency; implement inside sidecar/broker. URL: https://github.com/davidliuk/graph-of-skills |
| GraSP | Skill orchestration is a graph/DAG problem with preconditions, effects, node verification, and local repair. | Confirms SkillGraphIR, effect signatures, verifier nodes, local repair. | Do not force every task into executable DAG; use graph structure where evidence supports composition. URL: https://arxiv.org/abs/2604.17870 |
| SkillGraph | Directed graphs with prerequisite, enhancement, and co-occurrence edges support compositional tasks and maintenance decisions. | Strengthens topology edges and compose/decompose policies. | Do not add RL policy training in v1. URL: https://arxiv.org/abs/2605.12039 |
| Graph-of-Skills paper | Semantic retrieval can miss prerequisite chains; dependency-aware structural retrieval addresses incomplete bundles. | Add prerequisite expansion and graph neighbor features to broker. | Keep pgvector/hybrid retrieval as candidate generator, not sole authority. URL: https://arxiv.org/abs/2604.05333 |
| SkillReducer | Large public skill ecosystems contain routing/body token waste; compression can improve quality through less distraction. | Elevate context compiler and token budget governor; reject bloat and non-actionable prose. | Do not blindly delta-debug production artifacts without semantic equivalence/regression gates. URL: https://arxiv.org/abs/2603.29919 |
| SkillSmith | Compiling skills into boundary-guided executable interfaces improves reliability and reduces token/runtime overhead. | Keep compiled `WHEN/INPUTS/DO/VERIFY/FAIL/NEVER` runtime artifact. | Do not abandon OpenClaw `SKILL.md`; render compact OpenClaw-compatible output from SkillIR. URL: https://arxiv.org/html/2605.15215 |
| Skill-as-Pseudocode | Typed pseudocode and deterministic checks improve clarity and reduce prose ambiguity. | Adopt typed contracts and coverage/binding/replacement/risk checks. | Runtime pseudocode is compiled artifact, not canonical source; SkillIR remains source. URL: https://arxiv.org/html/2605.27955 |
| Formal Skill | Runtime-native skills with schemas/executors/hooks can reduce prompt burden and improve enforceability. | Use deterministic helper scripts and guard templates with manifests/capability declarations. | Do not make SkillKernel a custom non-OpenClaw runtime; OpenClaw compatibility remains required. URL: https://arxiv.org/html/2605.19604 |
| SkVM | Skills depend on model-harness capabilities; compilation/environment binding can reduce token consumption and improve portability. | Keep executor profiles and model/embedding qualification gates. | Do not implement full VM/JIT in v1. URL: https://arxiv.org/abs/2604.03088 |
| From Skill Text to Skill Structure | Skill text entangles scheduling, structure, and logic; structured representation improves discovery and risk assessment. | Confirms SkillIR fields and SkillGraphIR. | Do not rely only on Markdown parsing after generation. URL: https://arxiv.org/html/2604.24026 |
| SkillsVote | Governed lifecycle needs structured library search, subtask decomposition, outcome attribution, and evidence-gated updates. | Confirms credit ledger, action attribution, and helped/hurt/ignored/missing states. | Do not indiscriminately update from all successful traces. URL: https://arxiv.org/abs/2605.18401 |
| Trace2Skill | Broad trajectory pools, parallel analysis, and conflict-free consolidation beat sequential overfitting to one trace. | Adopt batch consolidation and conflict checks. | Single-turn persistent mutation only for explicit user instruction or severe safety rollback. URL: https://arxiv.org/html/2603.25158 |
| SkillGen | Contrast successful and failed trajectories; treat skills as interventions and verify net effect. | Confirms contrastive evidence and intervention trials. | Do not accept generic summarization as skill creation. URL: https://arxiv.org/html/2605.10999 |
| SkillLearnBench | Continual skill learning gains are inconsistent; stronger LLMs do not always produce better skills; self-feedback alone drifts. | Keep model qualification, external feedback preference, and no self-feedback-only mutation. | Do not assume the configured “best” model makes safe skills automatically. URL: https://arxiv.org/abs/2604.20087 |
| SkillFlow | High skill usage does not necessarily imply utility; repair and maintenance must be evaluated over time. | Keep no-skill baseline, utility attribution, and long-horizon metrics. | Do not equate load count with skill value. URL: https://arxiv.org/abs/2604.17308 |
| SkillOS | Skill curation is a delayed-feedback long-horizon policy problem. | Log curator-learning features and delayed outcomes. | Do not train/RL-optimize curator in v1. URL: https://arxiv.org/abs/2605.06614 |
| SkillOps | Skill libraries accumulate technical debt; maintenance actions include merge, repair, retire, add-validator, add-adapter. | Confirms library-health scans and first-class maintenance operations. | Do not rely on manual cleanup. URL: https://arxiv.org/html/2605.13716 |
| SWE-Skills-Bench | Many real SWE skills show zero or negative marginal utility and large token overhead. | Preserve no-skill baselines, token-budget rejection, and version-compatibility checks. | Do not activate plausible skills without marginal-value evidence. URL: https://arxiv.org/abs/2603.15401 |
| SkillsBench | Curated skills often help, self-generated skills do not reliably help, deterministic verifiers are central. | Keep deterministic evaluation and curated/evidence-gated acceptance. | Do not use LLM-as-judge as sole production gate. URL: https://arxiv.org/abs/2602.12670 |
| OpenSkillEval | Evaluation should adapt to evolving real-world artifacts and compare with/without skill across agent systems. | Add benchmark/validator adapter seam and executor-profile-aware evals. | Do not hard-code one benchmark suite. URL: https://arxiv.org/html/2605.23657 |
| skill-validator | Spec compliance is only baseline; validate links, token counts, content quality, non-standard files. | Add scanner checks for token counts, broken links, layout, language contamination, quality flags. | Do not depend on external validator binary in core. URL: https://github.com/agent-ecosystem/skill-validator |
| skillgrade | Skill changes need regression tests that verify discovery and use. | Add external grader adapter and discovery/use probes. | Do not require CI integration in v1 sidecar. URL: https://github.com/mgechev/skillgrade |
| Agent Skills specification | Skills are folders with `SKILL.md`, metadata, instructions, and optional scripts/resources; long files should split referenced content. | Emit standard skills and classify support artifacts. | Do not treat support files as free prompt budget. URL: https://agentskills.io/specification |
| Anthropic Agent Skills docs/blog | Progressive disclosure, scripts, resources, and deterministic code are core usage patterns. | Keep compiled compact `SKILL.md` plus manifest-bound deterministic support files. | Do not optimize for human tutorial-style Markdown. URL: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills |
| GitHub `gh skill` tooling | Skill packages are becoming versioned distributable artifacts with validation and immutable releases. | Keep manifests, hashes, immutable active packages, and release-like provenance. | Do not make v1 a public package manager. URL: https://github.blog/changelog/2026-04-16-manage-agent-skills-with-github-cli/ |
| OpenAI Codex Agent Skills docs | The open Agent Skills standard is becoming cross-agent. | Preserve SKILL.md compatibility to avoid ecosystem isolation. | Do not depend on Codex-specific behavior. URL: https://developers.openai.com/codex/skills |
| Microsoft Agent Skills docs | Skills are portable packages with progressive disclosure. | Reinforces open-standard artifact strategy. | Do not depend on Microsoft agent framework. URL: https://learn.microsoft.com/en-us/agent-framework/agents/skills |
| HarmfulSkillBench | Harmful skills exist in open ecosystems and can reduce model refusal behavior. | Keep harmful-capability classifier, policy gates, and context-bundle safety scanning. | Do not assume generated/internal skills are harmless. URL: https://arxiv.org/abs/2604.15415 |
| Skill-Inject / SkillJect | Prompt injection can be hidden in skill files and automated against skill-enabled agents. | Keep hidden content bans, semantic scanner, taint propagation, and no untrusted text-to-runtime promotion. | Do not load external skills into active SkillKernel ownership without import scan. URL: https://arxiv.org/abs/2602.20156 |
| AgentTrap | Malicious skills can disguise harmful side effects inside normal workflows. | Add runtime action attribution and tool-call boundary checks. | Do not rely on prompt refusal alone. URL: https://arxiv.org/abs/2605.13940 |
| Malicious Agent Skills in the Wild | Real registries contain malicious/vulnerable skills distributed with user-level privileges. | Treat skills as supply-chain artifacts; require manifests, hashes, capabilities, scans. | Do not trust public registry artifacts. URL: https://arxiv.org/abs/2602.06547 |
| SkillProbe / hierarchical malicious-skill triage | Atomic scanners miss combinatorial and natural-language attacks. | Scan composed bundles and broker-rendered context, not only individual files. | Do not rely only on regex or static code analyzers. URL: https://arxiv.org/html/2603.21019 |
| BadSkill | Bundled models or artifacts inside skills can carry backdoors. | Restrict helper artifacts, declare capabilities, hash files, and block opaque bundled models in v1 unless explicitly allowed. | Do not allow arbitrary model-in-skill payloads. URL: https://arxiv.org/html/2604.09378 |
| Sleeper Memory Poisoning / MemoryGraft / AgentPoison / MemMorph | Persistent memory and retrieval stores can become durable attack surfaces influencing future behavior. | Keep memory quarantine, taint, provenance, delayed activation, derived-data revocation, and control-flow integrity logs. | Do not let raw untrusted text become skill memory or runtime instruction. URLs: https://arxiv.org/abs/2605.15338, https://arxiv.org/html/2512.16962v1, https://openreview.net/forum?id=Y841BRW9rY |
| OWASP LLM risks and SLSA | LLM applications need supply-chain, data-poisoning, plugin design, excessive-agency, and provenance controls. | Keep fail-closed policy, SLSA-style manifests, audit hash chains, and deterministic writer. | Do not expose autonomous mutation without rollback-complete provenance. URLs: https://genai.owasp.org/, https://slsa.dev/ |

### 31A.1 Final v16 closure assessment

The landscape contains many useful mechanisms, but no source provides a complete control plane for SkillKernel’s target. The main lesson is negative as much as positive: systems that can generate skills are common; systems that can govern, attribute, compress, route, secure, evaluate, compose, decompose, and roll back an autonomous skill library are still the hard part.

The adopted SkillKernel stance is therefore:

```text
Generate less.
Validate more.
Compile tighter.
Route smarter.
Attribute causally.
Evolve transactionally.
Compose/decompose topology deliberately.
Treat every context token and every support artifact as production surface area.
```

No further pre-implementation conceptual expansion is recommended after v16. New changes should now originate from implementation seam failures, OpenClaw API validation, benchmark failures, security red-team findings, or production telemetry.


## 32. Final recommendation and closure

Proceed to implementation with the v16 design.

The top-level architecture is closed:

```text
one OpenClaw plugin
one Python sidecar
one Postgres database
one autoskill schema
pgvector
SkillIR as canonical source of truth
OpenClaw SKILL.md as compiled runtime artifact
sidecar-owned scheduler
runtime skill-context broker
context compiler + token budget governor
diagnostic momentum store
SkillIR effect signatures
SkillGraphIR for composed/decomposed workflow topology
ephemeral candidate lane
co-evolved verifier/probe lane
external benchmark/validator adapter seam
runtime immutability lock
trace-spine observability
operator-configurable text LLM profile
operator-configurable embedding profile
model/embedding profile qualification gates
SLSA-style artifact provenance manifests
no direct dollar-cost tracker/analyzer
no per-operation model-routing matrix in v1
no per-skill databases
no per-skill schemas in v1
no OpenClaw Cron dependency
no Skill Workshop dependency
```

The core product definition is closed:

```text
SkillKernel is an autonomous evidence-driven skill-library topology optimizer for OpenClaw.

It collects rich session/chat-turn/tool/outcome evidence and uses that evidence to perform four first-class autonomous topology operations:

create      = add a missing useful skill
improve     = modify an existing useful skill
compose     = build a higher-order workflow skill from repeatedly co-used smaller skills
decompose   = split a broad/clunky skill into sharper reusable skills
```

The final context-management addition remains non-optional: **context management is a hard architectural invariant**. Anything that can enter the running agent context is a compiled AI-facing runtime artifact, not human documentation. The full-fidelity source of truth is SkillIR plus Postgres evidence. `SKILL.md`, broker hints, runtime snippets, and any support material eligible for context loading must be scrutinized token-by-token for semantic density, execution value, safety, routing value, verification value, and marginal value per token. Verbose explanation, rationale, history, human-readable commentary, raw transcript fragments, duplicated constraints, and unmeasured examples are forbidden in runtime artifacts unless they measurably improve execution.

The final implementation order is:

```text
redaction
→ storage
→ executor profiles
→ scheduler
→ trace spine
→ evolution transaction/provenance/revocation tables
→ event/evidence/memory pipeline
→ memory quarantine
→ external-skill inventory
→ body-level index documents
→ retrieval logs
→ context artifact registry
→ token budget governor
→ semantic compression/equivalence gates
→ scanner
→ evaluator/probes
→ deterministic writer
→ rollback
→ action-attribution logs/checks
→ SkillIR effect-signature validation
→ SkillIR compiler
→ diagnostic momentum store
→ runtime broker
→ topology operation candidate generation
→ composition/decomposition evaluators
→ autonomous apply
→ marginal-value curation
→ broker policy canaries
```

The implementation warning is unchanged: **do not build autonomous skill writing first**. Build the control plane first. Autonomous mutation should begin only after redaction, storage, scheduler, trace spine, scanner, evaluator, deterministic writer, rollback, evolution transactions, provenance/revocation traversal, context compiler, token budget governor, SkillIR effect-signature validation, diagnostic momentum, audit, memory quarantine, executor profiles, action attribution, context attribution, and broker versioning exist.

As of this pass, no further pre-implementation conceptual design change is recommended. The remaining implementation-hardening elements were explicit SkillIR effect signatures, diagnostic-momentum improvement state, trace-spine observability, model/embedding profile qualification gates, SkillGraphIR for composed/decomposed workflows, and provenance manifests for generated artifacts. Those are now integrated. Further changes should come from OpenClaw API seam validation, implementation findings, benchmark failures, red-team findings, or production telemetry.
