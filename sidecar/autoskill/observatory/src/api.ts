import type { LiveEnvelope, ObjectResponse, SearchResponse, SnapshotResponse } from "./types";

const API_BASE = import.meta.env.VITE_ADMIN_API_BASE ?? "/admin/api/v1";

export type ApiSession = {
  token: string;
  roles: string;
};

function headers(session: ApiSession): HeadersInit {
  return {
    Accept: "application/json",
    ...(session.token ? { Authorization: `Bearer ${session.token}` } : {}),
    ...(session.roles ? { "X-SkillKernel-Roles": session.roles } : {})
  };
}

async function fetchJson<T>(
  path: string,
  session: ApiSession,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...headers(session),
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers
    }
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${message}`);
  }
  return (await response.json()) as T;
}

export function fetchSummary(session: ApiSession, workspaceId: string, windowMinutes: number) {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  params.set("window_minutes", String(windowMinutes));
  return fetchJson<SnapshotResponse>(`/summary?${params.toString()}`, session);
}

export function fetchObject(
  session: ApiSession,
  objectType: string,
  objectId: string,
  workspaceId: string
) {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<ObjectResponse>(
    `/objects/${encodeURIComponent(objectType)}/${encodeURIComponent(objectId)}?${params}`,
    session
  );
}

export function search(session: ApiSession, query: string, workspaceId: string) {
  const params = new URLSearchParams({ query, limit: "20" });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<SearchResponse>(`/search?${params}`, session);
}

export function postAction(
  session: ApiSession,
  body: {
    workspace_id: string;
    action: string;
    idempotency_key: string;
    reason?: string;
    target?: Record<string, unknown>;
    metadata?: Record<string, unknown>;
  }
) {
  return fetchJson<{ receipt: Record<string, unknown> }>("/actions", session, {
    method: "POST",
    body: JSON.stringify({ dry_run: true, target: {}, metadata: {}, ...body })
  });
}

export function liveUrl(session: ApiSession, workspaceId: string, lastSeq?: number) {
  const url = new URL("/admin/live", window.location.origin.replace(/^http/, "ws"));
  if (session.token) url.searchParams.set("token", session.token);
  if (workspaceId) url.searchParams.set("workspace_id", workspaceId);
  if (lastSeq) url.searchParams.set("last_seq", String(lastSeq));
  return url.toString();
}

export function liveSseUrl(session: ApiSession, workspaceId: string, lastSeq?: number) {
  const url = new URL("/admin/live-sse", window.location.origin);
  if (session.token) url.searchParams.set("token", session.token);
  if (workspaceId) url.searchParams.set("workspace_id", workspaceId);
  if (lastSeq) url.searchParams.set("last_seq", String(lastSeq));
  return url.toString();
}

export function isSnapshotPayload(payload: LiveEnvelope["payload"]): payload is SnapshotResponse["snapshot"] {
  return typeof payload === "object" && payload !== null && "pipeline" in payload;
}
