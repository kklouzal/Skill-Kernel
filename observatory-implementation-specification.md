# SkillKernel Observatory — Web Administration and Diagnostic Interface Implementation Specification

**Document type:** implementation handoff specification  
**Project:** SkillKernel Observatory web administration and observability interface  
**Deployment target:** SkillKernel Python sidecar container  
**Audience:** implementation engineers, frontend engineers, sidecar/backend engineers, operators, security reviewers  
**Relationship to core SkillKernel specification:** this document adds the sidecar-hosted Observatory interface that exposes SkillKernel’s runtime state, calibrated autonomy, evidence-fidelity posture, raw-vault policy state, semantic adjudication, lifecycle operations, evidence flow, component health, and diagnostic surfaces. It does not change the core autonomous skill-management architecture or grant the UI independent authority over SkillKernel decisions.

---

## 0. Executive implementation specification

Build a sidecar-hosted web interface named **SkillKernel Observatory**.

The Observatory is a multi-resolution diagnostic, observability, and administration layer for SkillKernel. It gives operators a bird’s-eye view of the entire autonomous skill-management pipeline and allows drill-down into every station in the system: live OpenClaw capture, historical ingestion, redaction, raw-evidence vault handling, evidence-fidelity classification, memory derivation, LLM semantic adjudication, calibrated selective-trust decisions, replay/canary corpus generation, retrieval, skill topology operations, context compilation, scanner/evaluator gates, deterministic artifact writing, activation, broker behavior, curation, rollback, scheduler health, database/index health, and audit trails.

The interface is not a second autonomous control plane. It is an inspectable operating console over the existing sidecar control plane: LLM adjudication, deterministic admissibility checks, threshold policy, scanner/evaluator gates, activation, rollback, revocation, and administrative escalation state remain owned by SkillKernel services. Administrative actions exposed through the UI must call the same authenticated sidecar APIs, pass the same policy checks, and write the same audit/evolution records as command-line or plugin-triggered actions.

The visual concept is an **interactive assembly line** with four reliable zoom depths: full system, subsystem workcell, station cockpit, and object microscope:

```text
[OpenClaw live capture] ─▶ [Historical bootstrap] ─▶ [Redaction + taint + raw-vault policy]
        │                         │                         │
        ▼                         ▼                         ▼
[Spool + normalization] ─▶ [Evidence fidelity + memory] ─▶ [LLM semantic adjudication]
        │                         │                         │
        ▼                         ▼                         ▼
[Retrieval + broker] ─▶ [Autonomy decision orchestrator] ─▶ [Replay/canary corpus]
        │                         │                         │
        ▼                         ▼                         ▼
[Topology operations: create | improve | compose | decompose] ─▶ [SkillIR / SkillGraphIR]
        │                                                   │
        ▼                                                   ▼
[Artifact planner + context compiler] ─▶ [Scanner] ─▶ [Evaluator]
        │                                      │             │
        ▼                                      ▼             ▼
[Deterministic writer] ─▶ [Activation / archive / rollback] ─▶ [Canary + runtime telemetry]
        │                                                                    │
        └────────────────────▶ [Audit + trace spine + read models + calibration corpus] ◀────┘
```

Each bracketed station is a visual node. Each node shows live health, throughput, backlog, latency, error/freeze state, and selected key metrics. Clicking a node transitions into a component-level cockpit with comprehensive internals, trace/event lists, local subgraphs, artifacts, jobs, warnings, and safe administrative actions.

The interface must be visually rich enough to make system behavior legible at a glance while remaining precise enough for debugging production failures. The implementation stack is:

```text
React + TypeScript + Vite application shell
React Flow / @xyflow/react for interactive pipeline, skill topology, and component subgraphs
ELK.js for automatic layered graph layout
Apache ECharts for high-density charts, timelines, heatmaps, funnels, Sankey diagrams, and treemaps
PixiJS canvas/WebGL/WebGPU overlay for animated event particles and high-density visual effects
Monaco Editor for read-only JSON/SkillIR/manifest/diff inspection
TanStack Query for API caching, invalidation, and server-state management
FastAPI sidecar routes for authenticated APIs, static frontend serving, and live streams
PostgreSQL read models, materialized summaries, and LISTEN/NOTIFY invalidation when it improves freshness without disturbing core processing
```

The design uses progressive disclosure. The overview shows the entire machine. Drill-down pages expose component details. Trace replay animates an individual event, job, candidate, skill change, or rollback through the pipeline. The UI supports both live operation and historical time-window replay.

Live operation must feel continuous. After a page or tab is mounted, routine telemetry changes reconcile into existing components in place. The interface must not clear and rebuild the visible route, graph, charts, or station cards on ordinary refresh cycles. Full replacement is reserved for intentional navigation, incompatible schema changes, sequence-gap recovery, or explicit operator reload.

---

## 1. Product goals

### 1.1 Primary goals

The Observatory must answer these questions without requiring an engineer to inspect logs manually:

1. Is SkillKernel healthy right now?
2. What is currently moving through the pipeline?
3. Where are jobs, events, candidates, or skill operations blocked?
4. Which autonomous operations are being proposed, evaluated, accepted, rejected, archived, promoted, rolled back, or frozen?
5. Which semantic decisions were adjudicated by the configured LLM, what evidence supported them, and what deterministic admissibility checks bounded them?
6. Which soft thresholds, confidence components, calibration policy versions, and fallback ladders affected an autonomous decision?
7. Which decisions are operating with `raw_vault_linked`, `declassified_summary`, `redacted_derivative`, `metadata_only`, or `hash_only` evidence?
8. Which decisions are degraded because evidence is insufficient for autonomy, and what autonomous evidence-repair actions are in progress?
9. Which skills are active, archived, shadowing each other, stale, harmful-risky, high-value, token-expensive, underused, or failing?
10. Which historical sources have been ingested, skipped, redacted, quarantined, or converted into evidence?
11. Which replay/canary episodes were synthesized from real telemetry, what redacted intent was produced, and what provenance supports it?
12. Which model and embedding profiles are configured, qualified, unhealthy, or producing failures?
13. What evidence caused a skill operation?
14. What scanner/evaluator gates accepted or rejected an operation?
15. What context did the runtime broker render, and why?
16. How much agent context is being spent on each skill, broker hint, or compiled artifact?
17. Which deterministic writer transaction created or changed files?
18. Can this change be rolled back, and what derived data must be revoked with it?
19. Which administrative escalations exist, what hard boundary caused them, and what autonomous alternatives were already attempted?
20. Which component owns a failure, and what is the safest next action?

### 1.2 Visual goals

The interface presents a command center for an autonomous skill factory:

- animated pipeline flow, where events, jobs, evidence clusters, skill candidates, and artifacts appear as moving particles;
- station nodes with live gauges and status rings;
- edge thickness and animation speed based on throughput and backlog;
- heat overlays for latency, error pressure, context pressure, regression pressure, and security risk;
- click-to-zoom transitions from system map to station cockpit;
- timeline replay for a single trace or evolution transaction;
- graph maps for skill topology, dependencies, composition, decomposition, shadowing, supersession, conflict, and broker routing;
- context-budget visualizations that make token waste immediately visible;
- provenance graph views that show source → evidence → memory → candidate → SkillIR → artifact → activation → runtime outcome;
- dark command-center aesthetic with restrained motion, high contrast, keyboard navigation, and reduced-motion mode.

Visual richness must never obscure correctness, evidence quality, or autonomy state. Every animated element must be backed by a concrete event, aggregate, or read model. Decorative effects may exist, but they must not imply system state.

The command-center aesthetic must expose causality and autonomy, not only status. The desired visual effect is a living, inspectable factory: material enters, gets transformed, passes gates, becomes artifacts, activates, generates runtime outcomes, and feeds back into future topology decisions. The operator must be able to move from a glowing overview edge to the exact records responsible for that glow.

### 1.3 Operational goals

The Observatory must support soak testing and production monitoring:

- real-time monitoring during live OpenClaw usage;
- historical bootstrap monitoring for deployments with months of existing session history;
- backlog and queue visibility;
- component health and freeze-state visibility;
- low-content diagnostic telemetry by default;
- raw/redacted content controls with role-based access;
- raw-vault access visibility without casual raw exposure;
- evidence-fidelity visibility for every decision family;
- calibrated-autonomy visibility for LLM adjudications, threshold policy, and fallback ladders;
- auditability for every administrative action and every autonomous semantic decision;
- safe deep links for sharing an exact trace, job, candidate, skill version, evaluation, scanner finding, or transaction;
- exportable diagnostic bundles that redact content by default.

### 1.4 Diagnostic coverage goal

The Observatory must make SkillKernel intelligible at four depths:

| Depth | Purpose | Primary UI surface |
|---|---|---|
| System map | Determine whether the full SkillKernel machine is healthy, moving work, and producing useful outcomes. | Assembly-line overview, KPI ribbon, issue board, timeline replay. |
| Subsystem lens | Inspect a coherent group of components that jointly perform a larger function. | Workcell pages such as capture/bootstrap, learning/memory, autonomy/adjudication, runtime context, topology design, quality gates, artifact mutation, lifecycle governance, and control/storage. |
| Station cockpit | Inspect one component in detail. | Component cockpit with local subgraph, metrics, records, traces, artifacts, config, audit, and help. |
| Object microscope | Inspect one concrete record. | Trace, job, candidate, skill version, scanner finding, evaluation, artifact, broker decision, source item, or evolution transaction detail. |

Every level must answer the same diagnostic questions:

```text
What is happening?
Is it healthy, degraded, blocked, frozen, or unknown?
How fresh and complete is the telemetry?
What changed recently?
Where is work accumulating?
Which upstream inputs and downstream outputs are affected?
Which evidence, trace, job, or artifact proves the conclusion?
What is the safest next diagnostic or administrative action?
```

The UI must treat missing telemetry as a diagnostic state. A quiet component is not automatically healthy. It is healthy only when expected inputs, outputs, heartbeats, read-model freshness, and coverage signals are within policy bounds.


### 1.5 Observatory coverage matrix

The Observatory must expose every major SkillKernel domain through at least one system-level indicator, one subsystem-level diagnostic, one component cockpit, and one object-level drill-down.

| SkillKernel domain | System indicator | Subsystem lens | Component/object drill-down |
|---|---|---|---|
| Live OpenClaw capture | live capture health, event rate, source coverage | capture + bootstrap | hook matrix, session coverage, captured event detail |
| Historical ingestion | bootstrap progress, source yield, quarantine count | capture + bootstrap | import run, source item, parser finding, derived evidence |
| Redaction and taint | raw/redacted eligibility, taint pressure | capture + bootstrap | taint graph, redaction finding, revocation path |
| Raw-evidence vault | retained raw windows, declassification queue, raw-access denials, retention/revocation pressure | capture + bootstrap; autonomy + adjudication | raw vault record, declassification report, access audit, derived-data traversal |
| Evidence fidelity | fidelity distribution, degraded-autonomy count, `evidence_insufficient_for_autonomy` count | capture + bootstrap; learning + memory; autonomy + adjudication | source item, evidence packet, fidelity tag, unsupported decision family |
| Semantic adjudication | verdict count, confidence components, contradiction rate, re-adjudication rate | autonomy + adjudication | adjudication record, evidence bundle, LLM output, deterministic admissibility result |
| Autonomy orchestration | autonomous accept/reject/quarantine/canary/no-op rates, soft-threshold misses, fallback ladder progress | autonomy + adjudication; lifecycle governance | autonomy decision, threshold policy, calibration record, fallback action |
| Replay and canary corpus | synthesized replay episodes, intent-redaction quality, corpus coverage, canary eligibility | autonomy + adjudication; quality gates | replay episode, redacted intent, expected decision, trace window, canary result |
| Evidence and memory | evidence maturity, memory quarantine, diagnostic momentum | learning + memory | cluster, memory record, provenance path |
| Retrieval and indexing | embedding backlog, recall audit, lexical/vector health | learning + memory; runtime context | retrieval audit, embedding profile, exact-rerank example |
| Runtime broker | no-skill decisions, loaded/suppressed counts, shadowing | runtime context | broker decision, scoring waterfall, rendered hint |
| Topology operations | create/improve/compose/decompose candidate counts | topology design | candidate, SkillIR/SkillGraphIR diff, trial matrix |
| Skill package planning | package artifact count, adjunct request count, support-file risk | topology design; artifact mutation | artifact plan, manifest, ancillary file preview |
| Context compilation | context pressure, token-budget rejections, ignored-token waste | runtime context; artifact mutation | compiled `SKILL.md`, broker hint, token diff |
| Scanner/security | hard findings, bundle findings, harmful-capability warnings | quality gates | scanner finding, taint-to-artifact path, risk matrix |
| Evaluator/probes | regression budget, probe failure, canary readiness | quality gates | evaluation run, probe fixture, comparison trial |
| Deterministic writer | staged transactions, activation lock, manifest hash state | artifact mutation | transaction, file diff, manifest, rollback pointer |
| Activation/curation | active/archive/freeze/canary states, active budget | lifecycle governance | skill lifecycle, curation decision, canary result |
| Rollback/revocation | rollback candidates, derived-data revocation backlog | lifecycle governance | evolution transaction, revocation graph, post-rollback validation |
| Scheduler/jobs | ready/running/retrying/blocked jobs, oldest job age | control + storage | job, schedule, lease, attempt timeline |
| Model/embedding profiles | qualification state, timeout/error pressure | control + storage; quality gates | profile qualification, structured-output failure, embedding sanity probe |
| Postgres/pgvector | migration state, read-model freshness, index health | control + storage | DB health report, index status, materialized-view refresh |
| Audit/trace spine | audit chain health, trace correlation, action attribution | lifecycle governance; control + storage | trace, span graph, action audit, causal attribution |
| Observatory itself | live stream health, API latency, read-model age | control + storage | admin self-health, frontend error, sequence-gap record |

A domain missing from this matrix represents an implementation defect.

### 1.6 Operator success model

The Observatory exists so an operator can determine whether SkillKernel is working correctly and efficiently without reading database rows, tracing sidecar logs manually, or reconstructing pipeline state from disconnected dashboards. Every primary view must support three operator modes:

| Mode | Operator question | Required UI behavior |
|---|---|---|
| Health scan | “Is the system healthy?” | Show global state, stale telemetry, frozen components, blocked work, failed gates, and security/regression alerts within the first screen. |
| Bottleneck hunt | “Where is work slowing down or disappearing?” | Show input/output rates, queue age, conversion loss, rejected records, redaction loss, parser loss, gate failures, activation locks, and downstream impact by station and subsystem. |
| Causal investigation | “Why did this happen?” | Provide trace replay, provenance graph, evidence links, gate decisions, artifact diffs, policy decisions, and action attribution for the exact object under investigation. |

The interface must avoid ambiguous “green dashboards.” A component is healthy only when all required signals are fresh and its input/output contract is satisfied. A subsystem is healthy only when its internal stations move work from input to output at expected quality, latency, and loss bounds. The full system is healthy only when live capture, historical ingestion, evidence extraction, topology operations, context compilation, gates, activation, broker feedback, curation, scheduler, storage, and audit are all observable and coherent.

### 1.7 Efficiency and quality questions

The Observatory must make operational efficiency visible, not merely uptime. Each major view must support answering:

```text
Are we collecting enough data?
Are we losing too much data to redaction, parser failures, deduplication, or quarantine?
Are useful candidates being generated at the expected rate?
Are candidates being rejected for correct reasons?
Are skills improving measured outcomes rather than only increasing library size?
Are composed skills outperforming their components after context cost?
Are decomposed skills reducing false-positive loads and token waste?
Is the broker selecting fewer, better skills over time?
Are context-loaded artifacts staying semantically dense?
Are scanner/evaluator failures concentrated in one artifact class, model profile, executor profile, or operation type?
Are historical bootstrap results converging into useful evidence or only producing low-confidence noise?
Is storage/index/read-model health strong enough that the UI reflects reality?
```

These questions are exposed through diagnostic lenses, subsystem workcells, station cockpits, issue board entries, and baseline comparisons.

### 1.8 Required operator journeys

The Observatory must support the following operator journeys without requiring manual SQL, raw log inspection, filesystem browsing, or sidecar shell access.

| Journey | Starting surface | Required drill-down path | Outcome |
|---|---|---|---|
| Whole-system soak check | Overview graph and KPI ribbon | issue board → subsystem lens → station cockpit → object microscope | Operator can determine whether the entire pipeline is healthy, degraded, blocked, stale, or merely idle. |
| Candidate drought investigation | Topology candidate KPI or opportunity miner issue | capture/bootstrap → learning/memory → opportunity miner → rejected candidates | Operator can tell whether no skills are being created because the system lacks data, redaction removed signal, clustering failed, duplicates were suppressed, or candidates failed quality gates. |
| Context-pressure investigation | Context pressure lens | runtime context → broker → context compiler → skill detail → topology decomposition candidates | Operator can identify token waste, broad-skill shadowing, verbose compiled artifacts, false-positive loads, or unnecessary support-context exposure. |
| Harm/regression investigation | Security, regression, or canary issue | scanner/evaluator → broker replay → action attribution → rollback/revocation graph | Operator can identify whether a skill, memory, broker hint, tool failure, external skill, or user context caused a bad runtime outcome. |
| Historical bootstrap validation | Historical bootstrap lens | source inventory → parser results → taint/quarantine → evidence yield → seeded candidates | Operator can determine whether an existing deployment’s history was discovered, parsed, redacted, deduplicated, and converted into useful evidence. |
| Skill package inspection | Skill library or artifact mutation workcell | skill detail → SkillIR/SkillGraphIR → package planner → context compiler → manifest → scanner/evaluator | Operator can see why a skill exists, what files it contains, why each artifact is present, what can enter context, and what gates accepted it. |
| Autonomous adjudication audit | Autonomy issue, adjudication KPI, or topology decision | autonomy workcell → adjudication record → evidence bundle → deterministic checks → outcome/canary | Operator can see what the LLM decided, why it was trusted or rejected, which hard invariants applied, and which fallback ladder was used. |
| Evidence-fidelity investigation | Evidence fidelity lens or `evidence_insufficient_for_autonomy` issue | source inventory → raw-vault policy → evidence packet → decision family matrix → evidence-repair jobs | Operator can tell whether autonomy is blocked by insufficient semantic evidence, disabled raw retention, parser loss, redaction signal loss, or missing trajectory/transcript windows. |
| Replay-corpus validation | Replay/canary corpus KPI | retrieval log → raw/declassified source window → synthesized `redacted_user_intent` → replay trial → canary linkage | Operator can determine whether real telemetry became safe replay evidence autonomously and whether the resulting episode is trustworthy. |
| Administrative escalation investigation | Administrative escalation issue | escalation record → hard-boundary reason → attempted autonomous alternatives → affected object → safe next action | Operator can distinguish true authority-boundary escalation from an autonomy defect or soft-threshold deadlock. |
| Infrastructure health check | Control + storage workcell | scheduler/jobs → model/embedding profiles → storage/read models → Observatory self-health | Operator can determine whether SkillKernel itself is running, whether the dashboard is fresh, and whether UI telemetry is trustworthy. |

A journey is complete only when it exposes a deterministic explanation, supporting record links, affected objects, missing telemetry warnings, and safe next actions.

### 1.9 Usability and truth invariants

The Observatory must be visually impressive, but it is primarily a truth-preserving diagnostic instrument. These invariants apply to every page:

1. Every displayed aggregate has a drill-down path to supporting records or an explicit explanation that the value is sampled, redacted, unavailable, or derived from a bounded read model.
2. Every health state includes freshness, coverage, and confidence indicators. A green status without telemetry freshness is forbidden.
3. Every object page shows upstream cause, local processing state, downstream effects, audit links, and redaction/taint status.
4. Every graph edge represents a real relationship from a read model, provenance link, trace span, dependency edge, or catalog entry.
5. Every administrative action is visible as a normal audited sidecar action with policy result, idempotency key, linked job, and outcome.
6. Every page provides a plain-language diagnostic summary and a machine-readable reason-code panel.
7. Every empty state distinguishes healthy idleness, missing telemetry, disabled subsystem, permission restriction, and real data absence.
8. Every lens and filter is reflected in the URL so a testing observation can be shared and reproduced.
9. The UI never presents estimated dollar cost, model-price advice, or cost optimization recommendations.
10. The interface remains useful with animations disabled, WebGL unavailable, slow read models, disconnected live stream, or partial telemetry.
11. A semantic decision is not considered explainable until the UI can show its evidence-fidelity tier, LLM adjudication artifact when applicable, deterministic admissibility result, threshold policy version, fallback ladder, and downstream outcome.
12. Administrative escalation is presented as an exceptional authority-boundary state, not as the ordinary path for semantic uncertainty.


### 1.10 Live-update and render-stability invariant

The Observatory is a live diagnostic interface, not a periodically rebuilt report. When the operator is viewing a route, tab, subsystem, graph, station cockpit, chart, table, timeline, or object microscope, routine data updates must reconcile into the mounted UI tree without clearing the visible surface.

Required behavior:

```text
initial navigation mounts the selected route
live deltas patch existing entity records
background snapshots reconcile by stable identity
new entities are inserted
removed entities are removed
changed entities update in place
unchanged entities preserve object identity where practical
selection, viewport, zoom, scroll, expanded panels, filters, and open drawers remain stable
```

The implementation must avoid full-route remounts during ordinary telemetry refresh. The visible symptom to prevent is a periodic flash where station cards disappear, graphs re-layout from scratch, charts blank/reinitialize, and then the same components reappear. That behavior is a defect because it breaks operator focus and makes the dashboard feel like a polling report instead of a live control-room instrument.

Allowed full replacement cases:

| Case | Required behavior |
|---|---|
| User changes top-level route or primary tab | The old route body may unmount and the new route body may mount. Persistent shell, auth state, command palette, theme, and live connection remain stable. |
| User explicitly presses reload/reset view | Route may reload intentionally and must indicate that the operator requested it. |
| WebSocket sequence gap cannot be patched | Reload only the affected read model or route region where practical; show a self-health warning and preserve viewport/selection if the affected objects still exist. |
| Major API/schema incompatibility | Stop live patching, show incompatible-version state, and require reload or upgrade. |
| Graph topology genuinely changes | Insert/remove/re-layout affected nodes and edges; metric-only changes must not trigger graph reconstruction. |

Prohibited ordinary-refresh behavior:

```text
using snapshot_seq, Date.now(), lastUpdatedAt, or polling counters as React keys
clearing arrays to [] before replacing them with new data
showing a full-page spinner during background refetch when previous data exists
disposing and reinitializing charts every poll interval
recreating React Flow node/edge types inside render
re-running full graph layout for metric-only updates
resetting viewport, selection, expanded panels, scroll position, or filters on data refresh
invalidating broad query families when an entity-level patch is available
```

Stable identity is mandatory. Use domain identifiers as UI identity keys:

```text
component_id
subsystem_id
station_id
edge_id
trace_id
job_id
skill_id
skill_version_id
candidate_id
artifact_id
issue_id
import_run_id
source_item_id
evaluation_id
scanner_finding_id
broker_decision_id
evolution_transaction_id
```

Snapshot sequence numbers, timestamps, read-model refresh times, and polling counters are synchronization metadata. They are never React keys for visible operational components.

Every live surface must distinguish:

| State | UI behavior |
|---|---|
| initial loading | Skeleton or loading state is allowed because no prior data exists. |
| background syncing | Existing data remains visible; show subtle sync indicator. |
| stale | Existing data remains visible with stale/freshness warning. |
| degraded stream | Existing data remains visible; show sequence-gap/reconnect warning and reconcile safely. |
| unavailable | Show degraded/unavailable state only for affected region, not the entire application shell. |

The design goal is continuity: the operator must be able to stare at one station, chart, graph edge, or object timeline while values change around it without the UI blinking, losing focus, or resetting spatial memory.



### 1.11 Alignment with core SkillKernel architecture

The Observatory must mirror SkillKernel’s governing distinction between semantic autonomy and deterministic authority. The UI must show that the LLM can adjudicate meaning-heavy decisions while deterministic services retain control over hard invariants, filesystem writes, scheduler state, activation, rollback, scanner hard-denies, raw exposure policy, and audit.

The Observatory must expose the following core architecture surfaces as first-class diagnostic objects:

- evidence-fidelity tier and raw-vault/declassification state for each semantic decision family;
- LLM adjudication records, including evidence IDs, confidence components, contradiction flags, and structured verdicts;
- deterministic admissibility checks that accepted, rejected, narrowed, quarantined, or canaried the LLM verdict;
- soft-threshold policy versions, calibration support, threshold-deadlock findings, and fallback ladders;
- administrative escalation records, limited to hard authority boundaries and unresolved contradiction after autonomous fallback;
- replay/canary corpus episodes synthesized from real telemetry, including redacted intent, expected decision, provenance, and trial outcomes.


Observatory must model the real SkillKernel machine rather than an approximate dashboard abstraction. The UI presents the same architectural boundaries used by the SkillKernel implementation:

```text
OpenClaw-facing plugin capture
sidecar-owned ingestion and scheduler
Postgres autoskill schema and read models
pgvector-backed retrieval and recall audits
SkillIR and SkillGraphIR source-of-truth records
context compiler and token budget governor
runtime skill-context broker
scanner and evaluator gates
deterministic writer and activation locks
evolution transactions, rollback, revocation, and audit
```

