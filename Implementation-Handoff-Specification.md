# SkillKernel — Comprehensive Implementation Handoff Specification

**Document type:** implementation handoff specification
**Date:** 2026-06-04
**Status:** authoritative implementation specification and soak-test baseline
**Project:** SkillKernel, an OpenClaw plugin + autonomous sidecar container for evidence-driven skill creation, improvement, composition, decomposition, curation, historical session/memory ingestion, AI-facing context compilation, operator-configurable LLM/embedding access, runtime skill-context control, token-budget governance, and reversible skill-library governance.
**Architecture:** one OpenClaw plugin, one Python sidecar, one Postgres database, one `autoskill` schema, pgvector, logical skill ownership by `skill_id`, canonical SkillIR as source of truth, governed skill-package artifact planner, deterministic context compiler/renderers that emit token-budgeted OpenClaw `SKILL.md` plus optional manifest-bound ancillary artifacts, historical backfill importer for existing OpenClaw deployments, SkillIR effect signatures, diagnostic-momentum improvement store, trace-spine observability, operator-configurable text-model access profile, operator-configurable embedding access profile, model/embedding profile qualification gates, governed raw-evidence vault, autonomous semantic adjudication engine, calibrated selective-trust controller, autonomy calibration corpus, automatic redacted-intent synthesis, SkillGraphIR for composed/decomposed workflow topology, SLSA-style artifact provenance manifests, no direct cost-tracker/analyzer, no per-operation model-routing matrix in v1, no per-skill databases, no per-skill schemas in v1, no OpenClaw Cron dependency, no Skill Workshop dependency.

---

## 0. Executive implementation specification

Build **SkillKernel** as an autonomous skill operating system for OpenClaw. The implementation may keep `autoskill` as the internal database/schema namespace, but the project-level concept is SkillKernel.

The system continuously captures live OpenClaw usage, ingests existing historical OpenClaw session/memory/workspace evidence when deployed into an established installation, extracts durable procedural evidence, converts repeated workflows/failures/corrections into evaluated skills, improves SkillKernel-owned skills from grounded usage data, compiles skill text into compact AI-facing runtime interfaces, controls which skills are visible or emphasized, archives low-value skills, promotes archived skills when demand recurs, merges duplicates, detects drift, and rolls back degraded changes.

The system is autonomous by default and bounded by calibrated guardrails. Administrative escalation is not part of the normal maintenance loop. Control comes from configured evidence-retention policy, a governed raw-evidence vault, redaction/declassification gates, taint tracking, autonomous LLM semantic adjudication, risk-weighted decision bands, scanner gates, evaluator gates, regression budgets, skill-context budgets, audit trails, canarying, rollback, quarantine, and freeze semantics. Deterministic thresholds exist as policy instruments, not brittle constants: hard gates protect safety, integrity, privacy, reversibility, and runtime compatibility; soft thresholds are calibrated, configurable, evidence-aware, and allowed to trigger more evidence collection, more probes, narrower activation, ephemeral trials, or LLM re-adjudication before escalation. The system must collect enough full-fidelity evidence to let a qualified LLM infer user intent and operational meaning for autonomous skill management. Privacy controls restrict access, retention, exposure, and derivation; they do not remove the semantic substrate required for autonomy when the deployment has enabled full autonomous mode.

The end-to-end loop is:

```text
OpenClaw event or historical datasource
→ plugin hook capture or sidecar historical importer
→ evidence-fidelity classification
→ raw-evidence vault capture when policy permits
→ redaction + tainting for analytics/indexing paths
→ local spool or sidecar ingest
→ event/import-source normalization
→ immutable evidence extraction
→ autonomous intent reconstruction and declassification when needed
→ governed memory derivation
→ active/archived skill matching
→ context-loadability classification
→ runtime skill-context calibration
→ action selection:
     no-op | create | improve | compose | decompose | compile | repair | merge | archive | promote | rollback | freeze
→ autonomous LLM semantic adjudication for ambiguous intent/topology/privacy cases
→ structured SkillIR change plan
→ SkillIR validation + static + semantic + capability scan
→ target + regression + adversarial evaluation
→ deterministic context compile + token-budget gate + staged file write
→ atomic activation/archive/promotion
→ canary observation
→ keep | repair again | roll back | freeze
→ utility, attribution, memory, retrieval, drift, and audit updates
```

The model-access design is intentionally simple: SkillKernel has one configured text LLM profile and one configured embedding profile. It supports either OpenClaw-routed calls or direct OpenAI-compatible `/v1` calls. It does not implement a direct dollar-cost tracker/analyzer or a per-operation model-routing matrix in v1.

The architecture is:

```text
OpenClaw runtime
  └─ SkillKernel plugin, TypeScript
       ├─ registers in-process OpenClaw hooks
       ├─ captures typed event envelopes
       ├─ captures full-fidelity event envelopes according to evidence-retention policy
       ├─ stores raw content only in an encrypted governed spool/vault path when enabled
       ├─ redacts, taints, and minimizes analytics/indexing payloads before normal persistence or forwarding
       ├─ spools locally when the sidecar is unavailable
       ├─ forwards batches to localhost sidecar
       ├─ exposes status/control/diagnostic commands
       ├─ optionally contributes a small runtime skill-context hint from sidecar cache
       ├─ verifies active/archive roots
       └─ never runs slow LLM analysis in hooks, schedules maintenance, or writes arbitrary files; may run a narrow OpenClaw LLM relay outside hooks when explicitly configured

SkillKernel sidecar, Python
  ├─ authenticated ingest/control API
  ├─ durable Postgres-backed scheduler
  ├─ durable Postgres-backed job queue with leases and idempotency
  ├─ event normalizer and evidence extractor
  ├─ governed raw-evidence vault manager and access auditor
  ├─ autonomous semantic adjudication engine
  ├─ calibrated selective-trust controller and autonomy calibration corpus manager
  ├─ redacted-intent and replay-corpus builder
  ├─ historical datasource discovery and backfill importer
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
       ├─ append-only event, historical import, evidence, and audit records
       ├─ encrypted raw-evidence records, declassification reports, and raw-access audit logs
       ├─ autonomous semantic adjudications, calibration records, and intent-interpretation records
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

## 1. Architecture requirements and control-plane invariants

SkillKernel is defined by the following architecture requirements and control-plane invariants. These requirements are normative for implementation and take precedence over lower-level examples when conflicts appear.

| Area | Requirement | Implementation consequence |
|---|---|---|
| Source of truth | Use **canonical SkillIR** as the internal source of truth. | `SKILL.md` is not the internal canonical representation. It is a generated OpenClaw runtime artifact. All creation, improvement, curation, drift, retrieval, evaluation, and rollback operate over SkillIR revisions. |
| Evidence fidelity | Preserve enough original user/agent/tool context to reconstruct intent for autonomous skill management when the deployment enables full autonomy. | Full-fidelity prompt, response, tool, and context windows go to a governed raw-evidence vault with encryption, retention, access policy, taint labels, and audit. Redacted/minimized derivatives feed analytics, embeddings, replay, and skill synthesis. Hash-only telemetry is a degraded mode, not the full-autonomy path. |
| Privacy-preserving autonomy | Treat privacy as governed access and derivation, not blanket semantic erasure. | Store raw evidence only under configured policy; redact before embedding and ordinary analytics; expose only the minimum raw window to the configured LLM profile when an autonomous reasoning job requires original intent. Every raw access has purpose, job, model profile, retention class, and audit record. |
| Autonomous semantic adjudication | Use the configured LLM to resolve semantic tasks that deterministic code cannot resolve with high fidelity. | Replay-corpus intent labeling, memory declassification, ambiguous topology choice, external-skill relationship classification, skill-synthesis plan generation, and context-equivalence reasoning are LLM-adjudicated first. Administrative escalation is reserved for policy-forbidden, low-confidence after autonomous fallback, contradictory, privacy-sensitive, or irreversible cases. |
| Calibrated selective trust | Trust LLM semantic decisions according to calibrated outcome evidence, not raw model confidence. | Every semantic verdict records a confidence decomposition, calibration bucket, uncertainty checks, deterministic admissibility checks, and delayed outcome labels. High-confidence semantic decisions can proceed autonomously when hard invariants pass and the selected action is reversible, canaried, or otherwise policy-admissible. |
| Dynamic soft-threshold scaling | Treat soft thresholds as risk-aware control surfaces rather than constants. | Thresholds scale by operation kind, risk, reversibility, source fidelity, executor profile, model-profile calibration, and workspace policy. Soft-threshold misses trigger autonomous uncertainty-reduction actions before escalation. |
| Skill compiler | Implement deterministic **SkillIR → OpenClaw renderers** and optional renderers for broker hints, probes, manifests, and support-file manifests. | LLMs may author structured semantic verdicts and SkillIR change plans. Deterministic code validates, normalizes, scans, renders, token-budgets, hashes, stages, and rolls back outputs. |
| Skill package planner | Treat optional files beside `SKILL.md` as first-class compiled artifacts, not incidental extras. | SkillKernel may generate scripts, references, templates, schemas, small immutable data, assets, examples, tests, probes, contracts, and inert adjunct requests only when evidence shows net value. Each support artifact has a loadability class, capability declaration, hash, tests or validation where applicable, and manifest entry. Generated skill packages cannot self-register OpenClaw hooks, OpenClaw Cron routines, tools, services, MCP servers, or mutable local stores; those needs become inert adjunct requests or administrative integration requests. |
| Skill text | Represent runtime instructions as **typed contracts and pseudocode-like runtime interfaces**. | Runtime instructions use fixed fields: `WHEN`, `INPUTS`, `PRECONDITIONS`, `DO`, `OUTPUTS`, `EFFECTS`, `TOOL TEMPLATES`, `VERIFY`, `FAIL`, `DO NOT USE WHEN`, and `NEVER`. Free-form prose is discouraged. |
| Runtime controls | Support **guard templates**, not arbitrary generated programs. | Skills may select from deterministic preapproved runtime guard templates such as preflight check, verify-only check, capability warning, sibling-disambiguation hint, or drift-block. LLMs cannot write executable guard logic. |
| Retrieval | The broker performs **hybrid retrieval + graph expansion + context compilation**. | Retrieve candidate skills, expand prerequisite/conflict/supersession/shadow edges, hydrate the minimal useful subunits, render a set-aware context under budget, and track shadowing outcomes. |
| Skill creation | Require **contrastive and intervention evidence**. | New skills are accepted only when success/failure contrasts and with/without-skill probes show net benefit inside regression limits. |
| Skill improvement | Use **evidence-gated, regression-aware updates**. | LLM self-feedback alone cannot mutate a skill. Patches need grounded evidence, target probes, regression probes, shadowing checks, scanner pass, and canary pass. |
| Memory | Use **memory-contract and poisoning defenses**. | Long-term evidence/memory is typed, provenance-scored, taint-aware, TTL-governed, and declassified only through verifier-backed transformations. External imperatives never become runtime instructions directly. |
| Security | Apply **skill supply-chain scanning**. | Ban hidden comments, invisible Unicode, bidi controls, dynamic fetch-exec patterns, secret exfiltration patterns, unexpected shell/network access, and LLM-controlled paths. Treat every generated artifact as untrusted until scanned and hashed. |
| Schemas | Use **one `autoskill` schema in v1**. | Per-skill schemas are acceptable in theory, but they add dynamic DDL, migration, index, and permission complexity without improving global retrieval, curation, attribution, or promotion. Use logical `skill_id` ownership and partitioning/indexes when scale demands it. |

The implementation posture is: **LLM as autonomous semantic adjudicator inside explicit policy; deterministic infrastructure as acceptance authority; SkillIR as source of truth; `SKILL.md` as compiled OpenClaw-facing artifact; skill topology as the optimized product surface.** Qualified LLM calls may infer intent, classify ambiguity, declassify safe operational meaning, recommend replay-corpus episodes, decide among topology operations, and produce structured plans. Deterministic infrastructure decides whether those LLM decisions are sufficiently grounded, safe, policy-compliant, reversible, and evaluated for autonomous action.

---

### 1.1 System-level requirements

The system-level requirements below prevent long-run failure modes as the skill bank grows, as memories accumulate, and as skills operate under different agents, sandboxes, models, and tool profiles.

| Area | Requirement | Why it matters |
|---|---|---|
| Runtime broker | Treat broker policy as a versioned, evaluated, rollbackable artifact. | Retrieval quality and context construction are independent failure modes. A static broker will decay as the skill bank grows. |
| Skill value | Measure marginal value with `skill-hidden`, `skill-visible`, and `no-skill` controls. | Usage count is not evidence of utility; a frequently loaded skill can be ignored, harmful, or shadowing a better skill. |
| Executor profiles | Evaluate and route skills against explicit executor profiles: model family, agent backend, sandbox, OS, available tools, binaries, API contracts, and permissions. | A skill that works under one harness can fail under another because tool semantics, context policy, or filesystem/shell behavior differs. |
| External skills | Inventory non-SkillKernel skills for collision, shadowing, and risk, but never mutate them autonomously. | The broker cannot avoid collisions if it only sees SkillKernel-owned skills. Autonomy must still respect ownership boundaries. |
| Memory | Add quarantine, delayed activation, provenance gates, and control-flow integrity auditing for memories that can affect retrieval, tool choice, or skill mutation. | Memory poisoning can steer future tool selection or skill edits without looking like a direct instruction. |
| Skill composition security | Scan not only individual skill files but also co-loaded skill sets and rendered broker context. | Individually benign skills can become harmful together through shared context, shadowing, or puppet-style redirection. |
| Runtime security | Add deterministic tool-call boundary enforcement hooks where available. | Model-level resistance is not enough for skill-file and tool-semantic attacks; runtime checks must constrain action boundaries. |
| Support artifacts | Allow helper scripts, reference files, templates, examples, structured schemas/data, and static assets only when they improve net utility, reduce context cost, or improve repeatability. | Support files are optional compiled artifacts. They must stay inside the skill directory, use approved directories, be referenced from `SKILL.md` only when agent access is intended, carry loadability/capability metadata in the manifest, and pass scanner/evaluator gates. Executable artifacts require stricter tests and capability-policy validation. |
| Compiler verifier | Require coverage, binding, replacement, and risk checks before rendering `SKILL.md`. | Generated runtime text must cover required SkillIR fields, bind to evidence/contracts, avoid vague replacements, and preserve security boundaries. |
| Batch consolidation | Periodically run holistic batch consolidation across recent candidates, not only incremental per-event updates. | Trace-level work shows that transferable skills often require cross-episode comparison and conflict resolution. |
| Historical ingestion | Treat existing sessions, trajectories, memories, workspace context, and task ledgers as first-class evidence sources. | Established deployments contain months of procedural signal. Fresh SkillKernel installs must bootstrap from that history without bypassing redaction, tainting, evidence maturity, or evaluation gates. |
| Intent reconstruction | Capture and preserve the original semantic intent needed to explain why the agent acted. | Redacted summaries alone are insufficient for replay, attribution, and skill synthesis. The system stores raw-evidence pointers and creates LLM-generated redacted intent records that remain linked to source prompts/tool windows through provenance. |
| Dynamic probes | Generate artifact-grounded probes from real failures, contracts, and drift events, then retire stale probes. | Static tests miss environment drift and overfit; probes must follow the actual operating surface. |
| Per-skill schemas | Keep the v1 decision: no per-skill databases and no per-skill schemas. | Per-skill schemas remain acceptable only as a later strict-isolation migration if measured constraints justify them. They do not improve v1’s core mechanisms. |

These requirements establish the governing principle: **the skill library, the broker, the memory layer, and the evaluator are all versioned systems. Skills are not the only artifacts that can improve or regress.**

### 1.2 Transaction, attribution, and revocation requirements

The following implementation details are first-release requirements, not optional polish.

| Area | Requirement | Implementation consequence |
|---|---|---|
| Evolution transaction | Every autonomous mutation is a single **evolution transaction** spanning DB rows, SkillIR revision, compiled files, manifests, embeddings, retrieval caches, broker cache invalidation, probe additions, lifecycle state, and audit entries. | Rollback must restore the whole effective state, not only the filesystem artifact. No orphan embeddings, stale broker hints, active compiled text, or unrevoked derived memories may survive a rollback. |
| Ephemeral trial workspace | Candidate skill versions, broker-policy versions, and support artifacts are evaluated in an isolated trial workspace/profile before activation. | Evaluation cannot mutate the real active skill root, scheduler state, production embeddings, or production memory. Candidate artifacts are promoted only after scanner, trial replay, regression probes, and activation checks pass. |
| Action attribution gate | Risky tool calls and state mutations influenced by skills, memories, broker context, or retrieved artifacts require deterministic attribution logging and, where feasible, counterfactual/attenuated replay. | A skill/memory/broker hint that materially causes an action unsupported by the user goal is marked harmful, triggers rollback/freeze, and becomes negative evidence. |
| Body-aware routing | Retrieval and reranking must have access to the full SkillIR, compiled runtime text, support-file manifests, and significant non-secret support-file content. | Names and descriptions are insufficient routing signals. The model-facing runtime context remains compact, but the broker/reranker must index and inspect the full body-level skill representation. |
| No-skill as policy action | The broker must be able to select `no_skill`, `defer_skill`, or `skill_hidden` explicitly. | Loading a skill is not always beneficial. The system must measure when not loading a skill improves outcome, latency, safety, or token cost. |
| Evidence maturity ladder | Evidence gets a maturity state: `observed`, `recurring`, `contrastive`, `intervention_validated`, `regression_validated`, `canaried`, `production_verified`, or `revoked`. | Recurrence alone can propose a candidate; intervention/regression maturity is required for activation; production/canary maturity is required for broad applicability and high active priority. |
| Harmful-capability classifier | Generated and external skills are classified for harmful capability, dual-use risk, unsafe implicit intent, sensitive-data access, credential exposure, and policy-override behavior. | A skill that improves task success but creates harmful capability amplification is quarantined or restricted by capability policy. |
| Core infrastructure immutability | SkillKernel may mutate SkillKernel-owned skills and support artifacts. It must not autonomously rewrite the plugin, sidecar, migrations, scheduler, scanner, evaluator, compiler, or policy engine in v1. | Infrastructure improvement evidence can be logged as administrative integration backlog only. Self-modification of the control plane is out of scope for v1. |
| Derived-data revocation | Retention, deletion, rollback, and quarantine must propagate to derived artifacts: memories, embeddings, evidence links, skill versions, broker logs, compiled files, and cached context hints. | Privacy and rollback are graph operations, not row-level deletes. The system must track provenance edges strongly enough to revoke downstream artifacts. |
| Secret reference discipline | Skills may refer to capability names or environment contract keys, but never raw secrets, credentials, tokens, personal identifiers, or private user facts. | Original prompts/tool outputs may be retained only in the encrypted raw-evidence vault under policy. Redaction happens before embedding, ordinary analytics, skill compilation, and non-vault logs; scanner blocks secret-like material in SkillIR, `SKILL.md`, support files, probes, and normal logs. |
| Change admission criterion | Any future proposed design change must identify a concrete failure mode not already covered by redaction, provenance, evidence maturity, transactionality, scanner, evaluator, broker, rollback, canary, or freeze. | The specification is ready for implementation decomposition. Additional changes should be driven by implementation issues, benchmark evidence, red-team findings, OpenClaw API seam validation, or production telemetry, not speculative pre-implementation expansion. |

This establishes the development principle: **autonomous mutation is allowed only as a rollback-complete transaction whose causal inputs, evidence maturity, compiled artifacts, runtime exposure, and downstream derived state are all versioned and auditable.**


---


### 1.3 Topology operation requirements

SkillKernel is not an automatic skill writer. It is an **evidence-driven skill-library topology optimizer**. The four primary autonomous operations are first-class implementation primitives:

```text
create      = add a missing useful skill
improve     = modify an existing useful skill
compose     = build a higher-order workflow skill from repeatedly co-used smaller skills
decompose   = split a broad/clunky skill into sharper reusable skills
```

This is a non-negotiable product requirement. Creation and improvement operate on individual skill nodes. Composition and decomposition operate on the topology of the skill graph. Curation, archiving, promotion, merge, split, recompile, repair, freeze, and rollback remain supporting operations, but they are not substitutes for the four core topology operations.

| Topology requirement | Implementation consequence |
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

The conceptual model is:

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

Topology operations do not require a separate service or database. They use the existing architecture plus the tables, policies, and acceptance gates needed to implement create, improve, compose, and decompose deliberately.


---

### 1.4 Context-management requirements

Context management is a hard invariant that governs how every skill artifact is authored, evaluated, stored, routed, and activated:

```text
Anything that can enter the running agent's context is a compiled AI-facing runtime artifact.
It is not documentation, not a transcript summary, and not human-oriented prose.
```

This requirement is first-class because context is the scarcest runtime resource in the system. A skill that improves task success but consumes excessive context, triggers false-positive loading, shadows a narrower skill, distracts the model, or injects verbose rationale is not a successful skill. Runtime text must be scrutinized token by token.

| Context-management requirement | Implementation consequence |
|---|---|
| Context-loadable artifacts are compiled artifacts. | `SKILL.md`, skill frontmatter descriptions, broker hints, support-file excerpts, tool templates, verification instructions, failure instructions, and component references must pass the same token, semantic-density, safety, and regression gates. |
| SkillIR/Postgres is the full-fidelity source of truth. | Evidence, rationale, long examples, raw traces, failures, alternatives, and improvement history remain in Postgres/SkillIR. They do not leak into runtime prompt text unless a compiler proves they are operationally necessary. |
| `SKILL.md` is an executable prompt interface, not documentation. | Use terse typed sections such as `WHEN`, `INPUTS`, `DO`, `OUTPUTS`, `EFFECTS`, `VERIFY`, `FAIL`, `NEVER`; ban explanations, historical notes, implementation commentary, and human-readable onboarding prose unless measured useful. |
| Every context-visible word must justify itself. | The compiler computes marginal utility per token, token delta per version, false-positive load cost, ignored-skill token waste, shadowing cost, and composed/decomposed token tradeoffs. |
| Progressive disclosure is allowed but governed. | Support files are not context-free; classify every support artifact as `never_loaded`, `agent_may_read`, `broker_excerpt_only`, `script_only`, `probe_only`, or `operator_only`. Any `agent_may_read` artifact must pass compression and scanner gates. |
| Compression is semantic compilation, not summarization. | LLMs may adjudicate semantic equivalence, author compact wording, and identify redundancy. Deterministic code enforces format, budget, forbidden text, required fields, hashing, scanning, and acceptance. |
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


SkillKernel is a skill lifecycle system, a topology optimizer, and a context-budget governor for autonomous skill libraries.


---

### 1.5 SkillIR, diagnostic momentum, and trace-spine requirements

The following implementation requirements reduce long-run failure modes in autonomous skill evolution.

| Area | Requirement | Why it matters |
|---|---|---|
| **SkillIR effect signatures** | Every SkillIR revision and graph edge must expose compact typed `OUTPUTS`, `EFFECTS`, `STATE DELTA`, `SIDE EFFECTS`, `TERMINATION`, and `IDEMPOTENCY` fields where applicable. | Graph-composition research shows that reliable composition depends on precondition-effect edges, not only semantic similarity. The broker and evaluator need to know what a skill changes, produces, requires, and terminates. |
| **Diagnostic momentum store** | Repeated failures, corrections, drift events, and probe losses must accumulate into a persistent diagnostic-momentum record before skill patches are accepted. One-off incidents may create probes or evidence, but should not normally rewrite a production skill. | Skill-improvement research indicates that recurring diagnostic patterns and contrastive losses stabilize skill updates better than heuristic reflection from a single trajectory. |
| **Trace spine** | Every captured event, sidecar job, model call, embedding call, retrieval decision, broker decision, evaluator run, file mutation, rollback, and high-risk tool-action attribution must carry `trace_id`, `span_id`, optional `parent_span_id`, and safe attributes. | Distributed tracing makes multi-service autonomous behavior debuggable and causally inspectable. It also supports rollback-complete evolution transactions and action-attribution gates. |

These are data-plane and control-plane refinements inside the existing plugin, sidecar, and Postgres architecture.

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

Patch rule: a production skill patch may be authored as a structured LLM semantic plan, but acceptance requires deterministic checks over diagnostic momentum plus normal scanner, semantic-equivalence, regression, shadowing, context-budget, and canary gates.

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

#### 1.5.4 Additional DDL for SkillIR, diagnostic momentum, and trace-spine requirements

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

### 1.6 Landscape-derived implementation requirements

The project landscape includes direct implementations, narrow research slices, benchmark systems, security audits, validation tools, open Agent Skills standards, and production ecosystem guidance. These sources establish the implementation stance: SkillKernel is a governed skill operating system, not a generator that occasionally writes `SKILL.md`.

The landscape-derived requirements below are first-release requirements unless explicitly marked as future-facing telemetry.

| Landscape-derived requirement | Adopted design rule | Implementation consequence |
|---|---|---|
| Batch evidence before durable mutation | Persistent skill creation/improvement normally requires clustered evidence windows, not one isolated trajectory. | Single events may create `ephemeral_candidate`, probes, negative evidence, rollback, or freeze. They should not normally produce a production `SKILL.md` unless the user gave explicit instruction or the event is severe enough to justify safety rollback. |
| Ephemeral candidate lane | Use candidate state `ephemeral_candidate` before normal persisted activation. | Temporary skill-like hints may be tested in trial workspaces and broker experiments without entering active OpenClaw skill roots. Promotion requires evidence maturity, scanner pass, regression pass, context-budget pass, and silent-bypass audit. |
| Silent-bypass audit | A skill receives positive credit only when it was retrieved, rendered or loaded, visible to the agent, temporally relevant, and causally plausible. | Outcome attribution must distinguish helped, hurt, ignored, missing, bypassed, environment-derived, agent-exploration-derived, and inconclusive. Presence in the candidate set is not usage. |
| Runtime immutability lock | Active skill packages are immutable for any session that may use them. | All changes stage a new version in a trial root, compile and hash artifacts, then activate by atomic pointer/symlink/snapshot swap at a safe boundary. Never rewrite an active `SKILL.md` in place mid-session. |
| External benchmark and validator adapter seam | Evaluator output must be adapter-friendly. | Support SkillsBench/SWE-Skills-Bench/OpenSkillEval/skillgrade/skill-validator-style adapters later without changing core schema. V1 need not bundle those tools, but evaluator records must support deterministic verifiers, gym-style tasks, pinned repos, and external grader artifacts. |
| Genericity and bloat rejection | Reject generic, broad, vague, human-prose-heavy, or redundant skills even if they look polished. | The scanner/compiler must flag weak triggers, marketing language, non-actionable prose, overbroad descriptions, body bloat, repeated constraints, unbounded examples, and token-heavy support files. |
| Co-evolved verifier lane | Skill generation/improvement and verifier/probe generation are separate roles. | A surrogate verifier can produce dense diagnostic checks, but it cannot alone admit a skill version. Its probes must themselves pass scanner, coverage, risk, and known-case sanity gates. |
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

`ephemeral_candidate` is not visible to OpenClaw as a normal skill. It exists for temporary broker trials, probe generation, and evidence gathering. Promotion from `ephemeral_candidate` to `trial_candidate` requires clustered evidence, explicit current-user request, or a configured admin bootstrap policy. Admin bootstrap policy is configuration authority, not routine semantic review. Promotion to `active` requires normal maturity, scanner, evaluator, context, provenance, and rollback gates.

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

#### 1.6.7 Architecture commitments

The implementation does not add per-skill databases, per-skill schemas, OpenClaw Cron dependency, Skill Workshop dependency, direct cost tracking, or a per-operation model-routing matrix.

The control plane includes the following safety and capability requirements:

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

These requirements address practical failure modes found across the research and project landscape.


### 1.7 Architecture decision rationale

The architecture intentionally favors a small number of stable, auditable control surfaces over many specialized execution paths. Each constrained choice exists to preserve autonomy, rollbackability, context efficiency, and long-run skill-library health.

| Decision | Rationale |
|---|---|
| Use one thin OpenClaw plugin and one sidecar. | OpenClaw hooks are the correct observation and control surface, but hook code should not perform slow analysis, LLM calls, migrations, scanning, evaluation, or file mutation. The sidecar owns durable autonomous work so the plugin remains fast, bounded, and replaceable. |
| Use one Postgres database and one `autoskill` schema. | Global retrieval, attribution, topology analysis, archived-skill promotion, duplicate detection, and cross-skill security checks depend on unified data access. Per-skill databases and per-skill schemas add migration, pooling, index, permission, and query complexity without improving the core autonomous-management loop. Logical `workspace_id` and `skill_id` scoping, indexes, row-level policy where needed, and measured partitioning provide the required isolation and performance. |
| Keep per-skill schemas out of v1. | Per-skill schemas are acceptable only if later operational evidence shows strict isolation or scale requires them. They should not be introduced before global topology, retrieval, curation, and provenance queries are stable, because they fragment the very evidence SkillKernel must reason over. |
| Own scheduling inside the sidecar. | Autonomous maintenance requires schedules, leases, retries, misfire handling, idempotency, job state, and audit records that users cannot accidentally disable by editing user-facing automation. OpenClaw Cron, system cron, Kubernetes CronJobs, and external schedulers do not provide the project-specific transactional semantics needed for skill evolution. |
| Do not depend on Skill Workshop. | Skill Workshop is useful prior art, but SkillKernel needs its own proposal store, scanner, evaluator, writer, archive, promotion, topology, broker, and rollback machinery. Depending on an experimental or user-facing plugin would make the autonomous control plane fragile. |
| Treat SkillIR and SkillGraphIR as canonical. | Directly mutating `SKILL.md` makes provenance, semantic equivalence, regression testing, context compilation, composition, decomposition, and rollback harder. SkillIR captures the executable meaning of a skill; SkillGraphIR captures workflow topology. `SKILL.md` is a compiled OpenClaw runtime projection. |
| Compile `SKILL.md` as an AI-facing runtime artifact. | Generated skills are loaded into the running agent context. They are not user documentation. Every word must justify its token cost by improving routing, execution, verification, safety, or failure recovery. Human-style prose, rationale, history, and redundant explanation are excluded unless they measurably improve model behavior. |
| Use one text LLM access profile and one embedding access profile in v1. | Operators need control over hosted versus local inference, model choice, thinking level, timeout, and token limits, but a per-operation model-routing matrix adds configuration burden and failure modes before there is operational evidence that it improves outcomes. One text profile and one embedding profile are sufficient for v1. |
| Do not implement a direct dollar-cost tracker/analyzer. | Cost mitigation is handled by operator model selection, local-model support, deterministic prefilters, token budgets, concurrency limits, and timeouts. Invocation audit may record token counts when available, but price analytics and model-cost optimization are outside the v1 control plane. |
| Generate embeddings outside pgvector. | pgvector stores vectors and performs similarity search; it does not create embeddings. SkillKernel therefore requires a configured embedding route and profile qualification gates. Embedding profile identity, dimensions, distance metric, and re-embedding campaigns are part of retrieval correctness. |
| Use LLMs as autonomous semantic adjudicators inside policy, not as unchecked executors. | LLMs are needed for intent reconstruction, redacted replay-intent synthesis, memory declassification, ambiguous topology choices, contrastive analysis, skill synthesis, patch planning, compression, and semantic scanning. They may produce high-confidence semantic verdicts and structured plans. They do not control SQL, paths, shell commands, scheduler state, file writes, external mutations, or rollback mechanics. Deterministic infrastructure validates confidence, provenance, redaction, policy, scanner/evaluator results, and then applies or rejects state transitions. |
| Prefer batch consolidation before durable mutation. | Isolated traces are noisy and can cause overfitting. Durable skill creation, improvement, composition, and decomposition should normally require clustered evidence, contrastive success/failure analysis, intervention trials, and regression checks. Explicit user instruction can create a high-priority candidate, but it still passes gates before activation. |
| Provide an `ephemeral_candidate` lane. | Temporary skill-like guidance can be evaluated without polluting the active skill bank. The ephemeral lane lets SkillKernel test emerging behavior while preserving the evidence maturity ladder for durable `SKILL.md` activation. |
| Treat create, improve, compose, and decompose as first-class topology operations. | SkillKernel optimizes the shape of the skill library, not merely individual files. Creation adds missing capabilities, improvement repairs useful capabilities, composition captures recurring multi-skill workflows, and decomposition splits broad or clunky skills into sharper reusable units. Merge, deduplicate, archive, promote, and retire are supporting operations. |
| Use a runtime Skill-Context Broker instead of inject-all behavior. | Large skill libraries degrade when irrelevant, stale, overlapping, or shadowing-prone skills enter context. The broker must retrieve, rerank, graph-expand, abstain when appropriate, and render the minimal useful context bundle under token budget. |
| Make no-skill a valid runtime decision. | A skill should not be loaded merely because it exists or weakly matches a task. No-skill routing avoids token waste, shadowing, stale guidance, and false attribution when deterministic execution or ordinary agent reasoning is sufficient. |
| Use runtime immutability and atomic activation. | Active skill packages must not change during sessions that may use them. Mutations stage a new version, pass gates, write manifests and hashes, then activate through an atomic pointer/snapshot transition with rollback. |
| Use evolution transactions across derived artifacts. | A skill change affects SkillIR, SkillGraphIR, compiled `SKILL.md`, support files, embeddings, probes, broker caches, memories, provenance, and audit records. Rollback and deletion must traverse these derived artifacts rather than only reverting a file. |
| Inventory but do not autonomously mutate external skills. | OpenClaw may load user, workspace, managed, bundled, plugin-provided, and extra-directory skills. SkillKernel must account for collisions, overlap, shadowing, risk, and routing interactions, but autonomous mutation is limited to SkillKernel-owned artifacts. |
| Use guard templates, not generated runtime programs. | Runtime enforcement is useful, but LLM-generated guard logic would create an unsafe executable control surface. Skills may select deterministic preapproved guard templates such as preflight checks, verify-only checks, capability warnings, sibling-disambiguation hints, and drift blocks. |
| Exclude control-plane self-modification from v1. | SkillKernel may improve skills, support artifacts, probes, broker policies, and lifecycle state. It must not autonomously rewrite the plugin, sidecar, scheduler, migrations, scanner, evaluator, compiler, deterministic writer, or policy engine in v1. |
| Treat memories and evidence as control inputs. | Stored traces, corrections, retrieved context, derived summaries, and memories can steer future behavior. They require provenance, taint propagation, delayed activation, quarantine, declassification, revocation traversal, and action attribution. |
| Use SLSA-style manifests for generated artifacts. | Skills, support files, probes, broker artifacts, and compiled runtime context are supply-chain artifacts. Hashes, generator metadata, SkillIR revision IDs, scanner/evaluator gate IDs, capability declarations, and rollback pointers are required for auditability and recovery. |
| Keep active skill artifacts compact and machine-oriented. | Context is the scarcest runtime resource. The context compiler and token budget governor must reject genericity, bloat, duplicated constraints, verbose examples, human-facing explanation, and low marginal utility per token. |
| Provide benchmark and validator adapter seams. | The evaluator should support project-local probes immediately and external benchmark/validator adapters later without redesign. This preserves compatibility with future skill-evaluation ecosystems while keeping v1 focused. |

These decisions are coupled. The simplified model-access layer reduces operational complexity; the deterministic control plane keeps autonomy safe; SkillIR and SkillGraphIR preserve semantic fidelity; the broker and context compiler protect runtime context; and unified storage preserves the evidence needed for create, improve, compose, decompose, archive, promote, rollback, and revocation.

### 1.8 Specification precedence and coherence rules

The rules below remove ambiguity and establish implementation precedence across the specification.

| Area | Rule | Implementation consequence |
|---|---|---|
| Project name | The project is **SkillKernel**. `autoskill` remains only the internal schema/path namespace. | Code, docs, status output, manifests, and plugin UI should say SkillKernel unless referring to the internal `autoskill` schema/path or the external ECNU AutoSkill project. |
| LLM access | One active text LLM profile in v1. | No per-operation model matrix. Typed LLM purposes all use the configured active text profile and are allowed only if that profile passes qualification gates. |
| Embeddings | One active embedding profile in v1. | pgvector stores vectors; embedding generation is performed by the configured embedding route. Profile/dimension are part of the vector contract. |
| Cost | No direct dollar-cost tracker/analyzer. | Record invocation metadata and token counts when returned for audit/debugging, but do not calculate prices, optimize by price, or expose cost analytics. |
| Context | Runtime-loaded skill artifacts are compiled AI-facing prompt artifacts. | `SKILL.md`, broker hints, runtime snippets, and any loadable support excerpts must pass semantic-density, token-budget, scanner, equivalence, and regression gates. |
| Topology | Create, improve, compose, and decompose are first-class lifecycle operations. | Merge/deduplicate, archive, promote, repair, compile, rollback, and freeze are supporting operations. They do not replace composition/decomposition. |
| Source of truth | SkillIR and SkillGraphIR are canonical. | `SKILL.md` is generated output. The LLM may author structured semantic IR changes and topology verdicts; deterministic code validates, renders, stages, hashes, activates, and rolls back. |
| Active artifacts | Active packages are immutable during sessions. | Mutations stage new versions and activate by atomic pointer/snapshot swap only after all gates pass. |
| External skills | External/non-SkillKernel skills are inventoried and considered for collision/shadowing but never mutated in place autonomously. | SkillKernel may autonomously classify relationships, suppress/shadow-aware route, or create a SkillKernel-owned replacement/adapter when policy, license/provenance, scanner, evaluator, and artifact gates pass. Mutating or deleting the external-owned source root requires operator action. |
| Control plane | Plugin, sidecar, scheduler, migrations, scanner, evaluator, compiler, deterministic writer, and policy engine are not autonomously rewritten in v1. | Self-improvement is limited to SkillKernel-owned skill artifacts, broker policies, probes, manifests, support artifacts, lifecycle state, and derived memories under transaction/rollback controls. |

Read this specification with the following precedence order:

```text
specification precedence and coherence rules
→ non-negotiable implementation decisions
→ OpenClaw compatibility constraints
→ autonomy policy
→ storage/retrieval/security/evaluation/compiler sections
→ research traceability
```

The implementation forbids operation-level model routing, human-facing skill prose in runtime artifacts, direct cost analytics, per-skill databases/schemas in v1, OpenClaw Cron usage, Skill Workshop dependency, synchronous hook-path LLM calls, and direct LLM file mutation.


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

**Requirement:** skill creation and improvement must be evidence-gated, externally grounded, and regression-aware. Self-reflection can generate hypotheses; it cannot be the only acceptance signal.

### 2.4 Skill update quality depends on lifecycle management

MUSE-Autoskill, SkillsVote, GRASP, Ratchet, SkillOps, SkillOS, SkillBrew, and related systems point to the same conclusion: the library manager matters as much as the skill author. Append-only accumulation creates redundancy, context pollution, and stale procedures.

**Requirement:** SkillKernel must own the full lifecycle: create, evaluate, register, use, attribute, refine, compile, merge, archive, promote, repair, and retire. Addition is only one of many actions.

### 2.5 Retrieval is not enough; context construction is a separate subsystem

SkillRet, Skill Retrieval Augmentation, Graph-of-Skills, More Skills/Worse Agents, and SkillsInjector all indicate that skill selection, dependency recovery, active budget, description rendering, and skill shadowing are separate bottlenecks. A high-similarity result can be wrong, insufficient, or harmful. A useful skill can be buried by sibling descriptions.

**Requirement:** SkillKernel needs a runtime skill-context broker. It should not expose a growing flat list and hope OpenClaw selects correctly. It should calibrate active visibility, retrieve dependency-complete bundles, render concise turn-specific hints, and detect shadowing.

### 2.6 Skill text is compiled from canonical SkillIR

SkillSmith, Skill-as-Pseudocode, SkillCompiler/SkillIR-style work, and Formal Skill-style runtime contracts point in the same direction: free-form Markdown is too ambiguous to be the system of record. It is useful as the model-facing artifact, but the manager needs a typed internal representation with explicit applicability, inputs, preconditions, operational steps, tool templates, verification, failure handling, boundaries, dependencies, risks, and environment contracts.

**Requirement:** `SKILL.md` is a compiled OpenClaw runtime interface, not the internal source of truth. The source of truth is versioned SkillIR. Runtime text uses stable sections: `WHEN`, `INPUTS`, `PRECONDITIONS`, `DO`, `OUTPUTS`, `EFFECTS`, `TOOL TEMPLATES`, `VERIFY`, `FAIL`, `DO NOT USE WHEN`, and `NEVER`.

### 2.7 Skill creation should use contrastive evidence

SkillGen-style approaches compare successful and failed trajectories to extract the behavior present in success but absent in failure. This is stronger than generic summarization because it grounds the skill in a causal-looking delta.

**Requirement:** candidate generation should cluster failures, cluster successes, retrieve nearest successful neighbors for failures, and synthesize corrections from local contrasts.

### 2.8 Skill drift is contract violation

Skill drift work shows that skills decay when APIs, packages, file formats, permissions, services, and environment assumptions change. Monitoring incidental values is noisy; monitoring role-bearing operational contracts is actionable.

**Requirement:** every skill version has extracted environment contracts. Drift checks target contracts and produce localized repair plans.

### 2.9 Memory and retrieval are attack surfaces

Memory poisoning, tool-selection poisoning, and sleeper-memory work show that long-term memory can carry delayed attacks. Skills can also be a persistence vector for prompt injection, exfiltration, or hidden directives.

**Requirement:** untrusted content is tainted at ingestion. Memory promotion and skill compilation require provenance, trust, and scanner gates. Skills are treated as untrusted inputs to the model unless they are SkillKernel-generated, scanned, versioned, and policy-cleared.

### 2.10 Skills are software supply-chain artifacts

Large-scale security studies of agent skills report vulnerabilities across prompt injection, data exfiltration, privilege escalation, and supply-chain abuse. Hidden-comment injection shows that Markdown can conceal instructions from ordinary visual review while remaining visible to models.

**Requirement:** SkillKernel-generated artifacts require manifests, capability declarations, file hashes, hidden-content bans, static and semantic scans, deterministic writes, restricted helper scripts, and rollback.

### 2.11 pgvector is useful, but vector-only retrieval is insufficient

pgvector provides exact search, approximate search, HNSW/IVFFlat indexes, half precision, binary quantization, filtering, iterative scans, and hybrid search with PostgreSQL full-text search. But approximate vector indexes can miss filtered results, and semantic similarity does not guarantee functional sufficiency.

**Requirement:** use pgvector as a candidate generator. retrieval combines lexical search, vector search, metadata filters, graph expansion, exact reranking, calibration, and recall audits.

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

**Requirement:** inventory external skills, hash their visible artifacts, embed their descriptions for collision/shadow analysis, mark their ownership as external, and treat them as read-only in their original roots. SkillKernel may autonomously create a SkillKernel-owned replacement, adapter, or suppress/route policy from declassified external-skill evidence when policy, provenance, scanner, evaluator, and rollback gates pass. In-place mutation or deletion of the external root requires operator action.

### 2.16 Memory is control input, not passive storage

Memories, evidence summaries, and retrieval notes can steer future tool choice, skill choice, and skill mutation. They therefore need the same trust logic as skill files, even when they are not directly rendered into `SKILL.md`.

**Requirement:** quarantine newly derived memory by default when it contains imperative language, user-specific data, external instructions, tool-choice claims, security-sensitive claims, or low-provenance content. Promote only after deterministic and semantic checks. Log control-flow events whenever memory influences retrieval, mutation, or tool routing.

### 2.17 Individual skill scanning is insufficient

Per-file scanning misses cross-skill and audit-runtime gaps. Two individually safe skills can jointly produce unsafe context; a skill can pass scanner/evaluator gates and later be modified; a mutable reference can change after scanner clearance; a broker-rendered bundle can change the meaning of a skill description.

**Requirement:** bind scanner verdicts to exact bytes/hashes, scan rendered skill bundles and broker hints, maintain co-load risk checks, and invalidate prior scanner/evaluator acceptances if bytes, metadata, dependencies, or renderer version changes.

### 2.18 Deterministic micro-executors and support artifacts are allowed but constrained

Some reusable procedures are better represented as deterministic scripts, adapters, validators, schemas, templates, examples, or assets than as model instructions. This reduces context and improves repeatability when the artifact is small, bounded, testable, and directly tied to observed work. It also increases supply-chain and execution risk, so support artifacts are never casual extras.

**Requirement:** support artifacts require a manifest, declared capabilities, file hashes, explicit interpreter/runtime where executable, tests or validation where applicable, no dynamic fetch-exec, no secret access unless explicitly declared, and scanner/evaluator acceptance. Approved OpenClaw-compatible active-root directories include `scripts/`, `references/`, `templates/`, `assets/`, and `examples/`; SkillKernel may also use governed `schemas/`, `data/`, `tests/`, `probes/`, and `adjunct_requests/` directories when their loadability class and scanner policy allow them. Tests, probes, bulky fixtures, mutable data stores, and operator audit material live under SkillKernel-managed `.autoskill/` storage by default. OpenClaw hooks, OpenClaw Cron routines, plugin tools, background services, MCP servers, and persistent local stores are not activated from a skill folder; SkillKernel creates inert adjunct requests or administrative integration requests for those needs. The LLM may author the semantic artifact plan; deterministic code decides artifact admissibility, writes exact files, scans, tests, hashes, manifests, and activates accepted artifacts.

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

**Requirement:** the plugin, sidecar, scheduler, migrations, scanner, evaluator, compiler, policy engine, and deterministic writer are not autonomously rewritten. SkillKernel may log infrastructure-defect evidence and generate administrative integration proposals, but v1 autonomous mutation is limited to SkillKernel-owned skills, manifests, support artifacts, broker policy versions, probes, and lifecycle state.

### 2.26 Rollback and deletion are provenance-graph operations

A rolled-back skill can leave downstream state behind: embeddings, memory summaries, broker hints, cached retrieval scores, attribution records, or derived probes. A deleted private fact can survive inside a skill or embedding if provenance is incomplete.

**Requirement:** every derived object stores provenance edges to source events, evidence, memories, skills, versions, transactions, and compiler/rendering policies. Rollback, quarantine, and deletion jobs traverse those edges and revoke, re-embed, recompile, or mark derived artifacts inactive.

### 2.27 The broker must be allowed to abstain

The right answer is sometimes not to load any skill. A skill can be semantically close but harmful, stale, redundant, token-wasteful, or likely to shadow a better low-level skill.

**Requirement:** `no_skill`, `defer_skill`, `use_builtin_only`, and `skill_hidden_control` are first-class broker decisions and logged outcomes. Curation policy should learn from cases where abstention produced better results.


### 2.28 Skill libraries must be optimized as topology, not append-only collections

The newest skill-bank and skill-scaling literature reinforces a single point: a growing library is not automatically better. Libraries become useful when their shape is governed: diverse enough to cover demand, compact enough to route accurately, decomposed enough to avoid black-hole skills, and composed enough to avoid repeating multi-skill workflows by hand.

**Requirement:** represent the skill library as a graph of skills, components, relationships, evidence clusters, and operation history. Bank-level curation must optimize topology, not only individual skill scores.

### 2.29 Skill granularity must be adaptive

Recent multi-granularity skill work argues against treating every skill as a flat, single-resolution prompt block. Useful libraries contain planning skills, functional skills, atomic execution skills, validators, adapters, and higher-order composed workflows.

**Requirement:** SkillIR must support nested components and relationship edges. The compiler can emit a compact `SKILL.md` for OpenClaw, but the internal representation must preserve multi-level structure for routing, composition, decomposition, and evaluation.

### 2.30 Composition and decomposition require causal-ish evidence, not aesthetic preference

The system should not compose skills because they look related, nor decompose skills because they look long. Composition requires evidence that a set of skills repeatedly participates in the same user-level goal and that a composed workflow improves utility, cost, reliability, or verification. Decomposition requires evidence that one broad skill contains separable usage clusters, routing false positives, partial-use patterns, or unrelated failure modes.

**Requirement:** compose/decompose operations require co-usage or partial-use evidence, operation-specific probes, and counterfactual/marginal-value trials. Cosmetic refactoring is not enough.

### 2.31 Routing and topology co-evolve

Skill composition and decomposition change retrieval behavior. A composed skill can shadow its components; a decomposed successor can reduce false positives but increase missing-prerequisite errors. Therefore topology operations must be broker-aware.

**Requirement:** every compose/decompose transaction includes broker replay, shadowing probes, component/successor routing tests, and no-skill/old-skill controls. Activation updates broker edges and context-rendering policy atomically.

### 2.32 Evidence quality determines autonomous decision quality

The value of autonomous skill operations depends on whether collected data can answer the right questions: what task was attempted, which skills were retrieved, which were visible, which were actually used, which were ignored, what tool calls followed, what failed, what the user corrected, what outcome was achieved, and what it cost.

**Requirement:** data capture must be designed from the start to support operation selection. “Usage count” is insufficient. Store co-retrieval, co-injection, co-use, sequence, partial-use, shadowing, missing-skill, no-skill, and intervention-trial events.


### 2.33 Context is finite, lossy, and distracting

Long-context capability does not remove the need for disciplined context construction. The system must assume that larger runtime context can increase cost, latency, distraction, false retrieval, and reasoning degradation even when the context window is not full.

**Requirement:** all skill-bank decisions must optimize net utility under an effective context budget, not merely nominal model context length.

### 2.34 Progressive disclosure is necessary but insufficient

Skill systems commonly use metadata-first loading and full-instruction loading only when needed. SkillKernel must go further: metadata, full instructions, support-file references, support-file excerpts, broker hints, and composed-skill bundles must all be classified, token-budgeted, and evaluated.

**Requirement:** progressive disclosure is implemented through context-loadability classes, not by assuming non-`SKILL.md` files are harmless.

### 2.35 Prompt compression must preserve operational semantics

Compression that deletes tokens without preserving operational contracts is unsafe. SkillKernel must compile SkillIR into compact runtime text through a measured semantic-density pipeline: compress, render, verify required fields, run equivalence probes, test target behavior, test regressions, and reject drift.

**Requirement:** runtime text compression is an evaluated compiler pass with semantic-equivalence tests, not a free-form summarization step.

### 2.36 AI-facing text differs from human-facing documentation

SkillKernel-generated skills are intended for model consumption. Human readability is secondary to correctness, compactness, unambiguous triggers, execution fidelity, and safety. The full human/debug explanation belongs in Postgres audit records and optional operator reports, not in context-loaded files.

**Requirement:** context-loadable language should be terse, structured, repetitive only where repetition improves model compliance, and free of human-oriented rationale.

### 2.37 Context pressure is a topology signal

Over-broad skills, overly general descriptions, verbose workflow skills, and frequently ignored skill bundles waste context and can harm routing. These are not only compression defects; they are evidence for decomposition, description tightening, archiving, or broker abstention. Conversely, repeated co-use can justify a composed skill only when it reduces total context and execution overhead.

**Requirement:** context telemetry is an input to create/improve/compose/decompose decisions.


### 2.38 Orchestration, not only availability, is the scaling bottleneck

The skill bank should not optimize for raw skill count. As the library grows, the limiting factor becomes selecting, sequencing, and composing the right minimal subset under context budget. Graph-composition research supports treating skills as nodes with preconditions, effects, dependencies, conflicts, and repair scopes rather than independent Markdown fragments.

**Requirement:** composed/decomposed workflows use SkillGraphIR when multiple component skills, ordered effects, verifier nodes, fallback branches, or local repairs are involved.

### 2.39 Formal contracts improve reliability, but OpenClaw output remains `SKILL.md`

Research on formal skill representations, typed pseudocode, and structured skill languages supports typed contracts, schema validation, executability constraints, deterministic quality checks, and explicit side-effect declarations. SkillKernel should adopt those internally without requiring OpenClaw to load a custom runtime format.

**Requirement:** SkillIR and SkillGraphIR are canonical internal contracts; OpenClaw `SKILL.md` remains the compiled, token-budgeted runtime artifact.

### 2.40 Local/operator-selected models require qualification, not blind trust

The simplified v1 model-access design is correct: one text model profile and one embedding profile. The missing hardening is qualification. A local or hosted model may fail JSON adherence, lose evidence IDs, hallucinate paths, compress away constraints, ignore refusal policy, mishandle long context, or produce unstable outputs. An embedding model may have the wrong dimension, poor query/document behavior, or unstable batches.

**Requirement:** active text and embedding profiles must pass lightweight qualification probes before autonomous apply. Failed profiles may still be usable for low-risk draft or classification tasks if explicitly allowed, but cannot be treated as production-autonomous reasoning backends.

### 2.41 Embedding profiles are retrieval contracts

pgvector stores and indexes vectors, but the embedding model defines the geometry. Vectors from different models, dimensions, query/document modes, or distance metrics are not interchangeable. Re-embedding campaigns are migration work, not transparent updates.

**Requirement:** every vector records embedding profile, dimension, metric, input mode, and source object. Retrieval never compares vectors across incompatible embedding profiles. Profile changes trigger controlled re-embedding and recall calibration.

### 2.42 Generated skills are supply-chain artifacts

Auto-generated skills, support scripts, manifests, probes, broker policies, and compiled snippets are artifacts that can be tampered with, partially rolled back, or activated without their dependencies if provenance is weak.

**Requirement:** each activated skill artifact set has a provenance manifest with artifact hashes, generator metadata, source SkillIR revision, scanner/evaluator gate IDs, capability declarations, and rollback pointer. Activation verifies the manifest before exposing the artifact.


### 2.43 Historical evidence is valuable but lower-trust than live typed capture

Established OpenClaw deployments can contain months of sessions, compaction summaries, trajectories, memory files, task records, tool failures, user corrections, and existing skill inventories. That historical corpus is often the fastest path to useful skill creation after installation. It also has weaker structure than live SkillKernel events, may contain stale instructions, raw secrets, private user facts, prompt-injection attempts, compacted summaries, truncated rows, orphan artifacts, and environment assumptions that no longer hold.

**Requirement:** historical ingestion is a first-class bootstrap path, but it produces imported sources, redacted chunks, evidence, memories, clusters, candidates, and probes through the same trust pipeline as live capture. Historical data cannot directly create active skills, runtime context, or trusted memory. It must pass source classification, fingerprinting, redaction, tainting, provenance linking, evidence maturity, contrastive analysis, scanner/evaluator gates, and transaction-scoped activation.

### 2.44 Ingestion quality determines downstream skill quality

RAG and agent-memory work consistently show that retrieval quality depends on source parsing, chunking, deduplication, provenance, summary fidelity, and index compatibility. Poor ingestion creates false clusters, poisoned memories, duplicated evidence, broken retrieval, and misleading skill candidates. Experience-replay work further supports aggregating past trajectories into compact reusable guidance, but only after experience records are selected, summarized, and retrieved under constraints.

**Requirement:** the historical importer is not a filesystem crawler that dumps text into embeddings. It is a controlled ETL subsystem with datasource-specific parsers, idempotent fingerprints, chunk lineage, source confidence, stale-context detection, deduplication, redaction-before-embedding, summary/body separation, multi-agent scoping, and replayable import runs.

### 2.45 Autonomous decisions require calibrated selective trust, not static approval gates

SkillKernel is an autonomous system, so ordinary semantic uncertainty must be resolved by the system itself. A fixed threshold that routes near-margin cases to administrative escalation by default defeats the product goal and creates a hidden operational bottleneck. At the same time, an uncalibrated LLM verdict is not a sufficient safety basis for autonomous mutation. The correct pattern is calibrated selective trust: the LLM performs semantic adjudication, deterministic infrastructure checks admissibility and execution safety, and the autonomy controller chooses an autonomous next step based on calibrated reliability, risk, reversibility, evidence fidelity, and canary containment.

**Requirement:** every semantic decision family has an auditable calibration loop. The system records the LLM verdict, confidence decomposition, evidence coverage, action class, selected autonomous action, delayed outcome, and eventual utility/harm signal. The resulting calibration data is used to adjust soft decision bands, trial sizing, canary exposure, and fallback strategy. Administrative escalation is reserved for explicit policy boundaries, raw-content reveal, irreversible external mutation, unavailable required infrastructure, or unresolved contradiction after autonomous fallback attempts.

### 2.46 Dynamic thresholds are policy artifacts with outcome feedback

Soft thresholds are not constants embedded in code. They are versioned policy artifacts calibrated against replay, historical bootstrap, canary, and production outcomes. A threshold has meaning only within a decision family, task family, executor profile, evidence-fidelity tier, risk class, and autonomy mode. Thresholds must move when the system learns that they are too strict, too permissive, stale for a new executor profile, or mismatched to the current evidence distribution.

**Requirement:** soft-threshold policies have a lifecycle: draft, replay evaluation, shadow mode, bounded canary, active, rollback, retired. Threshold updates cannot bypass hard invariants. They may change candidate priority, evidence budgets, probe budgets, canary sizing, decision bands, and no-op/reschedule behavior. Each policy version records reliability metrics such as coverage, false-accept rate, false-reject rate, calibration error, utility-per-token, regression rate, and harm findings.

### 2.47 Agentic confidence must be trajectory-aware

A single verbalized model confidence score is not enough for autonomous skill governance. Agentic outcomes depend on multi-step trajectories: user intent, evidence fidelity, skill retrieval, broker rendering, tool calls, errors, canary behavior, scanner findings, evaluator margins, and rollback capability. Confidence must therefore be computed from trajectory features and delayed outcomes rather than only the final model answer.

**Requirement:** SkillKernel maintains a trajectory-aware confidence calibrator. The calibrator consumes structured features from the trace spine, evidence packets, raw-vault/declassification state, LLM adjudications, scanner/evaluator results, broker decisions, canary outcomes, user corrections, and rollback events. It emits calibrated decision confidence per decision family and stores reason components so the system can autonomously repair confidence bottlenecks.

### 2.48 Reliability comes from separation of powers, not removing autonomy

The design must avoid both extremes: a single LLM call that adjudicates, authorizes, and executes high-risk work; and a brittle workflow that punts routine semantic judgments to operators. SkillKernel achieves autonomy through separation of powers. LLM calls adjudicate semantic meaning and produce structured verdicts or plans. Deterministic services enforce hard invariants, policy bounds, schemas, scanner results, rollback contracts, and execution mechanics. The Autonomy Decision Orchestrator combines these into a next action.

**Requirement:** no single LLM call can unilaterally adjudicate, accept, and execute a high-risk mutation. High-risk SkillKernel-owned mutations remain autonomous by using independent adjudication when needed, deterministic admissibility checks, isolated trials, regression probes, canary containment, and rollback-complete evolution transactions. External-owned root mutation, raw reveal, and new infrastructure capabilities require an explicit predelegated policy authority or admin action.

### 2.49 Abstention is an autonomous action, not a human handoff synonym

Abstention research is useful only if it produces better autonomous routing. In SkillKernel, abstention means the system chooses a safer autonomous action: no-op with reschedule, more evidence, re-adjudication, narrower scope, ephemeral candidate, canary-only activation, archive suppression, broker `no_skill`, automatic rejection, quarantine, freeze, or rollback. It does not mean default administrative escalation.

**Requirement:** all ordinary soft-threshold misses and semantic uncertainty cases must produce one of the defined autonomous fallback actions before escalation. The system tracks unnecessary abstention, delayed acceptance after abstention, and cases where over-conservative thresholds suppressed useful skills.

### 2.50 Research boundary

The research synthesis supports the architecture: a deterministic control plane, a governed evidence store, compact AI-facing compiled artifacts, profile-qualified LLM/embedding access, calibrated autonomous semantic adjudication, dynamic soft-threshold policy, graph-aware composition, regression-aware evaluation, supply-chain manifests, and rollback-complete transactions.

**Requirement:** future conceptual changes should be admitted only when they identify a concrete failure mode not already covered by redaction, provenance, evidence maturity, calibrated autonomy, profile qualification, SkillIR/SkillGraphIR contracts, transactionality, scanner, evaluator, broker, rollback, canary, freeze, or threshold-deadlock remediation.

### 2.51 Change admission condition

The principal risk is implementation discipline. The specification covers live capture, historical ingestion, redaction, provenance, storage, scheduling, retrieval, body-aware routing, SkillIR, compilation, LLM/deterministic boundaries, calibrated autonomous semantic adjudication, scanner, evaluator, transactionality, rollback, memory governance, broker governance, autonomous topology operations, creation, improvement, composition, decomposition, curation, archiving, promotion, external-skill inventory, harmful-capability controls, executor profiles, observability, retention, and implementation order.

**Requirement:** proceed with implementation. Design changes require a concrete failure mode not covered by the current control surfaces.


---

## 3. Non-negotiable implementation decisions

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
| Skill Workshop | **Do not depend on it.** | It is experimental and can change. Use only as conceptual reference pattern. |
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
| External skill adoption | **Autonomous relationship adjudication; no in-place external mutation.** | SkillKernel may create SkillKernel-owned replacements/adapters from scanned/declassified external evidence when policy permits. It never edits or deletes external-owned roots autonomously. |
| Creation priority | **Improve active → promote archived → merge/supersede → create new.** | Prevents duplicate bloat. |
| Runtime context | **Bounded skill-context broker.** | Prevents skill shadowing and token waste. |
| Broker abstention | **`no_skill` is a valid broker decision.** | Skill injection can hurt; abstention must be measured and rewarded when useful. |
| File writes | **LLM emits structured plans; deterministic writer applies.** | Prevents arbitrary paths and shell behavior. |
| Evaluation | **Hard safety gate + hard regression gate + multi-objective ranking.** | Reliability before optimization. |
| Trial evaluation | **Evaluate candidate artifacts in isolated trial workspaces/executor profiles before activation.** | Prevents candidate side effects from contaminating production state. |
| Risky action attribution | **Log causal contributors for high-risk actions and run counterfactual/attenuated checks where feasible.** | Runtime security depends on intent-to-execution integrity, not only text scanning. |
| Skill text | **Compiled runtime interface.** | Minimizes prompt overhead and ambiguity. |
| Memory | **DB-side governed memory.** | Avoids context bloat and memory poisoning. |
| Raw secrets | **Never embed, compile, or place in normal logs/analytics.** | Secret-like material may exist only in encrypted raw-evidence vault records when capture policy permits it; it is short-retention, access-audited, never compiled, and normally masked before LLM exposure. |
| User-specific data | **Never compile into general skills.** | Skills encode reusable procedure, not private facts. |
| Historical ingestion | **Core bootstrap importer.** | Live plugin capture and historical backfill feed the same evidence pipeline. Existing deployments must gain immediate value from prior sessions, trajectories, memory files, task records, workspace context, and existing skill inventories without bypassing redaction, provenance, taint, maturity, or evaluation gates. |
| Default autonomy | **`autonomous_guarded`.** | Applies safe changes automatically; rejects unsafe changes automatically. |

---


### 3.1 LLM and deterministic execution boundary

SkillKernel uses an LLM only where semantic judgment, abstraction, synthesis, or natural-language reasoning is required. It uses deterministic programmatic code everywhere a bounded algorithm can produce the correct result more safely, cheaply, repeatably, and auditably.

This is a non-negotiable implementation boundary, not an optimization suggestion.

#### 3.1.1 Core rule

```text
Use deterministic code for control, persistence, security, scheduling, IO, hard-invariant enforcement, validation, writing, rollback, and accounting.
Use LLM calls for semantic interpretation, reusable-procedure induction, structured plan generation, high-confidence semantic adjudication, repair hypotheses, compression decisions, and ambiguous evidence classification.
Use calibrated soft-threshold policies to guide evidence gathering, trial sizing, canary exposure, and priority; do not use arbitrary fixed thresholds as administrative-escalation tripwires.
Never let an LLM directly control paths, SQL, shell commands, scheduler state, raw policy permissions, file writes, archive/promotion state, or rollback behavior.
```

The LLM is a semantic adjudicator and plan generator. For meaning-heavy decisions, the LLM verdict is the semantic decision artifact; deterministic services are the admissibility, safety, and execution boundary.

#### 3.1.2 Required LLM uses

LLM calls are appropriate for these jobs because deterministic code cannot reliably infer the required procedural abstractions from messy real-world traces:

| Job | Why the LLM is used | Output contract |
|---|---|---|
| candidate skill discovery from transcript/evidence clusters | identify repeated latent workflows, missing procedures, user corrections, and recurring task intent | candidate classification plus cited evidence IDs |
| user-intent reconstruction | infer what the user was trying to accomplish from prompt/assistant/tool/context windows when redacted telemetry is insufficient | redacted intent record, task fingerprint, confidence, sensitivity report, and source evidence IDs |
| replay-corpus intent synthesis | convert real usage telemetry into safe durable replay/canary episodes without manual operator plans | `redacted_user_intent`, expected skill decision, redaction report, and replay eligibility verdict |
| memory declassification adjudication | determine whether a memory candidate is safe operational evidence, private fact, poisoned instruction, contradiction, or low-confidence | structured memory verdict plus declassification or rejection reason |
| external-skill relationship adjudication | classify whether an external skill overlaps, shadows, conflicts, supersedes, complements, or should inspire a SkillKernel-owned replacement | relationship record, risk labels, and routing/adoption recommendation |
| contrastive success/failure analysis | infer what successful trajectories did differently from failed ones | reusable behavioral delta with cited traces |
| skill creation planning | synthesize a new procedural capability from multiple evidence items | structured candidate plan JSON only |
| skill improvement planning | infer repair hypotheses from failures, corrections, regressions, and drift | structured patch plan JSON only |
| semantic compilation decisions | choose which components become runtime text and which remain DB-side memory | structured component selection and runtime-section draft |
| description and applicability refinement | write compact frontmatter descriptions, aliases, `WHEN`, and `DO NOT USE WHEN` boundaries | bounded text fields validated by deterministic checks |
| ambiguous outcome attribution support | help classify hard cases where a skill may have helped, hurt, been ignored, or been shadowed | suggested attribution, never ledger write without rule checks |
| semantic scanner support | detect prompt-injection-like intent or unsafe instruction semantics beyond regex/static checks | scanner finding with severity and rationale |
| probe generation | generate natural-language or tool-use regression probes from evidence | probe specification, expected behavior, and pass/fail conditions |
| topology reasoning | decide whether skills should be deduplicated, composed into a workflow skill, or decomposed into sharper skills | structured topology verdict/plan with evidence |

Every LLM output must be schema-validated, evidence-linked, scanned, and either accepted by deterministic gates or discarded.

#### 3.1.3 Deterministic-only responsibilities

The following must never depend on LLM judgment as the authority:

| Responsibility | Deterministic implementation |
|---|---|
| event capture, redaction, taint marking, and spooling | plugin code with explicit rules and allowlists |
| authentication, authorization, and control API access | fixed policy and credentials/mTLS/token validation |
| scheduling and job execution | Postgres schedules/jobs, leases, idempotency keys, advisory locks |
| SQL generation and migrations | static migrations and parameterized queries only |
| embedding writes and retrieval queries | fixed query builders, indexes, thresholds, exact rerank |
| hard-invariant enforcement and calibrated soft-threshold routing | configured formulas, decision bands, policy tables, and deadlock detection |
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

#### 3.1.4 Token-use and LLM-call control

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
- Do not ask an LLM to bypass acceptance policy, scanner, evaluator, rollback, or token-budget gates. The LLM may make a semantic verdict or plan; deterministic gates decide whether that verdict is actionable.
- Do ask a qualified LLM to infer user intent, classify why a turn happened, synthesize a redacted replay intent, choose among create/improve/compose/decompose/no-op for an ambiguous evidence packet, or recommend memory declassification when deterministic code cannot preserve enough meaning.

#### 3.1.5 Execution modes

LLM calls have three execution modes:

| Mode | Allowed latency | Uses | Notes |
|---|---:|---|---|
| synchronous hook path | none | no LLM calls | only cached context hints and deterministic lookup |
| asynchronous maintenance path | normal worker latency | creation, improvement, compilation, probes, semantic scans | budgeted and retryable through job queue |
| emergency repair path | bounded worker latency | rollback explanation, repair proposal after canary failure | cannot bypass scanner/evaluator gates |

This prevents skill management from degrading the interactive OpenClaw session.

#### 3.1.6 LLM client abstraction under one active text profile

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
infer_user_intent_from_raw_window
synthesize_redacted_replay_intent
adjudicate_memory_candidate
adjudicate_external_skill_relationship
adjudicate_topology_operation
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
- content-exposure level;
- redaction/declassification requirement;
- audit record;
- deterministic validator;
- fallback behavior.

No component calls a generic chat-completion function directly. No component selects a different model per operation in v1. The only active text LLM choice is the configured text model profile. Each purpose declares the maximum allowed input sensitivity so the raw-evidence vault can permit, mask, deny, or escalate the job before any model call.

#### 3.1.7 Single-profile capability policy

SkillKernel uses one active text profile in v1. The profile is qualified into capability levels by fixed probes:

| Qualification | Allowed use |
|---|---|
| `qualified_autonomous` | May perform autonomous semantic adjudication and author create/improve/compose/decompose verdicts/plans that can proceed to deterministic gates. |
| `qualified_propose_only` | May draft semantic plans and explanations for inspection or testing, but autonomous apply is blocked. |
| `qualified_classify` | May classify evidence, labels, and low-risk semantic fields only. |
| `failed` | Not used by SkillKernel jobs. |

High-impact actions such as creating a skill, expanding capability, composing workflow skills, decomposing broad skills, or accepting a broad patch require `qualified_autonomous`. If the active profile is only `qualified_propose_only`, the sidecar may store proposals and evaluator results but must not activate changes automatically. If the active profile is only `qualified_classify`, semantic mutation jobs are skipped.

This preserves user/operator control, avoids hidden provider/model selection, avoids cost-optimization machinery, and keeps v1 implementation simple while still preventing weak local models from driving autonomous mutations.

#### 3.1.8 Fallback behavior

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

### 3.2 Operator-configurable LLM and embedding access profiles

#### 3.2.1 Requirement

SkillKernel must support operator-controlled LLM and embedding access, but v1 must keep the configuration deliberately simple.

Model access is:

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

The model-access design intentionally avoids a per-operation routing matrix because that matrix increases configuration burden, test matrix size, failure modes, and support complexity without sufficient v1 value. Deterministic prefiltering, batching, token limits, and operator model choice provide the needed cost/privacy controls without per-operation model routing.

#### 3.2.2 Text LLM access profile

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
raw-window intent reconstruction
redacted replay-intent synthesis
memory declassification/adjudication
external-skill relationship adjudication
autonomous semantic adjudication of gated-but-reasoning-dependent cases
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

#### 3.2.3 OpenClaw-routed text profile

When `route_type: openclaw`, SkillKernel uses an explicitly supported OpenClaw text-generation capability for the target OpenClaw version. This route is valid only when OpenClaw can provide a maintenance-safe model path: either a host-owned simple-completion seam or a dedicated SkillKernel maintenance agent/session identity that does not inherit the active user's transcript, tools, approvals, memory, or transient turn context. If the installed OpenClaw version cannot provide that narrow service-model path, the `openclaw` profile is invalid and the operator must choose `openai_compatible` instead.

Rules:

1. Use canonical OpenClaw-style `provider/model` references.
2. Validate that the configured provider/model exists and supports the required text-generation capability.
3. Validate the requested thinking/reasoning level when the provider exposes that capability.
4. Do not drive, impersonate, or mutate the normal interactive user session.
5. Do not inherit user session tools, memory, approvals, transient context, or conversation history.
6. Do not scrape OpenClaw internals or rely on undocumented provider objects.
7. If the only available route is OpenClaw's OpenAI-compatible Gateway surface, require explicit opt-in, local/private network exposure, authentication, rate limiting, and a no-tools service profile.

The OpenClaw-routed profile is implemented through a narrow model relay, not through hook-time semantic work. The sidecar creates a bounded model-request record; the plugin, outside hook execution, claims that relay request and calls the supported OpenClaw runtime LLM capability for the configured maintenance profile. The plugin returns only the normalized model result, token/cache metadata if provided, provider/model attribution, and error state. It does not run candidate mining, scanner judgment, evaluator logic, file mutation, archive/promotion decisions, or policy decisions.

Required relay behavior:

1. Bind the relay to localhost/private IPC and authenticate every request.
2. Use `api.runtime.llm.complete` or an equivalent stable OpenClaw runtime capability only when it can satisfy the maintenance-profile isolation requirement above.
3. Require the operator trust gates for plugin LLM model overrides and allowed model refs when the configured `provider/model` differs from the default service profile.
4. Send only SkillKernel-maintenance prompts assembled by the sidecar after redaction and taint checks.
5. Disable tool/function calling for maintenance completions.
6. Propagate timeout, abort, schema, prompt hash, response hash, provider/model attribution, and retry metadata into `autoskill.llm_invocations`.
7. Discard provider price/estimated-cost fields even when OpenClaw exposes them; persist token/cache counts only when useful for audit/debugging.
8. Fail closed when OpenClaw's runtime LLM capability is unavailable, disabled, unsuitable for isolated maintenance use, or not trusted by configuration.

The direct OpenAI-compatible route bypasses this relay and is called by the sidecar directly.

#### 3.2.4 Direct OpenAI-compatible text profile

When `route_type: openai_compatible`, SkillKernel calls a configured `/v1` endpoint directly.

This is the required v1 escape hatch for local-first, private, offline, self-hosted, or low-cost deployments.

Required behavior:

1. Support `/v1/chat/completions` as the baseline endpoint.
2. Support `/v1/responses` only if explicitly configured and the target server supports it.
3. Do not require provider-specific adapters for Ollama, llama.cpp, LM Studio, vLLM, SGLang, or LiteLLM in v1 if their OpenAI-compatible routes work.
4. Require `base_url_env` and `api_key_env`; allow dummy API keys for local servers that require the header shape but do not validate it.
5. Disable tools/function-calling for SkillKernel maintenance prompts unless a future audited feature explicitly requires it.
6. Treat the direct route as untrusted infrastructure: validate schema outputs, enforce timeouts, and never allow model output to control paths, SQL, shell, or policy.

#### 3.2.5 Thinking/reasoning-level policy

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

#### 3.2.6 Token, concurrency, and outage controls

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

#### 3.2.7 Invocation audit, not cost ledger

SkillKernel records LLM invocations for reproducibility, debugging, safety audit, and rollback reasoning. It does not compute dollar cost, persist provider price estimates, enforce currency-denominated caps, rank models by price, or produce cost analytics. Resource-cost fields elsewhere in SkillKernel mean operational cost such as tokens, latency, tool invocations, context footprint, retry count, or maintenance burden; they do not mean currency accounting.

The invocation audit may record:

```text
job id
purpose class
route type
provider/model or endpoint model id
requested/effective thinking setting
input/output token counts if returned by provider
latency
relay claim/finish timestamps when OpenClaw-routed
prompt hash
response hash
schema-validation result
downstream acceptance result
error code
```

The invocation audit stores hashes and metadata by default. Raw prompts, raw responses, or model-visible raw evidence are stored only in the governed raw-evidence vault when the active evidence-retention policy permits them. The audit row links to vault record IDs and declassification reports; it does not duplicate raw content in ordinary audit fields.

#### 3.2.8 Embedding access profile

pgvector stores and searches vectors. It does not create embeddings. SkillKernel therefore needs a separately configured embedding profile.

The embedding profile uses the same two route types:

| Route type | Purpose |
|---|---|
| `openclaw` | Use a supported OpenClaw embedding provider/capability or secured OpenClaw-compatible embedding endpoint. |
| `openai_compatible` | Call a configured `/v1/embeddings` endpoint directly. |

When the OpenClaw Gateway OpenAI-compatible endpoint is used for embeddings, SkillKernel treats it as an operator-scoped Gateway surface, not a narrow embedding-only service. The deployment must keep it on loopback/private ingress, authenticate it, and explicitly set the target embedding model rather than relying on an implicit default.

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

#### 3.2.9 Embedding table shape

Use an unconstrained `vector` column plus `embedding_dim` and profile-specific partial expression indexes. Do not use a single hardcoded `vector(1536)` table in v1.

This preserves operator freedom to use OpenAI, local, Ollama, Gemini, Voyage, Mistral, OpenAI-compatible, or other embedding models with different vector dimensions.

Representative profile-specific HNSW index pattern:

```sql
CREATE INDEX embeddings_hnsw_profile_1536_cosine_example
ON autoskill.embeddings
USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE embedding_profile_id = '11111111-2222-4333-8444-555555555555' AND embedding_dim = 1536;
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

