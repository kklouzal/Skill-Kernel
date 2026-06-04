import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Boxes,
  Bug,
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
  fetchActionAudits,
  fetchBrokerReplayEpisodeDetail,
  fetchBrokerReplayEpisodes,
  fetchContextArtifacts,
  fetchObject,
  fetchSkillDetail,
  fetchSkills,
  fetchSummary,
  fetchTopology,
  fetchTraceReplay,
  fetchTraces,
  isSnapshotPayload,
  postAction,
  search,
  streamLive
} from "./api";
import type { ApiSession } from "./api";
import type {
  BrokerReplayEpisodeSummary,
  HealthState,
  Issue,
  LiveEnvelope,
  ObservatorySnapshot,
  Station,
  Subsystem,
  TraceSpan,
  TraceSummary
} from "./types";
import { AssemblyLine } from "./components/AssemblyLine";
import { EChartPanel } from "./components/EChartPanel";
import { Inspector } from "./components/Inspector";
import { ParticleLayer } from "./components/ParticleLayer";

type View = "overview" | "workcells" | "cockpit" | "skills" | "trace" | "replay" | "admin";
type CockpitTab = "records" | "metrics" | "traces" | "artifacts" | "config" | "audit" | "help";
type FrontendDiagnostics = {
  app_render_count: number;
  app_mount_count: number;
  live_snapshot_apply_count: number;
  duplicate_snapshot_suppression_count: number;
  sequence_gap_reload_count: number;
  summary_snapshot_seed_count: number;
  last_snapshot_signature: string | null;
  live_state: string;
  selected_view: View;
};

const storedToken = sessionStorage.getItem("skillkernel.admin.token") ?? "";
const initialParams = new URLSearchParams(window.location.search);
const initialView = ((): View => {
  const value = initialParams.get("view");
  return value && ["overview", "workcells", "cockpit", "skills", "trace", "replay", "admin"].includes(value)
    ? (value as View)
    : "overview";
})();
const initialWindowMinutes = (() => {
  const value = Number(initialParams.get("window") ?? 60);
  return Number.isFinite(value) && value > 0 ? value : 60;
})();

function incrementSessionCounter(key: string): number {
  const next = Number(sessionStorage.getItem(key) ?? 0) + 1;
  sessionStorage.setItem(key, String(next));
  return next;
}