The UI must not collapse these boundaries into generic status cards. A station, subsystem, issue, trace, or action visible in Observatory must correspond to a concrete SkillKernel component, read-model row, job, event, candidate, artifact, transaction, policy decision, or audited action.

The overview and drill-downs must make SkillKernel's four autonomous topology operations visible as first-class activity:

```text
create      = missing useful skill becomes a SkillIR candidate and staged package
improve     = existing skill version receives a guarded patch or support artifact change
compose     = repeatedly co-used skills become a higher-order SkillGraphIR workflow candidate
decompose   = broad or clunky skill splits into sharper successor skills
```

Observatory must also expose supporting lifecycle operations without conflating them with topology operations:

```text
retrieve, route, suppress, load, ignore, canary, freeze, archive, promote, merge, deduplicate, rollback, revoke, rescan, reevaluate
```

The UI is allowed to simplify visual presentation, but it must not simplify away causality. Every high-level statement must be traceable to an underlying source:

```text
health       -> component signals and freshness checks
flow         -> jobs/events/traces/read-model counters
candidate    -> evidence cluster, operation type, maturity state, and trials
skill change -> SkillIR/SkillGraphIR revision, artifact plan, manifest, gates, transaction
runtime load -> broker decision, context excerpt, selected/suppressed/no-skill rationale
failure      -> reason code, owner component, impacted objects, and safe next action
```

A beautiful graph that cannot explain why a station is green, red, idle, freshness-stale, or blocked is not acceptable. A plain diagnostic table that answers the question but is visually disconnected from the system map is also incomplete. Observatory must connect system-level orientation, subsystem reasoning, station detail, and object-level evidence into one coherent diagnostic flow.

---

## 2. Non-goals and boundary rules

The Observatory must not convert autonomy diagnostics into a hidden administrative-escalation queue. It may display administrative escalations, raw-vault policy denials, and threshold-deadlock findings, but ordinary replay intent synthesis, memory declassification, topology choice, context equivalence, and broker adjudication remain autonomous SkillKernel workflows when evidence fidelity and hard invariants permit them.


The web interface must not blur SkillKernel’s core architecture.

| Boundary | Rule |
|---|---|
| Autonomous control | The UI observes and requests actions. It does not bypass policy, scanner gates, evaluator gates, freeze state, or rollback semantics. |
| LLM usage | The UI does not trigger free-form maintenance LLM calls during rendering. If an operator initiates a job that normally uses the configured SkillKernel text profile, it is represented as a normal sidecar job and audited. |
| Cost analytics | The UI does not implement a direct dollar-cost tracker, price analyzer, model-price optimizer, or spend forecaster. It may display token counts, latency, retries, model-profile health, and invocation outcomes when already recorded by SkillKernel. |
| Raw content | The UI defaults to redacted excerpts and hashes. Raw transcript, memory, prompt, tool-result, or artifact content is visible only when configured and authorized. |
| Skill mutation | The UI does not write skill files. It calls existing sidecar action endpoints that stage deterministic transactions. |
| Scheduler | The UI does not create an alternate scheduler. It displays and controls the sidecar-owned scheduler through existing schedule/job APIs. |
| OpenClaw Cron | The UI does not depend on or manage OpenClaw Cron. If OpenClaw Cron evidence appears in historical/task records, it is shown as imported evidence only. |
| Skill Workshop | The UI does not depend on Skill Workshop. Similar concepts such as proposals, quarantine, and scanners are SkillKernel-native. |
| External observability | Grafana/Prometheus/OTel collectors may be used externally, but the Observatory must function without external dashboards. |
| Security scanner | The UI may display findings and trigger rescan jobs. It does not suppress hard scanner findings or whitelist unsafe artifacts without policy support. |

---

## 3. Architecture overview

### 3.1 Sidecar-hosted architecture

The web interface runs from the SkillKernel sidecar container.

```text
Browser
  ├─ loads static React app from sidecar
  ├─ authenticates using local token/session/mTLS/reverse-proxy identity
  ├─ calls /admin/api/v1/* for snapshots, queries, and guarded actions
  └─ subscribes to /admin/live for component/job/trace/skill updates

SkillKernel sidecar
  ├─ FastAPI admin API
  ├─ static frontend server
  ├─ WebSocket live stream, plus optional SSE read-only stream
  ├─ read-model service
  ├─ action gateway enforcing policy and audit
  ├─ notification bridge from internal event bus and Postgres LISTEN/NOTIFY
  └─ existing scheduler/job/evaluator/writer/broker services

Postgres autoskill schema
  ├─ source tables from core SkillKernel
  ├─ component catalog and read-model views
  ├─ materialized rollups for dashboard performance
  ├─ event notification/outbox table when required by the configured deployment
  └─ audit records for every administrative action
```

The admin API is a sidecar feature, not a separate deployment. The default bind address is loopback. Remote access requires explicit configuration through a private network, mTLS, or a trusted reverse proxy.

### 3.2 Recommended stack

| Layer | Technology | Reason |
|---|---|---|
| Backend HTTP/API | FastAPI | SkillKernel sidecar is Python; FastAPI provides type-hinted API construction and OpenAPI generation. |
| Live stream | WebSocket first; optional SSE read-only fallback | WebSocket supports bidirectional session control and efficient live updates. SSE is useful for one-way read-only streams and proxy-friendly dashboards. |
| API contract | OpenAPI 3.1 generated from FastAPI/Pydantic models | Keeps frontend types and API implementation aligned. |
| Frontend shell | React + TypeScript + Vite | Mature SPA stack with strong type safety and build performance. |
| Remote state | TanStack Query | Manages server state, caching, invalidation, retries, and background refresh. |
| Pipeline/graph UI | React Flow / `@xyflow/react` | Interactive nodes/edges, custom nodes, built-in MiniMap/Controls/Background, selection, zoom, pan, and edge types. |
| Graph layout | ELK.js | Advanced layered graph layout for pipeline, SkillGraphIR, component internals, and dependency topology. |
| Charts | Apache ECharts | Broad chart catalog, Canvas/SVG rendering, dynamic data, progressive rendering, heatmaps, Sankey, treemap, graph, timeline, funnel, and large-data support. |
| Visual effects | PixiJS overlay | GPU-accelerated canvas/WebGL/WebGPU particles, glow layers, and high-density animated flows without overloading React DOM. |
| Diff/JSON viewer | Monaco Editor | Read-only SkillIR, manifest, JSON, DDL, and compiled artifact diffs with editor-grade search and folding. |
| Styling | CSS variables + Tailwind or vanilla CSS modules | Use deterministic theme tokens; avoid coupling UI correctness to a design system service. |
| Icons | Lucide or local SVG icon set | Bundle locally; avoid external network calls. |

React Flow’s `ReactFlow` component is designed to render interactive nodes and edges, and its built-in MiniMap and Controls components support the requested overview and zoom/pan interaction model. Apache ECharts provides many chart types and can switch between Canvas and SVG rendering while supporting dynamic data updates and progressive rendering. PixiJS provides GPU-accelerated canvas rendering through WebGL/WebGL2/WebGPU-capable renderers. OpenTelemetry’s core model of traces, metrics, and logs supports the trace-spine view, while PostgreSQL `LISTEN`/`NOTIFY` can efficiently signal dashboard invalidations without adding a new message broker. See the reference section for authoritative links.

### 3.3 Data access principle

The UI reads **dashboard read models**, not raw operational tables directly.

Raw-vault records are never read directly by the frontend. The backend may expose a redacted preview, a declassification report, or a policy-denied placeholder. Authorized raw reveal uses a short-lived server-side reveal token, audited purpose, minimum-necessary scope, and explicit role checks; the live stream never carries raw-vault payloads.

```text
Core tables → dashboard views/materialized views → admin API → frontend
```

This prevents expensive ad hoc dashboard queries from disturbing autonomous processing. The UI may deep-link to raw records through bounded, paginated, policy-checked API endpoints when necessary.

### 3.4 Real-time principle

The live UI uses a snapshot-plus-delta model with stable entity reconciliation:

1. Browser loads an initial route snapshot with a monotonic `snapshot_seq`.
2. Browser normalizes snapshot entities by stable IDs.
3. Browser opens `/admin/live` WebSocket with `last_seq=snapshot_seq`.
4. Sidecar streams compact entity deltas.
5. Browser applies deltas through pure reducers that upsert, update, delete, or invalidate specific entities.
6. Browser periodically reconciles with a fresh snapshot by merging entities by stable ID.
7. Browser preserves unchanged object references where practical so memoized components and charts do not rebuild.
8. Browser shows background-sync state without replacing the visible route with loading UI.
9. If sequence gaps occur, the browser reloads the smallest affected read model and preserves local view state where possible.

Postgres `LISTEN`/`NOTIFY` payloads carry record IDs or invalidation keys, not large event bodies. Notification payloads never contain raw prompts, transcript content, secrets, artifacts, or other sensitive data. The sidecar fetches the details, enforces authorization/redaction, and emits UI-safe events.

Live deltas use explicit schema versions and monotonic sequence numbers. The frontend treats unknown delta schema versions as non-applicable, requests a fresh snapshot for the affected scope, and records a self-health warning. WebSocket messages are transport hints, not authoritative state; snapshots and bounded API reads remain authoritative.

A reconciliation cycle is not a render-reset cycle. The UI must not briefly clear visible content just because a five-second read-model refresh completed. Reconciliation updates the existing application state graph; it does not replace the mounted route tree, React Flow instance, chart instances, or cockpit component hierarchy unless a genuine navigation, topology, schema, or recovery event requires it.

Deltas are scoped:

| Delta scope | Example | Frontend handling |
|---|---|---|
| entity patch | station metric changed | Update only that entity and derived aggregate. |
| entity insert | new issue, job, candidate, trace event | Insert by stable ID without resetting lists or graph viewport. |
| entity delete/archive | issue resolved, skill archived | Remove or mark state transition; preserve unrelated state. |
| aggregate patch | subsystem health changed | Update aggregate and reason code without reloading child entities unless needed. |
| invalidation | evaluator summary stale | Refetch affected query key; keep previous visible data until replacement arrives. |
| topology change | new station, removed edge, skill graph changed | Recompute affected layout region; do not reset metrics-only nodes. |
| sequence gap | missed delta range | Reload affected read model, record self-health issue, preserve UI state where possible. |


---

## 4. User roles and access model

### 4.1 Roles

| Role | Capability |
|---|---|
| `viewer` | Read health, metrics, redacted events, dashboards, and non-sensitive summaries. Cannot trigger actions. |
| `operator` | Viewer permissions plus guarded actions: retry job, pause queue, resume queue, trigger dry-run import, trigger scan/evaluation, freeze skill, unfreeze skill, run broker calibration, request rollback. |
| `admin` | Operator permissions plus configuration inspection, token/profile qualification jobs, retention actions, dangerous rollback confirmation, and raw-content access when enabled. |
| `auditor` | Read-only access to audit, provenance, scanner findings, action attribution, and immutable manifests. |

A deployment may map all roles to one local admin token initially, but the API must be role-aware from the start.

Minimum permission matrix:

| Capability | viewer | auditor | operator | admin |
|---|---:|---:|---:|---:|
| View global health and redacted summaries | yes | yes | yes | yes |
| View audit/provenance/security records | limited | yes | yes | yes |
| View raw content when enabled | no | no | no | yes |
| Trigger safe diagnostic jobs | no | no | yes | yes |
| Retry/cancel eligible sidecar jobs | no | no | yes | yes |
| Freeze/unfreeze skill or operation class | no | no | yes | yes |
| Request rollback | no | no | yes | yes |
| Confirm destructive revocation/retention action | no | no | no | yes |
| Change Observatory configuration | no | no | no | yes |

The backend enforces permissions. The frontend hides unauthorized actions only as a usability feature.

### 4.2 Authentication and binding

Default configuration:

```yaml
web_admin:
  enabled: true
  bind_host: "127.0.0.1"
  bind_port: 8757
  base_path: "/admin"
  auth:
    mode: "bearer_token"
    token_env: "SKILLKERNEL_ADMIN_TOKEN"
  raw_content:
    enabled: false
  diagnostics:
    issue_board_enabled: true
    subsystem_lenses_enabled: true
    playbooks_enabled: true
    telemetry_staleness_warning_seconds: 30
    telemetry_staleness_degraded_seconds: 120
  csrf:
    enabled: true
  cors:
    allowed_origins: []
```

Production options:

```yaml
web_admin:
  bind_host: "0.0.0.0"
  bind_port: 8757
  auth:
    mode: "mTLS_or_reverse_proxy_header"
    trusted_proxy_cidrs:
      - "10.0.0.0/8"
    identity_header: "X-SkillKernel-User"
    roles_header: "X-SkillKernel-Roles"
  tls:
    enabled: true
    cert_file: "/run/secrets/skillkernel-admin.crt"
    key_file: "/run/secrets/skillkernel-admin.key"
```

The admin interface must not be publicly exposed without an explicit operator decision. Health liveness may be unauthenticated only when configured; readiness, metrics, records, traces, jobs, actions, artifacts, and raw-content endpoints require authentication.

### 4.3 Administrative action confirmation

High-impact actions require confirmation:

| Action | Confirmation |
|---|---|
| Freeze/unfreeze autonomous apply | modal confirmation with reason text |
| Rollback skill/evolution transaction | typed transaction ID and reason |
| Start historical import, not dry-run | scope preview confirmation |
| Delete/revoke retained data | typed source/candidate/skill ID and reason |
| Force retry after hard scanner failure | not allowed unless policy explicitly supports exception workflow |
| Raw content reveal | role check, reason, short-lived reveal token, audit record |
| Change raw-vault retention or exposure policy | typed policy ID and reason |
| Change threshold policy outside normal calibration workflow | typed policy ID and reason |
| Resolve administrative escalation | hard-boundary reason, disposition, and linked audit record |

All actions write `autoskill.admin_action_audit` and link to the underlying `autoskill.audit_log`, `autoskill.autonomy_decisions`, `autoskill.administrative_escalation_events`, or evolution transaction.

---

## 5. Component map

### 5.1 Pipeline stations

The main overview renders these first-class stations. Station IDs are stable API identifiers.

| Station ID | Display name | Purpose |
|---|---|---|
| `openclaw_live_capture` | OpenClaw live capture | Plugin hook and SDK-event capture from active OpenClaw sessions. |
| `historical_ingestion` | Historical bootstrap | Discovery and ingestion of existing transcripts, trajectories, memory/context files, task records, and existing skills. |
| `redaction_taint` | Redaction + taint | Sensitive-content reduction, taint propagation, source confidence, storage eligibility. |
| `raw_evidence_vault` | Raw-evidence vault | Encrypted full-fidelity evidence retention, raw/declassified access policy, raw access audit, retention, revocation, and derived-data traversal. |
| `evidence_fidelity` | Evidence fidelity | Classifies records as `raw_vault_linked`, `declassified_summary`, `redacted_derivative`, `metadata_only`, or `hash_only` and declares which decision families they can support. |
| `spool_ingest` | Spool + ingest | Local plugin spool, batch forwarding, sidecar ingest API, idempotency, normalization. |
| `event_normalization` | Event normalization | Converts live/historical records into canonical events, chunks, spans, and evidence inputs. |
| `evidence_memory` | Evidence + memory | Evidence extraction, memory derivation, provenance, maturity ladder, poisoning defenses. |
| `semantic_adjudication` | LLM semantic adjudication | Structured LLM verdicts for intent reconstruction, replay intent synthesis, memory declassification, topology choice, context equivalence, broker misses, and ambiguous evidence. |
| `autonomy_orchestrator` | Autonomy decision orchestrator | Combines LLM verdicts, evidence fidelity, hard invariants, soft thresholds, calibration, reversibility, and fallback ladders into autonomous next actions. |
| `replay_corpus` | Replay + canary corpus | Converts real telemetry into safe replay/canary episodes with redacted intent, expected decisions, provenance, and trial outcomes. |
| `retrieval_indexing` | Retrieval + indexing | Lexical/vector indexing, pgvector status, re-embedding, exact rerank, graph expansion indexes. |
| `broker_runtime` | Runtime broker | Skill-context selection, no-skill decision, shadowing control, context hint rendering. |
| `opportunity_mining` | Opportunity miner | Candidate discovery from clustered evidence, repeated workflows, failures, corrections, co-use, partial use. |
| `topology_operations` | Topology operations | Create, improve, compose, decompose, merge, archive, promote, rollback, freeze decisions. |
| `skill_ir_graph_ir` | SkillIR / SkillGraphIR | Canonical skill representation, graph workflows, version state, contracts, effect signatures. |
| `artifact_planner` | Skill package planner | Decides whether ancillary files are beneficial for a skill package. |
| `context_compiler` | Context compiler | Compiles SkillIR to compact AI-facing `SKILL.md`, broker hints, and context excerpts under token budgets. |
| `scanner_security` | Scanner + security | Static, semantic, capability, harmful-skill, guidance-injection, artifact, and bundle scanning. |
| `evaluator_probes` | Evaluator + probes | Target, regression, adversarial, canary, benchmark, and counterfactual trials. |
| `deterministic_writer` | Deterministic writer | Path-contained staging, manifest hashing, file writes, activation locks, transactionality. |
| `activation_curation` | Activation + curation | Active/archive/promotion lifecycle, active budget, utility rollups, skill technical debt. |
| `canary_rollback` | Canary + rollback | Runtime canary observation, rollback, freeze, derived-data revocation. |
| `administrative_escalation` | Administrative escalation | Exceptional authority-boundary events, attempted autonomous alternatives, escalation reason codes, and resolution state. |
| `scheduler_jobs` | Scheduler + jobs | Sidecar-owned schedules, jobs, leases, attempts, backoff, queue pressure. |
| `model_embedding` | Model + embedding profiles | Configured text LLM profile, embedding profile, qualification gates, invocation health. |
| `storage_db` | Postgres + pgvector | DB health, migrations, index health, materialized views, partitions, retention. |
| `audit_trace` | Audit + trace spine | Correlation across events, jobs, actions, model calls, evaluations, artifacts, and mutations. |
| `administrative_action_gateway` | Administrative action gateway | Role checks, confirmations, idempotency, guarded action dispatch, and action audit links. |
| `observatory_admin` | Observatory self-health | Admin API, frontend serving, live stream, read-model freshness, browser diagnostics, and dashboard performance. |

### 5.2 Subsystem workcells

Subsystem workcells provide the required intermediate zoom level between the global overview and individual station cockpits. A workcell is a coherent set of stations that together perform one larger function.

| Subsystem ID | Display name | Stations |
|---|---|---|
| `capture_bootstrap` | Capture + bootstrap workcell | `openclaw_live_capture`, `historical_ingestion`, `redaction_taint`, `spool_ingest`, `event_normalization` |
| `learning_memory` | Learning + memory workcell | `evidence_memory`, `evidence_fidelity`, `semantic_adjudication`, `retrieval_indexing`, `opportunity_mining` |
| `autonomy_adjudication` | Autonomy + adjudication workcell | `raw_evidence_vault`, `evidence_fidelity`, `semantic_adjudication`, `autonomy_orchestrator`, `replay_corpus`, `administrative_escalation`, `model_embedding`, `audit_trace` |
| `runtime_context` | Runtime context workcell | `retrieval_indexing`, `broker_runtime`, `context_compiler`, `canary_rollback` |
| `topology_design` | Topology design workcell | `opportunity_mining`, `topology_operations`, `skill_ir_graph_ir`, `artifact_planner` |
| `quality_gates` | Quality gates workcell | `scanner_security`, `evaluator_probes`, `replay_corpus`, `model_embedding` |
| `artifact_mutation` | Artifact mutation workcell | `artifact_planner`, `context_compiler`, `scanner_security`, `evaluator_probes`, `deterministic_writer`, `activation_curation`, `canary_rollback` |
| `lifecycle_governance` | Lifecycle governance workcell | `activation_curation`, `canary_rollback`, `autonomy_orchestrator`, `administrative_escalation`, `audit_trace`, `administrative_action_gateway` |
| `control_storage` | Control + storage workcell | `scheduler_jobs`, `model_embedding`, `storage_db`, `audit_trace`, `observatory_admin` |

Each subsystem page shows:

- local directed subgraph;
- subsystem health rollup;
- station health cards;
- upstream/downstream dependency summary;
- throughput, backlog, oldest-item age, and conversion rates;
- failure and freeze reasons by station;
- top traces currently moving through the subsystem;
- policy gates relevant to that subsystem;
- diagnostic playbook links;
- guarded subsystem actions that dispatch normal sidecar jobs.

A subsystem can be degraded even when every station reports `healthy` if the workcell-level conversion rate, data freshness, coverage, or output quality is outside bounds. Example: capture, redaction, and normalization may each be individually healthy while opportunity mining produces no viable candidates because redaction policy is stripping all task-specific structure. That condition belongs on the capture/bootstrap and learning/memory subsystem pages.

### 5.3 Station health model

Each station exposes the same health envelope:

```json
{
  "component_id": "context_compiler",
  "display_name": "Context compiler",
  "health": "healthy",
  "mode": "active",
  "freeze_state": "none",
  "last_success_at": "2026-06-03T14:26:13Z",
  "last_error_at": null,
  "input_rate_1m": 14.2,
  "output_rate_1m": 13.9,
  "queue_depth": 7,
  "backlog_seconds": 18.4,
  "p50_latency_ms": 122,
  "p95_latency_ms": 510,
  "error_rate_15m": 0.003,
  "warning_count": 2,
  "blocked_count": 0,
  "token_pressure": 0.42,
  "risk_pressure": 0.09,
  "evaluator_pressure": 0.18,
  "details_url": "/admin/components/context_compiler"
}
```

Health states:

| State | Meaning |
|---|---|
| `healthy` | Processing within expected bounds. |
| `degraded` | Latency, backlog, warning, or retry pressure elevated. |
| `blocked` | Required dependency unavailable or hard policy gate blocking work. |
| `frozen` | Component or skill lifecycle is intentionally frozen. |
| `offline` | Component heartbeat missing or disabled. |
| `unknown` | No sufficient telemetry yet. |

Mode values:

```text
active | read_only | dry_run | paused | maintenance | disabled
```

Each station also exposes a data-quality envelope:

```json
{
  "component_id": "opportunity_mining",
  "telemetry_freshness_seconds": 4,
  "expected_input_rate_1m": 6.0,
  "observed_input_rate_1m": 5.8,
  "output_conversion_rate_15m": 0.31,
  "sampling_rate": 1.0,
  "redaction_level": "default",
  "raw_content_available": false,
  "read_model_age_seconds": 3,
  "coverage_state": "complete",
  "missing_signals": []
}
```

Coverage states:

```text
complete | partial | missing | intentionally_disabled | unknown
```

A component with missing, stale, sampled, or partial telemetry must display that condition directly in the header. The UI must not hide data-quality uncertainty behind an ordinary green health state.

### 5.4 Edge metrics

Edges between stations show flow:

```json
{
  "edge_id": "evidence_memory_to_opportunity_mining",
  "from": "evidence_memory",
  "to": "opportunity_mining",
  "event_rate_1m": 8.7,
  "job_rate_1m": 0.4,
  "error_rate_15m": 0.001,
  "backpressure": 0.13,
  "oldest_item_age_seconds": 41,
  "dominant_item_kind": "evidence_cluster"
}
```

Edge width encodes throughput. Edge pulse speed encodes rate. Edge color/status encodes health. A high backlog edge must visibly thicken and slow, not simply turn red.

### 5.5 Component signal contract

Every station must publish a consistent diagnostic contract. The UI cannot infer health from arbitrary logs. Each station status snapshot contains:

```json
{
  "component_id": "context_compiler",
  "health": "healthy",
  "mode": "active",
  "freeze_state": "none",
  "input": {"rate_1m": 14.2, "backlog": 3, "oldest_age_seconds": 18},
  "processing": {"rate_1m": 13.9, "p50_ms": 184, "p95_ms": 912, "error_rate_1m": 0.0},
  "output": {"rate_1m": 13.7, "success_rate_1m": 0.986, "reject_rate_1m": 0.014},
  "quality": {"data_completeness": 0.998, "coverage": "complete", "freshness_seconds": 2},
  "dominant_issue_id": null,
  "trace_sample_ids": ["tr_01jz4z3gqfq8s4bkrcm5r6y7pp"],
  "captured_at": "2026-06-03T16:42:17Z"
}
```

Required signal classes:

| Signal class | Purpose |
|---|---|
| Input | Work arriving at the station: rate, backlog, oldest item, upstream coverage. |
| Processing | Latency, errors, retries, resource pressure, worker state. |
| Output | Work emitted: success, rejection, quarantine, downstream handoff. |
| Quality | Data completeness, freshness, confidence, coverage, and policy eligibility. |
| Control | mode, freeze state, maintenance state, paused state, activation lock. |
| Evidence | trace samples, issue links, audit links, and representative object IDs. |

A station missing any required signal class reports `unknown` or `degraded`, never `healthy`.

### 5.6 Pipeline invariants

The Observatory evaluates deterministic invariants that reveal invisible failures:

| Invariant | Failure shown as |
|---|---|
| Captured events eventually reach ingest, quarantine, or explicit drop records. | invisible loss / capture gap |
| Historical source items eventually reach parsed, skipped, quarantined, or revoked state. | bootstrap stall |
| Evidence clusters feeding topology candidates preserve provenance to source records. | provenance break |
| Candidate decisions have explicit accept/reject/quarantine/watch reasons. | decision opacity |
| LLM-backed proposals have structured-output validation records. | proposal opacity |
| Context compiler outputs have token counts and semantic-equivalence results. | context blind spot |
| Scanner/evaluator gates have complete coverage before writer activation. | unsafe activation risk |
| Writer transactions have manifests, hashes, and rollback pointers. | artifact integrity risk |
| Activated versions have broker/canary visibility. | runtime feedback gap |
| Rollback/revocation traverses derived memories, embeddings, artifacts, and caches. | derived-data leak |
| Dashboard read models are fresher than their configured staleness budget. | stale dashboard |

