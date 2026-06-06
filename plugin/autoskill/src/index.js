import {
  fetchContextHint,
  fetchCoreCompatibility,
  fetchStatus,
  forwardEvent,
  forwardEvents,
  recordActionAttributionCheck,
} from "./client/index.js";
import { resolveConfig } from "./config.js";
import { buildEventEnvelope } from "./event-envelope.js";
import { appendSpool, getSpoolStats, replaySpool } from "./spool/index.js";

let replayInFlight = false;
const compatibilityCache = new Map();

const CAPTURE_HOOKS = [
  ["after_tool_call", "tool_call_end", "tool_output", ["tool"]],
  ["before_tool_call", "tool_call_start", "agent_output", ["tool"]],
  ["gateway_start", "gateway_startup", "system_owned", ["gateway"]],
  ["llm_input", "llm_input", "agent_output", ["llm"]],
  ["llm_output", "llm_output", "agent_output", ["llm"]],
  ["message_received", "message_received", "external_content", ["message"]],
  ["message_sent", "message_sent", "agent_output", ["message"]],
  ["model_call_ended", "model_call_ended", "system_owned", ["model"]],
  ["model_call_started", "model_call_started", "system_owned", ["model"]],
  ["tool_result_persist", "tool_result_persist", "tool_output", ["tool"]],
];

export const id = "autoskill";
export const name = "AutoSkill Manager";

export function register(api) {
  for (const [hookName, eventType, trust, taint] of CAPTURE_HOOKS) {
    if (hookName === "before_tool_call") {
      api.on(hookName, (event, ctx) => beforeToolCall(event, ctx), {
        name: `autoskill-${eventType}`,
      });
      continue;
    }
    if (hookName === "tool_result_persist") {
      api.on(
        hookName,
        (event, ctx) => {
          void captureEvent({ eventType, payload: event, trust, taint, hookContext: ctx });
          return undefined;
        },
        { name: `autoskill-${eventType}` },
      );
      continue;
    }
    api.on(
      hookName,
      (event, ctx) => captureEvent({ eventType, payload: event, trust, taint, hookContext: ctx }),
      { name: `autoskill-${eventType}` },
    );
  }
  api.on(
    "before_prompt_build",
    (event, ctx) => maybeContextHint({ prompt: event?.prompt, hookContext: ctx }),
    { name: "autoskill-context-hint" },
  );
}

export default {
  id,
  name,
  register,
};

export async function captureEvent({ eventType, payload, trust, taint, hookContext }) {
  const config = resolveConfig(hookContext);
  if (!config.enabled) {
    return { captured: false, reason: "disabled" };
  }
  const rawCompatibility = await rawCaptureCompatibility(config);
  if (rawCompatibility?.compatible === false) {
    const envelope = buildEventEnvelope({
      eventType,
      payload,
      trust,
      taint,
      ctx: hookContext,
      config: { ...config, captureRawConversation: false },
    });
    envelope.payload = {
      ...envelope.payload,
      autoskill_raw_capture_degraded: {
        reason: rawCompatibility.reason,
      },
    };
    await appendSpool(config.spoolDir, envelope, { maxBytes: config.maxSpoolBytes });
    return {
      captured: true,
      forwarded: false,
      spooled: true,
      degraded: true,
      reason: "raw_capture_handshake_failed",
      eventId: envelope.event_id,
      error: rawCompatibility.reason,
    };
  }
  const envelope = buildEventEnvelope({ eventType, payload, trust, taint, ctx: hookContext, config });
  try {
    await forwardEvent(config.sidecarUrl, envelope, {
      timeoutMs: 500,
      authToken: config.ingestToken,
    });
  } catch (error) {
    await appendSpool(config.spoolDir, envelope, { maxBytes: config.maxSpoolBytes });
    return {
      captured: true,
      forwarded: false,
      spooled: true,
      eventId: envelope.event_id,
      error: String(error?.message ?? error),
    };
  }

  try {
    const replay = await replayCapturedSpool(config);
    return { captured: true, forwarded: true, eventId: envelope.event_id, replay };
  } catch (error) {
    return {
      captured: true,
      forwarded: true,
      eventId: envelope.event_id,
      replay: {
        failed: true,
        error: String(error?.message ?? error),
      },
    };
  }
}

export function clearCompatibilityHandshakeCache() {
  compatibilityCache.clear();
}

async function rawCaptureCompatibility(config) {
  if (!config.captureRawConversation) {
    return null;
  }
  const now = Date.now();
  const cacheKey = `${config.sidecarUrl}|${config.ingestToken ?? ""}`;
  const cached = compatibilityCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.result;
  }
  let result;
  try {
    result = await fetchCoreCompatibility(config.sidecarUrl, {
      timeoutMs: config.compatibilityHandshake.timeoutMs,
      authToken: config.ingestToken,
    });
  } catch (error) {
    result = {
      compatible: false,
      reason: `unreachable:${String(error?.message ?? error)}`,
    };
  }
  compatibilityCache.set(cacheKey, {
    result,
    expiresAt: now + Math.max(0, config.compatibilityHandshake.cacheTtlMs),
  });
  return result;
}

export async function beforeToolCall(event, hookContext) {
  const capture = await captureEvent({
    eventType: "tool_call_start",
    payload: event,
    trust: "agent_output",
    taint: ["tool"],
    hookContext,
  });
  const config = resolveConfig(hookContext);
  const decision = evaluateToolBoundary(event, config);
  if (!decision.block) {
    return capture;
  }
  let attributionCheck;
  try {
    attributionCheck = await recordBoundaryAttributionCheck(event, hookContext, config, decision);
  } catch (error) {
    attributionCheck = {
      recorded: false,
      error: String(error?.message ?? error),
    };
  }
  return {
    ...capture,
    block: true,
    blockReason: decision.reason,
    attributionCheck,
  };
}

