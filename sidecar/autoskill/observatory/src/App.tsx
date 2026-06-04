import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Boxes,
  Bug,
  Database,
  FileJson,
  Gauge,
  KeyRound,
  Layers,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  TimerReset,
  Workflow
} from "lucide-react";
import type { EChartsOption } from "echarts";
import {
  fetchObject,
  fetchSummary,
  isSnapshotPayload,
  postAction,
  search,
  streamLive
} from "./api";
import type { ApiSession } from "./api";
import type { Issue, LiveEnvelope, ObservatorySnapshot, Station, Subsystem } from "./types";
import { AssemblyLine } from "./components/AssemblyLine";
import { EChartPanel } from "./components/EChartPanel";
import { Inspector } from "./components/Inspector";
import { ParticleLayer } from "./components/ParticleLayer";

type View = "overview" | "workcells" | "cockpit" | "skills" | "trace" | "admin";
type CockpitTab = "records" | "metrics" | "traces" | "artifacts" | "config" | "audit" | "help";

const storedToken = sessionStorage.getItem("skillkernel.admin.token") ?? "";
const initialParams = new URLSearchParams(window.location.search);
const initialView = ((): View => {
  const value = initialParams.get("view");
  return value && ["overview", "workcells", "cockpit", "skills", "trace", "admin"].includes(value)
    ? (value as View)
    : "overview";
})();
const initialWindowMinutes = (() => {
  const value = Number(initialParams.get("window") ?? 60);
  return Number.isFinite(value) && value > 0 ? value : 60;
})();

