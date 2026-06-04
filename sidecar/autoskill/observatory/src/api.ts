import type {
  CollectionResponse,
  LiveEnvelope,
  ObjectResponse,
  SearchResponse,
  SnapshotResponse,
  TraceSummary
} from "./types";
import { adminApiPath } from "./generated/observatoryClient";

const API_BASE = import.meta.env.VITE_ADMIN_API_BASE ?? "/admin/api/v1";
const CSRF_HEADER = "X-SkillKernel-CSRF";
const BROWSER_SESSION_HEADER = "X-SkillKernel-Browser-Session";

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

async function csrfToken(session: ApiSession): Promise<string> {
  const seed = session.token || "local-dev-admin";
  const bytes = new TextEncoder().encode(`skillkernel-observatory-csrf:${seed}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
}

async function fetchJson<T>(
  path: string,
  session: ApiSession,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...headers(session),
      "Cache-Control": "no-cache",
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
  return fetchJson<SnapshotResponse>(`${adminApiPath("/summary")}?${params.toString()}`, session);
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
    `${adminApiPath("/objects/{object_type}/{object_id}", {
      object_type: objectType,
      object_id: objectId
    })}?${params}`,
    session
  );
}

export function search(session: ApiSession, query: string, workspaceId: string) {
  const params = new URLSearchParams({ query, limit: "20" });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<SearchResponse>(`${adminApiPath("/search")}?${params}`, session);
}

export function fetchTraces(session: ApiSession, workspaceId: string, limit = 25) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<CollectionResponse<TraceSummary>>(
    `${adminApiPath("/traces")}?${params}`,
    session
  );
}

export function fetchSkills(session: ApiSession, workspaceId: string, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<CollectionResponse>(`${adminApiPath("/skills")}?${params}`, session);
}

export function fetchSkillDetail(session: ApiSession, skillId: string, workspaceId: string) {
  const params = new URLSearchParams();
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<ObjectResponse>(
    `${adminApiPath("/skills/{skill_id}", { skill_id: skillId })}?${params}`,
    session
  );
}

export function fetchTopology(session: ApiSession, workspaceId: string, windowMinutes: number) {
  const params = new URLSearchParams({ window_minutes: String(windowMinutes) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<ObjectResponse>(`${adminApiPath("/topology")}?${params}`, session);
}

export function fetchContextArtifacts(session: ApiSession, workspaceId: string, limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<CollectionResponse>(
    `${adminApiPath("/context/artifacts")}?${params}`,
    session
  );
}

export function fetchActionAudits(session: ApiSession, workspaceId: string, limit = 25) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<CollectionResponse>(
    `${adminApiPath("/actions/audit")}?${params}`,
    session
  );
}

export function fetchTraceReplay(
  session: ApiSession,
  traceId: string,
  workspaceId: string,
  limit = 100
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  return fetchJson<ObjectResponse>(
    `${adminApiPath("/replay/traces/{trace_id}", { trace_id: traceId })}?${params}`,
    session
  );
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
  return csrfToken(session).then((token) =>
    fetchJson<{ receipt: Record<string, unknown> }>(adminApiPath("/actions"), session, {
      method: "POST",
      headers: {
        [BROWSER_SESSION_HEADER]: "true",
        [CSRF_HEADER]: token
      },
      body: JSON.stringify({ dry_run: true, target: {}, metadata: {}, ...body })
    })
  );
}

export async function streamLive(
  session: ApiSession,
  workspaceId: string,
  lastSeq: number | undefined,
  {
    onEnvelope,
    onOpen,
    signal
  }: {
    onEnvelope: (envelope: LiveEnvelope) => void;
    onOpen: () => void;
    signal: AbortSignal;
  }
) {
  const url = new URL("/admin/live-sse", window.location.origin);
  if (workspaceId) url.searchParams.set("workspace_id", workspaceId);
  if (lastSeq) url.searchParams.set("last_seq", String(lastSeq));
  const response = await fetch(url, {
    cache: "no-store",
    headers: headers(session),
    signal
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${message}`);
  }
  if (!response.body) {
    throw new Error("Live stream response did not include a readable body");
  }
  onOpen();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice("data:".length).trimStart())
        .join("\n");
      if (data) onEnvelope(JSON.parse(data) as LiveEnvelope);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export function isSnapshotPayload(payload: LiveEnvelope["payload"]): payload is SnapshotResponse["snapshot"] {
  return typeof payload === "object" && payload !== null && "pipeline" in payload;
}