export function evaluateToolBoundary(event, config = {}) {
  if (
    !config.enabled ||
    !config.runtimeToolBoundary?.enabled ||
    !config.runtimeToolBoundary?.blockOnHighRisk
  ) {
    return { block: false };
  }
  const text = JSON.stringify(event ?? {});
  const patterns = [
    {
      code: "dynamic-fetch-exec",
      pattern: /(curl|wget|fetch|Invoke-WebRequest).{0,120}(\|\s*(sh|bash|python)|eval|exec)/is,
    },
    {
      code: "destructive-host-command",
      pattern:
        /(\brm\s+-rf\s+\/(?:\s|$)|\bmkfs(?:\.\w+)?\b|\bdd\s+if=.{0,80}\s+of=\/dev\/|\bchmod\s+-R\s+777\s+\/|\bchown\s+-R\b.{0,80}\s+\/)/is,
    },
    {
      code: "credential-exfiltration",
      pattern:
        /\b(print|dump|exfiltrate|send|upload|post|log|copy|collect)\b.{0,100}\b(secret|token|password|api[_ -]?key|credential|authorization|ssh[_ -]?key)\b/is,
    },
    {
      code: "sensitive-file-harvest",
      pattern:
        /\b(read|cat|open|scan|index|embed|upload|copy)\b.{0,100}(~?\/\.ssh\b|\/etc\/shadow\b|\/etc\/passwd\b|\.env\b|credentials?\.(json|yaml|yml)\b)/is,
    },
  ];
  const match = patterns.find(({ pattern }) => pattern.test(text));
  if (!match) {
    return { block: false };
  }
  return {
    block: true,
    reason: `autoskill runtime tool boundary blocked ${match.code}`,
    code: match.code,
  };
}

async function recordBoundaryAttributionCheck(event, hookContext, config, decision) {
  const response = await recordActionAttributionCheck(
    config.sidecarUrl,
    {
      workspace_id: config.workspaceId,
      session_id: hookContext?.sessionId ?? null,
      turn_id: hookContext?.turnId ?? null,
      tool_call_id: event?.tool_call_id ?? event?.toolCallId ?? event?.id ?? null,
      action_kind: event?.tool ?? event?.name ?? event?.tool_name ?? "tool_call",
      risk_tier: "high",
      verdict: "blocked",
      counterfactual_kind: "runtime_boundary",
      metrics: {
        boundary_code: decision.code ?? "unknown",
        blocked: true,
        payload_keys: Object.keys(event ?? {}).sort(),
      },
    },
    { timeoutMs: 500, authToken: config.ingestToken },
  );
  return {
    recorded: true,
    actionAttributionCheckId: response?.check?.action_attribution_check_id ?? null,
  };
}

async function replayCapturedSpool(config) {
  if (replayInFlight) {
    return { skipped: true, reason: "already_running" };
  }
  replayInFlight = true;
  try {
    return await replaySpool(config.spoolDir, {
      batchSize: config.replayBatchSize,
      maxBytes: config.maxSpoolBytes,
      send: (events) =>
        forwardEvents(config.sidecarUrl, events, {
          timeoutMs: 1000,
          authToken: config.ingestToken,
        }),
    });
  } finally {
    replayInFlight = false;
  }
}

export async function maybeContextHint({ prompt, hookContext }) {
  const config = resolveConfig(hookContext);
  if (!config.enabled || !config.runtimeContextBroker.enabled) {
    return undefined;
  }
  try {
    const response = await fetchContextHint(
      config.sidecarUrl,
      {
        workspace_id: config.workspaceId,
        agent_id: hookContext?.agentId ?? null,
        session_id: hookContext?.sessionId ?? null,
        turn_id: hookContext?.turnId ?? null,
        user_intent: prompt ?? null,
        max_tokens: config.runtimeContextBroker.maxTokens,
      },
      { timeoutMs: config.runtimeContextBroker.timeoutMs, authToken: config.ingestToken },
    );
    if (!response?.hint) {
      return undefined;
    }
    return { appendContext: response.hint };
  } catch (error) {
    if (!config.runtimeContextBroker.failSoft) {
      throw error;
    }
    return undefined;
  }
}

export async function getPluginDiagnostics(hookContext) {
  const config = resolveConfig(hookContext);
  const spool = await getSpoolStats(config.spoolDir);
  let sidecar = { reachable: false };
  try {
    sidecar = {
      reachable: true,
      status: await fetchStatus(config.sidecarUrl, {
        timeoutMs: config.runtimeContextBroker.timeoutMs,
        authToken: config.ingestToken,
      }),
    };
  } catch (error) {
    sidecar = {
      reachable: false,
      error: String(error?.message ?? error),
    };
  }
  return {
    enabled: config.enabled,
    workspaceId: config.workspaceId,
    sidecarUrl: config.sidecarUrl,
    spool,
    sidecar,
    runtimeContextBroker: {
      enabled: config.runtimeContextBroker.enabled,
      maxTokens: config.runtimeContextBroker.maxTokens,
      timeoutMs: config.runtimeContextBroker.timeoutMs,
      failSoft: config.runtimeContextBroker.failSoft,
    },
  };
}