#### 3.2.10 Required model/embedding control-plane tables

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
  relay_owner text,
  relay_claimed_at timestamptz,
  finished_at timestamptz,
  status text NOT NULL CHECK (status IN ('queued','claimed','running','succeeded','failed','rejected','cancelled','unavailable','rate_limited','timed_out')),
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

#### 3.2.11 Configuration example

OpenClaw-routed text model plus direct local OpenAI-compatible embeddings:

```yaml
skillkernel:
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
        max_input_sensitivity: private
        allow_raw_evidence: true
        require_local_for_raw_private: true

  embeddings:
    active_profile: local_embeddings
    profiles:
      local_embeddings:
        route_type: openai_compatible
        provider: local-embedding
        model: embedding-model-id
        base_url_env: SKILLKERNEL_EMBEDDING_BASE_URL
        api_key_env: SKILLKERNEL_EMBEDDING_API_KEY
        dimensions: 1536
        distance_metric: cosine
        batch_size: 128
        timeout_ms: 60000
        hosted_allowed: false
        local_only: true
```

Direct local OpenAI-compatible text model plus direct local embeddings:

```yaml
skillkernel:
  llm:
    active_profile: local_reasoner
    profiles:
      local_reasoner:
        route_type: openai_compatible
        provider: local-llm
        model: local-model-id
        base_url_env: SKILLKERNEL_LOCAL_LLM_BASE_URL
        api_key_env: SKILLKERNEL_LOCAL_LLM_API_KEY
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
        base_url_env: SKILLKERNEL_EMBEDDING_BASE_URL
        api_key_env: SKILLKERNEL_EMBEDDING_API_KEY
        dimensions: 768
        distance_metric: cosine
        batch_size: 64
        timeout_ms: 60000
        hosted_allowed: false
        local_only: true
```

#### 3.2.12 Development acceptance criteria

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
15. Qualification runs are workspace-scoped and profile-linked, not keyed by mutable profile name alone.


### 3.3 Model and embedding profile qualification gates

The operator controls the text model and embedding model. SkillKernel must not assume those choices are safe, sufficiently capable, or semantically compatible with autonomous mutation. Qualification is a deterministic gate over model behavior, not a cost optimizer and not a multi-model routing system.

#### 3.3.1 Text model qualification

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
qualified_autonomous   = may be used for autonomous semantic adjudication and create/improve/compose/decompose plans
qualified_propose_only = may draft plans/explanations, but autonomous apply is blocked
qualified_classify     = may classify evidence or labels only
failed                 = not used by SkillKernel jobs
expired                = must requalify before autonomous use
```

The evaluator, scanner, compiler, token governor, writer, and rollback system remain deterministic execution authorities. A qualified model can author semantic verdicts and plans; it cannot directly write files, execute SQL or shell, mutate scheduler state, change policy state, archive, promote, roll back, or mark its own output accepted without deterministic admissibility checks.

#### 3.3.2 Embedding profile qualification

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

#### 3.3.3 Control-plane tables

```sql
CREATE TABLE autoskill.model_profile_qualification_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  text_model_profile_id uuid REFERENCES autoskill.text_model_profiles(text_model_profile_id),
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
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  embedding_profile_id uuid REFERENCES autoskill.embedding_profiles(embedding_profile_id),
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

Qualification rows are scoped by `workspace_id` and linked to the configured profile when possible. Profile names are retained for audit readability, but they are not the authority because names can be reused after configuration changes.

#### 3.3.4 Operational rules

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

1. `name` uses lowercase letters, digits, and hyphens.
2. `description` is one line, compact, and routing-relevant.
3. `SKILL.md` parses cleanly as Markdown with YAML frontmatter.
4. Frontmatter uses simple single-line keys. Required keys are `name` and `description`.
5. If `metadata` is emitted, it is a single-line JSON object. OpenClaw-specific runtime metadata belongs under `metadata.openclaw`, including gating and install metadata such as `requires.env`, `requires.bins`, `requires.anyBins`, `requires.config`, `primaryEnv`, `envVars`, `install`, `os`, `always`, `skillKey`, `emoji`, and `homepage` when those fields are applicable.
6. OpenClaw optional slash-command/frontmatter fields such as `user-invocable`, `disable-model-invocation`, `command-dispatch`, `command-tool`, `command-arg-mode`, and `homepage` are emitted as compact top-level single-line frontmatter keys only when the SkillIR explicitly requires them and the renderer verifies OpenClaw compatibility.
7. SkillKernel provenance, hashes, evidence links, lifecycle state, evaluator results, support-artifact metadata, rollback pointers, and internal compiler details live in Postgres and `.autoskill-manifest.json`, not in verbose frontmatter.
8. Long examples, diagnostics, evidence, raw traces, human rationale, and improvement notes do not belong in runtime `SKILL.md`.
9. Supporting files are allowed only when needed and must be declared in `.autoskill-manifest.json` with loadability class, purpose, hash, capability declarations, and scan/evaluation status.
10. Support files intended for broad OpenClaw/Agent Skills compatibility use ordinary skill-local directories such as `scripts/`, `references/`, `templates/`, `assets/`, and `examples/`. SkillKernel-governed optional directories such as `schemas/`, `data/`, `tests/`, `probes/`, and `adjunct_requests/` are treated as normal files by OpenClaw and become meaningful only through SkillKernel manifests, explicit `SKILL.md` references, existing OpenClaw tools, or evaluator-side handling. SkillKernel may keep internal probes/tests outside the active skill root under `.autoskill/` unless the agent must read a small immutable fixture.
11. Skills are organized under the SkillKernel subfolder so ownership is obvious.
12. Archive directories stay outside OpenClaw-visible roots so archived skills cannot be selected accidentally.

Skill folders are not plugins, schedulers, persistent services, or databases. A generated skill may include a script that the agent can run through an existing OpenClaw tool, a template that the agent can copy, a schema that a verifier can use, or a reference that the agent can read. It must not assume that `hooks/`, `cron/`, `services/`, or mutable local-state files placed in the skill directory will be registered by OpenClaw. When a reusable capability requires a new OpenClaw tool, plugin hook, sidecar schedule, background service, MCP server, or durable store, SkillKernel records an inert adjunct request or administrative integration request rather than silently embedding active infrastructure inside the skill folder.

OpenClaw plugin hooks are the capture seam. Hook handlers should not run slow analysis or file mutation. They normalize, redact, enqueue, and return. The only optional prompt-adjacent behavior is a short, cached, sidecar-supplied runtime skill-context hint with a strict timeout and fail-soft behavior.

OpenClaw Cron is not used as SkillKernel's scheduler. `cron_changed` may be observed as environmental evidence only, never as the autonomous maintenance substrate.

Skill Workshop is not a dependency. SkillKernel may be compared against it as prior art, but proposals, scanning, evaluation, writing, archiving, promotion, rollback, and topology operations are implemented inside SkillKernel.

---

## 5. Autonomy policy

The production default is:

```yaml
autonomy_mode: autonomous_guarded
```

SkillKernel is designed to operate autonomously end-to-end. Administrative escalation is not part of ordinary skill creation, improvement, composition, decomposition, replay-corpus construction, memory adjudication, external-skill relationship classification, broker tuning, archive/promotion, or repair workflows. Administrative involvement is reserved for explicitly configured policy boundaries, raw reveal, mutation of external-owned roots, irreversible infrastructure change, missing required infrastructure, or unresolved contradiction after autonomous evidence gathering and adjudication have been exhausted.

The autonomy model is:

```text
LLM semantic adjudication
+ calibrated soft decision policy
+ deterministic hard-invariant enforcement
+ isolated trial/canary/rollback controls
= autonomous high-confidence action
```

Autonomy modes:

| Mode | Behavior |
|---|---|
| `observe_only` | Capture, store, analyze. No proposals, no writes. Raw-evidence capture follows the configured evidence-retention policy. |
| `propose_only` | Generate candidates, redacted intents, semantic adjudications, evaluations, and staged plans. No filesystem writes. |
| `auto_archive_only` | Can archive/demote SkillKernel-owned low-utility skills. No creation/improvement writes. |
| `autonomous_guarded` | Can create, improve, compose, decompose, compile, archive, promote, merge, repair, roll back, build replay episodes, admit safe memory declassifications, and resolve semantic adjudication tasks inside policy gates. |
| `autonomous_max` | Same as guarded but with larger exploration budgets, wider trial/canary lanes, more retry/adjudication attempts, lower soft-threshold entry points, and more aggressive threshold-deadlock remediation. It does not lower hard safety, privacy, schema, scanner, rollback, ownership, or path-containment invariants. |
| `frozen` | Emergency stop. Capture may continue; mutation and context hints stop. Raw-evidence capture may continue only when incident policy explicitly permits it. |

### 5.1 Hard invariants versus calibrated soft thresholds

The implementation must not let arbitrary deterministic thresholds grind autonomy to a halt. Gates are divided into two classes.

**Hard invariants** are non-negotiable safety, integrity, privacy, ownership, compatibility, and reversibility requirements. A hard-invariant failure rejects, quarantines, freezes, or rolls back automatically. Examples:

- invalid OpenClaw `SKILL.md` format;
- path escape, symlink escape, or attempt to write outside approved roots;
- missing rollback pointer, manifest hash, provenance edge, or evolution transaction;
- failed critical scanner finding;
- forbidden capability expansion;
- secret leakage into embeddings, runtime skill text, normal logs, or support artifacts;
- raw-evidence exposure forbidden by deployment policy;
- unqualified text or embedding profile for the required sensitivity level;
- evaluator infrastructure unavailable for an action that requires evaluation;
- mutation of non-SkillKernel-owned roots;
- request to install hooks, tools, services, MCP servers, providers, or schedulers outside approved adjunct templates.

**Calibrated soft thresholds** are adaptive decision aids. They influence routing, priority, confidence, exploration, canary size, replay inclusion, evidence budgets, and operation selection, but they do not directly force human involvement. Examples:

- recurrence count;
- projected utility;
- evidence confidence;
- topology operation score;
- memory declassification confidence;
- replay-intent confidence;
- target-probe pass rate near boundary;
- context-token pressure;
- retrieval similarity;
- candidate priority;
- archive/promotion utility margins.

When a soft threshold is not met, SkillKernel must choose a non-blocking autonomous exit before administrative escalation:

```text
collect_more_evidence
run_additional_retrieval
use_raw_vault_context_if_policy_allows
run_llm_re_adjudication
run_independent_verifier_adjudication
create_ephemeral_candidate
reduce_scope
decompose_candidate
compile_more_conservatively
generate_more_probes
run_counterfactual_trial
canary_with_smaller_exposure
record_pending_candidate
auto_reject_with_reason
no_op_with_reschedule
```

A soft-threshold miss is an evidence-quality or calibration signal, not a stop sign.

### 5.2 Autonomous Decision Orchestrator

All semantic or topology-changing workflows pass through the Autonomous Decision Orchestrator. The orchestrator combines LLM semantic judgment, calibrated reliability estimates, deterministic admissibility checks, and operation risk to choose the next autonomous action.

Required orchestrator inputs:

```text
objective
operation_kind
action_risk_tier
evidence_packet_ids
raw_vault_access_decision
source_fidelity_tiers
source_taint
LLM structured verdict
LLM rationale evidence IDs
semantic_uncertainty_signals
repeated_adjudication_agreement
confidence decomposition
calibration_family
calibration_policy_version
hard_invariant_results
soft_threshold_results
scanner/evaluator/probe results
risk class
reversibility class
canary eligibility
current deployment autonomy mode
```

Required orchestrator outputs:

```text
auto_accept
auto_reject
collect_more_evidence
run_more_probes
run_re_adjudication
run_verifier_adjudication
stage_ephemeral_candidate
stage_canary
reduce_scope
quarantine
freeze
rollback
escalate_admin
no_op_reschedule
```

The LLM is allowed to decide semantic meaning, user intent, candidate purpose, redacted replay intent, memory interpretation, topology relationship, context equivalence, and whether an ambiguous case is conceptually safe or useful. Deterministic infrastructure decides whether the LLM verdict is admissible, supported, reversible, policy-compliant, and executable.

### 5.3 Action risk tiers

Risk is assigned to actions, not to entire components. The same subsystem may run fully autonomously for one action and require predelegated authority for another.

| Tier | Example action | Normal autonomy behavior |
|---|---|---|
| `T0_observe` | read telemetry, compute metrics, scan existing artifacts | Always autonomous when source access is configured. |
| `T1_internal_record` | create evidence packet, declassified summary, replay draft, memory verdict, broker diagnostic | Autonomous when schema, provenance, redaction, and raw-access policy pass. |
| `T2_trial_artifact` | stage SkillIR, SkillGraphIR, probes, package draft, ephemeral candidate | Autonomous when hard invariants pass; soft misses route to narrower trial, more evidence, or canary preparation. |
| `T3_owned_runtime_change` | activate SkillKernel-owned skill canary, promote archived SkillKernel skill, update broker policy, archive low-utility owned skill | Autonomous in `autonomous_guarded` when regression, scanner, context, canary, and rollback gates pass. |
| `T4_external_or_irreversible` | mutate external-owned root, reveal raw private content, install new hook/tool/service/provider, alter infrastructure policy | Requires explicit predelegated policy authority or admin action. If such authority is absent, the system creates an adjunct request and continues all reversible internal work. |

This tiering prevents brittle manual gates for routine semantic work while preserving hard trust boundaries around irreversible or externally owned effects.

### 5.4 Composite and calibrated confidence

SkillKernel must not trust verbalized model confidence alone. The decision confidence used for autonomous action is a composite score built from:

- model-provided structured confidence;
- evidence coverage;
- source-fidelity tier;
- recurrence and cross-session diversity;
- agreement between independent evidence clusters;
- agreement between repeated adjudication passes when used;
- semantic uncertainty or answer dispersion when sampled adjudication is used;
- contradiction checks against surrounding turns, memories, and skill history;
- scanner risk;
- evaluator/probe margin;
- reversibility;
- canary containment;
- model-profile qualification status;
- historical calibration outcomes for similar decisions;
- delayed production outcomes from prior decisions in the same calibration family.

Confidence bands are risk-weighted and calibrated per decision family:

| Band | Meaning | Default action |
|---|---|---|
| `clear_accept` | Strong evidence, high calibrated confidence, no hard-invariant failure, reversible or canaried | Apply autonomously or canary. |
| `clear_reject` | Strong evidence the candidate is unsafe, redundant, harmful, private, or not useful | Reject autonomously with reason and provenance. |
| `improve_evidence` | Decision is promising but under-supported | Gather more data, retrieve raw context if allowed, run more probes, or re-adjudicate. |
| `narrow_scope` | Candidate is useful but too broad/risky/token-heavy | Decompose, scope down, create ephemeral candidate, or tighten broker trigger. |
| `canary_only` | Useful but insufficiently proven for full activation | Activate only in a bounded canary with rollback triggers. |
| `quarantine` | Potentially useful but policy/safety ambiguity remains | Quarantine and schedule automated re-analysis when new evidence arrives. |
| `admin_required` | Policy explicitly requires admin authority, raw reveal, or external/irreversible mutation without predelegated authority | Escalate with a complete evidence packet and suggested resolution. |

### 5.5 Calibration families and reliability metrics

Each autonomous semantic task belongs to a calibration family. Families must be calibrated separately because a model can be reliable at one semantic task and unreliable at another.

Default calibration families:

```text
intent_reconstruction
replay_episode_promotion
memory_declassification
external_skill_relationship
topology_operation_choice
skill_plan_semantic_adjudication
context_equivalence
semantic_compression_preservation
broker_decision_adjudication
freeze_repair_triage
```

For each family, SkillKernel records:

```text
verdict
structured confidence
confidence components
evidence-fidelity tier
selected autonomous action
action risk tier
soft thresholds applied
hard invariants checked
adjudication agreement/disagreement
canary/trial status
delayed outcome
user correction signal when available
regression/security/context findings
rollback/freeze outcome
```

Reliability metrics include:

```text
coverage_rate
false_accept_rate
false_reject_rate
abstention_rate
unnecessary_abstention_rate
post_abstention_success_rate
calibration_error
brier_like_score
reliability_bin_summary
mean_evaluator_margin
canary_failure_rate
rollback_rate
harm_finding_rate
utility_per_context_token
```

The system uses these metrics to adjust soft decision bands, not to bypass hard invariants.

### 5.6 Selective trust and selective abstention

The orchestrator implements selective trust. It trusts an LLM semantic verdict only when the calibrated confidence and evidence conditions for the relevant family and risk tier are satisfied. It abstains from immediate activation when reliability is not yet sufficient, but abstention must produce a productive autonomous next step.

Valid abstention outcomes:

```text
no_skill
no_op_reschedule
collect_more_evidence
re_adjudicate
run_verifier_adjudication
build_ephemeral_candidate
generate_more_probes
reduce_scope
canary_only
auto_reject
quarantine
freeze
rollback
```

Invalid abstention outcome:

```text
administrative_escalation_because_soft_threshold_missed
```

Administrative escalation requires one of these reasons:

```text
policy_forbids_needed_raw_access
raw_reveal_requested
external_owned_root_mutation_requested
irreversible_infrastructure_change_requested
required_infrastructure_unavailable
repeated_contradictory_adjudications_after_fallback
predelegated_authority_absent_for_T4_action
```

### 5.7 Independent adjudication and verifier passes

For high-impact or near-boundary decisions, SkillKernel may run additional LLM calls through the same configured text profile. This is not a per-operation model-routing matrix. It is repeated or role-separated adjudication under one active text profile.

Allowed patterns:

| Pattern | Use |
|---|---|
| `single_adjudication` | Routine low-risk semantic decisions. |
| `repeat_same_prompt_with_seed_variation` | Estimate semantic stability for ambiguous natural-language interpretation. |
| `independent_verifier_prompt` | Ask a separate prompt to find contradictions, privacy leakage, policy violations, or missing evidence. |
| `contrastive_alternative_prompt` | Compare create vs improve vs compose vs decompose vs no-op. |
| `semantic_equivalence_prompt` | Check that compressed runtime text preserves SkillIR intent. |

The system stores disagreement rather than hiding it. Agreement increases calibrated confidence only when historical calibration for that family shows that agreement predicts success. Disagreement routes to more evidence, narrower scope, canary, quarantine, or autonomous rejection before admin escalation.

### 5.8 Adaptive threshold lifecycle

Soft thresholds are stored as versioned policy records and calibrated from observed outcomes. They may differ by workspace, executor profile, task family, skill granularity class, operation kind, source-fidelity tier, risk class, calibration family, and autonomy mode.

Soft-threshold policies follow this lifecycle:

```text
draft
→ replay_backtest
→ shadow_mode
→ canary_policy
→ active
→ retired_or_rolled_back
```

A threshold-policy update may be produced by deterministic analysis, LLM root-cause adjudication, or both. Activation requires deterministic evaluation on historical replay, canary data, and regression/security/context metrics. The update must record which stalled decisions it would unblock and which failure modes it may increase.

Threshold adaptation may change:

```text
soft evidence requirements
candidate priority
minimum recurrence for trial entry
probe budget
re-adjudication budget
canary exposure size
archive/promotion margins
context-pressure response thresholds
no-op/reschedule timing
```

Threshold adaptation may not change:

```text
path containment
ownership boundaries
secret handling
raw-access policy
scanner hard denies
OpenClaw skill-format validity
rollback requirements
external infrastructure authority
mandatory audit/provenance
```

### 5.9 Conformal and empirical calibration policy

Where enough exchangeable or approximately comparable calibration data exists, SkillKernel may use conformal or conformal-inspired selective calibration to choose accepted sets, action bands, or abstention policies for a decision family. The implementation must not overclaim statistical guarantees when calibration data is sparse, stale, non-exchangeable, or drawn from a different executor profile/task family.

Required behavior:

```text
if calibration_data_sufficient_and_comparable:
  use calibrated risk target for acceptance/canary/abstention band
else:
  mark calibration as empirical_low_support
  prefer reversible actions: more evidence, ephemeral candidate, narrower scope, canary, or auto-reject
```

Calibration state is surfaced in audit records and Observatory. A high-confidence LLM verdict with low calibration support can still proceed through reversible trial/canary lanes, but it does not receive the same authority as a well-calibrated decision family.

### 5.10 Threshold-deadlock prevention

The system must maintain a threshold-deadlock detector. A deadlock exists when candidates repeatedly stall for soft-threshold reasons while hard invariants pass and LLM adjudication indicates high utility or high user-intent confidence.

Deadlock handling is autonomous:

```text
create threshold_deadlock finding
retrieve stalled candidate cohort
run LLM root-cause adjudication
classify bottleneck as evidence, calibration, probe, scope, context, risk, or policy
refresh evidence window
retrieve richer redacted derivatives
retrieve raw-vault context when policy allows
run re-adjudication or verifier adjudication
generate narrower probes
narrow the operation scope
create an ephemeral candidate
canary with lower exposure
auto-reject with reason
no-op with reschedule
propose calibrated threshold-policy update when appropriate
evaluate threshold-policy update on replay and shadow data
activate policy update only if regression/security/context metrics pass
escalate only for explicit hard-boundary reasons
```

No candidate may bypass hard invariants through threshold adaptation. Threshold adaptation only changes soft routing, candidate priority, evidence budgets, canary sizing, and operation selection policy.

### 5.11 Default action rules

Default action rules:

1. If evidence is weak, preserve the evidence packet, schedule more evidence collection when plausible, create an ephemeral candidate when useful, or record a no-op with reschedule; do not discard useful signal silently.
2. If a matching active skill exists, improve or recompile it rather than create a new one.
3. If a matching archived skill exists, promote or repair it rather than create a new one.
4. If sibling skills conflict, merge/split/clarify before creating.
5. If a change fails a hard scanner invariant, reject, quarantine, freeze, or roll back.
6. If a change narrowly misses a soft target evaluation threshold, run more probes, narrow scope, re-adjudicate, or canary rather than escalating by default.
7. If a change fails a hard regression budget, reject, repair in trial mode, or decompose/narrow the candidate.
8. If canary fails after activation, roll back.
9. If repeated failures occur, freeze the skill, launch automated root-cause/adjudication/repair jobs in trial mode, and unfreeze only after a passed repair/canary transaction or explicit admin override.

Quarantine is not the normal workflow. It is an exception bucket for potentially useful but unsafe, ambiguous, or policy-limited artifacts. Ordinary semantic uncertainty is routed to autonomous LLM adjudication first; quarantine or administrative escalation is used only after configured autonomous fallback actions fail or policy forbids the needed evidence/action.

---

### 5.12 Autonomy assurance and evidence-completeness requirements

SkillKernel must avoid two failure modes at the same time: unsafe model overreach and quiet autonomy collapse. The system therefore treats LLM semantic adjudication, deterministic admissibility, and reversible execution as separate but cooperating powers.

SkillKernel's autonomy also depends on retaining enough governed semantic evidence for the configured LLM to reconstruct intent, workflow meaning, and operational consequences. The system must not replace needed semantic evidence with hashes and then treat the resulting ambiguity as a routine administrative review requirement.

Autonomy assurance rules:

1. A semantic decision that can be made from permitted evidence must be routed to LLM adjudication before administrative escalation is considered.
2. A hard invariant failure results in reject, quarantine, freeze, rollback, or explicit admin escalation according to policy; it is not softened by model confidence.
3. A soft threshold miss triggers autonomous next actions first: gather more evidence, widen or shift the permitted context window, re-adjudicate, run an independent verifier pass, generate additional probes, reduce scope, convert to ephemeral candidate, canary narrowly, auto-reject with reason, or reschedule.
4. A model verdict is admissible only when it cites evidence IDs, exposes uncertainty factors, passes schema validation, passes redaction and taint checks, and fits the calibrated decision family.
5. The system records both over-action and over-deferral. Over-action includes canary regression, rollback, scanner discovery, privacy leak, or harmful activation. Over-deferral includes repeated no-op/escalation when later evidence shows an autonomous action would have been safe and useful.
6. Threshold policies are calibrated artifacts. They can be updated through replay, shadow mode, canary, and outcome feedback, but cannot alter hard invariants or grant new capability surfaces.
7. Administrative escalation is an exception path with an allowed reason code, not a substitute for semantic reasoning.

Full-autonomy mode requires these additional evidence-completeness rules:

1. **Semantic evidence is retained or derivable.** For any decision family that needs user intent, task context, tool-result meaning, skill visibility, or outcome interpretation, the evidence packet must reference either raw-vault-linked records, trajectory/transcript windows, or declassified semantic derivatives that preserve the necessary meaning.
2. **Hash-only telemetry is explicitly degraded.** Hashes are useful for idempotency, deduplication, and correlation. They are not sufficient for user-intent reconstruction, replay-corpus promotion, memory declassification, topology choice, or semantic compression verification unless joined to preserved semantic evidence.
3. **The LLM adjudicates meaning when deterministic code cannot.** Routine ambiguity is resolved by assembling permitted evidence and running structured LLM adjudication. The LLM verdict may classify intent, declassify memory, synthesize redacted replay intent, choose a topology operation, or reject a candidate when its confidence is calibrated and deterministic admissibility checks pass.
4. **Deterministic gates enforce admissibility, not semantics-by-default.** Deterministic code validates schema, provenance, redaction, scanner findings, policy, rollback, path containment, ownership, evaluator results, and hard invariants. It does not block an otherwise admissible semantic decision merely because a fixed soft threshold is near a boundary.
5. **Administrative escalation is exceptional and measurable.** Escalation is allowed only for configured authority gaps: forbidden raw exposure, raw reveal, irreversible external mutation, infrastructure installation, missing required infrastructure, repeated contradictory adjudications after autonomous fallback, or absent predelegated authority for a `T4_external_or_irreversible` action.
6. **Repeated escalation is an autonomy defect.** If a decision family repeatedly escalates while hard invariants pass, the threshold-deadlock detector must open a finding, run autonomous root-cause analysis, and attempt policy/evidence/probe/scope/canary remediation.
7. **Full autonomy is scoped by ownership and reversibility.** SkillKernel-owned reversible changes can be made autonomously after gates pass. Non-SkillKernel-owned roots, raw reveal, new runtime capabilities, external infrastructure, and irreversible changes require predelegated authority or administrative action. This is a hard ownership/security boundary, not a semantic-review fallback.

Autonomy claims must be reported by evidence mode:

| Evidence mode | Autonomy claim | Normal behavior |
|---|---|---|
| `full_semantic` | Full SkillKernel autonomy is available for covered decision families. | Raw-vault-linked or declassified semantic evidence supports LLM adjudication and deterministic activation. |
| `semantic_derivative_only` | High autonomy is available, but some replay/probe fidelity is reduced. | Use declassified summaries and trajectories; prefer reversible actions and canaries for high-impact changes. |
| `metadata_only` | Limited autonomy. | Mine aggregate patterns, but do not claim reliable intent reconstruction without additional evidence. |
| `hash_only` | Correlation only. | Use for deduplication and counters; never promote durable replay episodes, memory declassification, or topology changes from hashes alone. |

The result is calibrated autonomy: the model is trusted for meaning when its configured profile and evidence support the task; deterministic infrastructure remains responsible for safety, execution, durability, and auditability. A deployed system that disables semantic evidence retention may still provide observability, aggregate mining, and conservative suggestions, but it must not present itself as fully autonomous for decisions that require intent interpretation.

### 5.13 Semantic autonomy decision matrix

Semantic decision families must declare the evidence fidelity they require for full autonomy. This prevents two failure modes: pretending hash-only telemetry is enough for meaning, and escalating ordinary semantic work even though permitted evidence exists.

| Decision family | Minimum evidence for full-autonomy path | LLM semantic authority | Deterministic authority boundary | Default autonomous fallback when evidence is insufficient |
|---|---|---|---|---|
| `intent_reconstruction` | `raw_vault_linked` prompt/turn/tool window, or `declassified_summary` with source links and contradiction check | Infer user goal, task family, sensitive fields to omit, and confidence bottlenecks. | Secret masking, declassification report, source provenance, retention policy, and output schema. | Assemble wider permitted window; synthesize lower-confidence derivative; mark degraded; reschedule or no-op without claiming intent certainty. |
| `replay_episode_promotion` | `raw_vault_linked` or declassified turn/tool window plus broker decision context | Synthesize `redacted_user_intent`, expected skill decision, avoid-list, and rationale codes. | Redaction scan, replay reproducibility, evidence links, confidence band, policy, and canary eligibility. | Keep as replay draft, run more retrieval reconstruction, create degraded candidate, or skip durable replay promotion. |
| `memory_declassification` | Source memory plus provenance, trust, taint, and enough surrounding context to classify intent | Decide whether candidate is operational lesson, evidence-only, private fact, contradiction, poisoned instruction, or low-confidence. | Scanner hard findings, privacy policy, taint policy, TTL, provenance, and derived-data revocation links. | Keep quarantined, transform to evidence-only, reject, or request more source context. |
| `external_skill_relationship` | External skill body/metadata/support manifest plus local active/archive skill body-level representation | Classify overlap, shadowing, complementarity, conflict, adapter opportunity, or replacement opportunity. | External ownership boundary, scanner results, package trust, active-root write rules, and mutation prohibition for external-owned roots. | Inventory only, suppress risky routing, create SkillKernel-owned candidate, or emit adjunct request. |
| `topology_operation_choice` | Evidence packet with co-use/order/outcome/correction/context-cost data and candidate skill matches | Choose create, improve, compose, decompose, no-op, or supporting action and explain the tradeoff. | Operation state machine, evaluator/probe gates, context budget, regression budget, ownership, rollback, and canary policy. | Trial multiple alternatives, narrow scope, create ephemeral candidate, generate probes, or defer with scheduled evidence collection. |
| `context_equivalence` | SkillIR revision, compiled runtime artifact, support-artifact summary, probes, and representative evidence | Judge whether compressed runtime text preserves operational meaning and failure boundaries. | Token budget, forbidden-content scan, semantic-density gate, probe pass/fail, context-regression check, and manifest hash. | Recompile, move detail to support file, decompose broad skill, reduce trigger surface, or reject compiled artifact. |
| `broker_decision_adjudication` | Retrieval candidates, broker features, rendered context, final outcome, and action attribution signals | Explain why a skill should have been loaded, hidden, suppressed, or replaced by no-skill. | Runtime hook no-LLM rule, broker policy versioning, shadowing controls, active-bank constraints, and canary rollout. | Update broker diagnostics, add replay episode, run shadow evaluation, tune soft policy, or leave current policy unchanged. |

A decision family may run in degraded mode with lower-fidelity evidence, but degraded mode has narrower authority. It may produce diagnostics, weak candidates, ephemeral candidates, or no-op/reschedule records. It may not silently produce durable replay truth, memory influence, topology mutation, or broad runtime activation when the evidence cannot support those decisions.

### 5.14 Threshold-governance contract

Soft thresholds are governed policy artifacts. Each threshold used by the Autonomous Decision Orchestrator must have:

- a named decision family;
- a reason code;
- a hard-invariant relationship, if any;
- an evidence-fidelity requirement;
- a default autonomous fallback ladder;
- calibration-support status;
- an expected effect on coverage, false accepts, false rejects, context cost, canary risk, and rollback rate;
- replay/shadow/canary evidence before broad activation;
- rollback criteria for the threshold policy itself.

Threshold policies may tighten automatically after scanner failures, canary regressions, rollback spikes, harmful-capability findings, privacy leaks, context regressions, or drift incidents. Threshold policies may relax only through replay backtests, shadow-mode comparison, limited canarying, and recorded improvement in autonomy without unacceptable increases in false accepts, harm findings, context cost, or rollback rate. Hard invariants cannot be relaxed by threshold policy.

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
| `skillkernel_generated` | previously generated skill version that passed gates | Yes |
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
6. Secrets and credentials are blocked from embeddings, skill text, support artifacts, normal logs, and ordinary analytics. They may appear only in raw-evidence vault records when raw retention is enabled, encrypted, access-controlled, short-retention by policy, and never exposed to hosted LLMs unless the operator explicitly allows that sensitivity tier.

### 6.1 Sidecar deployment and filesystem access boundaries

SkillKernel is deployed as a sidecar service, but the sidecar is not allowed to treat the operator's home directory or OpenClaw state directory as an unbounded read/write workspace. Deployment must declare exact roots, mount modes, and path mappings.

Required filesystem access classes:

| Path class | Default access | Purpose | Constraint |
|---|---|---|---|
| Active SkillKernel skill root | read/write | staged activation of compiled OpenClaw `SKILL.md` artifacts | must be under the configured OpenClaw workspace skill root and must contain only SkillKernel-owned directories |
| SkillKernel staging root | read/write | render, scan, hash, and evaluate candidate artifact sets before activation | must be outside OpenClaw-visible skill roots |
| SkillKernel archive root | read/write | immutable archived versions, rollback snapshots, and manifests | must be outside OpenClaw-visible skill roots |
| OpenClaw session stores and transcripts | read-only by default | historical ingestion and reconciliation | write access is not required; imports must tolerate pruning, reset archives, deleted-session archives, and orphan files |
| OpenClaw trajectory sidecars/exports | read-only by default | high-fidelity historical backfill and replay | imports respect truncation/redaction flags and never regenerate exports automatically unless explicitly configured |
| Workspace memory/context files | read-only by default | historical evidence, context-policy inventory, and memory-provenance import | direct mutation is not allowed; SkillKernel writes only its own generated skill artifacts and internal state |
| Diagnostic/raw-stream imports | disabled/read-only when enabled | explicit debugging import | never enabled by default because these files may contain raw prompts, tool outputs, and secrets |

Container deployments must provide explicit host-to-container path mappings. A path discovered from OpenClaw metadata is not trusted until it resolves inside a configured mounted root and survives realpath containment checks. If the Gateway and sidecar use different container mount prefixes, SkillKernel stores both the OpenClaw-reported path and the sidecar-resolved path with a mapping record.

Required deployment controls:

1. Run the sidecar as a non-root user unless an operator explicitly accepts a broader host-maintenance role.
2. Mount only the OpenClaw state roots, workspace roots, SkillKernel roots, and configured import roots required by the deployment.
3. Mount historical source roots read-only unless a specific writer job needs write access to a SkillKernel-owned root.
4. Reject symlink escapes, hardlink surprises, device files, sockets, FIFOs, world-writable plugin/skill roots, and files whose resolved path leaves the configured root.
5. Keep plugin-to-sidecar traffic on loopback, a Unix-domain socket, or a private container network with token/mTLS authentication.
6. Never expose the sidecar control API on a public interface.
7. Store sidecar credentials separately from OpenClaw model/provider credentials.
8. Treat remote Gateway deployments as explicit import jobs: either run the sidecar on the Gateway host, mount the Gateway state/workspace roots read-only, or use documented Gateway/CLI/export surfaces.

Configuration must support these deployment fields:

```yaml
skillkernel:
  deployment:
    sidecar_bind: "127.0.0.1:8765"
    sidecar_auth: token_env          # token_env | mtls | unix_socket
    sidecar_token_env: SKILLKERNEL_SIDECAR_TOKEN
    unix_socket_path: null
    run_as_non_root: true
    allow_public_bind: false

  paths:
    openclaw_home_env: OPENCLAW_HOME
    openclaw_state_dir_env: OPENCLAW_STATE_DIR
    openclaw_config_path_env: OPENCLAW_CONFIG_PATH
    openclaw_state_dir_default: "~/.openclaw"
    workspace_roots: []             # optional explicit roots; empty means discover from OpenClaw config/session metadata
    session_store_roots: []         # optional extra roots for nonstandard deployments
    trajectory_roots: []            # optional extra roots including OPENCLAW_TRAJECTORY_DIR
    transcript_corpus_roots: []     # optional extra transcript-corpus roots
    host_container_path_map: []     # [{host: "/home/alex/.openclaw", container: "/mnt/openclaw"}]
```

The sidecar may write only to `active_root`, `archive_root`, `staging_root`, Postgres, and its own temporary/cache directories. All other OpenClaw state is imported as evidence, not modified.

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
- optional fast runtime skill-context hint injection;
- optional content-safe agent-event/diagnostic subscription when supported;
- optional plugin-bundled internal-hook observation for coarse command/transcription/preprocessing events;
- optional OpenClaw-routed model relay outside hook execution when explicitly configured.

It does not perform:

- semantic LLM analysis inside hooks;
- candidate mining;
- scheduling;
- database maintenance;
- scanner evaluation beyond local hard denylists;
- arbitrary filesystem mutation;
- skill generation;
- skill improvement;
- skill archiving/promotion logic.

### 7.2 OpenClaw live-ingestion surfaces

SkillKernel captures live OpenClaw activity through stable typed plugin surfaces first. The plugin uses `api.on(...)` typed hooks for ordered middleware, policy, prompt shaping, message observation, tool observation, and lifecycle observation. The plugin uses documented agent-event subscriptions and runtime event notices when the installed SDK exposes them. Plugin-bundled internal hooks are optional coarse event listeners only; they are not the primary policy or evidence-capture substrate.

Live capture is divided into four ingestion categories:

| Tier | Surface | Use | Constraint |
|---|---|---|---|
| Primary | typed plugin hooks via `api.on(...)` | ordered runtime observation and bounded control | keep handlers fast; never run semantic LLM analysis, candidate mining, evaluator jobs, or file mutation in the hook path |
| Primary | `api.agent.events.registerAgentEventSubscription(...)` when exposed by the installed SDK | sanitized agent/runtime event subscriptions for workflow state, monitors, and content-safe observability | treat as event sources, not autonomous mutation triggers |
| Supplemental | `api.runtime.events.onAgentEvent(...)` and `api.runtime.events.onSessionTranscriptUpdate(...)` when exposed by the installed SDK | low-friction notices that agent events or persisted transcript state changed | optional; if unavailable, rely on transcript/trajectory importers and session lifecycle hooks |
| Supplemental | `api.onConversationBindingResolved(...)` when exposed by the installed SDK | channel/thread/user-to-session binding evidence, routing context, and session-key reconciliation | optional correlation source; do not treat binding success as task success |
| Secondary | plugin-bundled internal hooks (`HOOK.md`/handler packages) when OpenClaw internal-hook discovery is enabled | coarse command/lifecycle/transcription/preprocessing compatibility signals | optional; use only for side effects or gap filling when no typed hook/event subscription exists |
| Historical | sidecar importers over state/workspace files, task ledgers, transcripts, trajectory artifacts, memory/context files, and explicit exports | bootstrap established deployments and recover evidence missed by live hooks | always pass through redaction, taint, provenance, evidence maturity, scanner, and evaluation gates |