function App() {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<ApiSession>({
    token: storedToken,
    roles: "admin,operator,auditor,viewer"
  });
  const [tokenDraft, setTokenDraft] = useState("");
  const [workspaceId, setWorkspaceId] = useState(initialParams.get("workspace") ?? "dev-01");
  const [windowMinutes, setWindowMinutes] = useState(initialWindowMinutes);
  const [view, setView] = useState<View>(initialView);
  const [selectedStationId, setSelectedStationId] = useState<string | undefined>(
    initialParams.get("station") ?? undefined
  );
  const [selectedSubsystemId, setSelectedSubsystemId] = useState<string | undefined>(
    initialParams.get("subsystem") ?? undefined
  );
  const [query, setQuery] = useState(initialParams.get("q") ?? "");
  const [liveState, setLiveState] = useState<"offline" | "connecting" | "live">("offline");
  const [liveSnapshot, setLiveSnapshot] = useState<ObservatorySnapshot | null>(null);
  const [reducedMotion, setReducedMotion] = useState(
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
  const lastSeq = useRef<number | undefined>(undefined);
  const liveSnapshotSignature = useRef<string | undefined>(undefined);
  const hasAdminToken = session.token.trim().length > 0;

  const summary = useQuery({
    queryKey: ["summary", session.token, session.roles, workspaceId, windowMinutes],
    queryFn: () => fetchSummary(session, workspaceId, windowMinutes),
    enabled: hasAdminToken,
    retry: false
  });

  const snapshot = liveSnapshot ?? summary.data?.snapshot;
  const selectedStation =
    snapshot?.pipeline.stations.find((station) => station.component_id === selectedStationId) ??
    snapshot?.pipeline.stations[0];
  const selectedSubsystem =
    snapshot?.subsystems.find((subsystem) => subsystem.subsystem_id === selectedSubsystemId) ??
    snapshot?.subsystems[0];

  const objectQuery = useQuery({
    queryKey: ["object", session.token, workspaceId, selectedStation?.component_id],
    enabled: hasAdminToken && Boolean(selectedStation),
    queryFn: () => fetchObject(session, "component", selectedStation!.component_id, workspaceId)
  });

  const searchQuery = useQuery({
    queryKey: ["search", session.token, workspaceId, query],
    enabled: hasAdminToken && query.trim().length > 1,
    queryFn: () => search(session, query, workspaceId)
  });

  const actionMutation = useMutation({
    mutationFn: () =>
      postAction(session, {
        workspace_id: workspaceId,
        action: "verify_audit_chain",
        idempotency_key: `observatory-ui-${Date.now()}`,
        reason: "operator requested Observatory UI audit proof"
      })
  });

  useEffect(() => {
    sessionStorage.setItem("skillkernel.admin.token", session.token);
  }, [session.token]);

  useEffect(() => {
    if (summary.data?.snapshot) {
      liveSnapshotSignature.current = snapshotContentSignature(summary.data.snapshot);
    }
  }, [summary.data?.snapshot]);

  function updateToken(token: string) {
    lastSeq.current = undefined;
    liveSnapshotSignature.current = undefined;
    setLiveSnapshot(null);
    queryClient.removeQueries({ queryKey: ["summary"] });
    queryClient.removeQueries({ queryKey: ["object"] });
    queryClient.removeQueries({ queryKey: ["search"] });
    setSession((current) => ({ ...current, token }));
  }

  function commitTokenDraft() {
    const nextToken = tokenDraft.trim();
    if (!nextToken) return;
    updateToken(nextToken);
    setTokenDraft("");
  }

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("view", view);
    params.set("workspace", workspaceId);
    params.set("window", String(windowMinutes));
    if (selectedStationId) params.set("station", selectedStationId);
    if (selectedSubsystemId) params.set("subsystem", selectedSubsystemId);
    if (query.trim()) params.set("q", query.trim());
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [query, selectedStationId, selectedSubsystemId, view, windowMinutes, workspaceId]);

  useEffect(() => {
    if (!hasAdminToken) {
      setLiveState("offline");
      return;
    }
    let closed = false;
    const controller = new AbortController();
    const applyEnvelope = (envelope: LiveEnvelope) => {
      lastSeq.current = envelope.seq;
      if (envelope.requires_snapshot_reload) {
        void queryClient.invalidateQueries({ queryKey: ["summary"] });
      }
      if (isSnapshotPayload(envelope.payload)) {
        const nextSignature = snapshotContentSignature(envelope.payload);
        if (nextSignature === liveSnapshotSignature.current) return;
        liveSnapshotSignature.current = nextSignature;
        setLiveSnapshot(envelope.payload);
        queryClient.setQueryData(["summary", session.token, session.roles, workspaceId, windowMinutes], {
          snapshot: envelope.payload
        });
      }
    };
    setLiveState("connecting");
    void streamLive(session, workspaceId, lastSeq.current, {
      signal: controller.signal,
      onEnvelope: applyEnvelope,
      onOpen: () => {
        if (!closed) setLiveState("live");
      }
    }).catch((error: unknown) => {
      if (!closed && !(error instanceof DOMException && error.name === "AbortError")) {
        setLiveState("offline");
      }
    });
    return () => {
      closed = true;
      controller.abort();
    };
  }, [hasAdminToken, queryClient, session.roles, session.token, windowMinutes, workspaceId]);

  const healthChart = useMemo<EChartsOption>(() => {
    const counts = snapshot?.fitness.component_health_counts ?? {};
    return {
      backgroundColor: "transparent",
      tooltip: {},
      series: [
        {
          type: "pie",
          radius: ["48%", "72%"],
          avoidLabelOverlap: true,
          data: Object.entries(counts).map(([name, value]) => ({ name, value }))
        }
      ]
    };
  }, [snapshot]);

  const subsystemChart = useMemo<EChartsOption>(() => {
    return {
      backgroundColor: "transparent",
      tooltip: {},
      xAxis: { type: "category", data: snapshot?.subsystems.map((item) => item.display_name) ?? [] },
      yAxis: { type: "value" },
      grid: { left: 42, right: 12, bottom: 72, top: 24 },
      series: [
        {
          type: "bar",
          data: snapshot?.subsystems.map((item) => item.queue_depth) ?? [],
          itemStyle: { color: "#68d391" }
        }
      ]
    };
  }, [snapshot]);

  function selectStation(station: Station) {
    setSelectedStationId(station.component_id);
    setView("cockpit");
  }

  if (!hasAdminToken || summary.isError || !summary.isSuccess || !snapshot) {
    const gateMessage = summary.isError
      ? "The admin token was rejected or the sidecar could not verify it."
      : hasAdminToken
        ? "Verifying the configured admin token."
        : "Enter the configured admin token to open the operating console.";
    return (
      <main className="login-shell">
        <section className="login-panel">
          <KeyRound aria-hidden="true" />
          <h1>SkillKernel Observatory</h1>
          <p>{gateMessage}</p>
          <input
            type="password"
            aria-label="Admin token"
            placeholder="SKILLKERNEL_ADMIN_TOKEN"
            value={session.token}
            onChange={(event) => updateToken(event.target.value)}
          />
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Workflow aria-hidden="true" />
          <div>
            <h1>SkillKernel Observatory</h1>
            <p>{snapshot?.fitness.plain_language_summary ?? "Loading sidecar read models."}</p>
          </div>
        </div>
        <div className="controls-strip">
          <label>
            Workspace
            <input value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} />
          </label>
          <label>
            Window
            <input
              type="number"
              min={1}
              max={1440}
              value={windowMinutes}
              onChange={(event) => setWindowMinutes(Number(event.target.value))}
            />
          </label>
          <label>
            Token
            <input
              type="password"
              autoComplete="off"
              placeholder={session.token ? "Token stored" : "Paste token"}
              value={tokenDraft}
              onBlur={commitTokenDraft}
              onChange={(event) => setTokenDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.currentTarget.blur();
                }
              }}
            />
          </label>
          <button
            type="button"
            className="icon-button"
            title="Refresh snapshot"
            onClick={() => void summary.refetch()}
          >
            <RefreshCw aria-hidden="true" />
          </button>
          <button
            type="button"
            className="icon-button"
            title="Toggle reduced motion"
            onClick={() => setReducedMotion((value) => !value)}
          >
            <TimerReset aria-hidden="true" />
          </button>
        </div>
      </header>

      <nav className="view-tabs" aria-label="Observatory views">
        <Tab active={view === "overview"} label="Overview" icon={<Gauge />} onClick={() => setView("overview")} />
        <Tab active={view === "workcells"} label="Workcells" icon={<Layers />} onClick={() => setView("workcells")} />
        <Tab active={view === "cockpit"} label="Cockpit" icon={<Activity />} onClick={() => setView("cockpit")} />
        <Tab active={view === "skills"} label="Skills" icon={<Network />} onClick={() => setView("skills")} />
        <Tab active={view === "trace"} label="Trace" icon={<FileJson />} onClick={() => setView("trace")} />
        <Tab active={view === "admin"} label="Admin" icon={<ShieldCheck />} onClick={() => setView("admin")} />
      </nav>

      {summary.isLoading || !snapshot ? (
        <section className="loading-state">Loading Observatory snapshot...</section>
      ) : (
        <>
          <section className="kpi-ribbon">
            {snapshot.kpis.map((kpi) => (
              <div className="kpi" key={kpi.label}>
                <span>{kpi.label}</span>
                <strong>{String(kpi.value)}</strong>
                <small>{kpi.unit}</small>
              </div>
            ))}
            <div className={`live-badge live-${liveState}`}>{liveState}</div>
          </section>

          <section className="search-row">
            <Search aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find components, issues, traces, jobs, skills, reason codes"
            />
            {searchQuery.data?.results.length ? (
              <div className="search-results">
                {searchQuery.data.results.slice(0, 8).map((result) => (
                  <button
                    key={`${result.object_type}:${result.object_id}`}
                    type="button"
                    onClick={() => {
                      if (result.object_type === "component") {
                        setSelectedStationId(result.object_id);
                        setView("cockpit");
                      }
                    }}
                  >
                    <span>{result.object_type}</span>
                    <strong>{result.title}</strong>
                  </button>
                ))}
              </div>
            ) : null}
          </section>

          {view === "overview" && (
            <Overview
              snapshot={snapshot}
              selectedStationId={selectedStation?.component_id}
              reducedMotion={reducedMotion}
              healthChart={healthChart}
              subsystemChart={subsystemChart}
              onSelectStation={selectStation}
            />
          )}
          {view === "workcells" && (
            <Workcells
              snapshot={snapshot}
              selectedSubsystem={selectedSubsystem}
              onSelect={(subsystem) => setSelectedSubsystemId(subsystem.subsystem_id)}
              onOpenStation={selectStation}
            />
          )}
          {view === "cockpit" && selectedStation && (
            <Cockpit
              station={selectedStation}
              issues={snapshot.issue_board.filter((issue) => issue.component_id === selectedStation.component_id)}
              object={objectQuery.data?.object}
            />
          )}
          {view === "skills" && <SkillsAndTopology snapshot={snapshot} />}
          {view === "trace" && <TraceAndInspector snapshot={snapshot} object={objectQuery.data?.object} />}
          {view === "admin" && (
            <Admin
              snapshot={snapshot}
              actionPending={actionMutation.isPending}
              actionResult={actionMutation.data?.receipt}
              onAction={() => actionMutation.mutate()}
            />
          )}
        </>
      )}
    </main>
  );
}