Invariant failures create issue-board entries and appear in relevant subsystem lenses.

### 5.7 Status grammar and visual semantics

Every status badge and graph decoration uses a shared grammar so operators do not need to relearn meanings across pages.

| Dimension | Values | Visual treatment | Diagnostic meaning |
|---|---|---|---|
| Health | `healthy`, `degraded`, `blocked`, `frozen`, `offline`, `unknown` | ring state, label, icon, tooltip | Whether the component is functioning within policy. |
| Mode | `active`, `read_only`, `dry_run`, `paused`, `maintenance`, `disabled` | small mode pill | Whether the component is expected to mutate, observe only, or remain inactive. |
| Coverage | `complete`, `partial`, `missing`, `intentionally_disabled`, `unknown` | coverage stripe and data-quality badge | Whether expected inputs and outputs are visible. |
| Freshness | `fresh`, `stale`, `expired`, `not_applicable` | timestamp badge and pulse/decay indicator | Whether the displayed read model is recent enough to trust. |
| Severity | `info`, `warning`, `degraded`, `blocked`, `security`, `regression`, `freeze` | issue-card class, icon, priority order | How urgently the operator must investigate. |
| Confidence | `high`, `medium`, `low`, `insufficient` | confidence meter | How much evidence backs the conclusion. |

The status header for every station, subsystem, issue, skill, job, trace, and profile displays this minimum tuple:

```text
health | mode | freshness | coverage | confidence | dominant_reason_code
```

The dominant reason code links to the exact issue, trace, metric, job, policy gate, scanner finding, evaluator result, or stale-telemetry record responsible for the status.

### 5.8 Diagnostic reason-code catalog

Reason codes are stable identifiers used across the UI, API, tests, and runbooks. Examples:

```text
CAPTURE_NO_EVENTS
CAPTURE_SPOOL_BACKLOG
HISTORICAL_PARSER_FAILURE
REDACTION_SIGNAL_LOSS
EVIDENCE_CLUSTER_LOW_CONFIDENCE
RETRIEVAL_RECALL_AUDIT_FAILED
BROKER_FALSE_POSITIVE_LOAD_RATE
BROKER_MISSED_RELEVANT_SKILL
CONTEXT_TOKEN_BUDGET_EXCEEDED
SCANNER_HARD_FINDING
EVALUATOR_REGRESSION_BUDGET_EXCEEDED
WRITER_ACTIVATION_LOCKED
CANARY_FAILURE
ROLLBACK_REVOCATION_BACKLOG
SCHEDULER_LEASE_STALE
MODEL_PROFILE_UNQUALIFIED
EMBEDDING_DIMENSION_MISMATCH
RAW_VAULT_ACCESS_DENIED
EVIDENCE_INSUFFICIENT_FOR_AUTONOMY
REPLAY_INTENT_SYNTHESIS_LOW_CONFIDENCE
SEMANTIC_ADJUDICATION_CONTRADICTION
AUTONOMY_SOFT_THRESHOLD_DEADLOCK
AUTONOMY_POLICY_CALIBRATION_STALE
ADMINISTRATIVE_ESCALATION_REQUIRED
READ_MODEL_STALE
LIVE_STREAM_SEQUENCE_GAP
OBSERVATORY_FRONTEND_ERROR
```

Each reason code has a short explanation, affected subsystem, likely causes, first diagnostic views, and safe actions. The issue board and playbooks use the same reason-code catalog.

---

## 6. Main overview page

### 6.1 Layout

The default route `/admin` opens the Observatory overview.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ SkillKernel Observatory        Health: HEALTHY       Live  Replay  Settings │
├──────────────────────────────────────────────────────────────────────────────┤
│ KPI Ribbon + Issue Board                                                      │
│ Active skills | candidates | jobs | queue | failures | context pressure | risk │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                 Interactive Assembly-Line Graph + Subsystem Lanes             │
│                                                                              │
│      [Live] → [Hist] → [Redact/Vault] → [Ingest] → [Evidence] → [Adjudicate] │
│         \                                                ↘                    │
│          └──────────────→ [Broker] → [Orchestrate] → [Runtime]               │
│                         [Mine] → [Create/Improve/Compose/Decompose]           │
│                                  → [SkillIR] → [Compile] → [Scan] → [Eval]    │
│                                  → [Write] → [Activate] → [Canary/Rollback]   │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ Bottom drawer: selected subsystem/station / live events / warnings / actions  │
└──────────────────────────────────────────────────────────────────────────────┘
```

The graph must support:

- pan, zoom, fit-to-screen, minimap, and station search;
- grouped lanes: ingestion, intelligence, artifact pipeline, runtime, governance;
- health overlay mode;
- throughput overlay mode;
- latency overlay mode;
- security-risk overlay mode;
- context-pressure overlay mode;
- topology-operation overlay mode;
- historical-bootstrap overlay mode;
- click station → station cockpit;
- click edge → flow detail panel;
- click particle → trace/job/candidate detail when backed by a concrete record;
- timeline scrubber for replay mode.


### 6.1.1 Overview centerpiece visual-design contract

The main overview graph is the visual centerpiece of Observatory. It must not look like an unfinished developer diagram or a default library demo. The graph is the operator’s command-room map of the SkillKernel machine, so it needs a deliberate visual language that is polished, legible, and consistent with the rest of the UI.

Required aesthetic goals:

- the overview canvas feels like a live operations console, not a static flowchart;
- nodes look like instrumented stations with meaningful state, not plain boxes;
- edges look like governed material flow between stations, not generic connector lines;
- labels are integrated visual chips with clear hierarchy, not floating unstyled text;
- motion communicates real flow, pressure, or state transition, not decorative noise;
- severity, throughput, context pressure, security risk, and freshness are visually distinguishable without overwhelming the operator;
- the graph uses the same typography, spacing, radius, elevation, border, color, and shadow tokens as the rest of the admin UI;
- the graph remains useful and attractive in light, dark, reduced-motion, and low-power modes.

Required visual treatment:

| Element | Required treatment |
|---|---|
| Canvas background | Layered command-surface background with subtle grid, lane rails, depth gradients, and clear contrast against nodes and edges. |
| Subsystem lanes | Distinct horizontal or grouped workcell regions with soft boundaries, lane titles, health badges, and throughput/backpressure summary. |
| Station nodes | Custom React Flow nodes with compact metric cells, status halo, station icon/glyph, freshness indicator, queue/latency/error mini-readouts, and selected/hover/focus states. |
| Station status | Consistent shape/color/text grammar for healthy, degraded, blocked, frozen, offline, and unknown health states; stale data is communicated through the freshness badge. |
| Edges | Custom semantic edges with direction, stable labels, purpose chips, flow thickness/intensity, state-specific stroke style, and smooth selection/hover emphasis. |
| Edge labels | Readable label chips pinned to the edge path, with short purpose text and optional metric badge. Labels must not collide excessively at default zoom. |
| Animated flow | Subtle pulse/ribbon/particle movement representing actual event/job/candidate flow. Animation must be data-backed and rate-limited. |
| Event particles | Optional PixiJS particles for traces, jobs, candidates, scanner findings, activation, rollback, freeze, and quarantine. Particles augment the graph but do not carry exclusive meaning. |
| KPI integration | The KPI ribbon and issue board visually relate to the graph through shared colors, reason codes, and selected-object context. |
| Focus state | Selecting a node or edge dims unrelated flow, highlights upstream/downstream dependencies, and opens a bottom or side details panel without resetting viewport. |
| Empty/idle state | A quiet system still looks intentional: subdued lanes, explicit idle badges, and no misleading fake activity. |
| Error/degraded state | Degraded stations and blocked edges are visually prominent enough to notice immediately, with direct drill-down affordances. |

Default React Flow nodes, default bezier edges, unthemed labels, plain gray boxes, library-demo styling, and raw debug layouts are not acceptable for the main overview. The implementation may use React Flow as the interaction substrate, but the visual system must be custom-designed for Observatory.

### 6.1.2 Performance-safe visual fidelity

The overview must have a high-fidelity visual treatment without becoming a resource hog. Use the right rendering layer for each responsibility:

```text
React Flow / SVG / DOM = interaction, selection, accessible nodes, edge geometry, labels, focus, menus
CSS = theme tokens, node polish, transitions, shadows, gradients, reduced-motion behavior
PixiJS canvas/WebGL/WebGPU = optional high-density particles, glow layers, flow effects, burst effects
ECharts = charts and dense metric panels outside the central structural graph
```

Performance rules:

- graph structure is mounted once per route and updated by stable entity identity;
- metric-only updates patch node/edge data in place and do not re-run layout;
- expensive glow, blur, particle, and shadow effects have adaptive quality levels;
- particles are pooled/reused and capped by viewport and device capability;
- animations run through `requestAnimationFrame` and pause when the tab is hidden;
- offscreen or hidden subsystem effects are disabled or sampled;
- low-priority high-frequency events aggregate into edge intensity instead of spawning one particle per event;
- reduced-motion mode disables particle motion, edge pulses, camera fly-throughs, and nonessential transitions;
- low-power mode disables PixiJS effects and uses static CSS/SVG status cues;
- the dashboard never uses animation to represent state that is not also represented by text, shape, label, tooltip, or drill-down data.

Target performance envelope:

| Scenario | Target |
|---|---|
| Initial overview render with warm read models | under 3 seconds on a normal local deployment |
| Pan/zoom on expected graph size | visually smooth, with no sustained frame drops under ordinary load |
| Five-second metric refresh | no graph blanking, no full-route flash, no viewport reset, no broad remount |
| Particle overlay active | does not materially affect core dashboard interactivity |
| WebGL unavailable | graph remains complete and polished using DOM/SVG/CSS fallbacks |
| Reduced-motion enabled | all meaning remains visible without motion |

Visual quality and performance are both release criteria. The correct outcome is a polished live map that feels rich because it accurately visualizes the machine, not because it burns CPU/GPU on unrelated decoration.


### 6.1.3 Overview centerpiece acceptance rubric

The overview graph is complete only when it satisfies all of these visual and diagnostic checks:

| Check | Requirement |
|---|---|
| Visual finish | The graph uses custom nodes, custom edges, custom labels, subsystem lanes, cohesive spacing, polished hover/focus/selection states, and theme tokens. No default React Flow styling is visible in the shipped centerpiece. |
| Information density | At default zoom, every station exposes status, freshness, backlog or throughput, and one station-specific metric without requiring a click. |
| Legibility across zoom | At far zoom, subsystem lanes and station status remain legible. At normal zoom, edge labels and station metrics are readable. At close zoom, station internals provide useful diagnostic cues without opening a cockpit. |
| Diagnostic honesty | Visual intensity reflects real data. Glow, pulse, particle rate, edge thickness, and status halos are data-backed and degrade to static equivalents when motion is disabled. |
| Spatial memory | Stable station positions are preserved across live updates. Layout changes occur only when topology changes or the operator requests relayout. |
| Clutter control | Labels, particles, and metric badges use collision avoidance, aggregation, dimming, and lens-based filtering so busy systems remain understandable. |
| Performance envelope | The graph remains responsive with representative high-load fixtures, reduced-motion mode, low-power mode, and WebGL unavailable. |
| Drill-down continuity | Clicking a station, edge, particle, issue, or metric opens the relevant cockpit/object without losing overview viewport state. |
| Accessibility | Keyboard navigation, focus rings, non-color severity encoding, text alternatives, and reduced-motion behavior work in the centerpiece. |
| Thematic coherence | The graph feels like the central control-room surface of the same application, not an embedded third-party demo. |

The centerpiece must be designed and tested with seeded states that cover healthy idle, busy throughput, historical bootstrap, candidate drought, scanner hard finding, evaluator regression, context pressure, broker shadowing, rollback/freeze, stale telemetry, stream gap, low-power mode, and WebGL fallback.

Implementation teams must treat the overview graph as a product surface with visual acceptance criteria, not as a temporary debugging diagram. The graph is the first thing operators use to decide whether SkillKernel is functioning as a system.

### 6.2 KPI ribbon

The KPI ribbon shows bounded, high-signal metrics:

| KPI | Description |
|---|---|
| Global health | Rollup of component health, freeze state, scheduler state, DB state, scanner/evaluator state. |
| Active skills | Count by active, archived, frozen, canary, rollback-needed. |
| Topology candidates | Create/improve/compose/decompose candidates by maturity and status. |
| Current autonomous operations | Running jobs by operation type and stage. |
| Queue pressure | Jobs ready/running/retrying/blocked plus oldest job age. |
| Historical bootstrap | Sources discovered/importing/done/failed/quarantined. |
| Context pressure | Runtime skill tokens, broker hint tokens, ignored-skill token waste, over-budget rejections. |
| Scanner pressure | Open hard findings, quarantined artifacts, harmful-capability flags, guidance-injection findings. |
| Evaluator pressure | Failing target probes, regression violations, canary failures. |
| Broker quality | No-skill decisions, shadowing detections, false-positive loads, missed-skill cases. |
| Storage health | DB migration state, pgvector index state, materialized view freshness, retention backlog. |
| Model/profile health | Text LLM and embedding profile qualification status, recent error rate, retry pressure. |

No KPI may display dollar cost. Token counts and context pressure are allowed because they support context management and performance without implementing cost analysis.

### 6.3 Issue board and diagnostic lenses

The overview includes an issue board beside or below the graph. It aggregates actionable conditions across the system.

Issue card fields:

```json
{
  "issue_id": "iss_01jz4z6s8n9f8r6ayz0k9m0f8q",
  "severity": "warning",
  "scope": "runtime_context",
  "title": "Broker false-positive load rate elevated",
  "symptom": "False-positive skill loads exceeded policy for 3 consecutive windows.",
  "likely_causes": ["broad skill trigger", "stale archived-skill embedding", "overlapping external skill"],
  "evidence_links": ["/admin/broker/decisions/brd_01jz4z6v0wq2m0n4bks2y7gk1c"],
  "safe_actions": ["run broker dry-run", "open shadowing graph", "trigger retrieval calibration"]
}
```

Issue severities:

```text
info | warning | degraded | blocked | security | regression | freeze
```

Diagnostic lenses change the whole dashboard without changing the underlying data. Required lenses:

| Lens | Reveals |
|---|---|
| Health | Component and subsystem health, freezes, offline states, blocked gates. |
| Throughput | Event/job/candidate/artifact flow, queue depth, backpressure, oldest item age. |
| Latency | Per-station processing latency, slow traces, read-model freshness, scheduler lag. |
| Data quality | Coverage, sampling, stale telemetry, redaction level, missing signals, parser failures. |
| Context pressure | Runtime skill tokens, broker hint tokens, support-context usage, ignored-skill waste, token-budget rejections. |
| Security | Scanner findings, taint propagation, guidance injection, capability risk, raw-content exposure. |
| Evaluation | Probe failures, regression budgets, canary outcomes, benchmark adapter status. |
| Topology | Create/improve/compose/decompose candidates, library shape, co-use, shadowing, decomposition pressure. |
| Historical bootstrap | Source coverage, import progress, parser failure, evidence yield, historical candidate seeding. |
| Storage | DB health, pgvector indexes, materialized-view age, retention backlog, slow read-model queries. |

The selected lens is included in the URL query string so operators can share exact diagnostic views.

### 6.4 Live particles

Animated particles are optional visual elements backed by real events. Particle classes:

| Particle | Represents |
|---|---|
| small point | event or chunk |
| square | job |
| diamond | candidate |
| hexagon | SkillIR revision or SkillGraphIR node |
| ring | evaluation/probe run |
| shield | scanner finding or security gate |
| bolt | rollback/freeze action |
| glow burst | activation or promotion |
| dimmed particle | redacted/quarantined/discarded item |

The particle overlay is rendered with PixiJS. React Flow renders the structural graph. The PixiJS overlay tracks React Flow viewport transforms so particles align with node/edge positions.

Reduced-motion mode disables particles and uses static status bands.

### 6.5 System fitness panel

The overview includes a compact fitness panel that converts the machine state into operator-readable dimensions without hiding details:

| Dimension | Inputs | Display |
|---|---|---|
| Data fitness | live coverage, historical yield, redaction loss, parser loss, taint/quarantine | coverage gauge and loss waterfall |
| Learning fitness | evidence maturity, candidate yield, genericity rejection, duplicate suppression | maturity funnel and candidate trend |
| Runtime fitness | broker precision, no-skill rate, false-positive loads, missed skills, context waste | broker scorecard and context treemap |
| Gate fitness | scanner coverage, evaluator pass/fail, regression budget, stale probes | gate matrix |
| Artifact fitness | writer success, manifest integrity, activation locks, rollback availability | transaction lane |
| Governance fitness | active budget, archive/promotion health, freezes, canary health, revocation backlog | lifecycle heat strip |
| Infrastructure fitness | scheduler, DB, pgvector, read models, live stream, model/embedding profiles | control-plane panel |

The panel is not a single opaque score. Each dimension is clickable and decomposes into supporting signals, issue entries, and trace examples.

### 6.6 Global search, command palette, and time controls

The overview includes a global search and command palette available from every page. It supports direct lookup by:

```text
skill name
skill_id
version_id
trace_id
job_id
evaluation_id
scanner finding ID
candidate_id
artifact_id
import_run_id
source item fingerprint
reason code
component_id
subsystem_id
audit action ID
manifest hash
```

Search results are grouped by object type, permission-filtered, and redacted by default. Selecting a result opens the object microscope or the most specific available cockpit.

The time control bar supports:

```text
live
paused snapshot
last 15 minutes
last hour
last 24 hours
historical import run
custom absolute range
compare current window against baseline window
```

Comparison mode is required for soak testing. It lets operators answer whether the system is improving, regressing, or merely changing. Comparison summaries cover throughput, latency, candidate yield, acceptance/rejection rates, context pressure, scanner/evaluator failures, broker quality, storage freshness, and issue count.

### 6.7 Empty, idle, and partial-data states

The overview and every cockpit must distinguish:

| State | Meaning | Required UI treatment |
|---|---|---|
| Healthy idle | No work is expected and component heartbeats/read models are fresh. | Calm idle state with last-success timestamp. |
| Data absent | No records exist for the selected filters/time range. | Empty-state message with filter/time controls. |
| Telemetry missing | Expected source is silent or not reporting. | Warning state with missing-signal list. |
| Permission hidden | Records exist but the actor lacks access. | Access-limited message without leaking content. |
| Disabled by config | Component/source is intentionally off. | Disabled mode pill with config path. |
| Degraded silence | No work is flowing but work is expected. | Issue card and subsystem/station degradation. |

This prevents operators from mistaking missing data for successful operation.


### 6.8 System triage summary

The overview page must include a compact system triage summary that turns the visual map into an immediate operational conclusion. It is not a replacement for the graph; it is the graph's textual diagnosis.

Required summary fields:

```text
system_state: healthy | degraded | blocked | frozen | stale | unknown
primary_bottleneck: subsystem_id | component_id | null
primary_reason_code: reason_code | null
telemetry_freshness: fresh | lagging | stale | partial | unavailable
candidate_flow_state: active | quiet_expected | drought | gate_blocked | unknown
runtime_context_state: efficient | pressure | shadowing | stale_policy | unknown
security_state: clear | findings | hard_block | quarantine | unknown
safe_next_action: none | inspect_issue | run_playbook | retry_job | rescan | reevaluate | freeze | rollback | restore_stream
```

The summary must be generated from the same read models and reason codes used by the visual graph. It must link to the issue board, subsystem lens, or object microscope that explains the conclusion. This prevents the overview from being visually impressive but operationally ambiguous.

---

## 7. Drill-down interaction model

### 7.1 Station cockpit

Clicking a station opens a station cockpit.

Every station cockpit has a common layout:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Breadcrumb: Overview / Context compiler                          [Actions]  │
├──────────────────────────────────────────────────────────────────────────────┤
│ Station header: health, mode, last success, backlog, freeze state, owner      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Local subgraph / internal flow                                                │
├────────────────────────────┬─────────────────────────────────────────────────┤
│ Metrics panel              │ Live records / recent events / warnings         │
├────────────────────────────┴─────────────────────────────────────────────────┤
│ Tabs: Records | Traces | Artifacts | Config | Audit | Help                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

The common station tabs are:

| Tab | Content |
|---|---|
| `Records` | Paginated current records owned by the component. |
| `Traces` | Trace-spine spans crossing this station. |
| `Artifacts` | Relevant files, hashes, SkillIR, manifests, compiled snippets, scanner/evaluator outputs. |
| `Config` | Effective redacted configuration and qualification state. |
| `Audit` | Operator/system audit entries touching this station. |
| `Help` | Implementation description, failure modes, remediation actions, and links to source docs. |

### 7.2 Subsystem lens

Clicking a subsystem lane or workcell opens a subsystem lens.

Required subsystem lens layout:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Breadcrumb: Overview / Runtime context workcell                 [Actions]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Workcell header: health, data quality, conversion, queue, dominant issue      │
├──────────────────────────────────────────────────────────────────────────────┤
│ Local directed subgraph with station cards, upstream/downstream boundaries    │
├────────────────────────────┬─────────────────────────────────────────────────┤
│ Bottleneck + issue board   │ Trace/job/candidate stream crossing workcell     │
├────────────────────────────┴─────────────────────────────────────────────────┤
│ Tabs: Flow | Quality | Traces | Records | Playbooks | Actions | Audit        │
└──────────────────────────────────────────────────────────────────────────────┘
```

Subsystem lenses are required for soak testing because many failures are not owned by a single component. Examples:

- low candidate creation can result from capture gaps, redaction over-scrubbing, evidence clustering failure, or high genericity rejection;
- context bloat can result from broker false positives, broad skills, support-context loadability errors, or context-compiler failure;
- activation stalls can result from scanner findings, evaluator regressions, writer activation locks, canary freezes, or model-profile failure;
- historical bootstrap can appear busy while producing low-value evidence because parsers are falling back to low-confidence chunks.

The subsystem lens must show cause-and-effect across station boundaries instead of forcing the operator to open many unrelated component pages.

### 7.3 Zoom transitions

The UI may animate from overview to cockpit by expanding the selected station node into the local subgraph. This animation is visual polish, not state logic. If animation fails or reduced-motion is enabled, route transition falls back to a standard page change.

### 7.4 Deep links

Every drill-down object has a stable URL:

```text
/admin/subsystems/{subsystem_id}
/admin/components/{component_id}
/admin/traces/{trace_id}
/admin/jobs/{job_id}
/admin/evolution/{transaction_id}
/admin/skills/{skill_id}/versions/{version_id}
/admin/candidates/{candidate_id}
/admin/evaluations/{evaluation_id}
/admin/scanner-findings/{finding_id}
/admin/historical/imports/{import_run_id}
/admin/artifacts/{artifact_id}
```

Deep links must not leak raw content to unauthorized users. The server enforces authorization for every object.

### 7.5 Guided diagnostic playbooks

The UI includes built-in playbooks that turn raw telemetry into operator-readable investigation paths. A playbook never overrides policy or executes hidden actions; it links to relevant subsystem lenses, component cockpits, traces, and guarded actions.

Required playbooks:

| Playbook | First checks | Typical next views |
|---|---|---|
| No useful skills are being created | capture coverage, historical import yield, redaction loss, evidence maturity, candidate rejection, duplicate suppression | Capture + bootstrap, learning + memory, opportunity miner, topology operations |
| Skill improvements are repeatedly rejected | scanner findings, regression failures, semantic equivalence failures, token-budget failures, stale probes | Context compiler, scanner, evaluator, SkillIR diff |
| Context budget is growing | false-positive loads, broad-skill shadowing, support-context loadability, verbose compiled artifacts, ignored-skill waste | Runtime context, broker, context compiler, topology decomposition |
| A skill appears harmful after activation | canary failures, user corrections, action attribution, broker load decisions, regression drift | Canary/rollback, evaluator, broker replay, audit trace |
| Historical bootstrap is slow or low-yield | source discovery, parser failures, deduplication, redaction, quarantines, evidence yield by source | Historical ingestion, redaction, evidence + memory |
| Broker misses relevant skills | retrieval recall audit, embedding backlog, lexical/vector disagreement, shadowing suppression, no-skill decisions | Retrieval, broker, topology graph |
| Database/read models are stale | migration state, materialized view refresh, slow dashboard queries, LISTEN/NOTIFY bridge, retention backlog | Storage, Observatory self-health, audit trace |
| LLM-backed maintenance is stalled | text profile qualification, structured output failures, timeout/retry pressure, paused LLM jobs | Model/embedding profile, scheduler/jobs, opportunity miner |

Each playbook displays:

- current severity and confidence;
- top supporting records;
- missing telemetry warnings;
- affected skills/candidates/jobs;
- safe next diagnostic actions;
- actions that are blocked by policy and why.

### 7.6 Object microscope

The object microscope is the lowest drill-down depth. It is the canonical page pattern for individual records.

Required object microscope panels:

| Panel | Purpose |
|---|---|
| Summary | Type, ID, state, health, confidence, timestamps, owner component, dominant reason code. |
| Timeline | Ordered state transitions, attempts, spans, gate results, and administrative actions. |
| Provenance | Upstream source records, evidence, memory, candidate, SkillIR, artifact, activation, and runtime outcome links. |
| Effects | Downstream objects affected by this record, including derived memories, embeddings, artifacts, broker caches, issues, and rollback/revocation paths. |
| Content | Redacted preview by default; raw reveal only through policy. |
| Diagnostics | Reason codes, supporting metrics, missing telemetry, likely causes, and safe next views. |
| Audit | Immutable audit records, actor/action links, manifest hashes, and policy decisions. |

Supported microscope object types include traces, jobs, schedules, candidates, skills, skill versions, SkillIR revisions, SkillGraphIR revisions, artifacts, manifests, scanner findings, evaluation runs, broker decisions, replay/canary episodes, raw-vault records, declassification reports, evidence-fidelity records, LLM semantic adjudications, autonomy decisions, threshold policies, threshold-deadlock findings, administrative escalation events, historical source items, evidence clusters, memory records, evolution transactions, issues, model-profile qualification runs, embedding-profile qualification runs, and administrative actions.

### 7.7 Aggregate-to-evidence contract

Every aggregate visible in the UI must expose a “why?” affordance. Examples:

| Aggregate | Required explanation path |
|---|---|
| Global health degraded | dominant subsystem issue → component status snapshot → supporting issue/trace/job. |
| Context pressure elevated | token rollup → skill/context artifact contributors → broker decisions → ignored-token examples. |
| Candidate yield low | evidence clusters → rejected candidates → reason-code distribution → source coverage/redaction status. |
| Scanner pressure high | finding classes → affected artifacts/bundles → taint/provenance paths. |
| Broker quality degraded | false-positive/missed-skill records → retrieval candidates → scoring waterfall → outcome attribution. |
| Storage unhealthy | stale read model/index/retention signal → query/job/metric record. |

No aggregate may be a dead end. If raw supporting content is unavailable to the actor, the explanation still shows IDs, timestamps, redaction state, and non-sensitive reason codes.

---

## 8. Component cockpits

### 8.1 OpenClaw live capture cockpit

Purpose: show live plugin capture health.

Required views:

- hook registration status;
- OpenClaw SDK/API compatibility status;
- event counts by hook type;
- agent/session coverage;
- capture latency;
- local spool depth;
- dropped/rejected event counts;
- redaction before-forward pass rate;
- sidecar connection health;
- plugin version and active configuration;
- raw-content access disabled/enabled state;
- runtime hint contribution status.

Visuals:

- hook-source matrix heatmap;
- live event stream waterfall;
- agent/session coverage treemap;
- capture-to-ingest latency histogram.

Administrative actions:

- pause/resume forwarding;
- force spool flush;
- download redacted capture diagnostic bundle;
- verify sidecar handshake;
- show installed hook capability report.

### 8.2 Historical ingestion cockpit

Purpose: show deployment bootstrap and historical backfill progress.

Required views:

- discovered sources by kind: transcripts, trajectories, compactions, memory files, context files, task records, existing skills, diagnostics, exported memory/QMD artifacts;
- dry-run inventory results;
- bytes/files/sessions scanned;
- import checkpoints;
- parser success/failure counts;
- redaction and taint counts;
- quarantined source items;
- evidence yielded by source kind;
- topology candidates seeded from history;
- confidence/maturity distribution;
- import rate and ETA-style backlog measures using item counts, not promised completion time.

Visuals:

- historical source Sankey: source → parser → evidence class → candidate class;
- timeline of historical coverage by date/session/agent;
- import backlog burn-down;
- quarantine reason treemap;
- maturity funnel: observed → recurring → contrastive → intervention_validated → regression_validated → canaried → production_verified.

Administrative actions:

- run dry-run discovery;
- start import for an allowlisted source scope;
- pause/resume import;
- quarantine/unquarantine a source item through policy;
- revoke imported source and derived data through provenance traversal;
- download redacted import report.

Historical ingestion must use the same redaction, tainting, provenance, and evidence maturity gates as live capture.

### 8.3 Redaction and taint cockpit

Purpose: show sensitive data handling and trust state.

Required views:

- redaction policy version;
- sensitive-pattern counts by category;
- raw vs redacted storage eligibility;
- taint labels by source and artifact;
- declassification transformations;
- blocked-to-LLM counts;
- blocked-to-context counts;
- derived-data revocation reachability;
- memory poisoning/guidance injection warnings.

Visuals:

- taint propagation graph;
- redaction category heatmap;
- source confidence distribution;
- quarantine timeline.

Administrative actions:

- view redaction policy;
- run redaction audit sample;
- revoke source and derived data;
- export redacted evidence sample.

### 8.4 Spool, ingest, and normalization cockpit

Purpose: show data movement from plugin or historical importer into canonical event/evidence tables.

Required views:

- local spool depth by plugin instance;
- ingest API throughput;
- idempotency key collision/reject counts;
- normalization errors by event kind;
- malformed envelope counts;
- replay counts;
- sidecar internal queue pressure.

Visuals:

- ingest flow diagram;
- envelope type histogram;
- malformed-event examples with redaction;
- retry/backoff timeline.

Administrative actions:

- retry failed batch;
- drop quarantined malformed batch only through retention policy;
- export ingest diagnostics.

### 8.5 Evidence and memory cockpit

Purpose: inspect how raw events become durable evidence and governed memory.

Required views:

- evidence counts by class;
- evidence maturity distribution;
- recurring workflow clusters;
- corrections and failures;
- provenance source graph;
- memory clusters, memory links, taint, TTL, revocation state;
- diagnostic momentum records;
- evidence used for each candidate/skill.

Visuals:

- evidence cluster map using force/graph layout;
- maturity funnel;
- source-to-evidence provenance graph;
- diagnostic momentum timeline.

Administrative actions:

- quarantine evidence cluster;
- trigger cluster refresh;
- show linked candidates;
- show redacted examples;
- revoke derived memories from a source.

### 8.5.1 Raw-evidence vault and evidence-fidelity cockpit

Purpose: inspect whether SkillKernel has enough governed semantic evidence to operate autonomously without exposing raw content casually.

Shows:

- raw-vault record counts by source type, sensitivity, retention policy, taint state, and decision family;
- evidence-fidelity distribution: `raw_vault_linked`, `declassified_summary`, `redacted_derivative`, `metadata_only`, and `hash_only`;
- decision-family support matrix showing which families can operate fully autonomously, degraded, or not at all from current evidence;
- raw-access denials and reason codes;
- declassification reports, redaction checks, secret-mask results, and minimum-necessary evidence windows;
- derived-data traversal preview for retention, revocation, quarantine, rollback, and privacy-delete operations;
- source-to-evidence lineage from live hooks, historical transcripts, trajectories, memory files, context files, tasks, and existing skills.

Safe actions:

- run evidence-fidelity audit;
- retry declassification over a bounded source window;
- schedule evidence-repair job;
- open revocation preview;
- generate a redacted diagnostic bundle.

Forbidden actions:

- bulk raw export;
- browser-side raw caching;
- raw-vault access through live stream;
- using raw content as chart labels, search snippets, or graph node text.

### 8.5.2 Autonomous semantic adjudication cockpit

Purpose: inspect LLM-backed semantic decisions without granting the UI authority over those decisions.

Shows:

- adjudication records grouped by decision family: replay intent synthesis, memory declassification, topology choice, context equivalence, broker adjudication, skill-operation planning, and redaction uncertainty;
- configured text model profile and qualification state;
- evidence bundle IDs, fidelity tier, evidence coverage, contradiction indicators, and source windows;
- structured LLM verdict, confidence decomposition, uncertainty notes, and evidence citations after redaction policy;
- deterministic admissibility result and hard-invariant outcome;
- chosen autonomous next action: accept, reject, quarantine, probe, canary, narrow scope, no-op/reschedule, or administrative escalation;
- delayed outcome and calibration feedback when available.

Safe actions:

- rerun adjudication with a bounded evidence window;
- request verifier adjudication;
- create replay-only diagnostic bundle;
- open linked threshold policy and calibration record.

The cockpit must make clear that an LLM verdict can be semantically authoritative only within its decision family and evidence policy. It cannot directly write files, change scheduler state, reveal raw content, activate skills, or bypass scanner/evaluator gates.

### 8.5.3 Autonomy decision orchestrator and threshold-governance cockpit

Purpose: inspect how SkillKernel converts semantic verdicts and deterministic checks into autonomous next actions.

Shows:

- autonomy decisions by family, risk tier, reversibility, evidence fidelity, model profile, and policy version;
- hard invariant pass/fail table;
- soft-threshold bands, calibration support, and reason-code decomposition;
- fallback ladder state, including additional evidence lookup, raw-vault lookup, re-adjudication, verifier adjudication, probe generation, ephemeral candidate, narrowed scope, canary-only activation, auto-reject, and no-op/reschedule;
- threshold-deadlock findings and over-deferral/over-action trends;
- administrative escalation events with hard-boundary reason and attempted autonomous alternatives;
- outcome feedback used to recalibrate policy.

Safe actions:

- open policy version details;
- run shadow evaluation for a threshold policy;
- open calibration-support report;
- trigger read-only threshold-deadlock diagnostic;
- schedule bounded fallback attempt where policy permits.

### 8.5.4 Replay and canary corpus cockpit

Purpose: inspect how real telemetry becomes durable replay/canary evidence.

Shows:

- replay episode candidates, accepted episodes, rejected episodes, and degraded episodes;
- synthesized `redacted_user_intent`, expected skill decision, avoided skill decision, broker context, and outcome;
- source trace, retrieval log, raw/declassified evidence window, and redaction report;
- replay coverage by decision family, skill, broker policy, executor profile, topology operation, and historical/live source;
- canary eligibility and canary results;
- silent-bypass audit: whether the skill was retrieved, rendered, visible, causally used, ignored, or bypassed.

Safe actions:

- run replay-corpus dry-run;
- rerun redaction verification;
- run replay trial;
- exclude a poisoned or stale episode through normal sidecar policy;
- export redacted corpus diagnostics.

### 8.6 Retrieval and indexing cockpit

Purpose: show lexical/vector/metadata/graph retrieval health.

Required views:

- embedding profile qualification state;
- embedding queue depth;
- unembedded object counts;
- embedding dimension/profile distribution;
- pgvector index state;
- lexical index freshness;
- exact rerank counts;
- recall audit results;
- filtered search calibration;
- graph expansion edge stats;
- active/archived/external skill match quality.

Visuals:

- retrieval pipeline: candidate generation → filters → graph expansion → exact rerank;
- recall audit chart;
- embedding backlog timeline;
- vector/lexical overlap Venn-style summary;
- top false-positive and false-negative examples.

Administrative actions:

- run retrieval calibration;
- reindex lexical search;
- re-embed selected scope;
- show index DDL/status.

### 8.7 Runtime broker cockpit

Purpose: expose what the broker chooses to load or suppress.

Required views:

- broker policy version;
- no-skill decisions;
- loaded skills;
- suppressed skills;
- shadowing detections;
- false-positive loads;
- missed-skill reports;
- context budget allocations;
- sibling disambiguation outcomes;
- broker hint renderings;
- per-executor-profile routing results.

Visuals:

- broker decision tree/graph for selected turn;
- candidate skill scoring waterfall;
- loaded-vs-suppressed comparison;
- context budget treemap;
- shadowing graph overlay.

Administrative actions:

- run broker dry-run for selected trace;
- compare broker policy versions;
- freeze broker policy;
- trigger broker calibration job;
- export redacted broker decision report.

### 8.8 Opportunity miner cockpit

Purpose: show candidate discovery for create/improve/compose/decompose.

Required views:

- candidate counts by operation;
- cluster sources;
- evidence maturity, fidelity, and calibrated decision bands;
- deduplication decisions;
- active/archived duplicate matches;
- candidate maturity ladder;
- rejected genericity/bloat candidates;
- batch-consolidation windows.

Visuals:

- candidate funnel;
- operation distribution chart;
- evidence cluster → candidate graph;
- genericity rejection treemap;
- recurring workflow timeline.

Administrative actions:

- force candidate refresh;
- quarantine candidate;
- mark candidate as watch-only;
- open evidence bundle.

### 8.9 Topology operations cockpit

Purpose: inspect create, improve, compose, and decompose as first-class autonomous operations.

Required views:

- operation candidates by type and state;
- operation trials and counterfactuals;
- component-only vs composed skill results;
- original vs decomposed successor results;
- merge/deduplicate/archive/promote support operations;
- active budget decisions;
- utility rollups.

Visuals:

- skill-library topology graph;
- composition subgraphs;
- decomposition split maps;
- operation trial comparison matrix;
- marginal-value-per-context-token chart.

Administrative actions:

- run operation dry-run;
- freeze operation class;
- compare trials;
- open SkillIR/SkillGraphIR diff;
- request rollback or promotion job.

### 8.10 SkillIR and SkillGraphIR cockpit

Purpose: inspect canonical skill representations.

Required views:

- SkillIR revision history;
- SkillGraphIR component nodes and edges;
- contracts, preconditions, effects, conflicts, fallbacks;
- version lineage;
- supersession/composition/decomposition links;
- support artifact plan;
- compiled output previews.

Visuals:

- graph IR DAG;
- version timeline;
- diff viewer;
- contract/effect matrix;
- dependency/conflict graph.

Administrative actions:

- open read-only SkillIR JSON;
- compare revisions;
- run validation;
- run compile preview;
- export manifest bundle.

### 8.11 Skill package planner cockpit

Purpose: show why a skill is instruction-only or why it includes ancillary files.

Required views:

- artifact plan decisions;
- generated file list;
- loadability classes;
- capability declarations;
- artifact tests;
- scanner findings by artifact;
- context-token impact by artifact;
- adjunct requests.

Visuals:

- skill package tree;
- artifact value-vs-risk matrix;
- context-loadability map;
- manifest hash chain.

Administrative actions:

- rescan artifact plan;
- open read-only artifact preview;
- compare artifact diffs;
- quarantine adjunct request;
- export package manifest.

### 8.12 Context compiler cockpit

Purpose: monitor AI-facing context compilation and token-budget governance.

Required views:

- `SKILL.md` token counts;
- broker hint token counts;
- support-context token counts;
- compression ratios;
- semantic equivalence scores;
- rejected verbose/generic text;
- token-budget failures;
- ignored-skill token waste;
- context artifact classifications.

Visuals:

- context budget treemap;
- before/after diff with token annotations;
- semantic density scorecard;
- runtime context assembly timeline;
- context pressure over time.

Administrative actions:

- compile preview;
- rerun semantic equivalence check;
- open redacted compiled artifact;
- show context-value calculation.

### 8.13 Scanner and security cockpit

Purpose: monitor static, semantic, capability, supply-chain, guidance-injection, and composed-bundle scanning.

Required views:

- hard findings;
- soft findings;
- scanner policy version;
- artifact scans;
- bundle scans;
- harmful-capability classifications;
- hidden Unicode/comment findings;
- dynamic fetch/exec findings;
- path/capability violations;
- secret exfiltration patterns;
- guidance injection findings from workspace/memory/context sources;
- scanner coverage and stale scans.

Visuals:

- risk matrix;
- artifact tree with finding badges;
- bundle-composition risk graph;
- taint-to-artifact path view;
- scanner trend timeline.

Administrative actions:

- trigger rescan;
- quarantine artifact/candidate/skill;
- open finding details;
- freeze skill;
- export security report.

### 8.14 Evaluator and probes cockpit

Purpose: expose target, regression, adversarial, canary, and benchmark-style evaluation.

Required views:

- evaluation runs by type;
- pass/fail/error counts;
- target probe results;
- regression budget status;
- adversarial probe results;
- no-skill/current/new/composed/decomposed comparison;
- evaluator environment/executor profile;
- stale probes;
- co-evolved verifier candidate state.

Visuals:

- trial comparison table;
- regression sparkline;
- probe coverage matrix;
- evaluation trace replay;
- failure clustering chart.

Administrative actions:

- rerun evaluation;
- mark probe stale through policy;
- open redacted probe fixture;
- compare candidate vs current.

### 8.15 Deterministic writer and activation cockpit

Purpose: show staged files, manifests, activation locks, immutable active packages, and atomic swaps.

Required views:

- staged transactions;
- active packages;
- file manifests and hashes;
- activation lock status;
- safe activation windows;
- writer errors;
- path containment checks;
- runtime package immutability state.

Visuals:

- staged → scanned → evaluated → active transaction flow;
- file tree diff;
- hash/provenance chain;
- activation timeline.

Administrative actions:

- abort staged transaction;
- request activation at maintenance window;
- rollback active version;
- export manifest.

### 8.16 Canary, rollback, and freeze cockpit

Purpose: track post-activation behavior and fail-closed controls.

Required views:

- active canaries;
- canary metrics;
- rollback candidates;
- rollback records;
- freeze reasons;
- derived-data revocation status;
- affected skills/artifacts/memories/embeddings/broker caches;
- post-rollback verification.

Visuals:

- canary success/failure timeline;
- rollback dependency graph;
- derived-data revocation graph;
- freeze-state heatmap.

Administrative actions:

- freeze/unfreeze;
- rollback transaction;
- run post-rollback validation;
- export rollback report.

### 8.17 Scheduler and jobs cockpit

Purpose: monitor the sidecar-owned scheduler and durable jobs.

Required views:

- schedules;
- due jobs;
- running jobs;
- retries/backoff;
- leases;
- job attempts;
- worker heartbeats;
- queue depth by type;
- blocked jobs and reason codes;
- idempotency collisions.

Visuals:

- queue heatmap;
- Gantt-style job timeline;
- lease ownership graph;
- retry waterfall;
- schedule calendar.

Administrative actions:

- pause/resume schedule;
- retry failed job;
- cancel safe job;
- run dry-run job;
- view job payload redacted.

### 8.18 Model and embedding profile cockpit

Purpose: show configured text LLM and embedding profile health without cost analytics.

Required views:

- active text profile;
- active embedding profile;
- route type: `openclaw` or `openai_compatible`;
- qualification state;
- recent invocation success/error/timeout counts;
- structured-output adherence failures;
- embedding dimension sanity checks;
- retrieval sanity probes;
- local/hosted policy state;
- token counts when returned by provider;
- latency and retry pressure.

Visuals:

- qualification checklist;
- latency histogram;
- invocation outcome timeline;
- embedding sanity matrix;
- structured-output failure examples with redaction.

Administrative actions:

- run text-profile qualification;
- run embedding-profile qualification;
- view effective redacted configuration;
- pause LLM-backed maintenance jobs.

The cockpit must not show currency cost, price tables, or model-price recommendations.

### 8.19 Storage and database cockpit

Purpose: monitor Postgres, pgvector, read models, retention, migrations, and DB health.

Required views:

- migration version;
- table sizes;
- index sizes;
- pgvector index status;
- embedding counts by profile/dimension;
- materialized view freshness;
- slow dashboard queries;
- retention backlog;
- vacuum/analyze warning signals where available;
- LISTEN/NOTIFY bridge health;
- read-model refresh failures.

Visuals:

- schema size treemap;
- materialized view freshness gauges;
- index health table;
- read-query latency chart;
- retention backlog timeline.

Administrative actions:

- refresh read models;
- run DB health check;
- export storage diagnostic summary;
- trigger retention dry run.

### 8.20 Audit and trace-spine cockpit

Purpose: correlate everything.

Required views:

- trace search;
- span graph;
- administrative actions;
- model invocations;
- scanner/evaluator links;
- job attempts;
- artifact writes;
- transaction boundaries;
- action attribution records;
- autonomy decisions and administrative escalation records;
- audit hash-chain verification;
- provenance traversal.

Visuals:

- trace waterfall;
- provenance graph;
- audit chain verifier;
- action-attribution causal map;
- event replay animation.

Administrative actions:

- verify audit chain;
- export redacted trace bundle;
- open linked skill/candidate/job/evaluation;
- revoke source-derived records through policy.

### 8.21 Administrative escalation cockpit

Purpose: inspect exceptional cases where autonomous semantic adjudication and fallback paths cannot complete because a hard authority boundary, raw-exposure policy, external ownership boundary, or infrastructure failure requires administrative resolution.

Required views:

- open/resolved escalation events by hard-boundary category;
- linked autonomy decision, semantic adjudication run, evidence-fidelity state, raw-vault access attempt, threshold policy, and affected object;
- attempted autonomous alternatives before escalation;
- reason-code history and recurrence analysis;
- recommended resolution path: grant governed evidence access, adjust retention/exposure policy, fix model/profile qualification, reject external mutation, run infrastructure repair, or explicitly keep degraded mode;
- audit receipt and downstream impact graph.

Visuals:

- escalation funnel from autonomous fallback to hard-boundary event;
- recurrence heatmap by decision family;
- affected skill/candidate/source graph;
- hard-boundary taxonomy chart.

Administrative actions:

- acknowledge escalation;
- resolve with reason;
- reject unsafe request;
- open linked policy/evidence/job records;
- export redacted escalation bundle.

An administrative escalation is not a default semantic review queue. A recurring escalation without a hard-boundary reason is an autonomy defect and must be visible as such.

### 8.22 Administrative action gateway cockpit

Purpose: show guarded UI/API actions and their policy/audit path.

Required views:

- pending action requests;
- accepted/rejected action counts by action kind;
- role and confirmation failures;
- idempotency collisions;
- linked sidecar jobs;
- linked audit/evolution records;
- blocked-by-policy reasons;
- high-impact action history;
- raw-content reveal records.

Visuals:

- action request → policy → job → audit flow;
- rejection reason treemap;
- administrative action timeline;
- high-impact action matrix.

Administrative actions:

- open linked audit record;
- retry safe idempotent request only when policy allows;
- export redacted action report.

### 8.23 Observatory self-health cockpit

Purpose: show the web administration surface itself.

Required views:

- admin API health;
- static frontend build/version;
- live WebSocket/SSE sessions;
- sequence-gap and reconnect counts;
- read-model freshness by view;
- frontend error telemetry;
- slow admin API endpoints;
- browser performance diagnostics;
- authentication/authorization failures;
- rate-limit events;
- live event outbox lag;
- snapshot reload counts;
- active dashboard lens and page usage statistics, aggregated without raw content.

Visuals:

- live stream health timeline;
- read-model freshness heatmap;
- admin API latency chart;
- browser error table;
- active viewers by role, without exposing raw content.

Administrative actions:

- refresh read models;
- download redacted Observatory diagnostic bundle;
- verify live-stream sequence continuity;
- clear expired raw-content reveal tokens.

---

## 9. Skill-centric pages

### 9.1 Skill library page

Route: `/admin/skills`

The skill library page shows all SkillKernel-owned skills and inventoried external skills.

Columns:

- skill name;
- ownership: SkillKernel-owned or external/read-only;
- lifecycle state;
- active/archive/canary/frozen;
- current version;
- granularity: atomic, functional, workflow, planning, meta;
- token count;
- usage attribution;
- false-positive load rate;
- missed-skill signal;
- shadowing count;
- drift state;
- scanner state;
- evaluator state;
- last activation;
- rollback availability.

Filters:

```text
state, operation lineage, skill owner, granularity, token pressure, risk, drift, shadowing, utility, executor profile, source evidence, created from historical data, composed/decomposed lineage
```

### 9.2 Skill detail page

Route: `/admin/skills/{skill_id}`

Required panels:

- summary and health;
- lifecycle lineage;
- versions;
- SkillIR and SkillGraphIR;
- compiled `SKILL.md` preview;
- support artifact tree;
- context-token analysis;
- evidence sources;
- usage attribution;
- broker routing decisions;
- scanner findings;
- evaluator/probe results;
- curation decisions;
- rollback state;
- manifests and hashes;
- external overlap/shadowing relationships.

Views:

- `Overview`;
- `SkillIR`;
- `Package`;
- `Evidence`;
- `Routing`;
- `Context`;
- `Evaluation`;
- `Security`;
- `Lineage`;
- `Audit`.

### 9.3 Skill topology page

Route: `/admin/topology`

Purpose: visualize the library shape.

Graph node classes:

- SkillKernel active skill;
- SkillKernel archived skill;
- external skill;
- candidate;
- component skill;
- composed workflow skill;
- decomposed successor;
- superseded version;
- harmful/quarantined artifact.

Edge classes:

```text
component_of, composes, decomposes_to, supersedes, superseded_by, overlaps_with,
conflicts_with, requires, specializes, generalizes, shadows, shadowed_by,
created_from, improved_from, evaluated_against, rollback_of
```

Visual modes:

- topology;
- utility;
- token pressure;
- shadowing;
- drift;
- security risk;
- broker co-load;
- historical origin;
- version lineage.

Administrative actions:

- open candidate;
- compare composed vs component-only trial;
- compare decomposition split vs original;
- freeze a high-risk skill;
- open broker replay.

---

## 10. Subsystem pages

Subsystem pages are required because SkillKernel’s large functions span multiple components. They are available at `/admin/subsystems/{subsystem_id}`.

### 10.1 Capture + bootstrap workcell

Shows whether SkillKernel is receiving enough trustworthy live and historical data to learn from.

Required panels:

- live hook/source coverage;
- historical source coverage;
- redaction loss analysis;
- parser success/failure;
- canonical event conversion;
- evidence yield by source;
- taint/quarantine impact;
- source confidence and maturity distribution.

Primary question: "Is SkillKernel seeing the deployment accurately enough to learn?"

### 10.2 Learning + memory workcell

Shows how records become evidence, memory, retrieval objects, and candidate opportunities.