The plugin registers these typed hooks when supported by the installed OpenClaw version:

| OpenClaw area | Hook names | SkillKernel evidence value | SkillKernel behavior |
|---|---|---|---|
| Model resolution | `before_model_resolve` | current prompt and attachment metadata plus requested/default provider, model, and thinking-policy facts; resolved values are joined later from model-call, agent-end, subagent, session, and trajectory records | observe model routing; do not override the user session model unless the operator explicitly enables a SkillKernel model-relay profile |
| Same-turn context preparation | `agent_turn_prepare` | prepared session messages, queued exactly-once injections drained for the session, run/session correlation | consume sidecar-cached broker hints only when prompt-injection trust is enabled and the hint is within token/latency budget |
| Prompt/context construction | `before_prompt_build` | loaded messages, prompt-building phase, opportunity for bounded cached broker hint injection | inject only token-budgeted, cached, scanner-clean hints when prompt-injection trust is enabled; otherwise observe or skip |
| Agent run start/control | `before_agent_start`, `before_agent_run`, `before_agent_reply` | turn start, user input, loaded history, system prompt visibility, synthetic-reply/block decisions by other plugins | prefer explicit phase hooks over compatibility-only `before_agent_start`; capture turn envelope and prompt/context metadata; do not run slow analysis |
| Agent run finalization/end | `before_agent_finalize`, `agent_end` | final answer acceptance, final message list, run metadata, duration, terminal status | capture outcome, finalization behavior, correction windows, and trace correlation; bound flushing because hook execution may be timeout-limited |
| Heartbeat turns | `heartbeat_prompt_contribution` | heartbeat-only context opportunities, lifecycle-monitor state, recurring background check-ins | provide only compact cached status/hints for heartbeat turns; do not alter normal user-initiated turns through this hook |
| Provider-call telemetry | `model_call_started`, `model_call_ended` | sanitized provider/model attempt metadata, timing, outcome, request-id hashes, API/transport, effective context token budget | capture as low-content telemetry; no raw prompts, responses, headers, or request bodies should be required |
| Raw model input/output | `llm_input`, `llm_output` | system prompt, prompt, history, provider output, usage, resolved context token budget | capture only when explicit conversation-access trust is enabled; write raw content to the governed raw-evidence path when retention policy allows; write redacted/minimized derivatives to normal event/evidence stores; embed only redacted or declassified text |
| Tool execution | `before_tool_call`, `after_tool_call` | tool name/kind, params, approvals/blocks, result class, errors, latency, retries | capture before/after pairs and outcome attribution data; enforce deterministic guard templates for risky operations where enabled |
| Exec environment | `resolve_exec_env` | host/sandbox/node execution context and plugin-contributed environment facts | capture executor-profile facts only; do not inject secrets or broad environment changes |
| Tool persistence | `tool_result_persist`, `before_message_write` | transformed persisted tool result, bounded metadata, transcript-persistence behavior, write-attempt signals | capture persisted form for replay alignment; do not place prompt-critical text only in stripped metadata |
| Inbound messages | `inbound_claim`, `message_received` | sender, channel/thread, inbound content, reply metadata, delivery context, user corrections | capture user-turn evidence and corrections after local redaction |
| Outbound messages | `message_sending`, `reply_payload_sending`, `before_dispatch`, `reply_dispatch`, `message_sent` | assistant output, normalized reply payloads, cancellation/rewrite/delivery success/failure | capture delivery and correction evidence; never leak hidden broker/runtime metadata into user-visible payloads |
| Conversation binding | `api.onConversationBindingResolved(...)` SDK callback when present | channel/thread/user-to-agent binding, session-key mapping, direct/group routing facts, correlation between inbound channel messages and OpenClaw sessions | capture routing/correlation metadata only; never infer task completion from binding success |
| Sessions | `session_start`, `session_end` | lifecycle boundaries and reasons such as new, reset, idle, daily, compaction, deleted, shutdown, restart, unknown | start/end trace spans and close ghost sessions after shutdown/restart |
| Reset/compaction | `before_reset`, `before_compaction`, `after_compaction` | reset events, compaction cycles, summary checkpoints, evidence at risk of context loss | mark compaction-derived evidence as lower confidence; trigger import/reconciliation jobs |
| Subagents | `subagent_spawned`, `subagent_ended`; `subagent_delivery_target` only as compatibility observation when present | child session creation, completion, model/provider, delivery path, delegated workflow topology, detached outcome | link parent/child workflows and co-used skill sequences; child transcripts are imported through session/trajectory sources; do not infer success from spawn alone |
| Gateway lifecycle | `gateway_start`, `gateway_stop` | plugin service startup/shutdown, workspace/config access, graceful flush windows | verify roots, connect sidecar, drain spool, and close open trace/session records |
| Gateway-owned cron observation | `cron_changed` | external OpenClaw cron lifecycle facts that may later explain sessions/tasks | observe only as environmental evidence; never use OpenClaw Cron as SkillKernel's scheduler |
| Install scanning | `before_install` | skill/plugin install scan findings and install-block opportunities | record environment changes; optionally block clearly unsafe skill/plugin installs according to deterministic policy |

Conversation-bearing hooks require explicit operator trust. A non-bundled SkillKernel plugin must not assume raw prompt, history, response, or conversation access. Full-autonomy quality requires conversation-bearing access or equivalent authorized trajectory/transcript import because replay-corpus construction, user-intent inference, attribution, and topology decisions depend on original semantic context. When the required OpenClaw trust gate is absent, SkillKernel still captures non-content telemetry, tool metadata, session lifecycle, delivery metadata, trajectories, compaction summaries, and historical files, but the deployment runs in degraded evidence-fidelity mode with lower recall, lower confidence, fewer automatic replay/canary episodes, and more escalation/no-op decisions.

Prompt mutation is a separate trust gate from conversation reading. SkillKernel can capture events without prompt-injection permission. Runtime broker hints require prompt-injection permission and strict latency/token limits. If prompt mutation is disabled, the runtime broker still evaluates retrieval decisions offline and logs what it would have rendered for replay; it does not modify the live turn.

Supplemental plugin-bundled internal hooks may be used only for coarse event compatibility where typed plugin hooks do not expose equivalent content. Useful internal events include `command:new`, `command:reset`, `command:stop`, `session:compact:before`, `session:compact:after`, `session:patch`, `agent:bootstrap`, `message:received`, `message:transcribed`, `message:preprocessed`, and `message:sent`. These hooks are optional telemetry sources, not the authoritative control plane. They are useful for audio transcription evidence, link/media preprocessing evidence, command/reset correlation, and bootstrap-context inventory. SkillKernel must continue operating without them.

Trusted or bundled deployments may also observe pre-model tool-result normalization through OpenClaw tool-result middleware when the target runtime exposes that surface and the operator explicitly enables it. External plugin deployments do not rely on that path. The ordinary v1 capture path remains `before_tool_call`, `after_tool_call`, `tool_result_persist`, transcript import, and trajectory import.

Trajectory capture is not treated as a live typed plugin hook. Trajectory sidecars and trajectory exports are historical/backfill datasources containing prompts, tools, active skills, model settings, runtime settings, usage metadata, errors, prompt-cache details, and selected context-building details. Live hooks preserve enough correlation metadata to link later trajectory imports to the original run.

Context-engine plugins are not required for SkillKernel. OpenClaw context engines can participate in ingest, assemble, compact, and after-turn phases, but SkillKernel does not replace the configured context engine in v1. SkillKernel observes actual prompt/context behavior through `before_agent_run`, `llm_input` when permitted, context-budget metadata, transcript updates, and trajectory imports. Runtime skill-context hints use prompt/context hooks only when OpenClaw exposes the needed hook and the operator allows prompt injection.

Diagnostic and raw-stream surfaces are supplemental only. Diagnostic trace context should be propagated into SkillKernel's trace spine when present. Raw stream logs and raw provider payload logs are explicit debugging imports only, because they may contain full prompts, tool output, user data, and secrets. They are never enabled or ingested by default.

Runtime registration must be verified during install and health checks with OpenClaw runtime inspection. The plugin records which typed hooks, agent-event subscriptions, runtime event subscriptions, session-update notices, internal-hook bundles, permissions, and prompt-injection capabilities are actually active so the sidecar can grade evidence confidence instead of assuming all surfaces are available.

### 7.3 Event envelope

All plugin events share this shape:

```json
{
  "event_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "schema_version": 1,
  "workspace_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  "agent_id": "string-or-null",
  "session_id": "string-or-null",
  "turn_id": "string-or-null",
  "event_type": "tool_call_end",
  "occurred_at": "2026-06-01T12:00:00Z",
  "source": "openclaw-plugin",
  "source_event_key": "stable-source-id-or-event-id",
  "trust": "tool_output",
  "taint": ["runtime", "untrusted_output"],
  "redaction_state": "redacted",
  "evidence_fidelity": "redacted_derivative",
  "raw_evidence_record_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "payload_hash": "sha256:5f2d8d8f8f0f62c01c6f9b7e6d2a0c5e88f5f7b0a0d3c4b6e7f8a9b0c1d2e3f4",
  "payload": {},
  "plugin_version": "1.0.0",
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
- no secrets in normal spool; raw-content spool entries are encrypted, separately tagged, short-retention, and readable only by the sidecar raw-evidence importer;
- no blocking OpenClaw if sidecar is down.

### 7.5 Runtime skill-context hint path

The plugin may register a prompt/context hook that asks the sidecar for a tiny per-turn context hint.

This path is enabled only when OpenClaw exposes a prompt/context injection hook for the installed version and the operator allows prompt injection for the SkillKernel plugin. If prompt injection is disabled, unavailable, or over budget, SkillKernel still captures events and performs maintenance; it simply does not inject runtime hints.

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
- Most likely relevant skill: pdf-table-repair.
- Use when: task involves extracting structured tables from PDFs after normal parse fails.
- Do not use when: task is only summarizing text or editing a PDF layout.
- Related prerequisite: pdf-screenshot-inspection, only if visual table lines are missing.
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
| historical ingestion service | datasource discovery, dry-run inventory, import planning, safe parsing, redacted chunking, and backfill rollups for existing deployments |
| retrieval service | hybrid search and exact reranking |
| mining service | candidate discovery and duplicate matching |
| generation service | structured plan generation |
| raw-evidence vault service | encrypted raw evidence storage, retention, access checks, declassification jobs, and audit |
| autonomous adjudication service | LLM-assisted high-confidence decisions for intent, replay, memory, topology, external-skill relationships, and other semantic gates |
| replay-corpus builder | automatic redacted-intent synthesis and replay episode construction from live/historical evidence |
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
POST /v1/ingest/historical/discover
POST /v1/ingest/historical/import
GET  /v1/ingest/historical/runs
GET  /v1/evidence/raw-vault/status
POST /v1/evidence/adjudications/run
GET  /v1/evidence/adjudications/{adjudication_id}
GET  /v1/replay/candidates
POST /v1/replay/candidates/{candidate_id}/adjudicate
GET  /v1/health
GET  /v1/status
POST /v1/control/mode
POST /v1/control/freeze
POST /v1/control/unfreeze
POST /v1/runtime/context-hint
GET  /v1/relay/llm-requests
POST /v1/relay/llm-requests/{request_id}/claim
POST /v1/relay/llm-requests/{request_id}/complete
GET  /v1/skills
GET  /v1/skills/{skill_id}
GET  /v1/jobs
GET  /v1/audit/recent
```

All endpoints require localhost binding, a Unix-domain socket, or mTLS/token authentication on a private network. The control API is unavailable to remote callers by default. Health endpoints may return unauthenticated liveness only when configured, but readiness, status, jobs, audit, skills, relay, runtime hints, and ingest endpoints require authentication. Request bodies are size-limited, rate-limited, schema-validated, and rejected when the caller identity does not match the configured plugin/sidecar trust relationship.

### 8.3 Worker pools

Separate worker pools by risk and resource cost:

| Pool | Jobs |
|---|---|
| `ingest` | normalize live events, extract evidence |
| `backfill` | discover, fingerprint, parse, redact, chunk, and import historical data sources |
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
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
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

Idempotency keys and source-event keys must be stable but non-sensitive. When the natural key contains a path, user identifier, channel identifier, thread identifier, message text, or provider request identifier, SkillKernel stores a salted hash plus bounded metadata rather than the raw value.

### 9.3 Essential tables

DDL snippets are grouped by concept for readability. Migration files must be topologically ordered by foreign-key dependency, extension setup, and index dependency; snippets in this section are not a literal migration order.

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
  source_kind text NOT NULL DEFAULT 'live_hook',
  source_id text,
  source_event_key text NOT NULL,
  trust text NOT NULL,
  taint text[] NOT NULL DEFAULT '{}',
  redaction_state text NOT NULL,
  evidence_fidelity text NOT NULL DEFAULT 'redacted_derivative' CHECK (evidence_fidelity IN ('metadata_only','hash_only','redacted_derivative','declassified_summary','raw_vault_linked')),
  raw_evidence_record_id uuid,
  payload_hash text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, source_kind, source_event_key)
);

CREATE TABLE autoskill.raw_evidence_records (
  raw_evidence_record_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_event_hash text NOT NULL,
  source_kind text NOT NULL,
  source_id text,
  session_id text,
  turn_id text,
  raw_kind text NOT NULL CHECK (raw_kind IN (
    'user_prompt','agent_message','system_prompt','model_input','model_output','tool_params','tool_result','transcript_window','trajectory_window','memory_file','context_file','diagnostic_raw_stream','other'
  )),
  content_hash text NOT NULL,
  sensitivity_level text NOT NULL CHECK (sensitivity_level IN ('public','internal','private','secret_candidate','credential_candidate','unknown')),
  taint text[] NOT NULL DEFAULT '{}',
  retention_until timestamptz NOT NULL,
  encryption_key_id text NOT NULL,
  ciphertext bytea,
  external_ciphertext_ref text,
  compression text NOT NULL DEFAULT 'zstd',
  capture_policy_id text NOT NULL,
  redaction_policy_id text NOT NULL,
  access_policy jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  UNIQUE (workspace_id, source_event_hash, raw_kind, content_hash),
  CHECK ((ciphertext IS NOT NULL) OR (external_ciphertext_ref IS NOT NULL))
);