function snapshotContentSignature(snapshot: ObservatorySnapshot) {
  return JSON.stringify(stableSnapshotContent(snapshot));
}

function stableSnapshotContent(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(stableSnapshotContent);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => !["captured_at", "snapshot_seq"].includes(key))
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stableSnapshotContent(item)])
    );
  }
  return value;
}

function Tab({
  active,
  label,
  icon,
  onClick
}: {
  active: boolean;
  label: string;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <button className={active ? "is-active" : ""} type="button" onClick={onClick}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function Overview({
  snapshot,
  selectedStationId,
  reducedMotion,
  healthChart,
  subsystemChart,
  onSelectStation
}: {
  snapshot: ObservatorySnapshot;
  selectedStationId?: string;
  reducedMotion: boolean;
  healthChart: EChartsOption;
  subsystemChart: EChartsOption;
  onSelectStation: (station: Station) => void;
}) {
  return (
    <section className="overview-grid">
      <div className="pipeline-region">
        <ParticleLayer edges={snapshot.pipeline.edges} reducedMotion={reducedMotion} />
        <AssemblyLine
          stations={snapshot.pipeline.stations}
          edges={snapshot.pipeline.edges}
          selectedId={selectedStationId}
          onSelect={onSelectStation}
        />
      </div>
      <aside className="issue-board">
        <h2>Issue Board</h2>
        {snapshot.issue_board.slice(0, 12).map((issue) => (
          <IssueRow key={issue.issue_id} issue={issue} />
        ))}
      </aside>
      <EChartPanel title="Component Health" option={healthChart} />
      <EChartPanel title="Workcell Queue Depth" option={subsystemChart} />
      <section className="invariant-panel">
        <h2>Pipeline Invariants</h2>
        {snapshot.pipeline.invariants.map((invariant) => (
          <div key={String(invariant.invariant_id)} className="invariant-row">
            <strong>{String(invariant.invariant_id)}</strong>
            <span>{String(invariant.status)}</span>
          </div>
        ))}
      </section>
    </section>
  );
}

function Workcells({
  snapshot,
  selectedSubsystem,
  onSelect,
  onOpenStation
}: {
  snapshot: ObservatorySnapshot;
  selectedSubsystem?: Subsystem;
  onSelect: (subsystem: Subsystem) => void;
  onOpenStation: (station: Station) => void;
}) {
  return (
    <section className="workcell-layout">
      <div className="workcell-list">
        {snapshot.subsystems.map((subsystem) => (
          <button
            key={subsystem.subsystem_id}
            className={subsystem.subsystem_id === selectedSubsystem?.subsystem_id ? "is-selected" : ""}
            type="button"
            onClick={() => onSelect(subsystem)}
          >
            <span className={`status-dot health-${subsystem.health}`} />
            <strong>{subsystem.display_name}</strong>
            <small>{subsystem.queue_depth} queued</small>
          </button>
        ))}
      </div>
      {selectedSubsystem ? (
        <section className="workcell-detail">
          <h2>{selectedSubsystem.display_name}</h2>
          <div className="workcell-metrics">
            <span>Health {selectedSubsystem.health}</span>
            <span>Throughput {selectedSubsystem.throughput_1m.toFixed(1)}/min</span>
            <span>Conversion {(selectedSubsystem.conversion_rate * 100).toFixed(0)}%</span>
          </div>
          <div className="question-list">
            {selectedSubsystem.diagnostic_questions.map((question) => (
              <p key={question}>{question}</p>
            ))}
          </div>
          <div className="station-grid">
            {selectedSubsystem.station_ids.map((stationId) => {
              const station = snapshot.pipeline.stations.find((item) => item.component_id === stationId)!;
              return (
                <button key={stationId} type="button" onClick={() => onOpenStation(station)}>
                  <span className={`status-dot health-${station.health}`} />
                  <strong>{station.display_name}</strong>
                  <small>{station.reason_codes.join(", ") || "within bounds"}</small>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
    </section>
  );
}

function Cockpit({
  station,
  issues,
  object
}: {
  station: Station;
  issues: Issue[];
  object?: Record<string, unknown>;
}) {
  const [activeTab, setActiveTab] = useState<CockpitTab>("records");
  const tabs: Array<{ id: CockpitTab; label: string }> = [
    { id: "records", label: "Records" },
    { id: "metrics", label: "Metrics" },
    { id: "traces", label: "Traces" },
    { id: "artifacts", label: "Artifacts" },
    { id: "config", label: "Config" },
    { id: "audit", label: "Audit" },
    { id: "help", label: "Help" }
  ];
  const tabPayload: Record<CockpitTab, unknown> = {
    records: station.records,
    metrics: station.signal_contract,
    traces: object?.timeline ?? [],
    artifacts: {
      object_kinds: station.object_kinds,
      content_policy: object?.content_policy ?? { raw_available: false }
    },
    config: {
      mode: station.mode,
      freeze_state: station.freeze_state,
      data_quality: station.data_quality
    },
    audit: object?.audit ?? { links: [] },
    help: {
      purpose: station.purpose,
      reason_codes: station.reason_codes,
      safe_next_actions: issues.flatMap((issue) => issue.safe_next_actions)
    }
  };
  return (
    <section className="cockpit-layout">
      <div className="cockpit-main">
        <h2>{station.display_name}</h2>
        <p>{station.purpose}</p>
        <div className="workcell-metrics">
          <span>Health {station.health}</span>
          <span>Input {station.input_rate_1m.toFixed(1)}/min</span>
          <span>Output {station.output_rate_1m.toFixed(1)}/min</span>
          <span>Queue {station.queue_depth}</span>
        </div>
        <section className="reason-panel">
          <h3>Reason Codes</h3>
          {station.reason_codes.length ? (
            station.reason_codes.map((code) => <code key={code}>{code}</code>)
          ) : (
            <code>no-active-reason-codes</code>
          )}
        </section>
        <div className="cockpit-tabs" role="tablist" aria-label="Station cockpit panels">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "is-active" : ""}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <section className="records-panel">
          <h3>{tabs.find((tab) => tab.id === activeTab)?.label}</h3>
          <Inspector value={tabPayload[activeTab]} />
        </section>
      </div>
      <aside className="cockpit-side">
        <h3>Local Issues</h3>
        {issues.length ? issues.map((issue) => <IssueRow key={issue.issue_id} issue={issue} />) : <p>No active issues.</p>}
        <Inspector value={object ?? station} />
      </aside>
    </section>
  );
}

function SkillsAndTopology({ snapshot }: { snapshot: ObservatorySnapshot }) {
  const skillStations = snapshot.pipeline.stations.filter((station) =>
    ["skill_ir_graph_ir", "topology_operations", "activation_curation", "context_compiler"].includes(
      station.component_id
    )
  );
  return (
    <section className="topology-page">
      <div>
        <h2>Skill And Topology Lens</h2>
        <p>
          SkillIR, SkillGraphIR, package planning, context budget, activation, curation, and rollback
          surfaces are linked through the component cockpits below.
        </p>
      </div>
      <div className="station-grid">
        {skillStations.map((station) => (
          <div key={station.component_id} className="topology-tile">
            <span className={`status-dot health-${station.health}`} />
            <strong>{station.display_name}</strong>
            <small>{station.object_kinds.join(" / ")}</small>
          </div>
        ))}
      </div>
      <Inspector value={snapshot.pipeline.edges.filter((edge) => edge.dominant_item_kind.includes("skill"))} />
    </section>
  );
}

function TraceAndInspector({
  snapshot,
  object
}: {
  snapshot: ObservatorySnapshot;
  object?: Record<string, unknown>;
}) {
  return (
    <section className="trace-page">
      <div>
        <h2>Trace Replay And Object Microscope</h2>
        <p>
          Replays use recorded spans and read models only. They do not re-run jobs, mutate skills, or reveal
          raw content.
        </p>
      </div>
      <Inspector value={object ?? snapshot.pipeline.invariants} />
    </section>
  );
}

function Admin({
  snapshot,
  actionPending,
  actionResult,
  onAction
}: {
  snapshot: ObservatorySnapshot;
  actionPending: boolean;
  actionResult?: Record<string, unknown>;
  onAction: () => void;
}) {
  return (
    <section className="admin-page">
      <div className="admin-actions">
        <h2>Operator Action Gateway</h2>
        <p>Actions are role-checked, idempotency-keyed, policy-receipted, and written to audit.</p>
        <button type="button" onClick={onAction} disabled={actionPending}>
          <ShieldCheck aria-hidden="true" />
          <span>{actionPending ? "Recording..." : "Audit Verify Action"}</span>
        </button>
      </div>
      <div className="admin-columns">
        <section>
          <h3>Command Palette</h3>
          {snapshot.command_palette.map((command) => (
            <div key={String(command.command)} className="command-row">
              <strong>{String(command.label)}</strong>
              <code>{String(command.target)}</code>
            </div>
          ))}
        </section>
        <section>
          <h3>Receipt</h3>
          <Inspector value={actionResult ?? snapshot.auth} />
        </section>
      </div>
    </section>
  );
}

function IssueRow({ issue }: { issue: Issue }) {
  return (
    <article className={`issue-row severity-${issue.severity}`}>
      <Bug aria-hidden="true" />
      <div>
        <strong>{issue.title}</strong>
        <p>{issue.summary}</p>
        <small>{issue.reason_codes.join(", ")}</small>
      </div>
    </article>
  );
}

export default App;
