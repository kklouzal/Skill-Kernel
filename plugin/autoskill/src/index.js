import { fetchContextHint, fetchStatus, forwardEvent, forwardEvents } from "./client/index.js";
import { resolveConfig } from "./config.js";
import { buildEventEnvelope } from "./event-envelope.js";
import { appendSpool, getSpoolStats, replaySpool } from "./spool/index.js";

let replayInFlight = false;

const CAPTURE_HOOKS = [
  ["after_tool_call", "tool_call_end", "trusted", ["tool"]],
  ["before_tool_call", "tool_call_start", "trusted", ["tool"]],
  ["gateway_start", "gateway_startup", "trusted", ["gateway"]],
  ["llm_input", "llm_input", "trusted", ["llm"]],
  ["llm_output", "llm_output", "trusted", ["llm"]],
  ["message_received", "message_received", "untrusted", ["message"]],
  ["message_sent", "message_sent", "trusted", ["message"]],
  ["model_call_ended", "model_call_ended", "trusted", ["model"]],
  ["model_call_started", "model_call_started", "trusted", ["model"]],
  ["tool_result_persist", "tool_result_persist", "trusted", ["tool"]],
];

export const id = "autoskill";
export const name = "AutoSkill Manager";
export const kind = "memory";

export function register(api) {
  for (const [hookName, eventType, trust, taint] of CAPTURE_HOOKS) {
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
  kind,
  register,
};

export async function captureEvent({ eventType, payload, trust, taint, hookContext }) {
  const config = resolveConfig(hookContext);
  if (!config.enabled) {
    return { captured: false, reason: "disabled" };
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
