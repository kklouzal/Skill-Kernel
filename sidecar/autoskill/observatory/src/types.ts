export type HealthState = "healthy" | "degraded" | "blocked" | "frozen" | "offline" | "unknown";

export type Kpi = {
  label: string;
  value: string | number;
  unit: string;
};

export type Issue = {
  issue_id: string;
  severity: "critical" | "high" | "medium" | "low";
  component_id?: string;
  subsystem_id?: string;
  title: string;
  summary: string;
  reason_codes: string[];
  evidence_refs: Array<Record<string, unknown>>;
  safe_next_actions: Array<Record<string, unknown>>;
  deep_link: string;
};

export type Station = {
  component_id: string;
  display_name: string;
  purpose: string;
  health: HealthState;
  mode: string;
  freeze_state: string;
  input_rate_1m: number;
  output_rate_1m: number;
  queue_depth: number;
  backlog_seconds: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  error_rate_15m: number;
  warning_count: number;
  blocked_count: number;
  token_pressure: number;
  risk_pressure: number;
  evaluator_pressure: number;
  details_url: string;
  subsystem_ids: string[];
  object_kinds: string[];
  reason_codes: string[];
  signal_contract: Record<string, unknown>;
  data_quality: {
    telemetry_freshness_seconds: number;
    coverage_state: string;
    missing_signals: string[];
    missing_signal_keys?: string[];
    raw_content_available: boolean;
  };
  records: Array<Record<string, unknown>>;
};

export type PipelineEdge = {
  edge_id: string;
  from: string;
  to: string;
  event_rate_1m: number;
  job_rate_1m: number;
  error_rate_15m: number;
  backpressure: number;
  oldest_item_age_seconds: number;
  dominant_item_kind: string;
  health: HealthState;
};

export type Subsystem = {
  subsystem_id: string;
  display_name: string;
  health: HealthState;
  station_ids: string[];
  station_health: Record<string, HealthState>;
  diagnostic_questions: string[];
  throughput_1m: number;
  queue_depth: number;
  oldest_item_age_seconds: number;
  conversion_rate: number;
  reason_codes: string[];
  issue_ids: string[];
  edges: PipelineEdge[];
  playbooks: Array<Record<string, string>>;
  details_url: string;
};

export type ObservatorySnapshot = {
  schema_version: string;
  snapshot_seq: number;
  workspace_id: string | null;
  captured_at: string;
  window_minutes: number;
  base_path: string;
  auth: Record<string, unknown>;
  global_health: HealthState;
  fitness: {
    score: number;
    component_health_counts: Record<string, number>;
    issue_counts: Record<string, number>;
    plain_language_summary: string;
  };
  kpis: Kpi[];
  data_quality: Record<string, unknown>;
  pipeline: {
    stations: Station[];
    edges: PipelineEdge[];
    invariants: Array<Record<string, unknown>>;
  };
  subsystems: Subsystem[];
  issue_board: Issue[];
  dashboards: Record<string, unknown>;
  search_facets: Array<Record<string, unknown>>;
  command_palette: Array<Record<string, unknown>>;
  reason_code_catalog: Array<Record<string, string>>;
};

export type AdminMeta = {
  request_id: string;
  generated_at: string;
  redaction_level: string;
  warnings: string[];
};

export type AdminEnvelope<TData extends Record<string, unknown>> = {
  ok: boolean;
  data: TData;
  meta: AdminMeta;
};

export type SnapshotResponse = AdminEnvelope<{ snapshot: ObservatorySnapshot }> & {
  snapshot: ObservatorySnapshot;
};

export type SearchResult = {
  object_type: string;
  object_id: string;
  title: string;
  summary: string;
  url: string;
  reason_codes: string[];
};

export type SearchResponse = AdminEnvelope<{
  query: string;
  limit: number;
  results: SearchResult[];
}> & {
  query: string;
  limit: number;
  results: SearchResult[];
};

export type ObjectResponse = AdminEnvelope<{ object: Record<string, unknown> }> & {
  object: Record<string, unknown>;
};

export type CollectionResponse<TItem extends Record<string, unknown> = Record<string, unknown>> =
  AdminEnvelope<{
    collection: {
      object_type: string;
      title: string;
      items: TItem[];
      count: number;
      limit: number;
      cursor?: string | null;
      next_cursor?: string | null;
      source: string;
      diagnostics: Record<string, unknown>;
    };
  }> & {
    collection: {
      object_type: string;
      title: string;
      items: TItem[];
      count: number;
      limit: number;
      cursor?: string | null;
      next_cursor?: string | null;
      source: string;
      diagnostics: Record<string, unknown>;
    };
  };

export type TraceSummary = {
  object_type: "trace";
  object_id: string;
  trace_id: string;
  workspace_key?: string | null;
  span_count: number;
  statuses: string[];
  operation_kinds: string[];
  object_refs: Array<Record<string, unknown>>;
  started_at: string;
  last_event_at: string;
  status: string;
  title: string;
  summary: string;
  details_url: string;
  content_policy: Record<string, unknown>;
};

export type TraceSpan = {
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  workspace_id?: string | null;
  workspace_key?: string | null;
  operation_name: string;
  operation_kind: string;
  status: string;
  safe_attributes: Record<string, unknown>;
  object_refs: Array<Record<string, unknown>>;
  started_at: string;
  ended_at?: string | null;
};

export type LiveEnvelope = {
  schema_version: string;
  seq: number;
  cursor_seq?: number | null;
  event_type: string;
  captured_at: string;
  requires_snapshot_reload: boolean;
  payload: ObservatorySnapshot | Record<string, unknown>;
};