Required panels:

- evidence clusters;
- recurring workflow detection;
- correction/failure mining;
- memory quarantine and revocation;
- embedding/lexical indexing health;
- duplicate/near-match detection;
- candidate funnel.

Primary question: "Is the system extracting durable, useful, non-poisoned signals?"

### 10.3 Runtime context workcell

Shows whether runtime skill selection is helping or hurting the agent.

Required panels:

- retrieved/loaded/suppressed/no-skill decisions;
- broker scoring waterfall;
- false-positive and missed-skill cases;
- context budget and ignored-skill waste;
- runtime outcome attribution;
- shadowing and sibling conflicts;
- canary feedback.

Primary question: "Is the right skill context reaching the agent at the right time?"

### 10.4 Topology design workcell

Shows create, improve, compose, and decompose decisions before they become artifacts.

Required panels:

- topology candidates by operation;
- SkillIR/SkillGraphIR proposal state;
- composition/decomposition evidence;
- intervention trial design;
- genericity/bloat rejection;
- archived/external overlap;
- active budget pressure.

Primary question: "Is SkillKernel shaping the library correctly?"

### 10.5 Quality gates workcell

Shows scanner and evaluator readiness, coverage, and failure ownership.

Required panels:

- scanner policy coverage;
- artifact and bundle findings;
- target/regression/adversarial/canary probe results;
- benchmark adapter health;
- model/profile qualification failures;
- stale probes and stale scans;
- trial comparison summaries.

Primary question: "Are proposed changes safe and measurably useful?"

### 10.6 Artifact mutation workcell

Shows how accepted plans become immutable active packages.

Required panels:

- artifact plan;
- context compilation;
- package manifest;
- deterministic writer transaction;
- activation lock;
- atomic swap state;
- rollback pointer;
- support artifact scans/tests.

Primary question: "Did the system create exactly the intended package and activate it safely?"

### 10.7 Lifecycle governance workcell

Shows long-term health of active, archived, promoted, frozen, and rolled-back skills.

Required panels:

- active/archive/promotion states;
- canary and production verification;
- rollback/freeze records;
- derived-data revocation;
- skill technical debt;
- external skill collision/shadowing;
- action attribution.

Primary question: "Is the skill library improving over time without accumulating hidden debt?"

### 10.8 Autonomy + adjudication workcell

Primary question: "Is SkillKernel making semantic decisions autonomously, with enough evidence and calibrated trust?"

Stations:

```text
raw_evidence_vault
evidence_fidelity
semantic_adjudication
autonomy_orchestrator
replay_corpus
model_embedding
audit_trace
administrative_escalation
```

Required views:

- decision-family matrix showing replay promotion, memory declassification, topology choice, context equivalence, broker adjudication, and skill-operation planning;
- evidence-fidelity distribution by decision family: `raw_vault_linked`, `declassified_summary`, `redacted_derivative`, `metadata_only`, `hash_only`;
- raw-vault policy state, raw-access denials, declassification reports, and revocation backlog without exposing raw content by default;
- LLM adjudication records with evidence IDs, structured verdict, confidence decomposition, uncertainty fields, contradiction flags, model profile, and prompt-window policy;
- deterministic admissibility results: schema, provenance, redaction, scanner, rollback, risk tier, ownership, context budget, and canary checks;
- soft-threshold policy versions, calibration support, threshold-deadlock findings, and fallback-ladder progress;
- replay/canary corpus episodes synthesized from real telemetry, including redacted intent, expected skill decision, avoided skill decision, provenance, and trial outcome;
- administrative escalation records with hard-boundary reason, attempted autonomous alternatives, affected object, and safe next action;
- autonomy-defect trend chart distinguishing over-action, over-deferral, low evidence fidelity, stale calibration, model-profile failure, and policy-denied raw access.

Workcell health fails if semantic decision families repeatedly end in `administrative_escalation_required` without a hard authority-boundary reason, if `metadata_only` or `hash_only` evidence is being used for decisions that require user intent, if raw-vault access is denied for full-autonomy families without degraded-mode labeling, or if soft-threshold misses accumulate without autonomous fallback attempts.

### 10.9 Control + storage workcell

Shows whether the sidecar control plane, scheduler, model profiles, storage, read models, and Observatory itself are reliable.

Required panels:

- scheduler jobs/leases/backoff;
- model and embedding profile qualification;
- Postgres and pgvector health;
- read-model freshness;
- retention backlog;
- audit chain;
- Observatory self-health;
- administrative action gateway.

Primary question: "Is the infrastructure supporting autonomy correctly?"

---

## 11. Trace replay and time travel

### 11.1 Trace replay

Trace replay lets an operator select any event, job, candidate, evolution transaction, skill version, or runtime decision and watch it move through the SkillKernel pipeline.

Example trace:

```text
historical transcript chunk
→ redacted evidence
→ recurring workflow cluster
→ compose candidate
→ SkillGraphIR plan
→ compiled workflow skill package
→ scanner pass
→ component-only vs composed evaluation
→ activation transaction
→ broker canary
→ production verified
```

Replay UI requirements:

- timeline scrubber;
- station highlighting;
- edge animation;
- span waterfall;
- record detail drawer;
- policy/gate badges;
- diff panels for SkillIR and compiled artifacts;
- links to source evidence, evaluation runs, scanner findings, and audit entries;
- exportable redacted trace bundle.

### 11.2 Time-window replay

The overview supports replaying a time window:

```text
last 15 minutes | last hour | last 24 hours | historical import run | custom range
```

Time-window replay uses aggregated read models, not raw event streaming. It shows changing pipeline state and station pressure over time.

### 11.3 Playback safety

Replay never re-executes work. It visualizes persisted state and audit records only.

### 11.4 Baseline comparison

The UI supports comparing two bounded time windows or two object versions:

```text
current 30 minutes vs previous 30 minutes
post-bootstrap vs pre-bootstrap
before activation vs after activation
old broker policy vs current broker policy
original skill vs composed skill
large skill vs decomposed successors
```

Comparison views show deltas for throughput, latency, rejection rate, context tokens, scanner/evaluator failure rates, broker precision, candidate yield, activation count, rollback/freeze rate, and storage/read-model freshness.

Baseline comparison is diagnostic only. It does not decide autonomous policy. Policy decisions remain in SkillKernel’s evaluator, curation, broker, and lifecycle services.

---

## 12. Backend API

### 12.1 Route structure

All admin routes are under `/admin` by default.

```text
GET  /admin/                         static SPA shell
GET  /admin/assets/*                 frontend assets
GET  /admin/api/v1/health/live       liveness, optionally unauthenticated
GET  /admin/api/v1/health/ready      authenticated readiness
GET  /admin/api/v1/summary           global dashboard summary
GET  /admin/api/v1/search            global permission-filtered object search
GET  /admin/api/v1/pipeline          station and edge snapshot
GET  /admin/api/v1/subsystems        subsystem/workcell list and health rollups
GET  /admin/api/v1/subsystems/{id}   subsystem detail, local graph, issues, and playbooks
GET  /admin/api/v1/components        component list
GET  /admin/api/v1/components/{id}   component detail
GET  /admin/api/v1/components/{id}/metrics
GET  /admin/api/v1/events            paginated redacted event query
GET  /admin/api/v1/evidence/fidelity evidence-fidelity summary and unsupported decision families
GET  /admin/api/v1/evidence/fidelity/{id} evidence-fidelity object detail
GET  /admin/api/v1/raw-vault/summary redacted raw-vault policy and retention summary
GET  /admin/api/v1/raw-vault/records/{id} policy-checked redacted record/declassification detail
GET  /admin/api/v1/adjudications semantic adjudication query
GET  /admin/api/v1/adjudications/{id} semantic adjudication detail
GET  /admin/api/v1/autonomy/decisions autonomy decision query
GET  /admin/api/v1/autonomy/decisions/{id} autonomy decision detail
GET  /admin/api/v1/autonomy/policies threshold/calibration policy versions
GET  /admin/api/v1/autonomy/threshold-deadlocks threshold-deadlock findings
GET  /admin/api/v1/escalations administrative escalation query
GET  /admin/api/v1/escalations/{id} administrative escalation detail
GET  /admin/api/v1/replay-corpus replay/canary corpus query
GET  /admin/api/v1/replay-corpus/{id} replay/canary episode detail
GET  /admin/api/v1/traces            trace search
GET  /admin/api/v1/traces/{id}       trace detail and graph
GET  /admin/api/v1/jobs              job query
GET  /admin/api/v1/jobs/{id}         job detail
GET  /admin/api/v1/schedules         schedules
GET  /admin/api/v1/skills            skill list
GET  /admin/api/v1/skills/{id}       skill detail
GET  /admin/api/v1/skills/{id}/versions/{version_id}
GET  /admin/api/v1/topology          skill topology graph
GET  /admin/api/v1/candidates        candidate query
GET  /admin/api/v1/candidates/{id}   candidate detail
GET  /admin/api/v1/evaluations       evaluation query
GET  /admin/api/v1/evaluations/{id}  evaluation detail
GET  /admin/api/v1/scanner-findings  scanner finding query
GET  /admin/api/v1/artifacts/{id}    redacted artifact preview
GET  /admin/api/v1/historical/imports
GET  /admin/api/v1/historical/imports/{id}
GET  /admin/api/v1/broker/decisions
GET  /admin/api/v1/broker/decisions/{id}
GET  /admin/api/v1/context/artifacts
GET  /admin/api/v1/model-profile     text LLM profile status
GET  /admin/api/v1/embedding-profile embedding profile status
GET  /admin/api/v1/storage           DB/read-model/index summary
GET  /admin/api/v1/audit             audit query
GET  /admin/api/v1/issues            active diagnostic issues
GET  /admin/api/v1/issues/{id}       issue detail and supporting evidence
GET  /admin/api/v1/reason-codes      reason-code catalog
GET  /admin/api/v1/playbooks         diagnostic playbook catalog
GET  /admin/api/v1/playbooks/{id}    playbook detail and current signal state
GET  /admin/api/v1/observatory       admin UI/API/live-stream self-health
GET  /admin/api/v1/config/effective  redacted effective config
GET  /admin/api/v1/objects/{type}/{id} object microscope payload
GET  /admin/api/v1/invariants        pipeline invariant status
GET  /admin/api/v1/comparisons       saved baseline comparisons
POST /admin/api/v1/comparisons/query create read-only baseline comparison
GET  /admin/api/v1/diagnostics/bundles/{id}
POST /admin/api/v1/diagnostics/bundles create redacted diagnostic bundle
WS   /admin/live                     live delta stream
GET  /admin/live-sse                 optional read-only SSE stream
```

Guarded action routes:

```text
POST /admin/api/v1/actions/jobs/{id}/retry
POST /admin/api/v1/actions/jobs/{id}/cancel
POST /admin/api/v1/actions/schedules/{id}/pause
POST /admin/api/v1/actions/schedules/{id}/resume
POST /admin/api/v1/actions/historical/discover-dry-run
POST /admin/api/v1/actions/historical/import
POST /admin/api/v1/actions/candidates/{id}/quarantine
POST /admin/api/v1/actions/skills/{id}/freeze
POST /admin/api/v1/actions/skills/{id}/unfreeze
POST /admin/api/v1/actions/skills/{id}/rollback
POST /admin/api/v1/actions/evaluations/{id}/rerun
POST /admin/api/v1/actions/scanner/rescan
POST /admin/api/v1/actions/broker/calibrate
POST /admin/api/v1/actions/autonomy/evidence-audit
POST /admin/api/v1/actions/autonomy/rerun-adjudication
POST /admin/api/v1/actions/autonomy/threshold-diagnostic
POST /admin/api/v1/actions/escalations/{id}/resolve
POST /admin/api/v1/actions/replay-corpus/dry-run
POST /admin/api/v1/actions/replay-corpus/rerun-trial
POST /admin/api/v1/actions/model-profile/qualify
POST /admin/api/v1/actions/embedding-profile/qualify
POST /admin/api/v1/actions/storage/health-check
POST /admin/api/v1/actions/storage/retention-dry-run
POST /admin/api/v1/actions/audit/verify-chain
POST /admin/api/v1/actions/observatory/refresh-read-models
POST /admin/api/v1/actions/observatory/verify-live-stream
POST /admin/api/v1/actions/revocation/revoke-source
```

Action routes require `operator` or `admin` role, idempotency key, CSRF protection for browser sessions, confirmation payload for high-impact actions, and audit reason.

### 12.2 API response envelopes

All API responses use consistent envelopes.

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "request_id": "req_01jz4y1qqfsn9x3vv8h1x9wqf7",
    "snapshot_seq": 1874503,
    "generated_at": "2026-06-03T14:38:41Z",
    "redaction_level": "default",
    "warnings": []
  }
}
```

Error response:

```json
{
  "ok": false,
  "error": {
    "code": "FORBIDDEN_RAW_CONTENT",
    "message": "Raw content access is disabled by configuration.",
    "details": {
      "required_role": "admin",
      "config_path": "web_admin.raw_content.enabled"
    }
  },
  "meta": {
    "request_id": "req_01jz4y1s2rpxx5vgrhwrnb2kg2",
    "generated_at": "2026-06-03T14:39:04Z"
  }
}
```

### 12.3 Live stream envelope

```json
{
  "seq": 1874504,
  "sent_at": "2026-06-03T14:39:11Z",
  "kind": "component_health_changed",
  "component_id": "evaluator_probes",
  "trace_id": "trc_01jz4y20r9e0w0wqh91g6k2jbx",
  "payload": {
    "health": "degraded",
    "queue_depth": 42,
    "p95_latency_ms": 4280,
    "warning_count": 7
  }
}
```

Stream event kinds:

```text
component_health_changed
edge_flow_changed
job_started
job_progress
job_finished
job_failed
candidate_created
candidate_state_changed
skill_state_changed
skill_version_activated
skill_frozen
skill_rolled_back
historical_import_progress
scanner_finding_opened
scanner_finding_resolved
evaluation_started
evaluation_finished
broker_decision_logged
context_budget_changed
storage_health_changed
model_profile_changed
embedding_profile_changed
audit_record_appended
read_model_invalidated
subsystem_health_changed
issue_opened
issue_resolved
observatory_self_health_changed
```

### 12.4 Pagination and query limits

Every list endpoint supports cursor pagination:

```text
?limit=50&cursor=eyJ0IjoiMjAyNi0wNi0wM1QxNDozOTo1NloiLCJpZCI6IjAxanR4eTQifQ
```

Rules:

- default limit: 50;
- maximum limit: 500;
- no unbounded queries;
- all endpoints enforce server-side timeouts;
- all free-text searches run against approved read models or indexed columns;
- no endpoint returns raw event payloads without explicit raw-content authorization.

### 12.5 API compatibility and schema versioning

Every admin response and live-stream event includes:

```json
{
  "api_version": "admin.v1",
  "schema_version": 1,
  "server_build": "skillkernel-observatory-2026.06.03",
  "request_id": "req_01jz55dsy34zkd7d90a5h5p9se"
}
```

The frontend refuses to operate against an incompatible major `api_version`. Minor additive fields are ignored safely. Unknown enum values render as `unknown` with a self-health warning instead of crashing a view.


### 12.6 API truth and stability contract

The admin API must preserve UI stability and diagnostic truth.

Rules:

1. Entity identifiers are stable for the life of the entity. A refresh must not mint new IDs for the same component, station, edge, issue, job, trace, candidate, skill version, artifact, or transaction.
2. API responses include `schema_version`, `read_model_version`, `generated_at`, and `freshness` metadata where the frontend needs to distinguish stale data from healthy idle state.
3. List endpoints support cursor pagination and server-side filtering. Large tables, traces, and artifact lists are never dumped wholesale into the browser.
4. Snapshot endpoints return complete objects for the requested view. Delta endpoints return patches keyed by stable IDs.
5. If a backend cannot determine a status, it returns `unknown` with a reason code rather than manufacturing a healthy state.
6. All aggregate values that are approximate, sampled, redacted, or derived from stale read models include an explicit `data_quality` field.
7. Action endpoints return an audited action record or an idempotent reference to an existing action record. The UI does not infer action success from HTTP success alone.
8. Redacted fields remain structurally present where practical, using explicit redaction metadata, so layouts do not jump and users can understand why content is hidden.
9. WebSocket/SSE deltas are advisory state updates. The browser reconciles them against stable entities and can recover from gaps by fetching the affected snapshot region.
10. Semantic-decision endpoints include evidence-fidelity tier, adjudication status, deterministic admissibility result, policy version, fallback state, and escalation reason where applicable.
11. Raw-vault endpoints never return raw content unless the request presents a valid reveal token, role, purpose, and audit reason; ordinary object details return redacted previews or denial metadata.
12. Backend responses are responsible for policy-safe data shaping. The frontend is not the security boundary for raw content, hidden actions, or unauthorized records.

---

## 13. Read models and database additions

### 13.1 Read-model principle

The admin UI must not run heavy joins against raw event/evidence tables during every refresh. The sidecar maintains read models through scheduled refresh, incremental update, or materialized view refresh.

Use normal SQL views for cheap summaries and materialized views or rollup tables for expensive aggregates.

### 13.2 Database prerequisites

The `autoskill` schema is created by the core SkillKernel migrations. The Observatory migration requires UUID generation support before creating admin tables.

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS autoskill;
```

DDL snippets in this document are grouped by concept. Production migrations must topologically order extensions, schemas, tables, foreign keys, indexes, seed data, and materialized views.

### 13.3 Admin tables

```sql
CREATE TABLE IF NOT EXISTS autoskill.admin_subsystem_catalog (
  subsystem_id text PRIMARY KEY,
  display_name text NOT NULL,
  description text NOT NULL,
  details_route text NOT NULL,
  sort_order integer NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_component_catalog (
  component_id text PRIMARY KEY,
  display_name text NOT NULL,
  component_group text NOT NULL,
  description text NOT NULL,
  details_route text NOT NULL,
  sort_order integer NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_subsystem_component_map (
  subsystem_id text NOT NULL REFERENCES autoskill.admin_subsystem_catalog(subsystem_id),
  component_id text NOT NULL REFERENCES autoskill.admin_component_catalog(component_id),
  local_sort_order integer NOT NULL DEFAULT 0,
  role text NOT NULL DEFAULT 'member',
  PRIMARY KEY (subsystem_id, component_id)
);

CREATE TABLE IF NOT EXISTS autoskill.admin_pipeline_edges (
  edge_id text PRIMARY KEY,
  from_component_id text NOT NULL REFERENCES autoskill.admin_component_catalog(component_id),
  to_component_id text NOT NULL REFERENCES autoskill.admin_component_catalog(component_id),
  subsystem_id text REFERENCES autoskill.admin_subsystem_catalog(subsystem_id),
  edge_kind text NOT NULL DEFAULT 'data_flow',
  display_label text NOT NULL DEFAULT '',
  sort_order integer NOT NULL DEFAULT 0,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_component_status_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  component_id text NOT NULL REFERENCES autoskill.admin_component_catalog(component_id),
  health text NOT NULL CHECK (health IN ('healthy','degraded','blocked','frozen','offline','unknown')),
  mode text NOT NULL CHECK (mode IN ('active','read_only','dry_run','paused','maintenance','disabled')),
  freeze_state text NOT NULL DEFAULT 'none',
  metrics jsonb NOT NULL DEFAULT '{}',
  warnings jsonb NOT NULL DEFAULT '[]',
  captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_component_status_component_time_idx
ON autoskill.admin_component_status_snapshots(component_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_live_event_outbox (
  seq bigserial PRIMARY KEY,
  kind text NOT NULL,
  component_id text,
  trace_id text,
  object_type text,
  object_id text,
  payload jsonb NOT NULL DEFAULT '{}',
  redaction_level text NOT NULL DEFAULT 'default',
  created_at timestamptz NOT NULL DEFAULT now(),
  delivered_hint boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS admin_live_event_created_idx
ON autoskill.admin_live_event_outbox(created_at DESC);

CREATE INDEX IF NOT EXISTS admin_live_event_component_idx
ON autoskill.admin_live_event_outbox(component_id, seq DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_action_audit (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id text NOT NULL,
  actor_roles text[] NOT NULL DEFAULT '{}',
  action_kind text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  idempotency_key text NOT NULL,
  request_payload_redacted jsonb NOT NULL DEFAULT '{}',
  reason text NOT NULL,
  result text NOT NULL CHECK (result IN ('accepted','rejected','failed','completed')),
  linked_job_id uuid,
  linked_audit_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (actor_id, action_kind, target_type, target_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS autoskill.admin_diagnostic_issues (
  issue_id text PRIMARY KEY,
  severity text NOT NULL CHECK (severity IN ('info','warning','degraded','blocked','security','regression','freeze')),
  scope_type text NOT NULL CHECK (scope_type IN ('system','subsystem','component','skill','candidate','job','trace','autonomy_decision','evidence_fidelity','raw_vault','threshold_deadlock','administrative_escalation','replay_episode')),
  scope_id text NOT NULL,
  title text NOT NULL,
  symptom text NOT NULL,
  likely_causes jsonb NOT NULL DEFAULT '[]',
  evidence_links jsonb NOT NULL DEFAULT '[]',
  safe_actions jsonb NOT NULL DEFAULT '[]',
  state text NOT NULL CHECK (state IN ('open','acknowledged','resolved','suppressed')),
  opened_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS admin_diagnostic_issues_state_severity_idx
ON autoskill.admin_diagnostic_issues(state, severity, opened_at DESC);


CREATE TABLE IF NOT EXISTS autoskill.admin_autonomy_decision_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_id uuid NOT NULL,
  decision_family text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  evidence_fidelity text NOT NULL CHECK (evidence_fidelity IN ('raw_vault_linked','declassified_summary','redacted_derivative','metadata_only','hash_only')),
  llm_adjudication_state text NOT NULL CHECK (llm_adjudication_state IN ('not_required','pending','completed','failed','contradicted','policy_denied')),
  deterministic_admissibility text NOT NULL CHECK (deterministic_admissibility IN ('pending','passed','failed','quarantined','narrowed','canary_only')),
  selected_action text NOT NULL,
  policy_version text NOT NULL,
  confidence_components jsonb NOT NULL DEFAULT '{}',
  reason_codes text[] NOT NULL DEFAULT '{}',
  fallback_state jsonb NOT NULL DEFAULT '{}',
  linked_trace_id text,
  linked_issue_id text REFERENCES autoskill.admin_diagnostic_issues(issue_id),
  captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_autonomy_decision_family_time_idx
ON autoskill.admin_autonomy_decision_snapshots(decision_family, captured_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_evidence_fidelity_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type text NOT NULL,
  scope_id text NOT NULL,
  fidelity_counts jsonb NOT NULL DEFAULT '{}',
  unsupported_decision_families jsonb NOT NULL DEFAULT '[]',
  evidence_repair_jobs jsonb NOT NULL DEFAULT '[]',
  raw_vault_policy_state text NOT NULL DEFAULT 'unknown',
  captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_evidence_fidelity_scope_time_idx
ON autoskill.admin_evidence_fidelity_snapshots(scope_type, scope_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_replay_corpus_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  replay_episode_id uuid,
  state text NOT NULL CHECK (state IN ('candidate','accepted','rejected','degraded','canary','quarantined')),
  source_kind text NOT NULL,
  evidence_fidelity text NOT NULL,
  has_synthesized_redacted_intent boolean NOT NULL DEFAULT false,
  redaction_status text NOT NULL DEFAULT 'unknown',
  expected_decision_status text NOT NULL DEFAULT 'unknown',
  canary_status text NOT NULL DEFAULT 'not_applicable',
  reason_codes text[] NOT NULL DEFAULT '{}',
  captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_replay_corpus_state_time_idx
ON autoskill.admin_replay_corpus_snapshots(state, captured_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_administrative_escalation_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  escalation_id uuid NOT NULL,
  escalation_kind text NOT NULL,
  hard_boundary_reason text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  attempted_autonomous_alternatives jsonb NOT NULL DEFAULT '[]',
  current_state text NOT NULL CHECK (current_state IN ('open','resolved','superseded','cancelled')),
  reason_codes text[] NOT NULL DEFAULT '{}',
  captured_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_escalation_state_time_idx
ON autoskill.admin_administrative_escalation_snapshots(current_state, captured_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_diagnostic_assertions (
  assertion_id text PRIMARY KEY,
  scope_type text NOT NULL CHECK (scope_type IN ('system','subsystem','component','read_model','stream','security','storage','autonomy','evidence_fidelity','raw_vault','threshold_policy','administrative_escalation')),
  scope_id text NOT NULL,
  assertion_kind text NOT NULL,
  severity_on_fail text NOT NULL CHECK (severity_on_fail IN ('info','warning','degraded','blocked','security','regression','freeze')),
  description text NOT NULL,
  evaluator_name text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_diagnostic_assertion_results (
  result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assertion_id text NOT NULL REFERENCES autoskill.admin_diagnostic_assertions(assertion_id),
  passed boolean NOT NULL,
  measured_value jsonb NOT NULL DEFAULT '{}',
  expected_value jsonb NOT NULL DEFAULT '{}',
  linked_issue_id text REFERENCES autoskill.admin_diagnostic_issues(issue_id),
  evaluated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_assertion_results_recent_idx
ON autoskill.admin_diagnostic_assertion_results(assertion_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS autoskill.admin_comparison_runs (
  comparison_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id text NOT NULL,
  comparison_kind text NOT NULL,
  left_selector jsonb NOT NULL,
  right_selector jsonb NOT NULL,
  result_summary jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_diagnostic_bundles (
  bundle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id text NOT NULL,
  scope jsonb NOT NULL,
  redaction_level text NOT NULL,
  manifest jsonb NOT NULL DEFAULT '{}',
  storage_uri text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);
```