ALTER TABLE autoskill.raw_events
  ADD CONSTRAINT raw_events_raw_evidence_record_fk
  FOREIGN KEY (raw_evidence_record_id)
  REFERENCES autoskill.raw_evidence_records(raw_evidence_record_id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE autoskill.raw_evidence_access_log (
  raw_access_id uuid PRIMARY KEY,
  raw_evidence_record_id uuid NOT NULL REFERENCES autoskill.raw_evidence_records(raw_evidence_record_id),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  job_id uuid,
  purpose text NOT NULL,
  accessor_kind text NOT NULL CHECK (accessor_kind IN ('sidecar_job','llm_profile','operator_ui','retention_job','scanner','evaluator')),
  model_profile_id uuid,
  exposure_level text NOT NULL CHECK (exposure_level IN ('metadata','redacted','secret_masked_raw','raw_local_only','raw_allowed_hosted')),
  decision text NOT NULL CHECK (decision IN ('allowed','denied','masked','expired','revoked')),
  reason_code text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.declassification_reports (
  declassification_report_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  source_raw_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  output_kind text NOT NULL CHECK (output_kind IN ('redacted_intent','semantic_summary','operational_fact','memory_candidate','replay_episode','topology_hint','rejected')),
  redaction_policy_id text NOT NULL,
  model_profile_id uuid,
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  privacy_risk numeric NOT NULL CHECK (privacy_risk >= 0 AND privacy_risk <= 1),
  output jsonb NOT NULL,
  scanner_status text NOT NULL CHECK (scanner_status IN ('passed','failed','quarantined','not_run')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.autonomous_adjudications (
  adjudication_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  job_id uuid,
  adjudication_kind text NOT NULL CHECK (adjudication_kind IN (
    'intent_reconstruction','replay_episode_promotion','memory_declassification','external_skill_relationship','topology_operation_choice','policy_safe_action','skill_plan_semantic_adjudication','context_equivalence','quarantine_release','freeze_repair_triage'
  )),
  input_event_ids uuid[] NOT NULL DEFAULT '{}',
  input_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  input_raw_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  model_profile_id uuid,
  llm_verdict jsonb NOT NULL,
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  deterministic_checks jsonb NOT NULL DEFAULT '{}',
  decision text NOT NULL CHECK (decision IN ('auto_accept','auto_reject','collect_more_evidence','run_more_probes','run_re_adjudication','run_verifier_adjudication','stage_ephemeral_candidate','stage_canary','reduce_scope','quarantine','freeze','rollback','escalate_admin','no_op_reschedule')),
  escalation_reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.autonomy_policy_versions (
  autonomy_policy_version_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  policy_kind text NOT NULL CHECK (policy_kind IN ('decision_orchestrator','candidate_thresholds','acceptance_bands','broker_policy','curation_policy','canary_policy')),
  version_name text NOT NULL,
  policy jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','active','retired','quarantined')),
  activated_at timestamptz,
  retired_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, policy_kind, version_name)
);

CREATE TABLE autoskill.autonomy_calibration_observations (
  calibration_observation_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  calibration_family text NOT NULL,
  autonomy_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  model_profile_id uuid,
  adjudication_id uuid REFERENCES autoskill.autonomous_adjudications(adjudication_id),
  autonomy_decision_id uuid,
  action_risk_tier text NOT NULL CHECK (action_risk_tier IN ('T0_observe','T1_internal_record','T2_trial_artifact','T3_owned_runtime_change','T4_external_or_irreversible')),
  predicted_confidence numeric NOT NULL CHECK (predicted_confidence >= 0 AND predicted_confidence <= 1),
  confidence_components jsonb NOT NULL DEFAULT '{}',
  selected_action text NOT NULL,
  outcome_status text NOT NULL CHECK (outcome_status IN ('pending','success','failure','mixed','unknown','revoked')),
  outcome_observed_at timestamptz,
  outcome jsonb NOT NULL DEFAULT '{}',
  false_accept boolean,
  false_reject boolean,
  unnecessary_abstention boolean,
  harm_finding boolean,
  utility_score numeric,
  context_token_delta integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.autonomy_reliability_metrics (
  reliability_metric_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  calibration_family text NOT NULL,
  autonomy_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  executor_profile_id uuid,
  evidence_fidelity text,
  action_risk_tier text,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  sample_count integer NOT NULL DEFAULT 0,
  coverage_rate numeric,
  false_accept_rate numeric,
  false_reject_rate numeric,
  abstention_rate numeric,
  unnecessary_abstention_rate numeric,
  calibration_error numeric,
  brier_like_score numeric,
  canary_failure_rate numeric,
  rollback_rate numeric,
  harm_finding_rate numeric,
  utility_per_context_token numeric,
  reliability_bins jsonb NOT NULL DEFAULT '[]',
  calibration_support text NOT NULL CHECK (calibration_support IN ('none','empirical_low_support','empirical_supported','conformal_supported','stale')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.autonomy_policy_trials (
  autonomy_policy_trial_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  policy_kind text NOT NULL,
  candidate_policy jsonb NOT NULL,
  baseline_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  status text NOT NULL CHECK (status IN ('draft','replay_backtest','shadow_mode','canary_policy','accepted','rejected','rolled_back')),
  replay_result jsonb NOT NULL DEFAULT '{}',
  shadow_result jsonb NOT NULL DEFAULT '{}',
  canary_result jsonb NOT NULL DEFAULT '{}',
  hard_invariant_impact jsonb NOT NULL DEFAULT '{}',
  expected_unblocked_decisions integer NOT NULL DEFAULT 0,
  expected_risk_delta jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  retired_at timestamptz
);

CREATE TABLE autoskill.autonomy_decisions (
  autonomy_decision_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  job_id uuid,
  candidate_id uuid,
  skill_id uuid,
  operation_kind text NOT NULL,
  autonomy_policy_version_id uuid REFERENCES autoskill.autonomy_policy_versions(autonomy_policy_version_id),
  llm_adjudication_ids uuid[] NOT NULL DEFAULT '{}',
  hard_invariants jsonb NOT NULL DEFAULT '{}',
  soft_thresholds jsonb NOT NULL DEFAULT '{}',
  confidence_decomposition jsonb NOT NULL DEFAULT '{}',
  decision_band text NOT NULL CHECK (decision_band IN ('clear_accept','clear_reject','improve_evidence','narrow_scope','canary_only','quarantine','admin_required')),
  action text NOT NULL CHECK (action IN ('auto_accept','auto_reject','collect_more_evidence','run_more_probes','run_re_adjudication','stage_ephemeral_candidate','stage_canary','reduce_scope','quarantine','freeze','rollback','escalate_admin','no_op_reschedule')),
  reason_codes text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.administrative_escalation_events (
  escalation_event_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  autonomy_decision_id uuid REFERENCES autoskill.autonomy_decisions(autonomy_decision_id),
  adjudication_id uuid REFERENCES autoskill.autonomous_adjudications(adjudication_id),
  escalation_kind text NOT NULL CHECK (escalation_kind IN (
    'policy_forbids_needed_raw_access','raw_reveal_requested','external_owned_root_mutation_requested','irreversible_infrastructure_change_requested','required_infrastructure_unavailable','repeated_contradictory_adjudications_after_fallback','predelegated_authority_absent_for_T4_action'
  )),
  evidence_packet_id uuid,
  decision_family text,
  source_fidelity text,
  hard_invariants jsonb NOT NULL DEFAULT '{}',
  attempted_autonomous_alternatives text[] NOT NULL DEFAULT '{}',
  recommended_admin_action text,
  status text NOT NULL CHECK (status IN ('open','resolved','withdrawn','superseded','expired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE autoskill.threshold_deadlock_findings (
  threshold_deadlock_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  policy_kind text NOT NULL,
  stalled_candidate_ids uuid[] NOT NULL DEFAULT '{}',
  stall_reason_codes text[] NOT NULL DEFAULT '{}',
  hard_invariants_passed boolean NOT NULL,
  llm_high_utility_count integer NOT NULL DEFAULT 0,
  recommended_action text NOT NULL CHECK (recommended_action IN ('collect_more_evidence','generate_more_probes','relax_soft_threshold','narrow_scope','increase_canary_budget','reject_cohort','no_action')),
  status text NOT NULL CHECK (status IN ('open','trialing_policy','resolved','rejected','quarantined')),
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE autoskill.intent_interpretations (
  intent_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  session_id text,
  turn_id text,
  source_event_ids uuid[] NOT NULL DEFAULT '{}',
  raw_evidence_record_ids uuid[] NOT NULL DEFAULT '{}',
  declassification_report_id uuid REFERENCES autoskill.declassification_reports(declassification_report_id),
  redacted_user_intent text NOT NULL,
  intent_fingerprint text NOT NULL,
  expected_skill_decision jsonb NOT NULL DEFAULT '{}',
  confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  taint text[] NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('candidate','accepted','rejected','quarantined','revoked')),
  created_at timestamptz NOT NULL DEFAULT now()
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
    'ephemeral_candidate','trial_candidate','validated_candidate','active','canary_active',
    'archived','quarantined','frozen','superseded','revoked','deleted_by_retention'
  )),
  owner text NOT NULL DEFAULT 'skillkernel',
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
    'draft','staged','trial_active','canary_active','active','archived','rejected','rolled_back','quarantined','superseded','revoked'
  )),
  frontmatter jsonb NOT NULL,
  skill_ir jsonb NOT NULL,
  skill_ir_schema_version text NOT NULL DEFAULT 'skillir.v1',
  compiler_version text NOT NULL DEFAULT 'skillkernel-compiler.v1',
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
  compiler_version text NOT NULL DEFAULT 'skillkernel-compiler.v1',
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
  schedule_kind text NOT NULL CHECK (schedule_kind IN ('interval','cron_expr','event','manual')),
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
WHERE embedding_profile_id = '11111111-2222-4333-8444-555555555555' AND embedding_dim = 1536;
```

For very high volume, partition first by time for raw events and jobs, then by object type/status for embeddings if needed. Only use hash partitioning by `skill_id` after query plans show a need.

### 9.5 Control-plane tables

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
  artifact_type text NOT NULL CHECK (artifact_type IN (
    'skill_md','manifest','contract','script','reference','template','schema','static_data','asset','example',
    'test','probe_fixture','adjunct_request','profile_rendering','broker_hint','context_excerpt'
  )),
  loadability_class text NOT NULL CHECK (loadability_class IN (
    'runtime_always_metadata','runtime_on_skill_load','agent_may_read','broker_excerpt_only',
    'script_only','probe_only','operator_only','never_loaded'
  )),
  relative_path text NOT NULL DEFAULT '',
  content_hash text NOT NULL,
  byte_size bigint NOT NULL DEFAULT 0 CHECK (byte_size >= 0),
  context_token_estimate integer NOT NULL DEFAULT 0 CHECK (context_token_estimate >= 0),
  capabilities jsonb NOT NULL DEFAULT '{}',
  artifact_contract jsonb NOT NULL DEFAULT '{}',
  scanner_status text NOT NULL,
  test_status text NOT NULL DEFAULT 'not_applicable',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (skill_version_id, artifact_type, relative_path)
);

CREATE TABLE autoskill.integration_proposals (
  integration_proposal_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  originating_skill_id uuid REFERENCES autoskill.skills(skill_id),
  originating_skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  proposal_kind text NOT NULL CHECK (proposal_kind IN (
    'openclaw_tool','plugin_hook','plugin_service','mcp_server','sidecar_schedule','taskflow_template','persistent_store','capability_policy_change'
  )),
  status text NOT NULL CHECK (status IN ('draft','admin_integration_required','approved','rejected','implemented','superseded')),
  reason text NOT NULL,
  proposed_contract jsonb NOT NULL DEFAULT '{}',
  inert_template_artifact_id uuid REFERENCES autoskill.runtime_artifacts(runtime_artifact_id),
  source_evidence_ids uuid[] NOT NULL DEFAULT '{}',
  scanner_findings jsonb NOT NULL DEFAULT '{}',
  created_by_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE autoskill.skill_state_records (
  skill_state_record_id uuid PRIMARY KEY,
  workspace_id uuid NOT NULL,
  skill_id uuid NOT NULL REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
  state_key text NOT NULL,
  state_kind text NOT NULL CHECK (state_kind IN ('counter','cache','checkpoint','runtime_fact','drift_state','adjunct_state')),
  state_value jsonb NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}',
  taint_state text NOT NULL DEFAULT 'clean',
  retention_class text NOT NULL DEFAULT 'standard',
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, skill_id, state_key)
);
```

These tables do not create per-skill schemas. They preserve global analysis while allowing strict logical ownership and profile-aware evaluation.

---


### 9.6 Transaction, attribution, and revocation tables

These tables make autonomous updates rollback-complete across all derived state, not merely reversible at the file level.

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
  actor text NOT NULL DEFAULT 'skillkernel-sidecar',
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


### 9.7 Topology-operation tables

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
  tool_invocation_count integer NOT NULL DEFAULT 0,
  tool_resource_units numeric NOT NULL DEFAULT 0,
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


### 9.8 Context compiler and token-budget tables

Context management needs durable state because token pressure, ignored loads, false-positive routing, and semantic-loss regressions are lifecycle evidence.

```sql
CREATE TABLE autoskill.context_artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL,
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
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
  skill_id uuid REFERENCES autoskill.skills(skill_id),
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
  skill_id uuid REFERENCES autoskill.skills(skill_id),
  skill_version_id uuid REFERENCES autoskill.skill_versions(skill_version_id),
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
  skill_id uuid REFERENCES autoskill.skills(skill_id),
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


### 9.9 Historical ingestion tables

Historical ingestion state is durable and idempotent. These tables track discovered sources, import runs, source items, redacted chunks, parser errors, and checkpoints.

```sql
CREATE TABLE autoskill.historical_import_runs (
  historical_import_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid,
  requested_by text NOT NULL DEFAULT 'sidecar',
  mode text NOT NULL CHECK (mode IN ('discover','import','incremental','reindex','revoke')),
  source_scope jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled','partial')),
  started_at timestamptz,
  finished_at timestamptz,
  stats jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autoskill.historical_sources (
  historical_source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  agent_id text,
  source_type text NOT NULL CHECK (source_type IN (
    'session_store','raw_transcript','sanitized_session_history','transcript_corpus_export',
    'trajectory_sidecar','trajectory_export','compaction_summary','memory_file','workspace_context_file',
    'background_task_record','task_flow_record','subagent_acp_session_record','lobster_workflow_artifact',
    'plugin_session_extension','queued_turn_injection','active_memory_transcript','diagnostic_event_export',
    'otel_export','openclaw_log_diagnostic','raw_stream_debug_log','channel_media_artifact',
    'transcription_artifact','preprocessed_message_artifact','tool_mcp_capability_inventory',
    'existing_skill','qmd_export','memory_capability_public_artifact','memory_wiki_export','honcho_export','allowlisted_project_doc'
  )),
  source_uri text NOT NULL,
  source_owner text NOT NULL DEFAULT 'openclaw',
  discovered_metadata jsonb NOT NULL DEFAULT '{}',
  risk_class text NOT NULL DEFAULT 'sensitive',
  permission_state text NOT NULL CHECK (permission_state IN ('unknown','allowed','denied','skipped')),
  current_fingerprint text,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, source_type, source_uri)
);

CREATE TABLE autoskill.historical_source_items (
  historical_source_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  historical_source_id uuid NOT NULL REFERENCES autoskill.historical_sources(historical_source_id),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  agent_id text,
  session_id text,
  item_kind text NOT NULL,
  item_key text NOT NULL,
  source_timestamp timestamptz,
  raw_hash text,
  redacted_hash text,
  parser_version text NOT NULL,
  redaction_policy_version text NOT NULL,
  import_state text NOT NULL CHECK (import_state IN (
    'discovered','permission_checked','fingerprinted','parsed','redacted','chunked','normalized','embedded',
    'evidence_extracted','clustered','candidate_linked','imported','skipped_by_policy','missing','empty',
    'unsupported_format','parse_failed','redaction_failed','oversize','secret_blocked','tainted_quarantine',
    'duplicate','stale_superseded','revoked'
  )),
  trust text NOT NULL DEFAULT 'historical',
  taint text[] NOT NULL DEFAULT '{historical}',
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (historical_source_id, item_key, parser_version, redaction_policy_version)
);

CREATE TABLE autoskill.historical_chunks (
  historical_chunk_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  historical_source_item_id uuid NOT NULL REFERENCES autoskill.historical_source_items(historical_source_item_id),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  agent_id text,
  session_id text,
  chunk_kind text NOT NULL,
  range_metadata jsonb NOT NULL DEFAULT '{}',
  redacted_text text NOT NULL,
  dense_retrieval_text text NOT NULL,
  structured_metadata jsonb NOT NULL DEFAULT '{}',
  redacted_hash text NOT NULL,
  chunking_policy_version text NOT NULL,
  trust text NOT NULL DEFAULT 'historical',
  taint text[] NOT NULL DEFAULT '{historical}',
  source_timestamp timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, historical_source_item_id, redacted_hash, chunking_policy_version)
);

CREATE TABLE autoskill.historical_import_checkpoints (
  historical_import_checkpoint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id uuid NOT NULL REFERENCES autoskill.workspaces(workspace_id),
  historical_source_id uuid REFERENCES autoskill.historical_sources(historical_source_id),
  checkpoint_key text NOT NULL,
  checkpoint_value jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, checkpoint_key)
);

CREATE TABLE autoskill.historical_import_findings (
  historical_import_finding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  historical_import_run_id uuid REFERENCES autoskill.historical_import_runs(historical_import_run_id),
  historical_source_id uuid REFERENCES autoskill.historical_sources(historical_source_id),
  historical_source_item_id uuid REFERENCES autoskill.historical_source_items(historical_source_item_id),
  severity text NOT NULL CHECK (severity IN ('info','warning','error','critical')),
  finding_type text NOT NULL,
  message text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Required indexes:

```sql
CREATE INDEX historical_sources_workspace_type_idx
  ON autoskill.historical_sources(workspace_id, source_type, last_seen_at DESC);

CREATE INDEX historical_items_state_idx
  ON autoskill.historical_source_items(workspace_id, import_state, updated_at DESC);

CREATE INDEX historical_items_session_idx
  ON autoskill.historical_source_items(workspace_id, agent_id, session_id, source_timestamp DESC);

CREATE INDEX historical_chunks_text_idx
  ON autoskill.historical_chunks USING gin (to_tsvector('english', dense_retrieval_text));

CREATE INDEX historical_chunks_taint_idx
  ON autoskill.historical_chunks USING gin (taint);
```

Historical chunks can receive embeddings through the existing `autoskill.embeddings` table using `object_type='historical_chunk'`. Evidence rows derived from historical chunks link back through provenance edges and retain historical taint unless declassified by policy.

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
- duplicate detection near threshold.

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
  "rendered_hint": "Use pdf-table-repair only when a PDF table extraction failed or table layout evidence is needed; verify row/column integrity before returning results.",
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

Description format example:

```text
Repair PDF table extraction failures; use when row/column alignment, OCR uncertainty, or scanned-table layout affects tabular data; not for narrative PDF summaries.
```

Runtime hint example:

```text
SkillKernel routing hint:
- Use pdf-table-repair when table extraction failed or visible row/column structure is uncertain.
- Verify row count, column alignment, headers, and explicitly marked uncertain cells.
- Do not use generic-pdf-summary when the task requires structured table output.
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
| `operator_only` | Audit/debug/admin diagnostic notes. | Never loaded into agent context. |
| `never_loaded` | Raw evidence, examples, transcripts, logs. | Stored in Postgres; not placed in skill directory unless needed for offline evaluation. |

Default policy: generated skill directories should contain only `SKILL.md`, `.autoskill-manifest.json`, optional `.autoskill-contract.json`, and the minimal verified support files that are actually used: scripts, references, templates, schemas, small immutable data, assets, examples, tests, probes, or inert adjunct requests. No README, changelog, rationale, history, raw transcript excerpts, duplicated notes, mutable local database, or generated runtime registration file should exist inside a skill directory unless the artifact planner and context compiler classify it as operationally necessary and safe.

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
compression_ratio_from_preceding
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
This skill is designed to help the agent work with PDFs. It is important to first understand the background before beginning the task.
```

### 11.17 Support-file progressive disclosure policy

Support files are permitted only when they reduce net context cost, improve reliability, enable deterministic execution, preserve a precise structured contract, or provide a reusable artifact that would be wasteful inside `SKILL.md`. The compiler must decide whether a detail belongs in:

```text
SKILL.md compact body
broker hint
support reference file
support script
support template
support asset
support example
structured schema/data file
Postgres-only evidence
probe fixture outside the active skill root
operator-only audit record
integration proposal for plugin/tool/hook/scheduler work
```

Rules:

1. If the agent always needs it, compress it into `SKILL.md`.
2. If the agent rarely needs it but can decide when to read it, place a terse reference in `SKILL.md` and classify the file as `agent_may_read`.
3. If deterministic execution reduces tokens, errors, or brittle command reconstruction, generate a `scripts/` helper with an explicit interpreter, minimal dependencies, tests, and no undeclared network/secret/file authority.
4. If a precise output/input contract is needed, generate a compact JSON/YAML schema under `schemas/` or a reusable skeleton under `templates/` and refer to it from `VERIFY` or `TOOL TEMPLATES`; do not expand the full schema into `SKILL.md` unless it is short and always required.
5. If a reusable output form is needed, generate `templates/`; if a static reusable resource is needed, generate `assets/`; if a minimal worked case materially improves execution, generate `examples/`.
6. If the agent should not inspect a file directly, classify it as `broker_excerpt_only`, `script_only`, `probe_only`, `operator_only`, or `never_loaded`.
7. If it is rationale, history, raw evidence, improvement notes, large logs, private memory, or low-trust historical material, keep it in Postgres.
8. If it is long and partially useful, split into anchored sections with compact headings so the agent can read only the relevant part.
9. If the desired artifact would be an OpenClaw hook, OpenClaw Cron routine, tool, plugin service, MCP server, or persistent local database, do not place live infrastructure inside the skill folder. Create an administrative integration request and keep any skill-local file as an inert template/reference only.
10. No support artifact may be loaded into context, executed, or used by the broker unless it is manifest-bound, scanner-approved, and covered by the artifact decision record for the active skill version.


---

## 12. Evidence and memory pipeline

### 12.1 Raw events and raw evidence are immutable

Raw events are append-only redacted or minimized event envelopes. They are the normal analytics, indexing, evidence, and audit substrate. Derived records point back to raw event IDs.

Full-fidelity prompts, model messages, tool inputs/results, transcript windows, trajectory windows, memory/context file excerpts, and diagnostic raw streams are not stored in ordinary `raw_events.payload`. When retention policy permits full-fidelity capture, they are stored as encrypted `raw_evidence_records` with explicit retention, sensitivity, taint, source hash, access policy, and audit logging. `raw_events` may hold a pointer to the raw vault record plus redacted/minimized payload fields.

No job can mutate raw event payloads or raw evidence records except retention, revocation, or deletion jobs governed by policy. Deletion and revocation require audit entries and derived-data traversal.

### 12.1.1 Evidence-fidelity tiers

Evidence fidelity is part of the autonomy contract. The importer and live capture path must tag every source and derived object with the highest available fidelity level and the operations it can support. A lower-fidelity source can still contribute to recurrence, clustering, deduplication, and weak priors, but it cannot silently stand in for preserved semantics.

| Fidelity tier | Stored content | Appropriate uses | Inappropriate uses |
|---|---|---|---|
| `raw_vault_linked` | encrypted raw or minimally masked prompt/message/tool/context window with provenance | intent reconstruction, replay intent synthesis, semantic compression checks, memory declassification, topology adjudication | direct runtime context injection, ordinary analytics exposure, embedding secrets |
| `declassified_summary` | redacted semantic derivative with source links and declassification report | replay episodes, evidence packets, skill plans, memory candidates, probes | raw reveal, secret/private fact propagation |
| `redacted_derivative` | redacted turn/tool/context summary with enough operational meaning for some decisions | clustering, candidate evidence, low/medium-risk adjudication, bootstrap mining | high-risk activation without corroboration |
| `metadata_only` | timestamps, source IDs, status, model/tool/skill IDs, counters, result codes | correlation, health, recurrence, performance, routing statistics | user-intent reconstruction, redacted replay intent synthesis |
| `hash_only` | hashes/fingerprints without content | idempotency, deduplication, privacy-preserving joins | semantic decisions, replay promotion, memory declassification, topology choice |

Full-autonomy deployments should target `raw_vault_linked` for user prompts, assistant turns, relevant model inputs/outputs, and tool-result windows that materially affect skill decisions. Deployments that disable raw capture remain supported, but they operate in degraded evidence-fidelity mode and must expect more no-op, low-confidence, or administrative-escalation outcomes. A deployment cannot claim full autonomous skill management for a decision family unless that family has enough semantic evidence for calibrated LLM adjudication.

### 12.1.2 Raw-evidence vault policy

The raw-evidence vault exists to preserve original meaning for autonomous reasoning while preventing casual access or uncontrolled reuse.

Rules:

- raw evidence is encrypted at rest and never duplicated into ordinary analytics tables;
- raw evidence carries retention, sensitivity, taint, source, parser, capture-policy, and redaction-policy metadata;
- raw evidence is never embedded directly; embeddings use redacted derivatives or declassified semantic outputs;
- raw evidence is exposed to an LLM only through a declared purpose, minimum necessary source window, configured text profile, exposure-level check, scanner/secret-masker where applicable, and access audit;
- hosted LLM exposure for raw private content is disabled unless the operator explicitly configures that content tier;
- local/self-hosted LLM routes can be required for raw-sensitive adjudication;
- raw access denial produces an ordinary no-op/quarantine/escalation reason rather than silently weakening a decision;
- retention, privacy delete, source revocation, rollback, and quarantine traverse from raw evidence to derived summaries, embeddings, intent records, memories, replay episodes, candidates, probes, SkillIR revisions, compiled artifacts, and broker caches.

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
- calibrated recurrence, severity, explicit-intent, or source-fidelity policy supports promotion, or the candidate is routed to an autonomous fallback such as more evidence, quarantine, probe-only use, or rejection;
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

Quarantined memory is not embedded for runtime retrieval and cannot become skill text. Quarantine release requires provenance checks, scanner pass, and a deterministic transformation into a non-imperative evidence record.

Memory quarantine is not an administrative-escalation default. The sidecar first runs autonomous memory adjudication when enough source evidence exists. The LLM may classify the candidate as safe operational memory, evidence-only, private fact, external instruction, poisoned/imperative content, contradiction, or low-confidence. Deterministic checks then apply scanner findings, trust, recurrence, taint, privacy policy, source provenance, and confidence thresholds. High-confidence safe transformations are accepted automatically; high-confidence unsafe candidates are rejected automatically; low-confidence, contradictory, privacy-sensitive, or policy-forbidden cases remain quarantined or escalate.

### 12.8 Autonomous semantic adjudication pipeline

Autonomous semantic adjudication bridges the gap between collected data and decisions that require intent interpretation. It is used whenever deterministic code cannot reliably infer meaning from structured telemetry alone.

Adjudication tasks include:

```text
intent_reconstruction
replay_episode_promotion
memory_declassification
external_skill_relationship
topology_operation_choice
policy_safe_action
skill_plan_semantic_adjudication
context_equivalence
quarantine_release
freeze_repair_triage
```

Required stages:

```text
candidate source set
→ evidence-fidelity check
→ raw-vault access decision, if needed
→ minimum necessary context-window assembly
→ deterministic secret masking when required
→ LLM structured verdict under schema
→ deterministic schema/provenance/redaction/confidence validation
→ scanner/evaluator/policy checks
→ auto_accept | auto_reject | quarantine | escalate_admin | no_op_reschedule
→ audit + provenance edges + derived-data links
```

The LLM is allowed to make the semantic verdict. Deterministic infrastructure decides whether that verdict is admissible and executable. This distinction preserves autonomy without giving the model unchecked agency over files, scheduling, activation, rollback, or policy state.

### 12.8.1 Semantic adjudication is an autonomy enabler

Semantic adjudication exists to remove routine human interpretation from the maintenance loop. If a decision depends on user intent, workflow meaning, redaction semantics, topology relationship, memory meaning, or expected runtime behavior, the normal path is:

```text
assemble enough permitted evidence
→ ask the configured LLM for a structured verdict
→ validate the verdict deterministically
→ take the next autonomous action
```

A missing deterministic threshold alone is not a reason to ask a human. The system must first attempt the non-blocking autonomous exits defined by the Autonomous Decision Orchestrator: gather more evidence, re-run retrieval, use raw-vault context if policy allows, re-adjudicate, generate probes, narrow the scope, create an ephemeral candidate, canary at reduced exposure, reject with reason, or reschedule.

### 12.8.2 Adjudication confidence bands

Each adjudication stores both the LLM verdict and a deterministic confidence decomposition. The decomposition must identify which factors reduced confidence so the system can act autonomously on the bottleneck.

Examples:

| Confidence bottleneck | Autonomous response |
|---|---|
| `insufficient_context_window` | Retrieve a larger permitted transcript/trajectory window. |
| `raw_prompt_missing` | Use available redacted derivatives, historical trajectories, or mark source as degraded without blocking unrelated operations. |
| `redaction_uncertain` | Run redaction-specific adjudication and scanner; if still uncertain, quarantine rather than activate. |
| `topology_ambiguous` | Trial multiple topology alternatives: improve, compose, decompose, no-skill, and broker-only. |
| `probe_margin_low` | Generate more probes and run a canary-only path if hard gates pass. |
| `context_budget_near_limit` | Recompile, decompose, or move content into support files before rejection. |
| `reversibility_high` | Prefer bounded canary over administrative escalation when hard gates pass. |
| `irreversible_or_external` | Escalate only when the action cannot be represented as a reversible SkillKernel-owned change. |

### 12.8.3 Autonomy evidence failure modes

The implementation must explicitly detect evidence modes that would make autonomous reasoning impossible. A decision family is marked `evidence_insufficient_for_autonomy` when the available records contain only hashes, counters, selected skill IDs, or decontextualized metadata for a decision that requires user intent, workflow meaning, redaction semantics, or causal attribution. That state is not treated as a normal review queue. The sidecar must first attempt authorized historical lookup, raw-vault lookup, trajectory lookup, transcript-window reconstruction, related-turn expansion, broker/context-log reconstruction, and LLM adjudication over the richest permitted evidence. Only after those autonomous remedies fail may the decision become `administrative_escalation_required`.

This prevents a privacy implementation from silently degrading into non-autonomy. Privacy policy controls which evidence may be retained, viewed, declassified, embedded, or exposed to a local/hosted model. It must not let a deployment claim full autonomy while storing only correlation artifacts for semantic decision families.

### 12.9 Replay-corpus intent synthesis

Replay and canary corpora require a safe, stable `redacted_user_intent`. The system must synthesize this automatically when evidence permits.

Inputs:

```text
user prompt or transcript window from raw-evidence vault
assistant response and final status
tool calls/results and errors
retrieved/rendered/ignored skills
broker decision and context hints
session/task metadata
user corrections or follow-up turns
historical trajectory records when available
```

Output:

```json
{
  "redacted_user_intent": "Extract the failed PDF table into a CSV and preserve uncertain cells explicitly.",
  "task_family": "pdf_table_extraction",
  "expected_skill_decision": {
    "ideal": "load_skill",
    "skill_slug": "pdf-table-repair",
    "avoid": ["generic-pdf-summary"]
  },
  "sensitive_fields_removed": ["local_path", "customer_name"],
  "confidence": 0.93,
  "requires_administrative_escalation": false,
  "rationale_codes": ["explicit_user_request", "tool_error_context", "skill_retrieval_miss"]
}
```

Acceptance requires:

- source-window provenance;
- redaction/declassification report;
- deterministic secret scan pass;
- contradiction check against surrounding turns;
- confidence satisfies the calibrated replay-promotion policy, or the episode is routed to an autonomous fallback such as more evidence, degraded candidate recording, probe-only use, or rejection;
- no policy-forbidden content exposure;
- replay episode reproducibility using the redacted intent and recorded metadata.

An operator-provided `redacted_user_intent` is an override path, not the normal path. If raw prompts are not available and the LLM cannot reconstruct intent from redacted context, SkillKernel records a degraded candidate and either skips durable replay promotion or routes to `escalate_admin` according to policy.

### 12.10 Administrative escalation boundary

Administrative escalation is reserved for cases where autonomous adjudication and autonomous fallback actions cannot produce a safe, high-confidence, policy-compliant decision. It is not the default implementation path for semantic adjudication, replay-corpus building, memory declassification, external-skill relationship classification, topology operation choice, candidate acceptance, canary activation, or SkillKernel-owned rollback.

Before escalating, the sidecar must attempt the applicable autonomous alternatives:

```text
assemble richer permitted evidence
run re-adjudication with explicit uncertainty decomposition
generate more probes
run no-skill/current-skill/candidate counterfactuals
reduce scope
decompose candidate
create ephemeral candidate
run canary-only activation
auto-reject with reason
no-op and reschedule when useful future evidence is likely
```

Escalate only when:

- policy forbids the required raw-content exposure;
- the only adequate context contains secrets or private facts that cannot be masked without losing meaning;
- repeated adjudications contradict each other after more-evidence and re-adjudication attempts;
- composite confidence remains below the risk-weighted minimum floor after autonomous fallback attempts;
- source provenance is missing or revoked and the decision would create durable runtime influence;
- the action would mutate a non-SkillKernel-owned root or external system;
- the action would create a new capability surface outside preapproved adjunct templates;
- deterministic scanner/evaluator/rollback infrastructure is unavailable for an action that requires it;
- the deployment mode explicitly requires admin authorization for that action class.

Otherwise, SkillKernel uses LLM adjudication plus deterministic admissibility checks to continue autonomously.

### 12.11 Control-flow integrity logging

Whenever memory, skills, broker policy, or external-skill inventory materially influences retrieval, mutation, tool selection, archive, promotion, or rollback, SkillKernel writes a `control_flow_events` row. This supports audits and poisoning detection.

---


## 13. Rich data contract for autonomous topology operations

The success of SkillKernel depends on two coupled systems:

```text
A. collect rich, trustworthy, operation-relevant evidence
B. use that evidence to choose the correct autonomous operation
```

If A is weak, the system will make plausible but wrong skill changes. If B is weak, the system will store useful data without improving the skill bank. Both are implementation requirements, not optional analytics.

### 13.1 Required per-turn observability

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
| outcome | Needed for utility and attribution. |
| token/tool/time cost | Needed for compose/decompose and curation. |
| executor profile | Skill behavior depends on model/harness/tool/sandbox context. |
| taint/provenance of evidence | Prevents external content from becoming durable instructions. |

### 13.2 Data needed for creation

Creation needs evidence of missing durable procedure:

- repeated manual workflow;
- repeated user instruction or correction;
- repeated tool sequence with stable outcome;
- repeated failure fixed by the same intervention;
- high-cost task with reusable steps;
- archived skill match that is stale, missing, or not active;
- no active skill/component adequately covers the task.

Creation does **not** require co-use of existing skills. It requires a missing capability/workflow whose expected future value exceeds maintenance, context, and risk cost.

### 13.3 Data needed for improvement

Improvement needs evidence tied to a target skill version:

- skill was retrieved/visible/used;
- outcome improved, degraded, or required correction;
- exact failure, omission, or inefficiency is known;
- a reproducible probe can be generated;
- patch can be localized to SkillIR, description, validator, contract, support artifact, or broker boundary;
- regression set exists for current behavior.

A model saying “this could be better” is not evidence. The LLM may propose a patch; deterministic gates decide whether it is accepted.

### 13.4 Data needed for composition

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

### 13.5 Data needed for decomposition

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

### 13.6 Evidence maturity ladder for topology operations

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

### 13.7 Operation-decision loop

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


### 13.8 Data-to-usable-skill bridge

SkillKernel must implement an explicit bridge from collected data to an active, usable skill. Rich evidence is not enough. A candidate becomes a usable skill only after it is converted into SkillIR or SkillGraphIR, compiled into an OpenClaw-compatible skill package, evaluated against target and regression cases, transactionally activated, indexed by the runtime broker, and observed under canary policy.

The bridge is a required sidecar orchestration path. It applies to live capture, historical bootstrap, and incremental historical sync. Historical evidence can accelerate the early stages, but it does not bypass the same gates used for live evidence.

#### 13.8.1 Definition of a usable skill

A SkillKernel-owned skill is usable only when all of the following are true:

- an accepted `skills` record exists with a current active or canary version;
- canonical SkillIR exists for a single-skill node, or SkillGraphIR exists for a composed/decomposed workflow node;
- required clauses are present: use boundary, non-use boundary, inputs, preconditions, procedure, verification, failure handling, and safety constraints;
- all referenced evidence is redacted, provenance-linked, taint-classified, and mature enough for the operation;
- optional ancillary artifacts have an accepted artifact plan and manifest-bound records;
- `SKILL.md` compiles as a valid OpenClaw skill with required frontmatter and compact AI-facing runtime text;
- support files are immutable, hashed, scanned, loadability-classified, and referenced through safe paths such as `{baseDir}` when runtime access is intended;
- scanner, evaluator, regression, shadowing, token-budget, context-bundle, and profile-qualification gates pass;
- a rollback pointer and evolution transaction exist;
- the active package is installed under the SkillKernel active skill root at a safe activation boundary;
- archived/superseded packages are invisible to OpenClaw skill loading;
- broker indexes, embeddings, lexical indexes, topology edges, and runtime-context policy records are updated;
- canary observation is scheduled unless policy explicitly allows immediate production activation;
- every derived object is reachable from the provenance graph for audit and revocation.

Anything short of this state is not an active usable skill. It is an event, evidence record, memory, component, candidate, probe, package draft, canary, rejected candidate, archived version, or quarantine object.

#### 13.8.2 Bridge pipeline

The sidecar implements the bridge as a stateful pipeline with explicit inputs, outputs, gates, and failure exits:

```text
live/historical source records
→ redacted raw events and trace spine
→ evidence windows
→ evidence packets
→ task/workflow clusters
→ active/archive/external-skill matching
→ topology operation decision
→ autonomous LLM semantic adjudication and structured operation plan
→ SkillIR or SkillGraphIR construction
→ artifact planning
→ deterministic validation and taint checks
→ probe and trial generation
→ context compilation
→ package staging
→ scanner/evaluator/regression/shadowing gates
→ evolution transaction
→ atomic activation or quarantine
→ broker/index registration
→ canary observation
→ production verification, repair, rollback, freeze, archive, or promotion
```

The implementation should expose this bridge as a named workflow in job records and Observatory views. A developer should be able to inspect one candidate and see every stage from source records to final activation or rejection.

#### 13.8.3 Stage contract

| Stage | Input | Output | Authority | Failure exit |
|---|---|---|---|---|
| Source normalization | plugin events, transcripts, trajectories, memory/context files, tasks, existing skills | redacted raw events, trace links, source confidence | deterministic parser/redactor | rejected source item, parser finding |
| Evidence extraction | raw events and trace spans | typed evidence records and memory candidates | deterministic extraction plus bounded LLM classification when needed | evidence quarantine, memory quarantine |
| Evidence windowing | evidence records | evidence packet with task fingerprint, recurrence, outcome, tools, skills, costs, taint, provenance | deterministic clustering/retrieval | insufficient evidence, no-op |
| Skill matching | evidence packet | active/archive/external/component match set | hybrid lexical/vector/metadata/graph retrieval with exact rerank | duplicate, promote archived, improve existing |
| Operation decision | evidence packet and match set | create/improve/compose/decompose/no-op/supporting-action decision | calibrated autonomous decision orchestrator using deterministic policy, retrieval evidence, and LLM semantic adjudication when meaning, intent, or topology is not mechanically decidable | no-op, memory-only, probe-only, ephemeral candidate, more evidence |
| Semantic induction | high-signal candidate | structured operation plan, semantic verdict, confidence decomposition, uncertainty notes, and evidence IDs | LLM semantic adjudication plus deterministic schema/provenance/admissibility checks | schema reject, unsupported claim, re-adjudication, more evidence, low-confidence autonomous fallback |
| Canonical modeling | operation plan | SkillIR or SkillGraphIR revision | deterministic normalizer/validator | candidate quarantine |
| Artifact planning | SkillIR/SkillGraphIR | `SKILL.md` plus optional scripts/references/templates/schemas/data/assets/examples/tests/probes/adjunct requests | LLM authors artifact plan; deterministic planner admits allowed artifacts | instruction-only fallback, support artifact rejection |
| Probe generation | evidence packet and SkillIR/SkillGraphIR | target, regression, counterfactual, shadowing, and canary probes | LLM may author probe specs; deterministic evaluator owns execution | probe-only, candidate hold |
| Context compilation | SkillIR/SkillGraphIR and artifact plan | compact AI-facing runtime artifacts | deterministic compiler with LLM-assisted semantic compression | split, decompose, support-file move, keep prior version |
| Package staging | compiled artifacts | staged immutable package plus `.autoskill-manifest.json` | deterministic writer | path-containment reject, scanner reject |
| Evaluation | staged package and probes | trial results and acceptance verdict | deterministic evaluator | reject, repair candidate, freeze target, keep current |
| Activation | accepted transaction | active/canary skill package, updated indexes, broker policy records | deterministic transaction manager | rollback, quarantine, activation defer |
| Observation | canary/live usage | attribution, utility, drift, context, and repair evidence | deterministic logging plus bounded semantic analysis | keep, repair, archive, rollback, freeze |

#### 13.8.4 Evidence packet

The evidence packet is the handoff object between collection and skill design. It is the minimum unit that can produce a topology-operation candidate. It must include:

```json
{
  "evidence_packet_id": "evidence-packet:2b1d8f0a-3a7e-4a9d-9c4f-3353db6e5b21",
  "workspace_id": "workspace:0e1a6d5f-5d78-4a8a-8f2e-2b4a6e7c9a10",
  "agent_ids": ["agent:4f2c1e99-6b2f-40cd-a9b2-fdc0e4f71517"],
  "task_fingerprint": "task:pdf-table-repair:v1:7b6a9c",
  "source_window": {
    "kind": "mixed_live_and_historical",
    "first_seen_at": "2026-05-20T18:13:22Z",
    "last_seen_at": "2026-06-04T04:11:03Z"
  },
  "operation_hints": ["create", "improve"],
  "recurrence": {
    "event_count": 9,
    "distinct_sessions": 4,
    "distinct_days": 3
  },
  "outcomes": {
    "successes": 4,
    "failures": 5,
    "user_corrections": 2
  },
  "skill_context": {
    "active_matches": [],
    "archived_matches": [],
    "external_matches": ["external-skill:pdf-summary"],
    "co_used_skills": []
  },
  "procedural_signal": {
    "stable_tool_sequence": true,
    "stable_repair_delta": true,
    "verification_available": true
  },
  "risk": {
    "taint": "redacted_internal",
    "privacy": "low",
    "capability": ["filesystem-read"],
    "source_confidence": 0.86
  },
  "provenance": {
    "raw_event_ids": ["raw-event:1efc9a52-ef49-4039-9d82-f746e0c4df0d"],
    "evidence_ids": ["evidence:4f9a2b1c-1111-4222-8333-abcdefabcdef"],
    "historical_chunk_ids": ["historical-chunk:f08dc358-5c7e-4c56-a9d8-a384a81b8a55"]
  }
}
```

The packet is not prompt text. It is structured control-plane data. LLM prompts are rendered from redacted packet views with evidence IDs preserved.

#### 13.8.5 Semantic adjudication to SkillIR conversion

The LLM issues an autonomous semantic adjudication artifact for the candidate: interpreted user intent, operation choice, structured plan, confidence decomposition, uncertainty notes, redaction/declassification assumptions, and evidence-linked procedural claims. This artifact is the semantic decision input, not executable authority. The deterministic normalizer converts admissible adjudication artifacts into canonical SkillIR or SkillGraphIR by enforcing:

- valid slug/name/description constraints;
- operation class: create, improve, compose, decompose, or supporting action;
- explicit use and non-use boundaries;
- required inputs and preconditions;
- deterministic procedure clauses;
- verification and failure clauses;
- declared capabilities and environment contracts;
- evidence-ID coverage for every procedural claim;
- taint and source-trust compatibility;
- dependency, conflict, supersession, component, and sibling edges;
- artifact plan consistency;
- no unsupported instructions, raw transcript rationale, secrets, or external imperatives.

If a procedural claim cannot be traced to evidence or justified by a safe generalization rule, it does not enter SkillIR. If the missing support can be resolved autonomously, the orchestrator gathers more evidence, retrieves raw-vault context when policy allows, asks for re-adjudication, or narrows the scope. Otherwise the claim remains a candidate note, is rejected, or is quarantined according to policy.

#### 13.8.6 Data-to-skill path by operation

| Operation | Data signal | Canonical object | Package result | Activation proof |
|---|---|---|---|---|
| create | missing reusable procedure with recurrence, correction, failure repair, or explicit user request | new SkillIR node | new skill package | target probes beat no-skill and nearest active/archive alternatives without regression |
| improve | attributed failure, omission, drift, context waste, or user correction tied to a skill version | new SkillIR revision | replacement package version | patched version beats current version and preserves prior passes |
| compose | repeated co-use/sequence across smaller skills with measurable workflow overhead | SkillGraphIR orchestration node plus component edges | composed workflow package, usually leaving components intact | composed package beats component-only baseline and does not shadow components incorrectly |
| decompose | broad/clunky skill with separable usage clusters, false-positive loads, token waste, or independent drift | successor SkillIR nodes plus supersession/decomposition edges | smaller skill packages and archived/superseded original | successor set beats original and broker can select the right subset |

The bridge must never default to create when improve, promote, compose, decompose, merge, description tightening, broker suppression, memory-only storage, probe addition, or no-op is more appropriate.

#### 13.8.7 Artifact planner decision rules

The bridge produces an artifact plan after SkillIR/SkillGraphIR exists. Instruction-only skills are the default. Ancillary files are included only when they improve execution, verification, context economy, or safety.

Use optional artifacts as follows:

| Artifact class | Include when | Do not include when |
|---|---|---|
| `scripts/` | brittle deterministic transformation, parsing, validation, formatting, or repeated file operation is safer in code | the task requires judgment, external authority, or broad filesystem/network access |
| `schemas/` | output/input contract needs machine validation | schema is speculative or too task-specific to reuse |
| `templates/` | repeated exact output structure reduces model ambiguity | free-form output is acceptable |
| `references/` | compact static reference prevents long prompt text | reference would be loaded every time or can stay in Postgres |
| `data/` | small immutable lookup is needed at runtime | data is mutable, sensitive, large, or better indexed in Postgres |
| `assets/` | static example/image/resource is required for deterministic execution or tests | asset is decorative, large, or private |
| `examples/` | minimal example materially improves execution in probes | example is explanatory prose or token-expensive |
| `tests/` / `probes/` | package-local self-check is useful and small | full regression bank belongs in SkillKernel-managed `.autoskill/` storage |
| `adjunct_requests/` | skill would benefit from a scheduler/tool/hook/template outside skill authority | request would silently create active infrastructure |

The artifact planner is part of the bridge. A candidate is not ready for compilation until the artifact plan is allowed, minimized, and tied to capability declarations.

#### 13.8.8 Evaluation bridge

Evaluation must prove not only that the skill text exists, but that it changes behavior in the intended direction.

For every candidate, generate an evaluation bundle containing:

- positive target probes derived from failures, corrections, or recurring successful workflows;
- negative boundary probes for tasks where the skill must not activate;
- nearest-active-skill and nearest-archived-skill comparisons;
- no-skill baseline when feasible;
- regression probes from prior passes and sibling skills;
- context-pressure measurements;
- shadowing tests against broad and narrow related skills;
- support-artifact tests for scripts, schemas, templates, and deterministic validators;
- executor-profile compatibility checks;
- canary observation plan.

A candidate with good-looking text but no measurable evaluation advantage remains inactive.

#### 13.8.9 Activation bridge

Activation is a controlled state transition, not a file copy. The activation transaction must:

1. lock the target skill, topology edges, candidate, and active package pointer;
2. verify scanner, evaluator, compiler, manifest, and rollback records are current;
3. write or atomically swap the staged package into the active SkillKernel skill root only at a safe session boundary or maintenance window;
4. update `skills`, `skill_versions`, `runtime_artifacts`, `embeddings`, topology edges, broker records, and audit records;
5. ensure archived/superseded versions are outside OpenClaw-visible skill roots;
6. schedule canary and post-activation observation jobs;
7. emit Observatory trace events for every updated object;
8. release locks only after the rollback pointer is valid.

The activation bridge must be idempotent. A retry cannot create duplicate active packages, duplicate embeddings, duplicate topology edges, or orphan archive records.

#### 13.8.10 Required implementation object: data-to-skill trace

Every operation candidate and every active SkillKernel-owned skill must expose a data-to-skill trace:

```text
source item
→ raw event or historical chunk
→ evidence record
→ evidence packet
→ candidate
→ operation plan
→ SkillIR/SkillGraphIR revision
→ artifact plan
→ compiled artifact
→ staged package
→ evaluation result
→ evolution transaction
→ active/canary package
→ broker decision records
→ canary/production observations
```

This trace is part of the product, not an observability extra. It is required for debugging, trust, revocation, rollback, red-team analysis, and explaining why a generated skill exists.

#### 13.8.11 Non-skill exits

The bridge must be allowed to stop before skill creation. Valid non-skill outcomes include:

- `no_op`: evidence is insufficient or not reusable;
- `memory_only`: useful fact or preference, but not procedural skill;
- `probe_only`: failure needs future detection, not a runtime skill;
- `description_tighten`: existing skill only needs routing boundary improvement;
- `broker_policy_update`: skill exists, but runtime selection is wrong;
- `archive_or_promote`: lifecycle state change is better than new skill;
- `merge_candidate`: duplicate skills exist;
- `ephemeral_candidate`: temporary hint can be tried without active package mutation;
- `quarantine`: evidence, plan, artifact, or memory is unsafe;
- `administrative_escalation_required`: policy, confidence, provenance, privacy, or reversibility prevents autonomous adjudication after autonomous fallbacks are exhausted.

This prevents SkillKernel from converting all collected data into skill text. The correct output is the smallest safe control-plane change that improves future behavior.

#### 13.8.12 Development acceptance criteria for the bridge

The bridge is implemented only when all are true:

- a seeded set of raw events can produce an evidence packet with provenance and taint;
- a seeded missing-workflow packet can produce a create candidate, SkillIR, artifact plan, compiled `SKILL.md`, staged package, evaluator result, and inactive/inactive planning record;
- a seeded skill-failure packet can produce an improvement candidate against the correct skill version;
- a seeded co-use packet can produce a compose candidate with component edges and component-vs-composed trials;
- a seeded broad-skill packet can produce a decompose candidate with successor edges and original-vs-successor trials;
- every bridge stage exposes a status, reason code, input IDs, output IDs, and failure exit;
- rejected candidates remain inspectable and searchable so repeated failed attempts are not regenerated blindly;
- no active usable skill can exist without a complete data-to-skill trace, manifest, rollback pointer, broker registration, and evaluation verdict.


## 14. Historical ingestion and deployment bootstrap

SkillKernel includes a historical ingestion subsystem so established OpenClaw deployments can benefit from months of prior sessions, memory files, trajectory captures, tool failures, user corrections, task records, and existing skill inventories immediately after adoption. Historical ingestion is part of the normal evidence pipeline. It is not a separate shortcut around redaction, provenance, taint, evidence maturity, evaluation, or rollback.

The purpose is to convert previously accumulated deployment experience into usable procedural evidence for the four autonomous topology operations:

```text
historical sources
→ datasource discovery
→ dry-run inventory
→ fingerprinting and idempotency
→ parser selection
→ redaction and tainting
→ chunking and structure extraction
→ source confidence scoring
→ event/evidence normalization
→ embedding and lexical indexing
→ memory/evidence clustering
→ topology candidate generation
→ normal create/improve/compose/decompose gates
```

Historical data accelerates discovery. It does not lower acceptance standards.

### 14.1 Historical datasource catalog

The importer must support these OpenClaw-native source classes. Default discovery resolves the active OpenClaw state directory, OpenClaw home directory, config path, profile-specific state roots, agent directories, configured workspace directories, and session store roots before falling back to documented defaults. `OPENCLAW_HOME`, `OPENCLAW_STATE_DIR`, and `OPENCLAW_CONFIG_PATH` are treated as discovery inputs, not broad read permissions. Documented defaults include agent session stores under `~/.openclaw/agents/<agentId>/sessions/sessions.json`, transcript JSONL files under `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`, workspace memory/context files under each agent workspace, trajectory sidecars beside session files or under `OPENCLAW_TRAJECTORY_DIR`, trajectory exports under `.openclaw/trajectory-exports/`, and transcript-corpus exports under `$OPENCLAW_STATE_DIR/transcripts/YYYY-MM-DD/<session>/`. Operators can override or restrict every root through configuration. The importer must tolerate configured `session.store` overrides, `{agentId}` templated stores, named profiles, remote Gateway hosts, pruned session entries, archived reset/deleted transcripts, topic transcripts, and trajectory sidecars with pointer files.

| Source class | Primary value | Trust posture | Import behavior |
|---|---|---|---|
| Session metadata stores | agent IDs, session IDs, keys, channels, models, token counts, timestamps, labels, active/deleted state | medium | Use for session discovery, workspace/agent scoping, recurrence windows, and idempotency. Do not treat metadata alone as skill evidence. |
| Raw session transcripts | user turns, assistant turns, tool calls/results, compaction summaries, errors, corrections, workflow sequences | sensitive/high-value/low-trust | Parse locally only after source authorization. Store raw content only in the raw-evidence vault when policy permits; store redacted derivatives for ordinary persistence, chunking, and embedding. Preserve turn order, parent/branch structure, compaction markers, truncation markers, and tool-call pairing when present. |
| Transcript corpus exports | imported/live transcript folders, `summary.md`, `metadata.json`, `transcript.jsonl`, meeting or voice-session summaries when present | useful/derived/mixed trust | Import as historical narrative and transcript evidence. Treat summaries as derived/lower-confidence, preserve source metadata and line ranges, and never use summaries alone to activate a skill. |
| Sanitized session-history views | bounded, redacted, stripped recall of session content | safer but incomplete | Prefer for low-risk previews and triage. Do not rely on it for exact tool/outcome reconstruction because tool results may be excluded or stripped. |
| Trajectory sidecars and exports | ordered runtime timeline, prompts, selected prompt-building details, metadata, tools, prompt cache, usage, errors, compiled context, final artifacts | high-value/sensitive | Use when available for executor profiles, skill visibility, broker replay, action attribution, tool failures, usage/token metadata, and regression probes. Redact paths/secrets and respect trajectory truncation flags. |
| Compaction summaries | semantic summaries of older turns preserved inside transcripts | useful but lossy | Import as derived summary evidence with lower confidence than raw turns. Use to locate candidate windows, not as sole source for active skill creation. |
| Workspace memory files | durable facts, preferences, decisions, daily notes, dreams/backfill summaries | curated but poisoning-prone | Import as memory-context evidence, not direct runtime instructions. Separate user-specific facts from reusable procedural patterns. Taint imperative language and stale instructions. |
| Workspace context files | AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md, USER.md, HEARTBEAT.md, BOOTSTRAP.md, BOOT.md if present | policy/context and high-sensitivity guidance surface, not skill evidence by itself | Use to understand agent role, tool conventions, security boundaries, startup rituals, and workspace constraints. Scan for guidance injection, risky operational narratives, hidden approval changes, and persistent behavior steering. Never compile persona, user facts, bootstrap guidance, or workspace-specific policy text directly into general skills. |
| Background task ledger | detached work, subagent spawns, ACP runs, isolated automation executions, CLI operations, task status | medium/high-value | Link tasks to sessions and outcomes. Mine recurring delegated workflows and detached failure modes. Do not treat tasks as scheduler state. |
| Task Flow and workflow records | durable multi-step flow state, mirrored task flows, revision state, child-task relationships | medium/high-value | Import only OpenClaw-exposed records or configured exports. Use for composition/decomposition evidence and workflow topology; do not adopt external scheduler semantics. |
| Lobster/workflow artifacts | deterministic multi-step tool sequences, approval checkpoints, resume tokens, workflow YAML/JSON | optional/high-value | Import from allowlisted workspace/project paths only. Treat as project-specific procedural evidence and possible verifier/probe source. |
| Plugin session-extension state and queued next-turn injections | plugin-owned per-session state, pending context continuations, workflow status, hidden runtime hints | mixed/high-risk | Import SkillKernel-owned state fully. For non-SkillKernel plugins, import only allowlisted bounded metadata unless the operator explicitly allows parsing. Never treat opaque plugin state as trusted skill text. |
| Active-memory persisted transcripts and recall summaries | memory-recall subagent traces, recalled facts, hidden memory context, recall failures | optional/sensitive | Import only when explicitly persisted/configured. Treat as derived memory evidence with high taint; useful for memory-skill attribution and memory-poisoning audits, not direct skill compilation. |
| Diagnostic/OpenTelemetry exports | content-safe spans/metrics/logs for model runs, message flow, sessions, queues, exec, skill usage, context assembly, and tool loops | optional/low-content | Import only configured exports. Use for correlation, performance, context pressure, and outcome timing; never expect raw prompt/tool content. |
| Channel media, transcription, and preprocessing artifacts | audio transcriptions, media metadata, enriched `bodyForAgent`, link/media preprocessing outputs, attachment pointers | optional/sensitive | Import only configured artifacts and MIME/path allowlists. Default to metadata/transcript text after redaction; do not ingest raw media bytes unless explicitly enabled. |
| Subagent and ACP child-session records | parent session key, child session key, child transcript path, delegated task, runtime kind, resolved model/provider, completion state, stream-log path when present | medium/high-value | Link parent/child workflows, mine recurring delegation patterns, and import child transcripts through the normal transcript parser. Treat child summaries as lower-confidence than child transcript/tool evidence. |
| Tool, MCP, and runtime capability inventories | effective tool policy, tool profiles, sandbox gates, MCP server/tool catalogs, plugin tools, code-mode/tool-search availability | policy/context/drift evidence | Use to build executor profiles, tool environment contracts, drift checks, and skill applicability constraints. Do not treat tool availability as proof that a workflow succeeded. |
| OpenClaw logs and diagnostics bundles | operational errors, provider failures, gateway restarts, memory pressure, stuck-session warnings, redacted support metadata | optional/low-trust/metadata-heavy | Import only explicitly configured log/diagnostic paths. Prefer structured fields over free text, redact again, and use as corroborating operational evidence rather than direct skill content. |
| Raw stream/debug logs | raw assistant stream events or raw OpenAI-compatible chunks captured by explicit debugging flags | explicit-opt-in/highly sensitive | Disabled by default. Import only from allowlisted local paths, redact again, and use for provider/harness debugging or attribution gaps. Never use raw debug logs as direct skill text. |
| Existing skills from all OpenClaw-visible roots | active capability inventory, collision/shadowing, adoption candidates, external ownership | mixed ownership | Hash and index. SkillKernel-owned skills can enter governance. External skills remain read-only unless explicitly imported. |
| QMD/public memory-search artifacts | indexed memory, extra configured paths, transcript indexing, local-first search outputs | optional/externalized | Import only explicit public/exported artifacts or configured paths. Do not depend on QMD internals or scrape opaque indexes. |
| Registered memory-capability public artifacts | memory-plugin exported artifacts, public memory indexes, plugin-declared corpus supplements | optional/exported | Import only through documented public artifact/corpus surfaces or configured exports. Do not reach into another memory plugin's private layout. |
| Memory wiki / active-memory bridge artifacts | provenance-rich syntheses, dashboards, exported recall artifacts | optional/exported | Import only bridge/export artifacts with provenance. Treat as derived memory requiring source links and taint. |
| Honcho or external memory exports | cross-session memory models and summaries | optional/third-party | Import only operator-provided exports. Mark external-memory provenance and avoid direct skill compilation from summaries alone. |
| Project/workspace documentation explicitly allowed by config | recurring project-specific procedures, build/deploy/test conventions, API docs | optional/high-value | Import only from allowlisted paths. Prefer Markdown/text/JSON/YAML. Exclude hidden paths, dependency/build folders, caches, secrets, and generated artifacts. |

Source discovery should prefer the safest authoritative surface available for the deployment. When the Gateway is reachable and operator credentials are configured, use OpenClaw session/task/Gateway surfaces or CLI commands for inventories and sanitized previews. Use raw disk scans for full historical reconstruction, orphan recovery, pruned-store recovery, trajectory sidecar import, and authorized transcript parsing. Disk scans must reject symlink escapes, out-of-root paths, unexpected file types, oversized files, and paths outside configured roots.

The importer discovers all configured OpenClaw agents because each agent can have its own workspace, state directory, auth profiles, and session store. Agent/workspace boundaries are preserved in every row through `workspace_id`, `agent_id`, source identifiers, and provenance edges.

### 14.2 Source discovery and dry-run inventory

Historical ingestion begins with a read-only discovery job. It produces an inventory before importing content.

Discovery records:

```text
agent_id
workspace path
agentDir path
session store path
session count
transcript count
trajectory sidecar count
memory file count
workspace context file count
existing skill count
background task count when available
task-flow/workflow artifact count when configured
plugin session-extension / queued-injection state count when visible
active-memory transcript count when persisted
diagnostic/OTEL export count when configured
channel media/transcription/preprocessing artifact count when configured
estimated bytes
oldest/newest timestamps
known truncation/deletion/orphan indicators
source permission verdict
source risk class
import recommendation
```

The discovery job must not parse sensitive content beyond what is needed to classify the source and compute stable fingerprints. It should support:

```text
all agents
single agent
single workspace
single source kind
source allowlist
source denylist
time window
maximum bytes per run
maximum files per run
preview-only mode
incremental rescan mode
```

Dry-run inventory is required for operator visibility, but the sidecar remains responsible for autonomous job execution once historical ingestion is enabled in configuration.

### 14.3 Import states and idempotency

Every importable object moves through explicit states:

```text
discovered
→ permission_checked
→ fingerprinted
→ parsed
→ redacted
→ chunked
→ normalized
→ embedded
→ evidence_extracted
→ clustered
→ candidate_linked
→ imported
```

Terminal/problem states:

```text
skipped_by_policy
missing
empty
unsupported_format
parse_failed
redaction_failed
oversize
secret_blocked
tainted_quarantine
duplicate
stale_superseded
revoked
```

Idempotency uses multiple fingerprints:

```text
source URI/path fingerprint
agent/workspace/session fingerprint
content hash after raw read
redacted content hash
byte-range or line-range hash
OpenClaw session id / event id / trajectory event id when available
mtime/size as weak prefilter only
import parser version
redaction policy version
chunking policy version
```

`mtime` is never sufficient for identity. Redacted hash and source lineage determine duplicate handling. The importer must be safe to stop, restart, rerun, and run incrementally.

### 14.4 Parsing and normalization rules

Datasource-specific parsers are required. The importer must not flatten everything into unstructured text.

Raw transcript parser:

```text
preserve session id, key, agent id, channel/kind, model, timestamps
preserve turn order and parent/branch relationships when present
classify user, assistant, tool call, tool result, compaction summary, system/runtime metadata
pair tool calls with matching tool results where possible
extract errors, retries, cancellations, refusals, corrections, and explicit user instructions
mark truncation, dropped rows, malformed rows, provider artifacts, and compaction-derived rows
```

Trajectory parser:

```text
preserve ordered runtime timeline
extract prompt-building metadata, visible skill set, compiled context, tool definitions, usage, errors, prompt cache, final artifacts, and executor profile facts when present
link trajectory events to session transcript turns by session id, timestamp, parent id, or best-effort sequence alignment
record truncation and export completeness flags
```

Transcript-corpus parser:

```text
classify summary.md, metadata.json, transcript.jsonl, and imported transcript folders separately
preserve selector, date, source, start/stop timestamps, title, summary path, transcript path, and source metadata
import summary Markdown as derived narrative evidence with lower confidence than raw OpenClaw session JSONL
link corpus transcript entries to agent sessions only when identifiers or operator-provided mapping prove the relationship
```

Operational log/diagnostic parser:

```text
parse only configured structured logs, diagnostic bundles, and stability summaries
extract provider failures, repeated tool/system errors, gateway restarts, stuck sessions, memory pressure, and session-file growth signals
never compile log prose into skill text
use logs as corroboration for drift, failure, and executor-profile evidence
```

Memory parser:

```text
classify MEMORY.md, memory/YYYY-MM-DD.md, slugged daily notes, DREAMS.md, wiki exports, active-memory artifacts, and external memory exports separately
extract durable decisions, preferences, tool conventions, recurring workflows, open loops, and failure notes
mark user-specific facts, persona/boundary rules, external imperatives, stale commitments, and unverified claims
never compile memory text into skill text without evidence corroboration and declassification
```

Workspace-context parser:

```text
classify AGENTS.md/SOUL.md/TOOLS.md/IDENTITY.md/USER.md/HEARTBEAT.md/BOOTSTRAP.md/BOOT.md by role
extract agent boundaries, tool conventions, workspace-specific constraints, and known recurring instructions
mark persona and user-profile material as non-skill unless a reusable procedural pattern is separately evidenced
```

Plugin/session-state parser:

```text
classify SkillKernel-owned session extensions, non-SkillKernel plugin extension state, queued next-turn injections, and plugin-owned workflow state separately
import SkillKernel-owned state as control-plane evidence
import non-SkillKernel plugin state only when bounded, non-secret, and allowlisted; otherwise record existence, owner plugin, timestamps, and size only
mark pending or delivered context injections as potential causal factors for action/outcome attribution
never treat opaque third-party plugin JSON as trusted instruction text
```

Active-memory parser:

```text
classify persisted active-memory subagent transcripts, recall summaries, tool calls, recalled memory snippets, NONE/no-hit outcomes, and timeout/failure cases
link recall summaries to the parent session turn when identifiers or timestamps support it
mark recalled content as memory-derived and poisoning-prone
use active-memory evidence for memory attribution, missing-skill detection, and retrieval-quality analysis; do not compile recalled memory directly into skills
```

Task/workflow parser:

```text
classify background tasks, subagent tasks, ACP runs, CLI-initiated runs, task-flow records, mirrored flows, managed flows, and Lobster/workflow artifacts separately
extract goal, steps, child tasks, status, revisions, waits, approvals, errors, completion routing, and linked session keys
use recurring task/flow patterns as composition/decomposition evidence and probe seeds
never treat task ledgers as scheduling authority for SkillKernel
```

Message/media parser:

```text
classify transcribed audio, preprocessed bodyForAgent content, link summaries, media metadata, attachment pointers, MIME type, size, and generated media outputs separately
import raw media bytes only when explicitly enabled by operator allowlist and size/MIME policy
prefer transcription/preprocessed text after redaction for skill evidence
mark media-derived evidence with source modality and confidence
```

Diagnostic/observability parser:

```text
classify OpenClaw diagnostic exports, OTEL traces, metrics, logs, raw stream debug logs, QA summaries, and stability reports separately
extract run spans, model-call spans, context assembly spans, tool execution spans, exec events, queue pressure, memory pressure, skill-usage counters, duration, and error class
keep diagnostic content attributes content-safe; raw stream logs are disabled by default and treated as raw transcript risk when explicitly imported
use diagnostics for correlation, drift, context pressure, performance, and action attribution rather than direct skill text
```

Existing-skill parser:

```text
inventory OpenClaw-visible SkillKernel and non-SkillKernel skills
parse SKILL.md frontmatter and body
hash body and support files
classify ownership, capability scope, loadability, context cost, shadowing risk, and import eligibility
never mutate external skills autonomously
```

### 14.5 Redaction, taint, and privacy rules

Historical data is more sensitive than live typed telemetry because it may contain unbounded raw conversation, local paths, tool results, credentials, user facts, private project content, and old prompt-injection payloads. The importer must apply the same or stronger controls as live capture.

Hard rules:

```text
store raw historical content only in the governed raw-evidence vault when policy permits
store redacted derivatives in ordinary historical/evidence tables
redact or declassify before embedding
use raw content for LLM analysis only through the raw-vault access policy and minimum-necessary context windows
redact before ordinary logs
record source lineage before redaction while keeping sensitive payloads in the vault
store raw hashes in ordinary records; store raw sensitive payloads only in encrypted vault records
classify private user facts separately from reusable procedure
quarantine imperative external instructions
quarantine memory that tries to alter policy, identity, routing, tools, credentials, or future behavior
never convert historical text directly into runtime instructions
never treat old user intent as current user intent
```

Taint labels include:

```text
raw_transcript
historical
compaction_summary
tool_result
external_instruction
user_private_fact
credential_like
path_sensitive
policy_sensitive
prompt_injection_suspected
memory_poisoning_suspected
stale_environment
third_party_skill
external_memory_export
```

Historical evidence can mature, but taint does not disappear automatically. Declassification requires a transformation record and verifier/scanner gate.

### 14.6 Chunking, indexing, and retrieval preparation

Historical import uses structure-preserving chunking. Chunk boundaries should align to semantic and operational units:

```text
session turn
tool call + result pair
error + recovery sequence
user correction + assistant repair
compaction summary segment
memory bullet/section
workspace-context section
trajectory event group
skill section/component
```

Each chunk stores:

```text
source_id
source_item_id
agent_id
workspace_id
session_id when applicable
turn/event range
source byte/line range when safe
parser version
redaction version
chunking version
redacted hash
taint
trust
source timestamp
summary text
dense retrieval text
structured metadata
```

Embedding jobs operate only on redacted dense retrieval text. Lexical search vectors use redacted text plus typed metadata. Long documents may produce summary-augmented chunks, but summaries remain linked to exact source ranges and lower-confidence than direct evidence.

### 14.7 Historical evidence scoring

Historical evidence receives lower default confidence than live SkillKernel-captured typed evidence unless it contains strong corroborating signals.

Confidence increases when:

```text
same workflow recurs across sessions or agents
user explicitly corrected or confirmed the procedure
trajectory data links tool/action/outcome to the text
same pattern appears in memory and transcript evidence
same task has success/failure contrast
same operation appears under multiple executor profiles
existing skill inventory shows a gap or repeated shadowing
```

Confidence decreases when:

```text
source is only a compaction summary
source is old and environment contracts are stale
source contains user-private facts rather than procedure
source was imported from external memory summary only
source contains prompt-injection-like or policy-changing language
source is truncated, malformed, orphaned, or missing tool results
source conflicts with current workspace instructions or current skill contracts
```

Historical evidence can create `observed` and `recurring` candidates quickly. Activation still requires intervention and regression validation.

### 14.8 Bootstrap candidate generation

After a historical import batch completes, the sidecar runs a bootstrap consolidation job:

```text
cluster imported evidence by task fingerprint, tool sequence, correction pattern, error class, workflow goal, and skill overlap
match clusters against active SkillKernel skills, archived SkillKernel skills, external skills, rejected candidates, and existing skill body indexes
produce topology candidates: create, improve, compose, decompose, promote, merge, archive, description repair, no-op
rank candidates by evidence volume, recency, recurrence, severity, utility hint, token impact, evaluator feasibility, and risk
route high-signal candidates through normal LLM planning and deterministic gates
```

Bootstrap candidate generation follows the same operation precedence as live mining:

```text
repair/improve existing SkillKernel skill
→ promote archived SkillKernel skill
→ fix description/disambiguation
→ compose/decompose with strong topology evidence
→ create new skill
→ no-op
```

Historical import must not flood the active bank. Use daily creation limits, active-bank budget, ephemeral candidates, canary activation, and no-skill controls.

### 14.9 Incremental historical sync

Historical ingestion is not only a one-time migration. The sidecar runs low-priority incremental sync for sources that exist outside live plugin capture:

```text
new sessions created before plugin startup
sessions from agents where plugin capture was temporarily unavailable
trajectory sidecars flushed after session completion
memory files updated by OpenClaw features or users outside SkillKernel
workspace context changes that affect skill routing or executor contracts
new external skills added outside SkillKernel
background task records produced by detached operations
```

Incremental sync is bounded and coalesced. It never competes with runtime broker or safety jobs. It records checkpoints per source and respects retention/deletion/revocation traversal.

### 14.10 Deletion, retention, and source revocation

Historical import creates a provenance graph. Deletion or revocation of a historical source propagates through derived objects:

```text
import source
→ source item
→ chunk
→ embedding
→ evidence
→ memory
→ candidate
→ SkillIR revision
→ compiled artifact
→ broker cache
→ probe
→ evaluation
→ topology result
```

Revocation does not rewrite audit history. It tombstones derived objects, removes active runtime exposure, invalidates embeddings and broker caches, and blocks future use of affected evidence unless a retained aggregate is policy-retained and contains no sensitive source material.

### 14.11 Performance and operational limits

Historical import can be large. It must be safe for deployments with many agents and months of history.

Required limits:

```text
max bytes per run
max files per run
max sessions per run
max trajectory bytes per run
max memory bytes per run
max LLM jobs per bootstrap batch
max candidates per cluster kind
max active mutations per day
low-priority backfill worker pool
checkpointed progress
pause/resume/cancel controls
storage growth estimates
partition/rollup readiness
```

The importer should prefer deterministic parsing, classification, fingerprinting, clustering, and lexical/vector indexing before any LLM call. LLM calls are reserved for high-signal clusters after deterministic prefiltering.

### 14.12 Historical ingestion acceptance criteria

Historical ingestion is production-ready only when all are true:

1. all configured agents can be discovered without sharing state across agent boundaries;
2. dry-run inventory reports source counts, byte estimates, risk classes, import eligibility, and skipped reasons;
3. raw transcripts, trajectories, memories, workspace context, task records, and existing skills import through separate parsers;
4. every imported item has source lineage, fingerprint, parser version, redaction version, chunking version, and trust/taint labels;
5. no imported raw content is embedded raw or sent to an LLM outside raw-vault access policy; LLM use of raw historical context requires a minimum-necessary window, exposure check, redaction/secret masking when required, declassification report, and audit;
6. duplicate imports are idempotent across restarts and reruns;
7. compaction summaries are marked as lossy derived evidence;
8. historical memory files cannot directly become runtime skill text;
9. external skills are inventoried and indexed but not autonomously mutated in place; SkillKernel-owned replacements/adapters may be created only through normal policy, scan, evaluation, provenance, and rollback gates;
10. historical candidates enter the same topology operation gates as live candidates;
11. importing history cannot activate a skill without scanner, evaluator, token-budget, regression, and rollback gates;
12. source revocation invalidates derived embeddings, evidence, memories, candidates, compiled artifacts, broker caches, and probes;
13. backfill jobs are low-priority, bounded, resumable, and observable;
14. historical import improves candidate discovery without degrading normal OpenClaw runtime behavior.

## 15. Skill representation

### 15.1 Source of truth: SkillIR, not `SKILL.md`

The internal source of truth is **SkillIR**: a typed, versioned JSON object stored in Postgres. `SKILL.md` is the OpenClaw-facing compiled artifact generated from SkillIR.

This design prevents free-form Markdown from becoming an unstructured control plane. It also enables deterministic validation, diffing, migration, compression, evaluation, rendering, rollback, and platform-specific output generation.

### 15.2 SkillIR v1 shape

SkillIR v1 must contain these fields:

```json
{
  "schema": "skillir.v1",
  "identity": {
    "name": "skillkernel-example",
    "slug": "skillkernel-example",
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
  "support_artifacts": [
    {
      "path": "scripts/extract_tables.py",
      "kind": "script",
      "loadability": "script_only",
      "purpose": "Deterministic table extraction fallback used only after text/layout extraction fails.",
      "referenced_from_skill_md": true,
      "interpreter": "python3",
      "capabilities": ["read_user_file", "write_workspace_file"],
      "requires": {"bins": ["python3"], "env": []},
      "network": false,
      "mutable_state": false,
      "test_command": "python3 scripts/extract_tables.py --self-test",
      "sha256": null
    }
  ],
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
    "compiler_version": "skillkernel-compiler.v1",
    "token_budget": 900
  }
}
```

### 15.3 Compiled OpenClaw `SKILL.md` format

The renderer emits a normal OpenClaw skill directory containing `SKILL.md` and any allowed support files. The `SKILL.md` uses OpenClaw-compatible frontmatter: simple single-line keys, required `name` and `description`, and optional single-line JSON `metadata`. SkillKernel lifecycle metadata, hashes, evidence links, capability declarations, compiler metadata, and rollback pointers live in Postgres and `.autoskill-manifest.json`, not in verbose frontmatter.

```markdown
---
name: pdf-table-repair
description: Repair/extract PDF tables after text/layout extraction fails; not for generic PDF summary.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# pdf-table-repair

## WHEN
Use when a PDF table extraction failed, row/column alignment is suspect, or scanned-table visual inspection is required.

## INPUTS
- `source_pdf_path` or `page_image_path`
- requested table/page/range
- required output format

## PRECONDITIONS
- Source file is user-provided or workspace-local.
- Task asks for table data, not generic PDF summarization.

## DO
1. Inspect extraction failure mode: missing rows, merged cells, column drift, OCR uncertainty, or page-rotation issue.
2. Use the safest available extraction/inspection path; prefer deterministic tools before manual reconstruction.
3. Preserve uncertain cells with explicit uncertainty markers instead of inventing values.

## TOOL TEMPLATES
- Use PDF text extraction for born-digital tables.
- Use page screenshot/visual inspection for scanned or layout-damaged tables.

## VERIFY
- Row count and column count match visible evidence.
- Headers align with cell values.
- Empty cells are marked intentionally.

## FAIL
Stop and report the missing precondition or extraction blocker when the source is unavailable, unreadable, or outside allowed paths.

## DO NOT USE WHEN
- User asks for narrative PDF summary.
- Task involves non-table diagrams or prose-only content.

## NEVER
- Never fabricate missing cell values.
- Never overwrite the source PDF.
```

### 15.4 Skill package layout and optional support artifacts

A SkillKernel-generated skill is a normal OpenClaw skill directory with `SKILL.md` at the root. The directory may contain optional support artifacts when the artifact planner proves they improve correctness, reduce context, reduce repeated tool errors, encode brittle syntax, provide reusable templates, preserve formal contracts, or make verification deterministic. Instruction-only skills remain the default. Support artifacts are compiled artifacts with manifests, hashes, capability declarations, scanner results, tests or validators where applicable, and rollback links.

OpenClaw-compatible facts the compiler must honor:

- the root artifact is a directory containing `SKILL.md`;
- `SKILL.md` frontmatter requires `name` and `description`;
- OpenClaw frontmatter supports simple single-line keys, with `metadata` as single-line JSON;
- OpenClaw-specific gating belongs under `metadata.openclaw`;
- `{baseDir}` is the portable way for `SKILL.md` to reference files inside the skill directory;
- optional support files are files the agent may read or scripts the agent may execute only when existing OpenClaw tools, sandbox policy, and agent permissions allow it;
- `command-dispatch: tool` can reference only an already registered and allowlisted OpenClaw tool. A generated skill cannot create a new tool by adding files to its directory.

Allowed active skill layout:

```text
<workspace>/skills/autoskill/<slug>/
  SKILL.md                         required; compact AI-facing runtime interface
  .autoskill-manifest.json          required; hashes, SkillIR revision, gates, rollback pointer
  .autoskill-contract.json          optional; machine contract, not prompt text
  scripts/<safe-name>.py            optional deterministic helper/verifier/adapter
  scripts/<safe-name>.sh            optional thin shell wrapper; no unbounded shell synthesis
  references/<safe-name>.md         optional on-demand compressed reference material
  templates/<safe-name>.md          optional output/file/template skeleton
  templates/<safe-name>.txt         optional plain template text
  templates/<safe-name>.json        optional structured template
  schemas/<safe-name>.json          optional JSON Schema/OpenAPI/contract fragment
  schemas/<safe-name>.yaml          optional YAML schema/config contract
  data/<safe-name>.json             optional small immutable lookup table/config map
  data/<safe-name>.csv              optional small immutable tabular lookup data
  data/<safe-name>.yaml             optional small immutable structured data
  assets/<safe-name>.<allowed-ext>  optional static resource/template asset
  examples/<safe-name>.md           optional minimal example/counterexample
  tests/test_<safe-name>.py         optional small immutable package self-test for scripts/high-risk logic
  probes/<safe-name>.jsonl          optional small immutable evaluator fixture; main probe bank stays outside active root
  adjunct_requests/<safe-name>.json optional inert request for scheduler/hook/tool/state adjunct
  .clawhubignore                    optional export/publish ignore rules when operator export is enabled
```

No symlinks, hardlinks, parent traversal, absolute paths, hidden instruction channels, generated binary executables, private keys, credentials, downloaded remote code, dependency lockfile mutation, package-manager install side effects, unbounded shell wrappers, mutable database files, append-only execution logs, or runtime caches are allowed in a SkillKernel-owned active skill directory. Additional file extensions or script interpreters require an operator policy change and a deterministic scanner update, not an LLM decision.

Operational probes, full regression fixtures, generated verifier harnesses, bulky test corpora, trial workspaces, and mutable runtime data normally live outside the active OpenClaw skill root under SkillKernel-managed storage. Active-root `tests/` and `probes/` are limited to small immutable package-local self-tests or fixtures that are needed for artifact validation or agent-visible verification:

```text
<workspace>/.autoskill/probes/<skill-id>/<version>/
<workspace>/.autoskill/runtime-data/<skill-id>/
<workspace>/.autoskill/trial-workspaces/<transaction-id>/
```

Mutable skill state belongs in Postgres or a SkillKernel-managed runtime-data path, not in the active skill package. Active skill packages are immutable during any session that may use them.

#### 15.4.1 Artifact inclusion matrix

The artifact planner chooses the smallest artifact set that satisfies the skill contract. It must compare every support artifact against a no-artifact and `SKILL.md`-only baseline.

| Artifact role | Include when | Do not include when | Required handling |
|---|---|---|---|
| `SKILL.md` | Always. It provides routing and compact runtime instructions. | Never omitted. | frontmatter parse, description budget, semantic-density, scanner, equivalence, regression. |
| `.autoskill-manifest.json` | Always for SkillKernel-owned active packages. | Never omitted. | `operator_only`; not referenced from `SKILL.md`; used for hashes, provenance, gates, loadability, rollback. |
| `.autoskill-contract.json` | A machine-readable contract helps drift checks, tool compatibility, or evaluator binding. | The contract duplicates SkillIR and has no runtime/evaluator value. | `operator_only` or `broker_excerpt_only`; schema validated and hash-bound. |
| `scripts/` | Deterministic code materially reduces token use, repeated errors, brittle command reconstruction, or verification ambiguity. | The logic requires broad reasoning, undeclared secrets, dynamic fetch-exec, uncontrolled network access, or unbounded shell authority. | `script_only`; exact invocation may be referenced from `SKILL.md` via `{baseDir}`; static scan, interpreter allowlist, capability scan, tests, output-size cap. |
| `references/` | Rarely needed detail, API caveats, edge-case matrices, migration notes, or long deterministic rules are useful on demand. | The detail is always needed, private/raw evidence, generic documentation, or human rationale. | `agent_may_read` only for compressed, scanned, anchored files; otherwise `broker_excerpt_only` or `operator_only`. |
| `templates/` | A stable output/input/report/config/file skeleton reduces mistakes or repeated formatting work. | The template is generic, trivial, or larger than its measured benefit. | variable-marker validation, format validation, scanner, explicit variable markers. |
| `schemas/` | Validation, extraction, structured output, API-contract conformance, or drift checks depend on formal structure. | The structure is volatile, inferred from one weak example, or belongs in project source rather than a skill. | schema parser, sample validation, version contract, drift probe. |
| `data/` | A small immutable lookup table, taxonomy, normalization map, or static config is repeatedly needed and expensive to recreate. | The data is large, sensitive, mutable, user-private, stale-prone, or available from a safer authoritative runtime source. | size cap, provenance, hash, staleness contract, no secrets. |
| `assets/` | A static template/resource materially improves execution and is referenced only when needed. | The asset is large, opaque, mutable, private, or unnecessary for the workflow. | MIME/extension allowlist, hash, malware/static scan, excluded from prompt unless explicitly read. |
| `examples/` | Probe data shows the model fails without one minimal example or counterexample. | The example is explanatory, redundant, long, copied from a transcript, or included for human readability. | synthetic/redacted, token budget, semantic-density, regression proof. |
| `tests/` / `probes/` | A helper script, high-risk workflow, composed workflow, or previously regressed behavior needs deterministic validation. | A purely instruction-only low-risk skill has no executable or structured invariant to test. | evaluator-only loadability, deterministic runner, pinned fixtures, pass/fail semantics. |
| `.clawhubignore` | Operator export/publish/sync is enabled and internal artifacts should be excluded. | Normal local-only operation does not require it. | Must not hide files from SkillKernel scanner; only affects external publish/sync surfaces. |
| `adjunct_requests/` | Evidence shows benefit from scheduled evaluation, hook-time observation, a preapproved plugin tool, managed state, or another capability outside normal skill-package authority. | The request would require arbitrary new runtime code, OpenClaw Cron-based execution, unmanaged hooks, secret access, or operator-unapproved capabilities. | inert JSON only; sidecar/operator policy decides activation. |

#### 15.4.2 Hooks, schedules, tools, and state are adjuncts

A generated skill directory cannot autonomously activate new OpenClaw hooks, OpenClaw Cron routines, MCP servers, model providers, plugin tools, background services, or persistent databases. Skills are instruction/resource packages. Plugins, hooks, tools, providers, MCP servers, and scheduled automation are separate capability surfaces.

SkillKernel may create inert `adjunct_requests/*.json` files and matching Postgres records when evidence shows that a skill would benefit from an adjunct capability. Activation follows these rules:

1. **Hook adjuncts** use only preexisting SkillKernel plugin hook surfaces or preapproved deterministic hook templates. The LLM may identify the need for hook-time capture or a guard condition; it may not write hook handler logic. Non-template hook requests become administrative integration backlog.
2. **Schedule adjuncts** use the sidecar-owned scheduler. They never use OpenClaw Cron. A skill may request “run drift probe daily” or “refresh static-data source weekly,” but the sidecar stores and executes the schedule as a SkillKernel `sidecar_schedule` job linked to `skill_id` and version.
3. **Tool adjuncts** may route through stable, preexisting SkillKernel/OpenClaw tools only. A generated skill may set `command-dispatch: tool` only when the target tool already exists, is allowlisted, and the argument contract is deterministic. Requests for new tools become administrative integration backlog.
4. **Mutable state** lives in `autoskill.skill_state_records` or a configured SkillKernel runtime-data root. The active skill package may include immutable `data/` files, but not SQLite databases, append-only logs, or mutable caches.
5. **Execution outputs** created while using a skill belong in the user workspace or configured runtime-data root, never under the active skill package. Active packages remain read-only for sessions that may use them.

#### 15.4.3 Artifact planning algorithm

For each create, improve, compose, or decompose operation, the artifact planner performs:

```text
load SkillIR / SkillGraphIR
→ identify required operational components
→ classify each component as runtime text, on-demand reference, deterministic script, schema, template, static data, asset, example, test/probe, contract, adjunct request, or Postgres-only evidence
→ compare against no-artifact and SKILL.md-only baselines
→ estimate context savings, failure reduction, maintenance risk, security risk, drift risk, and evaluation value
→ reject artifacts whose marginal value is lower than their token/security/maintenance cost
→ generate structured artifact plans with evidence IDs and capability declarations
→ deterministic writer renders only allowlisted paths
→ scanner, tests, evaluator, and context compiler validate exact bytes
→ activation transaction records hashes, loadability class, and rollback pointer
```

The LLM may author an artifact plan explaining what kind of artifact would help and why. Deterministic infrastructure decides whether the artifact type is allowed, whether the path is legal, whether the content passes scanner/tests, whether the artifact improves evaluation, and whether it can be activated.

#### 15.4.4 Support artifact record

Every support artifact record must include enough information for scanning, routing, rollback, and revocation:

```json
{
  "path": "scripts/extract_tables.py",
  "kind": "script",
  "loadability": "script_only",
  "purpose": "Deterministic fallback for table extraction failures.",
  "referenced_from_skill_md": true,
  "capabilities": ["read_user_file", "write_workspace_file"],
  "requires": {"bins": ["python3"], "env": []},
  "interpreter": "python3",
  "network": false,
  "mutable_state": false,
  "test_command": "python3 scripts/extract_tables.py --self-test",
  "sha256": "4b68ab3847feda7d6c62c1fbcbeebfa35eab7351ed5e78f4ddadea5df64b8015"
}
```

A script or template that accesses secrets must declare the capability by name and rely on OpenClaw/SkillKernel secret-injection policy. Raw secret values never appear in `SKILL.md`, support files, examples, probes, manifests, logs, embeddings, or broker context.

Generated `SKILL.md` text must mention a support file only when the model needs to know it exists. The reference is terse and operational:

```markdown
Use `{baseDir}/scripts/extract_tables.py --input "$PDF" --pages "$PAGES" --out "$OUT"`; then verify row/column counts.
See `{baseDir}/schemas/table-output.schema.json` only when validating output shape.
```

The compiler rejects support artifacts when they increase attack surface or token surface without measured benefit. A support artifact can be split, moved to Postgres-only evidence, replaced by a shorter `SKILL.md` instruction, moved to a trial-only probe, or escalated as an administrative integration request.

### 15.5 Runtime text rules

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

### 15.6 Component model

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

### 15.7 Runtime guard templates

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

LLMs may adjudicate which preapproved guard template fits a semantic risk. They cannot author executable guard logic, filesystem paths, shell commands, SQL, or capability expansion.

### 15.8 Description management

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


### 15.9 SkillGraphIR for composed and decomposed workflows

SkillGraphIR is required when a candidate operation involves multiple component skills, ordered subprocedures, state transitions, fallback branches, verifier nodes, or localized repair. It is not rendered wholesale into agent context. It is an internal graph contract used by the broker, evaluator, compiler, and rollback system.

Minimum shape:

```json
{
  "skill_graph_ir_version": "1.0",
  "graph_kind": "composition | decomposition | broker_plan | repair_plan",
  "root_skill_id": null,
  "nodes": [
    {
      "node_id": "n1",
      "skill_id": "11111111-1111-4111-8111-111111111111",
      "skill_version_id": "22222222-2222-4222-8222-222222222222",
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

### 15.10 Skill granularity classes

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

## 16. Skill lifecycle state machine

SkillKernel uses separate states for evidence patterns, candidates, managed skills, versions, and external-skill inventory. Pattern and cluster states live in evidence/topology tables; managed skill states live in `autoskill.skills`; version states live in `autoskill.skill_versions`; external read-only state lives in `autoskill.external_skill_inventory`.

Pattern and candidate states:

```text
observed_pattern
candidate_cluster
ephemeral_candidate
trial_candidate
validated_candidate
```

Managed skill statuses:

```text
ephemeral_candidate
trial_candidate
validated_candidate
active
canary_active
archived
quarantined
frozen
superseded
revoked
deleted_by_retention
```

Version statuses:

```text
draft
staged
trial_active
canary_active
active
archived
rejected
rolled_back
quarantined
superseded
revoked
```

External inventory statuses:

```text
visible
missing
changed
ignored
quarantined
external_readonly
```

Transitions:

```text
observed_pattern → candidate_cluster → ephemeral_candidate
ephemeral_candidate → trial_candidate → validated_candidate → staged version
staged version → trial_active → canary_active → active
trial_candidate → rejected
trial_candidate → quarantined
active → archived
active → frozen
active → superseded
active version N → staged version N+1 → canary_active → active version N+1
active version N+1 → rolled_back, active version N restored
archived → trial_candidate → staged → canary_active → active
frozen → staged repair → canary_active → active
frozen → archived
active/quarantined/frozen → revoked when retention, deletion, or provenance revocation requires it
```

Transition requirements:

| Transition | Required gates |
|---|---|
| observed pattern → candidate cluster | recurrence or high-severity explicit signal, source confidence, redaction complete |
| candidate cluster → ephemeral candidate | duplicate/archived match check, source provenance, no hard scanner denial |
| ephemeral candidate → trial candidate | clustered evidence, explicit current-user request, or configured admin bootstrap policy; evaluator feasibility; provenance complete |
| trial candidate → validated candidate | target probes, no-skill control, nearest active/archived comparison, scanner pass |
| validated candidate → staged version | SkillIR valid, context compiler feasible, manifest plan complete |
| staged → trial/canary/active | target eval pass, regression eval pass, context-budget pass, manifest complete, rollback pointer present |
| active → archived | utility/resource-cost threshold, drift/risk policy, or active-bank budget |
| archived → active | recurrence, archived match, scanner re-pass, drift check, eval pass |
| active → frozen | repeated canary failure, scanner discovery, operator command, critical drift, or harmful attribution |
| active → superseded | replacement passes combined probes and migration plan |
| rollback | preceding version snapshot exists, manifest verifies, evolution transaction can revoke derived artifacts |
| revoke | source deletion, retention policy, malicious-source finding, or privacy deletion traverses provenance graph |

---


## 17. Autonomous skill topology operations

This section is the core product behavior. SkillKernel continuously optimizes the skill library topology through four primary autonomous operations:

```text
create
improve
compose
decompose
```

Supporting operations include compile/recompile, repair, add validator, add adapter, add disambiguator, archive, promote, merge duplicates, split support files, freeze, rollback, and no-op. Supporting operations exist to make the four primary operations safer and more effective.

### 17.1 Shared invariants for all topology operations

Every topology operation must satisfy these invariants:

1. It is represented as an `evolution_transaction`.
2. It cites source evidence and maturity state.
3. It has a structured LLM semantic verdict or plan where semantic reasoning is required.
4. It is normalized into deterministic SkillIR or lifecycle changes.
5. It passes scanner, policy, capability, token, and taint gates.
6. It has target probes and regression probes.
7. It has broker/routing replay when it changes description, relationships, visibility, composition, decomposition, or active status.
8. It can be rolled back across files, DB state, embeddings, broker caches, probes, context hints, and derived memories.
9. It writes only SkillKernel-owned active/archive roots.
10. It records attribution and utility outcomes after activation.

### 17.2 Operation 1 — create

**Purpose:** add a missing reusable skill that does not already exist as an active skill, archived skill, component, or repairable candidate.

**Primary evidence:** repeated missing-skill events, repeated manual workflows, recurring user corrections, recurring failure/fix pairs, high-value explicit user request, or archived-but-stale skill demand.

**LLM role:** infer the reusable procedure, applicability boundary, negative boundary, verification checks, failure handling, and candidate SkillIR from evidence clusters.

**Deterministic role:** active/archived duplicate search, hard-invariant checks, calibrated soft evidence banding, schema validation, scanner/evaluator, token budgeting, file writing, activation, rollback, and utility tracking.

**Acceptance tests:**

- no adequate active skill exists;
- no archived skill can be promoted/repaired more cheaply;
- target probes pass;
- no-skill/current-nearest-skill controls show positive marginal value;
- regression probes pass;
- security scanner passes;
- runtime description does not shadow stronger skills.

**Rollback:** archive or remove the created skill from active root, revoke embeddings/context hints/probes derived from it, and mark candidate/transaction rolled back.

### 17.3 Operation 2 — improve

**Purpose:** increase the utility, reliability, safety, concision, portability, or routing precision of an existing skill.

**Primary evidence:** skill helped but was inefficient, skill failed, tool/API drift, user correction, repeated verification failure, shadowing, misleading description, high token cost, stale support artifact, or evaluator/canary failure.

**LLM role:** author localized SkillIR change plans, repair hypotheses, clearer boundaries, validators, failure modes, contract updates, or compression plans.

**Deterministic role:** identify target version, generate diff, validate capability deltas, run regression probes, compare token/risk/utility, stage files, atomically activate or roll back.

**Acceptance tests:**

- patch is localized and evidence-linked;
- target failure improves;
- prior passing behavior remains inside regression budget;
- token/risk/capability deltas are justified;
- broker replay does not increase shadowing;
- canary monitoring confirms no production degradation.

**Rollback:** restore preceding active version and revoke all derived state from the rejected version.

### 17.4 Operation 3 — compose

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

### 17.5 Operation 4 — decompose

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

### 17.6 Topology operation scoring

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

Activation requires hard gates passing and an Autonomous Decision Orchestrator action of `auto_accept` or `stage_canary`. `operation_score` is a soft ranking signal, not an activation authority by itself.

### 17.7 Operation selection precedence

When multiple candidates compete, prefer the least invasive operation that solves the measured problem:

```text
no-op/reschedule or collect more evidence if evidence is weak
→ description/disambiguator repair
→ improve existing active skill
→ promote/repair archived skill
→ compose if repeated workflow cluster is strong
→ decompose if broad-skill false-positive/partial-use evidence is strong
→ create new skill if no reusable existing/archived/component path exists
→ archive/freeze if risk or negative utility dominates
```

This ordering prevents append-only skill growth while still allowing the library to become more capable.

### 17.8 Broker behavior for composed and decomposed skills

The runtime broker must understand granularity:

- use composed workflow skill when the user task matches the end-to-end workflow;
- use component skills when the user task matches only a subprocedure;
- suppress broad predecessor when a successor has better precision;
- include prerequisite components only when necessary;
- avoid loading both composed skill and all components unless verification requires it;
- log whether the composed/decomposed topology improved outcome.

### 17.9 Metrics for the four operations

Track separately:

| Operation | Primary metrics |
|---|---|
| create | missing-skill reduction, future reuse, target-pass delta, duplicate avoidance, token cost. |
| improve | failure reduction, regression rate, token delta, utility delta, drift recovery. |
| compose | co-use workflow success, component-vs-composed delta, step/token reduction, shadowing delta. |
| decompose | retrieval precision, false-positive reduction, token reduction, successor coverage, rollback rate. |

A release is not acceptable if it reports only aggregate “skills created” counts. The topology operations must have separate dashboards and acceptance criteria.


## 18. Skill creation algorithm

### 18.1 Creation priority

Before creating a new skill:

1. Search active skills.
2. Search archived skills.
3. Search skill components.
4. Search rejected/quarantined candidates for earlier similar attempts.
5. Check duplicate/merge potential.
6. Check whether an existing skill only needs description/disambiguator improvement.

Only then create.

### 18.2 Candidate triggers

Trigger a candidate when one or more are true:

- explicit user request to create/save a skill;
- repeated successful workflow with reusable procedure;
- repeated failure with stable fix;
- user correction recurs;
- tool failure pattern recurs;
- high-value task required repeated manual reasoning;
- archived skill demand recurs but archived skill is stale and repairable;
- active skill repeatedly shadows or gets shadowed and needs split/merge.

### 18.3 Candidate decision bands

Creation thresholds are soft policy inputs, not administrative-escalation blockers. The creation algorithm uses calibrated decision bands over recurrence, evidence confidence, projected utility, risk, context cost, reversibility, and explicit user intent.

Default soft policy values:

```yaml
min_recurrence_count: 3
min_distinct_sessions: 2
min_evidence_confidence: 0.72
min_projected_utility: 0.15
max_soft_risk_score: 0.35
max_token_cost_for_new_skill: 900
explicit_user_request_override: true
high_severity_failure_override: true
allow_ephemeral_below_threshold: true
allow_canary_near_threshold: true
allow_llm_high_confidence_semantic_override: true
```

Explicit user requests, high-severity repeated failures, strong raw-vault intent evidence, or high-confidence LLM semantic adjudication may lower soft recurrence and utility requirements. They do not bypass hard invariants: scanner, redaction, provenance, path containment, OpenClaw compatibility, rollback, token hard caps, and required evaluation still apply.

If a candidate misses a soft threshold, the default next step is not administrative escalation. The creation service chooses one of:

```text
collect_more_evidence
run_re_adjudication
create_ephemeral_candidate
compile narrower skill
repair archived skill
improve existing active skill
create probe-only record
no_op_reschedule
auto_reject_with_reason
```

Threshold policy must be versioned and calibrated against delayed outcomes. A workspace with limited historical data starts with conservative soft thresholds but can still act autonomously through explicit user requests, raw-vault intent evidence, ephemeral candidates, and canary-only activation.

### 18.4 Contrastive induction

For each candidate domain:

1. Cluster failures.
2. Cluster successes.
3. Retrieve nearest success for each failure.
4. Compare failed and successful trajectories.
5. Extract the behavior present in success and missing in failure.
6. Convert the delta into candidate components.
7. Generate probes for both failure repair and success preservation.

### 18.5 Candidate plan schema

The LLM emits only a structured plan:

```json
{
  "candidate_kind": "new_skill",
  "target_skill_id": null,
  "slug": "pdf-table-repair",
  "frontmatter": {
    "name": "pdf-table-repair",
    "description": "Use for repairing or extracting PDF tables when text extraction/layout alignment failed; not for generic PDF summary."
  },
  "components": [
    {
      "type": "functional",
      "title": "PDF table recovery workflow",
      "content": "Detect extraction failure mode, select deterministic or visual inspection path, reconstruct table conservatively, verify row/column integrity.",
      "evidence_ids": ["evidence:4f9a2b1c-1111-4222-8333-abcdefabcdef"]
    }
  ],
  "runtime_sections": {
    "WHEN": ["PDF table extraction failed or table layout evidence is required."],
    "INPUTS": ["source_pdf_path or page_image_path", "requested table/page/range", "required output format"],
    "DO": ["inspect failure mode", "choose extraction/visual path", "reconstruct conservatively"],
    "VERIFY": ["row/column counts match evidence", "headers align", "uncertain cells are marked"],
    "FAIL": ["stop when source is unavailable, unreadable, or outside allowed paths"],
    "DO_NOT_USE_WHEN": ["generic PDF summary", "non-table diagram", "prose-only document"],
    "NEVER": ["fabricate missing cell values", "overwrite the source PDF"]
  },
  "support_files": [],
  "capabilities": ["filesystem-read"],
  "environment_contracts": ["pdf_text_extraction_tool_available OR page_visual_inspection_available"],
  "probes": ["probe_pdf_table_born_digital", "probe_pdf_table_scanned_layout"],
  "expected_benefit": "reduce repeated table-repair failures and false-positive generic PDF skill loads",
  "known_risks": ["OCR uncertainty", "ambiguous merged cells"]
}
```

The deterministic compiler/writer validates and renders the plan.

---

## 19. Skill improvement algorithm

### 19.1 Improvement triggers

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

### 19.2 Improvement actions

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

### 19.3 Evidence requirements

An improvement must cite evidence IDs. It cannot be based only on model preference.

Minimum evidence for normal improvement:

- one explicit user correction, or
- two similar failures, or
- one severe failure with reproducible probe, or
- three retrieval/usage logs showing confusion, or
- one verified drift contract violation.

### 19.4 Regression-aware acceptance

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

## 20. SkillIR compiler and renderers

### 20.1 Purpose

The compiler transforms SkillIR into compact runtime artifacts. It is not summarization. It is structured compilation with deterministic validation, token budgeting, policy checks, and artifact hashing.

The primary renderer target is OpenClaw `SKILL.md`. Additional renderers may produce:

- broker context hints;
- probe definitions;
- environment contract checks;
- manifest files;
- support-file manifests;
- audit summaries.

### 20.2 Compiler stages

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

### 20.3 Compiler quality gates

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

### 20.4 Compression principles

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

### 20.5 Token budget

Default budgets:

```yaml
frontmatter_description_max_chars: 160
runtime_skill_target_tokens: 350
runtime_skill_max_tokens: 900
context_hint_max_tokens: 800
support_file_reference_max_tokens: 120
```

If a skill requires more, split it, move details into support files loaded only when needed, or keep evidence in Postgres rather than prompt context.


### 20.6 Context-loadable artifact audit

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
      "hash": "sha256:4c6f6e746578742d636f6d70696c65722d61727469666163742d6578616d706c6531",
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

### 20.7 Semantic compression acceptance

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

### 20.8 Compression failure actions

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

### 20.9 Context-aware examples policy

Examples are expensive. They may enter runtime text only if probe data shows the agent fails without them. Prefer one minimal counterexample or one terse template over full demonstrations. Store full examples in Postgres or probe fixtures, not `SKILL.md`.

### 20.10 Description minimization

OpenClaw injects skill metadata into the prompt for eligible skills, so the description itself is runtime context. Description writing is a compiler task.

Required description style:

```text
Repair PDF table extraction failures; use when extraction/layout/OCR uncertainty affects tabular data; not for narrative PDF summaries.
```

Reject descriptions that are generic, marketing-like, or broad enough to cause false-positive loading.


### 20.11 SkillIR migration

SkillIR is versioned. Migrations must be deterministic and reversible where possible.

Rules:

- never mutate historical SkillIR rows in place;
- create a new `skill_ir_revisions` row for migrated versions;
- record compiler version and migration reason;
- run scanner/evaluator gates after migration;
- keep old rendered artifacts available for rollback;
- fail closed if migration cannot preserve meaning.

---

## 21. Curation, archive, promotion, and merge

### 21.1 Active bank budget

The active bank is bounded.

Suggested defaults:

```yaml
max_active_skills: 80
max_active_skill_description_tokens_total: 4000
max_active_skillkernel_runtime_tokens_total_soft: 20000
max_new_skills_per_day: 8
max_improvements_per_skill_per_day: 3
max_archive_promotions_per_day: 10
```

The exact values should be configurable.

### 21.2 Utility score

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

### 21.3 Bank-level optimization

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

### 21.4 Archive policy

Archive when:

- utility below threshold for sustained period;
- no recent relevant retrievals;
- repeatedly harmful;
- repeatedly shadowing better skills;
- drifted and repair not worthwhile;
- superseded by another skill;
- token/risk cost exceeds benefit.

Archive never deletes history. It moves active files out of OpenClaw skill roots and updates DB status.

### 21.5 Promotion policy

Promote archived skill when:

- recent evidence matches archived skill;
- archived skill is better match than active skills;
- drift contracts still pass or repair passes;
- scanner passes current version;
- target/regression probes pass;
- active bank budget can accommodate it or another skill is archived.

### 21.6 Merge policy

Merge when:

- duplicate or overlapping skills repeatedly match same tasks;
- shadowing cannot be solved by descriptions;
- combined skill is shorter than separate skills;
- combined probes pass;
- no lost capability from merged boundaries.

If a merge increases context bloat or ambiguity, do not merge. Add disambiguators instead.

---


### 21.7 Composition policy

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

### 21.8 Decomposition policy

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

### 21.9 Merge/split remain supporting operations

Merge and split still exist, but they are narrower than compose/decompose:

| Operation | Meaning |
|---|---|
| merge | collapse duplicates or near-duplicates into one skill. |
| split | divide a file/component mechanically without creating an autonomous topology strategy. |
| compose | create a higher-order workflow skill from distinct reusable skills. |
| decompose | replace a broad skill with successor skills based on separable usage evidence. |

Do not use merge as a substitute for composition. Do not use split as a substitute for decomposition.


## 22. Contract and drift monitoring

### 22.1 Contract types

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

### 22.2 Contract record

```json
{
  "contract_type": "cli|api|package|path|schema|permission|format|service",
  "role": "operational_precondition|verification|output_assumption",
  "value": "pdftotext >= 24.0 available on PATH",
  "validation_method": "probe|tool_check|static|manual",
  "severity": "low|medium|high|critical",
  "last_checked_at": "2026-06-02T00:00:00Z",
  "status": "valid|violated|unknown"
}
```

### 22.3 Drift jobs

Run drift checks:

- on schedule;
- after tool failures;
- after OpenClaw/plugin updates;
- after dependency/package updates;
- before archived promotion;
- before active bank curation if contracts are stale.

### 22.4 Drift actions

If drift is detected:

1. mark contract violated;
2. generate targeted repair candidate;
3. add drift probe;
4. evaluate repair;
5. activate repair if gates pass;
6. archive/freeze if repair fails or risk is high.

---

## 23. Evaluation and probe-bank design

### 23.1 Evaluation categories

| Category | Purpose |
|---|---|
| target probes | confirm intended improvement |
| regression probes | preserve prior correct behavior |
| sibling probes | prevent shadowing and misuse |
| no-skill controls | measure intervention effect |
| adversarial probes | detect prompt injection and unsafe actions |
| drift probes | check environment contracts |
| canary probes | monitor production outcomes after activation |

### 23.2 Acceptance gate

Acceptance is split into hard invariants and soft evidence margins. Hard invariants are absolute. Soft margins determine whether to activate broadly, canary narrowly, gather more evidence, narrow the candidate, or reject.

A candidate is inadmissible if any hard invariant fails:

```text
scanner_critical_findings = true
OR path_containment_failed = true
OR manifest_or_rollback_missing = true
OR policy_forbidden_capability_expansion = true
OR required_redaction_failed = true
OR provenance_missing_or_revoked = true
OR OpenClaw_skill_format_invalid = true
OR evaluator_unavailable_for_required_gate = true
OR regression_hard_budget_exceeded = true
```

For admissible candidates, soft margins are evaluated as a decision band:

```text
target_probe_pass_rate
regression_margin
adversarial_noncritical_findings
token_delta
utility_delta
shadowing_delta
context_pressure
canary_reversibility
LLM_semantic_confidence
evidence_maturity
```

Suggested default policy:

```yaml
target_probe_min_pass_rate_for_direct_activation: 0.85
target_probe_min_pass_rate_for_canary: 0.70
regression_failure_hard_budget: 0
adversarial_critical_budget: 0
max_token_delta_without_utility_gain: 0
min_utility_delta_for_direct_activation: 0.03
min_utility_delta_for_canary: 0.00
allow_more_probe_generation_near_margin: true
allow_narrow_scope_recompile_near_margin: true
allow_ephemeral_trial_near_margin: true
```

For noisy tasks, use statistical confidence intervals, repeated probes, counterfactual trials, and canaries. Do not convert near-threshold uncertainty into immediate administrative escalation unless the action is high-impact, irreversible, policy-forbidden, or cannot be evaluated autonomously.

### 23.3 Intervention testing

For candidate skill S:

1. Run probes without S.
2. Run probes with S.
3. Compare fixes, new failures, token cost, latency, and tool errors.
4. Accept only if net improvement is positive under regression budget.

### 23.4 Probe generation

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

### 23.5 Canarying

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

### 23.6 Executor-profile-aware evaluation

Each probe result is scoped to an executor profile. A skill version can be active for one profile, degraded for another, and blocked for a third. Activation requires profile compatibility for the target workspace/agent. Cross-profile success is a measured property, not an assumption.

### 23.7 Marginal-value and counterfactual trials

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

### 23.8 Dynamic artifact-grounded probes

Probe generation uses real artifacts: failing commands, changed schemas, file samples, API responses, stack traces, missing binaries, permission errors, and user corrections. Stale probes are retired only after the skill’s contract changes and the retirement itself passes the normal scanner/evaluator/version gate.

---

## 24. Scanner and security model

### 24.1 Scanner layers

| Scanner | Checks |
|---|---|
| path scanner | no path traversal, no absolute writes outside roots |
| Markdown scanner | no hidden comments, Markdown reference-link tricks, invisible Unicode, bidi controls, suspicious links, HTML trickery |
| instruction scanner | no prompt injection, sleeper triggers, delayed activation, exfiltration, policy override, credential requests |
| capability scanner | capabilities declared and allowed |
| script scanner | no dangerous shell, network, credential, persistence, self-modifying code unless explicitly allowed |
| dependency scanner | no unapproved package installs or remote downloads |
| semantic scanner | LLM-assisted risk analysis over sanitized artifact |
| guidance/context scanner | detects hidden operational narratives, unsafe best-practice framing, approval-policy drift, credential-handling drift, persistence/exfiltration/destruction narratives, and behavior-steering guidance in `SKILL.md`, support files, broker bundles, memories, workspace context files, and historical imports |
| diff scanner | checks what changed from the preceding version |

### 24.2 Forbidden patterns

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
- harmful actions framed as routine maintenance, best practice, cleanup, optimization, safety hardening, or normal workflow;
- instructions that quietly redefine approval policy, security posture, credential handling, filesystem scope, network scope, or operator intent;
- narrative guidance that directs future risky actions without explicit current user intent;
- bootstrap/context guidance that tells the agent to normalize, conceal, automate, or persist risky behavior;
- memory-poisoning or instruction-laundering patterns;
- arbitrary dependency installation;
- model-behavior jailbreak text.

### 24.3 Capability manifest

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

### 24.4 LLM authority limits

The LLM may make structured semantic verdicts and plans for intent, redaction meaning, memory declassification, replay-corpus intent synthesis, skill topology, context equivalence, artifact usefulness, and repair strategy. Those verdicts are first-class autonomy inputs, not merely comments.

The LLM never directly controls:

- filesystem target path;
- archive path;
- SQL execution;
- shell execution;
- dependency installation;
- policy-state mutation;
- scanner acceptance;
- evaluator acceptance;
- rollback eligibility;
- capability expansion;
- activation state;
- raw-content reveal.

Deterministic services decide admissibility, execution, activation, rollback, and policy-state changes. This preserves full semantic autonomy while preventing unchecked agency over irreversible or externally scoped effects.

### 24.5 Audit-runtime binding

Scanner/evaluator acceptance is bound to exact bytes, renderer version, manifest, dependency hashes, and broker context rendering. If any of these change, acceptance is invalidated. Mutable URLs, remote scripts, package install commands, and support artifacts require re-scan on every material change.

### 24.6 Cross-skill and context-bundle scanning

The scanner checks:

- individual `SKILL.md` output;
- support files and manifests;
- the full rendered broker bundle;
- sibling skills with similar names or descriptions;
- dependency and prerequisite bundles;
- conflict/supersession chains;
- external skills visible in the same OpenClaw session.

A bundle can be rejected even if every individual skill passes.

### 24.7 Runtime action boundary enforcement

Where OpenClaw hook surfaces permit it, the plugin should implement deterministic boundary checks around risky tool calls. These checks are not LLM judgments. They enforce declared capabilities, known path roots, no-secret policies, drift-blocks, and skill manifest constraints.

---


### 24.8 Provenance manifest for generated artifacts

Every activated SkillKernel artifact set must include a manifest that lets the sidecar verify what was generated, from what source, under which gates, and how to roll it back. This is modeled after supply-chain provenance principles, but kept lightweight for v1.

Required file:

```text
<active-skill-root>/<slug>/.autoskill-manifest.json
```

Required shape:

```json
{
  "schema": "skillkernel-artifact-manifest.v1",
  "skill_id": "4b4c7a67-8fb7-4be7-95b3-6fcd3f9561f8",
  "skill_version_id": "63d4e605-8f49-4c23-8a7f-48b18b3a0a6d",
  "skill_ir_revision_id": "1a3f4ca7-a44d-4a6a-9b6d-41a5b6b9450a",
  "evolution_transaction_id": "b0792fb3-2c7e-4d91-8cc4-b4df4dced69f",
  "generator": {
    "skillkernel_version": "1.0.0",
    "compiler_version": "skillkernel-compiler.v1",
    "model_profile": "service_reasoner",
    "model_qualification_run_id": "be4147ad-bc33-4f88-a410-7a55ad5e3959",
    "embedding_profile": "default_embeddings"
  },
  "artifacts": [
    {
      "path": "SKILL.md",
      "sha256": "9f2c4f6f0f4b8e5a0a89e2e6a3d56f2ebf2c67e5f4e43db42dc57fa70d0e0a24",
      "kind": "skill_md",
      "loadability": "agent_may_read",
      "context_loadable": true
    },
    {
      "path": "scripts/extract_tables.py",
      "sha256": "4b68ab3847feda7d6c62c1fbcbeebfa35eab7351ed5e78f4ddadea5df64b8015",
      "kind": "script",
      "loadability": "script_only",
      "context_loadable": false,
      "capabilities": ["read_user_file", "write_workspace_file"],
      "test_command": "python3 scripts/extract_tables.py --self-test"
    },
    {
      "path": "references/table-schema.json",
      "sha256": "7d793037a0760186574b0282f2f435e7c57f29e2abf361b3f0d5b1b9ddf1358aa0",
      "kind": "schema",
      "loadability": "agent_may_read",
      "context_loadable": true
    }
  ],
  "capabilities": ["read_user_file", "write_workspace_file"],
  "scanner_run_ids": ["40b6f7d3-9659-4ad7-92ad-4c91b9f2a424"],
  "evaluation_run_ids": ["ef715dc8-a67b-482e-8f58-144e2ef92de4"],
  "token_budget_record_id": "9d7f5f4c-91e2-4c06-901e-3fdfaa3982c8",
  "rollback_pointer": {
    "previous_skill_version_id": "b96a49e2-693a-43fd-9f91-f96e2c2f4783",
    "archive_path": ".autoskill/archive/4b4c7a67-8fb7-4be7-95b3-6fcd3f9561f8/v2"
  },
  "created_at": "2026-06-02T18:40:31Z"
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

## 25. Filesystem writer

### 25.1 Active and archive roots

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

### 25.2 Write flow

```text
validate structured plan
→ render files in staging
→ parse SKILL.md
→ scan files
→ compute hashes
→ run evaluations
→ fsync staging files
→ acquire skill activation lock
→ confirm activation window: no in-use session for the target active root, or defer activation to next-session/idle policy
→ snapshot preceding active version
→ atomic replace active root from staging
→ verify hashes
→ update DB transaction
→ invalidate broker/retrieval caches
→ append audit record
→ enqueue canary monitor
```

Activation must respect OpenClaw skill snapshots and watcher behavior. SkillKernel does not rewrite an active package while a session may consume that package. If an activation window is unavailable, the evolution transaction remains staged and the sidecar activates it at the next safe session boundary, idle window, or explicit configured maintenance window. Watcher-triggered refresh is treated as an OpenClaw compatibility mechanism, not as permission to mutate in-use packages.

### 25.3 Rollback flow

```text
identify preceding active version
→ verify archive hashes
→ stage rollback files
→ atomic replace active root
→ update DB status
→ append audit record
→ mark failed version rolled_back
→ freeze if critical
```

### 25.4 Path containment

All write paths are derived from `workspace_id`, `skill_id`, version, and sanitized slug. The LLM cannot supply a path. Relative support-file paths are checked against an allowlist:

```text
SKILL.md
.autoskill-manifest.json
.autoskill-contract.json
scripts/<safe-name>.py
scripts/<safe-name>.sh
references/<safe-name>.md
templates/<safe-name>.md
templates/<safe-name>.txt
templates/<safe-name>.json
schemas/<safe-name>.json
schemas/<safe-name>.yaml
data/<safe-name>.json
data/<safe-name>.csv
data/<safe-name>.yaml
assets/<safe-name>.<allowed-ext>
examples/<safe-name>.md
tests/test_<safe-name>.py
probes/<safe-name>.jsonl
adjunct_requests/<safe-name>.json
```

No symlinks. No hardlinks. No parent traversal. No absolute paths.

---

## 26. Scheduler and job queue

### 26.1 No external scheduler dependency

Do not use:

- OpenClaw Cron;
- system cron;
- Kubernetes CronJob;
- Celery beat;
- pg_cron.

Use sidecar-owned schedules and jobs in Postgres.

The `cron_expr` schedule kind in SkillKernel tables means a cron-expression parser owned by the sidecar scheduler. It is not OpenClaw Cron and is not delegated to any external scheduler.

### 26.2 Scheduler loop

```text
every scheduler_tick:
  acquire advisory lock
  find due schedules
  coalesce misfires according to policy
  insert jobs with idempotency keys
  update next_run_at
  release lock
```

### 26.3 Worker lease loop

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

### 26.4 Core schedules

Recommended defaults:

| Job | Frequency |
|---|---|
| event normalization | continuous/queued |
| historical source discovery | on install, daily incremental, and manual trigger |
| historical import/backfill | queued, low priority, bounded by byte/session/file limits |
| historical bootstrap consolidation | after import batches and daily while backlog exists |
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

### 26.5 Misfire policy

Use:

- `coalesce` for routine scans;
- `catch_up_limited` for retention/audit;
- `skip` for expensive non-critical analysis;
- `immediate` only for safety/rollback jobs.

---

## 27. Outcome attribution and credit ledger

### 27.1 Why attribution exists

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

### 27.2 Attribution signals

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

### 27.3 Credit events

Credit events feed:

- utility score;
- curation;
- improvement triggers;
- archive/promote decisions;
- retrieval calibration;
- learned curator dataset.

---

## 28. Observability

### 28.1 Metrics

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

### 28.2 Dashboards

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

### 28.3 Audit hash chain

Every mutation appends an audit record with previous audit hash and current hash. Audit verification runs daily and before release/export.

---

## 29. Configuration

Example config:

```yaml
skillkernel:
  mode: autonomous_guarded
  workspace_id: auto
  active_root: "<workspace>/skills/autoskill"
  archive_root: "<workspace>/.autoskill/archive"
  staging_root: "<workspace>/.autoskill/staging"

  deployment:
    sidecar_bind: "127.0.0.1:8765"
    sidecar_auth: token_env
    sidecar_token_env: SKILLKERNEL_SIDECAR_TOKEN
    unix_socket_path: null
    run_as_non_root: true
    allow_public_bind: false

  paths:
    openclaw_home_env: OPENCLAW_HOME
    openclaw_state_dir_env: OPENCLAW_STATE_DIR
    openclaw_config_path_env: OPENCLAW_CONFIG_PATH
    openclaw_state_dir_default: "~/.openclaw"
    workspace_roots: []
    session_store_roots: []
    trajectory_roots: []
    transcript_corpus_roots: []
    host_container_path_map: []

  evidence_retention:
    mode: full_autonomous_vault       # metadata_only | redacted_only | full_autonomous_vault
    raw_vault_enabled: true
    capture_user_prompts: true
    capture_agent_messages: true
    capture_model_inputs: true
    capture_model_outputs: true
    capture_tool_params: true
    capture_tool_results: true
    capture_system_prompt_windows: bounded
    default_raw_retention_days: 30
    secret_candidate_retention_hours: 24
    encrypt_raw_evidence: true
    raw_access_requires_job_purpose: true
    raw_access_audit: true
    embed_raw_content: false
    hosted_llm_raw_private_allowed: false
    require_local_llm_for_raw_private: true
    minimum_necessary_window_tokens: 12000
    max_raw_window_tokens: 50000

  autonomous_adjudication:
    enabled: true
    structured_verdict_required: true
    require_evidence_ids: true
    require_deterministic_redaction_pass: true
    require_provenance_edges: true
    repeated_adjudication:
      enabled_for_near_margin: true
      max_attempts: 3
      verifier_prompt_enabled: true
      record_disagreement: true
    semantic_uncertainty:
      sample_when_ambiguous: true
      max_samples: 3
      cluster_by_meaning: true
    escalation_policy:
      escalate_on_policy_forbidden_raw_access: true
      escalate_on_raw_reveal: true
      escalate_on_predelegated_authority_absent_for_T4: true
      escalate_on_repeated_contradictory_adjudications_after_fallback: true

  autonomous_decision_orchestrator:
    enabled: true
    hard_invariants_fail_closed: true
    soft_thresholds_are_adaptive: true
    min_autonomous_fallback_attempts_before_escalation: 2
    allow_llm_high_confidence_semantic_override_for_soft_thresholds: true
    allow_ephemeral_candidate_when_under_supported: true
    allow_canary_when_near_soft_margin: true
    allow_more_probe_generation_near_margin: true
    allow_scope_reduction_near_margin: true
    threshold_deadlock_detector: true
    threshold_policy_versioning: true
    confidence_model: calibrated_composite
    calibration:
      enabled: true
      families:
        - intent_reconstruction
        - replay_episode_promotion
        - memory_declassification
        - external_skill_relationship
        - topology_operation_choice
        - skill_plan_semantic_adjudication
        - context_equivalence
        - semantic_compression_preservation
        - broker_decision_adjudication
        - freeze_repair_triage
      metrics:
        - coverage_rate
        - false_accept_rate
        - false_reject_rate
        - abstention_rate
        - unnecessary_abstention_rate
        - calibration_error
        - brier_like_score
        - canary_failure_rate
        - rollback_rate
        - harm_finding_rate
      threshold_lifecycle: [draft, replay_backtest, shadow_mode, canary_policy, active, retired_or_rolled_back]
      use_conformal_when_supported: true
      mark_low_support_when_sparse: true
    confidence_components:
      - llm_structured_confidence
      - evidence_coverage
      - source_fidelity
      - recurrence_diversity
      - repeated_adjudication_agreement
      - semantic_uncertainty
      - contradiction_check
      - scanner_risk
      - evaluator_margin
      - reversibility
      - canary_containment
      - model_profile_qualification
      - historical_calibration
      - delayed_outcome_reliability
    escalation_policy:
      escalate_on_policy_forbidden_raw_access: true
      escalate_on_raw_reveal: true
      escalate_on_irreversible_external_mutation_without_predelegated_authority: true
      escalate_on_missing_required_infrastructure: true
      escalate_on_repeated_contradictory_adjudications_after_fallback: true
      escalate_on_soft_threshold_only: false


  historical_ingestion:
    enabled: true
    mode: incremental            # discover_only | import | incremental | disabled
    dry_run_inventory_on_start: true
    agents: all                  # all | [main, work, research-agent]
    max_age_days: null           # null means no age cutoff
    max_bytes_per_run: 536870912
    max_sessions_per_run: 2000
    max_files_per_run: 10000
    max_llm_candidates_per_batch: 50
    low_priority: true
    import_sources:
      session_stores: true
      raw_transcripts: true
      sanitized_session_history: true
      trajectories: true
      compaction_summaries: true
      workspace_memory_files: true
      workspace_context_files: true
      background_tasks: true
      task_flows: true
      lobster_workflows: false
      plugin_session_extensions: true
      queued_turn_injections: true
      active_memory_transcripts: false
      diagnostics_exports: false
      channel_media_artifacts: false
      transcription_artifacts: true
      preprocessed_message_artifacts: true
      existing_skills: true
      qmd_exports: false
      memory_capability_public_artifacts: false
      memory_wiki_exports: false
      honcho_exports: false
      allowlisted_project_docs: []
      allowlisted_workflow_docs: []
      diagnostics_export_paths: []
      media_artifact_allowlist:
        enabled: false
        mime_types: ["text/plain", "text/markdown", "application/json", "application/pdf", "image/png", "image/jpeg"]
        max_file_bytes: 10485760
    deny_globs:
      - "**/.git/**"
      - "**/.cache/**"
      - "**/node_modules/**"
      - "**/vendor/**"
      - "**/dist/**"
      - "**/build/**"
      - "**/.env*"
      - "**/*secret*"
      - "**/*credential*"
    raw_content_policy: vault_then_redacted_derivative
    embed_policy: redacted_only
    llm_policy: autonomous_adjudication_with_raw_vault_when_needed
    compaction_summary_confidence_multiplier: 0.65
    stale_source_confidence_multiplier: 0.50
    historical_candidate_initial_maturity_cap: recurring
    require_normal_gates_for_activation: true

  plugin:
    capture_raw_conversation: true
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
    dsn_env: "SKILLKERNEL_DATABASE_URL"
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
        # base_url_env: SKILLKERNEL_LOCAL_LLM_BASE_URL
        # api_key_env: SKILLKERNEL_LOCAL_LLM_API_KEY
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
        max_input_sensitivity: private
        allow_raw_evidence: true
        require_local_for_raw_private: true

  embeddings:
    active_profile: default_embedding
    profiles:
      default_embedding:
        route_type: openai_compatible   # or openclaw
        provider: configured-embedding-provider
        model: embedding-model-id
        base_url_env: SKILLKERNEL_EMBEDDING_BASE_URL
        api_key_env: SKILLKERNEL_EMBEDDING_API_KEY
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
    approved_support_dirs: ["scripts", "references", "templates", "assets", "examples"]
    keep_tests_outside_active_skill_root: true
    allow_generated_hook_files: false
    allow_generated_cron_files: false
    allow_generated_service_files: false
    mutable_skill_state_location: "postgres_or_workspace_dot_autoskill"

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
    redact_before_ordinary_store: true
    redact_before_embed: true
    raw_content_only_in_vault: true

  scheduler:
    tick_seconds: 30
    worker_count: 4
    max_llm_jobs_concurrent: 2
```

---

## 30. Phased implementation plan

The implementation order is part of the safety design. Do not build autonomous skill writing before the control plane exists.

### Phase 0 — Confirm OpenClaw seams

Deliver:

- exact hook names and payloads for the target OpenClaw version;
- plugin permission requirements;
- active skill root behavior;
- watcher/snapshot behavior;
- prompt/context hook behavior;
- skill invocation observability;
- available stable text-inference seams, including whether `api.runtime.llm.complete` can be used by the SkillKernel relay;
- available stable embedding-provider seams, if any;
- confirmation that OpenClaw Cron and Skill Workshop are not required.

Acceptance:

- plugin can capture turn, message, and tool events without blocking sessions;
- generated test skill loads from the active SkillKernel root;
- archive root is invisible to OpenClaw;
- runtime context hint can be disabled and fails soft;
- OpenClaw-routed text profile either passes relay seam tests or is explicitly marked unavailable;
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


### Phase 5 — Historical ingestion and deployment bootstrap

Deliver:

- historical datasource discovery across configured OpenClaw agents;
- dry-run inventory report;
- parsers for session stores, raw transcripts, sanitized session-history exports, trajectory sidecars/exports, compaction summaries, workspace memory files, workspace context files, background task records, task-flow/workflow records, plugin session-extension state, queued next-turn injections, active-memory persisted transcripts, diagnostic/OTEL exports, channel media/transcription/preprocessing artifacts, and existing skills;
- source fingerprinting and idempotent import checkpoints;
- historical source/item/chunk tables;
- redacted structure-preserving chunking;
- historical evidence extraction and bootstrap consolidation;
- import-source revocation traversal.

Acceptance:

- established deployments with multiple agents can be inventoried without mutating OpenClaw state;
- every imported item records source lineage, parser version, redaction policy, chunking policy, trust, taint, and hash identity;
- raw transcript and memory text is never embedded raw and is sent to an LLM only through raw-vault access policy, minimum-necessary context windows, exposure checks, secret masking/redaction when required, declassification reports, and audit;
- historical candidates can reach observed/recurring maturity but cannot activate without the normal scanner, evaluator, regression, token-budget, and rollback gates;
- repeated import runs are idempotent and resumable;
- external skills are indexed for collision/shadowing but remain read-only;
- non-SkillKernel plugin session state and active-memory artifacts are imported only as allowlisted, tainted, derived evidence;
- diagnostic/OTEL imports remain content-safe unless raw debug logs are explicitly enabled and treated as raw-transcript risk;
- source revocation invalidates derived chunks, embeddings, evidence, memories, candidates, probes, broker caches, and compiled artifacts.

### Phase 6 — Evidence, memory, provenance, and revocation pipeline

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

### Phase 7 — Retrieval, body-aware indexes, and external-skill inventory

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

### Phase 8 — SkillIR, Context Compiler, and Token Budget Governor

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
- optional support files are included only when artifact-planner evidence shows net execution, reliability, or context-budget benefit;
- generated skill packages never self-register OpenClaw hooks, OpenClaw Cron routines, tools, MCP servers, or mutable local databases;
- composed and decomposed workflows have SkillGraphIR when multiple skills or component steps are involved;
- verbose/rationale-heavy runtime text is rejected;
- compression preserves required SkillIR facts and regression probes;
- over-budget artifacts fail closed.

### Phase 9 — Scanner, evaluator, probes, and regression gates

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

### Phase 10 — Deterministic writer, evolution transactions, and rollback

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

### Phase 11 — Runtime Skill-Context Broker and shadowing control

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

### Phase 12 — Creation, improvement, composition, and decomposition in inactive planning mode

Deliver:

- opportunity miner;
- data-to-usable-skill bridge runner;
- evidence-packet assembler;
- contrastive induction;
- active/archive/external-skill matching before creation;
- create/improve/compose/decompose candidate planners;
- operation-plan normalizer;
- SkillIR and SkillGraphIR skeleton builders;
- artifact planner;
- topology candidate tables;
- component/co-use graph analysis;
- operation-specific trial generation;
- data-to-skill trace records;
- adjudication/status UI for inactive candidates, operation plans, and traceability.

Acceptance:

- candidates require evidence packets, not raw transcript snippets;
- every proposed candidate exposes the source → evidence → packet → candidate → plan → SkillIR/SkillGraphIR trace;
- a seeded missing-workflow dataset produces a valid create candidate with compiled inactive `SKILL.md`;
- a seeded skill-failure dataset produces an improvement candidate tied to the correct current skill version;
- compose candidates beat component-only baselines before activation;
- decompose candidates beat original-skill baselines before activation;
- broad/clunky/black-hole skill detection works in dry-run reports;
- invalid, unsafe, low-maturity, or duplicate candidates exit through explicit non-skill outcomes instead of becoming active skills.

### Phase 13 — Autonomous guarded apply, canarying, curation, and archive/promotion

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

### Phase 14 — Advanced governance and production hardening

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

## 31. Production acceptance criteria

The release is production-ready only if all are true:

1. no dependency on OpenClaw Cron;
2. no dependency on Skill Workshop;
3. no per-skill databases;
4. no per-skill schemas;
5. ordinary analytics, indexing, evidence, and audit stores receive redacted or minimized event payloads; full-fidelity content may persist only in the governed encrypted raw-evidence vault when policy permits it;
6. embeddings are created only from redacted derivatives or declassified semantic outputs, never from raw private content;
7. sidecar outage does not block normal OpenClaw usage;
8. sidecar endpoint is private/authenticated and never exposed publicly;
9. container path mappings and root containment checks are verified before historical import or file activation;
10. scheduler survives restart and resumes safely;
11. job leases prevent duplicate mutation;
12. skill operation selection considers improve, promote, compose, decompose, merge, and archive before creating duplicates;
13. every created skill is a normal OpenClaw skill with valid `SKILL.md`;
14. every mutation has manifest, hashes, scanner result, evaluator result, and rollback pointer;
15. hidden comments and invisible Markdown are rejected;
16. scanner blocks known malicious skill patterns;
17. regression gate blocks local fixes that break prior probes;
18. no-skill controls or equivalent intervention checks exist for accepted skills;
19. active skill budget is enforced;
20. runtime context broker is bounded and fail-soft;
21. archived skills are invisible to OpenClaw but searchable through SkillKernel;
22. archived promotion works;
23. rollback works under canary failure;
24. drift checks detect simple broken environment contracts;
25. retrieval logs track retrieved/rendered/injected/used/outcome;
26. shadowing logs and remediation exist;
27. audit hash chain validates;
28. all core invariants are automated tests;
29. create, improve, compose, and decompose are implemented as separate operation classes with separate evidence, evaluation, and metrics;
30. composition requires co-use/sequence evidence and component-vs-composed trials;
31. decomposition requires partial-use/false-positive/separable-cluster evidence and original-vs-successor trials;
32. topology operations are rollback-complete across graph edges, broker policy, embeddings, probes, and active files;
33. no active SkillKernel-owned skill exists without a complete data-to-skill trace from source record through evidence packet, operation plan, SkillIR/SkillGraphIR revision, artifact plan, compiled package, evaluation verdict, evolution transaction, broker registration, and rollback pointer;
34. seeded datasets prove the bridge can produce create, improve, compose, and decompose proposals without bypassing scanner/evaluator/token/security gates;
35. every bridge stage has inspectable input IDs, output IDs, status, reason code, and non-skill failure exit;
36. every context-loadable artifact has a registry row, token count, budget, content hash, compiler version, scanner status, and provenance;
37. every compressed description passes positive/negative routing-equivalence tests;
38. every compressed body passes information-preservation and regression gates;
39. every support snippet has classification, budget, scan result, and retrieval boundary;
40. context-value-per-token is measured and can drive archive, compose, decompose, or no-skill decisions.
41. historical datasource discovery works across configured agents without crossing agent/workspace boundaries;
42. historical import supports session stores, transcripts, trajectories, compaction summaries, workspace memories, workspace context files, task records, task-flow/workflow records, plugin session-extension state, queued injections, active-memory persisted transcripts, diagnostics exports, channel media/transcription/preprocessing artifacts, and existing skills;
43. every historical import row has provenance, fingerprint, parser version, redaction version, trust, and taint;
44. historical raw content is never embedded raw, never placed in ordinary analytics/logs, and never compiled into runtime artifacts; LLM analysis of raw historical content occurs only through raw-vault access policy, minimum-necessary windows, declassification reports, and audit;
45. historical candidates use the same create/improve/compose/decompose gates as live candidates;
46. historical source revocation traverses derived chunks, embeddings, evidence, memories, candidates, probes, broker caches, and compiled artifacts;
47. established deployments can run a bounded bootstrap import without degrading normal OpenClaw runtime behavior;
48. replay-corpus candidates can be promoted automatically from raw-vault-linked telemetry by synthesizing `redacted_user_intent` through LLM adjudication plus deterministic validation, without requiring an operator plan in the normal path;
49. hash-only telemetry is reported as degraded evidence fidelity and cannot silently block full-autonomy claims;
50. memory quarantine has autonomous high-confidence accept/reject paths plus escalation only for policy/ambiguity/low-confidence cases;
51. every LLM adjudication stores input IDs, exposure level, declassification report, confidence, deterministic check results, decision, and escalation reason when applicable;
52. raw-prompt retention disabled mode remains functional but surfaces limited autonomy, lower evidence confidence, and reduced replay/canary creation capability;
53. soft-threshold misses do not default to administrative escalation; seeded tests prove the orchestrator first attempts configured autonomous alternatives such as more evidence, more probes, re-adjudication, ephemeral candidates, reduced scope, canary-only activation, autonomous rejection, or no-op reschedule;
54. hard invariants are clearly separated from soft thresholds in code, database records, UI reason codes, and documentation;
55. threshold-deadlock detection identifies stalled candidate cohorts where hard invariants pass but soft thresholds repeatedly block progress, and produces evaluated policy or candidate-remediation actions;
56. composite confidence records include model confidence, evidence coverage, source fidelity, contradiction checks, scanner risk, evaluator margin, reversibility, canary containment, and historical calibration factors;
57. near-margin acceptance tests prove candidates can move to canary, ephemeral, narrower-scope, or more-probe states without administrative intervention when hard gates pass;
58. every autonomous semantic decision family has calibration observations, delayed outcomes, and reliability metrics;
59. policy versions for soft thresholds pass replay/backtest, shadow-mode, or canary-policy evaluation before activation;
60. no hard invariant can be weakened by adaptive threshold updates;
61. high-impact SkillKernel-owned runtime changes use risk tiering, verifier/adjudication when needed, canary containment, and rollback rather than default administrative escalation;
62. administrative escalation records one of the allowed escalation reasons and cannot be triggered solely by a soft-threshold miss;
63. Observatory exposes calibration support, reliability metrics, threshold-deadlock findings, and reason codes for every stalled autonomous decision.

Additional context-management acceptance criteria:

- no SkillKernel-owned context-loadable artifact lacks a loadability class;
- no `SKILL.md` version can activate without token count, semantic-equivalence result, scanner pass, and artifact hash;
- generated descriptions stay within configured character budget unless explicitly excepted by policy;
- runtime skill bodies meet target token budget or produce a deterministic split/decompose decision;
- support files are never assumed safe merely because they are outside `SKILL.md`;
- no raw transcript, rationale, history, or improvement note appears in runtime context unless explicitly promoted through SkillIR and compiler gates;
- context regressions trigger reject, rollback, decompose, description tighten, or broker abstention.

## 32. Risk register

| Risk | Mitigation |
|---|---|
| Skill bloat degrades context | Active budget, context broker, compiler, curation, archive. |
| Over-compression drops rare critical constraints | Coverage map, information-preservation gate, semantic-equivalence probes, regression bank, rollback. |
| Support artifacts become hidden infrastructure | Skill folders cannot silently register OpenClaw hooks, OpenClaw Cron routines, tools, services, or mutable stores; such needs become administrative integration requests. |
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
| Historical import poisoning | Treat all historical transcripts, memory files, and external exports as tainted until redacted, declassified, and corroborated; activation still requires normal gates. |
| Historical import overfits stale workflows | Recency weighting, environment-contract checks, stale-source confidence penalties, current-skill matching, canarying, and rollback. |
| Historical import leaks private facts into skills | User-fact classifier, reusable-procedure separation, redaction-before-store/embed/LLM, and compiler ban on private facts. |
| Historical backfill overwhelms database or runtime | Low-priority backfill pool, byte/session/file limits, checkpoints, rollups, and pause/cancel controls. |
| Skill prompt injection | Scanner, no hidden comments, capability manifest, adversarial probes. |
| Malicious support script | Script scanner, capability policy, no unapproved shell/network. |
| LLM writes dangerous file | Structured plan only, deterministic path-contained writer. |
| pgvector recall loss | Hybrid retrieval, exact rerank, iterative scans, recall audits. |
| Drift from changing tools/APIs | Environment contracts and drift jobs. |
| Scheduler duplicate jobs | Idempotency keys, row locks, advisory locks. |
| Postgres growth | Partitioning, rollups, retention, vacuum/index maintenance. |
| User-facing dependency changes | No Cron/Skill Workshop dependency; narrow skill/hook compatibility surface. |
| Evaluation too expensive | Tiered probes, cached evals, canary sampling, multi-objective budget. |
| Soft-threshold rigidity stalls autonomy | Separate hard invariants from soft decision bands, run autonomous fallback actions before escalation, detect threshold deadlocks, and calibrate policy versions against delayed outcomes. |
| Threshold relaxation becomes unsafe | Threshold updates are policy-versioned, replay-tested, shadowed/canaried, auditable, and forbidden from weakening hard invariants. |
| LLM overconfidence causes bad autonomous decision | Composite confidence, evidence-linked rationale, calibration, contradiction checks, scanner/evaluator gates, canary containment, repeated/verifier adjudication when needed, and rollback. |
| LLM underconfidence suppresses useful autonomy | Track unnecessary abstention, post-abstention success, and threshold-deadlock cohorts; route near-margin decisions to additional evidence, narrower scope, ephemeral candidates, or canary rather than administrative escalation. |
| Autonomy incident | Freeze, quarantine, rollback, audit, operator controls. |

---

## 33. Developer handoff checklist

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
- [ ] Define hard invariants versus soft decision bands for candidate creation, improvement, composition, decomposition, replay-corpus promotion, memory declassification, broker changes, and curation.
- [ ] Define Autonomous Decision Orchestrator action mapping, composite confidence factors, threshold-deadlock detection, and autonomous fallback order before admin escalation.
- [ ] Define support-artifact planning, loadability classes, approved directories, manifest schema, script/test policy, and integration-proposal handling for hook/tool/sidecar-schedule/service-adjunct needs.
- [ ] Define no-human-prose and no-raw-transcript gates for runtime artifacts.
- [ ] Implement the skill-package artifact planner with support-file allowlists, inclusion rubric, scanner bindings, manifest generation, and adjunct-request handling.
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
- [ ] Build historical discovery as read-only inventory before historical import.
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

## 34. References and research traceability

The implementation team should treat this section as the research/design crosswalk, not as optional background. The architecture is intentionally constrained by the platform facts, agent-skill research, context-management research, database behavior, and security findings listed below.

### 34.1 Platform and runtime anchors

- **OpenClaw Creating skills documentation**: OpenClaw skills require `SKILL.md`, support `{baseDir}` references to files in the skill directory, expose optional frontmatter keys such as `user-invocable`, `disable-model-invocation`, and `command-dispatch`, and document support files in `assets/`, `examples/`, `references/`, `scripts/`, and `templates/` for Skill Workshop proposals. URL: https://docs.openclaw.ai/tools/creating-skills
- **OpenClaw Skills format/gating documentation**: OpenClaw skills support `metadata.openclaw` gating for binaries, environment variables, config paths, OS filters, and installer hints; `metadata` must be a single-line JSON object. SkillKernel uses these only for compact OpenClaw-compatible gates and keeps detailed provenance in Postgres/manifests. URL: https://docs.openclaw.ai/tools/skills
- **OpenClaw capability-surface documentation**: OpenClaw distinguishes tools, skills, plugins, hooks, and automation. Generated skill packages provide instructions/resources; they do not create new runtime hooks, tools, OpenClaw Cron routines, model providers, or MCP servers merely by adding files to a skill directory. URLs: https://docs.openclaw.ai/tools and https://docs.openclaw.ai/automation/hooks
- **Agent Skills open standard documentation**: Agent Skills are folders with required `SKILL.md` plus optional scripts, references, assets, templates, and other resources, loaded through progressive disclosure. SkillKernel follows this pattern while adding stricter artifact planning, manifests, scanning, and token gates. URL: https://agentskills.io/home
- **Anthropic Agent Skills documentation and engineering guidance**: Skills can contain metadata, `SKILL.md`, on-demand references, schemas, templates, examples, resources, and executable scripts. Progressive disclosure keeps unused files out of context, while scripts can provide deterministic work without loading code into the prompt. URLs: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview and https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- **GitHub Copilot and Microsoft Agent Skills documentation**: Skills are portable directories of instructions, scripts, and resources; scripts, references, assets, templates, and examples are optional support files, and skills should reference support resources from `SKILL.md` when needed. URLs: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills and https://learn.microsoft.com/en-us/agent-framework/agents/skills
- **Muse Autoskill reference implementation**: Muse Autoskill treats `SKILL.md` as the required package file and uses optional lifecycle/memory metadata, `scripts/`, `tests/`, `resources/`, and `references/`, with staging, testing, registration, and export. SkillKernel adopts the useful package/test/staging idea but keeps canonical state in Postgres/SkillIR rather than mutable package-local memory files. URL: https://github.com/elicie/muse-autoskill
- **OpenClaw Skills documentation**: OpenClaw skills are ordinary directories containing `SKILL.md`; skill metadata and Markdown body are loaded from defined roots and injected into the agent context. SkillKernel must therefore emit standard skill artifacts rather than a custom-only runtime format. URL: https://docs.openclaw.ai/tools/skills
- **OpenClaw Creating Skills documentation**: Skill directories can reference skill-local files with `{baseDir}`, use `metadata.openclaw` for gates such as binaries/env/config/OS, expose optional frontmatter fields such as `user-invocable` and command dispatch, and include support files under `assets/`, `examples/`, `references/`, `scripts/`, or `templates/` when proposal/support-file workflows require them. URL: https://docs.openclaw.ai/tools/creating-skills
- **OpenClaw ClawHub skill format documentation**: Skills are folders with `SKILL.md` plus optional text-based supporting files; runtime metadata declares requirements/install hints; publish surfaces scan text files and enforce bundle limits. URL: https://docs.openclaw.ai/clawhub/skill-format
- **OpenClaw built-in skill-creator guidance**: Keep `SKILL.md` lean, put only trigger-critical facts in the description, and move long examples/docs to `references/`, scripts to `scripts/`, and templates/media to `assets/`. URL: https://github.com/openclaw/openclaw/blob/main/skills/skill-creator/SKILL.md
- **Agent Skills specification**: Skills use progressive disclosure: metadata is loaded first, `SKILL.md` loads when activated, and resources such as `scripts/`, `references/`, or `assets/` load only when required. URL: https://agentskills.io/specification
- **OpenClaw skill creation documentation**: generated skill directories must contain valid `SKILL.md` frontmatter and body. URL: https://docs.openclaw.ai/tools/creating-skills
- **OpenClaw Plugin/Hooks documentation**: typed plugin hooks cover agent runs, prompt construction, provider calls, tool calls, message delivery, session lifecycle, subagents, compaction, installs, and Gateway lifecycle; hooks are in-process extension points and should remain lightweight. The sidecar owns slow scheduling, LLM analysis, evaluation, mutation, and rollback. URL: https://docs.openclaw.ai/plugins/hooks
- **OpenClaw Internal Hooks documentation**: internal hooks cover coarse command, compaction, bootstrap, gateway, and message-processing events. SkillKernel may use plugin-bundled internal hooks only as supplemental side-effect/event coverage, not as the primary ordered middleware or policy surface. URL: https://docs.openclaw.ai/automation/hooks
- **OpenClaw Plugin runtime helpers documentation**: OpenClaw exposes `api.runtime.llm.complete`, runtime event subscriptions such as `api.runtime.events.onAgentEvent(...)` and `api.runtime.events.onSessionTranscriptUpdate(...)`, session helpers, runtime config helpers, and model-thinking policy helpers for plugins; SkillKernel uses only stable helpers and keeps model-relay work outside hook execution. The OpenClaw-routed text profile is valid only when the helper can be used as a maintenance-safe simple-completion relay that does not inherit active user transcript, active tools, approvals, memory, or transient turn context beyond explicitly supplied messages. URL: https://docs.openclaw.ai/plugins/sdk-runtime
- **OpenClaw Plugin SDK overview documentation**: grouped SDK namespaces such as `api.session.state.registerSessionExtension(...)`, `api.session.workflow.enqueueNextTurnInjection(...)`, and `api.agent.events.registerAgentEventSubscription(...)` are the preferred host-hook registration surfaces for new plugin code; `api.onConversationBindingResolved(...)` supplies conversation-binding correlation when available, and memory-capability public artifact/corpus surfaces are the correct way to consume another memory plugin without scraping private storage. URL: https://docs.openclaw.ai/plugins/sdk-overview
- **OpenClaw Configuration reference**: plugin raw-conversation access, prompt-injection allowance, and plugin LLM model overrides are explicit trust gates; SkillKernel must fail closed when required trust gates are absent. URL: https://docs.openclaw.ai/gateway/configuration-reference
- **OpenClaw Scheduled Tasks/Cron documentation**: Cron is Gateway/user-facing automation; SkillKernel must not use it as the internal autonomous maintenance substrate. URL: https://docs.openclaw.ai/automation/cron-jobs
- **OpenClaw Skill Workshop documentation**: useful reference pattern for proposal/scanner/quarantine ideas, but excluded as a dependency because SkillKernel must own its lifecycle pipeline end-to-end.
- **OpenClaw session storage/security documentation**: session transcripts live under `~/.openclaw/agents/<agentId>/sessions/*.jsonl`, so historical import must treat local disk access as the trust boundary and redact before storage/embedding. URL: https://docs.openclaw.ai/gateway/security
- **OpenClaw sessions CLI and session management documentation**: session stores, transcripts, trajectory sidecars, archived/orphan artifacts, topic transcripts, configured session stores, and multi-agent session stores are maintained together; SkillKernel must import idempotently and tolerate pruned, archived, missing, or orphaned files. URLs: https://docs.openclaw.ai/cli/sessions, https://docs.openclaw.ai/concepts/session, and https://docs.openclaw.ai/reference/session-management-compaction
- **OpenClaw Transcripts CLI documentation**: transcript-corpus folders can contain summaries, metadata, and transcript JSONL separate from normal agent-session JSONL; SkillKernel imports them as derived historical evidence when configured. URL: https://docs.openclaw.ai/cli/transcripts
- **OpenClaw Environment variables and migration documentation**: `OPENCLAW_HOME`, `OPENCLAW_STATE_DIR`, `OPENCLAW_CONFIG_PATH`, named profiles, and migration/status commands determine where state, config, workspaces, agents, sessions, and transcript exports live; SkillKernel treats these as discovery inputs and still requires configured root containment before import. URLs: https://docs.openclaw.ai/help/environment and https://docs.openclaw.ai/install/migrating
- **OpenClaw Session tools documentation**: `sessions_history` returns a bounded, safety-filtered view and excludes tool results by default; useful for safe previews, but raw local transcripts or trajectories are needed for full skill-mining reconstruction. URL: https://docs.openclaw.ai/concepts/session-tool
- **OpenClaw Subagents and ACP documentation**: subagent/ACP runs create parent/child session relationships, can inherit or fork context, report child model/provider/runtime metadata, and can expose child transcript/stream-log paths; SkillKernel uses these to mine delegated workflow topology without treating spawn as success. URLs: https://docs.openclaw.ai/tools/subagents and https://docs.openclaw.ai/tools/acp-agents
- **OpenClaw Gateway protocol and task ledger documentation**: task summaries include status, runtime, agent/session keys, child session keys, run/task/flow IDs, timestamps, progress, terminal summaries, and sanitized errors; SkillKernel imports this as activity evidence, not scheduling state. URL: https://docs.openclaw.ai/gateway/protocol
- **OpenClaw Trajectory bundles documentation**: trajectory sidecars/exports can contain ordered runtime events, metadata, prompt-building details, tools, usage, errors, artifacts, and compiled context; they are high-value historical evidence sources. URL: https://docs.openclaw.ai/tools/trajectory
- **OpenClaw Memory overview/QMD/Memory search/configuration documentation**: memory files include `MEMORY.md`, daily `memory/` notes, optional indexes/sidecars, dreaming output, active-memory transcripts when persistence is enabled, and configurable embedding providers; QMD can index memory, extra directories, and transcripts; SkillKernel imports only configured/exported sources and keeps memory evidence governed. URLs: https://docs.openclaw.ai/concepts/memory, https://docs.openclaw.ai/concepts/memory-qmd, https://docs.openclaw.ai/concepts/memory-search, https://docs.openclaw.ai/concepts/active-memory, and https://docs.openclaw.ai/reference/memory-config
- **OpenClaw Context documentation**: workspace context files and skills consume prompt budget; historical ingestion must parse workspace context to understand instructions and token pressure without copying it into skills. URL: https://docs.openclaw.ai/concepts/context
- **OpenClaw Context engine documentation**: context engines can ingest, assemble, compact, and run after-turn persistence, but SkillKernel does not replace the selected context engine in v1; it observes prompt/context behavior through hooks, transcript updates, context-budget metadata, and trajectories. URL: https://docs.openclaw.ai/concepts/context-engine
- **OpenClaw tools/MCP/tool-search documentation**: tool profiles, allow/deny policy, sandbox gates, MCP registries, and tool-search surfaces affect which workflows are possible; SkillKernel imports capability inventories as executor-profile and drift evidence. URLs: https://docs.openclaw.ai/gateway/config-tools, https://docs.openclaw.ai/cli/mcp, and https://docs.openclaw.ai/tools/tool-search
- **OpenClaw Background tasks documentation**: task records track detached work such as ACP runs, subagents, isolated cron executions, and CLI operations; they are activity evidence, not scheduling substrate. URL: https://docs.openclaw.ai/automation/tasks
- **OpenClaw Agent workspace and FAQ documentation**: workspaces contain `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `MEMORY.md`, daily memory files, optional `HEARTBEAT.md`, and skills separately from Gateway state; SkillKernel preserves this boundary during historical import and skill writing. URLs: https://docs.openclaw.ai/concepts/agent-workspace and https://docs.openclaw.ai/help/faq
- **OpenClaw Logging, diagnostics, raw-stream, and transcript hygiene documentation**: logs, diagnostics, and debug streams can identify repeated provider/tool/runtime failures, but raw streams may contain full prompts, tool output, user data, and secrets; SkillKernel treats them as explicit-opt-in corroborating/debug evidence and keeps runtime/system context distinct from user-authored transcript text. URLs: https://docs.openclaw.ai/logging, https://docs.openclaw.ai/help/debugging, and https://docs.openclaw.ai/reference/transcript-hygiene

### 34.1.1 Calibrated autonomy, selective trust, and threshold governance anchors

- **Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement**: supports selective trust in LLM judgments based on calibrated confidence rather than unconditional trust or blanket escalation. SkillKernel applies this to autonomous semantic adjudication. URL: https://arxiv.org/abs/2407.18370
- **Agentic Confidence Calibration / Holistic Trajectory Calibration**: supports using process-level trajectory features, not only final-answer confidence, to estimate autonomous-agent reliability. SkillKernel therefore calibrates confidence from trace, evidence, scanner, evaluator, broker, canary, and rollback features. URL: https://arxiv.org/html/2601.15778v1
- **Uncertainty Quantification in LLM Agents**: supports treating uncertainty in tool-using agents as structured uncertainty across interactive decision processes. SkillKernel propagates uncertainty through evidence packets, semantic adjudication, candidate states, probes, canaries, and runtime broker decisions. URL: https://arxiv.org/html/2602.05073v2
- **Self-Evaluation Improves Selective Generation in Large Language Models**: supports quality-calibrated self-evaluation for selective generation. SkillKernel uses LLM self-evaluation as one calibrated feature, never as standalone authority. URL: https://arxiv.org/html/2312.09300v1
- **Answer, Refuse, or Guess? Investigating Risk-Aware Decision Policies in Language Models**: shows that language models can both over-answer high-risk cases and over-defer low-risk cases. SkillKernel treats both over-action and over-deferral as measurable autonomy failures. URL: https://arxiv.org/html/2503.01332v2
- **Survey of Confidence Estimation and Calibration in Large Language Models**: supports confidence decomposition and task-specific calibration instead of trusting verbalized model confidence. URL: https://aclanthology.org/2024.naacl-long.366/
- **NIST AI Risk Management Framework 1.0**: organizes trustworthy AI risk management around Govern, Map, Measure, and Manage. SkillKernel maps those functions into policy versioning, source/risk classification, calibration metrics, and adaptive management of autonomy policies. URL: https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf
- **OWASP Agentic AI Threats and Mitigations / OWASP LLM risks**: supports hard boundaries around permissions, raw reveal, external mutation, execution surfaces, prompt injection, supply-chain risk, and excessive agency. URLs: https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/ and https://genai.owasp.org/llm-top-10/
- **Microsoft secure autonomous agentic systems guidance**: supports identity, least privilege, runtime monitoring, and defense-in-depth as autonomy increases. SkillKernel keeps semantic adjudication separate from privileged execution and records action attribution, policy decisions, and rollback pointers. URL: https://learn.microsoft.com/en-us/security/zero-trust/sfi/secure-agentic-systems

### 34.2 Database and retrieval anchors

- **pgvector documentation**: supports exact search, HNSW/IVFFlat approximate search, hybrid lexical/vector retrieval, filtered-search caveats, iterative scans, partial indexes, partitioning, and reranking. SkillKernel uses pgvector as a candidate generator, never as the authority. URL: https://github.com/pgvector/pgvector
- **PostgreSQL full-text search**: use for lexical retrieval and hybrid reranking alongside vector search. URL: https://www.postgresql.org/docs/current/textsearch.html
- **PostgreSQL transactional primitives**: use ordinary SQL transactions, constraints, advisory locks, row-level/logical scoping, partitioning when measured, and durable job queues for the control plane.
- **OpenTelemetry trace concepts/specification**: spans, span context, span links, attributes, and context propagation provide a mature model for correlating multi-service work. SkillKernel implements a local Postgres trace spine and optional content-safe OpenTelemetry export. URL: https://opentelemetry.io/docs/concepts/signals/traces/

### 34.3 Agent-skill lifecycle, acquisition, retrieval, and topology anchors

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

### 34.4 Skill representation and compiler anchors

- **SkillSmith**: skills should compile into boundary-first minimal executable runtime interfaces rather than verbose human documentation. URL: https://arxiv.org/html/2605.15215v1
- **Skill-as-Pseudocode / Formal Skill / SkillIR-style work**: typed contracts, structured procedures, deterministic validators, and backend emission reduce ambiguity and support portability. URL: https://arxiv.org/abs/2605.27955
- **SkillRouter**: names and descriptions are insufficient for routing; body-aware indexing over SkillIR, compiled runtime text, contracts, probes, and support summaries is required.
- **SkVM / SkillRT / OpenSkillEval-style work**: skill effectiveness depends on executor profile, harness, runtime environment, tool availability, permissions, and artifact state; compiler-style environment binding can improve portability and reduce token consumption. URL: https://arxiv.org/abs/2604.03088
- **SWE-Skills-Bench-style findings**: skills must be evaluated by marginal value, not existence; token overhead and version-mismatched guidance can make otherwise plausible skills harmful.

### 34.5 Context-management and compression anchors

- **Anthropic effective context engineering**: context is a finite resource with diminishing returns; agents need curated context, not indiscriminate loading. URL: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **Anthropic Agent Skills overview and best practices**: staged/progressive disclosure and bounded `SKILL.md` contents support a compiler/token-governor architecture. URL: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- **Lost in the Middle**: long context is not used uniformly; relevant information can be missed depending on position. Runtime skill text must be short, positioned, and salient. URL: https://aclanthology.org/2024.tacl-1.9/
- **RULER**: advertised context windows can exceed effective context windows on complex long-context tasks. URL: https://arxiv.org/abs/2404.06654
- **Context Rot**: increasing input length and distractor content can degrade performance. SkillKernel must measure token cost, false-positive loads, and context-value per token. URL: https://www.trychroma.com/research/context-rot
- **Prompt Compression and Semantic Prompt Compression work**: compression must preserve semantics and task performance; lossy summaries are insufficient for runtime skill artifacts. URLs: https://arxiv.org/abs/2410.12388 and https://arxiv.org/html/2605.04426v1
- **LLMLingua / LongLLMLingua**: prompt compression can reduce token burden while preserving or improving task performance when key information is preserved and positioned well. URL: https://arxiv.org/abs/2310.06839
- **Lossless dictionary-encoding prompt compression**: repetitive structures can be compressed through dictionaries if savings exceed dictionary overhead and equivalence is validated; SkillKernel can use this only for internal analysis prompts or broker hints where the dictionary itself is budget-positive. URL: https://arxiv.org/abs/2604.13066
- **Active Context Compression**: long-running agents require autonomous context/memory management. SkillKernel treats context-loaded artifacts as compiled projections from full-fidelity SkillIR and evidence stores. URL: https://arxiv.org/html/2601.07190v1

### 34.6 Drift, security, and memory-poisoning anchors

- **OWASP Top 10 for LLM Applications**: prompt injection, insecure output handling, supply-chain vulnerabilities, sensitive information disclosure, excessive agency, and insecure plugin design are first-order system risks. URL: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- **Skill-Inject**: skill files can serve as persistent prompt-injection carriers; context-aware authorization and scanner gates are required. URL: https://arxiv.org/abs/2602.20156
- **SkillJect**: payloads can be hidden in `SKILL.md` and auxiliary artifacts; scanner, trace, and deterministic writer gates are non-optional. URL: https://arxiv.org/html/2602.14211v2
- **Malicious Agent Skills / ToxicSkills / harmful-skill analyses**: skills can be dangerous through capability amplification, local privilege, dynamic fetch/execute, or credential exposure even without obvious prompt injection.
- **Trojan's Whisper**: bootstrap guidance and workspace context files can be abused as persistent operating guidance; SkillKernel scans workspace guidance, memories, skills, support files, and broker bundles for hidden behavior-steering narratives and does not compile local guidance directly into skills. URL: https://arxiv.org/abs/2603.19974
- **OpenClaw PRISM**: runtime security work over OpenClaw supports in-process observation plus sidecar policy/audit services; SkillKernel uses that architecture pattern while keeping deterministic scanner, evaluator, attribution, and rollback gates. URL: https://arxiv.org/html/2603.22895
- **OpenClaw security survey and systematic evaluation work**: OpenClaw-style agents require lifecycle-wide security governance across cognition, execution, interaction, memory, skills, plugins, tools, and runtime orchestration; SkillKernel's scanner/evaluator/broker/action-attribution controls are part of that lifecycle governance, not prompt-only safety. URLs: https://arxiv.org/html/2605.25435v1 and https://arxiv.org/abs/2604.03131
- **ClawKeeper**: layered skill/plugin/watcher-style safety systems support combining context constraints, runtime enforcement, and external state monitoring; SkillKernel uses deterministic guard templates and sidecar canaries rather than relying on generated safety prose. URL: https://arxiv.org/abs/2603.24414
- **ToolHijacker**: attacks can target tool retrieval and selection; runtime broker and tool-call boundary checks must be monitored. URL: https://www.ndss-symposium.org/ndss-paper/prompt-injection-attack-to-tool-selection-in-llm-agents/
- **MemSkill**: memory extraction, consolidation, and pruning can themselves be skill-like routines that evolve; SkillKernel keeps memory-building governed, typed, and versioned rather than static summarization. URL: https://arxiv.org/abs/2602.02474
- **Contextual Experience Replay**: distilling past agent experiences into dynamic memory buffers supports bootstrapping from prior trajectories, but the experiences must be selected, synthesized, and retrieved under constraints. URL: https://openreview.net/forum?id=RXvFK5dnpz
- **How Memory Management Impacts LLM Agents**: memory management choices materially affect long-term agent behavior; SkillKernel therefore treats historical memory import as governed state, not passive text. URL: https://arxiv.org/html/2505.16067v1
- **Graph-based Agent Memory survey**: memory extraction, storage, retrieval, and evolution form a lifecycle; SkillKernel maps historical ingestion into this lifecycle with provenance and graph revocation. URL: https://arxiv.org/html/2602.05665v1
- **AgentPoison and memory-poisoning work**: long-term memory and RAG stores can be poisoned with small malicious demonstrations; historical import requires taint, provenance, redaction, and revocation. URL: https://openreview.net/forum?id=Y841BRW9rY
- **RAG chunking and ingestion research**: source parsing, chunking, and summary augmentation affect retrieval quality; SkillKernel uses structure-preserving chunks and source lineage rather than flat text dumps. URLs: https://pmc.ncbi.nlm.nih.gov/articles/PMC12649634/ and https://arxiv.org/html/2510.06999v1
- **MemMorph / eTAMP / memory-poisoning work**: persistent memories can steer tool selection and future reasoning across sessions; memory quarantine, provenance, declassification, revocation traversal, and negative controls are required. URLs: https://arxiv.org/html/2605.26154v1 and https://arxiv.org/html/2604.02623v2
- **AttriGuard / CausalArmor / AgentSentry / intent-to-execution integrity work**: high-risk actions should record causal attribution and verify that user intent, not poisoned context, caused the action.
- **MOSS / runtime-governance / self-evolving-agent work**: evolution must be evidence-batched, staged, verified, versioned, and rollbackable. V1 must not autonomously rewrite the plugin, scheduler, scanner, evaluator, compiler, migrations, or policy engine.

- **Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement**: supports selective trust in LLM judgments using confidence calibration and escalation only when uncertainty remains. SkillKernel applies this pattern to semantic adjudication by treating LLM verdicts as admissible when confidence is calibrated, evidence-linked, and deterministic checks pass.
- **LLM confidence-calibration and uncertainty-estimation work**: verbalized model confidence is not sufficient by itself. SkillKernel uses composite confidence decomposition, not a single self-reported number.
- **OWASP LLM excessive-agency guidance**: autonomous action needs bounded authority, least privilege, auditing, and hard safety invariants. SkillKernel permits high-confidence LLM semantic decisions while keeping file writes, raw policy access, activation, rollback, scheduling, and external capability changes under deterministic control.

### 34.7 Research-to-design traceability matrix

| Research or platform finding | design response |
|---|---|
| OpenClaw skills are context-loaded `SKILL.md` artifacts. | SkillKernel emits normal OpenClaw skills; SkillIR remains canonical; `SKILL.md` is compiled runtime output. |
| OpenClaw hooks are in-process and timeout-sensitive. | Plugin is thin; sidecar owns slow autonomous work. |
| OpenClaw Cron is user/Gateway-facing automation. | Sidecar-owned Postgres scheduler; no OpenClaw Cron dependency. |
| Skill Workshop is useful but unstable as a dependency. | Treat as reference pattern only; SkillKernel owns proposal, scanner, evaluator, writer, archive, and promotion. |
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
| Workspace/bootstrap guidance can steer behavior persistently. | Workspace context files are high-sensitivity guidance surfaces; importer scans them for guidance injection and never compiles them directly into general skills. |
| OpenClaw runtime security benefits from plugin-side observation plus sidecar policy. | SkillKernel keeps in-process hooks lightweight while sidecar services own risk accumulation, scanner/evaluator decisions, attribution, and audit. |
| Memory can be poisoned and persist. | Memory quarantine, provenance, declassification, revocation traversal, and negative controls. |
| Unsafe actions can be caused indirectly. | Action-attribution logs and high-risk boundary checks. |
| Rollback can leave derived state behind. | Evolution transactions covering DB state, files, embeddings, caches, memories, broker hints, probes, and derived artifacts. |
| LLM reasoning is useful but nondeterministic. | LLM adjudicates semantic meaning and authors structured plans; deterministic infrastructure validates admissibility, writes, schedules, archives, and rolls back. |
| Context-loaded skill docs are AI-facing, not human-facing. | No-human-prose gate; compact runtime interface; full details remain in SkillIR/Postgres. |
| Reliable composition requires precondition-effect structure. | SkillIR effect signatures, typed graph edges, component compatibility checks, node-level verification, and localized repair. |
| One-off reflection can overfit. | Diagnostic momentum store, contrastive support counts, counterevidence, targeted probes, and patch thresholds. |
| Autonomous control-plane behavior must be explainable across services. | Trace spine with `trace_id`, `span_id`, span links, safe attributes, audit linkage, and optional OpenTelemetry export. |

---

### 34.8 Additional platform and autonomy notes

- **OpenClaw plugin hooks documentation**: conversation-bearing hooks such as `before_agent_run`, `llm_input`, `llm_output`, `before_agent_finalize`, and `agent_end` require explicit `allowConversationAccess`; low-content provider telemetry hooks omit raw prompts/responses. SkillKernel uses this to separate full-fidelity autonomous mode from degraded telemetry-only mode.
- **OpenClaw trajectory documentation**: trajectory bundles record prompt/system-prompt/tool/transcript/model/settings/usage/error context and can contain prompts, tool results, local paths, and runtime data. SkillKernel treats trajectories as high-fidelity historical evidence subject to raw-vault/declassification policy.
- **OWASP LLM Top 10 and Excessive Agency guidance**: prompt injection, insecure output handling, sensitive information disclosure, insecure plugin design, excessive agency, overreliance, and data poisoning require layered controls. SkillKernel permits LLM semantic adjudication but constrains execution through deterministic policy, scanners, evaluators, minimum permissions, and audit.
- **NIST AI RMF Generative AI Profile**: generative AI systems may require different human-AI oversight configurations, tracking, documentation, data provenance, retention, monitoring, and risk-based controls. SkillKernel implements risk-based escalation rather than default administrative escalation.
- **RAG and memory privacy/security research**: private retrieval stores and persistent memories can leak data or be poisoned. SkillKernel therefore stores raw evidence in a governed vault, avoids raw embeddings, tracks taint/provenance, and declassifies only narrow operational meaning for skills/replay/memory.
- **LLM-as-judge/selective evaluation research**: LLM judges can scale semantic adjudication but require calibration, consistency checks, and selective escalation. SkillKernel uses the qualified text model as an autonomous semantic adjudicator whose verdicts must pass deterministic confidence, provenance, redaction, and evaluator gates.

## 35. Comprehensive landscape assimilation matrix

This appendix records the source-by-source ingestion pass. SkillKernel does not depend on these projects or papers. They inform design pressure, failure modes, and implementation requirements.

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
| Contextual Experience Replay | Past trajectories can be accumulated and synthesized into reusable dynamic memory for future decisions. | Historical import feeds governed evidence/memory buffers and bootstrap consolidation. | Do not expose raw historical experience directly to runtime context. URL: https://openreview.net/forum?id=RXvFK5dnpz |
| RAG ingestion/chunking research | Poor parsing/chunking causes retrieval mismatch, noise, and downstream errors. | Historical importer uses structure-preserving parsers, source ranges, redacted chunks, and provenance-aware indexing. | Do not treat historical ingestion as flat filesystem text dumping. URLs: https://pmc.ncbi.nlm.nih.gov/articles/PMC12649634/ and https://arxiv.org/html/2510.06999 |

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
| Trojan's Whisper | Bootstrap guidance and workspace context files can become persistent attack surfaces that frame malicious behavior as normal operational guidance. | Treat `AGENTS.md`, `SOUL.md`, `TOOLS.md`, `BOOTSTRAP.md`, `IDENTITY.md`, `USER.md`, `HEARTBEAT.md`, `BOOT.md`, memory files, skills, support files, and broker bundles as guidance-bearing artifacts requiring provenance, tainting, scanner clearance, and no direct compilation into runtime skills. | Do not trust workspace guidance merely because it is local, old, or phrased as best practice. URL: https://arxiv.org/abs/2603.19974 |
| OpenClaw PRISM | In-process plugin hooks plus sidecar services can provide runtime security monitoring, risk accumulation, policies, and auditability without forking the host runtime. | Confirms SkillKernel's thin-plugin/thick-sidecar security posture and action-attribution controls. | Do not replace SkillKernel's deterministic scanner/evaluator/rollback gates with LLM-only runtime judgment. URL: https://arxiv.org/html/2603.22895 |
| Sleeper Memory Poisoning / MemoryGraft / AgentPoison / MemMorph | Persistent memory and retrieval stores can become durable attack surfaces influencing future behavior. | Keep memory quarantine, taint, provenance, delayed activation, derived-data revocation, and control-flow integrity logs. | Do not let raw untrusted text become skill memory or runtime instruction. URLs: https://arxiv.org/abs/2605.15338, https://arxiv.org/html/2512.16962v1, https://openreview.net/forum?id=Y841BRW9rY |
| OWASP LLM risks and SLSA | LLM applications need supply-chain, data-poisoning, plugin design, excessive-agency, and provenance controls. | Keep fail-closed policy, SLSA-style manifests, audit hash chains, and deterministic writer. | Do not expose autonomous mutation without rollback-complete provenance. URLs: https://genai.owasp.org/, https://slsa.dev/ |

### 35.1 Landscape assessment

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

Conceptual expansion is deferred unless implementation seam failures, OpenClaw API validation, benchmark failures, security red-team findings, or production telemetry reveal a concrete uncovered failure mode.


## 36. Implementation readiness and execution order

Proceed to implementation with this specification.

The top-level architecture is:

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
calibrated selective-trust controller
autonomy calibration corpus
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

The core product definition is:

```text
SkillKernel is an autonomous evidence-driven skill-library topology optimizer for OpenClaw.

It collects rich live and historical session/chat-turn/tool/outcome evidence and uses that evidence to perform four first-class autonomous topology operations:

create      = add a missing useful skill
improve     = modify an existing useful skill
compose     = build a higher-order workflow skill from repeatedly co-used smaller skills
decompose   = split a broad/clunky skill into sharper reusable skills
```

The context-management invariant is non-optional: **context management is a hard architectural invariant**. Anything that can enter the running agent context is a compiled AI-facing runtime artifact, not human documentation. The full-fidelity source of truth is SkillIR plus Postgres evidence. `SKILL.md`, broker hints, runtime snippets, and any support material eligible for context loading must be scrutinized token-by-token for semantic density, execution value, safety, routing value, verification value, and marginal value per token. Verbose explanation, rationale, history, human-readable commentary, raw transcript fragments, duplicated constraints, and unmeasured examples are forbidden in runtime artifacts unless they measurably improve execution.

The implementation order is:

```text
redaction
→ storage
→ executor profiles
→ scheduler
→ trace spine
→ evolution transaction/provenance/revocation tables
→ historical ingestion bootstrap
→ event/evidence/memory pipeline
→ memory quarantine
→ autonomous semantic adjudication
→ autonomy calibration corpus and selective-trust policy trials
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

Implementation sequencing rule: **do not build autonomous skill writing first**. Build the control plane first. Autonomous mutation should begin only after redaction, storage, scheduler, historical ingestion, trace spine, scanner, evaluator, deterministic writer, rollback, evolution transactions, provenance/revocation traversal, context compiler, token budget governor, SkillIR effect-signature validation, diagnostic momentum, audit, memory quarantine, executor profiles, action attribution, context attribution, and broker versioning exist.

Further design changes require a concrete uncovered failure mode discovered through OpenClaw API seam validation, implementation findings, benchmark failures, red-team findings, or production telemetry. The implementation-hardening elements in this specification include historical ingestion/bootstrap, SkillIR effect signatures, diagnostic-momentum improvement state, trace-spine observability, model/embedding profile qualification gates, SkillGraphIR for composed/decomposed workflows, provenance manifests for generated artifacts, and the control-plane requirements described above.