function App() {
  const queryClient = useQueryClient();
  const renderCount = useRef(0);
  const mountCount = useRef<number | null>(null);
  if (mountCount.current === null) {
    mountCount.current = incrementSessionCounter("skillkernel.observatory.app_mount_count");
  }
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
  const [selectedTraceId, setSelectedTraceId] = useState<string | undefined>(
    initialParams.get("trace") ?? undefined
  );
  const [selectedReplayEpisodeId, setSelectedReplayEpisodeId] = useState<string | undefined>(
    initialParams.get("episode") ?? undefined
  );
  const [replayTag, setReplayTag] = useState(initialParams.get("replay_tag") ?? "production");
  const [selectedSkillId, setSelectedSkillId] = useState<string | undefined>(
    initialParams.get("skill") ?? undefined
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
  const [frontendDiagnostics, setFrontendDiagnostics] = useState<
    Omit<FrontendDiagnostics, "app_render_count" | "app_mount_count" | "live_state" | "selected_view">
  >({
    live_snapshot_apply_count: 0,
    duplicate_snapshot_suppression_count: 0,
    sequence_gap_reload_count: 0,
    summary_snapshot_seed_count: 0,
    last_snapshot_signature: null
  });
  renderCount.current += 1;

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

  const tracesQuery = useQuery({
    queryKey: ["traces", session.token, session.roles, workspaceId],
    enabled: hasAdminToken && view === "trace",
    queryFn: () => fetchTraces(session, workspaceId, 50),
    retry: false
  });
  const traceItems = tracesQuery.data?.collection.items ?? [];
  const effectiveTraceId = selectedTraceId ?? traceItems[0]?.trace_id;
  const traceReplayQuery = useQuery({
    queryKey: ["trace-replay", session.token, session.roles, workspaceId, effectiveTraceId],
    enabled: hasAdminToken && view === "trace" && Boolean(effectiveTraceId),
    queryFn: () => fetchTraceReplay(session, effectiveTraceId!, workspaceId, 150),
    retry: false
  });
  const replayEpisodesQuery = useQuery({
    queryKey: ["broker-replay-episodes", session.token, session.roles, workspaceId, replayTag],
    enabled: hasAdminToken && view === "replay",
    queryFn: () =>
      fetchBrokerReplayEpisodes(session, workspaceId, replayTag.trim() ? [replayTag] : [], 50),
    retry: false
  });
  const replayEpisodeItems = replayEpisodesQuery.data?.collection.items ?? [];
  const effectiveReplayEpisodeId =
    selectedReplayEpisodeId ?? replayEpisodeItems[0]?.broker_replay_episode_id;
  const replayEpisodeDetailQuery = useQuery({
    queryKey: [
      "broker-replay-episode",
      session.token,
      session.roles,
      workspaceId,
      effectiveReplayEpisodeId
    ],
    enabled: hasAdminToken && view === "replay" && Boolean(effectiveReplayEpisodeId),
    queryFn: () => fetchBrokerReplayEpisodeDetail(session, effectiveReplayEpisodeId!, workspaceId),
    retry: false
  });
  const skillsQuery = useQuery({
    queryKey: ["skills", session.token, session.roles, workspaceId],
    enabled: hasAdminToken && view === "skills",
    queryFn: () => fetchSkills(session, workspaceId, 100),
    retry: false
  });
  const skillItems = skillsQuery.data?.collection.items ?? [];
  const effectiveSkillId =
    selectedSkillId ??
    skillIdentifier(skillItems[0]) ??
    snapshot?.pipeline.stations.find((station) => station.component_id === "skill_ir_graph_ir")
      ?.component_id;
  const skillDetailQuery = useQuery({
    queryKey: ["skill-detail", session.token, session.roles, workspaceId, effectiveSkillId],
    enabled: hasAdminToken && view === "skills" && Boolean(effectiveSkillId),
    queryFn: () => fetchSkillDetail(session, effectiveSkillId!, workspaceId),
    retry: false
  });
  const topologyQuery = useQuery({
    queryKey: ["topology", session.token, session.roles, workspaceId, windowMinutes],
    enabled: hasAdminToken && view === "skills",
    queryFn: () => fetchTopology(session, workspaceId, windowMinutes),
    retry: false
  });
  const contextArtifactsQuery = useQuery({
    queryKey: ["context-artifacts", session.token, session.roles, workspaceId],
    enabled: hasAdminToken && view === "skills",
    queryFn: () => fetchContextArtifacts(session, workspaceId, 75),
    retry: false
  });
  const actionAuditsQuery = useQuery({
    queryKey: ["action-audits", session.token, session.roles, workspaceId],
    enabled: hasAdminToken && view === "admin",
    queryFn: () => fetchActionAudits(session, workspaceId, 50),
    retry: false
  });

  const actionMutation = useMutation({
    mutationFn: ({ action, reason }: { action: string; reason: string }) =>
      postAction(session, {
        workspace_id: workspaceId,
        action,
        idempotency_key: `observatory-ui-${action}-${Date.now()}`,
        reason
      }),
    onSuccess: () => {
      void actionAuditsQuery.refetch();
    }
  });

  useEffect(() => {
    sessionStorage.setItem("skillkernel.admin.token", session.token);
  }, [session.token]);

  useEffect(() => {
    if (summary.data?.snapshot) {
      const signature = snapshotContentSignature(summary.data.snapshot);
      liveSnapshotSignature.current = signature;
      setFrontendDiagnostics((current) => ({
        ...current,
        summary_snapshot_seed_count: current.summary_snapshot_seed_count + 1,
        last_snapshot_signature: signature.slice(0, 24)
      }));
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
    if (selectedTraceId) params.set("trace", selectedTraceId);
    if (selectedReplayEpisodeId) params.set("episode", selectedReplayEpisodeId);
    if (replayTag.trim()) params.set("replay_tag", replayTag.trim());
    if (selectedSkillId) params.set("skill", selectedSkillId);
    if (query.trim()) params.set("q", query.trim());
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [
    query,
    selectedStationId,
    selectedSubsystemId,
    selectedTraceId,
    selectedReplayEpisodeId,
    selectedSkillId,
    replayTag,
    view,
    windowMinutes,
    workspaceId
  ]);

  useEffect(() => {
    if (!selectedTraceId && traceItems[0]?.trace_id) {
      setSelectedTraceId(traceItems[0].trace_id);
    }
  }, [selectedTraceId, traceItems]);

  useEffect(() => {
    if (!selectedReplayEpisodeId && replayEpisodeItems[0]?.broker_replay_episode_id) {
      setSelectedReplayEpisodeId(replayEpisodeItems[0].broker_replay_episode_id);
    }
  }, [selectedReplayEpisodeId, replayEpisodeItems]);

  useEffect(() => {
    setSelectedReplayEpisodeId(undefined);
  }, [replayTag, workspaceId]);

  useEffect(() => {
    const firstSkillId = skillIdentifier(skillItems[0]);
    if (!selectedSkillId && firstSkillId) {
      setSelectedSkillId(firstSkillId);
    }
  }, [selectedSkillId, skillItems]);

  useEffect(() => {
    if (!hasAdminToken) {
      setLiveState("offline");
      return;
    }
    let closed = false;
    const controller = new AbortController();
    const applyEnvelope = (envelope: LiveEnvelope) => {
      lastSeq.current = envelope.cursor_seq ?? envelope.seq;
      if (envelope.requires_snapshot_reload) {
        setFrontendDiagnostics((current) => ({
          ...current,
          sequence_gap_reload_count: current.sequence_gap_reload_count + 1
        }));
        void queryClient.invalidateQueries({ queryKey: ["summary"] });
      }
      if (isSnapshotPayload(envelope.payload)) {
        const nextSignature = snapshotContentSignature(envelope.payload);
        if (nextSignature === liveSnapshotSignature.current) {
          setFrontendDiagnostics((current) => ({
            ...current,
            duplicate_snapshot_suppression_count: current.duplicate_snapshot_suppression_count + 1
          }));
          return;
        }
        liveSnapshotSignature.current = nextSignature;
        setLiveSnapshot(envelope.payload);
        setFrontendDiagnostics((current) => ({
          ...current,
          live_snapshot_apply_count: current.live_snapshot_apply_count + 1,
          last_snapshot_signature: nextSignature.slice(0, 24)
        }));
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

  const frontendDiagnosticsPayload: FrontendDiagnostics = {
    ...frontendDiagnostics,
    app_render_count: renderCount.current,
    app_mount_count: mountCount.current,
    live_state: liveState,
    selected_view: view
  };

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
        <Tab active={view === "replay"} label="Replay" icon={<Boxes />} onClick={() => setView("replay")} />
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
                      } else if (result.object_type === "trace") {
                        setSelectedTraceId(result.object_id);
                        setView("trace");
                      } else if (result.object_type === "broker_replay_episode") {
                        setSelectedReplayEpisodeId(result.object_id);
                        setView("replay");
                      } else if (result.object_type === "skill") {
                        setSelectedSkillId(result.object_id);
                        setView("skills");
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
          {view === "skills" && (
            <SkillsAndTopology
              snapshot={snapshot}
              skills={skillItems}
              selectedSkillId={effectiveSkillId}
              skillDetail={skillDetailQuery.data?.object}
              topology={topologyQuery.data?.object}
              contextArtifacts={contextArtifactsQuery.data?.collection.items ?? []}
              loading={
                skillsQuery.isLoading ||
                skillDetailQuery.isLoading ||
                topologyQuery.isLoading ||
                contextArtifactsQuery.isLoading
              }
              error={
                skillsQuery.error ??
                skillDetailQuery.error ??
                topologyQuery.error ??
                contextArtifactsQuery.error
              }
              onSelectSkill={setSelectedSkillId}
            />
          )}
          {view === "trace" && (
            <TraceAndInspector
              snapshot={snapshot}
              traces={traceItems}
              selectedTraceId={effectiveTraceId}
              replayObject={traceReplayQuery.data?.object}
              loading={tracesQuery.isLoading || traceReplayQuery.isLoading}
              error={tracesQuery.error ?? traceReplayQuery.error}
              onSelectTrace={setSelectedTraceId}
            />
          )}
          {view === "replay" && (
            <BrokerReplayCorpus
              episodes={replayEpisodeItems}
              selectedEpisodeId={effectiveReplayEpisodeId}
              replayObject={replayEpisodeDetailQuery.data?.object}
              replayTag={replayTag}
              loading={replayEpisodesQuery.isLoading || replayEpisodeDetailQuery.isLoading}
              error={replayEpisodesQuery.error ?? replayEpisodeDetailQuery.error}
              onSelectEpisode={setSelectedReplayEpisodeId}
              onReplayTagChange={setReplayTag}
            />
          )}
          {view === "admin" && (
            <Admin
              snapshot={snapshot}
              frontendDiagnostics={frontendDiagnosticsPayload}
              actionPending={actionMutation.isPending}
              actionResult={actionMutation.data?.receipt}
              actionAudits={actionAuditsQuery.data?.collection.items ?? []}
              auditsLoading={actionAuditsQuery.isLoading}
              onAction={(action, reason) => actionMutation.mutate({ action, reason })}
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
      missing_signals: station.data_quality.missing_signals,
      missing_signal_keys: station.data_quality.missing_signal_keys ?? [],
      safe_next_actions: issues.flatMap((issue) => issue.safe_next_actions)
    }
  };
  const missingSignals = station.data_quality.missing_signals;
  const missingSignalKeys = station.data_quality.missing_signal_keys ?? [];
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
        {missingSignals.length || missingSignalKeys.length ? (
          <section className="signal-panel">
            <h3>Missing Signals</h3>
            {missingSignals.map((signal) => (
              <code key={`signal-${signal}`}>{signal}</code>
            ))}
            {missingSignalKeys.map((signalKey) => (
              <code key={`key-${signalKey}`}>{signalKey}</code>
            ))}
          </section>
        ) : null}
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

function SkillsAndTopology({
  snapshot,
  skills,
  selectedSkillId,
  skillDetail,
  topology,
  contextArtifacts,
  loading,
  error,
  onSelectSkill
}: {
  snapshot: ObservatorySnapshot;
  skills: Array<Record<string, unknown>>;
  selectedSkillId?: string;
  skillDetail?: Record<string, unknown>;
  topology?: Record<string, unknown>;
  contextArtifacts: Array<Record<string, unknown>>;
  loading: boolean;
  error: unknown;
  onSelectSkill: (skillId: string) => void;
}) {
  const skillStations = snapshot.pipeline.stations.filter((station) =>
    ["skill_ir_graph_ir", "topology_operations", "activation_curation", "context_compiler"].includes(
      station.component_id
    )
  );
  const selectedSkill = skills.find((skill) => skillIdentifier(skill) === selectedSkillId);
  const diagnostics = (skillDetail?.diagnostics as Record<string, unknown> | undefined) ?? selectedSkill;
  const contextForSkill = contextArtifacts.filter((artifact) =>
    selectedSkillId ? JSON.stringify(artifact).includes(selectedSkillId) : true
  );

  return (
    <section className="topology-page">
      <div className="skill-layout">
        <aside className="skill-list" aria-label="Skill library">
          <h2>Skill Library</h2>
          {loading ? <p>Loading skill read models.</p> : null}
          {error ? <p>{error instanceof Error ? error.message : "Skill surfaces unavailable."}</p> : null}
          {skills.length ? (
            skills.map((skill) => {
              const id = skillIdentifier(skill);
              return (
                <button
                  key={id ?? JSON.stringify(skill)}
                  className={id === selectedSkillId ? "is-selected" : ""}
                  disabled={!id}
                  type="button"
                  onClick={() => id && onSelectSkill(id)}
                >
                  <span className={`status-dot health-${skillHealth(skill)}`} />
                  <strong>{skillLabel(skill)}</strong>
                  <small>
                    {String(skill.lifecycle_state ?? skill.status ?? "unknown")} /{" "}
                    {String(skill.active_version_id ?? skill.version_id ?? "no-version")}
                  </small>
                </button>
              );
            })
          ) : (
            <p>No SkillKernel-owned skills are visible for this workspace.</p>
          )}
        </aside>

        <section className="skill-detail">
          <div className="trace-replay__header">
            <div>
              <h2>{skillDetail ? String(skillDetail.title ?? selectedSkillId) : "Skill Detail"}</h2>
              <p>{String(skillDetail?.summary ?? "Select a skill to inspect lifecycle and artifact evidence.")}</p>
            </div>
            <div className="trace-badges">
              <span>{String(diagnostics?.lifecycle_state ?? "lifecycle unknown")}</span>
              <span>{String(diagnostics?.scanner_status ?? diagnostics?.scan_status ?? "scanner unknown")}</span>
              <span>{String(diagnostics?.evaluator_status ?? "evaluator unknown")}</span>
            </div>
          </div>

          <div className="skill-evidence-grid">
            <section>
              <h3>SkillIR / Version</h3>
              <Inspector value={diagnostics ?? skillDetail ?? { state: "empty" }} />
            </section>
            <section>
              <h3>Artifacts / Context Budget</h3>
              <Inspector
                value={{
                  selected_skill_id: selectedSkillId,
                  context_artifacts: contextForSkill,
                  artifact_count: contextForSkill.length
                }}
              />
            </section>
          </div>

          <div className="skill-evidence-grid">
            <section>
              <h3>Topology</h3>
              <Inspector value={topology ?? { state: "topology-read-model-unavailable" }} />
            </section>
            <section>
              <h3>Routing Stations</h3>
              <div className="station-grid">
                {skillStations.map((station) => (
                  <div key={station.component_id} className="topology-tile">
                    <span className={`status-dot health-${station.health}`} />
                    <strong>{station.display_name}</strong>
                    <small>{station.object_kinds.join(" / ")}</small>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </section>
      </div>
    </section>
  );
}

function skillIdentifier(skill?: Record<string, unknown>) {
  if (!skill) return undefined;
  for (const key of ["skill_id", "object_id", "slug", "active_version_id", "version_id"]) {
    const value = skill[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

function skillLabel(skill: Record<string, unknown>) {
  for (const key of ["name", "slug", "title", "skill_id", "object_id"]) {
    const value = skill[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "Unnamed skill";
}

function skillHealth(skill: Record<string, unknown>): HealthState {
  const state = String(skill.lifecycle_state ?? skill.status ?? "").toLowerCase();
  if (["active", "published", "ok", "healthy"].includes(state)) return "healthy";
  if (["frozen", "revoked"].includes(state)) return "frozen";
  if (["failed", "blocked"].includes(state)) return "blocked";
  if (["archived", "inactive", "candidate"].includes(state)) return "unknown";
  return "degraded";
}

function TraceAndInspector({
  snapshot,
  traces,
  selectedTraceId,
  replayObject,
  loading,
  error,
  onSelectTrace
}: {
  snapshot: ObservatorySnapshot;
  traces: TraceSummary[];
  selectedTraceId?: string;
  replayObject?: Record<string, unknown>;
  loading: boolean;
  error: unknown;
  onSelectTrace: (traceId: string) => void;
}) {
  const [activeIndex, setActiveIndex] = useState(0);
  const spans = useMemo(() => traceSpansFromReplay(replayObject), [replayObject]);
  const activeSpan = spans[Math.min(activeIndex, Math.max(0, spans.length - 1))];
  const touchedStationIds = useMemo(() => {
    const ids = new Set(spans.map((span) => stationIdForOperation(span.operation_kind)).filter(Boolean));
    return ids as Set<string>;
  }, [spans]);
  const activeStationId = activeSpan ? stationIdForOperation(activeSpan.operation_kind) : undefined;
  const selectedTrace = traces.find((trace) => trace.trace_id === selectedTraceId);
  const replaySafety = replayObject?.replay_safety as Record<string, unknown> | undefined;
  const diffPanels = diffPanelPayload(activeSpan);

  useEffect(() => {
    setActiveIndex(0);
  }, [selectedTraceId]);

  useEffect(() => {
    if (activeIndex >= spans.length) {
      setActiveIndex(Math.max(0, spans.length - 1));
    }
  }, [activeIndex, spans.length]);

  return (
    <section className="trace-page">
      <div className="trace-layout">
        <aside className="trace-list" aria-label="Trace list">
          <h2>Trace Replay</h2>
          {loading ? <p>Loading traces.</p> : null}
          {error ? <p>{error instanceof Error ? error.message : "Trace replay unavailable."}</p> : null}
          {traces.length ? (
            traces.map((trace) => (
              <button
                key={trace.trace_id}
                className={trace.trace_id === selectedTraceId ? "is-selected" : ""}
                type="button"
                onClick={() => onSelectTrace(trace.trace_id)}
              >
                <span className={`status-dot health-${traceHealth(trace.status)}`} />
                <strong>{traceTitle(trace)}</strong>
                <small>
                  {trace.span_count} spans / {trace.operation_kinds.slice(0, 3).join(", ") || "unknown"}
                </small>
              </button>
            ))
          ) : (
            <p>No traces in this workspace window.</p>
          )}
        </aside>

        <section className="trace-replay">
          <div className="trace-replay__header">
            <div>
              <h2>{selectedTrace ? traceTitle(selectedTrace) : "No Trace Selected"}</h2>
              <p>{String(replayObject?.summary ?? selectedTrace?.summary ?? "Select a trace to inspect recorded spans.")}</p>
            </div>
            <div className="trace-badges">
              <span>{String(replaySafety?.reexecutes_work === false ? "read-only replay" : "replay state unknown")}</span>
              <span>{String(replaySafety?.raw_content_included === false ? "redacted bundle" : "content policy unknown")}</span>
              {activeSpan ? <span>{activeSpan.status}</span> : null}
            </div>
          </div>

          <div className="replay-station-strip">
            {snapshot.pipeline.stations.map((station) => {
              const touched = touchedStationIds.has(station.component_id);
              const active = activeStationId === station.component_id;
              return (
                <div
                  key={station.component_id}
                  className={`replay-station ${touched ? "is-touched" : ""} ${active ? "is-active" : ""}`}
                >
                  <span className={`status-dot health-${station.health}`} />
                  <strong>{station.display_name}</strong>
                  <small>{station.reason_codes[0] ?? "within bounds"}</small>
                </div>
              );
            })}
          </div>

          <div className="trace-scrubber">
            <label>
              Span
              <input
                type="range"
                min={0}
                max={Math.max(0, spans.length - 1)}
                value={Math.min(activeIndex, Math.max(0, spans.length - 1))}
                disabled={spans.length === 0}
                onChange={(event) => setActiveIndex(Number(event.target.value))}
              />
            </label>
            <span>
              {spans.length ? activeIndex + 1 : 0} / {spans.length}
            </span>
          </div>

          <div className="span-waterfall">
            {spans.map((span, index) => (
              <button
                key={span.span_id}
                className={index === activeIndex ? "is-active" : ""}
                type="button"
                onClick={() => setActiveIndex(index)}
                title={`${span.operation_kind}: ${span.operation_name}`}
              >
                <span className={`span-bar status-${span.status}`} style={{ width: `${spanWidth(span)}%` }} />
                <strong>{span.operation_kind}</strong>
                <small>{span.status}</small>
              </button>
            ))}
          </div>

          <div className="trace-detail-grid">
            <section>
              <h3>Span Detail</h3>
              <Inspector value={activeSpan ?? replayObject ?? { state: "empty" }} />
            </section>
            <section>
              <h3>Object Links</h3>
              <div className="trace-link-list">
                {activeSpan?.object_refs.length ? (
                  activeSpan.object_refs.map((ref, index) => (
                    <a
                      key={`${String(ref.object_type)}:${String(ref.object_id)}:${index}`}
                      href={`/admin?view=trace&workspace=${encodeURIComponent(
                        snapshot.workspace_id ?? ""
                      )}&trace=${encodeURIComponent(selectedTraceId ?? "")}`}
                    >
                      <span>{String(ref.object_type ?? "object")}</span>
                      <strong>{String(ref.object_id ?? "unknown")}</strong>
                    </a>
                  ))
                ) : (
                  <p>No object refs recorded for this span.</p>
                )}
              </div>
            </section>
          </div>

          <div className="trace-detail-grid">
            <section>
              <h3>Gate And Policy Badges</h3>
              <div className="trace-badges">
                {gateBadges(activeSpan).map((badge) => (
                  <span key={badge}>{badge}</span>
                ))}
              </div>
            </section>
            <section>
              <h3>Diff Panels</h3>
              <Inspector value={diffPanels} />
            </section>
          </div>
        </section>
      </div>
    </section>
  );
}

function traceSpansFromReplay(replayObject?: Record<string, unknown>): TraceSpan[] {
  const timeline = replayObject?.timeline;
  return Array.isArray(timeline) ? (timeline as TraceSpan[]) : [];
}

function traceTitle(trace: TraceSummary) {
  return trace.trace_id.slice(0, 8);
}

function traceHealth(status: string): HealthState {
  if (["ok", "healthy"].includes(status)) return "healthy";
  if (["running", "unknown"].includes(status)) return "unknown";
  return "degraded";
}

function stationIdForOperation(operationKind: string) {
  const map: Record<string, string> = {
    archive: "activation_curation",
    broker: "broker_runtime",
    compiler: "context_compiler",
    embedding_call: "model_embedding",
    evaluator: "evaluator_probes",
    evidence: "evidence_memory",
    evolution: "topology_operations",
    ingest: "spool_ingest",
    job: "scheduler_jobs",
    llm_call: "model_embedding",
    memory: "evidence_memory",
    plugin_capture: "openclaw_live_capture",
    promotion: "activation_curation",
    redaction: "redaction_taint",
    retrieval: "retrieval_indexing",
    rollback: "canary_rollback",
    scanner: "scanner_security",
    scheduler: "scheduler_jobs",
    tool_attribution: "audit_trace",
    writer: "deterministic_writer"
  };
  return map[operationKind] ?? "audit_trace";
}

function spanWidth(span: TraceSpan) {
  const started = Date.parse(span.started_at);
  const ended = Date.parse(span.ended_at ?? span.started_at);
  if (!Number.isFinite(started) || !Number.isFinite(ended)) return 18;
  const ms = Math.max(1, ended - started);
  return Math.max(18, Math.min(100, 18 + Math.log10(ms + 1) * 22));
}

function gateBadges(span?: TraceSpan) {
  if (!span) return ["no-span-selected"];
  const badges = new Set<string>([span.operation_kind, span.status]);
  for (const [key, value] of Object.entries(span.safe_attributes ?? {})) {
    if (key.includes("policy") || key.includes("gate") || key.includes("verdict")) {
      badges.add(`${key}:${String(value)}`);
    }
  }
  if (!badges.size) badges.add("no-gate-metadata");
  return Array.from(badges);
}

function diffPanelPayload(span?: TraceSpan) {
  const attributes = span?.safe_attributes ?? {};
  const diffEntries = Object.entries(attributes).filter(([key]) => key.toLowerCase().includes("diff"));
  if (!diffEntries.length) {
    return {
      available: false,
      reason: "no-diff-metadata-for-selected-span",
      span_id: span?.span_id ?? null
    };
  }
  return Object.fromEntries(diffEntries);
}

function BrokerReplayCorpus({
  episodes,
  selectedEpisodeId,
  replayObject,
  replayTag,
  loading,
  error,
  onSelectEpisode,
  onReplayTagChange
}: {
  episodes: BrokerReplayEpisodeSummary[];
  selectedEpisodeId?: string;
  replayObject?: Record<string, unknown>;
  replayTag: string;
  loading: boolean;
  error: unknown;
  onSelectEpisode: (episodeId: string) => void;
  onReplayTagChange: (tag: string) => void;
}) {
  const selectedEpisode = episodes.find(
    (episode) => episode.broker_replay_episode_id === selectedEpisodeId
  );
  const diagnostics = replayObject?.diagnostics as Record<string, unknown> | undefined;
  const effects = replayObject?.effects as Record<string, unknown> | undefined;
  const provenance = replayObject?.provenance as Record<string, unknown> | undefined;
  const contentPolicy =
    (replayObject?.content_policy as Record<string, unknown> | undefined) ??
    selectedEpisode?.content_policy;

  return (
    <section className="replay-page">
      <div className="replay-layout">
        <aside className="replay-list" aria-label="Broker replay episode list">
          <div className="replay-filter">
            <h2>Broker Replay Corpus</h2>
            <label>
              Tag
              <input
                value={replayTag}
                placeholder="production"
                onChange={(event) => onReplayTagChange(event.target.value)}
              />
            </label>
          </div>
          {loading ? <p>Loading replay episodes.</p> : null}
          {error ? <p>{error instanceof Error ? error.message : "Broker replay corpus unavailable."}</p> : null}
          {episodes.length ? (
            episodes.map((episode) => (
              <button
                key={episode.broker_replay_episode_id}
                className={
                  episode.broker_replay_episode_id === selectedEpisodeId ? "is-selected" : ""
                }
                type="button"
                onClick={() => onSelectEpisode(episode.broker_replay_episode_id)}
              >
                <span className={`status-dot health-${replayHealth(episode.expected_decision)}`} />
                <strong>{episode.episode_key}</strong>
                <small>
                  {episode.expected_decision ?? "decision-unspecified"} /{" "}
                  {episode.expected_skill_ids.length} skills / {episode.tags.join(", ") || "untagged"}
                </small>
              </button>
            ))
          ) : (
            <p>No broker replay episodes match the current workspace and tag.</p>
          )}
        </aside>

        <section className="replay-detail">
          <div className="trace-replay__header">
            <div>
              <h2>{selectedEpisode?.episode_key ?? "No Replay Episode Selected"}</h2>
              <p>
                {String(
                  replayObject?.summary ??
                    selectedEpisode?.summary ??
                    "Select an operator-reviewed replay episode to inspect routing expectations."
                )}
              </p>
            </div>
            <div className="trace-badges">
              <span>{String(contentPolicy?.raw_prompt_stored === false ? "raw prompt absent" : "raw policy unknown")}</span>
              <span>{String(contentPolicy?.redaction_state ?? "redaction state unknown")}</span>
              <span>{String(selectedEpisode?.expected_decision ?? "decision unspecified")}</span>
            </div>
          </div>

          <div className="replay-evidence-grid">
            <section>
              <h3>Expected Routing</h3>
              <div className="replay-expected">
                <span>
                  <strong>{String(effects?.expected_decision ?? selectedEpisode?.expected_decision ?? "unknown")}</strong>
                  <small>decision</small>
                </span>
                <span>
                  <strong>{expectedSkillIds(effects, selectedEpisode).length}</strong>
                  <small>expected skills</small>
                </span>
                <span>
                  <strong>{selectedEpisode?.tags.length ?? 0}</strong>
                  <small>tags</small>
                </span>
              </div>
              <Inspector
                value={{
                  expected_skill_ids: expectedSkillIds(effects, selectedEpisode),
                  metadata_keys: diagnostics?.metadata_keys ?? [],
                  redacted_intent_hash: diagnostics?.redacted_intent_hash ?? null,
                  raw_prompt_stored: contentPolicy?.raw_prompt_stored ?? false
                }}
              />
            </section>
            <section>
              <h3>Replay Provenance</h3>
              <Inspector
                value={{
                  upstream: provenance?.upstream ?? [],
                  details_url: selectedEpisode?.details_url ?? null,
                  content_policy: contentPolicy ?? { raw_available: false }
                }}
              />
            </section>
          </div>

          <section>
            <h3>Object Microscope</h3>
            <Inspector value={replayObject ?? selectedEpisode ?? { state: "empty" }} />
          </section>
        </section>
      </div>
    </section>
  );
}

function replayHealth(expectedDecision?: string | null): HealthState {
  if (expectedDecision === "skill_hint") return "healthy";
  if (expectedDecision === "no_skill") return "unknown";
  if (expectedDecision) return "degraded";
  return "unknown";
}

function expectedSkillIds(
  effects?: Record<string, unknown>,
  episode?: BrokerReplayEpisodeSummary
): string[] {
  const effectIds = effects?.expected_skill_ids;
  if (Array.isArray(effectIds)) {
    return effectIds.map((item) => String(item));
  }
  return episode?.expected_skill_ids ?? [];
}

function Admin({
  snapshot,
  frontendDiagnostics,
  actionPending,
  actionResult,
  actionAudits,
  auditsLoading,
  onAction
}: {
  snapshot: ObservatorySnapshot;
  frontendDiagnostics: FrontendDiagnostics;
  actionPending: boolean;
  actionResult?: Record<string, unknown>;
  actionAudits: Array<Record<string, unknown>>;
  auditsLoading: boolean;
  onAction: (action: string, reason: string) => void;
}) {
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionReason, setActionReason] = useState("");
  const operatorActions = [
    "verify_audit_chain",
    "refresh_read_models",
    "verify_live_stream",
    "storage_health_check",
    "retention_dry_run",
    "model_profile_qualify",
    "embedding_profile_qualify",
    "broker_calibrate"
  ];
  const defaultReason = pendingAction
    ? `operator confirmed Observatory UI dry-run for ${pendingAction}`
    : "";

  return (
    <section className="admin-page">
      <div className="admin-actions">
        <h2>Operator Action Gateway</h2>
        <p>Actions are role-checked, idempotency-keyed, policy-receipted, and written to audit.</p>
        <div className="action-button-grid">
          {operatorActions.map((action) => (
            <button
              key={action}
              type="button"
              onClick={() => {
                setPendingAction(action);
                setActionReason(`operator confirmed Observatory UI dry-run for ${action}`);
              }}
              disabled={actionPending}
              title={`${action} dry-run`}
            >
              <ShieldCheck aria-hidden="true" />
              <span>{actionPending ? "Recording..." : action.replaceAll("_", " ")}</span>
            </button>
          ))}
        </div>
      </div>
      {pendingAction ? (
        <div className="action-dialog-backdrop" role="presentation">
          <section
            className="action-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="action-dialog-title"
          >
            <h3 id="action-dialog-title">{pendingAction.replaceAll("_", " ")}</h3>
            <label>
              Reason
              <textarea
                value={actionReason}
                placeholder={defaultReason}
                onChange={(event) => setActionReason(event.target.value)}
              />
            </label>
            <div className="action-dialog__buttons">
              <button type="button" onClick={() => setPendingAction(null)}>
                Cancel
              </button>
              <button
                type="button"
                disabled={actionPending}
                onClick={() => {
                  onAction(pendingAction, actionReason.trim() || defaultReason);
                  setPendingAction(null);
                }}
              >
                {actionPending ? "Recording..." : "Confirm dry-run"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
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
      <section>
        <h3>Frontend Diagnostics</h3>
        <Inspector value={frontendDiagnostics} />
      </section>
      <section>
        <h3>Action Audit</h3>
        {auditsLoading ? <p>Loading action audit records.</p> : null}
        <div className="audit-row-grid">
          {actionAudits.length ? (
            actionAudits.map((audit) => (
              <div key={String(audit.object_id ?? audit.action_id ?? JSON.stringify(audit))} className="audit-row">
                <strong>{String(audit.action_kind ?? audit.title ?? "operator action")}</strong>
                <span>{String(audit.result ?? "unknown")}</span>
                <small>{String(audit.created_at ?? audit.summary ?? "")}</small>
              </div>
            ))
          ) : (
            <p>No action audit records in the current workspace.</p>
          )}
        </div>
      </section>
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