### 13.3.1 Autonomy and evidence read models

The Observatory uses read models for autonomy and evidence state. These tables summarize canonical SkillKernel records; they do not replace raw-evidence, adjudication, decision, threshold, or audit tables.

```sql
CREATE TABLE IF NOT EXISTS autoskill.admin_evidence_fidelity_status (
  workspace_id text NOT NULL,
  source_kind text NOT NULL,
  decision_family text NOT NULL,
  evidence_fidelity text NOT NULL CHECK (evidence_fidelity IN (
    'raw_vault_linked','declassified_summary','redacted_derivative','metadata_only','hash_only','unavailable'
  )),
  item_count bigint NOT NULL DEFAULT 0,
  autonomy_support_state text NOT NULL CHECK (autonomy_support_state IN (
    'sufficient','degraded','evidence_insufficient_for_autonomy','policy_disallowed','not_applicable','unknown'
  )),
  dominant_reason_code text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, source_kind, decision_family, evidence_fidelity)
);

CREATE TABLE IF NOT EXISTS autoskill.admin_autonomy_decision_status (
  decision_id uuid PRIMARY KEY,
  workspace_id text NOT NULL,
  decision_family text NOT NULL,
  target_kind text NOT NULL,
  target_id text NOT NULL,
  action_risk_tier text NOT NULL,
  hard_invariant_state text NOT NULL,
  soft_threshold_state text NOT NULL,
  selected_action text NOT NULL,
  confidence_band text NOT NULL,
  evidence_fidelity text NOT NULL,
  autonomy_support_state text NOT NULL,
  dominant_reason_code text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS autoskill.admin_semantic_adjudication_status (
  adjudication_run_id uuid PRIMARY KEY,
  workspace_id text NOT NULL,
  decision_family text NOT NULL,
  model_profile_id uuid,
  schema_status text NOT NULL,
  confidence_band text NOT NULL,
  evidence_fidelity text NOT NULL,
  verifier_state text NOT NULL,
  raw_vault_exposure_class text NOT NULL,
  dominant_reason_code text,
  started_at timestamptz NOT NULL,
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS autoskill.admin_administrative_escalation_status (
  event_id uuid PRIMARY KEY,
  workspace_id text NOT NULL,
  hard_boundary_kind text NOT NULL,
  decision_family text NOT NULL,
  target_kind text NOT NULL,
  target_id text NOT NULL,
  attempted_autonomous_alternatives jsonb NOT NULL DEFAULT '[]'::jsonb,
  resolution_state text NOT NULL CHECK (resolution_state IN ('open','acknowledged','resolved','rejected','expired')),
  dominant_reason_code text NOT NULL,
  opened_at timestamptz NOT NULL,
  resolved_at timestamptz
);
```

### 13.4 Pipeline read model

```sql
CREATE MATERIALIZED VIEW IF NOT EXISTS autoskill.admin_mv_pipeline_component_health AS
SELECT
  c.component_id,
  c.display_name,
  c.component_group,
  c.description,
  c.details_route,
  c.sort_order,
  COALESCE(s.health, 'unknown') AS health,
  COALESCE(s.mode, 'disabled') AS mode,
  COALESCE(s.freeze_state, 'none') AS freeze_state,
  COALESCE(s.metrics, '{}'::jsonb) AS metrics,
  COALESCE(s.warnings, '[]'::jsonb) AS warnings,
  s.captured_at
FROM autoskill.admin_component_catalog c
LEFT JOIN LATERAL (
  SELECT *
  FROM autoskill.admin_component_status_snapshots s
  WHERE s.component_id = c.component_id
  ORDER BY s.captured_at DESC
  LIMIT 1
) s ON true
WHERE c.enabled = true;

CREATE UNIQUE INDEX IF NOT EXISTS admin_mv_pipeline_component_health_uidx
ON autoskill.admin_mv_pipeline_component_health(component_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS autoskill.admin_mv_subsystem_health AS
SELECT
  sc.subsystem_id,
  sc.display_name,
  sc.description,
  sc.details_route,
  sc.sort_order,
  jsonb_agg(
    jsonb_build_object(
      'component_id', ch.component_id,
      'display_name', ch.display_name,
      'health', ch.health,
      'mode', ch.mode,
      'freeze_state', ch.freeze_state,
      'metrics', ch.metrics,
      'warnings', ch.warnings,
      'captured_at', ch.captured_at
    ) ORDER BY scm.local_sort_order
  ) AS components,
  CASE
    WHEN bool_or(ch.health = 'blocked') THEN 'blocked'
    WHEN bool_or(ch.health = 'frozen') THEN 'frozen'
    WHEN bool_or(ch.health = 'degraded') THEN 'degraded'
    WHEN bool_or(ch.health = 'offline') THEN 'degraded'
    WHEN bool_and(ch.health = 'healthy') THEN 'healthy'
    ELSE 'unknown'
  END AS health,
  max(ch.captured_at) AS captured_at
FROM autoskill.admin_subsystem_catalog sc
JOIN autoskill.admin_subsystem_component_map scm ON scm.subsystem_id = sc.subsystem_id
JOIN autoskill.admin_mv_pipeline_component_health ch ON ch.component_id = scm.component_id
WHERE sc.enabled = true
GROUP BY sc.subsystem_id, sc.display_name, sc.description, sc.details_route, sc.sort_order;

CREATE UNIQUE INDEX IF NOT EXISTS admin_mv_subsystem_health_uidx
ON autoskill.admin_mv_subsystem_health(subsystem_id);
```

Refresh policy:

```text
refresh fast component snapshot tables every 2–5 seconds from in-memory sidecar state
refresh materialized aggregate views every 15–60 seconds depending on query expense
use PostgreSQL REFRESH MATERIALIZED VIEW CONCURRENTLY only when unique indexes exist and the view size justifies it
emit read_model_invalidated events after refresh
```

### 13.5 Example subsystem and component catalog seed

```sql
INSERT INTO autoskill.admin_subsystem_catalog
(subsystem_id, display_name, description, details_route, sort_order)
VALUES
('capture_bootstrap','Capture + bootstrap workcell','Live and historical source ingestion, redaction, taint, evidence-fidelity classification, and canonical normalization.','/admin/subsystems/capture_bootstrap',10),
('autonomy_adjudication','Autonomy + adjudication workcell','Evidence fidelity, raw-vault/declassification state, autonomous semantic adjudication, threshold governance, replay/canary corpus, and administrative escalation visibility.','/admin/subsystems/autonomy_adjudication',20),
('learning_memory','Learning + memory workcell','Evidence extraction, governed memory, indexing, semantic adjudication, and opportunity discovery.','/admin/subsystems/learning_memory',30),
('runtime_context','Runtime context workcell','Retrieval, broker decisions, context compilation, runtime feedback, and canaries.','/admin/subsystems/runtime_context',40),
('topology_design','Topology design workcell','Create, improve, compose, decompose, SkillIR, SkillGraphIR, and artifact planning.','/admin/subsystems/topology_design',50),
('quality_gates','Quality gates workcell','Scanner, evaluator, model profile qualification, and probe coverage.','/admin/subsystems/quality_gates',60),
('artifact_mutation','Artifact mutation workcell','Compiled packages, deterministic writes, activation locks, and rollback pointers.','/admin/subsystems/artifact_mutation',70),
('lifecycle_governance','Lifecycle governance workcell','Curation, canaries, rollback, freezes, action attribution, calibrated thresholds, administrative escalation, and administrative action control.','/admin/subsystems/lifecycle_governance',80),
('control_storage','Control + storage workcell','Scheduler, profiles, Postgres, pgvector, audit, read models, and Observatory self-health.','/admin/subsystems/control_storage',90)
ON CONFLICT (subsystem_id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  description = EXCLUDED.description,
  details_route = EXCLUDED.details_route,
  sort_order = EXCLUDED.sort_order,
  updated_at = now();

INSERT INTO autoskill.admin_component_catalog
(component_id, display_name, component_group, description, details_route, sort_order)
VALUES
('openclaw_live_capture','OpenClaw live capture','ingestion','Plugin hook and SDK-event capture from active OpenClaw sessions.','/admin/components/openclaw_live_capture',10),
('historical_ingestion','Historical bootstrap','ingestion','Discovery and ingestion of existing deployment data.','/admin/components/historical_ingestion',20),
('redaction_taint','Redaction + taint','ingestion','Sensitive-data handling, taint propagation, trust labeling, and storage eligibility.','/admin/components/redaction_taint',30),
('raw_evidence_vault','Raw-evidence vault','autonomy','Governed full-fidelity evidence retention, raw/declassified access policy, raw-access audit, retention, revocation, and derived-data traversal.','/admin/components/raw_evidence_vault',40),
('evidence_fidelity','Evidence fidelity','autonomy','Evidence-fidelity tiers and supported decision-family matrix.','/admin/components/evidence_fidelity',45),
('spool_ingest','Spool + ingest','ingestion','Plugin spool, batch forwarding, sidecar ingest, and idempotency.','/admin/components/spool_ingest',50),
('event_normalization','Event normalization','ingestion','Canonical event and chunk normalization.','/admin/components/event_normalization',60),
('evidence_memory','Evidence + memory','intelligence','Evidence extraction, memory derivation, maturity, and provenance.','/admin/components/evidence_memory',70),
('semantic_adjudication','LLM semantic adjudication','autonomy','LLM semantic verdicts, intent synthesis, memory declassification, topology choice, external-skill relationships, and context-equivalence adjudication.','/admin/components/semantic_adjudication',80),
('autonomy_orchestrator','Autonomy decision orchestrator','autonomy','Calibrated selective-trust decisions, soft-threshold policy, fallback ladders, policy trials, threshold-deadlock findings, and selected autonomous actions.','/admin/components/autonomy_orchestrator',90),
('replay_corpus','Replay + canary corpus','autonomy','Replay episode synthesis, redacted intent, expected decisions, canary eligibility, and corpus evidence coverage.','/admin/components/replay_corpus',95),
('retrieval_indexing','Retrieval + indexing','intelligence','Lexical/vector/metadata/graph indexing and retrieval calibration.','/admin/components/retrieval_indexing',100),
('broker_runtime','Runtime broker','runtime','Skill-context selection, no-skill decisions, and shadowing control.','/admin/components/broker_runtime',110),
('opportunity_mining','Opportunity miner','intelligence','Candidate discovery for skill topology operations.','/admin/components/opportunity_mining',120),
('topology_operations','Topology operations','operations','Create, improve, compose, decompose, and lifecycle support operations.','/admin/components/topology_operations',130),
('skill_ir_graph_ir','SkillIR / SkillGraphIR','operations','Canonical skill representation and graph workflow topology.','/admin/components/skill_ir_graph_ir',140),
('artifact_planner','Skill package planner','artifact','Ancillary artifact selection and package planning.','/admin/components/artifact_planner',150),
('context_compiler','Context compiler','artifact','AI-facing context compilation and token-budget governance.','/admin/components/context_compiler',160),
('scanner_security','Scanner + security','gates','Static, semantic, capability, artifact, and bundle scanning.','/admin/components/scanner_security',170),
('evaluator_probes','Evaluator + probes','gates','Regression-aware evaluation and probe-bank execution.','/admin/components/evaluator_probes',180),
('deterministic_writer','Deterministic writer','artifact','Path-contained staged writes, manifests, and activation locks.','/admin/components/deterministic_writer',190),
('activation_curation','Activation + curation','lifecycle','Active/archive/promotion and skill-library curation.','/admin/components/activation_curation',200),
('canary_rollback','Canary + rollback','lifecycle','Post-activation observation, rollback, freeze, and revocation.','/admin/components/canary_rollback',210),
('administrative_escalation','Administrative escalation','autonomy','Exceptional authority-boundary cases, attempted autonomous alternatives, escalation reason codes, and resolution state.','/admin/components/administrative_escalation',220),
('scheduler_jobs','Scheduler + jobs','control','Sidecar-owned schedules, leases, attempts, and queue health.','/admin/components/scheduler_jobs',230),
('model_embedding','Model + embedding profiles','control','Configured text LLM and embedding profile health.','/admin/components/model_embedding',240),
('storage_db','Postgres + pgvector','storage','Database, indexes, materialized views, retention, and pgvector health.','/admin/components/storage_db',250),
('audit_trace','Audit + trace spine','control','Cross-system correlation, audit chain, provenance, and action attribution.','/admin/components/audit_trace',260),
('administrative_action_gateway','Administrative action gateway','control','Role checks, confirmations, idempotency, guarded action dispatch, and action audit links.','/admin/components/administrative_action_gateway',270),
('observatory_admin','Observatory self-health','control','Admin API, frontend serving, live streams, read models, and dashboard performance.','/admin/components/observatory_admin',280)
ON CONFLICT (component_id) DO UPDATE SET
  display_name = EXCLUDED.display_name,
  component_group = EXCLUDED.component_group,
  description = EXCLUDED.description,
  details_route = EXCLUDED.details_route,
  sort_order = EXCLUDED.sort_order,
  updated_at = now();

INSERT INTO autoskill.admin_subsystem_component_map
(subsystem_id, component_id, local_sort_order, role)
VALUES
('capture_bootstrap','openclaw_live_capture',10,'source'),
('capture_bootstrap','historical_ingestion',20,'source'),
('capture_bootstrap','redaction_taint',30,'gate'),
('capture_bootstrap','raw_evidence_vault',35,'vault'),
('capture_bootstrap','evidence_fidelity',37,'fidelity'),
('capture_bootstrap','spool_ingest',40,'transport'),
('capture_bootstrap','event_normalization',50,'normalizer'),
('learning_memory','evidence_memory',10,'memory'),
('learning_memory','evidence_fidelity',15,'fidelity'),
('learning_memory','semantic_adjudication',18,'adjudicator'),
('learning_memory','retrieval_indexing',20,'index'),
('learning_memory','opportunity_mining',30,'miner'),
('autonomy_adjudication','raw_evidence_vault',10,'vault'),
('autonomy_adjudication','evidence_fidelity',20,'fidelity'),
('autonomy_adjudication','semantic_adjudication',30,'adjudicator'),
('autonomy_adjudication','autonomy_orchestrator',40,'orchestrator'),
('autonomy_adjudication','replay_corpus',50,'corpus'),
('autonomy_adjudication','model_embedding',60,'model_profile'),
('autonomy_adjudication','audit_trace',70,'audit'),
('runtime_context','retrieval_indexing',10,'retriever'),
('runtime_context','broker_runtime',20,'broker'),
('runtime_context','context_compiler',30,'compiler'),
('runtime_context','canary_rollback',40,'feedback'),
('topology_design','opportunity_mining',10,'miner'),
('topology_design','topology_operations',20,'planner'),
('topology_design','skill_ir_graph_ir',30,'ir'),
('topology_design','artifact_planner',40,'package_planner'),
('quality_gates','scanner_security',10,'scanner'),
('quality_gates','evaluator_probes',20,'evaluator'),
('quality_gates','replay_corpus',25,'corpus'),
('quality_gates','model_embedding',30,'profile_health'),
('artifact_mutation','artifact_planner',10,'package_planner'),
('artifact_mutation','context_compiler',20,'compiler'),
('artifact_mutation','scanner_security',30,'scanner'),
('artifact_mutation','evaluator_probes',40,'evaluator'),
('artifact_mutation','deterministic_writer',50,'writer'),
('artifact_mutation','activation_curation',60,'activator'),
('artifact_mutation','canary_rollback',70,'rollback'),
('lifecycle_governance','activation_curation',10,'curator'),
('lifecycle_governance','canary_rollback',20,'canary'),
('lifecycle_governance','autonomy_orchestrator',25,'orchestrator'),
('lifecycle_governance','audit_trace',30,'audit'),
('lifecycle_governance','administrative_escalation',35,'escalation'),
('lifecycle_governance','administrative_action_gateway',40,'action_gateway'),
('control_storage','scheduler_jobs',10,'scheduler'),
('control_storage','model_embedding',20,'profiles'),
('control_storage','storage_db',30,'storage'),
('control_storage','audit_trace',40,'audit'),
('control_storage','observatory_admin',50,'admin_surface')
ON CONFLICT (subsystem_id, component_id) DO UPDATE SET
  local_sort_order = EXCLUDED.local_sort_order,
  role = EXCLUDED.role;
```

---

## 14. Frontend implementation

### 14.1 Package layout

```text
sidecar/
  app/
    admin_api/
      __init__.py
      routes.py
      auth.py
      schemas.py
      streams.py
      readmodels.py
      actions.py
      static.py
    observability/
      admin_events.py
      component_health.py
      read_model_refresh.py
      notify_bridge.py
  web/
    package.json
    vite.config.ts
    index.html
    src/
      main.tsx
      App.tsx
      routes.tsx
      api/
        client.ts
        generated.ts
        liveStream.ts
      state/
        queryClient.ts
        useLiveDeltas.ts
      components/
        layout/
        pipeline/
        charts/
        cockpit/
        tables/
        dialogs/
        diff/
      pages/
        OverviewPage.tsx
        ComponentPage.tsx
        SkillsPage.tsx
        SkillDetailPage.tsx
        TopologyPage.tsx
        TraceReplayPage.tsx
        JobsPage.tsx
        HistoricalImportsPage.tsx
        SecurityPage.tsx
        StoragePage.tsx
        SettingsPage.tsx
      viz/
        reactFlowTheme.ts
        elkLayout.ts
        particleOverlay.ts
        echartsOptions.ts
      styles/
        tokens.css
        app.css
```

### 14.2 State management and incremental reconciliation

Use TanStack Query for authenticated API snapshots, cache ownership, retries, background synchronization, and explicit query invalidation. Use a normalized frontend entity layer for hot live dashboard state. This layer may be implemented with TanStack Query `setQueryData`, a small reducer/store, or another minimal observable store, but it must obey the same identity and patching rules.

Live updates are applied as narrow patches:

```text
snapshot -> normalize by entity type and stable ID
live delta -> validate sequence/schema -> patch normalized entities
background snapshot -> entity-level merge -> preserve unchanged references
view selectors -> derive route-specific arrays/graphs/charts
visible components -> receive stable IDs and memoized data slices
```

The state layer must separate three concerns:

| State class | Examples | Persistence rule |
|---|---|---|
| Server state | station metrics, jobs, issues, skills, traces, evaluations, read-model freshness | Owned by API snapshot/delta cache. |
| View state | selected tab, selected node, graph viewport, filters, expanded cards, scroll position, drawer state, replay cursor | Owned by route/local UI state and preserved across ordinary data refresh. |
| Ephemeral animation state | particles, pulse timers, transition progress, hover state | Owned by visual layer and never authoritative. |

Example query keys:

```text
['summary']
['pipeline']
['component', componentId]
['componentMetrics', componentId, window]
['skills', filters]
['skill', skillId]
['topology', mode, filters]
['trace', traceId]
['jobs', filters]
['historicalImport', importRunId]
['scannerFindings', filters]
['evaluations', filters]
['storage']
```

Query behavior requirements:

- keep previous data visible during background refetch;
- show loading skeletons only for first load or truly unavailable data;
- apply `queryClient.setQueryData` or equivalent entity patches for deltas that can be applied safely;
- invalidate only the smallest affected query scope when a delta cannot be patched;
- avoid broad invalidations such as “invalidate all dashboard queries” for ordinary station metric changes;
- preserve structural sharing for JSON-compatible unchanged subtrees;
- avoid transforming API results into new object graphs on every render;
- memoize derived arrays, graph nodes, chart series, and table rows from normalized state;
- never use `snapshot_seq`, refresh timestamp, polling counter, or random value as a React `key` for visible operational components.

Selector requirements:

- components subscribe only to the data slices they display;
- high-frequency metrics use narrow selectors and throttled visual updates;
- route shells do not subscribe to all dashboard entities;
- graph nodes receive stable `componentId` and changed metric props only;
- unrelated station updates do not force every station cockpit, chart, or object microscope to remount.

A background read-model refresh is represented as a data-change event, not a navigation event. The currently selected route remains mounted, and the reducer reconciles records into the existing view.

### 14.2.1 Live delta reducer contract

Every delta reducer must be pure, deterministic, and testable.

Delta envelope handling:

```ts
export type LiveDeltaEnvelope<T> = {
  api_version: string;
  delta_version: number;
  seq: number;
  emitted_at: string;
  scope: 'global' | 'subsystem' | 'component' | 'object' | 'topology' | 'read_model';
  entity_type: string;
  entity_id?: string;
  operation: 'upsert' | 'patch' | 'delete' | 'invalidate' | 'topology_change' | 'sequence_gap';
  payload: T;
};
```

Reducer behavior:

```text
upsert       -> add new entity or merge changed fields into existing entity
patch        -> update only listed fields; preserve unchanged nested references where practical
delete       -> remove entity or mark terminal state according to object type
invalidate  -> mark affected query/read model stale and refetch without clearing prior data
topology_change -> recompute graph structure only for affected topology scope
sequence_gap -> request scoped snapshot reload and preserve view state
```

Reducers must never implement a refresh by setting the visible entity collection to empty before loading replacement data. Empty arrays are valid only when the authoritative response says the collection is empty.

### 14.2.2 Render identity contract

Visible components must use stable keys and stable component types. React component identity is based on position and key; changing keys intentionally resets state, so keys are reserved for true identity changes, not refresh metadata.

Correct patterns:

```tsx
<StationNode key={component.componentId} componentId={component.componentId} />
<SkillRow key={skill.skillId} skillId={skill.skillId} />
<IssueCard key={issue.issueId} issueId={issue.issueId} />
```

Incorrect patterns:

```tsx
<StationNode key={`${component.componentId}:${snapshotSeq}`} />
<PipelineGraph key={lastRefreshAt} />
<OverviewPage key={Date.now()} />
```

Custom node types, chart option factories, column definitions, and route component definitions must be module-level constants or memoized values. Recreating component types inside render can cause remount behavior and visible flashes.


### 14.3 Global search and command palette implementation

The command palette is keyboard-accessible and available from every route.

Required behavior:

- open with `Ctrl+K` / `Cmd+K`;
- search through `/admin/api/v1/search`;
- show object type, redacted title, state, dominant reason code, and timestamp;
- never expose raw content in result labels;
- support quick navigation to subsystem, component, trace, job, skill, candidate, issue, artifact, import run, scanner finding, evaluation, broker decision, audit action, and reason-code pages;
- support quick filter commands such as `lens:security`, `state:blocked`, `skill:frozen`, `reason:READ_MODEL_STALE`;
- expose only actions allowed for the actor role and require normal action confirmations.

The search palette is a navigation and filtering surface, not an alternate action executor. Any mutating command dispatches through the guarded action gateway.

### 14.4 React Flow graph implementation

Use React Flow for structural graph interaction. The React Flow instance is a long-lived view object for the current route, not a disposable rendering target that is recreated on every refresh. React Flow supplies the interaction substrate; Observatory supplies the visual design.

The main overview must use custom node and edge renderers. Custom nodes are normal React components, which allows station cards to render the exact compact diagnostics, icons, status halos, badges, micro-metrics, and accessibility labels required by Observatory. Custom edges and labels are used to distinguish flow purpose, pressure, selection, warnings, and trace replay without relying on default diagram styling.

#### 14.4.1 Overview theme tokens

The graph must consume deterministic theme tokens instead of hardcoded colors scattered through node components. Required token families:

```text
--sk-bg-canvas
--sk-bg-canvas-grid
--sk-bg-lane
--sk-bg-node
--sk-bg-node-muted
--sk-border-node
--sk-border-selected
--sk-edge-default
--sk-edge-active
--sk-edge-muted
--sk-edge-label-bg
--sk-health-healthy
--sk-health-degraded
--sk-health-blocked
--sk-health-frozen
--sk-health-offline
--sk-health-unknown
--sk-risk-security
--sk-risk-regression
--sk-risk-context
--sk-freshness-stale
--sk-motion-flow-speed
--sk-motion-pulse-opacity
--sk-shadow-node
--sk-shadow-critical
```

Node, edge, particle, chart, issue-board, and cockpit colors must derive from the same semantic token set so the overview does not look disconnected from the rest of the interface.

#### 14.4.2 Custom station-node requirements

Each station node in the overview renders as a compact diagnostic card:

```text
┌──────────────────────────────┐
│ icon  Station Name   status  │
│ queue  latency  errors       │
│ throughput sparkline / strip │
│ warnings blocked freshness   │
└──────────────────────────────┘
```

Required node states:

```text
default | hover | selected | focused | upstream-highlight | downstream-highlight | muted | stale | degraded | blocked | frozen | offline
```

Required node behaviors:

- hover reveals concise tooltip and emphasizes directly connected edges;
- selection preserves viewport and opens the details drawer/cockpit link;
- keyboard focus is visible and works without pointer input;
- stale telemetry is visually different from healthy idle;
- blocked/frozen/security/regression states are not represented by color alone;
- micro-metrics animate by value interpolation only when reduced-motion is disabled.

#### 14.4.3 Custom edge and label requirements

Edges must communicate more than topology. Each edge has a purpose, flow direction, health/freshness state, and optional pressure metric.

Required edge classes:

```text
event_flow
historical_import_flow
evidence_flow
retrieval_flow
broker_context_flow
topology_operation_flow
artifact_transaction_flow
scanner_gate_flow
evaluator_gate_flow
activation_flow
rollback_flow
revocation_flow
storage_control_flow
```

Edge rendering rules:

- line thickness/intensity reflects bounded pressure or throughput buckets, not raw unbounded values;
- labels use short stable purpose names plus optional metric badge;
- selected edge highlights upstream source and downstream destination;
- warning/security/regression/frozen flows use distinct stroke pattern plus label icon;
- edge pulse speed is capped and disabled in reduced-motion mode;
- labels avoid excessive overlap at default zoom through lane routing, label offset rules, and zoom-dependent abbreviation;
- clicking an edge opens the flow detail panel with backing records.

Required features:

- custom node components by station group;
- custom edges with animated path styles;
- MiniMap always visible on large screens;
- Controls for zoom/fit/lock;
- panel overlays for search, mode switcher, legend, timeline;
- ELK.js layout for left-to-right layered pipeline;
- manual pinning of lanes for stable mental model;
- nested subflows for component cockpits;
- viewport synchronization with PixiJS overlay.

Node data contract:

```ts
export type PipelineNodeData = {
  componentId: string;
  displayName: string;
  group: 'ingestion' | 'intelligence' | 'operations' | 'artifact' | 'gates' | 'lifecycle' | 'runtime' | 'control' | 'storage';
  health: 'healthy' | 'degraded' | 'blocked' | 'frozen' | 'offline' | 'unknown';
  mode: 'active' | 'read_only' | 'dry_run' | 'paused' | 'maintenance' | 'disabled';
  queueDepth: number;
  inputRate1m: number;
  outputRate1m: number;
  p95LatencyMs: number;
  errorRate15m: number;
  tokenPressure?: number;
  riskPressure?: number;
  warningCount: number;
  blockedCount: number;
  detailsUrl: string;
};
```

React Flow update rules:

```text
node.id = stable component_id/station_id
edge.id = stable source-target-purpose identifier
node.type = stable station renderer type
node.position = preserved unless topology layout changes
node.data = replaced only when that node's displayed data changes
edges = patched by stable edge ID
layout = recalculated only for topology changes, not metric changes
viewport = preserved across all ordinary live updates
selection = preserved when selected object still exists
```

Metric-only station updates must update the relevant node’s `data` object and edge metric fields without rebuilding the entire node/edge array from scratch in a way that changes every object reference. React Flow supports updating node and edge properties when new arrays are passed, but changed node data must be represented as a new `data` object for the affected node so the node updates correctly.

Recommended patch pattern:

```ts
function patchNodeMetric(nodes: Node<PipelineNodeData>[], patch: Partial<PipelineNodeData> & { componentId: string }) {
  return nodes.map((node) => {
    if (node.id !== patch.componentId) return node;
    return {
      ...node,
      data: {
        ...node.data,
        ...patch,
      },
    };
  });
}
```

The layout engine receives topology snapshots, not high-frequency metrics. It runs when:

```text
station added
station removed
edge added
edge removed
subsystem/workcell membership changed
operator requests fit/re-layout
graph mode changes in a way that changes structure
```

It does not run when:

```text
queue depth changes
health changes
latency changes
throughput changes
warning count changes
risk/context pressure changes
background read-model refresh changes timestamps only
```

Custom node components must be memoized and receive stable primitive props where practical. Large diagnostic panels inside nodes must subscribe to their own entity slices rather than forcing the whole graph to repaint.


### 14.5 PixiJS particle and effects overlay

The PixiJS overlay provides the high-density visual effects that would be too expensive or awkward to render as React DOM nodes. It is used for particles, glow bursts, flow shimmer, lane ambience, replay traces, and short-lived event effects. The structural graph remains React Flow; the overlay is never authoritative.

The overlay is optional at runtime but required as part of the full visual design when the browser and operator settings permit it. If unavailable, the UI degrades to CSS/SVG effects while preserving all meaning.

Rules:

- render particles in a separate absolute-positioned canvas over the React Flow viewport;
- use viewport transform to map graph coordinates into canvas coordinates;
- do not store authoritative state in PixiJS objects;
- recreate particles from the live event buffer and edge geometry;
- cap active particles per viewport;
- degrade to CSS/SVG edge animation when WebGL/WebGPU is unavailable;
- obey reduced-motion mode.

Particle generation policy:

```text
high-priority events generate visible particles immediately
low-priority high-frequency events are sampled
aggregate metrics modify edge animation rather than generating every raw event
security/rollback/freeze particles are never sampled away
```


Visual-effect budgets:

| Budget | Requirement |
|---|---|
| Particle count | Hard cap by viewport and deployment config; default cap applies before any browser slowdown is visible. |
| Spawn rate | Sample low-priority events; aggregate noisy streams into edge intensity. |
| Lifetime | Short-lived effects expire predictably and return objects to pools. |
| Draw calls | Prefer batched sprites/graphics and shared textures/materials. |
| Quality mode | `high`, `balanced`, `low`, and `off` modes select particle density, blur/glow intensity, and transition duration. |
| Browser visibility | Pause the ticker or reduce to heartbeat mode when the document is hidden. |
| Failure mode | Overlay errors disable the effects layer and create an Observatory self-health issue; they do not break the graph. |

PixiJS must not render labels, menus, tooltips, accessibility semantics, or the canonical node/edge structure. Those remain DOM/SVG responsibilities so the interface stays inspectable, searchable, and accessible.

### 14.6 ECharts visualizations

Use ECharts for:

- line charts;
- latency histograms;
- heatmaps;
- treemaps;
- Sankey diagrams;
- funnel charts;
- graph charts for local dependency views where React Flow interaction is unnecessary;
- calendar heatmaps;
- timeline charts;
- radar/scorecard charts for bounded multidimensional summaries such as fitness, qualification, or gate coverage.

Charts must support:

- fixed time windows;
- hover tooltips with exact values;
- click-to-filter;
- export to PNG/SVG where safe;
- no raw-sensitive content in chart labels;
- keyboard-accessible underlying data tables.

Chart update rules:

```text
initialize chart instance once when the chart component mounts
call setOption or the chart wrapper's equivalent to update series/options
use stable series IDs/names and data point names where chart type supports diffing
preserve user state such as legend selection, dataZoom, hover/crosshair, and time-window selection where practical
do not dispose/reinitialize chart instances on ordinary data refresh
do not blank chart containers between refreshes
throttle high-frequency chart updates and coalesce low-priority points
```

ECharts performs data transitions by diffing updated option data against prior data when stable identifiers are available. The implementation must use that behavior for live charts rather than recreating chart components on each poll.

### 14.7 Monaco inspection

Use Monaco in read-only mode for:

- SkillIR JSON;
- SkillGraphIR JSON;
- `.autoskill-manifest.json`;
- `SKILL.md` compiled artifact preview;
- schema files;
- redacted tool/probe fixtures;
- diff views between versions.

Monaco must not be used as an editing surface. Operator edits to skill files are outside the web-admin scope.

---

## 15. Visual design system

### 15.1 Design language

The interface communicates a living autonomous factory:

```text
dark command center
subtle grid background
station cards as machine modules
flow particles as work items
health rings as station status
edge glow as throughput
warning bands as backpressure
trace replay as animated path lighting
context pressure as a budget heat overlay
security risk as containment shields and quarantine zones
```

### 15.2 Theme tokens

Example token names:

```css
:root {
  --sk-bg-root: #05070c;
  --sk-bg-panel: #0b1020;
  --sk-bg-panel-elevated: #11182a;
  --sk-text-primary: #f4f7fb;
  --sk-text-muted: #9ca8bd;
  --sk-accent-live: #4dd4ff;
  --sk-accent-skill: #a78bfa;
  --sk-accent-success: #37d67a;
  --sk-accent-warning: #fbbf24;
  --sk-accent-danger: #fb7185;
  --sk-accent-frozen: #94a3b8;
  --sk-edge-idle: rgba(148, 163, 184, 0.45);
  --sk-edge-active: rgba(77, 212, 255, 0.85);
  --sk-shadow-glow: 0 0 24px rgba(77, 212, 255, 0.25);
}
```

Colors must not be the only status indicator. Use icon, label, shape, pattern, and tooltip.

### 15.3 Motion rules

Motion clarifies state:

- flow direction;
- recent activation;
- active trace replay;
- warning escalation;
- freeze/rollback events;
- queue backpressure.

Motion must not distract:

- particles capped;
- background animation subtle;
- reduced-motion mode supported;
- no infinite high-flash animations;
- no status implied only by animation.

### 15.4 Responsive layout

Desktop is the primary target. Laptop and tablet are supported. Mobile is read-only and simplified.

Breakpoints:

| Viewport | Behavior |
|---|---|
| large desktop | full assembly-line graph, side drawer, charts, minimap. |
| laptop | graph plus collapsible drawers. |
| tablet | graph simplified, station list available. |
| mobile | KPI list, station cards, no complex topology editing. |

### 15.5 Accessibility and operability

The Observatory must remain usable by operators who cannot rely on motion, color, fine pointer control, or GPU acceleration.

Requirements:

- meet WCAG 2.2 AA intent for contrast, focus visibility, keyboard operation, non-color status communication, text alternatives, and motion reduction;
- every graph view has a list/table equivalent with the same records, statuses, and links;
- every chart has an accessible data table or summary;
- every status uses label, icon/shape, tooltip, and reason code in addition to color;
- every interactive node and edge is keyboard reachable when rendered as DOM/SVG;
- PixiJS effects are optional and never required to understand state;
- reduced-motion mode disables particle effects, flashing, and animated transitions while preserving all state changes through static labels and badges;
- large graph clustering exposes expansion controls and searchable node lists;
- loading, stale, disconnected, and permission-limited states use explicit text, not only visual styling.

Accessibility is part of diagnostic correctness. A dashboard that hides meaning behind color, animation, or canvas-only graphics is not acceptable for SkillKernel soak testing.

---

## 16. Security and privacy requirements

### 16.1 Content safety

The admin UI is itself a sensitive data surface.

Rules:

1. Redacted content is the default.
2. Raw content endpoints are disabled by default.
3. Raw-vault records are displayed as metadata, redacted preview, or declassification report unless a policy-checked reveal token is issued.
4. Raw reveal requires explicit config, admin role, reason, short-lived reveal token, minimum-necessary scope, and audit record.
5. No secrets appear in frontend logs, browser storage, query strings, or chart labels.
6. API keys, provider tokens, and filesystem paths are masked except for safe basename/path-class views.
7. Artifacts are previewed through policy-checked API endpoints, not direct filesystem serving.
8. Downloaded diagnostic bundles are redacted by default.
9. HTML rendering of stored text must be escaped/sanitized; no stored Markdown/HTML from evidence is rendered as trusted HTML.
10. Monaco previews render text/code only, not executable content.
11. External links are disabled or opened with `rel="noopener noreferrer"` and explicit warning when enabled.
12. Saved diagnostic views and operator annotations store redacted text and non-secret filter state only.

### 16.2 Browser-side storage

Do not store sensitive data in browser local storage.

Allowed:

- non-sensitive UI preferences;
- collapsed panels;
- last selected visual mode;
- non-secret theme setting.

Not allowed:

- bearer tokens unless unavoidable and explicitly configured;
- raw content;
- exported trace data;
- API keys;
- provider configuration secrets;
- unredacted artifacts.

### 16.3 Action audit

Every administrative action records:

```text
actor identity
roles
source IP / proxy identity when available
action kind
target type/id
request id
idempotency key
reason
confirmation payload hash
result
linked job/audit/evolution transaction
created_at
```

### 16.4 Abuse and failure protection

- rate-limit action endpoints;
- rate-limit raw reveal endpoints;
- cap WebSocket connections per actor;
- cap query ranges;
- reject unbounded regex searches;
- require POST with CSRF token for browser actions;
- enforce read-only mode during sidecar degraded state if policy says so;
- fail closed if auth backend is unavailable.

### 16.5 Browser hardening

The sidecar serves the admin app with restrictive browser security headers:

```text
Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
```

The frontend bundle is self-contained. It must not call CDNs, analytics services, font hosts, telemetry vendors, or third-party image endpoints. Diagnostic exports are generated server-side through authenticated endpoints, not by leaking browser state to external services.

---

## 17. Performance and reliability

### 17.1 Dashboard performance targets

| Target | Requirement |
|---|---|
| Initial overview load | less than 3 seconds on a normal local deployment with warm read models. |
| Live update latency | p95 less than 2 seconds from sidecar event to browser update for dashboard events. |
| Component page load | less than 2 seconds for default 24-hour summary. |
| Trace detail load | less than 5 seconds for ordinary traces under 5,000 linked records. |
| UI frame rate | maintain interactive pan/zoom above 30 FPS on ordinary laptop hardware for default graph size. |
| Live-refresh visual stability | no visible full-route flash, graph blanking, chart blanking, viewport reset, or selected-object loss during ordinary refresh/delta cycles. |
| Station update stability | a metric update for one station must not remount unrelated station nodes, charts, cockpits, or object microscope views. |
| Large graph mode | degrade gracefully with clustering/sampling above 1,000 topology nodes. |
| Backend query timeout | default 10 seconds for read endpoints, lower where possible. |

### 17.2 Backpressure

The admin live stream must not backpressure core SkillKernel processing.

Rules:

- if browser falls behind, drop low-priority deltas and force snapshot reload;
- never block scheduler/jobs on admin streaming;
- store only bounded outbox history;
- sample high-frequency metrics;
- aggregate noisy events into component pressure metrics;
- prioritize critical events: freeze, rollback, activation, scanner hard finding, evaluator regression failure, DB unhealthy.

### 17.3 Read-model refresh

Read models refresh through sidecar jobs.

Refresh classes:

| Class | Cadence |
|---|---|
| component status snapshots | 2–5 seconds |
| live queue/job rollups | 5–15 seconds |
| overview metrics | 10–30 seconds |
| historical import rollups | 15–60 seconds |
| skill topology graph | 30–120 seconds or event-invalidated |
| large retention/storage summaries | 5–30 minutes |
| audit chain verification | on demand and scheduled daily |

Cadences are configurable. Every read model exposes freshness in the UI. A read-model refresh updates the frontend data model; it must not imply clearing or remounting the visible route.

### 17.4 Data-quality and confidence display

Every aggregate and chart exposes data confidence:

| Confidence state | Meaning | UI behavior |
|---|---|---|
| complete | Required sources are fresh and coverage is within policy. | Normal rendering. |
| partial | Some sources are missing, sampled, or delayed. | Show warning badge and affected sources. |
| stale | Read model or source telemetry exceeds freshness budget. | Show stale overlay and link to self-health. |
| redacted | Content or metrics are intentionally reduced. | Show redaction badge and explain limits. |
| low_sample | Too few records for a reliable trend. | Suppress misleading trend arrows. |
| unknown | Required telemetry is absent. | Render unknown, never healthy. |

Charts with partial or stale data display the limitation in the chart header.


### 17.5 Live-render stability

The dashboard must remain visually stable during ordinary refresh. This requirement is separate from data freshness. A dashboard can receive fresh data and still be defective if it repeatedly clears and rebuilds the visible UI.

Implementation requirements:

- route components remain mounted while their selected route/tab remains active;
- React keys are stable domain IDs;
- graph viewport, zoom, pan, selection, pinned lanes, and open drawers persist across data updates;
- chart instances persist across data updates;
- tables preserve scroll position, sort, filters, selected row, and expanded rows when corresponding objects still exist;
- station cards update text, badges, gauges, and animations in place;
- background refetch never swaps the current route body for a global spinner when previous data exists;
- skeletons appear only for first load or unavailable regions;
- sequence-gap recovery is scoped and visibly explained through Observatory self-health.

Instrumentation requirements:

- development builds expose optional render/mount counters for overview graph, station node, subsystem lane, chart, and cockpit components;
- the Observatory self-health page records snapshot reload counts, scoped invalidation counts, full-route remount counts, graph layout recomputation counts, chart reinitialization counts, and sequence-gap recoveries;
- a periodic full-route remount without navigation, schema incompatibility, or sequence-gap recovery is classified as an Observatory defect;
- a chart or graph instance reinitialized during an ordinary metric update is classified as an Observatory defect.

Suggested self-health counters:

```text
overview_route_mount_count
overview_route_unexpected_remount_count
pipeline_graph_instance_recreated_count
pipeline_layout_recompute_count
station_node_mount_count_by_component
chart_instance_recreated_count_by_chart
background_refetch_count
scoped_snapshot_reload_count
sequence_gap_recovery_count
full_page_loading_state_count_after_initial_load
```

The UI must be capable of proving that live updates are incremental. The proof comes from counters, tests, and visible behavior.


---

## 18. Configuration

```yaml
web_admin:
  enabled: true
  bind_host: "127.0.0.1"
  bind_port: 8757
  base_path: "/admin"
  public_url: null

  auth:
    mode: "bearer_token"
    token_env: "SKILLKERNEL_ADMIN_TOKEN"
    session_cookie_name: "skillkernel_admin"
    session_ttl_minutes: 720

  roles:
    default_role: "viewer"
    local_token_role: "admin"

  raw_content:
    enabled: false
    require_reason: true
    reveal_ttl_seconds: 300

  evidence_and_autonomy:
    show_evidence_fidelity_lens: true
    show_raw_vault_policy_state: true
    show_llm_adjudication_details: true
    show_threshold_policy_versions: true
    show_administrative_escalations: true
    default_raw_vault_detail_mode: "redacted"   # redacted | metadata_only
    raw_vault_reveal_requires_admin: true
    adjudication_payload_mode: "redacted_structured"
    replay_corpus_preview_enabled: true

  streams:
    websocket_enabled: true
    sse_enabled: true
    max_connections_per_actor: 5
    outbox_retention_minutes: 60
    low_priority_sampling_rate: 0.25

  read_models:
    component_status_interval_seconds: 5
    overview_interval_seconds: 15
    topology_interval_seconds: 60
    storage_interval_seconds: 300

  visuals:
    particles_enabled_default: true
    particle_quality_default: "balanced"      # high | balanced | low | off
    max_particles: 1500
    max_particle_spawn_rate_per_second: 120
    flow_animation_enabled_default: true
    node_glow_enabled_default: true
    adaptive_visual_quality: true
    reduced_motion_default: false
    low_power_mode_default: false
    webgl_required: false
    large_graph_node_limit: 1000
    overview_visual_theme: "command_surface"

  actions:
    enabled: true
    require_idempotency_key: true
    require_reason: true
    high_impact_confirmation: true

  security:
    csrf_enabled: true
    cors_allowed_origins: []
    frame_ancestors: "'none'"
    content_security_policy_enabled: true
    diagnostics_downloads_enabled: true
```

Content Security Policy baseline:

```text
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
connect-src 'self' ws: wss:;
font-src 'self';
object-src 'none';
base-uri 'self';
frame-ancestors 'none';
```

If the deployment uses a reverse proxy and TLS termination, update `connect-src` and trusted proxy settings accordingly.

---

## 19. Implementation phases

### Phase 1 — Admin backend foundation

Deliverables:

- FastAPI admin router mounted in sidecar;
- auth middleware;
- role checks;
- OpenAPI schema;
- static frontend serving;
- common response envelopes;
- audit table;
- component catalog;
- component health snapshots;
- initial summary and pipeline endpoints;
- health/readiness endpoints.

Acceptance:

- authenticated dashboard shell loads from sidecar;
- `/summary` and `/pipeline` return real data;
- all endpoints enforce auth except configured liveness;
- action audit can record no-op test action.

### Phase 2 — Read models and live stream

Deliverables:

- dashboard read-model refresh service;
- WebSocket `/admin/live`;
- optional SSE `/admin/live-sse`;
- Postgres notification bridge;
- live event outbox;
- snapshot-plus-delta reconciliation;
- frontend live delta hook.

Acceptance:

- component status changes appear in UI without manual refresh, full-route remount, graph blanking, or selected-object loss;
- missed sequence triggers scoped safe snapshot reload;
- admin stream failure does not affect core jobs.

### Phase 3 — Visual overview

Deliverables:

- React/Vite/TypeScript app shell;
- React Flow assembly-line graph;
- ELK layout;
- custom station cards;
- custom semantic edges and label chips;
- overview theme tokens;
- subsystem lane rails and polished command-surface background;
- edge metrics;
- KPI ribbon;
- bottom drawer;
- basic visual modes;
- search and minimap;
- reduced-motion mode.

Acceptance:

- all pipeline stations render;
- the overview graph does not use default/plain library-demo node and edge styling;
- station cards, lane rails, edge labels, status halos, and selected/hover/focus states match the Observatory design system;
- clicking station opens a real station cockpit shell with live component health data;
- health/latency/backlog overlays reflect read models;
- overview remains responsive on expected graph size.

### Phase 4 — Component cockpits

Deliverables:

- station cockpit framework;
- common tabs;
- component-specific panels for ingestion, historical import, redaction, evidence, retrieval, broker, topology, compiler, scanner, evaluator, writer, scheduler, model/profile, storage, audit;
- charts with ECharts;
- tables with pagination/cursors;
- Monaco read-only viewers.

Acceptance:

- every station has a meaningful drill-down page;
- each cockpit shows records, metrics, traces, config, audit, and help;
- no cockpit performs unbounded raw-table queries.

### Phase 5 — Skill and topology pages

Deliverables:

- skill library page;
- skill detail page;
- topology graph page;
- SkillIR/SkillGraphIR diff views;
- artifact tree;
- context budget treemap;
- composition/decomposition comparison views;
- broker routing links.

Acceptance:

- operator can inspect why a skill exists, how it changed, what evidence supports it, how it routes, and how it can roll back;
- topology graph exposes composition/decomposition/supersession/shadowing relations.

### Phase 6 — Trace replay and provenance

Deliverables:

- trace search;
- trace detail waterfall;
- provenance graph;
- animated pipeline replay;
- time-window replay;
- redacted diagnostic bundle export.

Acceptance:

- a single evolution transaction can be replayed from evidence through activation and canary;
- source → derived data → artifact → runtime outcome links are visible;
- replay does not re-execute work.

### Phase 7 — Guarded administrative actions

Deliverables:

- retry/cancel jobs;
- pause/resume schedules;
- dry-run and start historical import;
- rescan/rerun evaluator;
- freeze/unfreeze skill;
- rollback transaction;
- model/embedding profile qualification;
- audit chain verification;
- source revocation action;
- confirmation and reason dialogs;
- action audit integration.

Acceptance:

- all actions go through sidecar policy;
- all actions are audited;
- high-impact actions require confirmation;
- rejected actions display deterministic reason codes.

### Phase 8 — Visual fidelity and soak-hardening

Deliverables:

- PixiJS particle/effects overlay;
- graph replay animations;
- mode-specific overlays;
- lane ambience and event-backed flow shimmer;
- high / balanced / low / off visual-quality modes;
- large graph clustering;
- theme polish;
- keyboard shortcuts;
- accessibility audit;
- reduced-motion support;
- low-power mode;
- performance profiling;
- browser error telemetry;
- diagnostic snapshots.

Acceptance:

- the main overview graph has the intended high-fidelity control-room appearance and does not look like an unfinished flowchart;
- visual effects remain data-backed and do not imply false state;
- dashboard achieves desired visual impact without degrading core sidecar performance;
- UI remains usable when live stream drops, DB read model is stale, WebGL is unavailable, or a component is degraded;
- reduced-motion and low-power modes remain fully functional.

---

## 20. Testing plan

### 20.1 Backend tests

- auth and role enforcement;
- response envelope validation;
- read-model queries with seeded data;
- pagination/cursor correctness;
- raw-content policy enforcement;
- action audit writes;
- WebSocket reconnect and sequence-gap handling;
- Postgres notification bridge;
- sidecar degraded-state behavior;
- rate limiting;
- CSRF enforcement for browser actions.

### 20.2 Frontend tests

- route rendering;
- component graph rendering;
- subsystem lane rendering;
- station and subsystem drill-down navigation;
- live delta reducer;
- entity-level patching without clearing collections;
- preservation of previous data during background refetch;
- stable React keys based on domain IDs;
- graph viewport/selection preservation across metric deltas;
- chart instance update without dispose/reinitialize on data refresh;
- station node mount-count guard for unrelated updates;
- snapshot reload on sequence gap;
- role-based action visibility;
- error boundary behavior;
- command palette search and permission filtering;
- object microscope rendering;
- reduced-motion mode;
- large graph clustering;
- Monaco read-only enforcement.

### 20.3 End-to-end tests

- live event appears in overview without full-page flash;
- five-second read-model refresh updates station values in place without clearing/rebuilding the overview graph;
- background refetch does not replace existing route content with a global loading spinner;
- React Flow viewport, selected node, and open cockpit remain stable across metric updates;
- ECharts charts update data in place and preserve visible user state across refresh;
- historical import progress appears in cockpit;
- subsystem lens shows cross-component bottleneck;
- global search opens trace/job/skill/object microscope pages without leaking raw content;
- issue board opens relevant playbook;
- failed scanner finding opens security cockpit;
- evaluation failure highlights evaluator station;
- activation transaction appears in writer and audit views;
- rollback replay shows provenance graph;
- skill topology graph shows composed/decomposed relationships;
- raw-content access denied by default;
- administrative action writes audit and creates linked sidecar job.

### 20.4 Visual regression tests

Use screenshot-based tests for:

- overview graph;
- station cockpit;
- topology graph;
- context treemap;
- trace replay;
- security finding view;
- reduced-motion mode.

### 20.5 Load tests

Seed datasets:

| Dataset | Size |
|---|---|
| small | 10 skills, 100 jobs, 10,000 events |
| medium | 250 skills, 10,000 jobs, 2 million events |
| large | 2,500 skills, 100,000 jobs, 50 million events |

Test:

- overview load;
- topology page with clustering;
- trace detail for long traces;
- WebSocket stream at high event rate;
- read-model refresh load;
- concurrent viewers.

### 20.6 Diagnostic usability tests

Run operator-focused tests with seeded failure scenarios:

| Scenario | Expected operator path |
|---|---|
| Capture is healthy but candidates stop appearing. | Overview issue → Capture + bootstrap → Learning + memory → redaction loss or evidence clustering fault. |
| Historical import produces many chunks but few candidates. | Historical ingestion → source Sankey → low-confidence parser or deduplication finding. |
| Context budget grows after a composed skill activates. | Runtime context → Context compiler → topology comparison → composed vs component token/value trial. |
| Scanner rejects many artifacts after one model-profile change. | Quality gates → Model profile → scanner trend → structured-output examples. |
| Broker stops loading a useful skill. | Runtime context → retrieval recall audit → broker scoring waterfall → shadowing/no-skill reason. |
| UI shows green while read models are stale. | Test must fail; self-health and affected views must render stale/unknown. |

These tests validate whether a normal operator can find the problem in the interface, not only whether components render.

### 20.7 Live-update defect tests

These tests specifically prevent the polling-report behavior described by operators during soak testing.

| Test | Expected result |
|---|---|
| Seed overview snapshot, then emit station metric delta every five seconds. | Station values update in place; graph does not disappear; route does not remount; viewport remains stable. |
| Emit a background snapshot with identical entities and newer `snapshot_seq`. | No visible rebuild; unchanged entity references remain stable where practical; no component flash. |
| Emit one changed station and many unchanged stations. | Only affected station data changes; unrelated station nodes do not remount. |
| Emit a new issue/entity. | New card/row appears without clearing existing issue list or resetting filters. |
| Resolve/delete an issue. | Only that issue leaves or changes state; scroll/filter/selection remains stable. |
| Trigger metric-only read-model invalidation. | Affected query refreshes with previous data visible; no global loading state appears. |
| Trigger graph topology change. | Affected topology updates with explained layout change; metrics-only layout state is not reset. |
| Trigger WebSocket sequence gap. | Scoped snapshot recovery occurs; self-health warning appears; route state is preserved when possible. |
| Refresh ECharts time series. | Chart transitions/diffs data; chart instance is not disposed and recreated. |
| Refresh React Flow node metrics. | Node `data` updates; React Flow instance, node IDs, viewport, and selection persist. |


### 20.8 Autonomy and evidence diagnostic tests

These tests prove that Observatory shows the calibrated-autonomy machine accurately rather than converting semantic work into an opaque administrative queue.

| Test | Expected result |
|---|---|
| Hash-only retrieval telemetry enters replay synthesis. | UI marks the candidate `evidence_insufficient_for_autonomy`, shows evidence-repair attempts, and does not present it as a normal semantic task. |
| Raw-vault-linked trajectory supports replay intent synthesis. | UI shows adjudication run, redacted intent report, deterministic validation, replay episode state, and calibration outcome. |
| Semantic adjudication schema failure occurs. | UI shows schema failure reason code, affected decision family, retry/fallback path, and model-profile health. |
| Soft threshold is missed while hard invariants pass. | UI shows fallback ladder rather than administrative escalation. |
| Threshold deadlock is detected. | UI opens an issue with calibration support, stalled decision family, and suggested autonomous remediation. |
| Administrative escalation is created. | UI shows hard authority boundary, attempted autonomous alternatives, linked decision/adjudication records, and audit receipt. |
| Raw content reveal is denied. | UI keeps redacted preview, records denial, and does not leak raw content to browser state or live stream. |

### 20.9 Overview visual-fidelity defect tests

These tests prevent the centerpiece graph from regressing into an unpolished debugging diagram.

| Test | Expected result |
|---|---|
| Render the overview on a seeded healthy deployment. | The canvas shows custom station cards, subsystem lanes, semantic edges, label chips, status halos, and theme-token alignment; no default/plain React Flow node styling is visible. |
| Switch through health, throughput, latency, security, context, topology, and historical-bootstrap lenses. | The same graph structure remains stable while visual encodings change coherently; labels, legends, and selected objects remain readable. |
| Select a station, then follow upstream/downstream highlighting. | Relevant nodes/edges are emphasized, unrelated flow is dimmed, viewport remains stable, and a details drawer opens without graph remount. |
| Select an edge label. | The edge highlights, its flow detail panel opens, and label placement remains readable at default zoom. |
| Emit high-rate low-priority events. | Particle count remains capped; edge intensity aggregates noisy flow; UI remains responsive. |
| Emit scanner/security/rollback/freeze events. | Required high-priority visual indicators appear and are never sampled away. |
| Disable WebGL or force PixiJS initialization failure. | The graph remains visually complete through DOM/SVG/CSS fallback; an Observatory self-health issue records the effects-layer failure. |
| Enable reduced-motion. | Particles, pulses, fly-throughs, and nonessential transitions stop; all state remains visible through static labels, icons, shapes, and panels. |
| Enable low-power mode. | Visual effects degrade predictably while graph readability and diagnostic function remain intact. |
| Run Playwright visual comparison for baseline overview states. | Healthy, degraded, blocked, security, reduced-motion, low-power, and WebGL-fallback screenshots remain within approved visual baselines. |

The implementation must include a small visual-regression fixture set for the overview graph. The fixture set uses deterministic seeded data and covers at least: healthy idle, busy throughput, historical import active, scanner hard finding, evaluator regression, context-budget pressure, rollback/freeze, stale telemetry, and reduced-motion.


---

## 21. Acceptance criteria

Autonomy/evidence acceptance criteria:

- evidence-fidelity state is visible at system, subsystem, station, and object levels;
- raw-vault linkage, declassification reports, and access audits are visible without exposing raw content by default;
- semantic adjudication runs are inspectable through structured verdicts, evidence IDs, confidence decomposition, verifier state, and deterministic admissibility checks;
- decision-orchestrator records distinguish hard invariant failures from soft-threshold fallback behavior;
- replay-corpus synthesis shows the path from permitted evidence to redacted intent to replay/canary episode;
- soft-threshold misses surface autonomous fallback ladders rather than generic review queues;
- administrative escalation is exceptional, reason-coded, audited, and linked to attempted autonomous alternatives;
- hash-only and metadata-only evidence modes are shown as degraded/correlation states and cannot appear as full-autonomy support.


The Observatory implementation is acceptable when all criteria are true:

1. The sidecar serves the web UI and API from a configurable `/admin` base path.
2. Authentication is required for every non-liveness endpoint.
3. The overview graph shows every SkillKernel pipeline station and reflects live health.
4. The overview graph uses a polished custom visual system: custom station cards, semantic edges, label chips, subsystem lanes, status halos, selected/hover/focus states, and theme-token alignment with the rest of the UI.
5. The overview graph avoids default library-demo styling and is visually complete enough to serve as the product's main control-room map.
6. Visual effects are performance-safe, data-backed, adaptive, and optional; WebGL failure or reduced-motion mode does not remove informational value.
7. Overview visual-regression fixtures cover healthy, degraded, blocked, security, context-pressure, rollback/freeze, stale-telemetry, reduced-motion, low-power, and WebGL-fallback states.
8. Each subsystem has an intermediate workcell lens showing cross-component flow, conversion, bottlenecks, data quality, traces, issues, and playbooks.
9. Each station has a drill-down cockpit with component-specific metrics, records, traces, config, audit, and help.
10. The issue board surfaces actionable degraded, blocked, security, regression, freeze, stale-telemetry, and data-quality conditions.
11. Live updates work through WebSocket and survive reconnect through snapshot/delta reconciliation.
12. Ordinary refresh cycles update visible components in place: no full-route flash, graph blanking, chart blanking, viewport reset, tab reset, selected-object loss, or broad component remount occurs without a justified navigation, topology, schema, or sequence-gap event.
13. Background refetch preserves previous data and shows scoped syncing/stale indicators rather than replacing the current view with global loading UI.
14. React Flow and ECharts instances persist through metric/data refreshes and update through keyed/diffed data changes.
15. Global search and command palette can locate traces, jobs, skills, candidates, artifacts, issues, imports, audit actions, and reason codes without leaking raw content.
16. Object microscope pages expose summary, timeline, provenance, effects, content policy state, diagnostics, and audit for every major object type.
17. The UI can replay an individual trace/evolution transaction through the pipeline without re-executing work.
18. Skill pages show SkillIR, SkillGraphIR, compiled artifacts, support files, context budget, scanner/evaluator state, usage attribution, and rollback links.
19. Topology pages show create/improve/compose/decompose lineage, dependency, conflict, shadowing, supersession, and external-skill relationships.
20. Context budget pages make `SKILL.md`, broker hint, support-context, and ignored-skill token pressure visible.
21. Historical ingestion pages show source discovery, dry-run, import progress, parser failures, taint/quarantine, evidence yielded, and candidates seeded.
22. Scanner/evaluator pages expose hard findings, probe results, regression state, and canary state.
23. Autonomy pages expose evidence fidelity, raw-vault policy state, LLM semantic adjudications, deterministic admissibility checks, threshold policy versions, fallback ladders, threshold-deadlock findings, replay/canary corpus episodes, and administrative escalations.
24. The UI distinguishes degraded evidence mode from full-autonomy mode and never implies that hash-only or metadata-only telemetry can support user-intent reconstruction.
25. Storage pages expose migration state, read-model freshness, pgvector/index status, and retention backlog.
26. Model/embedding pages expose qualification and health without implementing dollar-cost analysis.
27. Administrative action pages expose action requests, policy checks, idempotency, confirmation state, linked jobs, and audit records.
28. Observatory self-health pages expose admin API health, live-stream gaps, frontend diagnostics, and read-model staleness.
29. Administrative actions are role-checked, confirmation-gated when required by the configured deployment, idempotent, policy-controlled, and audited.
30. The UI defaults to redacted content and does not expose raw content unless explicitly configured and authorized.
31. Admin streaming and dashboard queries do not block core SkillKernel processing.
32. Reduced-motion and low-power modes preserve full informational value.
33. Component health is based on the required signal contract and never reports healthy when required telemetry is missing.
34. Pipeline invariant failures create issue-board entries and deep links to supporting records.
35. Baseline comparison supports bounded time-window and object-version comparisons without changing autonomous policy.
36. Diagnostic bundles can be generated with redaction by default and audited access.
37. The interface meets the configured accessibility, keyboard-navigation, reduced-motion, and low-power requirements.
38. The visual design delivers the requested assembly-line bird’s-eye view, subsystem workcell views, station cockpits, and object microscope behavior.
39. The overview graph passes the centerpiece acceptance rubric for visual finish, legibility across zoom, diagnostic honesty, spatial memory, clutter control, performance, accessibility, and theme coherence.
40. Every core SkillKernel topology operation, lifecycle operation, artifact operation, broker decision, scanner/evaluator decision, scheduler state, and historical-ingestion state has a visible path from system overview to object-level evidence.
41. The system triage summary can identify healthy, degraded, blocked, frozen, stale, and unknown states with a primary reason code and safe next action.
42. Seeded high-load fixtures demonstrate that Observatory remains effective for large deployments with months of transcripts, many agents, historical imports, large skill libraries, and active soak-test telemetry.
---

## 22. Implementation notes for “wow” without fragility

The strongest visual result comes from combining technologies by responsibility:

```text
React Flow = exact interactive structure
ELK.js = automatic readable layout
PixiJS = high-performance visual effects layer
ECharts = dense metrics/charts
Monaco = precise artifact/JSON/diff inspection
FastAPI = typed sidecar API
Postgres read models = reliable data source
```

Do not implement the whole dashboard in WebGL. WebGL is excellent for particles and dense effects, but the operator needs accessible DOM/SVG nodes, selectable text, keyboard navigation, precise tooltips, and browser-native layout. React Flow owns structure. PixiJS adds motion and density. ECharts owns charts.

Do not make the particles the source of truth. They are renderings of real events or aggregates.

Do not let beauty hide failure. When the system is degraded, blocked, frozen, or unsafe, the UI must become clearer and more explicit, not more decorative.

---


## 23. Implementation anti-patterns

Autonomy/evidence anti-patterns are release blockers:

- presenting `metadata_only` or `hash_only` records as sufficient for user-intent reconstruction;
- using a generic ambiguous status where the real state is soft-threshold fallback, evidence-insufficient, hard-invariant failure, raw-vault policy disallow, or administrative escalation;
- hiding LLM adjudication verdicts behind a pass/fail badge without showing evidence IDs, confidence decomposition, schema status, verifier state, and deterministic admissibility checks;
- letting raw prompts, tool arguments, tool results, or memory text enter WebSocket payloads, browser persistence, logs, analytics, or URL parameters;
- representing administrative escalation as a normal work queue for semantic decisions;
- showing a healthy autonomy state when repeated soft-threshold misses are stalling decisions;
- displaying model-profile health without qualification state, schema-adherence failures, timeout pressure, and verifier disagreement.


These implementation choices are release-blocking because they undermine Observatory's purpose:

| Anti-pattern | Why it is unacceptable |
|---|---|
| Poll-and-replace page refresh | Causes flashing, resets operator focus, hides continuity problems, and makes the interface feel like a static report. |
| Default graph-library styling | Makes the central system map look unfinished and reduces trust in the diagnostic surface. |
| Health without freshness | A green indicator without current telemetry is misleading. |
| Aggregates without drill-down | Prevents operators from proving whether a metric reflects real SkillKernel state. |
| Charts with no object links | Turns diagnostics into decoration rather than investigation tools. |
| UI-local action state | Creates a second control plane and breaks auditability. |
| Raw-content convenience toggles | Risks exposing transcripts, memories, prompts, tool results, or artifacts without explicit authorization and audit. |
| Hiding evidence insufficiency as ordinary review | Makes autonomy failures look like operator workflow; evidence insufficiency must appear as a diagnostic condition with repair attempts. |
| Treating LLM verdicts as invisible magic | Prevents trust calibration; semantic adjudications must expose evidence, confidence components, deterministic checks, and outcome links. |
| Showing raw-vault availability without policy state | Misleads users into thinking evidence exists and is usable; raw-vault records must show access policy, retention, declassification, and denial reasons. |
| Confusing administrative escalation with semantic uncertainty | Routine semantic uncertainty belongs to autonomous adjudication and fallback ladders; escalation is reserved for hard authority boundaries. |
| Broad query invalidation for small deltas | Causes avoidable remounts, flicker, network load, and state loss. |
| Unbounded data fetches | Makes soak testing fragile under real deployment history and large skill libraries. |
| Visual effects as source of truth | Creates attractive but untrustworthy animation detached from audited records. |
| Silent disabled components | Prevents operators from distinguishing healthy idle from missing telemetry or disabled ingestion. |
| Non-deterministic demo data in production views | Makes screenshots, tests, and issue reports unreproducible. |

Every anti-pattern has a positive replacement elsewhere in this specification: stable entity reconciliation, custom visual components, freshness-aware health, aggregate-to-evidence drill-downs, action gateway auditing, redacted-by-default content policy, bounded APIs, data-backed effects, explicit disabled states, and seeded deterministic fixtures.

## 24. Developer checklist

Autonomy/evidence checklist:

- [ ] Add read models and routes for evidence fidelity, raw-vault audit, semantic adjudication, autonomy decisions, replay synthesis, threshold deadlocks, and administrative escalation.
- [ ] Render evidence-fidelity and autonomy-support states in the system overview, subsystem workcells, station headers, object microscope pages, and issue board.
- [ ] Implement autonomy decision object microscope pages with evidence links, hard invariants, soft thresholds, fallback ladder, and audit links.
- [ ] Implement replay-corpus synthesis pages that show LLM-synthesized redacted intent and deterministic validation without requiring raw content exposure.
- [ ] Ensure raw content is never emitted in live stream deltas, LISTEN/NOTIFY payloads, browser local storage, URLs, or console logs.
- [ ] Add visual and end-to-end tests for evidence-insufficient, soft-threshold fallback, threshold deadlock, administrative escalation, and raw-reveal denial states.


- [ ] Add admin API module to sidecar.
- [ ] Add auth/role middleware.
- [ ] Add `web_admin` config block.
- [ ] Add subsystem and component catalog seed migration.
- [ ] Add component status snapshots.
- [ ] Add live event outbox.
- [ ] Add diagnostic assertion and issue read models.
- [ ] Add baseline comparison and diagnostic bundle endpoints.
- [ ] Add admin action audit table.
- [ ] Add pipeline and subsystem summary read models.
- [ ] Add read-model refresh service.
- [ ] Add WebSocket live stream.
- [ ] Add optional SSE stream.
- [ ] Add OpenAPI-generated frontend client.
- [ ] Build React/Vite app shell.
- [ ] Build overview assembly-line graph with subsystem lanes.
- [ ] Implement stable-identity live reconciliation for overview graph, charts, tables, and cockpits.
- [ ] Add render/mount counters and live-update defect tests that detect full-route flashes and graph/chart reinitialization.
- [ ] Build subsystem lens framework.
- [ ] Build station cockpit framework.
- [ ] Build all component cockpits.
- [ ] Build skill library/detail/topology pages.
- [ ] Build issue board, diagnostic assertions, and guided playbooks.
- [ ] Build trace replay, baseline comparison, and provenance graph.
- [ ] Build context budget views.
- [ ] Build scanner/evaluator/security pages.
- [ ] Build scheduler/jobs pages.
- [ ] Build model/embedding profile pages.
- [ ] Build storage/read-model pages.
- [ ] Build Observatory self-health page.
- [ ] Add guarded action dialogs.
- [ ] Add audit chain verification UI.
- [ ] Add PixiJS particle overlay.
- [ ] Add reduced-motion, low-power, keyboard, and accessibility modes.
- [ ] Add raw-content access safeguards and browser security headers.
- [ ] Add E2E tests and load fixtures.
- [ ] Add visual regression tests.
- [ ] Add documentation and operator runbook.

---

## 25. Authoritative references

These references support the implementation choices in this document.

### 25.1 OpenClaw and SkillKernel platform boundaries

- OpenClaw plugin hooks: in-process extension points for observing/changing agent runs, tool calls, message flow, session lifecycle, subagent routing, installs, and Gateway startup.  
  URL: https://docs.openclaw.ai/plugins/hooks

- OpenClaw configuration reference: trusted conversation-bearing plugin hook access requires explicit `plugins.entries.<id>.hooks.allowConversationAccess`.  
  URL: https://docs.openclaw.ai/gateway/configuration-reference

- OpenClaw skills: `SKILL.md`-based skill directories loaded into agent context, including frontmatter, load roots, precedence, `{baseDir}` references, and gating behavior.  
  URL: https://docs.openclaw.ai/tools/skills

- OpenClaw session management and session tools: session routing, session history behavior, bounded/safety-filtered `sessions_history`, and transcript concepts used by Observatory drill-downs.  
  URL: https://docs.openclaw.ai/concepts/session
  URL: https://docs.openclaw.ai/concepts/session-tool

- OpenClaw trajectory and transcript references: historical execution records, prompts, tools, errors, runtime settings, active skills, and transcript hygiene behavior used by historical, evidence-fidelity, and trace views.  
  URL: https://docs.openclaw.ai/tools/trajectory
  URL: https://docs.openclaw.ai/reference/transcript-hygiene

- OpenClaw plugin SDK runtime helpers: simple model-completion seams, runtime helper boundaries, and model attribution relevant to Observatory model-profile and adjudication visibility.  
  URL: https://docs.openclaw.ai/plugins/sdk-runtime

### 25.2 Autonomy, security, and governance anchors

- NIST AI Risk Management Framework and generative-AI profile: lifecycle risk management, governance, measurement, and monitoring concepts relevant to calibrated autonomy and issue surfacing.  
  URL: https://www.nist.gov/itl/ai-risk-management-framework
  URL: https://www.nist.gov/itl/ai-risk-management-framework/generative-artificial-intelligence

- OWASP agentic/LLM guidance: excessive agency, sensitive-information disclosure, plugin/tool boundaries, and defense-in-depth requirements relevant to raw-vault views, administrative escalation, and UI action gates.  
  URL: https://genai.owasp.org/

- OWASP Top 10: web application security guidance relevant to admin-surface access control, injection, insecure design, security misconfiguration, logging, and SSRF protections.  
  URL: https://owasp.org/Top10/

### 25.3 Frontend rendering, live-update, and visual fidelity anchors

- React state identity: React preserves or resets state based on component position and keys; stable domain keys are required for live dashboard continuity.  
  URL: https://react.dev/learn/preserving-and-resetting-state

- React memoization: `memo` can avoid child re-renders when props are unchanged, useful for station nodes and cockpit subcomponents after profiling.  
  URL: https://react.dev/reference/react/memo

- React Flow / `@xyflow/react`: interactive node-edge diagrams, built-in MiniMap, Controls, custom node/edge support, and layouting examples with Dagre/ELK.  
  URL: https://reactflow.dev/

- React Flow custom nodes, custom edges, updating nodes, and performance guidance: required for a polished high-fidelity overview that updates in place rather than rebuilding.  
  URL: https://reactflow.dev/examples/nodes/custom-node
  URL: https://reactflow.dev/examples/edges/animating-edges
  URL: https://reactflow.dev/examples/nodes/update-node
  URL: https://reactflow.dev/learn/advanced-use/performance

- ELK.js / Eclipse Layout Kernel: layered graph layout for directed node-link diagrams and port-aware layouts.  
  URL: https://github.com/kieler/elkjs

- Apache ECharts: charting library with many chart types, Canvas/SVG rendering, dynamic data, progressive rendering, large data support, and transition/diff behavior through `setOption`.  
  URL: https://echarts.apache.org/
  URL: https://apache.github.io/echarts-handbook/en/how-to/data/dynamic-data/
  URL: https://echarts.apache.org/handbook/en/how-to/animation/transition/

- PixiJS: GPU-accelerated canvas rendering through WebGL/WebGL2/WebGPU-capable renderers.  
  URL: https://pixijs.com/

- D3: low-level web-standard data visualization primitives useful for scales, shapes, and custom transforms when ECharts/React Flow do not cover a niche visualization.  
  URL: https://d3js.org/

- TanStack Query: server-state fetching, caching, synchronization, invalidation, structural sharing, and async-state handling for React/TypeScript applications.  
  URL: https://tanstack.com/query/latest
  URL: https://tanstack.com/query/v5/docs/framework/react/guides/important-defaults

- Monaco Editor: browser editor powering VS Code, useful for read-only JSON, manifest, `SKILL.md`, and diff inspection.  
  URL: https://microsoft.github.io/monaco-editor/

- Playwright visual comparisons: screenshot baselines can detect accidental visual regressions in the overview graph and reduced-motion/low-power variants.  
  URL: https://playwright.dev/docs/test-snapshots

- CSS reduced-motion preference and Page Visibility API: required to prevent excessive motion and avoid wasting client resources when the dashboard is hidden.  
  URL: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40media/prefers-reduced-motion
  URL: https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API

### 25.4 Backend API, observability, and database anchors

- FastAPI and FastAPI WebSockets: type-hinted API framework, OpenAPI generation, static serving, security utilities, and WebSocket endpoint support for live dashboard streams.  
  URL: https://fastapi.tiangolo.com/
  URL: https://fastapi.tiangolo.com/advanced/websockets/

- OpenAPI Specification: standard API description format for generating typed clients and validating API contracts.  
  URL: https://swagger.io/specification/

- OpenTelemetry: vendor-neutral observability APIs and concepts for metrics, traces, and logs.  
  URL: https://opentelemetry.io/docs/

- WCAG 2.2: accessibility guidance for contrast, focus, keyboard interaction, text alternatives, and reduced-motion-friendly design.  
  URL: https://www.w3.org/TR/WCAG22/

- PostgreSQL `LISTEN`/`NOTIFY`: built-in database notification mechanism for waking live dashboard streams and read-model invalidation; notifications should carry invalidation IDs, not sensitive bodies.  
  URL: https://www.postgresql.org/docs/current/sql-notify.html

- PostgreSQL materialized views: read-optimized query results refreshable by the sidecar for dashboard performance.  
  URL: https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html

---

## 26. Readiness statement

The SkillKernel Observatory is the correct next subsystem for soak testing. SkillKernel’s autonomous control plane needs a high-fidelity visual interface because the system’s behavior is distributed across live capture, historical ingestion, raw-vault and evidence-fidelity policy, autonomous semantic adjudication, calibrated decision orchestration, storage, retrieval, topology operations, context compilation, scanner/evaluator gates, file transactions, broker decisions, administrative escalation exceptions, and rollback logic.

The Observatory makes those internals visible without weakening the control plane. It runs from the sidecar, consumes governed read models, streams safe deltas, defaults to redacted content, provides drill-down across subsystem workcells and every station, and exposes guarded administrative actions only through existing sidecar policy and audit paths.

Correctness, inspectability, continuity, and visual quality are all implementation requirements. The desired “wow” effect comes from a polished, high-fidelity rendering of the real SkillKernel machine, not from decorative animation detached from real state. A user must be able to start at the overview, identify whether SkillKernel is healthy or inefficient, follow the affected subsystem, inspect the responsible station, and open the exact object-level evidence without leaving the web interface.
